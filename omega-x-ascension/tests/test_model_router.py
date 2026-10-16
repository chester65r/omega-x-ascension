import asyncio

import httpx
import pytest

from omega.model_router import ModelExecutionFailed, ModelRouter


class FakeGateway:
    capabilities = frozenset({"planning"})

    def __init__(self, name, priority, result=None, error=None):
        self.name = name
        self.priority = priority
        self.result = result
        self.error = error
        self.calls = 0

    async def healthy(self):
        return True

    async def complete(self, *, system, prompt):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class FakeRegistry:
    def __init__(self, gateways):
        self.gateways = gateways

    def all(self):
        return tuple(self.gateways)


def test_model_router_falls_back_to_next_healthy_provider():
    async def check():
        primary = FakeGateway("primary", 100, error=TimeoutError("provider timeout"))
        fallback = FakeGateway("fallback", 50, result="verified response")
        router = ModelRouter(FakeRegistry([fallback, primary]))

        result = await router.complete("planning", system="system", prompt="prompt")

        assert result == "verified response"
        assert primary.calls == 1
        assert fallback.calls == 1

    asyncio.run(check())


def test_model_router_rejects_empty_completion_and_tries_fallback():
    async def check():
        primary = FakeGateway("primary", 100, result="  ")
        fallback = FakeGateway("fallback", 50, result="fallback response")
        router = ModelRouter(FakeRegistry([primary, fallback]))

        assert await router.complete("planning", system="s", prompt="p") == "fallback response"
        assert primary.calls == 1
        assert fallback.calls == 1

    asyncio.run(check())


def test_model_router_tries_third_provider_when_first_two_fail():
    async def check():
        primary = FakeGateway("primary", 100, error=_status_error(429))
        secondary = FakeGateway("secondary", 80, error=_status_error(503))
        tertiary = FakeGateway("tertiary", 50, result="tertiary response")
        router = ModelRouter(FakeRegistry([tertiary, secondary, primary]))

        result = await router.complete("planning", system="s", prompt="p")

        assert result == "tertiary response"
        assert primary.calls == 1
        assert secondary.calls == 1
        assert tertiary.calls == 1

    asyncio.run(check())


def test_model_router_reports_safe_failure_when_all_providers_fail():
    async def check():
        router = ModelRouter(
            FakeRegistry(
                [
                    FakeGateway(
                        "primary",
                        100,
                        error=TimeoutError("secret-bearing provider error"),
                    ),
                    FakeGateway("fallback", 50, error=ConnectionError("unavailable")),
                ]
            )
        )
        with pytest.raises(
            ModelExecutionFailed, match="all 2 attempted model providers failed"
        ):
            await router.complete("planning", system="s", prompt="p")

    asyncio.run(check())


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.example/v1/chat/completions")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        f"provider returned HTTP {status}",
        request=request,
        response=response,
    )


def test_model_router_marks_payment_required_as_non_retryable():
    async def check():
        provider = FakeGateway("huggingface", 80, error=_status_error(402))
        router = ModelRouter(FakeRegistry([provider]))

        with pytest.raises(ModelExecutionFailed) as caught:
            await router.complete("planning", system="s", prompt="p")

        assert caught.value.retryable is False
        assert provider.calls == 1

    asyncio.run(check())


def test_model_router_keeps_transient_provider_status_retryable():
    async def check():
        provider = FakeGateway("temporary-outage", 80, error=_status_error(503))
        router = ModelRouter(FakeRegistry([provider]))

        with pytest.raises(ModelExecutionFailed) as caught:
            await router.complete("planning", system="s", prompt="p")

        assert caught.value.retryable is True

    asyncio.run(check())
