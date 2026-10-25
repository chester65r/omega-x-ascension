from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from omega.adapters.models import GeminiGateway, OpenAICompatibleGateway
from omega.config import ProviderConfig


class SequencedClient:
    """Return configured HTTP outcomes so retry behavior is tested without network access."""

    def __init__(self, statuses: list[int], payload: dict):
        self.statuses = statuses
        self.payload = payload
        self.calls = 0

    async def post(self, url, **kwargs):
        self.calls += 1
        status = self.statuses[min(self.calls - 1, len(self.statuses) - 1)]
        request = httpx.Request("POST", str(url))
        if status != 200:
            response = httpx.Response(status, request=request)
            response.raise_for_status()
        return httpx.Response(200, json=self.payload, request=request)


def make_gateway(kind: str, client: SequencedClient):
    if kind == "gemini":
        return GeminiGateway(
            api_key="test-secret",
            model="gemini-3.8-flash",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            priority=100,
            timeout_seconds=10,
            client=client,
        )
    config = ProviderConfig(
        name="openai-test",
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("test-secret"),
        model="gpt-4.1-mini",
        capabilities=frozenset({"planning"}),
        priority=100,
    )
    return OpenAICompatibleGateway(config, client)


@pytest.mark.parametrize("kind", ["gemini", "openai"])
def test_gateway_retries_transient_503_and_returns_response(kind):
    async def check():
        payload = (
            {"candidates": [{"content": {"parts": [{"text": "retried successfully"}]}}]}
            if kind == "gemini"
            else {"choices": [{"message": {"content": "retried successfully"}}]}
        )
        client = SequencedClient([503, 200], payload)
        gateway = make_gateway(kind, client)

        result = await gateway.complete(system="system", prompt="Hi")

        assert result == "retried successfully"
        assert client.calls == 2

    asyncio.run(check())


@pytest.mark.parametrize("kind", ["gemini", "openai"])
@pytest.mark.parametrize("status", [402, 403])
def test_gateway_does_not_retry_quota_or_authorization_failures(kind, status):
    async def check():
        payload = (
            {"candidates": [{"content": {"parts": [{"text": "should not run"}]}}]}
            if kind == "gemini"
            else {"choices": [{"message": {"content": "should not run"}}]}
        )
        client = SequencedClient([status, 200], payload)
        gateway = make_gateway(kind, client)

        with pytest.raises(httpx.HTTPStatusError):
            await gateway.complete(system="system", prompt="Hi")

        assert client.calls == 1

    asyncio.run(check())


def test_retry_predicate_classifies_provider_errors():
    from omega.adapters.models import _retryable_provider_error

    request = httpx.Request("POST", "https://provider.invalid/v1/chat/completions")

    def status_error(status: int) -> httpx.HTTPStatusError:
        response = httpx.Response(status, request=request)
        return httpx.HTTPStatusError("provider error", request=request, response=response)

    assert _retryable_provider_error(httpx.ConnectError("down", request=request))
    assert _retryable_provider_error(status_error(503))
    assert _retryable_provider_error(status_error(500))
    assert not _retryable_provider_error(status_error(401))
    assert not _retryable_provider_error(status_error(403))
    assert not _retryable_provider_error(ValueError("bad payload"))
    # Cancellation is a BaseException, not an Exception; it must never be retried.
    assert not _retryable_provider_error(asyncio.CancelledError())
