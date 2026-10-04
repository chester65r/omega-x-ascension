from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


class BrowserTool:
    """Web browsing tool with scheme, DNS and redirect validation."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._headers = {"User-Agent": "OMEGA-X-Browser/1.1"}

    @staticmethod
    def _validate_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("only http and https URLs are allowed")
        if parsed.username or parsed.password:
            raise ValueError("URL credentials are not allowed")
        host = parsed.hostname
        for family, _, _, _, sockaddr in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
            address = ipaddress.ip_address(sockaddr[0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified:
                raise ValueError("destination resolves to a non-public address")
        return url

    async def _get(self, url: str) -> httpx.Response:
        current = self._validate_url(url)
        for _ in range(5):
            response = await self._client.get(current, follow_redirects=False, timeout=30, headers=self._headers)
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("redirect without location")
                current = self._validate_url(urljoin(current, location))
                continue
            return response
        raise ValueError("too many redirects")

    async def fetch(self, url: str) -> dict:
        try:
            response = await self._get(url)
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                title = soup.title.string if soup.title else str(response.url)
                links = [{"text": a.get_text(strip=True)[:100], "url": a.get("href", "")} for a in soup.find_all("a", href=True)[:30]]
                return {"url": str(response.url), "title": title, "text": text[:8000], "links": links, "html": response.text[:100000], "status": response.status_code}
            return {"url": str(response.url), "title": str(response.url), "text": response.text[:8000], "links": [], "html": "", "status": response.status_code}
        except (httpx.HTTPError, ValueError, socket.gaierror) as exc:
            return {"url": url, "title": url, "text": "", "links": [], "html": "", "status": 0, "error": str(exc)}

    async def search(self, query: str) -> dict:
        try:
            response = await self._client.get("https://html.duckduckgo.com/html/", params={"q": query}, follow_redirects=False, timeout=30, headers=self._headers)
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            for result in soup.select(".result")[:10]:
                title_elem = result.select_one(".result__title a")
                snippet_elem = result.select_one(".result__snippet")
                if title_elem:
                    results.append({"title": title_elem.get_text(strip=True), "url": title_elem.get("href", ""), "snippet": snippet_elem.get_text(strip=True) if snippet_elem else ""})
            return {"query": query, "results": results}
        except httpx.HTTPError as exc:
            return {"query": query, "results": [], "error": str(exc)}

    async def proxy(self, url: str) -> tuple[str, str]:
        response = await self._get(url)
        content_type = response.headers.get("content-type", "text/html")
        html = response.text
        if "text/html" in content_type and "<head" in html.lower():
            html = html.replace("<head>", f'<head><base href="{response.url}">', 1)
        return html, content_type
