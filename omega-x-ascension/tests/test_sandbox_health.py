from __future__ import annotations

import asyncio

import httpx
from fastapi.testclient import TestClient

from omega import sandbox_service
from omega.sandbox_service import SandboxRuntime
from omega.tools.computer import ComputerTool


def test_sandbox_health_accepts_no_header_for_render_but_validates_optional_header(
    monkeypatch, tmp_path
):
    token = "a" * 64
    monkeypatch.setenv("OMEGA_SANDBOX_TOKEN", token)
    monkeypatch.setattr(sandbox_service, "runtime", SandboxRuntime(tmp_path / "workspace"))
    client = TestClient(sandbox_service.app)

    render_health = client.get("/health")
    assert render_health.status_code == 200
    assert render_health.json()["workspace_ready"] is True
    assert render_health.json()["command_execution"] is False

    rejected = client.get(
        "/health",
        headers={"X-OMEGA-SANDBOX-TOKEN": "b" * 64},
    )
    assert rejected.status_code == 401
    accepted = client.get(
        "/health",
        headers={"X-OMEGA-SANDBOX-TOKEN": token},
    )
    assert accepted.status_code == 200
    assert token not in accepted.text


def test_sandbox_health_fails_clearly_when_shared_credential_is_missing(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.delenv("OMEGA_SANDBOX_TOKEN", raising=False)
    monkeypatch.setattr(sandbox_service, "runtime", SandboxRuntime(tmp_path / "workspace"))
    response = TestClient(sandbox_service.app).get("/health")

    assert response.status_code == 503
    assert response.json()["detail"] == "sandbox service credential is not configured"
    assert "shared service credential is missing or too short" in caplog.text


def test_sandbox_health_fails_clearly_when_workspace_is_not_writable(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("OMEGA_SANDBOX_TOKEN", "c" * 64)
    monkeypatch.setattr(sandbox_service, "runtime", SandboxRuntime(tmp_path / "workspace"))

    def reject_workspace(_root):
        raise PermissionError("private path details should not be returned to clients")

    monkeypatch.setattr(sandbox_service, "_check_workspace_writable", reject_workspace)
    response = TestClient(sandbox_service.app).get("/health")

    assert response.status_code == 503
    assert response.json()["detail"] == "sandbox workspace is not writable"
    assert "workspace is not writable (error_type=PermissionError)" in caplog.text
    assert "private path details" not in response.text


def test_computer_health_sends_shared_credential_to_sandbox_probe():
    async def check():
        async def handler(request):
            assert request.url.path == "/health"
            assert request.headers.get("X-OMEGA-SANDBOX-TOKEN") == "d" * 64
            return httpx.Response(200, json={"status": "ok"}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tool = ComputerTool(
                client=client,
                token="d" * 64,
                enabled=False,
                files_enabled=True,
            )
            assert await tool.health() is True

    asyncio.run(check())
