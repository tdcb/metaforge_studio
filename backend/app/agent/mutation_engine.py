"""Canonical Metamodel Mutation Engine for AI Agent execution (Gemini + Built-in)."""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..metamodel.schema import (
    Cardinality,
    ColumnModel,
    EntityModel,
    EntityPosition,
    ModelingStereotype,
    ProjectMetamodel,
    RelationshipModel,
    RelationshipType,
)
from ..metamodel.glossary import (
    expand_business_text,
    physical_to_logical_guess,
    sanitize_model_business_text,
)
from ..compilers.dbt_generator import write_dbt_artifacts_to_disk
from ..config import settings


HEADER_PALETTE = [
    "#1e3a8a",  # Deep Blue
    "#065f46",  # Emerald
    "#7c2d12",  # Amber/Rust
    "#581c87",  # Purple
    "#0f766e",  # Teal
    "#831843",  # Pink
    "#1e293b",  # Slate
]


def _humanize(name: str) -> str:
    guess = physical_to_logical_guess(name)
    return expand_business_text(guess)


def _map_data_types(raw_type: str) -> Tuple[str, str, str]:
    t = raw_type.upper().strip()
    if any(k in t for k in ("INT", "NUMBER", "BIGINT", "SERIAL")):
        return ("NUMBER(38,0)", "BIGINT", "NUMBER(38,0)")
    if any(k in t for k in ("DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "MONEY", "AMOUNT")):
        return ("NUMBER(18,2)", "DECIMAL(18,2)", "NUMBER(18,2)")
    if any(k in t for k in ("DATETIME", "TIMESTAMP")):
        return ("TIMESTAMP_NTZ", "DATETIME2(6)", "TIMESTAMP(6)")
    if "DATE" in t:
        return ("DATE", "DATE", "DATE")
    if any(k in t for k in ("BOOL", "BOOLEAN", "FLAG", "IND")):
        return ("BOOLEAN", "BIT", "CHAR(1)")
    if "TEXT" in t:
        return ("VARCHAR(16777216)", "VARCHAR(MAX)", "CLOB")
    # Default to VARCHAR(255)
    return ("VARCHAR(255)", "VARCHAR(255)", "VARCHAR2(255)")


def apply_action(
    model: ProjectMetamodel,
    action: Dict[str, Any],
) -> Optional[str]:
    """Applies a single mutation action to the ProjectMetamodel. Returns a human-readable description of the change."""
    act_type = str(action.get("action", "")).lower().strip()

    # 1. ADD SUBJECT AREA
    if act_type in ("add_subject_area", "create_subject_area"):
        sa = str(action.get("name") or action.get("subject_area") or "").strip()
        if sa and sa not in model.subject_areas:
            model.subject_areas.append(sa)
            return f"Created Subject Area `{sa}`"
        return None

    # 2. ADD TABLE
    if act_type in ("add_table", "create_table"):
        phys = str(action.get("physical_name") or action.get("name") or "").upper().strip()
        if not phys:
            return None
        existing = next((e for e in model.entities.values() if e.physical_name.upper() == phys), None)
        if existing:
            return f"Table `{phys}` already exists (skipped duplicate creation)"

        logic = str(action.get("logical_name") or _humanize(phys))
        sa = str(action.get("subject_area") or (model.subject_areas[0] if model.subject_areas else "Core"))
        if sa not in model.subject_areas:
            model.subject_areas.append(sa)

        ent_id = f"ent-{phys.lower()}-{uuid.uuid4().hex[:4]}"
        ent_count = len(model.entities)
        grid_x = 100.0 + (ent_count % 3) * 440.0
        grid_y = 100.0 + (ent_count // 3) * 380.0

        raw_cols = action.get("columns", [])
        columns: List[ColumnModel] = []
        if not raw_cols:
            # Provide default surrogate PK column
            pk_col = f"{phys.replace('DIM_', '').replace('FCT_', '')}_ID"
            raw_cols = [{"physical_name": pk_col, "logical_name": _humanize(pk_col), "data_type": "NUMBER(38,0)", "is_pk": True}]

        for idx, col_def in enumerate(raw_cols):
            c_phys = str(col_def.get("physical_name") or col_def.get("name") or f"COL_{idx+1}").upper().strip()
            c_logic = str(col_def.get("logical_name") or _humanize(c_phys))
            sf_t, ss_t, ora_t = _map_data_types(str(col_def.get("data_type") or "VARCHAR(255)"))
            is_pk = bool(col_def.get("is_pk", idx == 0))
            is_fk = bool(col_def.get("is_fk", False))
            is_nullable = False if is_pk else bool(col_def.get("is_nullable", True))
            pii = str(col_def.get("pii_classification") or ("RESTRICTED_PII" if any(w in c_phys for w in ("EMAIL", "SSN", "TAX_ID", "PHONE")) else "NONE"))

            columns.append(
                ColumnModel(
                    id=f"col-{phys.lower()}-{c_phys.lower()}-{uuid.uuid4().hex[:4]}",
                    logical_name=c_logic,
                    physical_name=c_phys,
                    data_type_snowflake=sf_t,
                    data_type_sql_server=ss_t,
                    data_type_oracle=ora_t,
                    is_pk=is_pk,
                    is_fk=is_fk,
                    is_nullable=is_nullable,
                    is_unique=is_pk or bool(col_def.get("is_unique", False)),
                    description=str(col_def.get("description") or f"{c_logic} attribute."),
                    pii_classification=pii,
                    dbt_tests=["unique", "not_null"] if is_pk else (["not_null"] if not is_nullable else []),
                )
            )

        color = HEADER_PALETTE[ent_count % len(HEADER_PALETTE)]
        model.entities[ent_id] = EntityModel(
            id=ent_id,
            entity_type="table",
            modeling_stereotype=action.get("modeling_stereotype") or ("FACT_TRANSACTION" if phys.startswith("FCT_") or phys.startswith("FACT_") else "DIM_SCD1"),
            logical_name=logic,
            physical_name=phys,
            database_schema="CORE",
            subject_area=sa,
            description=str(action.get("description") or f"Enterprise {logic} table."),
            header_color=color,
            position=EntityPosition(x=grid_x, y=grid_y),
            columns=columns,
            dbt_materialization="table",
            dbt_layer="mart",
            dbt_unique_key=columns[0].physical_name if columns else None,
        )
        return f"Added Table `{phys}` ({logic}) with {len(columns)} column(s) in Subject Area `{sa}`"

    # 3. MODIFY TABLE
    if act_type in ("modify_table", "alter_table", "update_table"):
        phys = str(action.get("physical_name") or action.get("name") or "").upper().strip()
        target = next((e for e in model.entities.values() if e.physical_name.upper() == phys), None)
        if not target:
            return f"Table `{phys}` not found for modification"

        changes = []
        if action.get("new_physical_name"):
            old = target.physical_name
            target.physical_name = str(action["new_physical_name"]).upper().strip()
            changes.append(f"renamed `{old}` -> `{target.physical_name}`")
        if action.get("new_logical_name"):
            target.logical_name = str(action["new_logical_name"]).strip()
            changes.append(f"logical name updated to `{target.logical_name}`")
        if action.get("new_subject_area"):
            sa = str(action["new_subject_area"]).strip()
            target.subject_area = sa
            if sa not in model.subject_areas:
                model.subject_areas.append(sa)
            changes.append(f"moved to Subject Area `{sa}`")
        if action.get("new_description"):
            target.description = str(action["new_description"]).strip()
            changes.append("description updated")

        # Columns to add
        for c in action.get("columns_to_add", []):
            c_phys = str(c.get("physical_name") or "").upper().strip()
            if not c_phys or any(ex.physical_name.upper() == c_phys for ex in target.columns):
                continue
            sf_t, ss_t, ora_t = _map_data_types(str(c.get("data_type") or "VARCHAR(255)"))
            target.columns.append(
                ColumnModel(
                    id=f"col-{target.physical_name.lower()}-{c_phys.lower()}-{uuid.uuid4().hex[:4]}",
                    logical_name=str(c.get("logical_name") or _humanize(c_phys)),
                    physical_name=c_phys,
                    data_type_snowflake=sf_t,
                    data_type_sql_server=ss_t,
                    data_type_oracle=ora_t,
                    is_pk=bool(c.get("is_pk", False)),
                    is_fk=bool(c.get("is_fk", False)),
                    is_nullable=bool(c.get("is_nullable", True)),
                    description=str(c.get("description") or f"{_humanize(c_phys)} attribute."),
                    pii_classification=str(c.get("pii_classification") or "NONE"),
                    dbt_tests=c.get("dbt_tests", []),
                )
            )
            changes.append(f"added column `{c_phys}`")

        # Columns to drop
        for c_drop in action.get("columns_to_drop", []):
            d_name = str(c_drop).upper().strip()
            target.columns = [col for col in target.columns if col.physical_name.upper() != d_name]
            changes.append(f"dropped column `{d_name}`")

        return f"Modified Table `{phys}`: {', '.join(changes)}" if changes else f"Table `{phys}` inspected (no changes)"

    # 4. DROP TABLE
    if act_type in ("drop_table", "delete_table"):
        phys = str(action.get("physical_name") or action.get("name") or "").upper().strip()
        target = next((e for e in model.entities.values() if e.physical_name.upper() == phys), None)
        if not target:
            return f"Table `{phys}` not found to drop"
        tid = target.id
        del model.entities[tid]
        # Drop cascade relationships
        model.relationships = {
            rid: r for rid, r in model.relationships.items()
            if r.parent_entity_id != tid and r.child_entity_id != tid
        }
        return f"Dropped Table `{phys}` and removed its relationships"

    # 5. ADD COLUMN
    if act_type in ("add_column", "create_column"):
        tbl_name = str(action.get("table_name") or action.get("table") or "").upper().strip()
        target = next((e for e in model.entities.values() if e.physical_name.upper() == tbl_name), None)
        if not target:
            return f"Table `{tbl_name}` not found for column addition"
        c_phys = str(action.get("physical_name") or action.get("name") or "").upper().strip()
        if not c_phys:
            return None
        if any(c.physical_name.upper() == c_phys for c in target.columns):
            return f"Column `{tbl_name}.{c_phys}` already exists"

        sf_t, ss_t, ora_t = _map_data_types(str(action.get("data_type") or "VARCHAR(255)"))
        target.columns.append(
            ColumnModel(
                id=f"col-{tbl_name.lower()}-{c_phys.lower()}-{uuid.uuid4().hex[:4]}",
                logical_name=str(action.get("logical_name") or _humanize(c_phys)),
                physical_name=c_phys,
                data_type_snowflake=sf_t,
                data_type_sql_server=ss_t,
                data_type_oracle=ora_t,
                is_pk=bool(action.get("is_pk", False)),
                is_fk=bool(action.get("is_fk", False)),
                is_nullable=bool(action.get("is_nullable", True)),
                description=str(action.get("description") or f"{_humanize(c_phys)} attribute."),
                pii_classification=str(action.get("pii_classification") or "NONE"),
                dbt_tests=action.get("dbt_tests", []),
            )
        )
        return f"Added column `{c_phys}` to `{tbl_name}` ({sf_t})"

    # 6. MODIFY COLUMN
    if act_type in ("modify_column", "alter_column", "update_column"):
        tbl_name = str(action.get("table_name") or action.get("table") or "").upper().strip()
        target = next((e for e in model.entities.values() if e.physical_name.upper() == tbl_name), None)
        if not target:
            return f"Table `{tbl_name}` not found"
        c_phys = str(action.get("physical_name") or action.get("column_name") or "").upper().strip()
        col = next((c for c in target.columns if c.physical_name.upper() == c_phys), None)
        if not col:
            return f"Column `{tbl_name}.{c_phys}` not found"

        changes = []
        if action.get("new_physical_name"):
            old = col.physical_name
            col.physical_name = str(action["new_physical_name"]).upper().strip()
            changes.append(f"renamed to `{col.physical_name}`")
        if action.get("new_logical_name"):
            col.logical_name = str(action["new_logical_name"]).strip()
            changes.append(f"logical name `{col.logical_name}`")
        if action.get("data_type"):
            sf_t, ss_t, ora_t = _map_data_types(str(action["data_type"]))
            col.data_type_snowflake = sf_t
            col.data_type_sql_server = ss_t
            col.data_type_oracle = ora_t
            changes.append(f"type changed to `{sf_t}`")
        if "is_nullable" in action:
            col.is_nullable = bool(action["is_nullable"])
            changes.append(f"nullable={col.is_nullable}")
        if action.get("description"):
            col.description = str(action["description"]).strip()
            changes.append("updated description")
        if action.get("pii_classification"):
            col.pii_classification = str(action["pii_classification"]).strip()
            changes.append(f"PII={col.pii_classification}")

        return f"Modified `{tbl_name}.{c_phys}`: {', '.join(changes)}" if changes else f"Column `{tbl_name}.{c_phys}` unchanged"

    # 7. DROP COLUMN
    if act_type in ("drop_column", "delete_column"):
        tbl_name = str(action.get("table_name") or action.get("table") or "").upper().strip()
        target = next((e for e in model.entities.values() if e.physical_name.upper() == tbl_name), None)
        if not target:
            return f"Table `{tbl_name}` not found"
        c_phys = str(action.get("physical_name") or action.get("column_name") or "").upper().strip()
        before_len = len(target.columns)
        target.columns = [c for c in target.columns if c.physical_name.upper() != c_phys]
        if len(target.columns) < before_len:
            return f"Dropped column `{tbl_name}.{c_phys}`"
        return f"Column `{tbl_name}.{c_phys}` not found to drop"

    # 8. ADD RELATIONSHIP
    if act_type in ("add_relationship", "create_relationship", "connect_tables"):
        parent_name = str(action.get("parent_table") or action.get("parent") or "").upper().strip()
        child_name = str(action.get("child_table") or action.get("child") or "").upper().strip()
        p_ent = next((e for e in model.entities.values() if e.physical_name.upper() == parent_name), None)
        c_ent = next((e for e in model.entities.values() if e.physical_name.upper() == child_name), None)
        if not p_ent or not c_ent:
            return f"Could not link relationship: parent `{parent_name}` or child `{child_name}` does not exist"

        p_col_name = str(action.get("parent_column") or "").upper().strip()
        p_col = (
            next((c for c in p_ent.columns if c.physical_name.upper() == p_col_name), None)
            or next((c for c in p_ent.columns if c.is_pk), None)
            or (p_ent.columns[0] if p_ent.columns else None)
        )
        if not p_col:
            return f"No primary key or valid column found on parent table `{parent_name}`"

        c_col_name = str(action.get("child_column") or "").upper().strip()
        c_col = next((c for c in c_ent.columns if c.physical_name.upper() == c_col_name), None)
        if not c_col:
            # Check for migrated FK or create one
            c_col = next((c for c in c_ent.columns if c.physical_name.upper() == p_col.physical_name.upper()), None)
            if not c_col:
                c_col = ColumnModel(
                    id=f"col-{c_ent.physical_name.lower()}-{p_col.physical_name.lower()}-{uuid.uuid4().hex[:4]}",
                    logical_name=p_col.logical_name,
                    physical_name=p_col.physical_name,
                    data_type_snowflake=p_col.data_type_snowflake,
                    data_type_sql_server=p_col.data_type_sql_server,
                    data_type_oracle=p_col.data_type_oracle,
                    is_pk=False,
                    is_fk=True,
                    is_nullable=True,
                    description=f"Migrated foreign key referencing {p_ent.physical_name}.{p_col.physical_name}",
                    pii_classification=p_col.pii_classification,
                    dbt_tests=["not_null"],
                )
                c_ent.columns.append(c_col)
            else:
                c_col.is_fk = True

        raw_rel_type = str(action.get("rel_type") or "non_identifying").lower()
        rel_type = RelationshipType.IDENTIFYING if "identifying" in raw_rel_type and "non" not in raw_rel_type else (
            RelationshipType.UPSTREAM_LINEAGE if "lineage" in raw_rel_type or "upstream" in raw_rel_type else RelationshipType.NON_IDENTIFYING
        )
        raw_card = str(action.get("cardinality") or "one_to_many").lower()
        cardinality = Cardinality.ONE_TO_ONE if "one_to_one" in raw_card or "1:1" in raw_card else (
            Cardinality.MANY_TO_MANY if "many_to_many" in raw_card or "m:n" in raw_card else Cardinality.ONE_TO_MANY
        )

        rel_id = f"rel-{uuid.uuid4().hex[:6]}"
        rel_name = str(action.get("name") or f"FK_{c_ent.physical_name}_{p_ent.physical_name}")
        model.relationships[rel_id] = RelationshipModel(
            id=rel_id,
            name=rel_name,
            parent_entity_id=p_ent.id,
            child_entity_id=c_ent.id,
            parent_column_id=p_col.id,
            child_column_id=c_col.id,
            cardinality=cardinality,
            rel_type=rel_type,
            transformation_note=action.get("transformation_note"),
        )
        return f"Created relationship `{rel_name}`: `{p_ent.physical_name}.{p_col.physical_name}` -> `{c_ent.physical_name}.{c_col.physical_name}` [{rel_type.value}, {cardinality.value}]"

    # 9. MODIFY RELATIONSHIP
    if act_type in ("modify_relationship", "alter_relationship"):
        target_name = str(action.get("name") or "").upper().strip()
        rel = next((r for r in model.relationships.values() if r.name.upper() == target_name or r.id == target_name), None)
        if not rel:
            return f"Relationship `{target_name}` not found to modify"
        changes = []
        if action.get("cardinality"):
            c_val = str(action["cardinality"]).lower()
            rel.cardinality = Cardinality.ONE_TO_ONE if "one_to_one" in c_val else Cardinality.ONE_TO_MANY
            changes.append(f"cardinality={rel.cardinality.value}")
        if action.get("rel_type"):
            t_val = str(action["rel_type"]).lower()
            rel.rel_type = RelationshipType.IDENTIFYING if "identifying" in t_val and "non" not in t_val else RelationshipType.NON_IDENTIFYING
            changes.append(f"rel_type={rel.rel_type.value}")
        return f"Modified relationship `{rel.name}`: {', '.join(changes)}"

    # 10. DROP RELATIONSHIP
    if act_type in ("drop_relationship", "delete_relationship"):
        target_name = str(action.get("name") or action.get("id") or "").upper().strip()
        to_del = [rid for rid, r in model.relationships.items() if r.name.upper() == target_name or r.id == target_name]
        for rid in to_del:
            del model.relationships[rid]
        return f"Dropped {len(to_del)} relationship(s) matching `{target_name}`"

    # 11. ADD VIEW
    if act_type in ("add_view", "create_view"):
        phys = str(action.get("physical_name") or action.get("name") or "").upper().strip()
        if not phys:
            return None
        existing = next((e for e in model.entities.values() if e.physical_name.upper() == phys), None)
        if existing:
            return f"View `{phys}` already exists"

        logic = str(action.get("logical_name") or _humanize(phys))
        sa = str(action.get("subject_area") or (model.subject_areas[0] if model.subject_areas else "Core"))
        if sa not in model.subject_areas:
            model.subject_areas.append(sa)

        ent_id = f"ent-vw-{phys.lower()}-{uuid.uuid4().hex[:4]}"
        ent_count = len(model.entities)
        grid_x = 100.0 + (ent_count % 3) * 440.0
        grid_y = 100.0 + (ent_count // 3) * 380.0

        view_sql = str(action.get("view_sql") or action.get("sql") or "").strip()
        raw_cols = action.get("columns", [])
        columns: List[ColumnModel] = []

        # If columns specified, create them
        for idx, col_def in enumerate(raw_cols):
            c_phys = str(col_def.get("physical_name") or col_def.get("name") or f"COL_{idx+1}").upper().strip()
            c_logic = str(col_def.get("logical_name") or _humanize(c_phys))
            sf_t, ss_t, ora_t = _map_data_types(str(col_def.get("data_type") or "VARCHAR(255)"))
            columns.append(
                ColumnModel(
                    id=f"col-{phys.lower()}-{c_phys.lower()}-{uuid.uuid4().hex[:4]}",
                    logical_name=c_logic,
                    physical_name=c_phys,
                    data_type_snowflake=sf_t,
                    data_type_sql_server=ss_t,
                    data_type_oracle=ora_t,
                    is_pk=bool(col_def.get("is_pk", False)),
                    is_fk=False,
                    is_nullable=True,
                    source_expression=str(col_def.get("source_expression") or ""),
                    description=str(col_def.get("description") or f"Projected view column {c_logic}."),
                    pii_classification="NONE",
                )
            )

        if not columns:
            # Add at least 1 placeholder projection column
            columns.append(
                ColumnModel(
                    id=f"col-{phys.lower()}-id-{uuid.uuid4().hex[:4]}",
                    logical_name="View ID",
                    physical_name="ID",
                    data_type_snowflake="NUMBER(38,0)",
                    data_type_sql_server="BIGINT",
                    data_type_oracle="NUMBER(38,0)",
                    is_pk=False,
                    is_fk=False,
                    is_nullable=True,
                    description="View primary projection key",
                    pii_classification="NONE",
                )
            )

        # Default SQL if empty
        if not view_sql:
            view_sql = f"SELECT {', '.join(c.physical_name for c in columns)} FROM CORE.DIM_CUSTOMER"

        mat = str(action.get("materialization") or "view").lower()
        is_mat = "materialized" in mat
        model.entities[ent_id] = EntityModel(
            id=ent_id,
            entity_type="materialized_view" if is_mat else "view",
            modeling_stereotype="ANALYTICAL_VIEW",
            logical_name=logic,
            physical_name=phys,
            database_schema="CORE",
            subject_area=sa,
            description=str(action.get("description") or f"Business analytical view for {logic}."),
            header_color="#6d28d9",  # Purple for views
            position=EntityPosition(x=grid_x, y=grid_y),
            columns=columns,
            view_sql=view_sql,
            dbt_materialization="view",
            dbt_layer="mart",
        )

        # Automatically discover upstream lineage from referenced table names in view_sql
        lineage_count = 0
        sql_upper = view_sql.upper()
        for source_ent in model.entities.values():
            if source_ent.id == ent_id:
                continue
            if source_ent.physical_name.upper() in sql_upper:
                rel_id = f"rel-lineage-{uuid.uuid4().hex[:6]}"
                p_col = next((c for c in source_ent.columns if c.is_pk), source_ent.columns[0] if source_ent.columns else None)
                if p_col:
                    model.relationships[rel_id] = RelationshipModel(
                        id=rel_id,
                        name=f"LINEAGE_{source_ent.physical_name}_TO_{phys}",
                        parent_entity_id=source_ent.id,
                        child_entity_id=ent_id,
                        parent_column_id=p_col.id,
                        child_column_id=columns[0].id,
                        cardinality=Cardinality.ONE_TO_MANY,
                        rel_type=RelationshipType.UPSTREAM_LINEAGE,
                        transformation_note=f"Projected via SQL in {phys}",
                    )
                    lineage_count += 1

        return f"Created View `{phys}` ({logic}) with {len(columns)} column(s) and {lineage_count} upstream lineage relationship(s)"

    # 12. MODIFY VIEW
    if act_type in ("modify_view", "alter_view", "update_view"):
        phys = str(action.get("physical_name") or action.get("name") or "").upper().strip()
        target = next((e for e in model.entities.values() if e.physical_name.upper() == phys and e.entity_type in ("view", "materialized_view")), None)
        if not target:
            return f"View `{phys}` not found to modify"
        changes = []
        if action.get("view_sql"):
            target.view_sql = str(action["view_sql"]).strip()
            changes.append("updated view SQL definition")
        if action.get("new_logical_name"):
            target.logical_name = str(action["new_logical_name"]).strip()
            changes.append(f"logical name `{target.logical_name}`")
        if action.get("new_description"):
            target.description = str(action["new_description"]).strip()
            changes.append("updated description")
        if action.get("materialization"):
            mat = str(action["materialization"]).lower()
            target.entity_type = "materialized_view" if "materialized" in mat else "view"
            changes.append(f"materialization={target.entity_type}")

        return f"Modified View `{phys}`: {', '.join(changes)}" if changes else f"View `{phys}` unchanged"

    # 13. DROP VIEW
    if act_type in ("drop_view", "delete_view"):
        phys = str(action.get("physical_name") or action.get("name") or "").upper().strip()
        target = next((e for e in model.entities.values() if e.physical_name.upper() == phys and e.entity_type in ("view", "materialized_view")), None)
        if not target:
            return f"View `{phys}` not found to drop"
        vid = target.id
        del model.entities[vid]
        model.relationships = {
            rid: r for rid, r in model.relationships.items()
            if r.parent_entity_id != vid and r.child_entity_id != vid
        }
        return f"Dropped View `{phys}`"

    return None


def execute_mutations(
    model: ProjectMetamodel,
    actions: List[Dict[str, Any]],
) -> Tuple[ProjectMetamodel, List[str]]:
    """Applies a sequence of mutation actions and returns (updated_model, actions_taken)."""
    applied: List[str] = []
    for act in actions:
        try:
            msg = apply_action(model, act)
            if msg:
                applied.append(msg)
        except Exception as exc:
            applied.append(f"Failed action {act.get('action')}: {exc}")

    if applied:
        sanitize_model_business_text(model)
        write_dbt_artifacts_to_disk(model, settings.exported_dbt_dir)

    return model, applied
