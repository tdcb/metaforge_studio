"""Unit tests for MetaForge Model Context Protocol (MCP) Server and Endpoints."""
import json
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.agent.mcp_server import mcp_registry, dispatch_jsonrpc_request


@pytest.fixture
def client():
    return TestClient(app)


def test_mcp_registry_tools_and_resources():
    tools = mcp_registry.list_tools()
    tool_names = [t["name"] for t in tools]
    assert "get_model_summary" in tool_names
    assert "get_table_schema" in tool_names
    assert "add_table" in tool_names
    assert "modify_table" in tool_names
    assert "drop_table" in tool_names
    assert "add_relationship" in tool_names
    assert "add_view" in tool_names
    assert "compile_ddl" in tool_names
    assert "generate_dbt_project" in tool_names
    assert "run_complete_compare" in tool_names
    assert "reverse_engineer_ddl" in tool_names
    assert "apply_naming_glossary" in tool_names
    assert "profile_data" in tool_names

    resources = mcp_registry.list_resources()
    resource_uris = [r["uri"] for r in resources]
    assert "model://canonical" in resource_uris
    assert "model://ddl/snowflake" in resource_uris
    assert "model://ddl/sql_server" in resource_uris
    assert "model://dbt/schema" in resource_uris

    prompts = mcp_registry.list_prompts()
    prompt_names = [p["name"] for p in prompts]
    assert "design_star_schema" in prompt_names
    assert "audit_pii_and_governance" in prompt_names


def test_mcp_jsonrpc_initialize_and_ping():
    init_res = dispatch_jsonrpc_request({
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    })
    assert init_res["id"] == "req-1"
    assert init_res["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in init_res["result"]["capabilities"]
    assert init_res["result"]["serverInfo"]["name"] == "metaforge-data-modeling-mcp"

    ping_res = dispatch_jsonrpc_request({
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "ping",
    })
    assert ping_res["id"] == "req-2"
    assert ping_res["result"] == {}


def test_mcp_jsonrpc_resource_read():
    res = dispatch_jsonrpc_request({
        "jsonrpc": "2.0",
        "id": "req-res",
        "method": "resources/read",
        "params": {"uri": "model://ddl/snowflake"},
    })
    assert res["id"] == "req-res"
    contents = res["result"]["contents"]
    assert len(contents) > 0
    assert "CREATE" in contents[0]["text"]


def test_mcp_jsonrpc_tool_call_flow():
    # 1. Summary
    call_res = dispatch_jsonrpc_request({
        "jsonrpc": "2.0",
        "id": "req-call-1",
        "method": "tools/call",
        "params": {"name": "get_model_summary", "arguments": {}},
    })
    assert call_res["result"]["isError"] is False
    summary = json.loads(call_res["result"]["content"][0]["text"])
    assert "project_name" in summary
    assert summary["total_entities"] > 0

    # 2. Compile DDL
    ddl_res = dispatch_jsonrpc_request({
        "jsonrpc": "2.0",
        "id": "req-call-2",
        "method": "tools/call",
        "params": {"name": "compile_ddl", "arguments": {"dialect": "sql_server"}},
    })
    assert ddl_res["result"]["isError"] is False
    ddl_out = json.loads(ddl_res["result"]["content"][0]["text"])
    assert ddl_out["dialect"] == "sql_server"
    assert "CREATE TABLE" in ddl_out["ddl_sql"]

    # 3. Add Table & Column
    add_res = dispatch_jsonrpc_request({
        "jsonrpc": "2.0",
        "id": "req-call-3",
        "method": "tools/call",
        "params": {
            "name": "add_table",
            "arguments": {
                "physical_name": "DIM_MCP_TEST",
                "logical_name": "MCP Test Dimension",
                "subject_area": "Testing",
                "description": "Created via MCP tool",
                "columns": [
                    {"physical_name": "TEST_ID", "data_type": "NUMBER(38,0)", "is_pk": True},
                    {"physical_name": "TEST_NAME", "data_type": "VARCHAR(255)", "is_nullable": False},
                ],
            },
        },
    })
    assert add_res["result"]["isError"] is False

    # 4. Inspect new table schema
    inspect_res = dispatch_jsonrpc_request({
        "jsonrpc": "2.0",
        "id": "req-call-4",
        "method": "tools/call",
        "params": {"name": "get_table_schema", "arguments": {"table_name": "DIM_MCP_TEST"}},
    })
    assert inspect_res["result"]["isError"] is False
    schema = json.loads(inspect_res["result"]["content"][0]["text"])
    assert schema["physical_name"] == "DIM_MCP_TEST"
    assert len(schema["columns"]) >= 2


def test_mcp_http_endpoints(client):
    # Test GET /api/mcp/tools
    res = client.get("/api/mcp/tools")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 15

    # Test GET /api/mcp/resources
    res = client.get("/api/mcp/resources")
    assert res.status_code == 200
    assert len(res.json()["resources"]) >= 5

    # Test GET /api/mcp/config
    res = client.get("/api/mcp/config")
    assert res.status_code == 200
    cfg = res.json()
    assert cfg["status"] == "ready"
    assert "claude_code" in cfg["clients"]
    assert "cursor" in cfg["clients"]
    assert "kiro" in cfg["clients"]
    assert "gemini" in cfg["clients"]

    # Test POST /api/mcp/rpc
    res = client.post("/api/mcp/rpc", json={
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/list",
    })
    assert res.status_code == 200
    rpc_data = res.json()
    assert rpc_data["id"] == 99
    assert len(rpc_data["result"]["tools"]) >= 15

    # Test POST /api/mcp/call
    res = client.post("/api/mcp/call", json={
        "name": "get_model_summary",
        "arguments": {},
    })
    assert res.status_code == 200
    call_data = res.json()
    assert call_data["ok"] is True
    assert call_data["tool"] == "get_model_summary"
