import asyncio
from types import SimpleNamespace

from omega.api import BROWSER_PROXY_HEADERS, browser_proxy


class FakeBrowser:
    async def proxy(self, url: str) -> tuple[str, str]:
        return "<html><body>hello</body></html>", "text/html; charset=utf-8"


def test_browser_proxy_response_is_sandboxed_and_not_cached():
    async def check():
        services = SimpleNamespace(browser=FakeBrowser())
        response = await browser_proxy(url="https://public.example/", principal=None, svc=services)

        assert response.headers["content-security-policy"] == "sandbox allow-scripts allow-forms"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["cache-control"] == "no-store"
        assert "allow-same-origin" not in BROWSER_PROXY_HEADERS["Content-Security-Policy"]

    asyncio.run(check())
