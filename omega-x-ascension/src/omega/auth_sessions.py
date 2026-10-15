from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, HTTPException, Request, Security, status
from pydantic import BaseModel, Field
from jwt import InvalidTokenError

from omega.auth import Principal, current_principal
from omega.config import get_settings

router = APIRouter(tags=["device sessions"])

ACCESS_TOKEN_LIFETIME_SECONDS = 60 * 60
DEVICE_REFRESH_LIFETIME_SECONDS = 30 * 24 * 60 * 60
REFRESH_REVOKED_PREFIX = "omega:device-refresh:revoked:"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=60, max_length=4096)


def _encode_access_token(subject: str, tenant_id: UUID, scopes: frozenset[str]) -> str:
    cfg = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": subject,
        "tenant_id": str(tenant_id),
        "scope": " ".join(sorted(scopes)),
        "iss": cfg.jwt_issuer,
        "aud": cfg.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ACCESS_TOKEN_LIFETIME_SECONDS)).timestamp()),
        "token_use": "access",
    }
    return jwt.encode(claims, cfg.jwt_secret.get_secret_value(), algorithm=cfg.jwt_algorithm)


def _decode_refresh_token(value: str) -> dict:
    cfg = get_settings()
    try:
        claims = jwt.decode(
            value,
            cfg.jwt_secret.get_secret_value(),
            algorithms=[cfg.jwt_algorithm],
            issuer=cfg.jwt_issuer,
            audience=cfg.jwt_audience,
            options={
                "require": [
                    "exp", "iat", "sub", "tenant_id", "iss", "aud",
                    "jti", "token_use", "scope", "access_scope",
                ]
            },
        )
        if claims.get("token_use") != "device_refresh" or claims.get("scope") != "device:refresh":
            raise InvalidTokenError("not a device refresh token")
        UUID(str(claims["tenant_id"]))
        if not str(claims.get("sub", "")).strip():
            raise InvalidTokenError("missing subject")
        if not isinstance(claims.get("access_scope"), str):
            raise InvalidTokenError("missing access scopes")
        return claims
    except (InvalidTokenError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired device session",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def _assert_not_revoked(request: Request, claims: dict) -> int:
    ttl = int(claims["exp"]) - int(time.time())
    if ttl <= 0:
        raise HTTPException(status_code=401, detail="device session expired")
    redis = request.app.state.services.redis
    try:
        if await redis.get(REFRESH_REVOKED_PREFIX + str(claims["jti"])):
            raise HTTPException(status_code=401, detail="device session was signed out")
    except HTTPException:
        raise
    except Exception as exc:
        # Fail closed: never allow a refresh when revocation state cannot be checked.
        raise HTTPException(status_code=503, detail="session service temporarily unavailable") from exc
    return ttl


@router.post("/auth/device")
async def create_device_session(
    principal: Principal = Security(current_principal, scopes=["runs:read"]),
):
    """Exchange a valid short-lived access JWT for a revocable device refresh credential."""
    cfg = get_settings()
    now = datetime.now(UTC)
    expires = int((now + timedelta(seconds=DEVICE_REFRESH_LIFETIME_SECONDS)).timestamp())
    claims = {
        "sub": principal.user_id,
        "tenant_id": str(principal.tenant_id),
        "scope": "device:refresh",
        "access_scope": " ".join(sorted(principal.scopes)),
        "iss": cfg.jwt_issuer,
        "aud": cfg.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": expires,
        "jti": uuid4().hex,
        "token_use": "device_refresh",
    }
    refresh_token = jwt.encode(
        claims, cfg.jwt_secret.get_secret_value(), algorithm=cfg.jwt_algorithm
    )
    return {
        "token_type": "Bearer",
        "refresh_token": refresh_token,
        "expires_at": expires,
        "expires_in": DEVICE_REFRESH_LIFETIME_SECONDS,
        "access_expires_in": ACCESS_TOKEN_LIFETIME_SECONDS,
    }


@router.post("/auth/refresh")
async def refresh_device_session(body: RefreshRequest, request: Request):
    """Mint a short-lived access token from a device-only credential held in Android Keystore."""
    claims = _decode_refresh_token(body.refresh_token)
    await _assert_not_revoked(request, claims)
    scope_string = str(claims.get("access_scope", "")).strip()
    allowed_scopes = {
        "runs:read", "runs:write", "runs:approve",
        "computer:read", "computer:write", "computer:execute",
    }
    scopes = frozenset(scope for scope in scope_string.split() if scope in allowed_scopes)
    # Do not turn a malformed or stripped refresh claim into a broader permission set.
    if not scopes or scopes != frozenset(scope_string.split()):
        raise HTTPException(status_code=401, detail="device session contains invalid scopes")
    access_token = _encode_access_token(
        str(claims["sub"]), UUID(str(claims["tenant_id"])), scopes
    )
    return {
        "token_type": "Bearer",
        "access_token": access_token,
        "expires_in": ACCESS_TOKEN_LIFETIME_SECONDS,
        "refresh_expires_at": int(claims["exp"]),
    }


@router.post("/auth/revoke")
async def revoke_device_session(body: RefreshRequest, request: Request):
    """Revoke a device refresh credential; safe to call repeatedly during sign-out."""
    claims = _decode_refresh_token(body.refresh_token)
    ttl = int(claims["exp"]) - int(time.time())
    if ttl > 0:
        redis = request.app.state.services.redis
        try:
            await redis.set(
                REFRESH_REVOKED_PREFIX + str(claims["jti"]), "1", ex=ttl
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="session service temporarily unavailable") from exc
    return {"revoked": True}
