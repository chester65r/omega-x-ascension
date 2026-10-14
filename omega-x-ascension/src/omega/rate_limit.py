from __future__ import annotations

import hashlib
import time

from fastapi import HTTPException

# Redis performs the increment and initial expiry atomically across API replicas.
_INCREMENT_WITH_EXPIRY = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


async def enforce_rate_limit(
    redis,
    *,
    tenant_id: object,
    user_id: str,
    action: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    """Apply a tenant-and-user-scoped Redis limit; fail closed if Redis is unavailable."""
    if limit < 1 or window_seconds < 1:
        raise ValueError("rate limit and window must be positive")
    bucket = int(time.time() // window_seconds)
    user_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    key = f"omega:rate:v1:{tenant_id}:{user_hash}:{action}:{window_seconds}:{bucket}"
    try:
        count = int(await redis.eval(_INCREMENT_WITH_EXPIRY, 1, key, window_seconds * 2))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="request limiter unavailable",
            headers={"Retry-After": "5"},
        ) from exc
    if count > limit:
        retry_after = window_seconds - (int(time.time()) % window_seconds)
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(max(1, retry_after))},
        )
