from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from omega_api.config import Settings
from omega_api.main import create_app, get_provider
from omega_api.provider import Completion, ProviderNotConfigured


class FakeProvider:
    configured = True

    async def complete(self, messages):
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
    assert client.get('/health/live').json() == {'status': 'alive'}
    ready = client.get('/health/ready')
    assert ready.status_code == 200
    assert ready.json()['database'] == 'connected'


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


def test_chat_persists_per_user_and_tracks_usage(client):
    token = register(client)
    headers = auth(token)
    created = client.post('/api/v1/conversations', headers=headers, json={'title': 'Planning'})
    assert created.status_code == 201
    conversation_id = created.json()['id']
    response = client.post(
        f'/api/v1/conversations/{conversation_id}/messages',
        headers=headers,
        json={'content': 'Give me a short plan.', 'request_id': '327bbffc-ec4c-4e2e-a8ac-c2b9ca661ee1'},
    )
    assert response.status_code == 200, response.text
    assert response.json()['assistant_message']['content'] == 'A real test-provider response.'
    detail = client.get(f'/api/v1/conversations/{conversation_id}', headers=headers)
    assert [message['role'] for message in detail.json()['messages']] == ['user', 'assistant']
    assert detail.json()['messages'][1]['content'] == 'A real test-provider response.'
    usage = client.get('/api/v1/usage', headers=headers).json()
    assert usage['requests'] == 1
    assert usage['prompt_tokens'] == 12
    assert usage['completion_tokens'] == 7
    assert usage['estimated_cost_usd'] is None


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
    assert client.delete(f"/api/v1/conversations/{created['id']}", headers=headers).status_code == 204
    assert client.get('/api/v1/conversations', headers=headers).json() == []
    assert client.get('/api/v1/usage', headers=headers).json()['requests'] == 0


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
