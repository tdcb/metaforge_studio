"""Complete Compare Engine: Bidirectional Schema Diffing & Safe ALTER Script Generation."""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from ..metamodel.schema import (
    ColumnModel,
    EntityModel,
    ProjectMetamodel,
    TargetDialect,
)
from ..compilers.snowflake import compile_snowflake_entity
from ..compilers.sql_server import compile_sql_server_entity
from ..compilers.oracle import compile_oracle_entity


class ColumnDiffItem(BaseModel):
    table_name: str
    column_name: str
    change_type: str  # ADDED, DROPPED, MODIFIED
    source_type: Optional[str] = None
    target_type: Optional[str] = None
    source_nullable: Optional[bool] = None
    target_nullable: Optional[bool] = None
    details: str


class TableDiffItem(BaseModel):
    table_name: str
    logical_name: str
    change_type: str  # ADDED, DROPPED, MODIFIED
    column_changes: List[ColumnDiffItem] = Field(default_factory=list)


class RelationshipDiffItem(BaseModel):
    relationship_name: str
    parent_table: str
    child_table: str
    child_column: str
    change_type: str  # ADDED, DROPPED


class CompareDiffResult(BaseModel):
    dialect: TargetDialect
    added_tables: List[str] = Field(default_factory=list)
    dropped_tables: List[str] = Field(default_factory=list)
    modified_tables: List[str] = Field(default_factory=list)
    table_diffs: List[TableDiffItem] = Field(default_factory=list)
    column_diffs: List[ColumnDiffItem] = Field(default_factory=list)
    relationship_diffs: List[RelationshipDiffItem] = Field(default_factory=list)
    alter_script: str = ""
    total_differences: int = 0


def _get_col_type_for_dialect(col: ColumnModel, dialect: TargetDialect) -> str:
    if dialect == TargetDialect.SNOWFLAKE:
        return (col.data_type_snowflake or "VARCHAR(255)").upper().strip()
    if dialect == TargetDialect.SQL_SERVER:
        return (col.data_type_sql_server or "NVARCHAR(255)").upper().strip()
    return (col.data_type_oracle or "VARCHAR2(255 CHAR)").upper().strip()


def _format_qualified_table(ent: EntityModel, dialect: TargetDialect) -> str:
    if dialect == TargetDialect.SQL_SERVER:
        sch = ent.sql_server_props.schema_name or "dbo"
        return f"[{sch}].[{ent.physical_name.upper()}]"
    if dialect == TargetDialect.ORACLE:
        sch = (ent.oracle_props.schema_name or "CORE_DATA").upper()
        return f"{sch}.{ent.physical_name.upper()}"
    sch = (ent.database_schema or "CORE").upper()
    return f"{sch}.{ent.physical_name.upper()}"


def run_complete_compare(
    current_model: ProjectMetamodel,
    baseline_model: ProjectMetamodel,
    dialect: TargetDialect = TargetDialect.SNOWFLAKE,
) -> CompareDiffResult:
    """
    Compare `current_model` (desired canvas state) against `baseline_model` (target DB / snapshot)
    and emit structured differences + a non-destructive dialect-specific ALTER migration script.
    """
    curr_tables: Dict[str, EntityModel] = {
        e.physical_name.upper(): e for e in current_model.entities.values()
    }
    base_tables: Dict[str, EntityModel] = {
        e.physical_name.upper(): e for e in baseline_model.entities.values()
    }

    added_tables: List[str] = []
    dropped_tables: List[str] = []
    modified_tables: List[str] = []
    table_diffs: List[TableDiffItem] = []
    column_diffs: List[ColumnDiffItem] = []
    relationship_diffs: List[RelationshipDiffItem] = []
    alter_statements: List[str] = [
        "-- =============================================================================",
        f"-- MetaForge Studio - Complete Compare & Synchronization Script ({dialect.value.upper()})",
        f"-- Source (Desired Canvas): {current_model.name} (v{current_model.version})",
        f"-- Target (Baseline/DB):    {baseline_model.name} (v{baseline_model.version})",
        "-- Policy: Non-destructive ALTER synchronization (Dropped objects commented for safety)",
        "-- =============================================================================",
        "",
    ]

    # 1. Added Tables (present in current_model, absent in baseline_model)
    for tbl_name, curr_ent in curr_tables.items():
        if tbl_name not in base_tables:
            added_tables.append(tbl_name)
            col_items = [
                ColumnDiffItem(
                    table_name=tbl_name,
                    column_name=c.physical_name.upper(),
                    change_type="ADDED",
                    source_type=_get_col_type_for_dialect(c, dialect),
                    target_type=None,
                    source_nullable=c.is_nullable,
                    target_nullable=None,
                    details=f"New column on new table {tbl_name}",
                )
                for c in curr_ent.columns
            ]
            table_diffs.append(
                TableDiffItem(
                    table_name=tbl_name,
                    logical_name=curr_ent.logical_name,
                    change_type="ADDED",
                    column_changes=col_items,
                )
            )
            column_diffs.extend(col_items)

            if dialect == TargetDialect.SNOWFLAKE:
                alter_statements.append(compile_snowflake_entity(curr_ent, current_model))
            elif dialect == TargetDialect.SQL_SERVER:
                alter_statements.append(compile_sql_server_entity(curr_ent))
            else:
                alter_statements.append(compile_oracle_entity(curr_ent))
            alter_statements.append("")

    # 2. Dropped Tables (present in baseline_model, absent in current_model)
    for tbl_name, base_ent in base_tables.items():
        if tbl_name not in curr_tables:
            dropped_tables.append(tbl_name)
            table_diffs.append(
                TableDiffItem(
                    table_name=tbl_name,
                    logical_name=base_ent.logical_name,
                    change_type="DROPPED",
                    column_changes=[],
                )
            )
            q_name = _format_qualified_table(base_ent, dialect)
            alter_statements.append(
                f"-- [SAFEGUARD] Table {tbl_name} was removed from canvas model.\n"
                f"-- Uncomment below after archiving data if physical drop is intended:\n"
                f"-- DROP TABLE {q_name};"
            )
            alter_statements.append("")

    # 3. Common Tables -> Compare Columns
    for tbl_name, curr_ent in curr_tables.items():
        if tbl_name not in base_tables:
            continue
        base_ent = base_tables[tbl_name]
        q_name = _format_qualified_table(curr_ent, dialect)

        curr_cols = {c.physical_name.upper(): c for c in curr_ent.columns}
        base_cols = {c.physical_name.upper(): c for c in base_ent.columns}
        this_table_col_diffs: List[ColumnDiffItem] = []

        # Added Columns
        for col_name, c_col in curr_cols.items():
            if col_name not in base_cols:
                c_type = _get_col_type_for_dialect(c_col, dialect)
                null_str = "NULL" if c_col.is_nullable else "NOT NULL"
                default_clause = (
                    f" DEFAULT {c_col.default_value}"
                    if c_col.default_value
                    else (" DEFAULT ''" if not c_col.is_nullable and "CHAR" in c_type else "")
                )
                diff_item = ColumnDiffItem(
                    table_name=tbl_name,
                    column_name=col_name,
                    change_type="ADDED",
                    source_type=c_type,
                    target_type=None,
                    source_nullable=c_col.is_nullable,
                    target_nullable=None,
                    details=f"Added column {col_name} ({c_type} {null_str})",
                )
                this_table_col_diffs.append(diff_item)
                column_diffs.append(diff_item)

                if dialect == TargetDialect.SNOWFLAKE:
                    alter_statements.append(
                        f"ALTER TABLE {q_name} ADD COLUMN {col_name} {c_type}{default_clause} {null_str};"
                    )
                elif dialect == TargetDialect.SQL_SERVER:
                    alter_statements.append(
                        f"ALTER TABLE {q_name} ADD [{col_name}] {c_type}{default_clause} {null_str};\nGO"
                    )
                else:
                    alter_statements.append(
                        f"ALTER TABLE {q_name} ADD ({col_name} {c_type}{default_clause} {null_str});"
                    )

        # Dropped Columns
        for col_name, b_col in base_cols.items():
            if col_name not in curr_cols:
                b_type = _get_col_type_for_dialect(b_col, dialect)
                diff_item = ColumnDiffItem(
                    table_name=tbl_name,
                    column_name=col_name,
                    change_type="DROPPED",
                    source_type=None,
                    target_type=b_type,
                    source_nullable=None,
                    target_nullable=b_col.is_nullable,
                    details=f"Column {col_name} ({b_type}) removed from canvas model",
                )
                this_table_col_diffs.append(diff_item)
                column_diffs.append(diff_item)

                alter_statements.append(
                    f"-- [SAFEGUARD] Column {tbl_name}.{col_name} removed in model (non-destructive comment):\n"
                    f"-- ALTER TABLE {q_name} DROP COLUMN {col_name};"
                )

        # Modified Columns (type or nullability change)
        for col_name, c_col in curr_cols.items():
            if col_name not in base_cols:
                continue
            b_col = base_cols[col_name]
            c_type = _get_col_type_for_dialect(c_col, dialect)
            b_type = _get_col_type_for_dialect(b_col, dialect)

            type_changed = c_type != b_type
            null_changed = c_col.is_nullable != b_col.is_nullable

            if type_changed or null_changed:
                change_parts: List[str] = []
                if type_changed:
                    change_parts.append(f"Type: {b_type} -> {c_type}")
                if null_changed:
                    change_parts.append(
                        f"Nullable: {b_col.is_nullable} -> {c_col.is_nullable}"
                    )

                diff_item = ColumnDiffItem(
                    table_name=tbl_name,
                    column_name=col_name,
                    change_type="MODIFIED",
                    source_type=c_type,
                    target_type=b_type,
                    source_nullable=c_col.is_nullable,
                    target_nullable=b_col.is_nullable,
                    details="; ".join(change_parts),
                )
                this_table_col_diffs.append(diff_item)
                column_diffs.append(diff_item)

                if dialect == TargetDialect.SNOWFLAKE:
                    if type_changed:
                        alter_statements.append(
                            f"ALTER TABLE {q_name} ALTER COLUMN {col_name} SET DATA TYPE {c_type};"
                        )
                    if null_changed:
                        null_action = "DROP NOT NULL" if c_col.is_nullable else "SET NOT NULL"
                        alter_statements.append(
                            f"ALTER TABLE {q_name} ALTER COLUMN {col_name} {null_action};"
                        )
                elif dialect == TargetDialect.SQL_SERVER:
                    null_kw = "NULL" if c_col.is_nullable else "NOT NULL"
                    alter_statements.append(
                        f"ALTER TABLE {q_name} ALTER COLUMN [{col_name}] {c_type} {null_kw};\nGO"
                    )
                else:
                    null_kw = ""
                    if null_changed:
                        null_kw = " NULL" if c_col.is_nullable else " NOT NULL"
                    alter_statements.append(
                        f"ALTER TABLE {q_name} MODIFY ({col_name} {c_type}{null_kw});"
                    )

        if this_table_col_diffs:
            modified_tables.append(tbl_name)
            table_diffs.append(
                TableDiffItem(
                    table_name=tbl_name,
                    logical_name=curr_ent.logical_name,
                    change_type="MODIFIED",
                    column_changes=this_table_col_diffs,
                )
            )

    # 4. Compare Relationships (by parent_table, child_table, child_col)
    def _rel_Map(m: ProjectMetamodel) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for r in m.relationships.values():
            p_e = m.entities.get(r.parent_entity_id)
            c_e = m.entities.get(r.child_entity_id)
            if not p_e or not c_e:
                continue
            p_c = next((c for c in p_e.columns if c.id == r.parent_column_id), None)
            c_c = next((c for c in c_e.columns if c.id == r.child_column_id), None)
            if not p_c or not c_c:
                continue
            key = f"{p_e.physical_name.upper()}->{c_e.physical_name.upper()}.{c_c.physical_name.upper()}"
            out[key] = (r, p_e, c_e, p_c, c_c)
        return out

    curr_rels = _rel_Map(current_model)
    base_rels = _rel_Map(baseline_model)

    for key, (r, p_e, c_e, p_c, c_c) in curr_rels.items():
        if key not in base_rels:
            relationship_diffs.append(
                RelationshipDiffItem(
                    relationship_name=r.name.upper(),
                    parent_table=p_e.physical_name.upper(),
                    child_table=c_e.physical_name.upper(),
                    child_column=c_c.physical_name.upper(),
                    change_type="ADDED",
                )
            )
            c_q = _format_qualified_table(c_e, dialect)
            p_q = _format_qualified_table(p_e, dialect)
            rely_sfx = " RELY" if dialect == TargetDialect.SNOWFLAKE else ""
            alter_statements.append(
                f"ALTER TABLE {c_q} ADD CONSTRAINT {r.name.upper()} "
                f"FOREIGN KEY ({c_c.physical_name.upper()}) "
                f"REFERENCES {p_q} ({p_c.physical_name.upper()}){rely_sfx};"
            )

    for key, (r, p_e, c_e, p_c, c_c) in base_rels.items():
        if key not in curr_rels:
            relationship_diffs.append(
                RelationshipDiffItem(
                    relationship_name=r.name.upper(),
                    parent_table=p_e.physical_name.upper(),
                    child_table=c_e.physical_name.upper(),
                    child_column=c_c.physical_name.upper(),
                    change_type="DROPPED",
                )
            )
            c_q = _format_qualified_table(c_e, dialect)
            alter_statements.append(
                f"ALTER TABLE {c_q} DROP CONSTRAINT {r.name.upper()};"
            )

    total_diffs = (
        len(added_tables)
        + len(dropped_tables)
        + len(column_diffs)
        + len(relationship_diffs)
    )
    if total_diffs == 0:
        alter_statements.append("-- No schema differences detected. Target is 100% synchronized with Canvas Model.")

    return CompareDiffResult(
        dialect=dialect,
        added_tables=added_tables,
        dropped_tables=dropped_tables,
        modified_tables=modified_tables,
        table_diffs=table_diffs,
        column_diffs=column_diffs,
        relationship_diffs=relationship_diffs,
        alter_script="\n".join(alter_statements),
        total_differences=total_diffs,
    )
