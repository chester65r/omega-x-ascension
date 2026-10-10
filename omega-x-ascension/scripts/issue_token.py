from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from omega.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Issue a short-lived OMEGA-X access token for a trusted operator."
    )
    parser.add_argument("--subject", required=True, help="Operator identifier, not a password")
    parser.add_argument(
        "--tenant-id",
        required=True,
        help="Tenant UUID; keep this value stable for this operator's data",
    )
    parser.add_argument(
        "--scopes",
        default="runs:read runs:write runs:approve",
        help="Space-separated scopes. Computer scopes are powerful and must be granted explicitly.",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=60,
        help="Token lifetime in minutes (1-1440; default 60)",
    )
    args = parser.parse_args()

    if not 1 <= args.minutes <= 1440:
        parser.error("--minutes must be between 1 and 1440")
    try:
        tenant_id = str(UUID(args.tenant_id))
    except ValueError:
        parser.error("--tenant-id must be a valid UUID")
    scopes = set(args.scopes.split())
    allowed = {"runs:read", "runs:write", "runs:approve", "computer:read", "computer:write", "computer:execute"}
    if not scopes or scopes - allowed:
        parser.error(f"--scopes must contain only: {' '.join(sorted(allowed))}")

    cfg = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": args.subject,
        "tenant_id": tenant_id,
        "scope": " ".join(sorted(scopes)),
        "iss": cfg.jwt_issuer,
        "aud": cfg.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=args.minutes),
    }
    print(jwt.encode(claims, cfg.jwt_secret.get_secret_value(), algorithm=cfg.jwt_algorithm))


if __name__ == "__main__":
    main()
