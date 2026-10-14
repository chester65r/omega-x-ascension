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


def test_workspace_file_access_requires_read_scope_and_edits_require_write_plus_approval():
    tenant = UUID("11111111-1111-1111-1111-111111111111")
    reader = Principal(
        user_id="user-1",
        tenant_id=tenant,
        scopes=frozenset({"runs:write", "computer:read"}),
    )
    require_requested_action_scopes(["use_workspace_files"], reader)

    no_read_scope = Principal(
        user_id="user-1",
        tenant_id=tenant,
        scopes=frozenset({"runs:write"}),
    )
    with pytest.raises(HTTPException) as exc:
        require_requested_action_scopes(["use_workspace_files"], no_read_scope)
    assert exc.value.status_code == 403

    no_write_scope = Principal(
        user_id="user-1",
        tenant_id=tenant,
        scopes=frozenset({"runs:write", "computer:read", "runs:approve"}),
    )
    with pytest.raises(HTTPException) as exc:
        require_requested_action_scopes(
            ["use_workspace_files", "write_workspace_files"], no_write_scope
        )
    assert exc.value.status_code == 403
    assert "computer:write" in str(exc.value.detail)

    no_approval = Principal(
        user_id="user-1",
        tenant_id=tenant,
        scopes=frozenset({"runs:write", "computer:read", "computer:write"}),
    )
    with pytest.raises(HTTPException) as exc:
        require_requested_action_scopes(
            ["use_workspace_files", "write_workspace_files"], no_approval
        )
    assert exc.value.status_code == 403
    assert "runs:approve" in str(exc.value.detail)

    writer = Principal(
        user_id="user-1",
        tenant_id=tenant,
        scopes=frozenset({"runs:write", "runs:approve", "computer:read", "computer:write"}),
    )
    require_requested_action_scopes(
        ["use_workspace_files", "write_workspace_files"], writer
    )


def test_workspace_write_action_must_include_workspace_read_action():
    writer = Principal(
        user_id="user-1",
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        scopes=frozenset({"runs:write", "runs:approve", "computer:read", "computer:write"}),
    )
    with pytest.raises(HTTPException) as exc:
        require_requested_action_scopes(["write_workspace_files"], writer)
    assert exc.value.status_code == 400
