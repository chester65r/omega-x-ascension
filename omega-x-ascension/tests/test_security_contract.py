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


def test_workspace_files_can_work_without_enabling_shell_execution():
    async def check():
        async def handler(request):
            assert request.headers.get("X-OMEGA-SANDBOX-TOKEN") == "s" * 32
            assert request.url.path == "/files"
            return httpx.Response(
                200,
                json={"path": ".", "entries": [{"name": "note.txt", "type": "file", "size": 2}], "truncated": False},
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tool = ComputerTool(
                client=client,
                token="s" * 32,
                enabled=False,
                files_enabled=True,
            )
            result = await tool.list_dir(".", workspace_id="00000000-0000-0000-0000-000000000001")
            assert result["entries"][0]["name"] == "note.txt"
            with pytest.raises(RuntimeError, match="execution is disabled"):
                await tool.execute("echo blocked")

    asyncio.run(check())


def test_workspace_file_tools_can_be_disabled_independently():
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={}, request=request)
        )) as client:
            tool = ComputerTool(
                client=client,
                token="s" * 32,
                enabled=True,
                files_enabled=False,
            )
            with pytest.raises(RuntimeError, match="file tools are disabled"):
                await tool.list_dir(".")

    asyncio.run(check())


def test_file_routes_use_separate_policy_and_are_not_duplicated():
    api = Path("src/omega/api.py").read_text(encoding="utf-8")
    assert api.count('@router.get("/computer/files")') == 1
    assert api.count("require_computer_files_enabled(svc)") == 4  # declaration plus three route checks
    assert 'scopes=["runs:write", "runs:approve", "computer:execute"]' in api


def test_sandbox_workspace_file_crud_is_tenant_scoped(tmp_path):
    runtime = SandboxRuntime(tmp_path / "workspace")
    tenant_a = "11111111-1111-1111-1111-111111111111"
    tenant_b = "22222222-2222-2222-2222-222222222222"

    written = runtime.write_file(tenant_a, "src/main.py", "print('ok')\\n")
    assert written["written"] is True
    assert written["bytes"] == len("print('ok')\\n".encode("utf-8"))
    assert runtime.read_file(tenant_a, "src/main.py")["content"] == "print('ok')\\n"
    assert runtime.list_dir(tenant_a, "src")["entries"][0]["name"] == "main.py"
    assert runtime.list_dir(tenant_b)["entries"] == []
    with pytest.raises(ValueError, match="regular file"):
        runtime.read_file(tenant_b, "src/main.py")


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
    assert 'sandbox="allow-scripts allow-forms"' in index
    assert "allow-same-origin" not in index
    java = Path("../android/app/src/main/java/com/omega/ascension/MainActivity.java").read_text()
    assert "WebViewCompat.addWebMessageListener" in java
    assert "if (!isMainFrame || !isTrustedAppOrigin(sourceOrigin))" in java
    assert "addJavascriptInterface" not in java


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


def test_browser_navigation_is_routed_through_proxy():
    browser = Path("src/omega/tools/browser.py").read_text(encoding="utf-8")
    dashboard = Path("static/app.js").read_text(encoding="utf-8")
    assert "data-omega-browser-bridge" in browser
    assert "window.parent.postMessage" in browser
    assert "event.source !== frame.contentWindow" in dashboard
    assert "navigateTo(url.href)" in dashboard
    assert "Only public HTTP/HTTPS navigation is allowed" in dashboard


def test_audit_log_endpoint_is_authenticated_and_tenant_scoped():
    api = Path("src/omega/api.py").read_text(encoding="utf-8")
    database = Path("src/omega/adapters/database.py").read_text(encoding="utf-8")
    assert '@router.get("/events"' in api
    assert 'scopes=["runs:read"]' in api
    assert "self._tenant_session(tenant_id)" in database
    assert "AuditEventRow.tenant_id == tenant_id" in database


def test_mobile_assistant_logs_and_about_controls_exist():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    for element_id in (
        "assistant-form", "assistant-prompt", "assistant-voice", "assistant-speak",
        "assistant-share", "assistant-clear", "logs-list", "server-audit-list",
        "logs-export", "about-title", "about-device-refresh", "browser-results",
    ):
        assert f'id="{element_id}"' in html
    for behavior in (
        "/v1/runs", "/v1/events?limit=100", "/health/models",
        "omega:native", "postMessage", "Clear local app logs",
    ):
        assert behavior in js or behavior in html



def test_native_browser_does_not_expose_privileged_javascript_bridge():
    browser = Path("../android/app/src/main/java/com/omega/ascension/BrowserActivity.java").read_text(encoding="utf-8")
    assert "addJavascriptInterface" not in browser
    assert "setAllowFileAccess(false)" in browser
    assert "setAllowContentAccess(false)" in browser
    assert "WebSettings.MIXED_CONTENT_NEVER_ALLOW" in browser
    assert "String scheme = uri.getScheme()" in browser
    assert '"https".equalsIgnoreCase(scheme)' in browser
    assert '"http".equalsIgnoreCase(scheme)' in browser
