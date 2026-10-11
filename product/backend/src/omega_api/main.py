from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from secrets import token_urlsafe
from typing import Annotated

import anyio
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omega_api.config import Settings
from omega_api.db import get_db, initialize_schema, make_engine, make_session_factory
from omega_api.models import AuditEvent, Conversation, Message, Project, ProjectCheckpoint, ProjectFile, UsageRecord, User
from omega_api.provider import OpenAICompatibleProvider, ProviderError
from omega_api.rate_limit import enforce_auth_rate_limit
from omega_api.schemas import (
    AccountDeleteRequest,
    ChatResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationPatch,
    ConversationRead,
    LoginRequest,
    MessageCreate,
    MessageRead,
    ProjectCheckpointCreate,
    ProjectCheckpointRead,
    ProjectCreate,
    ProjectDiffResponse,
    ProjectFileRead,
    ProjectFileSummary,
    ProjectFileWrite,
    ProjectRead,
    RegisterRequest,
    TokenResponse,
    UsageSummary,
)
from omega_api.security import create_access_token, decode_access_token, hash_password, verify_password
from omega_api.workspace import WorkspaceInputError, build_project_diff, normalize_project_path

bearer = HTTPBearer(auto_error=False)
_DUMMY_PASSWORD_HASH = hash_password(token_urlsafe(32))
MAX_PROJECTS_PER_USER = 10
MAX_FILES_PER_PROJECT = 100
MAX_FILE_BYTES = 512 * 1024
MAX_PROJECT_BYTES = 2 * 1024 * 1024
MAX_PROJECT_CHECKPOINTS = 3
MAX_DIFF_BYTES = 256 * 1024

RESPONSE_MODE_INSTRUCTIONS = {
    'balanced': "Respond clearly and directly, matching the user's language and desired level of detail.",
    'explain': 'Teach the topic step by step, define unfamiliar terms, and use a small example when it helps.',
    'concise': 'Keep the answer brief and focused; use only the details needed to answer the request.',
    'writing': 'Help produce polished, audience-appropriate writing. Preserve the user’s intent and do not invent facts.',
    'coding': 'Prioritize accurate programming guidance, show practical code when appropriate, and state assumptions or risks.',
}


def get_provider(request: Request) -> OpenAICompatibleProvider:
    return request.app.state.provider


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != 'bearer':
        raise HTTPException(status_code=401, detail='Authentication required', headers={'WWW-Authenticate': 'Bearer'})
    try:
        claims = decode_access_token(credentials.credentials, request.app.state.settings.jwt_secret.get_secret_value())
    except ValueError:
        raise HTTPException(status_code=401, detail='Invalid or expired access token', headers={'WWW-Authenticate': 'Bearer'}) from None
    user = await db.scalar(select(User).where(User.id == claims['sub']))
    if user is None:
        raise HTTPException(status_code=401, detail='Account no longer exists', headers={'WWW-Authenticate': 'Bearer'})
    if claims.get('ver', 0) != user.token_version:
        raise HTTPException(status_code=401, detail='Session has been revoked', headers={'WWW-Authenticate': 'Bearer'})
    return user


def _conversation_read(row: Conversation) -> ConversationRead:
    return ConversationRead.model_validate(row)


async def _owned_conversation(db: AsyncSession, user_id: str, conversation_id: str) -> Conversation:
    row = await db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail='Conversation not found')
    return row


async def _owned_project(db: AsyncSession, user_id: str, project_id: str, *, lock: bool = False) -> Project:
    statement = select(Project).where(Project.id == project_id, Project.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    row = await db.scalar(statement)
    if row is None:
        raise HTTPException(status_code=404, detail='Project not found')
    return row


async def _project_file_bytes(db: AsyncSession, project_id: str, *, excluding_id: str | None = None) -> int:
    statement = select(ProjectFile.content).where(ProjectFile.project_id == project_id)
    if excluding_id is not None:
        statement = statement.where(ProjectFile.id != excluding_id)
    contents = (await db.scalars(statement)).all()
    return sum(len(content.encode('utf-8')) for content in contents)


async def _check_auth_rate_limit(request: Request, db: AsyncSession, email: str) -> None:
    settings = request.app.state.settings
    client_ip = request.client.host if request.client else 'unknown'
    await enforce_auth_rate_limit(
        db,
        email=email,
        client_ip=client_ip,
        secret=settings.jwt_secret.get_secret_value(),
        email_limit=settings.auth_rate_email_limit,
        ip_limit=settings.auth_rate_ip_limit,
        window_seconds=settings.auth_rate_window_seconds,
    )


def _audit_subject_hash(secret: str, user_id: str) -> str:
    return hmac.new(secret.encode('utf-8'), f'audit:{user_id}'.encode('utf-8'), hashlib.sha256).hexdigest()


async def _add_audit_event(db: AsyncSession, request: Request, user_id: str, event_type: str) -> None:
    secret = request.app.state.settings.jwt_secret.get_secret_value()
    db.add(AuditEvent(subject_hash=_audit_subject_hash(secret, user_id), event_type=event_type))
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    await db.execute(delete(AuditEvent).where(AuditEvent.created_at < cutoff))


def _export_line(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n'


async def _stream_account_export(session_factory, user_id: str):
    """Stream an account-scoped NDJSON export with bounded page memory."""
    async with session_factory() as export_db:
        user = await export_db.scalar(select(User).where(User.id == user_id))
        if user is None:
            return
        yield _export_line({
            'type': 'account',
            'id': user.id,
            'email': user.email,
            'created_at': user.created_at.isoformat(),
            'exported_at': datetime.now(timezone.utc).isoformat(),
        })

        last_id = ''
        while True:
            rows = (await export_db.scalars(
                select(Conversation).where(
                    Conversation.user_id == user_id,
                    Conversation.id > last_id,
                ).order_by(Conversation.id).limit(250)
            )).all()
            if not rows:
                break
            for row in rows:
                yield _export_line({
                    'type': 'conversation',
                    'id': row.id,
                    'title': row.title,
                    'created_at': row.created_at.isoformat(),
                    'updated_at': row.updated_at.isoformat(),
                })
            last_id = rows[-1].id

        last_id = ''
        while True:
            rows = (await export_db.scalars(
                select(Message).where(
                    Message.user_id == user_id,
                    Message.id > last_id,
                ).order_by(Message.id).limit(500)
            )).all()
            if not rows:
                break
            for row in rows:
                yield _export_line({
                    'type': 'message',
                    'id': row.id,
                    'conversation_id': row.conversation_id,
                    'role': row.role,
                    'content': row.content,
                    'created_at': row.created_at.isoformat(),
                })
            last_id = rows[-1].id

        last_id = ''
        while True:
            rows = (await export_db.scalars(
                select(UsageRecord).where(
                    UsageRecord.user_id == user_id,
                    UsageRecord.id > last_id,
                ).order_by(UsageRecord.id).limit(500)
            )).all()
            if not rows:
                break
            for row in rows:
                yield _export_line({
                    'type': 'usage',
                    'id': row.id,
                    'conversation_id': row.conversation_id,
                    'model': row.model,
                    'prompt_tokens': row.prompt_tokens,
                    'completion_tokens': row.completion_tokens,
                    'created_at': row.created_at.isoformat(),
                })
            last_id = rows[-1].id

        last_id = ''
        while True:
            rows = (await export_db.scalars(
                select(Project).where(Project.user_id == user_id, Project.id > last_id)
                .order_by(Project.id).limit(100)
            )).all()
            if not rows:
                break
            for row in rows:
                yield _export_line({
                    'type': 'project', 'id': row.id, 'name': row.name,
                    'description': row.description, 'created_at': row.created_at.isoformat(),
                    'updated_at': row.updated_at.isoformat(),
                })
            last_id = rows[-1].id

        last_id = ''
        while True:
            rows = (await export_db.scalars(
                select(ProjectFile).join(Project, Project.id == ProjectFile.project_id)
                .where(Project.user_id == user_id, ProjectFile.id > last_id)
                .order_by(ProjectFile.id).limit(100)
            )).all()
            if not rows:
                break
            for row in rows:
                yield _export_line({
                    'type': 'project_file', 'id': row.id, 'project_id': row.project_id,
                    'path': row.path, 'content': row.content, 'revision': row.revision,
                    'created_at': row.created_at.isoformat(), 'updated_at': row.updated_at.isoformat(),
                })
            last_id = rows[-1].id

        last_id = ''
        while True:
            rows = (await export_db.scalars(
                select(ProjectCheckpoint).join(Project, Project.id == ProjectCheckpoint.project_id)
                .where(Project.user_id == user_id, ProjectCheckpoint.id > last_id)
                .order_by(ProjectCheckpoint.id).limit(100)
            )).all()
            if not rows:
                break
            for row in rows:
                yield _export_line({
                    'type': 'project_checkpoint', 'id': row.id, 'project_id': row.project_id,
                    'label': row.label, 'snapshot': row.snapshot, 'created_at': row.created_at.isoformat(),
                })
            last_id = rows[-1].id


async def _account_export_exceeds_limit(session_factory, user_id: str, max_bytes: int) -> bool:
    """Preflight a bounded mobile share export without retaining its body in memory."""
    stream = _stream_account_export(session_factory, user_id)
    total_bytes = 0
    try:
        async for line in stream:
            total_bytes += len(line.encode('utf-8'))
            if total_bytes > max_bytes:
                return True
        return False
    finally:
        await stream.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.auto_create_schema and settings.environment.lower() != 'production':
            await initialize_schema(engine)
        yield
        await engine.dispose()

    app = FastAPI(
        title=settings.service_name,
        version='0.1.0',
        description='Authenticated chat, conversation persistence, and provider-independent model access.',
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.provider = OpenAICompatibleProvider(settings)

    @app.middleware('http')
    async def security_response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/health/live', tags=['diagnostics'])
    async def live():
        return {'status': 'alive'}

    @app.get('/health/ready', tags=['diagnostics'])
    async def ready(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
        try:
            await db.execute(text('SELECT 1'))
        except Exception:
            raise HTTPException(status_code=503, detail='Database is unavailable') from None
        provider = request.app.state.provider
        configured = provider.configured
        return {
            'status': 'ready' if configured else 'degraded',
            'database': 'connected',
            'model_provider_configured': configured,
            'model': request.app.state.settings.model or None,
            'capabilities': {
                'response_modes': True,
                'message_content_search': True,
                'account_export': True,
                'account_deletion': True,
                'auth_rate_limiting': True,
                'project_workspace': True,
                'project_checkpoint_diff': True,
                'isolated_execution': False,
                'browser_automation': False,
                'agent_tasks': False,
            },
        }

    @app.post('/api/v1/auth/register', response_model=TokenResponse, status_code=status.HTTP_201_CREATED, tags=['authentication'])
    async def register(payload: RegisterRequest, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
        await _check_auth_rate_limit(request, db, payload.email)
        exists = await db.scalar(select(User.id).where(User.email == payload.email))
        if exists:
            raise HTTPException(status_code=409, detail='An account with this email already exists')
        password_hash = await anyio.to_thread.run_sync(hash_password, payload.password)
        user = User(email=payload.email, password_hash=password_hash)
        db.add(user)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=409, detail='An account with this email already exists') from None
        await db.refresh(user)
        token = create_access_token(user.id, request.app.state.settings.jwt_secret.get_secret_value(), request.app.state.settings.access_token_ttl_seconds, user.token_version)
        return TokenResponse(access_token=token, expires_in=request.app.state.settings.access_token_ttl_seconds)

    @app.post('/api/v1/auth/login', response_model=TokenResponse, tags=['authentication'])
    async def login(payload: LoginRequest, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
        await _check_auth_rate_limit(request, db, payload.email)
        user = await db.scalar(select(User).where(User.email == payload.email))
        stored_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
        password_is_valid = await anyio.to_thread.run_sync(verify_password, payload.password, stored_hash)
        if user is None or not password_is_valid:
            raise HTTPException(status_code=401, detail='Invalid email or password', headers={'WWW-Authenticate': 'Bearer'})
        token = create_access_token(user.id, request.app.state.settings.jwt_secret.get_secret_value(), request.app.state.settings.access_token_ttl_seconds, user.token_version)
        return TokenResponse(access_token=token, expires_in=request.app.state.settings.access_token_ttl_seconds)

    @app.post('/api/v1/auth/logout', status_code=204, tags=['authentication'])
    async def logout(request: Request, user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
        user.token_version += 1
        await _add_audit_event(db, request, user.id, 'sessions_revoked')
        await db.commit()
        return Response(status_code=204)

    @app.get(
        '/api/v1/account/export',
        response_class=StreamingResponse,
        tags=['account'],
        responses={200: {
            'description': 'Account export in newline-delimited JSON format',
            'content': {'application/x-ndjson': {'schema': {'type': 'string'}}},
        }},
    )
    async def export_account(
        request: Request,
        user: Annotated[User, Depends(get_current_user)],
        max_bytes: int | None = Query(default=None, ge=1, le=50_000_000),
    ):
        factory = request.app.state.session_factory
        if max_bytes is not None and await _account_export_exceeds_limit(factory, user.id, max_bytes):
            raise HTTPException(status_code=413, detail='Account export exceeds the requested download limit')
        return StreamingResponse(
            _stream_account_export(factory, user.id),
            media_type='application/x-ndjson',
            headers={'Content-Disposition': 'attachment; filename="omega-x-ascension-export.ndjson"'},
        )

    @app.delete('/api/v1/account', status_code=204, tags=['account'])
    async def delete_account(
        request: Request,
        payload: AccountDeleteRequest,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        valid_password = await anyio.to_thread.run_sync(verify_password, payload.password, user.password_hash)
        if not valid_password:
            raise HTTPException(status_code=403, detail='Current password is incorrect')
        await _add_audit_event(db, request, user.id, 'account_deleted')
        await db.delete(user)
        await db.commit()
        return Response(status_code=204)

    @app.get('/api/v1/conversations', response_model=list[ConversationRead], tags=['conversations'])
    async def list_conversations(
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
        q: str | None = Query(default=None, max_length=120),
        limit: int = Query(default=50, ge=1, le=100),
    ):
        statement = select(Conversation).where(Conversation.user_id == user.id)
        if q and q.strip():
            term = q.strip()
            statement = statement.where(or_(
                Conversation.title.ilike(f'%{term}%'),
                Conversation.messages.any(Message.content.ilike(f'%{term}%')),
            ))
        rows = (await db.scalars(statement.order_by(Conversation.updated_at.desc()).limit(limit))).all()
        return [_conversation_read(row) for row in rows]

    @app.post('/api/v1/conversations', response_model=ConversationRead, status_code=201, tags=['conversations'])
    async def create_conversation(
        payload: ConversationCreate,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        row = Conversation(user_id=user.id, title=payload.title)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return _conversation_read(row)

    @app.get('/api/v1/conversations/{conversation_id}', response_model=ConversationDetail, tags=['conversations'])
    async def get_conversation(
        conversation_id: str,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        row = await db.scalar(
            select(Conversation).options(selectinload(Conversation.messages)).where(
                Conversation.id == conversation_id, Conversation.user_id == user.id
            )
        )
        if row is None:
            raise HTTPException(status_code=404, detail='Conversation not found')
        return ConversationDetail.model_validate(row)

    @app.patch('/api/v1/conversations/{conversation_id}', response_model=ConversationRead, tags=['conversations'])
    async def rename_conversation(
        conversation_id: str,
        payload: ConversationPatch,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        row = await _owned_conversation(db, user.id, conversation_id)
        row.title = payload.title
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
        return _conversation_read(row)

    @app.delete('/api/v1/conversations/{conversation_id}', status_code=204, tags=['conversations'])
    async def delete_conversation(
        conversation_id: str,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        row = await _owned_conversation(db, user.id, conversation_id)
        await db.delete(row)
        await db.commit()
        return Response(status_code=204)

    @app.post('/api/v1/conversations/{conversation_id}/messages', response_model=ChatResponse, tags=['chat'])
    async def send_message(
        conversation_id: str,
        payload: MessageCreate,
        request: Request,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
        provider: Annotated[OpenAICompatibleProvider, Depends(get_provider)],
    ):
        conversation = await _owned_conversation(db, user.id, conversation_id)
        history = list((await db.scalars(
            select(Message).where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc()).limit(80)
        )).all())
        history.reverse()
        model_messages = [
            {'role': 'system', 'content': 'You are Omega X Ascension, a helpful AI assistant. Respond in the user’s language unless they ask otherwise. Be clear about uncertainty and never claim to have used tools or services unless you actually did. ' + RESPONSE_MODE_INSTRUCTIONS[payload.response_mode]},
            *({'role': item.role, 'content': item.content} for item in history),
            {'role': 'user', 'content': payload.content},
        ]
        try:
            completion = await provider.complete(model_messages)
        except ProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None

        user_message = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role='user',
            content=payload.content,
            client_request_id=str(payload.request_id),
        )
        assistant_message = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role='assistant',
            content=completion.content,
        )
        conversation.updated_at = datetime.now(timezone.utc)
        if conversation.title == 'New conversation':
            conversation.title = payload.content[:60].strip() or 'New conversation'
        db.add_all([user_message, assistant_message])
        db.add(UsageRecord(
            user_id=user.id,
            conversation_id=conversation.id,
            model=completion.model,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
        ))
        await db.commit()
        await db.refresh(user_message)
        await db.refresh(assistant_message)
        return ChatResponse(
            conversation_id=conversation.id,
            user_message=MessageRead.model_validate(user_message),
            assistant_message=MessageRead.model_validate(assistant_message),
            model=completion.model,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
        )

    @app.get('/api/v1/usage', response_model=UsageSummary, tags=['usage'])
    async def usage(
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        requests, prompt_tokens, completion_tokens = (await db.execute(
            select(
                func.count(UsageRecord.id),
                func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
                func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
            ).where(UsageRecord.user_id == user.id)
        )).one()
        return UsageSummary(
            requests=int(requests),
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
        )

    @app.get('/api/v1/projects', response_model=list[ProjectRead], tags=['projects'])
    async def list_projects(
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        return (await db.scalars(
            select(Project).where(Project.user_id == user.id)
            .order_by(Project.updated_at.desc(), Project.id).limit(MAX_PROJECTS_PER_USER)
        )).all()

    @app.post('/api/v1/projects', response_model=ProjectRead, status_code=201, tags=['projects'])
    async def create_project(
        payload: ProjectCreate,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        await db.scalar(select(User.id).where(User.id == user.id).with_for_update())
        count = await db.scalar(select(func.count(Project.id)).where(Project.user_id == user.id))
        if int(count or 0) >= MAX_PROJECTS_PER_USER:
            raise HTTPException(status_code=429, detail=f'Project limit reached ({MAX_PROJECTS_PER_USER} per account).')
        row = Project(user_id=user.id, name=payload.name, description=payload.description.strip())
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @app.delete('/api/v1/projects/{project_id}', status_code=204, tags=['projects'])
    async def delete_project(
        project_id: str,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        project = await _owned_project(db, user.id, project_id)
        await db.delete(project)
        await db.commit()
        return Response(status_code=204)

    @app.get('/api/v1/projects/{project_id}/files', response_model=list[ProjectFileSummary], tags=['projects'])
    async def list_project_files(
        project_id: str,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        await _owned_project(db, user.id, project_id)
        rows = (await db.scalars(
            select(ProjectFile).where(ProjectFile.project_id == project_id)
            .order_by(ProjectFile.path).limit(MAX_FILES_PER_PROJECT)
        )).all()
        return [ProjectFileSummary(
            path=row.path, size_bytes=len(row.content.encode('utf-8')),
            revision=row.revision, updated_at=row.updated_at,
        ) for row in rows]

    @app.get('/api/v1/projects/{project_id}/files/{file_path:path}', response_model=ProjectFileRead, tags=['projects'])
    async def read_project_file(
        project_id: str,
        file_path: str,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        try:
            safe_path = normalize_project_path(file_path)
        except WorkspaceInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        await _owned_project(db, user.id, project_id)
        row = await db.scalar(select(ProjectFile).where(
            ProjectFile.project_id == project_id, ProjectFile.path == safe_path,
        ))
        if row is None:
            raise HTTPException(status_code=404, detail='Project file not found')
        return ProjectFileRead(
            path=row.path, content=row.content, revision=row.revision,
            created_at=row.created_at, updated_at=row.updated_at,
        )

    @app.put('/api/v1/projects/{project_id}/files/{file_path:path}', response_model=ProjectFileRead, tags=['projects'])
    async def write_project_file(
        project_id: str,
        file_path: str,
        payload: ProjectFileWrite,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        try:
            safe_path = normalize_project_path(file_path)
        except WorkspaceInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        content_bytes = len(payload.content.encode('utf-8'))
        if content_bytes > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f'File exceeds the {MAX_FILE_BYTES}-byte limit.')
        project = await _owned_project(db, user.id, project_id, lock=True)
        existing = await db.scalar(select(ProjectFile).where(
            ProjectFile.project_id == project_id, ProjectFile.path == safe_path,
        ))
        if existing is None:
            if payload.expected_revision is not None:
                raise HTTPException(status_code=409, detail='The file does not exist; reload the project before creating it.')
            count = await db.scalar(select(func.count(ProjectFile.id)).where(ProjectFile.project_id == project_id))
            if int(count or 0) >= MAX_FILES_PER_PROJECT:
                raise HTTPException(status_code=429, detail=f'File limit reached ({MAX_FILES_PER_PROJECT} per project).')
            if await _project_file_bytes(db, project_id) + content_bytes > MAX_PROJECT_BYTES:
                raise HTTPException(status_code=413, detail=f'Project storage exceeds the {MAX_PROJECT_BYTES}-byte limit.')
            row = ProjectFile(project_id=project_id, path=safe_path, content=payload.content, revision=1)
            db.add(row)
        else:
            if payload.expected_revision is None:
                raise HTTPException(status_code=428, detail='expected_revision is required when replacing an existing file.')
            if payload.expected_revision != existing.revision:
                raise HTTPException(status_code=409, detail='File revision changed; reload before saving.')
            if await _project_file_bytes(db, project_id, excluding_id=existing.id) + content_bytes > MAX_PROJECT_BYTES:
                raise HTTPException(status_code=413, detail=f'Project storage exceeds the {MAX_PROJECT_BYTES}-byte limit.')
            existing.content = payload.content
            existing.revision += 1
            existing.updated_at = datetime.now(timezone.utc)
            row = existing
        project.updated_at = datetime.now(timezone.utc)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=409, detail='A concurrent file update conflicted; reload and retry.') from None
        await db.refresh(row)
        return ProjectFileRead(
            path=row.path, content=row.content, revision=row.revision,
            created_at=row.created_at, updated_at=row.updated_at,
        )

    @app.delete('/api/v1/projects/{project_id}/files/{file_path:path}', status_code=204, tags=['projects'])
    async def delete_project_file(
        project_id: str,
        file_path: str,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        try:
            safe_path = normalize_project_path(file_path)
        except WorkspaceInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        project = await _owned_project(db, user.id, project_id, lock=True)
        row = await db.scalar(select(ProjectFile).where(
            ProjectFile.project_id == project_id, ProjectFile.path == safe_path,
        ))
        if row is None:
            raise HTTPException(status_code=404, detail='Project file not found')
        await db.delete(row)
        project.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return Response(status_code=204)

    @app.post('/api/v1/projects/{project_id}/checkpoints', response_model=ProjectCheckpointRead, status_code=201, tags=['projects'])
    async def create_project_checkpoint(
        project_id: str,
        payload: ProjectCheckpointCreate,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        await _owned_project(db, user.id, project_id, lock=True)
        rows = (await db.scalars(
            select(ProjectFile).where(ProjectFile.project_id == project_id).order_by(ProjectFile.path)
        )).all()
        if sum(len(row.content.encode('utf-8')) for row in rows) > MAX_PROJECT_BYTES:
            raise HTTPException(status_code=413, detail='Project is too large to checkpoint.')
        checkpoint = ProjectCheckpoint(
            project_id=project_id, label=payload.label,
            snapshot={row.path: row.content for row in rows},
        )
        db.add(checkpoint)
        await db.flush()
        old_rows = (await db.scalars(
            select(ProjectCheckpoint).where(ProjectCheckpoint.project_id == project_id)
            .order_by(ProjectCheckpoint.created_at.desc(), ProjectCheckpoint.id.desc())
            .offset(MAX_PROJECT_CHECKPOINTS)
        )).all()
        for old in old_rows:
            await db.delete(old)
        await db.commit()
        await db.refresh(checkpoint)
        return checkpoint

    @app.get('/api/v1/projects/{project_id}/checkpoints', response_model=list[ProjectCheckpointRead], tags=['projects'])
    async def list_project_checkpoints(
        project_id: str,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        await _owned_project(db, user.id, project_id)
        return (await db.scalars(
            select(ProjectCheckpoint).where(ProjectCheckpoint.project_id == project_id)
            .order_by(ProjectCheckpoint.created_at.desc(), ProjectCheckpoint.id.desc())
            .limit(MAX_PROJECT_CHECKPOINTS)
        )).all()

    @app.get('/api/v1/projects/{project_id}/diff', response_model=ProjectDiffResponse, tags=['projects'])
    async def project_checkpoint_diff(
        project_id: str,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
        checkpoint_id: str = Query(min_length=1, max_length=36),
    ):
        await _owned_project(db, user.id, project_id)
        checkpoint = await db.scalar(select(ProjectCheckpoint).where(
            ProjectCheckpoint.id == checkpoint_id,
            ProjectCheckpoint.project_id == project_id,
        ))
        if checkpoint is None:
            raise HTTPException(status_code=404, detail='Project checkpoint not found')
        rows = (await db.scalars(select(ProjectFile).where(ProjectFile.project_id == project_id))).all()
        changes = build_project_diff(checkpoint.snapshot, {row.path: row.content for row in rows})
        if sum(len(item['diff'].encode('utf-8')) for item in changes) > MAX_DIFF_BYTES:
            raise HTTPException(status_code=413, detail='Diff exceeds the response-size limit; compare fewer or smaller files.')
        return ProjectDiffResponse(checkpoint_id=checkpoint.id, changes=changes)

    return app


app = create_app()
