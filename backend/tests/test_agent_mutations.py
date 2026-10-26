"""Tests for AI Agent Gemini integration, Natural Language mutations, and Mutation Engine."""
import json
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.metamodel.seed import build_default_project
from backend.app.agent.mutation_engine import apply_action, execute_mutations

client = TestClient(app)


def _login():
    res = client.post(
        "/api/auth/login",
        json={"email": "architect@metaforge.local", "password": "password123"},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_gemini_models_endpoint():
    headers = _login()
    res = client.get("/api/agent/gemini-models", headers=headers)
    assert res.status_code == 200
    models = res.json()["models"]
    model_ids = [m["id"] for m in models]
    assert "gemini-2.5-flash" in model_ids
    assert "gemini-2.5-pro" in model_ids
    assert "gemini-2.0-flash" in model_ids


def test_mutation_engine_add_table_and_view():
    project = build_default_project()
    actions = [
        {"action": "add_subject_area", "name": "Logistics"},
        {
            "action": "add_table",
            "physical_name": "DIM_WAREHOUSE",
            "logical_name": "Warehouse",
            "subject_area": "Logistics",
            "columns": [
                {"physical_name": "WAREHOUSE_ID", "data_type": "NUMBER(38,0)", "is_pk": True},
                {"physical_name": "WAREHOUSE_NM", "data_type": "VARCHAR(150)", "is_nullable": False},
                {"physical_name": "CAPACITY_SQFT", "data_type": "NUMBER(18,2)"},
            ],
        },
        {
            "action": "add_view",
            "physical_name": "VW_LARGE_WAREHOUSES",
            "logical_name": "Large Warehouses View",
            "subject_area": "Logistics",
            "view_sql": "SELECT WAREHOUSE_ID, WAREHOUSE_NM FROM DIM_WAREHOUSE WHERE CAPACITY_SQFT > 50000",
            "columns": [
                {"physical_name": "WAREHOUSE_ID", "data_type": "NUMBER(38,0)"},
                {"physical_name": "WAREHOUSE_NM", "data_type": "VARCHAR(150)"},
            ],
        },
        {
            "action": "add_relationship",
            "name": "FK_CLAIM_WAREHOUSE",
            "parent_table": "DIM_WAREHOUSE",
            "child_table": "DIM_INSURANCE_POLICY",
            "parent_column": "WAREHOUSE_ID",
            "child_column": "WAREHOUSE_ID",
            "rel_type": "non_identifying",
            "cardinality": "one_to_many",
        },
    ]

    updated_model, applied = execute_mutations(project, actions)
    assert len(applied) == 4
    assert "DIM_WAREHOUSE" in [e.physical_name for e in updated_model.entities.values()]
    assert "VW_LARGE_WAREHOUSES" in [e.physical_name for e in updated_model.entities.values()]

    vw = next(e for e in updated_model.entities.values() if e.physical_name == "VW_LARGE_WAREHOUSES")
    assert vw.entity_type == "view"
    assert "DIM_WAREHOUSE" in vw.view_sql

    # Upstream lineage was automatically created from DIM_WAREHOUSE to VW_LARGE_WAREHOUSES
    lineage_rels = [
        r for r in updated_model.relationships.values()
        if r.rel_type.value == "upstream_lineage" and r.child_entity_id == vw.id
    ]
    assert len(lineage_rels) >= 1


def test_agent_natural_language_instructions_via_api():
    headers = _login()
    project = client.get("/api/project", headers=headers).json()

    # 1. Natural Language: Add Table
    res1 = client.post(
        "/api/agent/execute",
        json={
            "prompt": "Create table DIM_VEHICLE with columns VEHICLE_ID number pk, VIN_NBR varchar, MAKE varchar, MODEL varchar, YEAR int",
            "mode": "builtin-llm",
            "project": project,
        },
        headers=headers,
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["mutated"] is True
    assert "DIM_VEHICLE" in data1["updated_model"]["entities"] or any(
        e["physical_name"] == "DIM_VEHICLE" for e in data1["updated_model"]["entities"].values()
    )

    # 2. Natural Language: Add View
    res2 = client.post(
        "/api/agent/execute",
        json={
            "prompt": "Create view VW_ACTIVE_CUSTOMERS as SELECT CUST_ID, CUST_FULL_NM FROM DIM_CUSTOMER WHERE CUST_STAT_CD = 'ACTIVE'",
            "mode": "builtin-llm",
            "project": data1["updated_model"],
        },
        headers=headers,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["mutated"] is True
    assert any(e["physical_name"] == "VW_ACTIVE_CUSTOMERS" for e in data2["updated_model"]["entities"].values())

    # 3. Natural Language: Add Relationship
    res3 = client.post(
        "/api/agent/execute",
        json={
            "prompt": "Connect relation from DIM_VEHICLE to FCT_CLAIM_TRANSACTION",
            "mode": "builtin-llm",
            "project": data2["updated_model"],
        },
        headers=headers,
    )
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["mutated"] is True

    # 4. Natural Language: Add Column
    res4 = client.post(
        "/api/agent/execute",
        json={
            "prompt": "Add column ODOMETER_MILES number to DIM_VEHICLE",
            "mode": "builtin-llm",
            "project": data3["updated_model"],
        },
        headers=headers,
    )
    assert res4.status_code == 200
    data4 = res4.json()
    assert data4["mutated"] is True
    veh = next(e for e in data4["updated_model"]["entities"].values() if e["physical_name"] == "DIM_VEHICLE")
    col_names = [c["physical_name"] for c in veh["columns"]]
    assert "ODOMETER_MILES" in col_names

    # Clean up project
    client.post("/api/project/reset", headers=headers)


def test_gemini_metadata_generation_fallback_and_live():
    from backend.app.agent.gemini_service import generate_metadata_with_gemini
    from unittest.mock import MagicMock, patch

    project = build_default_project()
    first_ent = next(iter(project.entities.values()))

    # 1. Fallback when API key is empty
    stats, updated_model = generate_metadata_with_gemini(
        model=project,
        entity_id=first_ent.id,
        gemini_api_key="",
        gemini_model="gemini-2.5-flash",
        overwrite_existing=True,
    )
    assert stats["entities_updated"] >= 1
    assert "Gemini" in stats["ai_provider"]

    # 2. Live call with simulated Gemini JSON response
    mock_gemini_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "entities": [
                                    {
                                        "id": first_ent.id,
                                        "physical_name": first_ent.physical_name,
                                        "logical_name": "Verified Policyholder Dimension",
                                        "description": "Enterprise dimension storing verified corporate and retail customer accounts with regulatory retention policies.",
                                        "business_purpose": "Master identity and credit risk scoring",
                                        "grain": "One record per individual customer account entity",
                                        "retention_period": "7 years (SOX Compliance)",
                                        "modeling_stereotype": "DIM_SCD2",
                                        "columns": [
                                            {
                                                "physical_name": first_ent.columns[0].physical_name,
                                                "logical_name": "Master Customer Account Key",
                                                "description": "Surrogate primary key identifying the customer across omnichannel claims systems.",
                                                "pii_classification": "NONE"
                                            }
                                        ]
                                    }
                                ]
                            })
                        }
                    ]
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_gemini_response

    with patch("httpx.Client.post", return_value=mock_resp):
        stats_live, updated_live = generate_metadata_with_gemini(
            model=project,
            entity_id=first_ent.id,
            gemini_api_key="test-mock-gemini-key",
            gemini_model="gemini-2.5-flash",
            overwrite_existing=True,
        )
        assert stats_live["live_llm"] is True
        assert stats_live["entities_updated"] == 1
        assert "Google Gemini (gemini-2.5-flash)" in stats_live["ai_provider"]
        target = updated_live.entities[first_ent.id]
        assert target.logical_name == "Verified Policyholder Dimension"
        assert target.grain_statement == "One record per individual customer account entity"
        assert target.retention_policy.regulatory_framework == "SOX_7YR"
        assert target.columns[0].logical_name == "Master Customer Account Key"


def test_auto_metadata_endpoint_with_gemini():
    headers = _login()
    res = client.post(
        "/api/governance/auto-metadata",
        json={
            "gemini_model": "gemini-2.5-flash",
            "overwrite_existing": True,
        },
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert "stats" in data
    assert data["stats"]["entities_updated"] > 0


def test_apply_mutations_endpoint():
    headers = _login()
    res = client.post(
        "/api/agent/apply-mutations",
        json={
            "mutations": [
                {
                    "action": "add_view",
                    "physical_name": "VW_CLIENT_TEST_SUMMARY",
                    "view_sql": "SELECT 1 AS TEST_COL",
                    "materialization": "view",
                }
            ],
            "prompt": "Create test view",
            "reply": "Successfully created view VW_CLIENT_TEST_SUMMARY",
            "mode_used": "Google Gemini (gemini-2.5-flash)",
        },
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mutated"] is True
    assert any("VW_CLIENT_TEST_SUMMARY" in a for a in data["actions_taken"])
    assert any(
        e["physical_name"] == "VW_CLIENT_TEST_SUMMARY"
        for e in data["updated_model"]["entities"].values()
    )


def test_agent_execute_gemini_fallback():
    headers = _login()
    # When Gemini API throws a network error, execute should fall back to built-in architect without failing
    res = client.post(
        "/api/agent/execute",
        json={
            "prompt": "Create view VW_FALLBACK_AUTO_VIEW as SELECT 1 AS ID",
            "mode": "gemini",
            "gemini_api_key": "dummy-unreachable-key",
            "gemini_model": "gemini-2.5-flash",
        },
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mutated"] is True
    assert "Built-in Architect" in data["mode_used"]
    assert any("VW_FALLBACK_AUTO_VIEW" in a for a in data["actions_taken"])


