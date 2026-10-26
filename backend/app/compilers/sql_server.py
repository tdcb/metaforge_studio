"""Microsoft SQL Server (T-SQL) Enterprise DDL Compiler (Tables, Views, Dynamic Masking & Extended Properties)."""
from typing import List, Optional
from ..metamodel.schema import EntityModel, ProjectMetamodel, TargetDialect
from .view_builder import compile_view_ddl


def _escape_tsql(val: str) -> str:
    return val.replace("'", "''")


def compile_sql_server_entity(entity: EntityModel, model: Optional[ProjectMetamodel] = None) -> str:
    if getattr(entity, "entity_type", "table") in ("view", "materialized_view") and model is not None:
        return compile_view_ddl(entity, model, TargetDialect.SQL_SERVER)

    ss = entity.sql_server_props
    ret = entity.retention_policy
    schema_name = ss.schema_name or "dbo"
    table_name = entity.physical_name.upper()
    filegroup = ss.filegroup or "PRIMARY"
    full_name = f"[{schema_name}].[{table_name}]"

    lines: List[str] = []
    lines.append("-- =============================================================================")
    lines.append(
        f"-- Entity: {entity.logical_name} ({full_name}) | Filegroup: [{filegroup}] | Stereotype: {entity.modeling_stereotype}"
    )
    lines.append(
        f"-- Retention: {ret.regulatory_framework} (Hot: {ret.active_retention_days}d, Archive: {ret.archive_retention_days}d)"
    )
    lines.append("-- =============================================================================")
    lines.append(f"CREATE TABLE {full_name} (")

    col_defs: List[str] = []
    pk_cols: List[str] = []

    for col in entity.columns:
        col_name = col.physical_name.upper()
        dtype = col.data_type_sql_server or "NVARCHAR(255)"
        parts = [f"    [{col_name}] {dtype}"]

        if col.is_identity and any(
            k in dtype.upper() for k in ("INT", "BIGINT", "SMALLINT", "NUMERIC", "DECIMAL")
        ):
            parts.append("IDENTITY(1,1)")
        if col.pii_classification == "RESTRICTED_PII" and not col.is_pk:
            parts.append("MASKED WITH (FUNCTION = 'default()')")
        if not col.is_nullable or col.is_pk:
            parts.append("NOT NULL")
        else:
            parts.append("NULL")

        if col.default_value is not None and str(col.default_value).strip() != "":
            parts.append(f"CONSTRAINT [DF_{table_name}_{col_name}] DEFAULT ({col.default_value})")
        if (col.is_unique or col.is_ak) and not col.is_pk:
            parts.append(f"CONSTRAINT [UQ_{table_name}_{col_name}] UNIQUE")
        if col.check_constraint:
            parts.append(f"CONSTRAINT [CK_{table_name}_{col_name}] CHECK ({col.check_constraint})")

        col_defs.append(" ".join(parts))
        if col.is_pk:
            pk_cols.append(f"[{col_name}]")

    if ss.system_versioned_temporal:
        col_defs.append("    [SysStartTime] DATETIME2(7) GENERATED ALWAYS AS ROW START NOT NULL")
        col_defs.append("    [SysEndTime] DATETIME2(7) GENERATED ALWAYS AS ROW END NOT NULL")
        col_defs.append("    PERIOD FOR SYSTEM_TIME ([SysStartTime], [SysEndTime])")

    if pk_cols and not ss.clustered_columnstore:
        pk_expr = ", ".join(pk_cols)
        col_defs.append(
            f"    CONSTRAINT [PK_{table_name}] PRIMARY KEY CLUSTERED ({pk_expr}) ON [{filegroup}]"
        )
    elif pk_cols and ss.clustered_columnstore:
        pk_expr = ", ".join(pk_cols)
        col_defs.append(
            f"    CONSTRAINT [PK_{table_name}] PRIMARY KEY NONCLUSTERED ({pk_expr}) ON [{filegroup}]"
        )

    lines.append(",\n".join(col_defs))

    if ss.system_versioned_temporal:
        lines.append(
            f") ON [{filegroup}]\nWITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = [{schema_name}].[{table_name}_HISTORY]));"
        )
    else:
        lines.append(f") ON [{filegroup}];")
    lines.append("GO")

    if ss.clustered_columnstore:
        lines.append("")
        lines.append(
            f"CREATE CLUSTERED COLUMNSTORE INDEX [CCI_{table_name}] ON {full_name} ON [{filegroup}];"
        )
        lines.append("GO")

    if entity.description:
        lines.append("")
        lines.append(
            f"EXEC sys.sp_addextendedproperty "
            f"@name=N'MS_Description', @value=N'{_escape_tsql(entity.description)}', "
            f"@level0type=N'SCHEMA', @level0name=N'{_escape_tsql(schema_name)}', "
            f"@level1type=N'TABLE', @level1name=N'{_escape_tsql(table_name)}';"
        )
        lines.append("GO")

    for col in entity.columns:
        col_name = col.physical_name.upper()
        if col.description:
            lines.append(
                f"EXEC sys.sp_addextendedproperty "
                f"@name=N'MS_Description', @value=N'{_escape_tsql(col.description)}', "
                f"@level0type=N'SCHEMA', @level0name=N'{_escape_tsql(schema_name)}', "
                f"@level1type=N'TABLE', @level1name=N'{_escape_tsql(table_name)}', "
                f"@level2type=N'COLUMN', @level2name=N'{_escape_tsql(col_name)}';"
            )
            lines.append("GO")
        if col.pii_classification != "NONE":
            lines.append(
                f"EXEC sys.sp_addextendedproperty "
                f"@name=N'PII_Classification', @value=N'{col.pii_classification}', "
                f"@level0type=N'SCHEMA', @level0name=N'{_escape_tsql(schema_name)}', "
                f"@level1type=N'TABLE', @level1name=N'{_escape_tsql(table_name)}', "
                f"@level2type=N'COLUMN', @level2name=N'{_escape_tsql(col_name)}';"
            )
            lines.append("GO")

    return "\n".join(lines)


def compile_sql_server_ddl(
    model: ProjectMetamodel,
    subject_area: Optional[str] = None,
) -> str:
    """Compile full Microsoft SQL Server T-SQL script for the ProjectMetamodel."""
    header = [
        "-- *****************************************************************************",
        "-- MetaForge Studio - Microsoft SQL Server (T-SQL) Enterprise DDL",
        f"-- Project: {model.name} (v{model.version})",
        "-- Features: FILEGROUP placement, IDENTITY, Dynamic Data Masking, COLUMNSTORE, SYSTEM_VERSIONING, Views",
        "-- *****************************************************************************",
        "",
    ]

    entities = [
        e
        for e in model.entities.values()
        if not subject_area or subject_area == "All" or e.subject_area == subject_area
    ]
    entity_ids = {e.id for e in entities}

    blocks = [compile_sql_server_entity(ent, model) for ent in entities]

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

        c_schema = child_ent.sql_server_props.schema_name or "dbo"
        p_schema = parent_ent.sql_server_props.schema_name or "dbo"
        fk_name = rel.name.upper()

        fk_statements.append(
            f"ALTER TABLE [{c_schema}].[{child_ent.physical_name.upper()}] WITH CHECK\n"
            f"    ADD CONSTRAINT [{fk_name}] FOREIGN KEY ([{child_col.physical_name.upper()}])\n"
            f"    REFERENCES [{p_schema}].[{parent_ent.physical_name.upper()}] ([{parent_col.physical_name.upper()}]);\n"
            f"GO"
        )

    output = "\n\n".join(header + blocks)
    if fk_statements:
        output += "\n\n-- =============================================================================\n"
        output += "-- Foreign Key Constraints & Upstream/Downstream Lineage\n"
        output += "-- =============================================================================\n"
        output += "\n\n".join(fk_statements) + "\n"
    return output
