from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from omega.auth import Principal, TokenVerifier
from omega.api import require_requested_action_scopes


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


def test_privileged_computer_action_requires_computer_execute_scope():
    base = {
        "user_id": "user-1",
        "tenant_id": UUID("11111111-1111-1111-1111-111111111111"),
    }
    limited = Principal(scopes=frozenset({"runs:write", "runs:approve"}), **base)
    with pytest.raises(HTTPException) as exc:
        require_requested_action_scopes(["execute_code"], limited)
    assert exc.value.status_code == 403
    assert "computer:execute" in str(exc.value.detail)

    permitted = Principal(
        scopes=frozenset({"runs:write", "runs:approve", "computer:execute"}),
        **base,
    )
    require_requested_action_scopes(["execute_code"], permitted)


def test_non_privileged_agent_actions_do_not_need_computer_execute_scope():
    principal = Principal(
        user_id="user-1",
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        scopes=frozenset({"runs:write", "runs:approve"}),
    )
    require_requested_action_scopes([], principal)
    require_requested_action_scopes(["use_remote_mcp"], principal)
