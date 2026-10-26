"""Unit & integration tests for Remote Model Repository, User Access Control (ACL), Check-Out Locking, Force Release & 3-Way Auto-Reapply."""
import copy
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers(client: TestClient, email: str, password: str = "password123") -> dict:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_remote_repo_full_workflow_checkout_lock_force_release_and_reapply(client: TestClient):
    admin_headers = _auth_headers(client, "admin@metaforge.local")
    arch_headers = _auth_headers(client, "architect@metaforge.local")
    steward_headers = _auth_headers(client, "steward@metaforge.local")
    viewer_headers = _auth_headers(client, "viewer@metaforge.local")

    # 1. Create a fresh remote model for deterministic testing
    create_resp = client.post(
        "/api/remote-models",
        headers=admin_headers,
        json={
            "name": "Global Claims & Reinsurance Model",
            "description": "Shared enterprise model for testing remote check-in/out and 3-way merge",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    model_summary = create_resp.json()
    model_id = model_summary["id"]
    assert model_summary["current_version"] == 1
    assert model_summary["is_locked"] is False

    # 2. Admin configures user-based access control (ACL)
    acl_resp = client.get(f"/api/remote-models/{model_id}/access", headers=admin_headers)
    assert acl_resp.status_code == 200
    entries = acl_resp.json()
    assert len(entries) >= 4

    # Let's give architect EDIT, steward EDIT, and viewer VIEW
    updated_entries = []
    for entry in entries:
        if entry["user_email"] == "admin@metaforge.local":
            entry["permission"] = "ADMIN"
        elif entry["user_email"] in ("architect@metaforge.local", "steward@metaforge.local"):
            entry["permission"] = "EDIT"
        else:
            entry["permission"] = "VIEW"
        updated_entries.append(entry)

    put_acl = client.put(
        f"/api/remote-models/{model_id}/access",
        headers=admin_headers,
        json={"entries": updated_entries},
    )
    assert put_acl.status_code == 200

    # Non-admin (viewer) cannot change ACL
    forbidden_acl = client.put(
        f"/api/remote-models/{model_id}/access",
        headers=viewer_headers,
        json={"entries": updated_entries},
    )
    assert forbidden_acl.status_code == 403

    # 3. View-Only inspection without checkout
    view_resp = client.get(f"/api/remote-models/{model_id}/view", headers=viewer_headers)
    assert view_resp.status_code == 200
    view_data = view_resp.json()
    assert view_data["work_mode"] == "view_only"
    assert view_data["summary"]["is_locked"] is False
    assert view_data["summary"]["user_permission"] == "VIEW"

    # Viewer with VIEW permission cannot check out the model
    viewer_co = client.post(f"/api/remote-models/{model_id}/checkout", headers=viewer_headers)
    assert viewer_co.status_code == 403

    # 4. Architect checks out the model -> downloads locally & locks in shared repo
    arch_co = client.post(f"/api/remote-models/{model_id}/checkout", headers=arch_headers)
    assert arch_co.status_code == 200, arch_co.text
    arch_co_data = arch_co.json()
    assert arch_co_data["work_mode"] == "checked_out_by_me"
    assert arch_co_data["summary"]["is_locked"] is True
    assert arch_co_data["summary"]["checked_out_by_email"] == "architect@metaforge.local"
    assert "Marcus Sterling" in arch_co_data["summary"]["checked_out_by_name"]
    arch_checkout_id = arch_co_data["active_checkout_id"]
    assert arch_checkout_id is not None

    # 5. Steward & Viewer can see who checked out the model, and can still open in View-Only mode
    steward_view = client.get(f"/api/remote-models/{model_id}/view", headers=steward_headers)
    assert steward_view.status_code == 200
    sv_data = steward_view.json()
    assert sv_data["work_mode"] == "view_only"
    assert sv_data["summary"]["is_locked"] is True
    assert sv_data["summary"]["checked_out_by_email"] == "architect@metaforge.local"

    # Steward tries to check out while locked by Architect -> blocked with 409 showing lock holder
    steward_co_blocked = client.post(f"/api/remote-models/{model_id}/checkout", headers=steward_headers)
    assert steward_co_blocked.status_code == 409
    assert "Marcus Sterling" in steward_co_blocked.json()["detail"]

    # 6. Architect makes local edits to their checked-out model and saves draft
    arch_project = copy.deepcopy(arch_co_data["project"])
    ent_keys = sorted(arch_project["entities"].keys())
    ent0_key = ent_keys[0]
    ent1_key = ent_keys[1]

    # Architect modifies entity 0 description and adds a new table 'DIM_REINSURANCE_TREATY'
    arch_project["entities"][ent0_key]["description"] = "Architect updated description for entity 0 (non-conflicting)"
    arch_project["entities"]["ent-reinsurance-treaty"] = {
        "id": "ent-reinsurance-treaty",
        "physical_name": "DIM_REINSURANCE_TREATY",
        "logical_name": "Reinsurance Treaty Dimension",
        "description": "Tracks quota share and excess of loss reinsurance treaties.",
        "subject_area": "Core",
        "entity_type": "table",
        "columns": [
            {
                "id": "col-treaty-sk",
                "physical_name": "TREATY_SK",
                "logical_name": "Treaty Surrogate Key",
                "data_type_snowflake": "NUMBER(38,0)",
                "data_type_sql_server": "BIGINT",
                "data_type_oracle": "NUMBER(19)",
                "is_pk": True,
                "is_fk": False,
                "is_nullable": False,
                "description": "Primary surrogate key for reinsurance treaty.",
            }
        ],
    }

    draft_resp = client.post(
        f"/api/remote-models/{model_id}/draft",
        headers=arch_headers,
        json={"project": arch_project, "checkout_id": arch_checkout_id},
    )
    assert draft_resp.status_code == 200

    # 7. Admin force-releases Architect's lock!
    force_resp = client.post(
        f"/api/remote-models/{model_id}/force-release",
        headers=admin_headers,
        json={"reason": "Emergency production governance patch required by Steward"},
    )
    assert force_resp.status_code == 200, force_resp.text
    force_summary = force_resp.json()
    assert force_summary["is_locked"] is False
    assert force_summary["checked_out_by_email"] is None

    # 8. Architect attempts to check in their changes -> DENIED with 409 CHECKIN_DENIED_FORCE_RELEASED,
    #    while preserving Architect's draft for later re-application!
    denied_checkin = client.post(
        f"/api/remote-models/{model_id}/checkin",
        headers=arch_headers,
        json={
            "project": arch_project,
            "commit_message": "Architect attempting check-in after force release",
            "checkout_id": arch_checkout_id,
        },
    )
    assert denied_checkin.status_code == 409
    denied_detail = denied_checkin.json()["detail"]
    assert "CHECKIN_DENIED_FORCE_RELEASED" in str(denied_detail)

    # 9. Meanwhile, Admin (or another editor) checks out the model, modifies Entity 1 (different entity),
    #    and checks in v2!
    admin_co = client.post(f"/api/remote-models/{model_id}/checkout", headers=admin_headers)
    assert admin_co.status_code == 200
    admin_project = copy.deepcopy(admin_co.json()["project"])
    admin_checkout_id = admin_co.json()["active_checkout_id"]

    # Admin updates Entity 1 description (non-conflicting with Architect's Entity 0 + new table)
    admin_project["entities"][ent1_key]["description"] = "Admin emergency update on Entity 1 in v1.0.2"

    admin_ci = client.post(
        f"/api/remote-models/{model_id}/checkin",
        headers=admin_headers,
        json={
            "project": admin_project,
            "commit_message": "Admin emergency hotfix on Entity 1",
            "checkout_id": admin_checkout_id,
        },
    )
    assert admin_ci.status_code == 200
    assert admin_ci.json()["summary"]["current_version"] == 2
    assert admin_ci.json()["summary"]["is_locked"] is False

    # 10. Now the model is available for checkout again!
    #     Architect checks list_remote_models and sees `revoked_session` metadata available.
    arch_list = client.get("/api/remote-models", headers=arch_headers).json()
    target_summary = next(m for m in arch_list if m["id"] == model_id)
    assert target_summary["revoked_session"] is not None
    assert target_summary["revoked_session"]["checkout_id"] == arch_checkout_id

    # 11. Architect calls `/reapply` to check out v2 and automatically re-apply non-conflicting changes from v1 draft!
    reapply_resp = client.post(
        f"/api/remote-models/{model_id}/reapply",
        headers=arch_headers,
        json={"checkout_id": arch_checkout_id},
    )
    assert reapply_resp.status_code == 200, reapply_resp.text
    reapply_data = reapply_resp.json()
    assert reapply_data["work_mode"] == "checked_out_by_me"
    assert reapply_data["summary"]["is_locked"] is True
    assert reapply_data["summary"]["checked_out_by_email"] == "architect@metaforge.local"
    assert reapply_data["merge_report"]["base_version"] == 1
    assert reapply_data["merge_report"]["target_remote_version"] == 2
    assert len(reapply_data["merge_report"]["applied_changes"]) >= 2
    assert len(reapply_data["merge_report"]["conflicts_skipped"]) == 0

    merged_project = reapply_data["project"]
    # Verify BOTH Admin's v2 change on Entity 1 AND Architect's changes on Entity 0 + DIM_REINSURANCE_TREATY are present!
    assert merged_project["entities"][ent0_key]["description"] == "Architect updated description for entity 0 (non-conflicting)"
    assert merged_project["entities"][ent1_key]["description"] == "Admin emergency update on Entity 1 in v1.0.2"
    entity_names = [e["physical_name"] for e in merged_project["entities"].values()]
    assert "DIM_REINSURANCE_TREATY" in entity_names

    # 12. Architect checks in the merged model as v3!
    final_ci = client.post(
        f"/api/remote-models/{model_id}/checkin",
        headers=arch_headers,
        json={
            "project": merged_project,
            "commit_message": "Checked in re-applied non-conflicting changes on top of v1.0.2",
            "checkout_id": reapply_data["active_checkout_id"],
        },
    )
    assert final_ci.status_code == 200, final_ci.text
    final_data = final_ci.json()
    assert final_data["summary"]["current_version"] == 3
    assert final_data["summary"]["is_locked"] is False


def test_remote_repo_conflict_detection_voluntary_release_and_none_permission(client: TestClient):
    admin_headers = _auth_headers(client, "admin@metaforge.local")
    arch_headers = _auth_headers(client, "architect@metaforge.local")
    viewer_headers = _auth_headers(client, "viewer@metaforge.local")

    create_resp = client.post(
        "/api/remote-models",
        headers=admin_headers,
        json={
            "name": "Conflict & ACL Verification Model",
            "description": "Tests 3-way conflict skipping, voluntary release, and NONE access restriction",
        },
    )
    assert create_resp.status_code == 200
    model_id = create_resp.json()["id"]

    # 1. Set viewer permission to NONE and verify viewer cannot see or view the model
    entries = client.get(f"/api/remote-models/{model_id}/access", headers=admin_headers).json()
    for e in entries:
        if e["user_email"] == "viewer@metaforge.local":
            e["permission"] = "NONE"
        elif e["user_email"] == "architect@metaforge.local":
            e["permission"] = "EDIT"
    client.put(f"/api/remote-models/{model_id}/access", headers=admin_headers, json={"entries": entries})

    viewer_list = client.get("/api/remote-models", headers=viewer_headers).json()
    assert all(m["id"] != model_id for m in viewer_list)
    assert client.get(f"/api/remote-models/{model_id}/view", headers=viewer_headers).status_code == 403

    # 2. Voluntary checkout & release
    co1 = client.post(f"/api/remote-models/{model_id}/checkout", headers=arch_headers)
    assert co1.status_code == 200
    assert co1.json()["summary"]["is_locked"] is True

    rel1 = client.post(f"/api/remote-models/{model_id}/release", headers=arch_headers)
    assert rel1.status_code == 200
    assert rel1.json()["summary"]["is_locked"] is False
    assert rel1.json()["work_mode"] == "view_only"

    # 3. Architect checks out again, edits Entity 0 description (will conflict) AND Entity 1 description (non-conflicting)
    co2 = client.post(f"/api/remote-models/{model_id}/checkout", headers=arch_headers).json()
    arch_draft = copy.deepcopy(co2["project"])
    ent_keys = sorted(arch_draft["entities"].keys())
    e0, e1 = ent_keys[0], ent_keys[1]

    arch_draft["entities"][e0]["description"] = "Architect conflicting description on E0"
    arch_draft["entities"][e1]["description"] = "Architect non-conflicting description on E1"
    client.post(
        f"/api/remote-models/{model_id}/draft",
        headers=arch_headers,
        json={"project": arch_draft, "checkout_id": co2["active_checkout_id"]},
    )

    # Admin force-releases, checks out, edits Entity 0 description differently, and checks in
    client.post(f"/api/remote-models/{model_id}/force-release", headers=admin_headers, json={"reason": "Urgent override"})
    admin_co = client.post(f"/api/remote-models/{model_id}/checkout", headers=admin_headers).json()
    admin_proj = copy.deepcopy(admin_co["project"])
    admin_proj["entities"][e0]["description"] = "Admin authoritative description on E0"
    client.post(
        f"/api/remote-models/{model_id}/checkin",
        headers=admin_headers,
        json={"project": admin_proj, "commit_message": "Admin updated E0", "checkout_id": admin_co["active_checkout_id"]},
    )

    # Architect re-applies: E1 change is automatically applied, E0 conflict is skipped!
    reapply = client.post(
        f"/api/remote-models/{model_id}/reapply",
        headers=arch_headers,
        json={"checkout_id": co2["active_checkout_id"]},
    )
    assert reapply.status_code == 200
    rdata = reapply.json()
    assert len(rdata["merge_report"]["applied_changes"]) == 1
    assert len(rdata["merge_report"]["conflicts_skipped"]) == 1
    assert rdata["project"]["entities"][e0]["description"] == "Admin authoritative description on E0"
    assert rdata["project"]["entities"][e1]["description"] == "Architect non-conflicting description on E1"

