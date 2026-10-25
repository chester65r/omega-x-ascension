from types import SimpleNamespace
from uuid import UUID

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from omega.auth import Principal, current_principal
from omega.auth_sessions import router


class Config:
    jwt_secret = SecretStr("z" * 40)
    jwt_issuer = "omega-x"
    jwt_audience = "omega-x-api"
    jwt_algorithm = "HS256"
    token_bootstrap_secret = SecretStr("b" * 64)


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def incr(self, key):
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value

    async def expire(self, key, seconds):
        return key in self.values


def make_client(monkeypatch):
    import omega.auth_sessions as sessions

    monkeypatch.setattr(sessions, "get_settings", lambda: Config())
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.state.services = SimpleNamespace(redis=MemoryRedis())
    principal = Principal(
        user_id="device-user",
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        scopes=frozenset({"runs:read", "runs:write", "runs:approve"}),
    )
    app.dependency_overrides[current_principal] = lambda: principal
    return TestClient(app), app


def test_public_guest_enrollment_issues_isolated_limited_sessions(monkeypatch):
    client, _app = make_client(monkeypatch)

    first = client.post("/v1/auth/guest")
    second = client.post("/v1/auth/guest")
    assert first.status_code == 201
    assert second.status_code == 201

    first_data = first.json()
    second_data = second.json()
    assert first_data["account_type"] == "guest"
    assert first_data["access_token"]
    assert first_data["refresh_token"]
    assert first_data["access_token"] != second_data["access_token"]

    first_claims = jwt.decode(
        first_data["access_token"],
        Config.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=Config.jwt_issuer,
        audience=Config.jwt_audience,
    )
    second_claims = jwt.decode(
        second_data["access_token"],
        Config.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=Config.jwt_issuer,
        audience=Config.jwt_audience,
    )
    first_scopes = set(first_claims["scope"].split())
    assert first_claims["tenant_id"] != second_claims["tenant_id"]
    assert first_scopes == {"runs:read", "runs:write", "computer:read", "computer:write"}
    assert "runs:approve" not in first_scopes
    assert "computer:execute" not in first_scopes


def test_guest_enrollment_is_rate_limited(monkeypatch):
    client, _app = make_client(monkeypatch)
    for _ in range(20):
        assert client.post("/v1/auth/guest").status_code == 201
    limited = client.post("/v1/auth/guest")
    assert limited.status_code == 429


def test_device_session_exchange_refreshes_access_token_with_same_scopes(monkeypatch):
    client, _app = make_client(monkeypatch)

    enrolled = client.post("/v1/auth/device")
    assert enrolled.status_code == 200
    refresh_token = enrolled.json()["refresh_token"]
    refresh_claims = jwt.decode(
        refresh_token,
        Config.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=Config.jwt_issuer,
        audience=Config.jwt_audience,
    )
    assert refresh_claims["token_use"] == "device_refresh"
    assert refresh_claims["scope"] == "device:refresh"
    assert refresh_claims["access_scope"] == "runs:approve runs:read runs:write"

    refreshed = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    data = refreshed.json()
    access_claims = jwt.decode(
        data["access_token"],
        Config.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=Config.jwt_issuer,
        audience=Config.jwt_audience,
    )
    assert access_claims["token_use"] == "access"
    assert access_claims["sub"] == "device-user"
    assert access_claims["scope"] == "runs:approve runs:read runs:write"
    assert data["expires_in"] == 3600


def test_refresh_session_can_be_revoked_and_then_rejected(monkeypatch):
    client, _app = make_client(monkeypatch)
    refresh_token = client.post("/v1/auth/device").json()["refresh_token"]

    revoked = client.post("/v1/auth/revoke", json={"refresh_token": refresh_token})
    assert revoked.status_code == 200
    assert revoked.json() == {"revoked": True}

    refreshed = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 401


def test_device_refresh_token_cannot_authorize_normal_api_calls(monkeypatch):
    client, _app = make_client(monkeypatch)
    refresh_token = client.post("/v1/auth/device").json()["refresh_token"]

    from omega.auth import TokenVerifier

    try:
        TokenVerifier(Config()).verify(refresh_token)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401
    else:
        raise AssertionError("device refresh tokens must never authorize regular API endpoints")



def test_one_time_bootstrap_issues_scoped_access_and_refresh_tokens(monkeypatch):
    client, _app = make_client(monkeypatch)

    response = client.post(
        "/v1/auth/bootstrap",
        headers={"X-OMEGA-BOOTSTRAP-SECRET": Config.token_bootstrap_secret.get_secret_value()},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["expires_in"] == 300
    assert data["access_token"]
    assert data["refresh_token"]

    access_claims = jwt.decode(
        data["access_token"],
        Config.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=Config.jwt_issuer,
        audience=Config.jwt_audience,
    )
    assert access_claims["sub"] == "omega-primary-device"
    assert access_claims["token_use"] == "access"
    assert "runs:read" in access_claims["scope"].split()
    assert "runs:write" in access_claims["scope"].split()
    assert "computer:read" in access_claims["scope"].split()
    assert "computer:write" in access_claims["scope"].split()
    assert "computer:execute" in access_claims["scope"].split()

    refresh_claims = jwt.decode(
        data["refresh_token"],
        Config.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=Config.jwt_issuer,
        audience=Config.jwt_audience,
    )
    assert refresh_claims["token_use"] == "device_refresh"
    assert refresh_claims["access_scope"] == access_claims["scope"]

    reused = client.post(
        "/v1/auth/bootstrap",
        headers={"X-OMEGA-BOOTSTRAP-SECRET": Config.token_bootstrap_secret.get_secret_value()},
    )
    assert reused.status_code == 410



def test_invalid_bootstrap_secret_does_not_consume_the_valid_setup_key(monkeypatch):
    client, _app = make_client(monkeypatch)

    rejected = client.post(
        "/v1/auth/bootstrap",
        headers={"X-OMEGA-BOOTSTRAP-SECRET": "c" * 64},
    )
    assert rejected.status_code == 401

    accepted = client.post(
        "/v1/auth/bootstrap",
        headers={"X-OMEGA-BOOTSTRAP-SECRET": Config.token_bootstrap_secret.get_secret_value()},
    )
    assert accepted.status_code == 200

    replay = client.post(
        "/v1/auth/bootstrap",
        headers={"X-OMEGA-BOOTSTRAP-SECRET": Config.token_bootstrap_secret.get_secret_value()},
    )
    assert replay.status_code == 410

def test_refresh_rotates_device_credential_and_commit_revokes_previous(monkeypatch):
    client, _app = make_client(monkeypatch)
    enrolled = client.post("/v1/auth/device")
    assert enrolled.status_code == 200
    previous_token = enrolled.json()["refresh_token"]
    previous_claims = jwt.decode(
        previous_token,
        Config.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=Config.jwt_issuer,
        audience=Config.jwt_audience,
    )

    refreshed = client.post("/v1/auth/refresh", json={"refresh_token": previous_token})
    assert refreshed.status_code == 200
    rotation = refreshed.json()
    replacement_token = rotation["refresh_token"]
    replacement_claims = jwt.decode(
        replacement_token,
        Config.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=Config.jwt_issuer,
        audience=Config.jwt_audience,
    )
    assert replacement_token != previous_token
    assert replacement_claims["parent_jti"] == previous_claims["jti"]
    assert replacement_claims["jti"] != previous_claims["jti"]
    assert replacement_claims["exp"] >= previous_claims["exp"]

    # The old credential remains usable until the client confirms secure storage.
    assert client.post(
        "/v1/auth/refresh", json={"refresh_token": previous_token}
    ).status_code == 200

    committed = client.post(
        "/v1/auth/refresh/commit",
        json={
            "previous_refresh_token": previous_token,
            "refresh_token": replacement_token,
        },
    )
    assert committed.status_code == 200
    assert committed.json() == {"committed": True}
    assert client.post(
        "/v1/auth/refresh", json={"refresh_token": previous_token}
    ).status_code == 401
    assert client.post(
        "/v1/auth/refresh", json={"refresh_token": replacement_token}
    ).status_code == 200
