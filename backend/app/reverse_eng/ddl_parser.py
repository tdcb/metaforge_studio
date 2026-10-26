"""SQLGlot AST Parser: Reverse-Engineers Tables AND Complex Views (CTEs, JOINs, Aggregations, Window Functions) into Canonical Metamodel + Upstream Lineage."""
import re
import uuid
from typing import Dict, List, Optional, Set, Tuple
import sqlglot
from sqlglot import exp

from ..metamodel.schema import (
    Cardinality,
    ColumnModel,
    EntityModel,
    EntityPosition,
    RelationshipModel,
    RelationshipType,
    TargetDialect,
)


HEADER_PALETTE = [
    "#2563eb",
    "#0d9488",
    "#7c3aed",
    "#d97706",
    "#dc2626",
    "#059669",
    "#4f46e5",
    "#db2777",
]


from ..metamodel.glossary import expand_business_text, physical_to_logical_guess


def _humanize_identifier(phys_name: str) -> str:
    """Convert an UPPER_SNAKE_CASE physical name into a clean, authoritative business Logical Name without abbreviations."""
    guess = physical_to_logical_guess(phys_name)
    return expand_business_text(guess)


def _map_cross_dialect_types(raw_type: str) -> Tuple[str, str, str]:
    up = raw_type.upper().strip()
    m_varchar = re.match(
        r"^(?:N?VARCHAR2?|CHAR|TEXT|STRING)\s*(?:\(\s*(\d+)(?:\s*(?:CHAR|BYTE))?\s*\))?",
        up,
    )
    if m_varchar:
        length = m_varchar.group(1) or "255"
        return (f"VARCHAR({length})", f"NVARCHAR({length})", f"VARCHAR2({length} CHAR)")

    m_num = re.match(
        r"^(?:NUMBER|NUMERIC|DECIMAL|DEC)\s*(?:\(\s*(\d+)\s*(?:,\s*(\d+))?\s*\))?",
        up,
    )
    if m_num:
        prec = m_num.group(1) or "18"
        scale = m_num.group(2)
        if scale and int(scale) > 0:
            return (
                f"NUMBER({prec},{scale})",
                f"DECIMAL({prec},{scale})",
                f"NUMBER({prec},{scale})",
            )
        p_int = int(prec)
        if p_int >= 19:
            return ("NUMBER(38,0)", "BIGINT", "NUMBER(19,0)")
        return (f"NUMBER({prec},0)", "INT", f"NUMBER({prec},0)")

    if any(k in up for k in ("BIGINT", "INT8")):
        return ("NUMBER(38,0)", "BIGINT", "NUMBER(19,0)")
    if any(k in up for k in ("INT", "INTEGER", "SMALLINT", "TINYINT")):
        return ("NUMBER(10,0)", "INT", "NUMBER(10,0)")
    if "DATE" == up:
        return ("DATE", "DATE", "DATE")
    if any(k in up for k in ("TIMESTAMP", "DATETIME", "DATETIME2")):
        return ("TIMESTAMP_NTZ(9)", "DATETIME2(7)", "TIMESTAMP(6)")
    if any(k in up for k in ("BOOL", "BIT")):
        return ("BOOLEAN", "BIT", "NUMBER(1,0)")
    if any(k in up for k in ("FLOAT", "DOUBLE", "REAL")):
        return ("FLOAT", "FLOAT", "BINARY_DOUBLE")

    return (up or "VARCHAR(255)", up or "NVARCHAR(255)", up or "VARCHAR2(255 CHAR)")


def _infer_view_expr_types(expr_sql: str, alias_name: str) -> Tuple[str, str, str]:
    """Infer cross-dialect types for a complex SELECT projection expression."""
    up_expr = expr_sql.upper()
    up_alias = alias_name.upper()
    if any(fn in up_expr for fn in ("SUM(", "AVG(", "ROUND(")) or up_alias.endswith("_AMT"):
        return ("NUMBER(18,2)", "DECIMAL(18,2)", "NUMBER(18,2)")
    if any(fn in up_expr for fn in ("COUNT(", "ROW_NUMBER(", "RANK(", "DENSE_RANK(")) or up_alias.endswith(("_ID", "_CNT", "_QTY")):
        return ("NUMBER(38,0)", "BIGINT", "NUMBER(19,0)")
    if up_alias.endswith("_DT") or "TO_DATE(" in up_expr or "CAST(" in up_expr and "DATE" in up_expr:
        return ("DATE", "DATE", "DATE")
    if up_alias.endswith("_TS") or "TIMESTAMP" in up_expr or "GETDATE(" in up_expr or "SYSDATE" in up_expr:
        return ("TIMESTAMP_NTZ(9)", "DATETIME2(7)", "TIMESTAMP(6)")
    return ("VARCHAR(255)", "NVARCHAR(255)", "VARCHAR2(255 CHAR)")


def _preprocess_ddl_for_sqlglot(ddl: str, dialect: TargetDialect) -> str:
    cleaned = re.sub(r"(?im)^\s*GO\s*$", ";", ddl)
    cleaned = re.sub(r"(?i)\bWITH\s+TAG\s*\([^)]*\)", "", cleaned)
    cleaned = re.sub(r"(?i)\b(?:NO)?RELY\b", "", cleaned)
    cleaned = re.sub(r"(?i),\s*PERIOD\s+FOR\s+SYSTEM_TIME\s*\([^)]*\)", "", cleaned)
    cleaned = re.sub(
        r"(?i)\bGENERATED\s+ALWAYS\s+AS\s+ROW\s+(?:START|END)", "", cleaned
    )
    cleaned = re.sub(
        r"(?i)\bON\s+\[?[A-Za-z0-9_]+\]?(?=\s*(?:;|WITH|\)))", "", cleaned
    )
    cleaned = re.sub(
        r"(?i)\bWITH\s*\(\s*SYSTEM_VERSIONING\s*=\s*ON\s*\([^)]*\)\s*\)",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\bUSING\s+INDEX\s+TABLESPACE\s+[A-Za-z0-9_]+", "", cleaned
    )
    return cleaned


def parse_ddl_to_metamodel(
    ddl_script: str,
    dialect: TargetDialect = TargetDialect.SNOWFLAKE,
    default_subject_area: str = "Core",
    existing_entities: Optional[Dict[str, EntityModel]] = None,
) -> Tuple[List[EntityModel], List[RelationshipModel]]:
    """
    Reverse-engineer raw DDL SQL (Tables AND Complex Views with CTEs, JOINs, Aggregations,
    Window Functions) using SQLGlot AST into EntityModel and RelationshipModel objects.
    """
    sqlglot_dialect_map = {
        TargetDialect.SNOWFLAKE: "snowflake",
        TargetDialect.SQL_SERVER: "tsql",
        TargetDialect.ORACLE: "oracle",
    }
    sg_dialect = sqlglot_dialect_map.get(dialect, "snowflake")
    cleaned_sql = _preprocess_ddl_for_sqlglot(ddl_script, dialect)

    entities_by_name: Dict[str, EntityModel] = {}
    if existing_entities:
        for ent in existing_entities.values():
            entities_by_name[ent.physical_name.upper()] = ent

    newly_parsed_names: List[str] = []
    pending_fks: List[Dict[str, str]] = []
    pending_lineage: List[Dict[str, str]] = []

    try:
        statements = sqlglot.parse(
            cleaned_sql, read=sg_dialect, error_level=sqlglot.ErrorLevel.IGNORE
        )
    except Exception:
        statements = []

    for stmt in statements:
        if stmt is None or not isinstance(stmt, exp.Create):
            continue

        kind = str(stmt.args.get("kind", "")).upper()

        # ---------------------------------------------------------------------
        # CASE A: CREATE TABLE
        # ---------------------------------------------------------------------
        if kind == "TABLE":
            this_node = stmt.this
            table_expr = (
                this_node.this if isinstance(this_node, exp.Schema) else this_node
            )
            if not isinstance(table_expr, exp.Table):
                table_expr = stmt.find(exp.Table)
            if not table_expr:
                continue

            phys_table = table_expr.name.upper().strip('[]"')
            schema_name = (table_expr.db or "CORE").upper().strip('[]"')

            ent_id = f"ent-{phys_table.lower()}-{uuid.uuid4().hex[:6]}"
            columns: List[ColumnModel] = []
            table_pk_cols: Set[str] = set()

            if isinstance(this_node, exp.Schema):

                def _collect_fk(fk_node: exp.ForeignKey, constraint_name: str) -> None:
                    fk_cols = [
                        c.name.upper().strip('[]"') for c in fk_node.expressions
                    ]
                    ref = fk_node.args.get("reference")
                    if not (ref and fk_cols):
                        return
                    ref_tbl = ref.find(exp.Table)
                    ref_cols = (
                        [c.name.upper().strip('[]"') for c in ref.this.expressions]
                        if hasattr(ref.this, "expressions")
                        else []
                    )
                    if ref_tbl and ref_cols:
                        parent_tbl = ref_tbl.name.upper().strip('[]"')
                        pending_fks.append(
                            {
                                "name": constraint_name
                                or f"FK_{phys_table}_{parent_tbl}_{fk_cols[0]}",
                                "child_table": phys_table,
                                "child_col": fk_cols[0],
                                "parent_table": parent_tbl,
                                "parent_col": ref_cols[0],
                            }
                        )

                for expr_item in this_node.expressions:
                    if isinstance(expr_item, exp.Constraint):
                        for sub in expr_item.expressions:
                            if isinstance(sub, exp.PrimaryKey):
                                for pk_c in sub.expressions:
                                    table_pk_cols.add(pk_c.name.upper().strip('[]"'))
                            elif isinstance(sub, exp.ForeignKey):
                                _collect_fk(sub, expr_item.name)
                    elif isinstance(expr_item, exp.ForeignKey):
                        # Unnamed table-level "FOREIGN KEY (...) REFERENCES ..." clause
                        _collect_fk(expr_item, "")
                    elif isinstance(expr_item, exp.PrimaryKey):
                        for pk_c in expr_item.expressions:
                            table_pk_cols.add(pk_c.name.upper().strip('[]"'))

                for expr_item in this_node.expressions:
                    if not isinstance(expr_item, exp.ColumnDef):
                        continue
                    col_phys = expr_item.name.upper().strip('[]"')
                    if col_phys in ("SYSSTARTTIME", "SYSENDTIME"):
                        continue

                    kind_node = expr_item.args.get("kind")
                    raw_dtype = (
                        kind_node.sql(dialect=sg_dialect)
                        if kind_node
                        else "VARCHAR(255)"
                    )
                    sf_t, ss_t, ora_t = _map_cross_dialect_types(raw_dtype)

                    is_pk = col_phys in table_pk_cols
                    is_nullable = True
                    is_unique = False
                    is_identity = False
                    default_val: Optional[str] = None
                    col_comment = ""

                    for constraint in expr_item.args.get("constraints", []):
                        c_kind = constraint.kind
                        if isinstance(c_kind, exp.PrimaryKeyColumnConstraint):
                            is_pk = True
                            is_nullable = False
                        elif isinstance(c_kind, exp.NotNullColumnConstraint):
                            is_nullable = False
                        elif isinstance(c_kind, exp.UniqueColumnConstraint):
                            is_unique = True
                        elif isinstance(
                            c_kind, exp.GeneratedAsIdentityColumnConstraint
                        ):
                            is_identity = True
                        elif isinstance(c_kind, exp.DefaultColumnConstraint):
                            default_val = (
                                c_kind.this.sql(dialect=sg_dialect)
                                if c_kind.this
                                else None
                            )
                        elif isinstance(c_kind, exp.CommentColumnConstraint):
                            col_comment = c_kind.this.name if c_kind.this else ""

                    if is_pk:
                        is_nullable = False

                    dbt_tests = []
                    if is_pk:
                        dbt_tests = ["unique", "not_null"]
                    elif not is_nullable:
                        dbt_tests = ["not_null"]

                    pii_level = "NONE"
                    if any(
                        w in col_phys
                        for w in ("SSN", "TAX_ID", "EMAIL", "PHONE", "FULL_NM", "BIRTH")
                    ):
                        pii_level = "RESTRICTED_PII"
                    elif any(
                        w in col_phys for w in ("AMT", "SALARY", "PREM", "BAL")
                    ):
                        pii_level = "CONFIDENTIAL"

                    columns.append(
                        ColumnModel(
                            id=f"col-{phys_table.lower()}-{col_phys.lower()}-{uuid.uuid4().hex[:4]}",
                            logical_name=_humanize_identifier(col_phys),
                            physical_name=col_phys,
                            data_type_snowflake=sf_t,
                            data_type_sql_server=ss_t,
                            data_type_oracle=ora_t,
                            is_pk=is_pk,
                            is_fk=False,
                            is_nullable=is_nullable,
                            is_unique=is_unique or is_pk,
                            is_identity=is_identity,
                            default_value=default_val,
                            description=col_comment,
                            pii_classification=pii_level,
                            dbt_tests=dbt_tests,
                        )
                    )

            col_idx = len(newly_parsed_names)
            grid_x = 120.0 + (col_idx % 3) * 440.0
            grid_y = 120.0 + (col_idx // 3) * 380.0

            dbt_layer = "mart"
            if phys_table.startswith("STG_"):
                dbt_layer = "staging"
            elif phys_table.startswith("RAW_"):
                dbt_layer = "source"

            new_ent = EntityModel(
                id=ent_id,
                entity_type="table",
                logical_name=_humanize_identifier(phys_table),
                physical_name=phys_table,
                database_schema=schema_name,
                subject_area=default_subject_area,
                description=f"Reverse-engineered Table from {dialect.value} DDL",
                header_color=HEADER_PALETTE[col_idx % len(HEADER_PALETTE)],
                position=EntityPosition(x=grid_x, y=grid_y),
                columns=columns,
                dbt_materialization="view" if dbt_layer == "staging" else "table",
                dbt_layer=dbt_layer,
            )
            entities_by_name[phys_table] = new_ent
            newly_parsed_names.append(phys_table)

        # ---------------------------------------------------------------------
        # CASE B: CREATE [OR REPLACE] [MATERIALIZED] VIEW (Complex Views with CTEs/JOINs/Aggregations)
        # ---------------------------------------------------------------------
        elif "VIEW" in kind:
            this_node = stmt.this
            table_expr = (
                this_node.this if isinstance(this_node, exp.Schema) else this_node
            )
            if not isinstance(table_expr, exp.Table):
                table_expr = stmt.find(exp.Table)
            if not table_expr:
                continue

            phys_view = table_expr.name.upper().strip('[]"')
            schema_name = (table_expr.db or "CORE").upper().strip('[]"')
            is_materialized = "MATERIALIZED" in kind or bool(
                re.search(r"\bMATERIALIZED\s+VIEW\b", stmt.sql(dialect=sg_dialect), re.IGNORECASE)
            )

            # Extract the query AST (stmt.expression)
            query_expr = stmt.expression
            view_select_sql = (
                query_expr.sql(dialect=sg_dialect, pretty=True)
                if query_expr
                else stmt.sql(dialect=sg_dialect)
            )

            # Identify internal CTE names so we don't treat CTE aliases as external upstream tables
            cte_names: Set[str] = set()
            if query_expr:
                for cte in query_expr.find_all(exp.CTE):
                    alias_id = cte.alias
                    if alias_id:
                        cte_names.add(alias_id.upper().strip('[]"'))

            # Collect all upstream physical tables referenced in FROM / JOIN
            upstream_tables: List[str] = []
            if query_expr:
                for tbl in query_expr.find_all(exp.Table):
                    t_name = tbl.name.upper().strip('[]"')
                    if t_name and t_name != phys_view and t_name not in cte_names:
                        if t_name not in upstream_tables:
                            upstream_tables.append(t_name)

            # Extract projected columns from the outermost SELECT
            outer_select: Optional[exp.Select] = None
            if isinstance(query_expr, exp.Select):
                outer_select = query_expr
            elif query_expr:
                # For UNION or parenthesized queries, grab the last/top Select
                selects = list(query_expr.find_all(exp.Select))
                if selects:
                    outer_select = selects[0]

            view_columns: List[ColumnModel] = []
            if outer_select:
                for proj_idx, proj in enumerate(outer_select.expressions):
                    raw_expr_sql = proj.sql(dialect=sg_dialect)
                    alias_name = proj.alias_or_name.upper().strip('[]"')
                    if not alias_name or alias_name == "*":
                        alias_name = f"VIEW_COL_{proj_idx + 1}"

                    # Extract underlying source expression (without AS alias)
                    source_expr = (
                        proj.this.sql(dialect=sg_dialect)
                        if isinstance(proj, exp.Alias) and proj.this
                        else raw_expr_sql
                    )
                    sf_t, ss_t, ora_t = _infer_view_expr_types(source_expr, alias_name)

                    # Check if an upstream table has a column with the same physical_name to inherit its exact types & PII
                    pii_class = "NONE"
                    for up_t in upstream_tables:
                        up_ent = entities_by_name.get(up_t)
                        if up_ent:
                            matched_c = next(
                                (c for c in up_ent.columns if c.physical_name.upper() == alias_name),
                                None,
                            )
                            if matched_c:
                                sf_t = matched_c.data_type_snowflake
                                ss_t = matched_c.data_type_sql_server
                                ora_t = matched_c.data_type_oracle
                                pii_class = matched_c.pii_classification
                                break

                    view_columns.append(
                        ColumnModel(
                            id=f"col-{phys_view.lower()}-{alias_name.lower()}-{uuid.uuid4().hex[:4]}",
                            logical_name=_humanize_identifier(alias_name),
                            physical_name=alias_name,
                            data_type_snowflake=sf_t,
                            data_type_sql_server=ss_t,
                            data_type_oracle=ora_t,
                            is_pk=False,
                            is_fk=False,
                            is_nullable=True,
                            source_expression=source_expr,
                            description=f"Projected view expression: {source_expr}",
                            pii_classification=pii_class,
                        )
                    )

            col_idx = len(newly_parsed_names)
            view_ent = EntityModel(
                id=f"ent-{phys_view.lower()}-{uuid.uuid4().hex[:6]}",
                entity_type="materialized_view" if is_materialized else "view",
                logical_name=_humanize_identifier(phys_view),
                physical_name=phys_view,
                database_schema=schema_name,
                subject_area=default_subject_area,
                description=f"Reverse-engineered {'Materialized ' if is_materialized else ''}View parsed via SQLGlot AST ({len(upstream_tables)} upstream source tables)",
                header_color="#0891b2",
                position=EntityPosition(
                    x=160.0 + (col_idx % 3) * 440.0,
                    y=220.0 + (col_idx // 3) * 380.0,
                ),
                columns=view_columns,
                view_sql=view_select_sql,
                dbt_materialization="table" if is_materialized else "view",
                dbt_layer="mart",
            )
            entities_by_name[phys_view] = view_ent
            newly_parsed_names.append(phys_view)

            for up_t in upstream_tables:
                pending_lineage.append(
                    {
                        "upstream_table": up_t,
                        "downstream_view": phys_view,
                    }
                )

    # Also regex-scan for ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ... REFERENCES ...
    fk_regex = re.compile(
        r"ALTER\s+TABLE\s+(?:[A-Za-z0-9_\[\]\"]+\.)?([A-Za-z0-9_\[\]\"]+)\s+"
        r"(?:WITH\s+CHECK\s+)?ADD\s+(?:CONSTRAINT\s+([A-Za-z0-9_\[\]\"]+)\s+)?"
        r"FOREIGN\s+KEY\s*\(\s*([A-Za-z0-9_\[\]\"]+)\s*\)\s*"
        r"REFERENCES\s+(?:[A-Za-z0-9_\[\]\"]+\.)?([A-Za-z0-9_\[\]\"]+)\s*\(\s*([A-Za-z0-9_\[\]\"]+)\s*\)",
        re.IGNORECASE,
    )
    for match in fk_regex.finditer(ddl_script):
        child_tbl = match.group(1).strip('[]"').upper()
        c_name = (match.group(2) or f"FK_{child_tbl}").strip('[]"').upper()
        child_col = match.group(3).strip('[]"').upper()
        parent_tbl = match.group(4).strip('[]"').upper()
        parent_col = match.group(5).strip('[]"').upper()
        pending_fks.append(
            {
                "name": c_name,
                "child_table": child_tbl,
                "child_col": child_col,
                "parent_table": parent_tbl,
                "parent_col": parent_col,
            }
        )

    # Wire Foreign Key relationships
    relationships: List[RelationshipModel] = []
    seen_pairs = set()
    for fk in pending_fks:
        c_ent = entities_by_name.get(fk["child_table"])
        p_ent = entities_by_name.get(fk["parent_table"])
        if not c_ent or not p_ent:
            continue
        c_col = next(
            (c for c in c_ent.columns if c.physical_name.upper() == fk["child_col"]),
            None,
        )
        p_col = next(
            (c for c in p_ent.columns if c.physical_name.upper() == fk["parent_col"]),
            None,
        )
        if not c_col or not p_col:
            continue
        pair_key = (p_ent.id, c_ent.id, p_col.id, c_col.id)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        c_col.is_fk = True
        rel_type = (
            RelationshipType.IDENTIFYING
            if c_col.is_pk
            else RelationshipType.NON_IDENTIFYING
        )
        relationships.append(
            RelationshipModel(
                id=f"rel-{uuid.uuid4().hex[:8]}",
                name=fk["name"],
                parent_entity_id=p_ent.id,
                child_entity_id=c_ent.id,
                parent_column_id=p_col.id,
                child_column_id=c_col.id,
                cardinality=Cardinality.ONE_TO_MANY,
                rel_type=rel_type,
            )
        )

    # Wire Upstream -> Downstream Lineage relationships for Views
    for lin in pending_lineage:
        up_ent = entities_by_name.get(lin["upstream_table"])
        down_view = entities_by_name.get(lin["downstream_view"])
        if not up_ent or not down_view:
            continue
        up_col = next((c for c in up_ent.columns if c.is_pk), up_ent.columns[0] if up_ent.columns else None)
        down_col = next(
            (
                c
                for c in down_view.columns
                if up_col and c.physical_name.upper() == up_col.physical_name.upper()
            ),
            down_view.columns[0] if down_view.columns else None,
        )
        if not up_col or not down_col:
            continue
        relationships.append(
            RelationshipModel(
                id=f"rel-lin-{uuid.uuid4().hex[:8]}",
                name=f"LINEAGE_{up_ent.physical_name}_{down_view.physical_name}",
                parent_entity_id=up_ent.id,
                child_entity_id=down_view.id,
                parent_column_id=up_col.id,
                child_column_id=down_col.id,
                cardinality=Cardinality.ONE_TO_MANY,
                rel_type=RelationshipType.UPSTREAM_LINEAGE,
                transformation_note=f"Upstream source table referenced in view {down_view.physical_name}",
            )
        )

    parsed_entities = [entities_by_name[name] for name in newly_parsed_names]
    return parsed_entities, relationships
