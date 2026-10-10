from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from omega.config import Capability
from omega.domain import ApprovalPolicy, RunStatus, WorkflowRun

router = APIRouter(tags=["mcp"])

SERVER_NAME = "omega-x-ascension-mcp"
SERVER_VERSION = "0.7.0"
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "omega_create_run",
        "description": "Trigger an autonomous multi-stage workflow run in Omega-X Ascension with goal and capability.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The objective or mission for the agent system to execute.",
                },
                "task_type": {
                    "type": "string",
                    "enum": [
                        "reasoning",
                        "coding",
                        "mathematics",
                        "planning",
                        "analysis",
                        "summarization",
                        "research",
                    ],
                    "description": "Primary capability required for specialist routing.",
                },
                "requested_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional actions such as execute_code.",
                },
            },
            "required": ["goal", "task_type"],
        },
    },
    {
        "name": "omega_get_run",
        "description": "Get details, status, output, or error of a specific workflow run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "UUID string of the workflow run"}
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "omega_list_runs",
        "description": "List recent workflow runs and their status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of runs to return (default 20)",
                }
            },
        },
    },
    {
        "name": "omega_approve_run",
        "description": "Approve a workflow run waiting for human-in-the-loop sign-off.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "UUID string of the workflow run"}
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "omega_search_web",
        "description": "Run a live web search using Omega's browser tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "omega_get_version",
        "description": "Get platform version, API version, and enabled features.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Any | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


def _jsonrpc_success(req_id: Any, result: Any) -> JSONResponse:
    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": result})


def _jsonrpc_error(req_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}},
    )


@router.get("")
@router.get("/")
async def mcp_info():
    return {
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "protocolVersion": PROTOCOL_VERSION,
        "tools_count": len(TOOLS),
        "tools": [t["name"] for t in TOOLS],
        "status": "ready",
    }


@router.post("")
@router.post("/")
async def handle_mcp(request: Request, body: JsonRpcRequest):
    svc = request.app.state.services
    method = body.method
    req_id = body.id
    params = body.params or {}

    if method == "initialize":
        return _jsonrpc_success(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    elif method == "ping":
        return _jsonrpc_success(req_id, {})

    elif method == "tools/list":
        return _jsonrpc_success(req_id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})

        try:
            if tool_name == "omega_get_version":
                return _jsonrpc_success(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "version": SERVER_VERSION,
                                    "api_version": "v1",
                                    "protocol": PROTOCOL_VERSION,
                                    "features": [
                                        "langgraph_feedback_loop",
                                        "mcp_server",
                                        "hitl_approval",
                                    ],
                                }),
                            }
                        ],
                        "isError": False,
                    },
                )

            elif tool_name == "omega_search_web":
                query = args.get("query", "").strip()
                if not query:
                    return _jsonrpc_error(req_id, -32602, "Missing query parameter")
                res = await svc.browser.search(query)
                return _jsonrpc_success(
                    req_id,
                    {
                        "content": [{"type": "text", "text": json.dumps(res)}],
                        "isError": False,
                    },
                )

            elif tool_name == "omega_create_run":
                goal = args.get("goal")
                task_type = args.get("task_type")
                actions = args.get("requested_actions", [])
                if not goal or not task_type:
                    return _jsonrpc_error(
                        req_id, -32602, "Missing required parameters: goal and task_type"
                    )

                tenant_id = uuid4()
                user_id = "mcp-client"

                run = WorkflowRun(
                    goal=goal,
                    task_type=task_type,
                    tenant_id=tenant_id,
                    created_by=user_id,
                    requested_actions=actions,
                )
                if ApprovalPolicy().requires_approval(set(actions)):
                    run.status = RunStatus.WAITING_APPROVAL
                    run.approval_digest = run.digest()

                await svc.repo.create_run(run, user_id, run.status == RunStatus.PENDING)
                return _jsonrpc_success(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "run_id": str(run.id),
                                    "tenant_id": str(run.tenant_id),
                                    "status": run.status.value,
                                    "goal": run.goal,
                                    "task_type": run.task_type,
                                }),
                            }
                        ],
                        "isError": False,
                    },
                )

            elif tool_name == "omega_approve_run":
                raw_id = args.get("run_id")
                if not raw_id:
                    return _jsonrpc_error(req_id, -32602, "Missing run_id")
                run_uuid = UUID(raw_id)
                return _jsonrpc_success(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "run_id": str(run_uuid),
                                    "message": "Approval request received",
                                }),
                            }
                        ],
                        "isError": False,
                    },
                )

            else:
                return _jsonrpc_error(req_id, -32601, f"Unknown tool: {tool_name}")

        except Exception as exc:
            return _jsonrpc_error(req_id, -32000, f"Tool execution failed: {type(exc).__name__}: {exc}")

    else:
        return _jsonrpc_error(req_id, -32601, f"Unknown method: {method}")
