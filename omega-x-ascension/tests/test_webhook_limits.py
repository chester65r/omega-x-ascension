from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid

import pytest
from fastapi import HTTPException

from omega.config import Settings
from omega.webhooks import github_webhook, read_bounded_body


class FakeRequest:
    def __init__(self, chunks, headers=None):
        self._chunks = chunks
        self.headers = headers or {}

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


def test_bounded_webhook_reader_accepts_small_payload():
    async def check():
        result = await read_bounded_body(FakeRequest([b'{"action":', b'"ping"}']))
        assert result == b'{"action":"ping"}'

    asyncio.run(check())


def test_bounded_webhook_reader_rejects_oversized_content_length():
    async def check():
        with pytest.raises(HTTPException) as exc:
            await read_bounded_body(FakeRequest([], {"content-length": "1001"}), max_bytes=1000)
        assert exc.value.status_code == 413

    asyncio.run(check())


def test_bounded_webhook_reader_rejects_oversized_stream_without_content_length():
    async def check():
        with pytest.raises(HTTPException) as exc:
            await read_bounded_body(FakeRequest([b"a" * 600, b"b" * 500]), max_bytes=1000)
        assert exc.value.status_code == 413

    asyncio.run(check())


def test_bounded_webhook_reader_rejects_invalid_content_length():
    async def check():
        with pytest.raises(HTTPException) as exc:
            await read_bounded_body(FakeRequest([], {"content-length": "invalid"}))
        assert exc.value.status_code == 400

    asyncio.run(check())


class FakeRepo:
    def __init__(self):
        self.created = []

    async def create_run(self, run, actor, is_enqueued=False):
        self.created.append(run)


class FakeRedis:
    def __init__(self):
        self.keys = set()

    async def set(self, key, value, ex=None, nx=False):
        if key in self.keys:
            return None
        self.keys.add(key)
        return True

    async def get(self, key):
        return "1" if key in self.keys else None

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.keys:
                self.keys.discard(key)
                removed += 1
        return removed


class FakeServices:
    def __init__(self, repo=None, redis=None):
        self.repo = repo or FakeRepo()
        self.redis = redis
        self.http = None


def _webhook_settings(notifications_enabled=False):
    return Settings(
        env="test",
        database_url="postgresql+asyncpg://app:app@localhost/omega",
        checkpoint_database_url="postgresql://app:app@localhost/omega",
        redis_url="redis://localhost:6379/0",
        jwt_secret="x" * 32,
        github_webhook_secret="github-secret",
        notifications_enabled=notifications_enabled,
    )


def _signed_headers(payload: bytes, secret: str = "github-secret"):
    signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return {"x-github-event": "ping", "x-hub-signature-256": signature}


def test_github_webhook_ping_uses_bounded_body(monkeypatch):
    """Regression: the endpoint must read the request body instead of an undefined name."""
    settings = _webhook_settings()
    monkeypatch.setattr("omega.webhooks.get_settings", lambda: settings)
    payload = json.dumps({"zen": "Keep it logically awesome."}).encode()

    async def check():
        result = await github_webhook(
            FakeRequest([payload], _signed_headers(payload)),
            x_github_event="ping",
            x_hub_signature_256=_signed_headers(payload)["x-hub-signature-256"],
            x_github_delivery=None,
            svc=FakeServices(),
        )
        assert result["status"] == "pong"

    asyncio.run(check())


def test_github_webhook_rejects_bad_signature(monkeypatch):
    settings = _webhook_settings()
    monkeypatch.setattr("omega.webhooks.get_settings", lambda: settings)
    payload = b"{}"

    async def check():
        with pytest.raises(HTTPException) as exc:
            await github_webhook(
                FakeRequest([payload], {"x-github-event": "ping"}),
                x_github_event="ping",
                x_hub_signature_256="sha256=" + "0" * 64,
                x_github_delivery=None,
                svc=FakeServices(),
            )
        assert exc.value.status_code == 401

    asyncio.run(check())


def test_github_webhook_triages_with_notifications_enabled(monkeypatch):
    """The notification branch must use ApprovalPolicy().requires_approval (class
    attribute lookups like is_approval_required do not exist and would crash)."""
    settings = _webhook_settings(notifications_enabled=True)
    monkeypatch.setattr("omega.webhooks.get_settings", lambda: settings)
    notified = []

    async def fake_notify(run, status, **kwargs):
        notified.append((run.id, status))

    monkeypatch.setattr("omega.webhooks.notify_run_status_change", fake_notify)
    monkeypatch.setattr("omega.webhooks.notify_approval_requested", fake_notify)
    payload = json.dumps(
        {"action": "opened", "issue": {"number": 9, "title": "Add docs", "body": "Details"}}
    ).encode()
    headers = _signed_headers(payload)
    svc = FakeServices(redis=FakeRedis())

    async def check():
        result = await github_webhook(
            FakeRequest([payload], headers),
            x_github_event="issues",
            x_hub_signature_256=headers["x-hub-signature-256"],
            x_github_delivery=str(uuid.uuid4()),
            svc=svc,
        )
        assert result["status"] == "triaged"
        assert len(notified) == 1
        assert len(svc.repo.created) == 1

    asyncio.run(check())


def test_github_webhook_releases_replay_marker_on_failure(monkeypatch):
    """A failed delivery must not be acknowledged so GitHub retries are retried."""
    settings = _webhook_settings()
    monkeypatch.setattr("omega.webhooks.get_settings", lambda: settings)
    payload = json.dumps(
        {"action": "opened", "issue": {"number": 11, "title": "Flaky", "body": "x"}}
    ).encode()
    headers = _signed_headers(payload)
    delivery_id = str(uuid.uuid4())

    class FailingRepo(FakeRepo):
        def __init__(self, failures):
            super().__init__()
            self.failures = failures

        async def create_run(self, run, actor, is_enqueued=False):
            if self.failures > 0:
                self.failures -= 1
                raise RuntimeError("database unavailable")
            await super().create_run(run, actor, is_enqueued=is_enqueued)

    svc = FakeServices(repo=FailingRepo(failures=1), redis=FakeRedis())

    async def check():
        with pytest.raises(RuntimeError):
            await github_webhook(
                FakeRequest([payload], headers),
                x_github_event="issues",
                x_hub_signature_256=headers["x-hub-signature-256"],
                x_github_delivery=delivery_id,
                svc=svc,
            )
        # The replay marker was released, so the retry is processed, not dropped.
        result = await github_webhook(
            FakeRequest([payload], headers),
            x_github_event="issues",
            x_hub_signature_256=headers["x-hub-signature-256"],
            x_github_delivery=delivery_id,
            svc=svc,
        )
        assert result["status"] == "triaged"
        assert len(svc.repo.created) == 1

    asyncio.run(check())


def test_github_webhook_asgi_rejects_unsigned_and_accepts_signed(monkeypatch):
    """HTTP-level regression: the mounted route must return 401/202, never 500."""
    import httpx
    from fastapi import FastAPI

    from omega.webhooks import router as webhooks_router

    settings = _webhook_settings()
    monkeypatch.setattr("omega.webhooks.get_settings", lambda: settings)
    test_app = FastAPI()
    test_app.state.services = FakeServices(redis=FakeRedis())
    test_app.include_router(webhooks_router, prefix="/webhooks")

    payload = json.dumps({"zen": "Keep it logically awesome."}).encode()
    signature = _signed_headers(payload)["x-hub-signature-256"]

    async def check():
        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            unsigned = await client.post(
                "/webhooks/github",
                content=payload,
                headers={"X-GitHub-Event": "ping"},
            )
            assert unsigned.status_code == 401

            signed = await client.post(
                "/webhooks/github",
                content=payload,
                headers={
                    "X-GitHub-Event": "ping",
                    "X-Hub-Signature-256": signature,
                },
            )
            assert signed.status_code == 202
            assert signed.json()["status"] == "pong"

    asyncio.run(check())


def test_github_webhook_triages_signed_issue(monkeypatch):
    settings = _webhook_settings()
    monkeypatch.setattr("omega.webhooks.get_settings", lambda: settings)
    payload = json.dumps(
        {"action": "opened", "issue": {"number": 7, "title": "Fix crash on startup", "body": "Steps..."}}
    ).encode()
    headers = _signed_headers(payload)
    svc = FakeServices(redis=FakeRedis())

    async def check():
        result = await github_webhook(
            FakeRequest([payload], headers),
            x_github_event="issues",
            x_hub_signature_256=headers["x-hub-signature-256"],
            x_github_delivery=str(uuid.uuid4()),
            svc=svc,
        )
        assert result["status"] == "triaged"
        assert result["event"] == "issues"
        assert len(svc.repo.created) == 1
        assert svc.repo.created[0].created_by == "github-webhook"

    asyncio.run(check())
