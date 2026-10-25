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
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"city": {"type": "string"}},
                                },
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
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "test-server", "version": "1"},
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
                                "name": "fetch-record",
                                "description": "Fetch and delete a record",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ]
                    },
                },
            )
        if method == "tools/call":
            pytest.fail("A mutating remote tool must never be called")
        return httpx.Response(400)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RemoteMCPClient("https://example.test/mcp", None, 5, http)
        with pytest.raises(RemoteMCPError, match="read-only safety policy"):
            await client.call_tool("fetch-record", {})
    assert "tools/call" not in [call.get("method") for call in calls]


@pytest.mark.asyncio
async def test_remote_mcp_blocks_tools_marked_destructive():
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
                        "serverInfo": {"name": "test-server", "version": "1"},
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
                                "name": "fetch-record",
                                "description": "Fetch a record",
                                "annotations": {"readOnlyHint": True, "destructiveHint": True},
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ]
                    },
                },
            )
        if method == "tools/call":
            pytest.fail("A tool marked destructive must never be called")
        return httpx.Response(400)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RemoteMCPClient("https://example.test/mcp", None, 5, http)
        with pytest.raises(RemoteMCPError, match="read-only safety policy"):
            await client.call_tool("fetch-record", {})
    assert "tools/call" not in [call.get("method") for call in calls]


@pytest.mark.asyncio
async def test_remote_mcp_streamable_http_negotiates_version_and_preserves_session():
    calls: list[dict[str, str | None]] = []
    session = "test-mcp-session"

    def sse(payload: dict) -> str:
        return "event: message" + chr(10) + "data: " + json.dumps(payload) + chr(10) * 2

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload.get("method")
        calls.append(
            {
                "method": method,
                "protocol": request.headers.get("MCP-Protocol-Version"),
                "session": request.headers.get("Mcp-Session-Id"),
            }
        )
        if method == "initialize":
            # MCP version is negotiated in initialize.params, not as an HTTP header.
            assert request.headers.get("MCP-Protocol-Version") is None
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream", "Mcp-Session-Id": session},
                text=sse(
                    {
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "streamable-test-server", "version": "1.0"},
                        },
                    }
                ),
            )
        if method == "notifications/initialized":
            assert request.headers.get("MCP-Protocol-Version") == "2024-11-05"
            assert request.headers.get("Mcp-Session-Id") == session
            return httpx.Response(202)
        if method == "tools/list":
            assert request.headers.get("MCP-Protocol-Version") == "2024-11-05"
            assert request.headers.get("Mcp-Session-Id") == session
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream", "Mcp-Session-Id": session},
                text=sse(
                    {
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {
                            "tools": [
                                {
                                    "name": "fetch-weather",
                                    "description": "Get current weather for a city",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {"city": {"type": "string"}},
                                    },
                                }
                            ],
                        },
                    }
                ),
            )
        return httpx.Response(400, text="unexpected method")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RemoteMCPClient("https://example.test/mcp", None, 5, http)
        status = await client.initialize()
        tools = await client.list_tools()

    assert status["status"] == "connected"
    assert status["protocolVersion"] == "2024-11-05"
    assert status["serverInfo"]["name"] == "streamable-test-server"
    assert [item["name"] for item in tools] == ["fetch-weather"]
    assert [call["method"] for call in calls] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]
    assert calls[0]["protocol"] is None
    assert calls[0]["session"] is None
    assert calls[1]["protocol"] == "2024-11-05"
    assert calls[1]["session"] == session
    assert calls[2]["protocol"] == "2024-11-05"
    assert calls[2]["session"] == session
