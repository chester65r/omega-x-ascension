from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from pydantic import BaseModel, Field

from omega.auth import Principal, current_principal
from omega.config import get_settings
from omega.rate_limit import enforce_rate_limit

router = APIRouter(tags=["external-mcp"])
MAX_RESPONSE_BYTES = 2_000_000

# MCP annotations and names are untrusted hints. Require a read-style tool name,
# and reject explicit or described side effects before any remote call.
_READ_ONLY_TOOL_PREFIXES = (
    "get", "read", "list", "fetch", "search", "find", "lookup", "query",
    "inspect", "view", "check", "status", "describe", "review", "analyze", "summarize",
)
_MUTATING_TOOL_TERMS = re.compile(
    r"\b(?:create|update|delete|remove|modify|write|edit|patch|post|put|upload|download|"
    r"deploy|execute|run|shell|command|send|email|message|notify|publish|purchase|pay|"
    r"transfer|grant|revoke|invite|approve|cancel|reset|restart|change|alter|destroy|"
    r"erase|drop|insert|replace|configure|configuration|set)\b",
    re.IGNORECASE,
)


def is_read_only_tool(tool: dict[str, Any]) -> bool:
    """Fail-closed, metadata-based guard; this is not a substitute for server trust."""
    name = tool.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", name):
        return False
    annotations = tool.get("annotations")
    if isinstance(annotations, dict):
        if annotations.get("readOnlyHint") is False or annotations.get("destructiveHint") is True:
            return False
    normalized_name = re.sub(r"[^a-z0-9]", "", name.lower())
    if not any(normalized_name.startswith(prefix) for prefix in _READ_ONLY_TOOL_PREFIXES):
        return False
    description = tool.get("description", "")
    if not isinstance(description, str):
        description = str(description)
    return _MUTATING_TOOL_TERMS.search(f"{name} {description}") is None


class RemoteMCPError(RuntimeError):
    """Raised when the configured remote MCP endpoint cannot be used safely."""


class RemoteToolCall(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")
    arguments: dict[str, Any] = Field(default_factory=dict)


class RemoteMCPClient:
    """Small Streamable HTTP MCP client; it never executes tools locally."""

    def __init__(
        self,
        url: str | None,
        token: str | None,
        timeout_seconds: float,
        http: httpx.AsyncClient,
    ) -> None:
        self.url = self._validate_url(url) if url else None
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.http = http
        self._session_id: str | None = None
        self._initialized = False
        self._next_id = 1
        self._protocol_version = "2024-11-05"

    @staticmethod
    def _validate_url(url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("Remote MCP URL must be an HTTPS URL without embedded credentials")
        if parts.fragment:
            raise ValueError("Remote MCP URL must not contain a fragment")
        return url.rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def new_session(self) -> "RemoteMCPClient":
        """Create an isolated MCP protocol session while reusing the HTTP pool."""
        return RemoteMCPClient(self.url, self.token, self.timeout_seconds, self.http)

    def _headers(self, *, initialize_request: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        # The initial initialize request negotiates a protocol version in its JSON-RPC
        # params. The MCP-Protocol-Version header belongs on subsequent requests.
        if not initialize_request:
            headers["MCP-Protocol-Version"] = self._protocol_version
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    async def _post(self, payload: dict[str, Any], *, notification: bool = False, initialize_request: bool = False) -> dict[str, Any] | None:
        if not self.url:
            raise RemoteMCPError("Remote MCP integration is disabled; configure OMEGA_REMOTE_MCP_URL")
        try:
            response = await self.http.post(
                self.url,
                json=payload,
                headers=self._headers(initialize_request=initialize_request),
                timeout=httpx.Timeout(self.timeout_seconds),
            )
        except httpx.HTTPError as exc:
            raise RemoteMCPError(f"Remote MCP transport failed: {type(exc).__name__}") from exc

        if response.status_code == 401 or response.status_code == 403:
            raise RemoteMCPError("Remote MCP authentication or authorization failed")
        if response.status_code == 404 and self._session_id:
            self._session_id = None
            self._initialized = False
            raise RemoteMCPError("Remote MCP session expired; retry the request")
        if response.status_code not in (200, 202):
            raise RemoteMCPError(f"Remote MCP returned HTTP {response.status_code}")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise RemoteMCPError("Remote MCP response exceeded the 2 MB safety limit")
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self._session_id = session_id
        if notification or response.status_code == 202 or not response.content:
            return None

        content_type = response.headers.get("content-type", "").lower()
        try:
            if "text/event-stream" in content_type:
                messages = []
                for line in response.text.splitlines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data and data != "[DONE]":
                            messages.append(json.loads(data))
                if not messages:
                    raise RemoteMCPError("Remote MCP returned an empty event stream")
                return messages[-1]
            result = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise RemoteMCPError("Remote MCP returned invalid JSON or SSE data") from exc
        if not isinstance(result, dict):
            raise RemoteMCPError("Remote MCP response must be a JSON object")
        return result

    async def _rpc(self, method: str, params: dict[str, Any] | None = None, *, initialize_request: bool = False) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        response = await self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
            initialize_request=initialize_request,
        )
        if response is None:
            raise RemoteMCPError("Remote MCP did not return a JSON-RPC response")
        if response.get("id") != request_id:
            raise RemoteMCPError("Remote MCP response ID did not match request")
        if "error" in response:
            error = response["error"]
            message = error.get("message", "unknown JSON-RPC error") if isinstance(error, dict) else "unknown JSON-RPC error"
            raise RemoteMCPError(f"Remote MCP JSON-RPC error: {message}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise RemoteMCPError("Remote MCP result is missing or malformed")
        return result

    async def initialize(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "status": "disabled"}
        if self._initialized:
            return {"enabled": True, "status": "connected"}
        result = await self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "omega-x-ascension", "version": "0.8.3"},
            },
            initialize_request=True,
        )
        server_info = result.get("serverInfo", {})
        protocol = result.get("protocolVersion")
        if not isinstance(server_info, dict) or not isinstance(protocol, str) or not protocol.strip():
            raise RemoteMCPError("Remote MCP initialize response is missing server metadata")
        self._protocol_version = protocol
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, notification=True)
        self._initialized = True
        return {
            "enabled": True,
            "status": "connected",
            "protocolVersion": protocol,
            "serverInfo": server_info,
        }

    async def list_tools(self) -> list[dict[str, Any]]:
        await self.initialize()
        result = await self._rpc("tools/list")
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise RemoteMCPError("Remote MCP tools/list response is malformed")
        safe_tools = []
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                continue
            annotations = tool.get("annotations")
            safe_annotations = {}
            if isinstance(annotations, dict):
                for key in ("readOnlyHint", "destructiveHint"):
                    if isinstance(annotations.get(key), bool):
                        safe_annotations[key] = annotations[key]
            safe_tools.append({
                "name": tool["name"][:128],
                "description": str(tool.get("description", ""))[:2000],
                "inputSchema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                "annotations": safe_annotations,
            })
        return safe_tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", name):
            raise RemoteMCPError("Invalid tool name")
        try:
            encoded_arguments = json.dumps(arguments, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise RemoteMCPError("Tool arguments must be JSON-serializable") from exc
        if len(encoded_arguments) > 65_536:
            raise RemoteMCPError("Tool arguments exceeded the 64 KB safety limit")
        tools = await self.list_tools()
        selected_tool = next((tool for tool in tools if tool["name"] == name), None)
        if selected_tool is None:
            raise RemoteMCPError("Requested tool is not advertised by the configured MCP server")
        if not is_read_only_tool(selected_tool):
            raise RemoteMCPError("Remote MCP call blocked: tool does not pass the read-only safety policy")
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result.get("content", []), list):
            raise RemoteMCPError("Remote MCP tool result is malformed")
        return result


def _client(request: Request) -> RemoteMCPClient:
    client = getattr(request.app.state, "remote_mcp", None)
    if client is None:
        raise HTTPException(503, "Remote MCP integration is unavailable")
    return client.new_session()


@router.get("/status")
async def remote_mcp_status(
    principal: Principal = Security(current_principal, scopes=["runs:read"]),
    client: RemoteMCPClient = Depends(_client),
):
    if not client.enabled:
        return {"enabled": False, "status": "disabled"}
    try:
        return await client.initialize()
    except RemoteMCPError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/tools")
async def remote_mcp_tools(
    principal: Principal = Security(current_principal, scopes=["runs:read"]),
    client: RemoteMCPClient = Depends(_client),
):
    try:
        tools = await client.list_tools()
        return {"enabled": client.enabled, "tools": tools}
    except RemoteMCPError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/tools/call")
async def remote_mcp_call(
    request: Request,
    body: RemoteToolCall,
    principal: Principal = Security(current_principal, scopes=["runs:write", "runs:approve"]),
    client: RemoteMCPClient = Depends(_client),
):
    svc = getattr(request.app.state, "services", None)
    await enforce_rate_limit(
        getattr(svc, "redis", None),
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="remote:mcp",
        limit=20,
    )
    try:
        return await client.call_tool(body.name, body.arguments)
    except RemoteMCPError as exc:
        raise HTTPException(502, str(exc)) from exc
