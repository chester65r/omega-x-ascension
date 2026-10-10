import asyncio
import runpy
from types import SimpleNamespace

import pytest


verify_live_inference = runpy.run_path("scripts/verify_model_provider.py")["verify_live_inference"]


class FakeGateway:
    name = "fixture-provider"

    def __init__(self, response):
        self.response = response
        self.calls = []

    async def complete(self, *, system, prompt):
        self.calls.append((system, prompt))
        return self.response


class FakeRouter:
    def __init__(self, gateway):
        self.gateway = gateway
        self.capability = None

    async def select(self, capability):
        self.capability = capability
        return SimpleNamespace(gateway=self.gateway)


def test_live_provider_probe_runs_a_real_completion_and_reports_safe_metadata():
    async def check():
        gateway = FakeGateway("Model is responding.")
        router = FakeRouter(gateway)
        result = await verify_live_inference(router)
        assert result == ("fixture-provider", len("Model is responding."))
        assert router.capability == "planning"
        assert len(gateway.calls) == 1
        assert "verifying an ai model connection" in gateway.calls[0][0].lower()

    asyncio.run(check())


def test_live_provider_probe_rejects_empty_completions():
    async def check():
        router = FakeRouter(FakeGateway("  "))
        with pytest.raises(RuntimeError, match="empty completion"):
            await verify_live_inference(router)

    asyncio.run(check())
