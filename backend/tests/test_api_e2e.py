"""End-to-End REST API Integration Tests covering all Section 6 endpoints."""
from fastapi.testclient import TestClient
from backend.app.main import app


client = TestClient(app)


def test_full_rest_api_workflow():
    # 1. POST /api/auth/login (Architect)
    login_res = client.post(
        "/api/auth/login",
        json={"email": "architect@metaforge.local", "password": "password123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. GET /api/auth/me
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "Data Architect"

    # 3. GET /api/project
    proj_res = client.get("/api/project", headers=headers)
    assert proj_res.status_code == 200
    project = proj_res.json()
    assert len(project["entities"]) >= 4

    # 4. POST /api/project/compile
    comp_res = client.post(
        "/api/project/compile",
        json={"project": project},
        headers=headers,
    )
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert "CREATE OR REPLACE" in comp_data["snowflake_ddl"]
    assert "CREATE TABLE [dbo].[DIM_CUSTOMER]" in comp_data["sql_server_ddl"]
    assert "CREATE TABLE CORE_DATA.DIM_CUSTOMER" in comp_data["oracle_ddl"]
    assert "models/schema.yml" in comp_data["dbt_files"]

    # 5. POST /api/project/glossary/apply
    nsm_res = client.post(
        "/api/project/glossary/apply",
        json=project,
        headers=headers,
    )
    assert nsm_res.status_code == 200

    # 6. POST /api/reverse-engineer/ddl
    rev_res = client.post(
        "/api/reverse-engineer/ddl",
        json={
            "ddl_script": "CREATE TABLE FINANCE.DIM_UNDERWRITER (UW_ID NUMBER(38,0) PRIMARY KEY, UW_FULL_NM VARCHAR(100) NOT NULL);",
            "dialect": "snowflake",
            "subject_area": "Finance",
            "merge_into_project": True,
        },
        headers=headers,
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["entities_parsed"] == 1

    # 7. POST /api/compare/diff
    diff_res = client.post(
        "/api/compare/diff",
        json={
            "dialect": "snowflake",
            "target_ddl": "CREATE TABLE CORE.DIM_CUSTOMER (CUST_ID NUMBER(38,0) PRIMARY KEY, CUST_FULL_NM VARCHAR(50) NOT NULL);",
        },
        headers=headers,
    )
    assert diff_res.status_code == 200
    assert diff_res.json()["total_differences"] > 0
    assert "ALTER TABLE" in diff_res.json()["alter_script"]

    # 8. POST /api/agent/execute
    agent_res = client.post(
        "/api/agent/execute",
        json={
            "prompt": "Which foreign keys are missing indexes in Oracle?",
            "mode": "builtin-llm",
        },
        headers=headers,
    )
    assert agent_res.status_code == 200
    assert "CREATE INDEX" in agent_res.json()["reply"]

    # 9. GET /api/revisions
    revs_res = client.get("/api/revisions", headers=headers)
    assert revs_res.status_code == 200
    assert len(revs_res.json()) >= 1

    # 10. GET /api/mcp/tools
    mcp_res = client.get("/api/mcp/tools", headers=headers)
    assert mcp_res.status_code == 200
    tool_names = {t["name"] for t in mcp_res.json()["tools"]}
    assert "get_model_summary" in tool_names
    assert "run_complete_compare" in tool_names
    assert "generate_dbt_project" in tool_names

    # 11. POST /api/governance/auto-metadata
    cust_id = next(iter(project["entities"].keys()))
    meta_res = client.post(
        "/api/governance/auto-metadata",
        json={"project": project, "entity_id": cust_id, "overwrite_existing": True},
        headers=headers,
    )
    assert meta_res.status_code == 200
    meta_data = meta_res.json()
    assert meta_data["stats"]["entities_updated"] >= 1
    assert meta_data["project"]["entities"][cust_id]["grain_statement"] != ""

    # 12. POST /api/governance/profile
    prof_res = client.post(
        "/api/governance/profile",
        json={"project": meta_data["project"], "entity_id": cust_id},
        headers=headers,
    )
    assert prof_res.status_code == 200
    prof_data = prof_res.json()
    assert prof_data["project"]["entities"][cust_id]["volumetrics"]["estimated_row_count"] > 0
    assert prof_data["project"]["entities"][cust_id]["columns"][0]["profile"] is not None

    # 13. POST /api/governance/apply-dq
    dq_res = client.post(
        "/api/governance/apply-dq",
        json={"project": prof_data["project"], "entity_id": cust_id},
        headers=headers,
    )
    assert dq_res.status_code == 200

    # 14. POST /api/governance/apply-pattern (SCD_TYPE_2)
    pat_res = client.post(
        "/api/governance/apply-pattern",
        json={"project": dq_res.json()["project"], "entity_id": cust_id, "pattern": "SCD_TYPE_2"},
        headers=headers,
    )
    assert pat_res.status_code == 200
    pat_cols = [c["physical_name"] for c in pat_res.json()["project"]["entities"][cust_id]["columns"]]
    assert "EFF_START_TS" in pat_cols
    assert "EFF_END_TS" in pat_cols

    # 15. Verify Open Data Contract YAML in /api/project/compile
    assert "dataContractSpecification: 2.2.0" in comp_data["datacontract_yaml"]
    assert "CREATE MASKING POLICY" in comp_data["snowflake_ddl"]

    # Reset project to clean seed state
    client.post("/api/project/reset", headers=headers)

