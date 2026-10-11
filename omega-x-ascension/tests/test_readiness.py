import asyncio
from types import SimpleNamespace

from omega.main import app, ready


class DummyConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, *_args):
        return None


class DummyEngine:
    def connect(self):
        return DummyConnection()


class DummyRedis:
    async def ping(self):
        return True


class DummyComputer:
    def __init__(self, enabled=False, files_enabled=False, healthy=True):
        self.enabled = enabled
        self.files_enabled = files_enabled
        self._healthy = healthy

    async def health(self):
        return self._healthy


class DummyRouter:
    def __init__(self, providers):
        self.providers = providers

    async def status(self):
        return self.providers


def call_ready_with_providers(providers, computer=None):
    had_services = hasattr(app.state, "services")
    previous = getattr(app.state, "services", None)
    app.state.services = SimpleNamespace(
        engine=DummyEngine(),
        redis=DummyRedis(),
        computer=computer or DummyComputer(),
        router=DummyRouter(providers),
    )

    async def invoke():
        return await ready()

    try:
        return asyncio.run(invoke())
    finally:
        if had_services:
            app.state.services = previous
        else:
            delattr(app.state, "services")


def test_readiness_is_503_when_no_model_is_healthy():
    response = call_ready_with_providers([])
    assert response.status_code == 503
    assert b"no_healthy_model_configured" in response.body


def test_readiness_requires_and_reports_a_healthy_model():
    response = call_ready_with_providers([{"name": "fixture", "healthy": True}])
    assert response["status"] == "ready"
    assert response["configured_models"] == 1
    assert response["healthy_models"] == 1


def test_readiness_is_503_when_enabled_sandbox_capability_is_unavailable():
    response = call_ready_with_providers(
        [{"name": "fixture", "healthy": True}],
        computer=DummyComputer(enabled=True, files_enabled=True, healthy=False),
    )
    assert response.status_code == 503
    assert b'"reason":"RuntimeError"' in response.body
