from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

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


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value


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
