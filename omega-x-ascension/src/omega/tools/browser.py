from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import cast
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


class BrowserTool:
    """Web browsing tool with SSRF-aware URL validation."""

    _MAX_REDIRECTS = 5

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._headers = {"User-Agent": "OMEGA-X-Browser/1.0 (+https://omega-x.local)"}

    async def _validate_url(self, url: str) -> str:
        """Resolve once, reject non-public answers, and return an IP to pin the request to."""
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

        addresses = {info[4][0].split("%", 1)[0] for info in infos}
        if not addresses:
            raise ValueError("URL host could not be resolved")

        for address in addresses:
            try:
                is_public = ipaddress.ip_address(address).is_global
            except ValueError as exc:
                raise ValueError("URL host resolved to an invalid IP address") from exc
            if not is_public:
                raise ValueError("private, local, or non-public network targets are blocked")

        # The actual HTTP connection uses this literal IP, so a second DNS lookup
        # cannot rebind the hostname to a private or local address.
        return sorted(addresses)[0]

    async def _get_public(self, url: str, **kwargs) -> tuple[httpx.Response, str]:
        """Fetch public content with redirect revalidation and a hard decompressed-size ceiling."""
        current = url
        for _ in range(self._MAX_REDIRECTS + 1):
            pinned_ip = await self._validate_url(current)
            original_url = httpx.URL(current)
            pinned_url = original_url.copy_with(host=pinned_ip)
            request_headers = dict(kwargs.get("headers") or {})
            # Preserve the original virtual host while connecting to the validated IP.
            request_headers["Host"] = original_url.netloc.decode("ascii")
            # Do not pool pinned-IP connections across different original hostnames:
            # the pool's origin key is the IP, while TLS identity is the original host.
            # Closing each response prevents a later host from reusing a connection
            # whose certificate was verified against a different SNI name.
            request_headers["Connection"] = "close"
            extensions = {}
            if original_url.scheme == "https":
                try:
                    ipaddress.ip_address(original_url.host)
                    original_host_is_ip = True
                except ValueError:
                    original_host_is_ip = False
                if not original_host_is_ip:
                    # Keep TLS SNI and certificate hostname verification bound to
                    # the original hostname rather than the pinned connection IP.
                    extensions["sni_hostname"] = original_url.raw_host

            request_kwargs = {key: value for key, value in kwargs.items() if key != "headers"}
            request = self._client.build_request(
                "GET",
                pinned_url,
                headers=request_headers,
                extensions=extensions,
                **request_kwargs,
            )
            streamed = await self._client.send(request, stream=True, follow_redirects=False)
            try:
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
            finally:
                await streamed.aclose()

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
        """Search the public web and normalize DuckDuckGo redirect links."""
        query = query.strip()
        if not query or len(query) > 300:
            return {"query": query[:300], "results": [], "error": "query must be 1–300 characters"}

        try:
            search_url = httpx.URL("https://html.duckduckgo.com/html/").copy_merge_params(
                {"q": query}
            )
            response, _ = await self._get_public(
                str(search_url),
                timeout=20,
                headers=self._headers,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            for result in soup.select(".result")[:10]:
                title_elem = result.select_one(".result__title a")
                snippet_elem = result.select_one(".result__snippet")
                if not title_elem:
                    continue

                raw_url = cast(str, title_elem.get("href") or "")
                candidate = urljoin("https://duckduckgo.com/", raw_url)
                parsed = urlparse(candidate)
                if (
                    parsed.hostname
                    and parsed.hostname.lower().endswith("duckduckgo.com")
                    and parsed.path.startswith("/l/")
                ):
                    candidate = cast(str, parse_qs(parsed.query).get("uddg", [""])[0])
                    parsed = urlparse(candidate)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                ):
                    continue

                results.append(
                    {
                        "title": title_elem.get_text(" ", strip=True)[:240],
                        "url": candidate,
                        "snippet": snippet_elem.get_text(" ", strip=True)[:600]
                        if snippet_elem
                        else "",
                    }
                )
            return {"query": query, "results": results}
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "query": query,
                "results": [],
                "error": f"Search request failed: {type(exc).__name__}",
            }

    async def proxy(self, url: str) -> tuple[str, str]:
        """Fetch a page and route navigation through the SSRF-checked proxy."""
        response, final_url = await self._get_public(
            url,
            timeout=30,
            headers=self._headers,
        )
        content_type = response.headers.get("content-type", "text/html").lower()
        if not (
            "text/html" in content_type
            or "text/plain" in content_type
            or "application/json" in content_type
        ):
            raise ValueError("this browser preview supports HTML, text, and JSON pages only")

        body = response.text
        if "text/html" not in content_type:
            from html import escape

            body = (
                "<!doctype html><html><head><meta charset='utf-8'></head>"
                "<body><pre style='white-space:pre-wrap;overflow-wrap:anywhere'>"
                + escape(body[:100_000])
                + "</pre></body></html>"
            )

        import html

        safe_base = html.escape(final_url, quote=True)
        navigation_bridge = r"""<script data-omega-browser-bridge>
(() => {
  const send = (url) => {
    try {
      const target = new URL(url, document.baseURI);
      if (target.protocol !== 'http:' && target.protocol !== 'https:') return;
      if (target.username || target.password) return;
      window.parent.postMessage({
        source: 'omega-browser',
        action: 'navigate',
        url: target.href
      }, '*');
    } catch (_) {}
  };

  document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = event.target && event.target.closest
      ? event.target.closest('a[href]') : null;
    if (!anchor || anchor.hasAttribute('download')) return;
    const target = (anchor.getAttribute('target') || '').toLowerCase();
    if (target === '_blank' || target === '_parent' || target === '_top') {
      event.preventDefault();
      send(anchor.href);
      return;
    }
    if (anchor.href) {
      event.preventDefault();
      send(anchor.href);
    }
  }, true);

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const method = (form.method || 'get').toLowerCase();
    event.preventDefault();
    if (method !== 'get') {
      window.parent.postMessage({
        source: 'omega-browser',
        action: 'notice',
        message: 'This preview supports GET search forms only.'
      }, '*');
      return;
    }
    const target = new URL(form.action || location.href, document.baseURI);
    const data = new FormData(form);
    for (const [key, value] of data.entries()) {
      if (typeof value === 'string') target.searchParams.append(key, value);
    }
    send(target.href);
  }, true);
})();
</script>"""

        import re

        injection = f'<base href="{safe_base}">{navigation_bridge}'
        head_pattern = re.compile(r"(<head\b[^>]*>)", re.IGNORECASE)
        if head_pattern.search(body):
            body = head_pattern.sub(lambda match: match.group(1) + injection, body, count=1)
        else:
            body = (
                "<!doctype html><html><head>"
                + injection
                + "</head><body>"
                + body
                + "</body></html>"
            )

        return body, "text/html; charset=utf-8"
