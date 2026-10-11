from fastapi.testclient import TestClient

from omega import __version__
from omega.main import app


def test_mcp_info_and_version():
    client = TestClient(app)

    # Check /version
    res_ver = client.get("/version")
    assert res_ver.status_code == 200
    data_ver = res_ver.json()
    assert data_ver["version"] == __version__
    assert data_ver["api_version"] == "v1"
    assert "mcp_server" in data_ver["features"]
    assert "langgraph_feedback_loop" in data_ver["features"]

    # Check /mcp info
    res_mcp = client.get("/mcp")
    assert res_mcp.status_code == 200
    data_mcp = res_mcp.json()
    assert data_mcp["server"] == "omega-x-ascension-mcp"
    assert data_mcp["version"] == __version__
    assert "omega_create_run" in data_mcp["tools"]


def test_mcp_jsonrpc_protocol():
    client = TestClient(app)

    # Initialize
    init_payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    res_init = client.post("/mcp", json=init_payload)
    assert res_init.status_code == 200
    data_init = res_init.json()
    assert data_init["result"]["serverInfo"]["name"] == "omega-x-ascension-mcp"
    assert data_init["result"]["protocolVersion"] == "2024-11-05"

    # Ping
    ping_payload = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    res_ping = client.post("/mcp", json=ping_payload)
    assert res_ping.status_code == 200
    assert res_ping.json()["result"] == {}

    # Tools list
    tools_payload = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    res_tools = client.post("/mcp", json=tools_payload)
    assert res_tools.status_code == 200
    tools = res_tools.json()["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "omega_get_version" in tool_names
    assert "omega_create_run" in tool_names

    # Call tool omega_get_version
    call_payload = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "omega_get_version", "arguments": {}},
    }
    res_call = client.post("/mcp", json=call_payload)
    assert res_call.status_code == 200
    result = res_call.json()["result"]
    assert result["isError"] is False
    assert __version__ in result["content"][0]["text"]
