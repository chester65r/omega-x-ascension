from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

import anyio
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omega_api.config import Settings
from omega_api.db import get_db, initialize_schema, make_engine, make_session_factory
from omega_api.models import Conversation, Message, UsageRecord, User
from omega_api.provider import OpenAICompatibleProvider, ProviderError
from omega_api.schemas import (
    ChatResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationPatch,
    ConversationRead,
    LoginRequest,
    MessageCreate,
    MessageRead,
    RegisterRequest,
    TokenResponse,
    UsageSummary,
)
from omega_api.security import create_access_token, decode_access_token, hash_password, verify_password

bearer = HTTPBearer(auto_error=False)


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
        }

    @app.post('/api/v1/auth/register', response_model=TokenResponse, status_code=status.HTTP_201_CREATED, tags=['authentication'])
    async def register(payload: RegisterRequest, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
        exists = await db.scalar(select(User.id).where(User.email == payload.email))
        if exists:
            raise HTTPException(status_code=409, detail='An account with this email already exists')
        password_hash = await anyio.to_thread.run_sync(hash_password, payload.password)
        user = User(email=payload.email, password_hash=password_hash)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        token = create_access_token(user.id, request.app.state.settings.jwt_secret.get_secret_value(), request.app.state.settings.access_token_ttl_seconds, user.token_version)
        return TokenResponse(access_token=token, expires_in=request.app.state.settings.access_token_ttl_seconds)

    @app.post('/api/v1/auth/login', response_model=TokenResponse, tags=['authentication'])
    async def login(payload: LoginRequest, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
        user = await db.scalar(select(User).where(User.email == payload.email))
        if user is None or not await anyio.to_thread.run_sync(verify_password, payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail='Invalid email or password', headers={'WWW-Authenticate': 'Bearer'})
        token = create_access_token(user.id, request.app.state.settings.jwt_secret.get_secret_value(), request.app.state.settings.access_token_ttl_seconds, user.token_version)
        return TokenResponse(access_token=token, expires_in=request.app.state.settings.access_token_ttl_seconds)

    @app.post('/api/v1/auth/logout', status_code=204, tags=['authentication'])
    async def logout(user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
        user.token_version += 1
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
            statement = statement.where(Conversation.title.ilike(f'%{q.strip()}%'))
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
            {'role': 'system', 'content': 'You are Omega X Ascension, a helpful AI assistant. Be clear about uncertainty and never claim to have used tools or services unless you actually did.'},
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

    return app


app = create_app()
