"""Unit tests for Canonical Metamodel, Enterprise Domains, Naming Standards Glossary, and RBAC."""
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.metamodel.seed import build_default_project
from backend.app.metamodel.domains import cascade_domain_to_model
from backend.app.metamodel.glossary import apply_glossary_to_project, translate_logical_to_physical
from backend.app.metamodel.schema import EnterpriseDomain


client = TestClient(app)


def test_seed_model_structure():
    project = build_default_project()
    assert len(project.domains) >= 4
    assert len(project.glossary.abbreviations) >= 15
    assert "ent-dim-customer" in project.entities
    assert "ent-dim-policy" in project.entities
    assert "ent-fct-claim" in project.entities
    assert "ent-stg-raw-claims" in project.entities
    assert "ent-vw-policy-claim-summary" in project.entities
    assert len(project.relationships) >= 4



def test_domain_cascade_updates_bound_columns():
    project = build_default_project()
    updated_monetary = EnterpriseDomain(
        id="dom-monetary-amount",
        name="Monetary_Amount",
        logical_type="Currency / High-Precision Decimal",
        snowflake_type="NUMBER(22,4)",
        sql_server_type="DECIMAL(22,4)",
        oracle_type="NUMBER(22,4)",
        nullable_default=False,
        dbt_tests=["not_null"],
    )
    count = cascade_domain_to_model(project, updated_monetary)
    assert count >= 3
    fct_claim = project.entities["ent-fct-claim"]
    paid_col = next(c for c in fct_claim.columns if c.physical_name == "CLM_PAID_AMT")
    assert paid_col.data_type_snowflake == "NUMBER(22,4)"
    assert paid_col.data_type_sql_server == "DECIMAL(22,4)"
    assert paid_col.data_type_oracle == "NUMBER(22,4)"


def test_naming_standards_glossary_translation():
    project = build_default_project()
    translated = translate_logical_to_physical("Customer Transaction Amount", project.glossary)
    assert translated == "CUST_TXN_AMT"

    ent = project.entities["ent-dim-customer"]
    ent.columns[1].logical_name = "Customer Account Balance Amount"
    stats = apply_glossary_to_project(project, overwrite_existing=True)
    assert stats["columns_updated"] >= 1
    assert ent.columns[1].physical_name == "CUST_ACCT_BAL_AMT"


def test_auth_and_rbac_enforcement():
    # Login as Viewer
    res_viewer = client.post(
        "/api/auth/login",
        json={"email": "viewer@metaforge.local", "password": "password123"},
    )
    assert res_viewer.status_code == 200
    viewer_token = res_viewer.json()["access_token"]

    # Viewer can load project
    get_res = client.get(
        "/api/project",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert get_res.status_code == 200
    project_data = get_res.json()

    # Viewer is blocked from PUT /api/project
    put_res = client.put(
        "/api/project",
        json=project_data,
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert put_res.status_code == 403

    # Login as Data Steward
    res_steward = client.post(
        "/api/auth/login",
        json={"email": "steward@metaforge.local", "password": "password123"},
    )
    assert res_steward.status_code == 200
    steward_token = res_steward.json()["access_token"]

    # Steward can update business metadata (description)
    project_data["entities"]["ent-dim-customer"]["description"] = "Steward updated description"
    steward_ok = client.put(
        "/api/project",
        json=project_data,
        headers={"Authorization": f"Bearer {steward_token}"},
    )
    assert steward_ok.status_code == 200

    # Steward is blocked from changing physical data types
    project_data["entities"]["ent-dim-customer"]["columns"][0]["data_type_snowflake"] = "VARCHAR(999)"
    steward_blocked = client.put(
        "/api/project",
        json=project_data,
        headers={"Authorization": f"Bearer {steward_token}"},
    )
    assert steward_blocked.status_code == 403

    # Restore clean seed state
    client.post("/api/project/reset")

