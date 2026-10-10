from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from omega.auth import TokenVerifier


class Config:
    jwt_secret = SecretStr("a" * 32)
    jwt_issuer = "omega-x"
    jwt_audience = "omega-x-api"
    jwt_algorithm = "HS256"


def token(**overrides):
    now = datetime.now(UTC)
    claims = {
        "sub": "user-1",
        "tenant_id": str(uuid4()),
        "scope": "runs:read runs:write",
        "iss": "omega-x",
        "aud": "omega-x-api",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, "a" * 32, algorithm="HS256"), claims


def test_verifies_tenant_and_scopes():
    encoded, claims = token()
    principal = TokenVerifier(Config()).verify(encoded)
    assert str(principal.tenant_id) == claims["tenant_id"]
    assert "runs:read" in principal.scopes


def test_rejects_wrong_audience():
    encoded, _ = token(aud="other")
    with pytest.raises(HTTPException) as exc:
        TokenVerifier(Config()).verify(encoded)
    assert exc.value.status_code == 401
