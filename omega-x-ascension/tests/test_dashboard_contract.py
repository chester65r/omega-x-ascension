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
