from html.parser import HTMLParser
from pathlib import Path
import re


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


def test_dashboard_has_local_ai_tab_and_chat_controls():
    html = Path("static/index.html").read_text(encoding="utf-8")
    for required in (
        'data-tab="local-ai"',
        'id="local-ai-url"',
        'id="local-ai-check"',
        'id="local-ai-form"',
        'id="local-ai-prompt"',
        'id="local-ai-send"',
    ):
        assert required in html


def test_local_ai_android_mixed_content_is_restricted_to_loopback():
    main_activity = Path("../android/app/src/main/java/com/omega/ascension/MainActivity.java").read_text()
    network_config = Path("../android/app/src/main/res/xml/network_security_config.xml").read_text()
    assert "MIXED_CONTENT_COMPATIBILITY_MODE" in main_activity
    assert 'cleartextTrafficPermitted="false"' in network_config
    assert "127.0.0.1" in network_config and "localhost" in network_config



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



def test_native_browser_is_available_without_cloud_backend():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    main = Path("../android/app/src/main/java/com/omega/ascension/MainActivity.java").read_text(encoding="utf-8")
    browser = Path("../android/app/src/main/java/com/omega/ascension/BrowserActivity.java").read_text(encoding="utf-8")
    assert 'id="browser-full-open"' in html
    assert "openNativeBrowser(cleanQuery)" in js
    assert "nativeBrowserTarget" in js
    assert 'case "openBrowser"' in main
    assert "BrowserActivity.EXTRA_URL" in main
    assert "setAllowFileAccess(false)" in browser
    assert "setAllowContentAccess(false)" in browser
    assert "WebSettings.MIXED_CONTENT_NEVER_ALLOW" in browser
    assert "addJavascriptInterface" not in browser
