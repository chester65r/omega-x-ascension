from __future__ import annotations

import httpx
from bs4 import BeautifulSoup


class BrowserTool:
    """Web browsing tool for AI agents — fetch pages, search the web, proxy for display."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._headers = {"User-Agent": "OMEGA-X-Browser/1.0 (+https://omega-x.local)"}

    async def fetch(self, url: str) -> dict:
        """Fetch a web page and return structured content."""
        try:
            response = await self._client.get(
                url, follow_redirects=True, timeout=30, headers=self._headers
            )
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                title = soup.title.string if soup.title else url
                links = [
                    {"text": a.get_text(strip=True)[:100], "url": a.get("href", "")}
                    for a in soup.find_all("a", href=True)[:30]
                ]
                return {
                    "url": str(response.url),
                    "title": title,
                    "text": text[:8000],
                    "links": links,
                    "html": response.text[:100000],
                    "status": response.status_code,
                }
            return {
                "url": str(response.url),
                "title": url,
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
        """Search the web using DuckDuckGo HTML endpoint."""
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
                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "url": title_elem.get("href", ""),
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                    })
            return {"query": query, "results": results}
        except httpx.HTTPError as exc:
            return {"query": query, "results": [], "error": str(exc)}

    async def proxy(self, url: str) -> tuple[str, str]:
        """Fetch a URL and return (html, content_type) for iframe proxy display."""
        response = await self._client.get(
            url, follow_redirects=True, timeout=30, headers=self._headers
        )
        content_type = response.headers.get("content-type", "text/html")
        html = response.text
        # Inject <base> so relative URLs resolve against the original page
        if "text/html" in content_type and "<head>" in html:
            html = html.replace("<head>", f'<head><base href="{response.url}">', 1)
        return html, content_type
