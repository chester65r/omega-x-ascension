from __future__ import annotations

import json

import httpx
import pytest

from omega.remote_mcp import RemoteMCPClient, RemoteMCPError


@pytest.mark.asyncio
async def test_remote_mcp_initialize_list_and_call():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "example-mcp", "version": "1.0.0"},
                    },
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "fetch-weather",
                                "description": "Get weather for a city",
                                "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}},
                            }
                        ]
                    },
                },
            )
        if method == "tools/call":
            assert payload["params"]["name"] == "fetch-weather"
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"content": [{"type": "text", "text": "Sunny"}], "isError": False},
                },
            )
        return httpx.Response(400)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RemoteMCPClient("https://example.test/mcp", None, 5, http)
        status = await client.initialize()
        assert status["status"] == "connected"
        tools = await client.list_tools()
        assert [tool["name"] for tool in tools] == ["fetch-weather"]
        result = await client.call_tool("fetch-weather", {"city": "Jeddah"})
        assert result["content"][0]["text"] == "Sunny"
        assert [call["method"] for call in calls] == [
            "initialize",
            "notifications/initialized",
            "tools/list",
            "tools/list",
            "tools/call",
        ]


def test_remote_mcp_rejects_non_https_url():
    async def unused() -> None:
        pass

    with pytest.raises(ValueError, match="HTTPS"):
        # The HTTP client is not used when construction rejects the URL.
        RemoteMCPClient("http://example.test/mcp", None, 5, httpx.AsyncClient())
