"""Snowflake Enterprise DDL Compiler (Tables, Views, Masking Policies & Lifecycle Retention Tasks)."""
from typing import List, Optional
from ..metamodel.schema import EntityModel, ProjectMetamodel, TargetDialect
from .view_builder import compile_view_ddl


def _escape_sql_str(val: str) -> str:
    return val.replace("'", "''")


def compile_snowflake_entity(entity: EntityModel, model: ProjectMetamodel) -> str:
    if getattr(entity, "entity_type", "table") in ("view", "materialized_view"):
        return compile_view_ddl(entity, model, TargetDialect.SNOWFLAKE)

    sf = entity.snowflake_props
    ret = entity.retention_policy
    sla = entity.data_contract
    vol = entity.volumetrics

    transient_kw = "TRANSIENT " if sf.transient else ""
    schema_name = (entity.database_schema or "CORE").upper()
    table_name = entity.physical_name.upper()
    full_name = f"{schema_name}.{table_name}"

    lines: List[str] = []
    lines.append("-- =============================================================================")
    lines.append(
        f"-- Entity: {entity.logical_name} ({full_name}) | Stereotype: {entity.modeling_stereotype}"
    )
    if entity.grain_statement:
        lines.append(f"-- Grain: {entity.grain_statement}")
    lines.append(
        f"-- Governance: Owner={sla.data_owner} | SLA={sla.freshness_sla_hours}h | "
        f"Retention={ret.regulatory_framework} (Hot: {ret.active_retention_days}d, Archive: {ret.archive_retention_days}d, Action: {ret.disposition_action})"
    )
    lines.append(
        f"-- Volumetrics: ~{vol.estimated_row_count:,} rows | Growth: {vol.monthly_growth_pct}%/mo | Est. Size: {vol.estimated_size_gb} GB"
    )
    lines.append("-- =============================================================================")
    lines.append(f"CREATE OR REPLACE {transient_kw}TABLE {full_name} (")

    col_defs: List[str] = []
    pk_cols: List[str] = []

    for col in entity.columns:
        col_name = col.physical_name.upper()
        dtype = col.data_type_snowflake or "VARCHAR(255)"
        parts = [f"    {col_name:<28} {dtype}"]

        if col.is_identity and ("NUMBER" in dtype.upper() or "INT" in dtype.upper()):
            parts.append("IDENTITY(1,1)")
        if not col.is_nullable or col.is_pk:
            parts.append("NOT NULL")
        if col.default_value is not None and str(col.default_value).strip() != "":
            parts.append(f"DEFAULT {col.default_value}")
        if (col.is_unique or col.is_ak) and not col.is_pk:
            parts.append("UNIQUE")
        if col.pii_classification == "RESTRICTED_PII" and "CHAR" in dtype.upper():
            parts.append("WITH MASKING POLICY GOVERNANCE.MASK_RESTRICTED_PII")
        if col.pii_classification != "NONE":
            parts.append(f"WITH TAG (GOVERNANCE.PII_CLASSIFICATION = '{col.pii_classification}')")
        if col.description:
            parts.append(f"COMMENT '{_escape_sql_str(col.description)}'")

        col_defs.append(" ".join(parts))
        if col.is_pk:
            pk_cols.append(col_name)

    if pk_cols:
        pk_list = ", ".join(pk_cols)
        col_defs.append(f"    CONSTRAINT PK_{table_name} PRIMARY KEY ({pk_list}) RELY")

    lines.append(",\n".join(col_defs))
    lines.append(")")

    if sf.cluster_by:
        cluster_expr = ", ".join(c.upper() for c in sf.cluster_by)
        lines.append(f"CLUSTER BY ({cluster_expr})")

    lines.append(f"DATA_RETENTION_TIME_IN_DAYS = {sf.data_retention_days}")

    merged_tags = dict(sf.tags)
    pii_cols = [c.pii_classification for c in entity.columns if c.pii_classification != "NONE"]
    if pii_cols and "PII_CONTAINS" not in merged_tags:
        merged_tags["PII_CONTAINS"] = "TRUE"
    if ret.regulatory_framework != "NONE":
        merged_tags["RETENTION_POLICY"] = f"{ret.regulatory_framework}_{ret.active_retention_days}D"

    if merged_tags:
        tag_pairs = ", ".join(
            f"GOVERNANCE.{k.upper()} = '{_escape_sql_str(v)}'" for k, v in merged_tags.items()
        )
        lines.append(f"WITH TAG ({tag_pairs})")

    if entity.description:
        lines.append(f"COMMENT = '{_escape_sql_str(entity.description)}';")
    else:
        lines[-1] = lines[-1] + ";"

    # Lifecycle Retention & Archival Task generation
    date_col = ret.retention_date_column
    if ret.legal_hold:
        lines.append(
            f"-- [LEGAL HOLD ACTIVE] Lifecycle purge/archival task for {full_name} is suspended by Legal Hold."
        )
    elif date_col and ret.disposition_action != "KEEP_INDEFINITELY":
        lines.append(
            f"-- Automated Lifecycle Governance Task ({ret.regulatory_framework}: {ret.disposition_action} after {ret.active_retention_days} days)"
        )
        if ret.disposition_action == "PURGE_HARD_DELETE":
            lines.append(
                f"CREATE OR REPLACE TASK {schema_name}.TSK_RETENTION_{table_name}\n"
                f"    WAREHOUSE = GOVERNANCE_WH SCHEDULE = 'USING CRON 0 2 * * * UTC'\n"
                f"AS DELETE FROM {full_name} WHERE {date_col} < DATEADD(DAY, -{ret.active_retention_days}, CURRENT_DATE());"
            )
        elif ret.disposition_action == "ARCHIVE_TO_COLD_STORAGE":
            lines.append(
                f"CREATE OR REPLACE TASK {schema_name}.TSK_RETENTION_{table_name}\n"
                f"    WAREHOUSE = GOVERNANCE_WH SCHEDULE = 'USING CRON 0 2 * * * UTC'\n"
                f"AS DELETE FROM {full_name} WHERE {date_col} < DATEADD(DAY, -{ret.archive_retention_days}, CURRENT_DATE());"
            )

    return "\n".join(lines)


def compile_snowflake_ddl(
    model: ProjectMetamodel,
    subject_area: Optional[str] = None,
) -> str:
    """Compile full Snowflake DDL script for the ProjectMetamodel (Tables + Views + Masking + FKs)."""
    header = [
        "-- *****************************************************************************",
        "-- MetaForge Studio - Snowflake Enterprise DDL & Governance Script",
        f"-- Project: {model.name} (v{model.version})",
        "-- Features: TRANSIENT, CLUSTER BY, Dynamic Masking Policies, Lifecycle Retention Tasks, RELY FKs, Views",
        "-- *****************************************************************************",
        "",
        "CREATE MASKING POLICY IF NOT EXISTS GOVERNANCE.MASK_RESTRICTED_PII AS (VAL STRING) RETURNS STRING ->",
        "    CASE WHEN CURRENT_ROLE() IN ('ADMIN', 'DATA_ARCHITECT') THEN VAL ELSE '***-MASKED-PII-***' END;",
        "",
    ]

    entities = [
        e
        for e in model.entities.values()
        if not subject_area or subject_area == "All" or e.subject_area == subject_area
    ]
    entity_ids = {e.id for e in entities}

    blocks: List[str] = []
    for entity in entities:
        blocks.append(compile_snowflake_entity(entity, model))

    fk_statements: List[str] = []
    for rel in model.relationships.values():
        if rel.parent_entity_id not in entity_ids or rel.child_entity_id not in entity_ids:
            continue
        parent_ent = model.entities.get(rel.parent_entity_id)
        child_ent = model.entities.get(rel.child_entity_id)
        if not parent_ent or not child_ent:
            continue

        if (
            rel.rel_type.value == "upstream_lineage"
            or getattr(parent_ent, "entity_type", "table") != "table"
            or getattr(child_ent, "entity_type", "table") != "table"
        ):
            fk_statements.append(
                f"-- [UPSTREAM/DOWNSTREAM LINEAGE] {parent_ent.physical_name.upper()} ---> {child_ent.physical_name.upper()} ({rel.name})"
            )
            continue

        parent_col = next((c for c in parent_ent.columns if c.id == rel.parent_column_id), None)
        child_col = next((c for c in child_ent.columns if c.id == rel.child_column_id), None)
        if not parent_col or not child_col:
            continue

        child_full = f"{(child_ent.database_schema or 'CORE').upper()}.{child_ent.physical_name.upper()}"
        parent_full = f"{(parent_ent.database_schema or 'CORE').upper()}.{parent_ent.physical_name.upper()}"
        fk_name = rel.name.upper()
        rel_label = "IDENTIFYING" if rel.rel_type.value == "identifying" else "NON-IDENTIFYING"

        fk_statements.append(
            f"-- {rel_label} ({rel.cardinality.value})\n"
            f"ALTER TABLE {child_full}\n"
            f"    ADD CONSTRAINT {fk_name}\n"
            f"    FOREIGN KEY ({child_col.physical_name.upper()})\n"
            f"    REFERENCES {parent_full} ({parent_col.physical_name.upper()}) RELY;"
        )

    output = "\n\n".join(header + blocks)
    if fk_statements:
        output += "\n\n-- =============================================================================\n"
        output += "-- Foreign Key Constraints & Upstream/Downstream Lineage\n"
        output += "-- =============================================================================\n"
        output += "\n\n".join(fk_statements) + "\n"
    return output
