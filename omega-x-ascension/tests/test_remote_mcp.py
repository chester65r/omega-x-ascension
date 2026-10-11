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


@pytest.mark.asyncio
async def test_remote_mcp_rejects_non_https_url():
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError, match="HTTPS"):
            RemoteMCPClient("http://example.test/mcp", None, 5, http)

@pytest.mark.asyncio
async def test_remote_mcp_blocks_advertised_mutating_tools_before_call():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "test-server", "version": "1"},
                },
            })
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "result": {"tools": [{
                    "name": "delete-file",
                    "description": "Delete a file from storage",
                    "inputSchema": {"type": "object", "properties": {}},
                }]},
            })
        if method == "tools/call":
            pytest.fail("A mutating remote tool must never be called")
        return httpx.Response(400)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RemoteMCPClient("https://example.test/mcp", None, 5, http)
        with pytest.raises(RemoteMCPError, match="read-only safety policy"):
            await client.call_tool("delete-file", {})
    assert "tools/call" not in [call.get("method") for call in calls]


@pytest.mark.asyncio
async def test_remote_mcp_blocks_tools_marked_destructive():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "test-server", "version": "1"},
                },
            })
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "result": {"tools": [{
                    "name": "fetch-record",
                    "description": "Fetch a record",
                    "annotations": {"readOnlyHint": True, "destructiveHint": True},
                    "inputSchema": {"type": "object", "properties": {}},
                }]},
            })
        if method == "tools/call":
            pytest.fail("A tool marked destructive must never be called")
        return httpx.Response(400)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RemoteMCPClient("https://example.test/mcp", None, 5, http)
        with pytest.raises(RemoteMCPError, match="read-only safety policy"):
            await client.call_tool("fetch-record", {})
    assert "tools/call" not in [call.get("method") for call in calls]
