"""Automatic Background SQL Query & DDL Generator for View & Materialized View Entities."""
import re
from typing import List, Tuple
from ..metamodel.schema import EntityModel, ProjectMetamodel, TargetDialect


def _qualify_table(ent: EntityModel, dialect: TargetDialect) -> str:
    if dialect == TargetDialect.SQL_SERVER:
        sch = ent.sql_server_props.schema_name or "dbo"
        return f"[{sch}].[{ent.physical_name.upper()}]"
    if dialect == TargetDialect.ORACLE:
        sch = (ent.oracle_props.schema_name or "CORE_DATA").upper()
        return f"{sch}.{ent.physical_name.upper()}"
    sch = (ent.database_schema or "CORE").upper()
    return f"{sch}.{ent.physical_name.upper()}"


def synthesize_view_select_sql(
    view_entity: EntityModel,
    model: ProjectMetamodel,
    dialect: TargetDialect = TargetDialect.SNOWFLAKE,
) -> str:
    """
    Generate the SELECT query body for a View or Materialized View entity.
    If the user provided custom `view_sql`, returns it; otherwise synthesizes
    a complete SELECT ... FROM ... JOIN ... GROUP BY query from upstream lineage
    relationships and view columns.
    """
    if view_entity.view_sql and view_entity.view_sql.strip():
        return view_entity.view_sql.strip().rstrip(";")

    # Find all upstream entities feeding this view (where view is child_entity_id)
    upstream_rels = [
        r
        for r in model.relationships.values()
        if r.child_entity_id == view_entity.id and r.parent_entity_id in model.entities
    ]
    upstream_entities: List[EntityModel] = []
    for r in upstream_rels:
        p_ent = model.entities[r.parent_entity_id]
        if all(x.id != p_ent.id for x in upstream_entities):
            upstream_entities.append(p_ent)

    # Alias map: e.g. DIM_CUSTOMER -> t1, DIM_POLICY -> t2
    alias_map = {ent.id: f"t{idx + 1}" for idx, ent in enumerate(upstream_entities)}
    phys_to_alias = {
        ent.physical_name.upper(): f"t{idx + 1}"
        for idx, ent in enumerate(upstream_entities)
    }

    select_exprs: List[str] = []
    group_by_candidates: List[str] = []
    has_aggregation = False

    for col in view_entity.columns:
        col_name = col.physical_name.upper()
        expr = (col.source_expression or "").strip()

        if expr:
            # Replace any upstream physical table prefix with its alias if applicable
            resolved_expr = expr
            for phys_tbl, alias in phys_to_alias.items():
                resolved_expr = re.sub(
                    rf"\b{re.escape(phys_tbl)}\.",
                    f"{alias}.",
                    resolved_expr,
                    flags=re.IGNORECASE,
                )
            if re.search(r"\b(SUM|COUNT|AVG|MIN|MAX)\s*\(", resolved_expr, re.IGNORECASE):
                has_aggregation = True
            else:
                group_by_candidates.append(resolved_expr)
            select_exprs.append(f"    {resolved_expr} AS {col_name}")
        else:
            # Auto-resolve column from upstream tables by matching physical_name
            matched_ref = None
            for up_ent in upstream_entities:
                if any(c.physical_name.upper() == col_name for c in up_ent.columns):
                    matched_ref = f"{alias_map[up_ent.id]}.{col_name}"
                    break
            if matched_ref:
                group_by_candidates.append(matched_ref)
                select_exprs.append(f"    {matched_ref} AS {col_name}")
            elif upstream_entities:
                first_alias = alias_map[upstream_entities[0].id]
                group_by_candidates.append(f"{first_alias}.{col_name}")
                select_exprs.append(f"    {first_alias}.{col_name} AS {col_name}")
            else:
                select_exprs.append(f"    NULL AS {col_name}")

    if not select_exprs:
        select_exprs = ["    1 AS DUMMY_COL"]

    lines: List[str] = ["SELECT", ",\n".join(select_exprs)]

    if upstream_entities:
        base_ent = upstream_entities[0]
        base_alias = alias_map[base_ent.id]
        lines.append(f"FROM {_qualify_table(base_ent, dialect)} {base_alias}")

        joined_ids = {base_ent.id}
        for up_ent in upstream_entities[1:]:
            up_alias = alias_map[up_ent.id]
            # Look for a relationship between already-joined entities and up_ent
            join_cond = None
            for rel in model.relationships.values():
                if rel.parent_entity_id in joined_ids and rel.child_entity_id == up_ent.id:
                    p_e = model.entities[rel.parent_entity_id]
                    p_c = next((c for c in p_e.columns if c.id == rel.parent_column_id), None)
                    c_c = next((c for c in up_ent.columns if c.id == rel.child_column_id), None)
                    if p_c and c_c:
                        join_cond = f"{alias_map[p_e.id]}.{p_c.physical_name.upper()} = {up_alias}.{c_c.physical_name.upper()}"
                        break
                elif rel.child_entity_id in joined_ids and rel.parent_entity_id == up_ent.id:
                    c_e = model.entities[rel.child_entity_id]
                    p_c = next((c for c in up_ent.columns if c.id == rel.parent_column_id), None)
                    c_c = next((c for c in c_e.columns if c.id == rel.child_column_id), None)
                    if p_c and c_c:
                        join_cond = f"{alias_map[c_e.id]}.{c_c.physical_name.upper()} = {up_alias}.{p_c.physical_name.upper()}"
                        break

            # Fallback join on matching column name or view relationship
            if not join_cond:
                common_cols = {c.physical_name.upper() for c in base_ent.columns} & {
                    c.physical_name.upper() for c in up_ent.columns
                }
                common_key = next(
                    (k for k in common_cols if k.endswith("_ID") or k.endswith("_KEY")),
                    next(iter(common_cols), "ID"),
                )
                join_cond = f"{base_alias}.{common_key} = {up_alias}.{common_key}"

            lines.append(
                f"LEFT JOIN {_qualify_table(up_ent, dialect)} {up_alias}\n    ON {join_cond}"
            )
            joined_ids.add(up_ent.id)

        if has_aggregation and group_by_candidates:
            lines.append("GROUP BY\n    " + ",\n    ".join(group_by_candidates))

    return "\n".join(lines)


def compile_view_ddl(
    view_entity: EntityModel,
    model: ProjectMetamodel,
    dialect: TargetDialect,
) -> str:
    """Emit dialect-specific CREATE [OR REPLACE] [MATERIALIZED] VIEW DDL."""
    q_name = _qualify_table(view_entity, dialect)
    select_body = synthesize_view_select_sql(view_entity, model, dialect)
    is_mat = view_entity.entity_type == "materialized_view"
    kind_label = "MATERIALIZED VIEW" if is_mat else "VIEW"

    header = [
        f"-- =============================================================================",
        f"-- {kind_label}: {view_entity.logical_name} ({q_name}) | Subject Area: {view_entity.subject_area}",
        f"-- Auto-Synthesized Background SQL from Upstream Lineage & Column Projections",
        f"-- =============================================================================",
    ]

    if dialect == TargetDialect.SNOWFLAKE:
        mat_kw = "MATERIALIZED " if is_mat else ""
        comment_clause = (
            f"\nCOMMENT = '{view_entity.description.replace(chr(39), chr(39)*2)}'"
            if view_entity.description
            else ""
        )
        return (
            "\n".join(header)
            + f"\nCREATE OR REPLACE {mat_kw}VIEW {q_name}{comment_clause}\nAS\n{select_body};"
        )

    if dialect == TargetDialect.SQL_SERVER:
        return (
            "\n".join(header)
            + f"\nCREATE OR ALTER VIEW {q_name}\nAS\n{select_body};\nGO"
        )

    # Oracle
    if is_mat:
        tbs = (view_entity.oracle_props.tablespace or "USERS").upper()
        return (
            "\n".join(header)
            + f"\nCREATE MATERIALIZED VIEW {q_name}\nTABLESPACE {tbs}\nBUILD IMMEDIATE\nREFRESH FORCE ON DEMAND\nAS\n{select_body};"
        )
    return (
        "\n".join(header)
        + f"\nCREATE OR REPLACE FORCE VIEW {q_name}\nAS\n{select_body};"
    )
