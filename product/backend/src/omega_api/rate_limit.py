import hashlib
import hmac
import time

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from omega_api.models import RateLimitBucket


async def enforce_auth_rate_limit(
    db: AsyncSession,
    *,
    email: str,
    client_ip: str,
    secret: str,
    email_limit: int,
    ip_limit: int,
    window_seconds: int,
) -> None:
    """Atomically enforce fixed-window email and source-IP limits in SQL storage."""
    now = int(time.time())
    window_start = now - now % window_seconds
    dialect = db.get_bind().dialect.name
    insert = {'sqlite': sqlite_insert, 'postgresql': pg_insert}.get(dialect)
    if insert is None:
        raise RuntimeError(f'Authentication rate limiting is unsupported for database dialect: {dialect}')

    buckets = (
        (f'email:{email.strip().lower()}', email_limit),
        (f'ip:{client_ip or "unknown"}', ip_limit),
    )
    retry_after = window_seconds - (now - window_start)
    limited = False
    for raw_key, limit in buckets:
        key_hash = hmac.new(secret.encode('utf-8'), raw_key.encode('utf-8'), hashlib.sha256).hexdigest()
        statement = insert(RateLimitBucket).values(
            key_hash=key_hash,
            window_start=window_start,
            attempts=1,
        ).on_conflict_do_update(
            index_elements=[RateLimitBucket.key_hash, RateLimitBucket.window_start],
            set_={'attempts': RateLimitBucket.attempts + 1},
        ).returning(RateLimitBucket.attempts)
        attempts = (await db.execute(statement)).scalar_one()
        limited = limited or attempts > limit

        # Keep only the current fixed window for keys that have become active again.
        await db.execute(delete(RateLimitBucket).where(
            RateLimitBucket.key_hash == key_hash,
            RateLimitBucket.window_start < window_start,
        ))

    # Keep transient throttling data bounded; keys are HMAC digests, never raw emails/IPs.
    await db.execute(delete(RateLimitBucket).where(RateLimitBucket.window_start < now - 86400))
    await db.commit()
    if limited:
        raise HTTPException(
            status_code=429,
            detail='Too many authentication attempts. Please wait before trying again.',
            headers={'Retry-After': str(retry_after)},
        )
