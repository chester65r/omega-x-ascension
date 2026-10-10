from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


class BrowserTool:
    """Web browsing tool with SSRF-aware URL validation."""

    _MAX_REDIRECTS = 5

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._headers = {"User-Agent": "OMEGA-X-Browser/1.0 (+https://omega-x.local)"}

    async def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http and https URLs are allowed")
        if parsed.username or parsed.password:
            raise ValueError("credential-bearing URLs are not allowed")

        host = parsed.hostname
        if not host:
            raise ValueError("URL host is required")

        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise ValueError("invalid URL port") from exc

        try:
            infos = await asyncio.to_thread(
                socket.getaddrinfo,
                host,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise ValueError("URL host could not be resolved") from exc

        addresses = {info[4][0] for info in infos}
        if not addresses:
            raise ValueError("URL host could not be resolved")

        for address in addresses:
            if not ipaddress.ip_address(address).is_global:
                raise ValueError("private, local, or non-public network targets are blocked")

    async def _get_public(self, url: str, **kwargs) -> tuple[httpx.Response, str]:
        """Fetch public content with redirect revalidation and a hard decompressed-size ceiling."""
        current = url
        for _ in range(self._MAX_REDIRECTS + 1):
            await self._validate_url(current)
            async with self._client.stream(
                "GET",
                current,
                follow_redirects=False,
                **kwargs,
            ) as streamed:
                if streamed.is_redirect:
                    location = streamed.headers.get("location")
                    if not location:
                        raise ValueError("redirect response did not include a location header")
                    current = urljoin(current, location)
                    continue

                content_length = streamed.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > 2_000_000:
                            raise ValueError("browser response exceeds the 2 MB limit")
                    except ValueError as exc:
                        if "2 MB limit" in str(exc):
                            raise
                        raise ValueError("invalid Content-Length from target page") from exc

                chunks: list[bytes] = []
                size = 0
                async for chunk in streamed.aiter_bytes():
                    size += len(chunk)
                    if size > 2_000_000:
                        raise ValueError("browser response exceeds the 2 MB limit")
                    chunks.append(chunk)

                headers = dict(streamed.headers)
                headers.pop("content-length", None)
                headers.pop("content-encoding", None)
                response = httpx.Response(
                    status_code=streamed.status_code,
                    headers=headers,
                    content=b"".join(chunks),
                    request=streamed.request,
                    extensions=dict(streamed.extensions),
                )
                return response, current

        raise ValueError("too many redirects")

    async def fetch(self, url: str) -> dict:
        """Fetch a public web page and return structured content."""
        try:
            response, final_url = await self._get_public(
                url,
                timeout=30,
                headers=self._headers,
            )
            content_type = response.headers.get("content-type", "")

            if "text/html" in content_type:
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()

                text = soup.get_text(separator="\n", strip=True)
                title = soup.title.string if soup.title else final_url
                links = [
                    {"text": a.get_text(strip=True)[:100], "url": a.get("href", "")}
                    for a in soup.find_all("a", href=True)[:30]
                ]
                return {
                    "url": final_url,
                    "title": title,
                    "text": text[:8000],
                    "links": links,
                    "html": response.text[:100000],
                    "status": response.status_code,
                }

            return {
                "url": final_url,
                "title": final_url,
                "text": response.text[:8000],
                "links": [],
                "html": "",
                "status": response.status_code,
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "url": url,
                "title": url,
                "text": "",
                "links": [],
                "html": "",
                "status": 0,
                "error": str(exc),
            }

    async def search(self, query: str) -> dict:
        """Search the web using DuckDuckGo HTML."""
        try:
            response = await self._client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                follow_redirects=True,
                timeout=30,
                headers=self._headers,
            )
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            for result in soup.select(".result")[:10]:
                title_elem = result.select_one(".result__title a")
                snippet_elem = result.select_one(".result__snippet")
                if title_elem:
                    results.append(
                        {
                            "title": title_elem.get_text(strip=True),
                            "url": title_elem.get("href", ""),
                            "snippet": (
                                snippet_elem.get_text(strip=True) if snippet_elem else ""
                            ),
                        }
                    )
            return {"query": query, "results": results}
        except httpx.HTTPError as exc:
            return {"query": query, "results": [], "error": str(exc)}

    async def proxy(self, url: str) -> tuple[str, str]:
        """Fetch a public URL for isolated iframe display."""
        response, final_url = await self._get_public(
            url,
            timeout=30,
            headers=self._headers,
        )
        content_type = response.headers.get("content-type", "text/html")
        html = response.text

        if "text/html" in content_type and "<head>" in html:
            safe_base = final_url.replace('"', "%22")
            html = html.replace(
                "<head>",
                f'<head><base href="{safe_base}">',
                1,
            )

        return html, content_type
