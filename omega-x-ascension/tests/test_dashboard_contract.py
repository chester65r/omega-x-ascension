import re
import tomllib
from html.parser import HTMLParser
from pathlib import Path

import pytest
from pydantic import ValidationError

from omega.api import RunCreate


class DashboardParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.tabs = []
        self.sections = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.append(element_id)
        data_tab = attributes.get("data-tab")
        if tag == "button" and data_tab:
            self.tabs.append(data_tab)
        if tag == "section" and "tab-content" in attributes.get("class", "").split():
            self.sections.append(element_id)


def test_dashboard_tab_order_and_ids_are_consistent():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    parser = DashboardParser()
    parser.feed(html)

    assert len(parser.ids) == len(set(parser.ids)), "duplicate HTML element IDs"
    assert parser.tabs == parser.sections
    selected_ids = set(re.findall(r"\$\('#([^']+)'\)", js))
    # approve-run is intentionally created dynamically for runs awaiting approval.
    assert selected_ids - set(parser.ids) <= {"approve-run"}


def test_local_ai_event_handlers_are_registered_on_page_load():
    js = Path("static/app.js").read_text(encoding="utf-8")
    save_handler = js.index("$('#save-server-btn').addEventListener")
    save_handler_end = js.index("\n  });", save_handler)
    local_ai_block = js.index("// Local on-device model mode:")

    # Regression guard: Local AI must not be initialized only after saving the API URL.
    assert local_ai_block > save_handler_end
    assert "$('#local-ai-check').addEventListener" in js
    assert "$('#local-ai-form').addEventListener" in js
    assert "renderLocalAiMessages();" in js[local_ai_block:]


def test_local_ai_chat_bounds_context_and_has_a_timeout():
    js = Path("static/app.js").read_text(encoding="utf-8")
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert "localAiMessages.filter((m) => m !== pending).slice(-4)" in js
    assert "window.setTimeout(() => requestController.abort(), 180000)" in js
    assert "window.clearTimeout(requestTimeout)" in js
    assert "max_tokens: 256" in js
    assert 'id="local-ai-prompt" rows="3" maxlength="1200"' in html


def test_dashboard_calls_out_file_and_shell_flags_separately():
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert "OMEGA_ENABLE_COMPUTER_FILES" in html
    assert "OMEGA_ENABLE_COMPUTER_EXECUTION" in html
    assert "not a hardened per-job VM" in html


def test_dashboard_has_local_ai_tool_and_chat_controls():
    html = Path("static/index.html").read_text(encoding="utf-8")
    for required in (
        'id="tool-local-ai"',
        'id="local-ai-url"',
        'id="local-ai-check"',
        'id="local-ai-form"',
        'id="local-ai-prompt"',
        'id="local-ai-send"',
    ):
        assert required in html


def test_local_ai_android_mixed_content_is_restricted_to_loopback():
    main_activity = Path(
        "../android/app/src/main/java/com/omega/ascension/MainActivity.java"
    ).read_text()
    network_config = Path("../android/app/src/main/res/xml/network_security_config.xml").read_text()
    assert "MIXED_CONTENT_COMPATIBILITY_MODE" in main_activity
    assert 'cleartextTrafficPermitted="false"' in network_config
    assert "127.0.0.1" in network_config and "localhost" in network_config


def test_run_create_accepts_short_greetings_but_rejects_blank_goals():
    run = RunCreate(goal=" Hi ", task_type="reasoning")
    assert run.goal == "Hi"

    with pytest.raises(ValidationError):
        RunCreate(goal="   ", task_type="reasoning")


def test_chat_does_not_reject_non_empty_prompts_shorter_than_three_characters():
    js = Path("static/app.js").read_text(encoding="utf-8")
    assert "if (clean.length < 3)" not in js
    assert "at least 3 characters to start an agent task" not in js


def test_personal_assistant_does_not_fake_backend_responses():
    js = Path("static/app.js").read_text(encoding="utf-8")
    assert "Cloud agent tasks require a signed JWT" in js
    assert "No fake answer was generated." in js
    assert "run.status === 'succeeded'" in js
    assert "run.status === 'failed'" in js


def test_model_health_ui_uses_real_provider_status_endpoint():
    js = Path("static/app.js").read_text(encoding="utf-8")
    main = Path("src/omega/main.py").read_text(encoding="utf-8")
    router = Path("src/omega/model_router.py").read_text(encoding="utf-8")
    assert "apiFetch('/health/models')" in js
    assert '@app.get("/health/models")' in main
    assert "await gateway.healthy()" in router


def test_tool_health_ui_explains_policy_limited_features():
    js = Path("static/app.js").read_text(encoding="utf-8")
    main = Path("src/omega/main.py").read_text(encoding="utf-8")
    assert "apiFetch('/health/tools')" in js
    assert "terminal disabled by server policy" in js
    assert '@app.get("/health/tools")' in main
    assert "requires_explicit_scope_and_approval" in main


def test_native_browser_is_available_without_cloud_backend():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    main = Path("../android/app/src/main/java/com/omega/ascension/MainActivity.java").read_text(
        encoding="utf-8"
    )
    browser = Path(
        "../android/app/src/main/java/com/omega/ascension/BrowserActivity.java"
    ).read_text(encoding="utf-8")
    assert 'id="browser-full-open"' in html
    assert "openNativeBrowser(cleanQuery)" in js
    assert "nativeBrowserTarget" in js
    assert 'case "openBrowser"' in main
    assert "BrowserActivity.EXTRA_URL" in main
    assert "setAllowFileAccess(false)" in browser
    assert "setAllowContentAccess(false)" in browser
    assert "WebSettings.MIXED_CONTENT_NEVER_ALLOW" in browser
    assert "addJavascriptInterface" not in browser


def test_optional_agent_tools_are_opt_in_and_sent_to_the_real_workflow_api():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    for element_id in (
        "assistant-use-remote-mcp",
        "assistant-use-workspace-files",
        "assistant-allow-file-edits",
        "assistant-use-computer",
        "browser-use-remote-mcp",
    ):
        assert f'id="{element_id}"' in html
    assert "actions.push('use_remote_mcp')" in js
    assert "actions.push('use_workspace_files')" in js
    assert "actions.push('write_workspace_files')" in js
    assert "actions.push('execute_code')" in js
    assert "requested_actions: requestedActions" in js
    # Tool choices must be one-run opt-ins, not sticky permission grants.
    assert "$('#assistant-use-remote-mcp').checked = false;" in js
    assert "$('#assistant-use-workspace-files').checked = false;" in js
    assert "$('#assistant-allow-file-edits').checked = false;" in js
    assert "$('#assistant-use-computer').checked = false;" in js
    assert "$('#browser-use-remote-mcp').checked = false;" in js


def test_approval_polling_resumes_after_user_approves_a_tool():
    js = Path("static/app.js").read_text(encoding="utf-8")
    assert "Approval required · waiting for your decision" in js
    assert "() => pollBrowserAgentRun(runId, elapsed + 5000)" in js
    assert "() => pollAssistantRun(runId, responseIndex, elapsed + 5000)" in js
    assert "requested action, and approve it if you trust the request" in js


def test_agent_tool_controls_have_mobile_friendly_styles():
    css = Path("static/style.css").read_text(encoding="utf-8")
    assert ".assistant-tool-options" in css
    assert ".assistant-tool-option" in css
    assert ".browser-agent-option" in css
    assert "@media (max-width: 520px)" in css


def test_chat_interface_has_sidebar_local_history_and_safe_markdown():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    css = Path("static/style.css").read_text(encoding="utf-8")
    for required in (
        'id="chat-sidebar"',
        'id="sidebar-toggle"',
        'id="assistant-new-chat"',
        'id="chat-history"',
        'id="assistant-tool-details"',
        'placeholder="Message OMEGA…"',
    ):
        assert required in html
    assert "omega-chat-history-v1" in js
    assert "function openSavedConversation" in js
    assert "function startNewConversation" in js
    assert "function renderMessageMarkdown" in js
    assert "assistantMessages.slice(-24)" in js
    assert "slice(0, 3500)" in js
    assert "link.rel = 'noopener noreferrer'" in js
    assert ".assistant-card.has-messages .assistant-empty-state { display: none; }" in css
    assert ".chat-sidebar" in css



def test_android_first_launch_enrolls_without_manual_activation_key():
    js = Path("static/app.js").read_text(encoding="utf-8")
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert "'/v1/auth/guest'" in js
    assert "async function enrollNativeGuestDevice()" in js
    assert "enrollNativeGuestDevice();" in js
    assert "saveRefreshTokenForDevice(refreshToken)" in js
    assert "getStoredRefreshToken" in js
    assert "First-time setup only: activate this device with the one-time owner key." not in js
    assert "One-time device activation key" in html  # browser compatibility only



def test_dashboard_initially_exposes_the_assistant_tab_before_javascript_runs():
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert '<button class="tab active" data-tab="assistant"' in html
    assert '<section id="assistant" class="tab-content active"' in html



def test_android_guest_credential_is_saved_before_network_verification():
    js = Path("static/app.js").read_text(encoding="utf-8")
    startup_start = js.index("async function enrollNativeGuestDevice()")
    startup_end = js.index("\n  function initializeNativeDeviceSession()", startup_start)
    startup = js[startup_start:startup_end]
    save_credential = startup.index("saveRefreshTokenForDevice(refreshToken)")
    network_probe = startup.index("await api('/v1/runs?limit=1')")
    assert save_credential < network_probe
    assert "The server returned an incomplete guest session." in startup
    assert "Guest session was saved" in startup


def test_android_api_and_session_are_internal_and_navigation_is_simplified():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    css = Path("static/style.css").read_text(encoding="utf-8")
    assert "let apiBase = isNativeApp ? DEFAULT_API_BASE" in js
    assert "initializeNativeDeviceSession();" in js
    assert "'/v1/auth/refresh'" in js
    assert "storeRefreshToken" in js
    assert 'placeholder="One-time device activation key"' in html
    assert "signed JWT once" not in html
    assert '<span>Workspace</span>' in html
    assert "Cloud access is secured on this device" in html
    assert "#tool-overview,#tool-runs,#tool-local-ai{display:none!important}" in css
    assert "body.native-app #api-base" in css
    assert "body.native-app #save-server-btn" in css



def test_release_version_is_consistent_across_android_api_and_dashboard():
    app_root = Path(__file__).resolve().parents[1]
    repo_root = app_root.parent
    version = tomllib.loads(
        (app_root / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]

    assert version == "0.8.6"
    package_version = (app_root / "src/omega/__init__.py").read_text(encoding="utf-8")
    html = (app_root / "static/index.html").read_text(encoding="utf-8")
    js = (app_root / "static/app.js").read_text(encoding="utf-8")
    css = (app_root / "static/style.css").read_text(encoding="utf-8")
    service_worker = (app_root / "static/sw.js").read_text(encoding="utf-8")
    model_adapter = (app_root / "src/omega/adapters/models.py").read_text(encoding="utf-8")
    remote_mcp = (app_root / "src/omega/remote_mcp.py").read_text(encoding="utf-8")
    android_gradle = (repo_root / "android/app/build.gradle").read_text(encoding="utf-8")
    android_dockerfile = (repo_root / "android/Dockerfile").read_text(encoding="utf-8")

    assert f'__version__ = "{version}"' in package_version
    assert f'<span class="section-chip">VERSION {version}</span>' in html
    assert f'<dd id="about-version">{version}</dd>' in html
    assert f"version: '{version}'," in js
    assert f"OMEGA-X {version}" in css
    assert f'const CACHE_NAME = "omega-x-v{version}";' in service_worker
    assert f"omega-x-ascension/{version}" in model_adapter
    assert f'"version": "{version}"' in remote_mcp
    assert f'versionName "{version}"' in android_gradle
    assert f"omega-x-ascension-{version}-debug.apk" in android_dockerfile

def test_application_and_legacy_rewrite_use_render_only():
    from pathlib import Path
    import json

    js = Path("static/app.js").read_text(encoding="utf-8")
    rewrite = json.loads(Path("vercel.json").read_text(encoding="utf-8"))

    render_url = "https://omega-x-ascension-api.onrender.com"
    assert f"const DEFAULT_API_BASE = '{render_url}';" in js
    assert "railway.app" not in js.lower()

    destinations = [rule["destination"] for rule in rewrite["rewrites"]]
    assert all(render_url in destination for destination in destinations)
    assert all("railway.app" not in destination.lower() for destination in destinations)
