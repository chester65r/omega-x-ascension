import asyncio
from urllib.parse import urlparse

import httpx
import pytest

from omega.tools.browser import BrowserTool


def make_tool(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = BrowserTool(client)

    async def allow_fixture_urls(url):
        parsed = urlparse(url)
        if parsed.hostname not in {"public.example", "duckduckgo.com", "html.duckduckgo.com"}:
            raise ValueError("private, local, or non-public network targets are blocked")
        return "93.184.216.34"

    tool._validate_url = allow_fixture_urls
    return tool, client


def test_browser_proxy_injects_safe_base_and_routes_clicks_through_parent():
    async def check():
        async def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<html><head><title>Start</title></head><body><a href='/next'>Next</a></body></html>",
                request=request,
            )

        tool, client = make_tool(handler)
        try:
            html, content_type = await tool.proxy("https://public.example/start")
            assert content_type.startswith("text/html")
            assert '<base href="https://public.example/start">' in html
            assert "data-omega-browser-bridge" in html
            assert "window.parent.postMessage" in html
            assert "omega-browser" in html
            assert "This preview supports GET search forms only." in html
        finally:
            await client.aclose()

    asyncio.run(check())


def test_browser_revalidates_each_redirect_target():
    async def check():
        seen = []

        async def handler(request):
            seen.append(str(request.url))
            return httpx.Response(
                302,
                headers={"location": "http://127.0.0.1:8000/secret"},
                request=request,
            )

        tool, client = make_tool(handler)
        try:
            with pytest.raises(ValueError, match="private, local"):
                await tool._get_public("https://public.example/redirect")
            assert seen == ["https://93.184.216.34/redirect"]
        finally:
            await client.aclose()

    asyncio.run(check())



def test_browser_pins_socket_target_and_preserves_host_and_tls_name():
    async def check():
        async def handler(request):
            assert request.url.host == "93.184.216.34"
            assert request.headers["host"] == "public.example"
            assert request.headers["connection"] == "close"
            assert request.extensions["sni_hostname"] == b"public.example"
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="pinned",
                request=request,
            )

        tool, client = make_tool(handler)
        try:
            response, final_url = await tool._get_public(
                "https://public.example/resource",
                timeout=5,
                headers={"User-Agent": "test"},
            )
            assert response.text == "pinned"
            assert final_url == "https://public.example/resource"
        finally:
            await client.aclose()

    asyncio.run(check())


def test_browser_search_normalizes_duckduckgo_redirect_links():
    async def check():
        async def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<div class="result"><h2 class="result__title">'
                    '<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpublic.example%2Fpage">Example result</a>'
                    '</h2><div class="result__snippet">A useful result</div></div>'
                ),
                request=request,
            )

        tool, client = make_tool(handler)
        try:
            result = await tool.search("example")
            assert len(result["results"]) == 1
            assert result["results"][0]["url"] == "https://public.example/page"
            assert result["results"][0]["title"] == "Example result"
            assert result["results"][0]["snippet"] == "A useful result"
        finally:
            await client.aclose()

    asyncio.run(check())


def test_browser_proxy_converts_json_into_readable_safe_html():
    async def check():
        async def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                text='{"status":"ok","text":"<script>alert(1)</script>"}',
                request=request,
            )

        tool, client = make_tool(handler)
        try:
            html, _ = await tool.proxy("https://public.example/status")
            assert "<pre" in html
            assert "&lt;script&gt;" in html
            assert "<script>alert(1)</script>" not in html
        finally:
            await client.aclose()

    asyncio.run(check())
