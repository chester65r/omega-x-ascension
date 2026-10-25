from __future__ import annotations

import json
import logging
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Request, Security
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from omega import __version__
from omega.auth import Principal, current_principal, require_requested_action_scopes
from omega.config import Capability
from omega.domain import ApprovalPolicy, RunStatus, WorkflowRun
from omega.model_router import NoEligibleModel
from omega.rate_limit import enforce_rate_limit

router = APIRouter(tags=["mcp"])
logger = logging.getLogger("omega.mcp")

SERVER_NAME = "omega-x-ascension-mcp"
SERVER_VERSION = __version__
PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_CAPABILITIES = frozenset(
    {"reasoning", "coding", "mathematics", "planning", "analysis", "summarization", "research"}
)


def _tool_result(req_id: Any, payload: Any) -> JSONResponse:
    return _jsonrpc_success(
        req_id,
        {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "isError": False,
        },
    )


TOOLS = [
    {
        "name": "omega_create_run",
        "description": "Create a tenant-scoped AI workflow. Requires runs:write; sensitive actions wait for explicit approval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "minLength": 3, "maxLength": 20000},
                "task_type": {"type": "string", "enum": sorted(SUPPORTED_CAPABILITIES)},
                "requested_actions": {
                    "type": "array",
                    "maxItems": 20,
                    "items": {"type": "string", "maxLength": 100},
                },
            },
            "required": ["goal", "task_type"],
        },
    },
    {
        "name": "omega_get_run",
        "description": "Get one workflow run belonging to the authenticated tenant. Requires runs:read.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string", "format": "uuid"}},
            "required": ["run_id"],
        },
    },
    {
        "name": "omega_list_runs",
        "description": "List recent workflow runs belonging to the authenticated tenant. Requires runs:read.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
        },
    },
    {
        "name": "omega_approve_run",
        "description": "Approve and enqueue a valid pending approval for this tenant. Requires runs:approve.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string", "format": "uuid"}},
            "required": ["run_id"],
        },
    },
    {
        "name": "omega_search_web",
        "description": "Run a bounded public web search using Omega's SSRF-aware browser tool. Requires runs:read.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 300}},
            "required": ["query"],
        },
    },
    {
        "name": "omega_get_version",
        "description": "Get platform version, API version, and enabled features. Requires runs:read.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: Any | None = None
    method: str = Field(min_length=1, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict)


def _jsonrpc_success(req_id: Any, result: Any) -> JSONResponse:
    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": result})


def _jsonrpc_error(req_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}},
    )


def _run_payload(run: WorkflowRun) -> dict[str, object]:
    return {
        "id": str(run.id),
        "goal": run.goal,
        "task_type": run.task_type,
        "status": run.status.value,
        "output": run.output,
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


@router.get("")
@router.get("/")
async def mcp_info():
    # Public discovery reveals only protocol metadata. Every JSON-RPC request below
    # requires a verified Bearer JWT and tool-specific scopes.
    return {
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "protocolVersion": PROTOCOL_VERSION,
        "tools_count": len(TOOLS),
        "tools": [tool["name"] for tool in TOOLS],
        "status": "ready",
        "authentication": "Bearer JWT",
    }


@router.post("")
@router.post("/")
async def handle_mcp(
    request: Request,
    body: JsonRpcRequest,
    principal: Principal = Security(current_principal),
):
    method = body.method
    req_id = body.id
    params = body.params or {}
    tool_name = params.get("name") if method == "tools/call" else None

    # Scope gates are evaluated before any work. A request cannot choose a tenant
    # or actor in MCP arguments; both come solely from the verified bearer token.
    if tool_name == "omega_create_run":
        principal.require({"runs:write"})
        # MCP run creation must enforce the same computer-capability scopes as REST.
        arguments = params.get("arguments")
        if isinstance(arguments, dict):
            actions = arguments.get("requested_actions", [])
            if isinstance(actions, list):
                require_requested_action_scopes(actions, principal)
    elif tool_name == "omega_approve_run":
        principal.require({"runs:approve"})
    else:
        principal.require({"runs:read"})

    svc = getattr(request.app.state, "services", None)

    if method == "initialize":
        return _jsonrpc_success(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "ping":
        return _jsonrpc_success(req_id, {})
    if method == "tools/list":
        return _jsonrpc_success(req_id, {"tools": TOOLS})
    if method != "tools/call":
        return _jsonrpc_error(req_id, -32601, "Unknown method")

    action = (
        "runs:create"
        if tool_name == "omega_create_run"
        else "browser:search"
        if tool_name == "omega_search_web"
        else "mcp:tools"
    )
    limit = 10 if action == "runs:create" else 30 if action == "browser:search" else 60
    try:
        await enforce_rate_limit(
            getattr(svc, "redis", None),
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            action=action,
            limit=limit,
        )
    except Exception as exc:
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            return _jsonrpc_error(req_id, -32029 if exc.status_code == 429 else -32000, exc.detail)
        raise

    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return _jsonrpc_error(req_id, -32602, "Tool arguments must be an object")
    try:
        if len(json.dumps(arguments, ensure_ascii=False).encode("utf-8")) > 65_536:
            return _jsonrpc_error(req_id, -32602, "Tool arguments exceed the 64 KB limit")
    except (TypeError, ValueError):
        return _jsonrpc_error(req_id, -32602, "Tool arguments must be valid JSON data")

    if not isinstance(tool_name, str):
        return _jsonrpc_error(req_id, -32602, "Missing tool name")

    try:
        if tool_name == "omega_get_version":
            return _tool_result(
                req_id,
                {
                    "version": SERVER_VERSION,
                    "api_version": "v1",
                    "protocol": PROTOCOL_VERSION,
                    "features": ["langgraph_feedback_loop", "mcp_server", "hitl_approval"],
                },
            )

        if tool_name == "omega_search_web":
            if svc is None:
                return _jsonrpc_error(req_id, -32000, "Service layer is not initialized")
            query = arguments.get("query")
            if not isinstance(query, str) or not query.strip() or len(query) > 300:
                return _jsonrpc_error(req_id, -32602, "query must contain 1 to 300 characters")
            result = await svc.browser.search(query.strip())
            return _tool_result(req_id, result)

        if tool_name == "omega_create_run":
            if svc is None:
                return _jsonrpc_error(req_id, -32000, "Service layer is not initialized")
            goal = arguments.get("goal")
            task_type = arguments.get("task_type")
            actions = arguments.get("requested_actions", [])
            if not isinstance(goal, str) or not 3 <= len(goal.strip()) <= 20_000:
                return _jsonrpc_error(req_id, -32602, "goal must contain 3 to 20000 characters")
            if not isinstance(task_type, str) or task_type not in SUPPORTED_CAPABILITIES:
                return _jsonrpc_error(req_id, -32602, "task_type is not supported")
            if (
                not isinstance(actions, list)
                or len(actions) > 20
                or any(not isinstance(action, str) or len(action) > 100 for action in actions)
            ):
                return _jsonrpc_error(
                    req_id, -32602, "requested_actions must contain at most 20 short strings"
                )

            try:
                await svc.router.select(task_type)
            except NoEligibleModel:
                return _jsonrpc_error(
                    req_id, -32000, "No healthy model is configured for this capability"
                )

            run = WorkflowRun(
                goal=goal.strip(),
                task_type=cast(Capability, task_type),
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                requested_actions=actions,
            )
            if ApprovalPolicy().requires_approval(set(actions)):
                run.status = RunStatus.WAITING_APPROVAL
                run.approval_digest = run.digest()

            await svc.repo.create_run(run, principal.user_id, run.status == RunStatus.PENDING)
            return _tool_result(
                req_id,
                {
                    "run_id": str(run.id),
                    "status": run.status.value,
                    "goal": run.goal,
                    "task_type": run.task_type,
                    "approval_required": run.status == RunStatus.WAITING_APPROVAL,
                },
            )

        if tool_name == "omega_get_run":
            if svc is None:
                return _jsonrpc_error(req_id, -32000, "Service layer is not initialized")
            raw_id = arguments.get("run_id")
            try:
                run_id = UUID(str(raw_id))
            except (ValueError, TypeError, AttributeError):
                return _jsonrpc_error(req_id, -32602, "run_id must be a valid UUID")
            run = await svc.repo.get(principal.tenant_id, run_id)
            if run is None:
                return _jsonrpc_error(req_id, -32004, "Run not found")
            return _tool_result(req_id, _run_payload(run))

        if tool_name == "omega_list_runs":
            if svc is None:
                return _jsonrpc_error(req_id, -32000, "Service layer is not initialized")
            limit = arguments.get("limit", 20)
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
                return _jsonrpc_error(req_id, -32602, "limit must be an integer from 1 to 100")
            runs = await svc.repo.list_runs(principal.tenant_id, limit)
            return _tool_result(req_id, {"runs": [_run_payload(run) for run in runs]})

        if tool_name == "omega_approve_run":
            if svc is None:
                return _jsonrpc_error(req_id, -32000, "Service layer is not initialized")
            raw_id = arguments.get("run_id")
            try:
                run_id = UUID(str(raw_id))
            except (ValueError, TypeError, AttributeError):
                return _jsonrpc_error(req_id, -32602, "run_id must be a valid UUID")
            run = await svc.repo.get(principal.tenant_id, run_id)
            if run is None:
                return _jsonrpc_error(req_id, -32004, "Run not found")
            if run.status != RunStatus.WAITING_APPROVAL or run.approval_digest != run.digest():
                return _jsonrpc_error(req_id, -32009, "Approval request is stale or invalid")
            approved = await svc.repo.approve_and_enqueue(
                run.tenant_id, run.id, run.approval_digest, principal.user_id
            )
            if not approved:
                return _jsonrpc_error(req_id, -32009, "Approval request changed concurrently")
            return _tool_result(
                req_id,
                {"run_id": str(run.id), "status": "pending", "message": "Approved and queued"},
            )

        return _jsonrpc_error(req_id, -32601, "Unknown tool")
    except Exception:
        logger.exception("MCP tool execution failed: tool=%s", tool_name[:128])
        return _jsonrpc_error(req_id, -32000, "Tool execution failed")
