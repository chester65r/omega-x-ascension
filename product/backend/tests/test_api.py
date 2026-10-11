import json
import sqlite3

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from omega_api.config import Settings
from omega_api.main import create_app, get_provider
from omega_api.provider import Completion, ProviderNotConfigured
from omega_api.workspace import WorkspaceInputError, build_project_diff, normalize_project_path


class FakeProvider:
    configured = True
    last_messages = []

    async def complete(self, messages):
        FakeProvider.last_messages = messages
        assert messages[-1]['role'] == 'user'
        return Completion('A real test-provider response.', 'test/model', 12, 7)


class UnconfiguredProvider:
    configured = False

    async def complete(self, messages):
        raise ProviderNotConfigured('The server model provider is not configured.')


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        jwt_secret=SecretStr('test-secret-that-is-at-least-thirty-two-chars'),
        auto_create_schema=True,
        environment='test',
        provider_api_key=SecretStr('test-only-key'),
        model='test/model',
    )
    app = create_app(settings)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, email='person@example.com') -> str:
    response = client.post('/api/v1/auth/register', json={'email': email, 'password': 'correct horse battery staple'})
    assert response.status_code == 201, response.text
    token = response.json()['access_token']
    return token


def auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_liveness_and_readiness(client):
    live = client.get('/health/live')
    assert live.json() == {'status': 'alive'}
    assert live.headers['x-content-type-options'] == 'nosniff'
    assert live.headers['x-frame-options'] == 'DENY'
    assert live.headers['cache-control'] == 'no-store'
    ready = client.get('/health/ready')
    assert ready.status_code == 200
    assert ready.json()['database'] == 'connected'
    assert ready.json()['capabilities']['response_modes'] is True
    assert ready.json()['capabilities']['message_content_search'] is True
    assert ready.json()['capabilities']['auth_rate_limiting'] is True
    assert ready.json()['capabilities']['account_export'] is True
    assert ready.json()['capabilities']['account_deletion'] is True
    assert ready.json()['capabilities']['project_workspace'] is True
    assert ready.json()['capabilities']['project_checkpoint_diff'] is True
    assert ready.json()['capabilities']['agent_tasks'] is False
    assert ready.json()['capabilities']['browser_automation'] is False
    assert ready.json()['capabilities']['isolated_execution'] is False
    schema = client.get('/openapi.json').json()
    assert '/api/v1/account/export' in schema['paths']
    assert 'application/x-ndjson' in schema['paths']['/api/v1/account/export']['get']['responses']['200']['content']
    assert '/api/v1/account' in schema['paths']


def test_registration_login_and_password_hashing(client):
    response = client.post('/api/v1/auth/register', json={'email': ' A@Example.com ', 'password': 'correct horse battery staple'})
    assert response.status_code == 201
    assert response.json()['token_type'] == 'bearer'
    duplicate = client.post('/api/v1/auth/register', json={'email': 'a@example.com', 'password': 'correct horse battery staple'})
    assert duplicate.status_code == 409
    login = client.post('/api/v1/auth/login', json={'email': 'a@example.com', 'password': 'correct horse battery staple'})
    assert login.status_code == 200
    assert client.post('/api/v1/auth/login', json={'email': 'a@example.com', 'password': 'wrong-password'}).status_code == 401


def test_logout_revokes_all_active_tokens(client):
    token = register(client)
    password = 'correct horse battery staple'
    second_token = client.post('/api/v1/auth/login', json={'email': 'person@example.com', 'password': password}).json()['access_token']
    assert client.post('/api/v1/auth/logout', headers=auth(token)).status_code == 204
    assert client.get('/api/v1/conversations', headers=auth(token)).status_code == 401
    assert client.get('/api/v1/conversations', headers=auth(second_token)).status_code == 401
    fresh_token = client.post('/api/v1/auth/login', json={'email': 'person@example.com', 'password': password}).json()['access_token']
    assert client.get('/api/v1/conversations', headers=auth(fresh_token)).status_code == 200


def test_password_policy_and_auth_required(client):
    assert client.post('/api/v1/auth/register', json={'email': 'bad@example.com', 'password': 'short'}).status_code == 422
    assert client.get('/api/v1/conversations').status_code == 401


def test_authentication_attempts_are_rate_limited(client):
    for _ in range(8):
        failed = client.post('/api/v1/auth/login', json={'email': 'limited@example.com', 'password': 'wrong-password'})
        assert failed.status_code == 401
    limited = client.post('/api/v1/auth/login', json={'email': 'limited@example.com', 'password': 'wrong-password'})
    assert limited.status_code == 429
    assert int(limited.headers['retry-after']) > 0
    with sqlite3.connect(client.app.state.engine.url.database) as connection:
        stored_keys = [row[0] for row in connection.execute('SELECT key_hash FROM auth_rate_limit_buckets')]
    assert 'limited@example.com' not in stored_keys


def test_chat_persists_per_user_and_tracks_usage(client):
    token = register(client)
    headers = auth(token)
    created = client.post('/api/v1/conversations', headers=headers, json={'title': 'Planning'})
    assert created.status_code == 201
    conversation_id = created.json()['id']
    response = client.post(
        f'/api/v1/conversations/{conversation_id}/messages',
        headers=headers,
        json={'content': 'Give me a short plan.', 'response_mode': 'explain', 'request_id': '327bbffc-ec4c-4e2e-a8ac-c2b9ca661ee1'},
    )
    assert response.status_code == 200, response.text
    assert response.json()['assistant_message']['content'] == 'A real test-provider response.'
    assert 'step by step' in FakeProvider.last_messages[0]['content']
    detail = client.get(f'/api/v1/conversations/{conversation_id}', headers=headers)
    assert [message['role'] for message in detail.json()['messages']] == ['user', 'assistant']
    assert detail.json()['messages'][1]['content'] == 'A real test-provider response.'
    usage = client.get('/api/v1/usage', headers=headers).json()
    assert usage['requests'] == 1
    assert usage['prompt_tokens'] == 12
    assert usage['completion_tokens'] == 7
    assert usage['estimated_cost_usd'] is None


def test_unsupported_response_mode_is_rejected(client):
    token = register(client)
    headers = auth(token)
    conversation = client.post('/api/v1/conversations', headers=headers, json={'title': 'Mode validation'}).json()
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={'content': 'Use an unsupported mode.', 'response_mode': 'pretend'},
    )
    assert response.status_code == 422
    assert client.get(f"/api/v1/conversations/{conversation['id']}", headers=headers).json()['messages'] == []


def test_other_user_cannot_read_rename_or_delete_conversation(client):
    owner_token = register(client)
    other_token = register(client, 'other@example.com')
    created = client.post('/api/v1/conversations', headers=auth(owner_token), json={'title': 'Private'})
    conversation_id = created.json()['id']
    other_headers = auth(other_token)
    assert client.get(f'/api/v1/conversations/{conversation_id}', headers=other_headers).status_code == 404
    assert client.patch(f'/api/v1/conversations/{conversation_id}', headers=other_headers, json={'title': 'Stolen'}).status_code == 404
    assert client.delete(f'/api/v1/conversations/{conversation_id}', headers=other_headers).status_code == 404
    assert client.get(f'/api/v1/conversations/{conversation_id}', headers=auth(owner_token)).status_code == 200


def test_conversation_search_rename_delete(client):
    token = register(client)
    headers = auth(token)
    created = client.post('/api/v1/conversations', headers=headers, json={'title': 'Alpha planning'}).json()
    assert len(client.get('/api/v1/conversations?q=planning', headers=headers).json()) == 1
    renamed = client.patch(f"/api/v1/conversations/{created['id']}", headers=headers, json={'title': 'Beta'}).json()
    assert renamed['title'] == 'Beta'
    answered = client.post(
        f"/api/v1/conversations/{created['id']}/messages",
        headers=headers,
        json={'content': 'This content should be deleted with the conversation.'},
    )
    assert answered.status_code == 200
    content_search = client.get('/api/v1/conversations?q=should%20be%20deleted', headers=headers)
    assert [item['id'] for item in content_search.json()] == [created['id']]
    assert client.delete(f"/api/v1/conversations/{created['id']}", headers=headers).status_code == 204
    assert client.get('/api/v1/conversations', headers=headers).json() == []
    assert client.get('/api/v1/usage', headers=headers).json()['requests'] == 0


def test_account_export_is_scoped_and_account_deletion_requires_password(client):
    token = register(client)
    headers = auth(token)
    conversation = client.post('/api/v1/conversations', headers=headers, json={'title': 'My export'}).json()
    sent = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={'content': 'Private export marker.'},
    )
    assert sent.status_code == 200

    other_token = register(client, 'other@example.com')
    other_headers = auth(other_token)
    other_conversation = client.post('/api/v1/conversations', headers=other_headers, json={'title': 'Other private chat'}).json()
    other_sent = client.post(
        f"/api/v1/conversations/{other_conversation['id']}/messages",
        headers=other_headers,
        json={'content': 'Other account private marker.'},
    )
    assert other_sent.status_code == 200

    exported = client.get('/api/v1/account/export', headers=headers)
    assert exported.status_code == 200
    assert exported.headers['content-type'].startswith('application/x-ndjson')
    assert 'attachment;' in exported.headers['content-disposition']
    rows = [json.loads(line) for line in exported.text.splitlines()]
    assert [row['type'] for row in rows].count('account') == 1
    assert [row['type'] for row in rows].count('conversation') == 1
    assert [row['type'] for row in rows].count('message') == 2
    assert [row['type'] for row in rows].count('usage') == 1
    assert any(row.get('content') == 'Private export marker.' for row in rows)
    assert all(row.get('title') != 'Other private chat' for row in rows)
    assert all(row.get('content') != 'Other account private marker.' for row in rows)
    assert all('password_hash' not in row and 'token_version' not in row for row in rows)
    owner_id = next(row['id'] for row in rows if row['type'] == 'account')

    wrong_password = client.request('DELETE', '/api/v1/account', headers=headers, json={'password': 'wrong-password'})
    assert wrong_password.status_code == 403
    deleted = client.request('DELETE', '/api/v1/account', headers=headers, json={'password': 'correct horse battery staple'})
    assert deleted.status_code == 204
    assert client.get('/api/v1/conversations', headers=headers).status_code == 401
    assert client.get('/api/v1/account/export', headers=headers).status_code == 401
    assert client.post('/api/v1/auth/login', json={'email': 'person@example.com', 'password': 'correct horse battery staple'}).status_code == 401
    with sqlite3.connect(client.app.state.engine.url.database) as connection:
        assert connection.execute('SELECT count(*) FROM users WHERE id = ?', (owner_id,)).fetchone()[0] == 0
        for table in ('conversations', 'messages', 'usage_records'):
            assert connection.execute(f'SELECT count(*) FROM {table} WHERE user_id = ?', (owner_id,)).fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM users').fetchone()[0] == 1
        audit_event = connection.execute('SELECT event_type, subject_hash FROM audit_events').fetchone()
    assert audit_event is not None
    assert audit_event[0] == 'account_deleted'
    assert len(audit_event[1]) == 64
    assert 'person@example.com' not in audit_event[1]


def test_provider_failure_returns_error_and_saves_no_fake_answer(client):
    token = register(client)
    headers = auth(token)
    created = client.post('/api/v1/conversations', headers=headers, json={'title': 'Provider test'}).json()
    client.app.dependency_overrides[get_provider] = lambda: UnconfiguredProvider()
    response = client.post(
        f"/api/v1/conversations/{created['id']}/messages",
        headers=headers,
        json={'content': 'Do not fabricate a model answer.'},
    )
    assert response.status_code == 503
    assert 'not configured' in response.json()['detail']
    detail = client.get(f"/api/v1/conversations/{created['id']}", headers=headers).json()
    assert detail['messages'] == []


def test_chat_history_survives_api_restart(tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}"
    settings = Settings(
        database_url=database_url,
        jwt_secret=SecretStr('restart-test-secret-that-is-at-least-32-chars'),
        auto_create_schema=True,
        environment='test',
        provider_api_key=SecretStr('test-only-key'),
        model='test/model',
    )
    app1 = create_app(settings)
    app1.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app1) as first:
        token = register(first)
        headers = auth(token)
        conversation = first.post('/api/v1/conversations', headers=headers, json={'title': 'Survives restart'}).json()
        sent = first.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=headers,
            json={'content': 'Persist this exchange.'},
        )
        assert sent.status_code == 200

    app2 = create_app(settings)
    with TestClient(app2) as second:
        login = second.post('/api/v1/auth/login', json={'email': 'person@example.com', 'password': 'correct horse battery staple'})
        assert login.status_code == 200
        history = second.get(f"/api/v1/conversations/{conversation['id']}", headers=auth(login.json()['access_token']))
        assert [item['role'] for item in history.json()['messages']] == ['user', 'assistant']
        assert history.json()['messages'][1]['content'] == 'A real test-provider response.'


def test_settings_reject_unsafe_production_defaults():
    with pytest.raises(ValueError):
        Settings(environment='production', auto_create_schema=False)
    with pytest.raises(ValueError):
        Settings(environment='production', jwt_secret=SecretStr('custom-but-too-short'), auto_create_schema=False)
    with pytest.raises(ValueError, match='HTTPS'):
        Settings(environment='production', jwt_secret=SecretStr('unique-production-secret-thirty-two-chars'), auto_create_schema=False, database_url='postgresql+asyncpg://user:pass@db.example.test/omega', provider_api_key=SecretStr('provider-test-key'), provider_base_url='http://provider.example')
    with pytest.raises(ValueError, match='JWT_SECRET'):
        Settings(environment='production', jwt_secret=SecretStr('replace-with-unique-random-secret-of-at-least-32-characters'), auto_create_schema=False, database_url='postgresql+asyncpg://user:pass@db.example.test/omega', provider_api_key=SecretStr('provider-test-key'))
    with pytest.raises(ValueError, match='OPENAI_COMPATIBLE_API_KEY'):
        Settings(environment='production', jwt_secret=SecretStr('unique-production-secret-thirty-two-chars'), auto_create_schema=False, database_url='postgresql+asyncpg://user:pass@db.example.test/omega')
    with pytest.raises(ValueError, match='PostgreSQL'):
        Settings(environment='production', jwt_secret=SecretStr('unique-production-secret-thirty-two-chars'), auto_create_schema=False, provider_api_key=SecretStr('provider-test-key'))
    production = Settings(environment='production', jwt_secret=SecretStr('unique-production-secret-thirty-two-chars'), auto_create_schema=False, database_url='postgresql+asyncpg://user:pass@db.example.test/omega', provider_api_key=SecretStr('provider-test-key'), model='provider-confirmed-model')
    assert production.environment == 'production'
    with pytest.raises(ValueError, match='AI_MODEL'):
        Settings(environment='test', auto_create_schema=False, provider_api_key=SecretStr('provider-test-key'), model='')


def test_database_url_normalization():
    from omega_api.config import normalize_database_url
    assert normalize_database_url('postgres://user:pass@host/db') == 'postgresql+asyncpg://user:pass@host/db'
    assert normalize_database_url('postgresql://user:pass@host/db') == 'postgresql+asyncpg://user:pass@host/db'


def test_project_workspace_is_account_scoped_and_supports_safe_edit_checkpoint_diff(client):
    owner = auth(register(client, 'workspace-owner@example.com'))
    other = auth(register(client, 'workspace-other@example.com'))
    created = client.post('/api/v1/projects', headers=owner, json={'name': 'Alpha', 'description': 'Demo workspace'})
    assert created.status_code == 201, created.text
    project_id = created.json()['id']
    assert created.json()['name'] == 'Alpha'

    hidden = client.get('/api/v1/projects', headers=other)
    assert hidden.status_code == 200 and hidden.json() == []
    assert client.get(f'/api/v1/projects/{project_id}/files', headers=other).status_code == 404

    first = client.put(
        f'/api/v1/projects/{project_id}/files/src/main.py', headers=owner,
        json={'content': 'print("one")\n'},
    )
    assert first.status_code == 200, first.text
    assert first.json()['revision'] == 1
    checkpoint = client.post(
        f'/api/v1/projects/{project_id}/checkpoints', headers=owner,
        json={'label': 'before edit'},
    )
    assert checkpoint.status_code == 201, checkpoint.text

    changed = client.put(
        f'/api/v1/projects/{project_id}/files/src/main.py', headers=owner,
        json={'content': 'print("two")\n', 'expected_revision': 1},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()['revision'] == 2
    stale = client.put(
        f'/api/v1/projects/{project_id}/files/src/main.py', headers=owner,
        json={'content': 'stale write', 'expected_revision': 1},
    )
    assert stale.status_code == 409
    missing_revision = client.put(
        f'/api/v1/projects/{project_id}/files/src/main.py', headers=owner,
        json={'content': 'blind overwrite'},
    )
    assert missing_revision.status_code == 428

    diff = client.get(
        f'/api/v1/projects/{project_id}/diff', headers=owner,
        params={'checkpoint_id': checkpoint.json()['id']},
    )
    assert diff.status_code == 200, diff.text
    assert diff.json()['changes'][0]['change'] == 'modified'
    assert '-print("one")' in diff.json()['changes'][0]['diff']
    assert '+print("two")' in diff.json()['changes'][0]['diff']

    export = client.get('/api/v1/account/export', headers=owner)
    rows = [json.loads(line) for line in export.text.splitlines()]
    assert any(row['type'] == 'project' and row['name'] == 'Alpha' for row in rows)
    assert any(row['type'] == 'project_file' and row['path'] == 'src/main.py' for row in rows)
    assert any(row['type'] == 'project_checkpoint' for row in rows)
    assert client.delete(f'/api/v1/projects/{project_id}/files/src/main.py', headers=other).status_code == 404
    assert client.delete(f'/api/v1/projects/{project_id}', headers=owner).status_code == 204
    assert client.get('/api/v1/projects', headers=owner).json() == []


def test_workspace_path_validation_blocks_traversal_and_platform_paths():
    assert normalize_project_path('src/module.py') == 'src/module.py'
    assert normalize_project_path('.env.example') == '.env.example'
    for path in ('../secret', 'src/../secret', '/etc/passwd', 'C:\\Windows\\win.ini', 'src//main.py', 'src/./main.py', 'a/../../b', 'bad\x00path'):
        with pytest.raises(WorkspaceInputError):
            normalize_project_path(path)


def test_workspace_diff_includes_added_modified_deleted_files():
    changes = build_project_diff({'same.txt': 'stable\n', 'old.txt': 'before\n', 'gone.txt': 'remove\n'},
                                 {'same.txt': 'stable\n', 'old.txt': 'after\n', 'new.txt': 'added\n'})
    assert [(item['path'], item['change']) for item in changes] == [
        ('gone.txt', 'deleted'), ('new.txt', 'added'), ('old.txt', 'modified'),
    ]


def test_account_deletion_cascades_workspace_files_and_checkpoints(client):
    token = register(client, 'workspace-delete@example.com')
    headers = auth(token)
    project = client.post('/api/v1/projects', headers=headers, json={'name': 'Temporary project'}).json()
    project_id = project['id']
    file = client.put(
        f'/api/v1/projects/{project_id}/files/notes.txt', headers=headers,
        json={'content': 'private project data'},
    )
    assert file.status_code == 200
    checkpoint = client.post(
        f'/api/v1/projects/{project_id}/checkpoints', headers=headers,
        json={'label': 'private snapshot'},
    )
    assert checkpoint.status_code == 201

    deleted = client.request('DELETE', '/api/v1/account', headers=headers,
                             json={'password': 'correct horse battery staple'})
    assert deleted.status_code == 204
    with sqlite3.connect(client.app.state.engine.url.database) as connection:
        for table in ('projects', 'project_files', 'project_checkpoints'):
            assert connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_workspace_enforces_file_and_per_account_storage_limits(client):
    headers = auth(register(client, 'workspace-quota@example.com'))
    project = client.post('/api/v1/projects', headers=headers, json={'name': 'Bounded project'}).json()
    project_id = project['id']
    chunk = 'x' * (512 * 1024)
    for index in range(4):
        response = client.put(
            f'/api/v1/projects/{project_id}/files/file-{index}.txt', headers=headers,
            json={'content': chunk},
        )
        assert response.status_code == 200, response.text
    over_project_limit = client.put(
        f'/api/v1/projects/{project_id}/files/one-more.txt', headers=headers,
        json={'content': 'x'},
    )
    assert over_project_limit.status_code == 413
    over_file_limit = client.put(
        f'/api/v1/projects/{project_id}/files/too-large.txt', headers=headers,
        json={'content': chunk + 'x'},
    )
    assert over_file_limit.status_code == 422

    for index in range(1, 10):
        response = client.post('/api/v1/projects', headers=headers, json={'name': f'Project {index}'})
        assert response.status_code == 201, response.text
    capped = client.post('/api/v1/projects', headers=headers, json={'name': 'One project too many'})
    assert capped.status_code == 429


def test_account_export_client_limit_rejects_large_stream_before_download(client):
    headers = auth(register(client, 'large-export@example.com'))
    project = client.post('/api/v1/projects', headers=headers, json={'name': 'Large export'}).json()
    content = 'x' * (510 * 1024)
    saved = client.put(
        f"/api/v1/projects/{project['id']}/files/large.txt", headers=headers,
        json={'content': content},
    )
    assert saved.status_code == 200

    capped = client.get('/api/v1/account/export?max_bytes=500000', headers=headers)
    assert capped.status_code == 413
    assert capped.headers['content-type'].startswith('application/json')
    assert len(capped.content) < 500
    full = client.get('/api/v1/account/export', headers=headers)
    assert full.status_code == 200
    assert len(full.content) > 500_000


def test_account_export_preflight_and_stream_terminate_with_checkpoint(client):
    headers = auth(register(client, 'checkpoint-export@example.com'))
    project = client.post('/api/v1/projects', headers=headers, json={'name': 'Checkpoint export'}).json()
    file = client.put(
        f"/api/v1/projects/{project['id']}/files/note.txt", headers=headers,
        json={'content': 'checkpointed content'},
    )
    assert file.status_code == 200
    checkpoint = client.post(
        f"/api/v1/projects/{project['id']}/checkpoints", headers=headers,
        json={'label': 'first'},
    )
    assert checkpoint.status_code == 201

    response = client.get('/api/v1/account/export?max_bytes=500000', headers=headers)
    assert response.status_code == 200
    rows = [json.loads(line) for line in response.text.splitlines()]
    assert [row['type'] for row in rows].count('project_checkpoint') == 1
    assert next(row for row in rows if row['type'] == 'project_checkpoint')['label'] == 'first'
