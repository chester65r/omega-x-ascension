from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from omega.rate_limit import enforce_rate_limit


class FakeRedis:
    def __init__(self):
        self.counts = {}
        self.expirations = {}

    async def eval(self, script, numkeys, key, ttl):
        assert numkeys == 1
        assert "INCR" in script and "EXPIRE" in script
        self.counts[key] = self.counts.get(key, 0) + 1
        if self.counts[key] == 1:
            self.expirations[key] = ttl
        return self.counts[key]


def test_rate_limit_allows_requests_up_to_limit_and_then_returns_429():
    async def check():
        redis = FakeRedis()
        for _ in range(2):
            await enforce_rate_limit(
                redis, tenant_id="tenant-a", user_id="user-a", action="runs:create", limit=2
            )
        with pytest.raises(HTTPException) as exc:
            await enforce_rate_limit(
                redis, tenant_id="tenant-a", user_id="user-a", action="runs:create", limit=2
            )
        assert exc.value.status_code == 429
        assert int(exc.value.headers["Retry-After"]) >= 1

    asyncio.run(check())


def test_rate_limits_are_isolated_by_tenant_user_and_action():
    async def check():
        redis = FakeRedis()
        await enforce_rate_limit(
            redis, tenant_id="tenant-a", user_id="user-a", action="runs:create", limit=1
        )
        await enforce_rate_limit(
            redis, tenant_id="tenant-b", user_id="user-a", action="runs:create", limit=1
        )
        await enforce_rate_limit(
            redis, tenant_id="tenant-a", user_id="user-b", action="runs:create", limit=1
        )
        await enforce_rate_limit(
            redis, tenant_id="tenant-a", user_id="user-a", action="browser:search", limit=1
        )
        assert len(redis.counts) == 4

    asyncio.run(check())


def test_rate_limiter_fails_closed_when_redis_is_unavailable():
    class BrokenRedis:
        async def eval(self, *args):
            raise ConnectionError("redis unavailable")

    async def check():
        with pytest.raises(HTTPException) as exc:
            await enforce_rate_limit(
                BrokenRedis(),
                tenant_id="tenant-a",
                user_id="user-a",
                action="runs:create",
                limit=2,
            )
        assert exc.value.status_code == 503

    asyncio.run(check())
