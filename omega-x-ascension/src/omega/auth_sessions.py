from __future__ import annotations

import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Header, HTTPException, Request, Security, status
from jwt import InvalidTokenError
from pydantic import BaseModel, Field

from omega.auth import Principal, current_principal
from omega.config import get_settings

router = APIRouter(tags=["device sessions"])

ACCESS_TOKEN_LIFETIME_SECONDS = 60 * 60
DEVICE_REFRESH_LIFETIME_SECONDS = 30 * 24 * 60 * 60
REFRESH_REVOKED_PREFIX = "omega:device-refresh:revoked:"
BOOTSTRAP_USED_PREFIX = "omega:token-bootstrap:used:"
BOOTSTRAP_ATTEMPT_PREFIX = "omega:token-bootstrap:attempts:"
BOOTSTRAP_RATE_WINDOW_SECONDS = 60
BOOTSTRAP_MAX_ATTEMPTS = 12
BOOTSTRAP_ACCESS_LIFETIME_SECONDS = 5 * 60
BOOTSTRAP_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
BOOTSTRAP_SUBJECT = "omega-primary-device"
BOOTSTRAP_SCOPES = frozenset({
    "runs:read", "runs:write", "runs:approve", "computer:read", "computer:write",
})


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=60, max_length=4096)


class RefreshRotationCommitRequest(BaseModel):
    previous_refresh_token: str = Field(min_length=60, max_length=4096)
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


@router.post("/auth/bootstrap")
async def bootstrap_device(
    request: Request,
    supplied_secret: str | None = Header(default=None, alias="X-OMEGA-BOOTSTRAP-SECRET"),
):
    """Enroll the trusted Android app without putting the JWT signing key in the APK."""
    cfg = get_settings()
    configured_secret = (
        cfg.token_bootstrap_secret.get_secret_value()
        if cfg.token_bootstrap_secret
        else ""
    )
    if len(configured_secret) < 32:
        raise HTTPException(status_code=404, detail="not found")

    redis = request.app.state.services.redis
    client_host = request.client.host if request.client else "unknown"
    attempts_key = BOOTSTRAP_ATTEMPT_PREFIX + hashlib.sha256(
        client_host.encode("utf-8")
    ).hexdigest()[:24]
    try:
        attempts = await redis.incr(attempts_key)
        if attempts == 1:
            await redis.expire(attempts_key, BOOTSTRAP_RATE_WINDOW_SECONDS)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="setup service temporarily unavailable") from exc
    if attempts > BOOTSTRAP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="too many setup attempts; try again shortly")

    if not supplied_secret or not hmac.compare_digest(supplied_secret, configured_secret):
        raise HTTPException(status_code=401, detail="invalid one-time setup key")

    # Atomically consume the setup key. Redis failure is fail-closed.
    secret_fingerprint = hashlib.sha256(configured_secret.encode("utf-8")).hexdigest()
    try:
        claimed = await redis.set(
            BOOTSTRAP_USED_PREFIX + secret_fingerprint,
            "1",
            nx=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="setup service temporarily unavailable") from exc
    if not claimed:
        raise HTTPException(status_code=410, detail="this setup key has already been used")

    now = datetime.now(UTC)
    issued_at = int(now.timestamp())
    scope_string = " ".join(sorted(BOOTSTRAP_SCOPES))
    access_expiry = int((now + timedelta(seconds=BOOTSTRAP_ACCESS_LIFETIME_SECONDS)).timestamp())
    refresh_expiry = int((now + timedelta(seconds=DEVICE_REFRESH_LIFETIME_SECONDS)).timestamp())
    access_claims = {
        "sub": BOOTSTRAP_SUBJECT,
        "tenant_id": str(BOOTSTRAP_TENANT_ID),
        "scope": scope_string,
        "iss": cfg.jwt_issuer,
        "aud": cfg.jwt_audience,
        "iat": issued_at,
        "exp": access_expiry,
        "token_use": "access",
    }
    access_token = jwt.encode(
        access_claims, cfg.jwt_secret.get_secret_value(), algorithm=cfg.jwt_algorithm
    )
    refresh_claims = {
        "sub": BOOTSTRAP_SUBJECT,
        "tenant_id": str(BOOTSTRAP_TENANT_ID),
        "scope": "device:refresh",
        "access_scope": scope_string,
        "iss": cfg.jwt_issuer,
        "aud": cfg.jwt_audience,
        "iat": issued_at,
        "exp": refresh_expiry,
        "jti": uuid4().hex,
        "token_use": "device_refresh",
    }
    refresh_token = jwt.encode(
        refresh_claims, cfg.jwt_secret.get_secret_value(), algorithm=cfg.jwt_algorithm
    )
    return {
        "token_type": "Bearer",
        "access_token": access_token,
        "expires_in": BOOTSTRAP_ACCESS_LIFETIME_SECONDS,
        "refresh_token": refresh_token,
        "refresh_expires_at": refresh_expiry,
    }


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
    cfg = get_settings()
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

    # Rotate the device credential with a sliding 30-day lifetime. The previous
    # token stays usable until Android confirms the replacement was saved.
    now = datetime.now(UTC)
    issued_at = int(now.timestamp())
    refresh_expiry = int((now + timedelta(seconds=DEVICE_REFRESH_LIFETIME_SECONDS)).timestamp())
    scope_string = " ".join(sorted(scopes))
    rotated_claims = {
        "sub": str(claims["sub"]),
        "tenant_id": str(claims["tenant_id"]),
        "scope": "device:refresh",
        "access_scope": scope_string,
        "iss": cfg.jwt_issuer,
        "aud": cfg.jwt_audience,
        "iat": issued_at,
        "exp": refresh_expiry,
        "jti": uuid4().hex,
        "parent_jti": str(claims["jti"]),
        "token_use": "device_refresh",
    }
    rotated_refresh_token = jwt.encode(
        rotated_claims, cfg.jwt_secret.get_secret_value(), algorithm=cfg.jwt_algorithm
    )
    return {
        "token_type": "Bearer",
        "access_token": access_token,
        "expires_in": ACCESS_TOKEN_LIFETIME_SECONDS,
        "refresh_token": rotated_refresh_token,
        "refresh_expires_at": refresh_expiry,
    }


@router.post("/auth/refresh/commit")
async def commit_device_session_rotation(body: RefreshRotationCommitRequest, request: Request):
    """Revoke the previous refresh credential only after its replacement is stored."""
    previous = _decode_refresh_token(body.previous_refresh_token)
    replacement = _decode_refresh_token(body.refresh_token)

    if (
        replacement.get("parent_jti") != str(previous.get("jti", ""))
        or replacement.get("jti") == previous.get("jti")
        or replacement.get("sub") != previous.get("sub")
        or replacement.get("tenant_id") != previous.get("tenant_id")
        or replacement.get("access_scope") != previous.get("access_scope")
    ):
        raise HTTPException(status_code=401, detail="invalid device session rotation")

    await _assert_not_revoked(request, replacement)
    ttl = int(previous["exp"]) - int(time.time())
    if ttl > 0:
        redis = request.app.state.services.redis
        try:
            await redis.set(REFRESH_REVOKED_PREFIX + str(previous["jti"]), "1", ex=ttl)
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="session service temporarily unavailable"
            ) from exc
    return {"committed": True}


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
