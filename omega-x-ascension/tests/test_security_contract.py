import asyncio
from pathlib import Path

import httpx
import pytest

from omega.tools.browser import BrowserTool
from omega.tools.computer import ComputerTool
from omega.sandbox_service import SandboxRuntime


def test_computer_execution_is_disabled_by_default():
    tool = ComputerTool()
    with pytest.raises(RuntimeError, match="disabled"):
        asyncio.run(tool.execute("echo blocked"))


def test_sandbox_workspace_blocks_path_traversal(tmp_path):
    runtime = SandboxRuntime(tmp_path / "workspace")
    tenant_id = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(ValueError, match="escapes"):
        runtime.write_file(tenant_id, "../escape.txt", "blocked")
    assert not (tmp_path / "escape.txt").exists()


def test_sandbox_commands_do_not_inherit_service_secrets(tmp_path, monkeypatch):
    runtime = SandboxRuntime(tmp_path / "workspace")
    monkeypatch.setenv("OMEGA_SANDBOX_TOKEN", "do-not-inherit-this")
    result = asyncio.run(runtime.execute(
        "00000000-0000-0000-0000-000000000001",
        "printf '%s' \"$OMEGA_SANDBOX_TOKEN\"",
        timeout=3,
    ))
    assert result["stdout"] == ""
    assert result["returncode"] == 0


def test_sandbox_output_is_bounded(tmp_path):
    runtime = SandboxRuntime(tmp_path / "workspace")
    result = asyncio.run(runtime.execute(
        "00000000-0000-0000-0000-000000000001",
        "python -c 'print(\"x\" * 200000)'",
        timeout=5,
    ))
    assert result["output_limited"] is True
    assert len(result["stdout"]) <= 16_000


def test_browser_blocks_private_literal_addresses():
    async def check():
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError):
                await BrowserTool(client)._validate_url("http://127.0.0.1:8000")

    asyncio.run(check())


def test_dashboard_iframe_does_not_grant_same_origin():
    index = Path("static/index.html").read_text()
    assert 'sandbox="allow-scripts allow-forms allow-popups"' in index
    assert "allow-same-origin" not in index


def test_docker_image_copies_static_assets():
    dockerfile = Path("Dockerfile").read_text()
    assert "COPY static ./static" in dockerfile


def test_job_requeue_has_app_update_privilege():
    migration = Path("alembic/versions/0001_production_baseline.py").read_text()
    assert "GRANT SELECT,INSERT,UPDATE ON workflow_jobs TO omega_app" in migration


def test_direct_computer_execution_requires_explicit_scopes():
    api = Path("src/omega/api.py").read_text()
    assert 'scopes=["runs:write", "runs:approve", "computer:execute"]' in api
    assert 'scopes=["runs:write", "runs:approve", "computer:write"]' in api


def test_agent_only_executes_computer_commands_when_requested_and_approved():
    workflow = Path("src/omega/workflow.py").read_text()
    assert '"execute_code" not in state.get("requested_actions", [])' in workflow
    assert 'workspace_id=state.get("workspace_id")' in workflow
    compose = Path("docker-compose.yml").read_text()
    assert "sandbox_internal:" in compose and "internal: true" in compose
    assert "cap_drop: [ALL]" in compose
    assert "network_mode: host" not in compose


def test_browser_response_size_is_bounded_without_external_network(tmp_path):
    async def check():
        async def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"x" * 2_000_001,
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tool = BrowserTool(client)

            async def allow_test_host(_url):
                return None

            tool._validate_url = allow_test_host
            with pytest.raises(ValueError, match="2 MB limit"):
                await tool._get_public("https://example.invalid")

    asyncio.run(check())


def test_sandbox_does_not_receive_backend_env_file_or_model_credentials():
    compose = Path("docker-compose.yml").read_text()
    sandbox = compose.split("  sandbox:\n", 1)[1].split("\n  ollama:", 1)[0]
    assert "env_file: .env" not in sandbox
    assert "OMEGA_SANDBOX_TOKEN:" in sandbox
    assert "OMEGA_DATABASE_URL" not in sandbox
    assert "OMEGA_MODEL_PROVIDERS" not in sandbox
