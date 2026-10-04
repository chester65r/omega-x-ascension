from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes
from jwt import InvalidTokenError

from omega.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    tenant_id: UUID
    scopes: frozenset[str]

    def require(self, required: set[str]) -> None:
        missing = required.difference(self.scopes)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing scopes: {', '.join(sorted(missing))}",
            )


class TokenVerifier:
    def __init__(self, settings: Settings):
        self._secret = settings.jwt_secret.get_secret_value()
        self._issuer = settings.jwt_issuer
        self._audience = settings.jwt_audience
        self._algorithm = settings.jwt_algorithm

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "sub", "tenant_id", "iss", "aud"]},
            )
            tenant_id = UUID(str(claims["tenant_id"]))
            raw_scopes = claims.get("scope", "")
            scopes = frozenset(str(raw_scopes).split())
            return Principal(user_id=str(claims["sub"]), tenant_id=tenant_id, scopes=scopes)
        except (InvalidTokenError, ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc


async def current_principal(
    security_scopes: SecurityScopes,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
    settings: Settings = Security(get_settings),
) -> Principal:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    principal = TokenVerifier(settings).verify(credentials.credentials)
    principal.require(set(security_scopes.scopes))
    return principal
