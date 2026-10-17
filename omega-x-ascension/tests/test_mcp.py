from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi.testclient import TestClient
from pydantic import SecretStr

from omega import __version__
from omega.config import get_settings
from omega.domain import RunStatus, WorkflowRun
from omega.main import app

TEST_SECRET = "a" * 32


class TestSettings:
    jwt_secret = SecretStr(TEST_SECRET)
    jwt_issuer = "omega-x"
    jwt_audience = "omega-x-api"
    jwt_algorithm = "HS256"


def make_token(tenant_id: UUID, scopes: str = "runs:read runs:write runs:approve") -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": "test-user",
            "tenant_id": str(tenant_id),
            "scope": scopes,
            "iss": "omega-x",
            "aud": "omega-x-api",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        TEST_SECRET,
        algorithm="HS256",
    )


class FakeRedis:
    async def eval(self, script, numkeys, key, ttl):
        return 1


class FakeRouter:
    async def select(self, capability):
        return object()


class FakeRepo:
    def __init__(self):
        self.runs = {}

    async def create_run(self, run: WorkflowRun, actor: str, enqueue: bool) -> None:
        self.runs[(run.tenant_id, run.id)] = run

    async def get(self, tenant_id: UUID, run_id: UUID):
        return self.runs.get((tenant_id, run_id))

    async def list_runs(self, tenant_id: UUID, limit: int = 50):
        runs = [run for (tenant, _), run in self.runs.items() if tenant == tenant_id]
        return sorted(runs, key=lambda run: run.created_at, reverse=True)[:limit]

    async def approve_and_enqueue(self, tenant_id: UUID, run_id: UUID, digest: str, actor: str):
        run = self.runs.get((tenant_id, run_id))
        if (
            run is None
            or run.status != RunStatus.WAITING_APPROVAL
            or run.approval_digest != digest
        ):
            return False
        run.status = RunStatus.PENDING
        return True


class FakeBrowser:
    async def search(self, query):
        return {"query": query, "results": []}


class FakeServices:
    def __init__(self):
        self.repo = FakeRepo()
        self.router = FakeRouter()
        self.browser = FakeBrowser()
        self.redis = FakeRedis()


def rpc(client, token, method, params=None, request_id=1):
    response = client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def tool_call(client, token, name, arguments=None, request_id=10):
    return rpc(
        client,
        token,
        "tools/call",
        {"name": name, "arguments": arguments or {}},
        request_id,
    )


def test_mcp_info_and_public_version():
    client = TestClient(app)

    res_ver = client.get("/version")
    assert res_ver.status_code == 200
    data_ver = res_ver.json()
    assert data_ver["version"] == __version__
    assert data_ver["api_version"] == "v1"
    assert "mcp_server" in data_ver["features"]

    res_mcp = client.get("/mcp")
    assert res_mcp.status_code == 200
    data_mcp = res_mcp.json()
    assert data_mcp["server"] == "omega-x-ascension-mcp"
    assert data_mcp["version"] == __version__
    assert "omega_create_run" in data_mcp["tools"]
    assert data_mcp["authentication"] == "Bearer JWT"


def test_mcp_jsonrpc_requires_authentication(monkeypatch):
    app.dependency_overrides[get_settings] = lambda: TestSettings()
    client = TestClient(app)
    try:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "omega_create_run",
                    "arguments": {"goal": "unauthenticated work", "task_type": "planning"},
                },
            },
        )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_mcp_protocol_and_tenant_scoped_run_lifecycle(monkeypatch):
    tenant = uuid4()
    other_tenant = uuid4()
    token = make_token(tenant)
    other_token = make_token(other_tenant)
    services = FakeServices()
    prior_services = getattr(app.state, "services", None)
    app.state.services = services
    app.dependency_overrides[get_settings] = lambda: TestSettings()
    client = TestClient(app)
    try:
        initialized = rpc(client, token, "initialize")["result"]
        assert initialized["serverInfo"]["name"] == "omega-x-ascension-mcp"
        assert initialized["protocolVersion"] == "2024-11-05"

        listed_tools = rpc(client, token, "tools/list")["result"]["tools"]
        names = {item["name"] for item in listed_tools}
        assert {"omega_get_version", "omega_create_run", "omega_get_run", "omega_list_runs", "omega_approve_run"} <= names

        version = tool_call(client, token, "omega_get_version")["result"]
        assert version["isError"] is False
        assert __version__ in version["content"][0]["text"]

        created_response = tool_call(
            client,
            token,
            "omega_create_run",
            {"goal": "Prepare a controlled rollout", "task_type": "planning", "requested_actions": ["deploy"]},
        )
        created = json.loads(created_response["result"]["content"][0]["text"])
        run_id = created["run_id"]
        assert created["status"] == "waiting_approval"
        run = services.repo.runs[(tenant, UUID(run_id))]
        assert run.created_by == "test-user"
        assert run.tenant_id == tenant

        fetched_response = tool_call(client, token, "omega_get_run", {"run_id": run_id})
        fetched = json.loads(fetched_response["result"]["content"][0]["text"])
        assert fetched["id"] == run_id
        assert fetched["status"] == "waiting_approval"

        listed_response = tool_call(client, token, "omega_list_runs", {"limit": 10})
        listed = json.loads(listed_response["result"]["content"][0]["text"])
        assert len(listed["runs"]) == 1

        denied = tool_call(client, other_token, "omega_get_run", {"run_id": run_id})
        assert denied["error"]["code"] == -32004

        approved_response = tool_call(client, token, "omega_approve_run", {"run_id": run_id})
        approved = json.loads(approved_response["result"]["content"][0]["text"])
        assert approved["status"] == "pending"
        assert services.repo.runs[(tenant, UUID(run_id))].status == RunStatus.PENDING
    finally:
        app.dependency_overrides.clear()
        if prior_services is None:
            try:
                del app.state.services
            except AttributeError:
                pass
        else:
            app.state.services = prior_services


def test_mcp_scope_is_enforced(monkeypatch):
    tenant = uuid4()
    token = make_token(tenant, "runs:write")
    app.dependency_overrides[get_settings] = lambda: TestSettings()
    client = TestClient(app)
    try:
        response = client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {token}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_mcp_create_run_enforces_computer_action_scopes(monkeypatch):
    """MCP run creation must require the same computer scopes as the REST API."""
    tenant = uuid4()
    # Full run permissions, but no computer:execute / computer:read / computer:write.
    token = make_token(tenant, "runs:read runs:write runs:approve")
    services = FakeServices()
    prior_services = getattr(app.state, "services", None)
    app.state.services = services
    app.dependency_overrides[get_settings] = lambda: TestSettings()
    client = TestClient(app)
    try:
        def create_with_actions(actions, request_id):
            return client.post(
                "/mcp",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {
                        "name": "omega_create_run",
                        "arguments": {
                            "goal": "Scoped capability request",
                            "task_type": "coding",
                            "requested_actions": actions,
                        },
                    },
                },
            )

        executed = create_with_actions(["execute_code"], 1)
        assert executed.status_code == 403
        assert "computer:execute" in executed.json()["detail"]
        assert not services.repo.runs

        read_files = create_with_actions(["use_workspace_files"], 2)
        assert read_files.status_code == 403
        assert "computer:read" in read_files.json()["detail"]
        assert not services.repo.runs

        malformed = create_with_actions(["write_workspace_files"], 3)
        assert malformed.status_code == 400
        assert "use_workspace_files" in malformed.json()["detail"]
        assert not services.repo.runs
    finally:
        app.dependency_overrides.clear()
        if prior_services is None:
            try:
                del app.state.services
            except AttributeError:
                pass
        else:
            app.state.services = prior_services
