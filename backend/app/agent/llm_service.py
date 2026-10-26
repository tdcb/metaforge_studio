"""Built-in Tool-Calling LLM & Deterministic Enterprise Architect Engine."""
import re
import uuid
from typing import Dict, List, Optional, Tuple, Literal
from pydantic import BaseModel, Field

from ..config import settings
from ..metamodel.schema import (
    Cardinality,
    ColumnModel,
    EntityModel,
    EntityPosition,
    ProjectMetamodel,
    RelationshipModel,
    RelationshipType,
)
from ..compilers.dbt_generator import write_dbt_artifacts_to_disk
from .kilo_bridge import execute_kilo_command
from .mutation_engine import apply_action, execute_mutations
from .gemini_service import call_gemini_agent, GEMINI_AVAILABLE_MODELS


class AgentExecutionResponse(BaseModel):
    mode_used: str
    mutated: bool
    reply: str
    actions_taken: List[str] = Field(default_factory=list)
    cli_trace: Optional[Dict[str, object]] = None
    updated_model: ProjectMetamodel


def _answer_pii_query(model: ProjectMetamodel) -> Tuple[str, List[str]]:
    restricted: List[str] = []
    confidential: List[str] = []
    internal: List[str] = []

    for ent in model.entities.values():
        for col in ent.columns:
            entry = f"- **`{ent.physical_name}.{col.physical_name}`** (*{col.logical_name}*) — `{col.data_type_snowflake}` | Subject Area: `{ent.subject_area}`"
            if col.pii_classification == "RESTRICTED_PII":
                restricted.append(entry)
            elif col.pii_classification == "CONFIDENTIAL":
                confidential.append(entry)
            elif col.pii_classification == "INTERNAL":
                internal.append(entry)

    lines = [
        "### Enterprise PII & Data Privacy Impact Analysis",
        f"Scanned **{len(model.entities)}** entities across **{len(model.subject_areas)}** subject areas.",
        "",
        f"#### 1. Restricted PII (`RESTRICTED_PII`) — {len(restricted)} column(s)",
    ]
    lines.extend(restricted or ["- *None detected*"])
    lines.append("")
    lines.append(f"#### 2. Confidential Financial/Underwriting (`CONFIDENTIAL`) — {len(confidential)} column(s)")
    lines.extend(confidential or ["- *None detected*"])
    lines.append("")
    lines.append(f"#### 3. Internal Reference (`INTERNAL`) — {len(internal)} column(s)")
    lines.extend(internal or ["- *None detected*"])
    lines.append("")
    lines.append(
        "> **Governance Note:** Snowflake DDL automatically attaches `WITH TAG (GOVERNANCE.PII_CLASSIFICATION = ...)` "
        "and SQL Server emits `@name=N'PII_Classification'` extended properties for all classified columns."
    )
    return "\n".join(lines), ["Executed MCP Tool: `search_metadata(filter='pii_classification')`"]


def _answer_lineage_query(model: ProjectMetamodel, prompt: str) -> Tuple[str, List[str]]:
    # Find referenced entity in prompt, default to FCT_CLAIM if none matched
    target_ent: Optional[EntityModel] = None
    up_prompt = prompt.upper()
    for ent in model.entities.values():
        if ent.physical_name.upper() in up_prompt or ent.logical_name.upper() in up_prompt:
            target_ent = ent
            break
    if not target_ent:
        target_ent = next(
            (e for e in model.entities.values() if e.physical_name.upper() == "FCT_CLAIM"),
            next(iter(model.entities.values()), None),
        )
    if not target_ent:
        return "No entities exist in the active model.", []

    upstream_parents: List[str] = []
    downstream_children: List[str] = []

    for rel in model.relationships.values():
        p_ent = model.entities.get(rel.parent_entity_id)
        c_ent = model.entities.get(rel.child_entity_id)
        if not p_ent or not c_ent:
            continue
        p_col = next((c for c in p_ent.columns if c.id == rel.parent_column_id), None)
        c_col = next((c for c in c_ent.columns if c.id == rel.child_column_id), None)
        p_col_name = p_col.physical_name if p_col else "PK"
        c_col_name = c_col.physical_name if c_col else "FK"

        if rel.child_entity_id == target_ent.id:
            upstream_parents.append(
                f"- **Upstream Dimension/Parent:** `{p_ent.physical_name}` (*{p_ent.logical_name}*) "
                f"via `{p_ent.physical_name}.{p_col_name} -> {target_ent.physical_name}.{c_col_name}` "
                f"[`{rel.rel_type.value}`, `{rel.cardinality.value}`]"
            )
        if rel.parent_entity_id == target_ent.id:
            downstream_children.append(
                f"- **Downstream Consumer/Child:** `{c_ent.physical_name}` (*{c_ent.logical_name}*) "
                f"via `{target_ent.physical_name}.{p_col_name} -> {c_ent.physical_name}.{c_col_name}` "
                f"[`{rel.rel_type.value}`, `{rel.cardinality.value}`]"
            )

    lines = [
        f"### Lineage & Dependency Graph for `{target_ent.physical_name}` (*{target_ent.logical_name}*)",
        f"- **Subject Area:** `{target_ent.subject_area}` | **dbt Layer:** `{target_ent.dbt_layer}` (`materialized='{target_ent.dbt_materialization}'`)",
        "",
        "#### Upstream Parent Entities (`{{ ref() }}` / PK Providers)",
    ]
    lines.extend(upstream_parents or ["- *No upstream parent entities linked.*"])
    lines.append("")
    lines.append("#### Downstream Child / Dependent Entities")
    lines.extend(downstream_children or ["- *No downstream child entities linked.*"])
    lines.append("")
    lines.append(
        f"#### dbt Model Output\n"
        f"- File: `models/{target_ent.subject_area.lower()}/{target_ent.physical_name.lower()}.sql`\n"
        f"- Unique Key: `{target_ent.dbt_unique_key or 'Composite PK'}`"
    )
    return "\n".join(lines), [f"Executed MCP Tool: `get_entity_lineage(entity='{target_ent.physical_name}')`"]


def _answer_oracle_fk_index_audit(model: ProjectMetamodel) -> Tuple[str, List[str]]:
    unindexed_fks: List[str] = []
    covered_fks: List[str] = []

    for rel in model.relationships.values():
        p_ent = model.entities.get(rel.parent_entity_id)
        c_ent = model.entities.get(rel.child_entity_id)
        if not p_ent or not c_ent:
            continue
        c_col = next((c for c in c_ent.columns if c.id == rel.child_column_id), None)
        if not c_col:
            continue

        # In Oracle, an FK column is automatically indexed only if it is the leading column of the PK or unique constraint
        pk_cols = [c.physical_name for c in c_ent.columns if c.is_pk]
        is_leading_pk = len(pk_cols) > 0 and pk_cols[0] == c_col.physical_name
        ora_schema = c_ent.oracle_props.schema_name.upper()
        ora_idx_tbs = c_ent.oracle_props.index_tablespace.upper()

        if is_leading_pk or c_col.is_unique:
            covered_fks.append(
                f"- `{c_ent.physical_name}.{c_col.physical_name}` (Covered by PK/Unique index)"
            )
        else:
            idx_ddl = (
                f"CREATE INDEX {ora_schema}.IX_{rel.name[:22].upper()} "
                f"ON {ora_schema}.{c_ent.physical_name} ({c_col.physical_name}) "
                f"TABLESPACE {ora_idx_tbs};"
            )
            unindexed_fks.append(
                f"- **`{c_ent.physical_name}.{c_col.physical_name}`** (References `{p_ent.physical_name}`, `{rel.rel_type.value}`)\n"
                f"  ```sql\n  {idx_ddl}\n  ```"
            )

    lines = [
        "### Oracle Foreign Key Indexing & Lock-Escalation Audit",
        "In Oracle Database, unindexed Foreign Key columns can cause full-table TM lock contention on child tables during parent PK updates/deletes.",
        "",
        f"#### Foreign Keys Requiring Dedicated B-Tree Indexes ({len(unindexed_fks)})",
    ]
    lines.extend(unindexed_fks or ["- *All foreign keys are covered by leading primary/unique indexes.*"])
    if covered_fks:
        lines.append("")
        lines.append(f"#### Foreign Keys Already Covered by Leading Key ({len(covered_fks)})")
        lines.extend(covered_fks)
    lines.append("")
    lines.append(
        "> **Tip:** MetaForge Studio's Oracle PL/SQL Compiler (`compilers/oracle.py`) automatically emits these `CREATE INDEX ... TABLESPACE <idx_tbs>` statements below each `ALTER TABLE ... ADD CONSTRAINT`."
    )
    return "\n".join(lines), ["Executed MCP Tool: `audit_oracle_fk_indexes()`"]


def _mutate_add_audit_columns(model: ProjectMetamodel, prompt: str) -> Tuple[str, List[str]]:
    # Determine if scoped to a specific subject area (e.g., "Claims", "Core", "Finance")
    target_sa: Optional[str] = None
    for sa in model.subject_areas:
        if re.search(rf"\b{re.escape(sa)}\b", prompt, re.IGNORECASE):
            target_sa = sa
            break

    audit_specs = [
        {
            "logical_name": "Record Created Timestamp",
            "physical_name": "REC_CRTD_TS",
            "domain_id": "dom-audit-timestamp",
            "sf": "TIMESTAMP_NTZ(9)",
            "ss": "DATETIME2(7)",
            "ora": "TIMESTAMP(6)",
            "desc": "UTC audit timestamp when the record was initially inserted.",
        },
        {
            "logical_name": "Record Updated Timestamp",
            "physical_name": "REC_UPDT_TS",
            "domain_id": "dom-audit-timestamp",
            "sf": "TIMESTAMP_NTZ(9)",
            "ss": "DATETIME2(7)",
            "ora": "TIMESTAMP(6)",
            "desc": "UTC audit timestamp when the record was last updated.",
        },
        {
            "logical_name": "Source System Code",
            "physical_name": "SRC_SYS_CD",
            "domain_id": "dom-standard-code",
            "sf": "VARCHAR(30)",
            "ss": "VARCHAR(30)",
            "ora": "VARCHAR2(30 CHAR)",
            "desc": "Enterprise identifier of the originating operational source system.",
        },
    ]

    updated_tables: List[str] = []
    added_col_count = 0

    for ent in model.entities.values():
        if target_sa and ent.subject_area.lower() != target_sa.lower():
            continue
        existing_names = {c.physical_name.upper() for c in ent.columns}
        added_this_ent: List[str] = []
        for spec in audit_specs:
            if spec["physical_name"] not in existing_names:
                ent.columns.append(
                    ColumnModel(
                        id=f"col-{ent.physical_name.lower()}-{spec['physical_name'].lower()}-{uuid.uuid4().hex[:4]}",
                        logical_name=spec["logical_name"],
                        physical_name=spec["physical_name"],
                        domain_id=spec["domain_id"] if spec["domain_id"] in model.domains else None,
                        data_type_snowflake=spec["sf"],
                        data_type_sql_server=spec["ss"],
                        data_type_oracle=spec["ora"],
                        is_pk=False,
                        is_fk=False,
                        is_nullable=False,
                        description=spec["desc"],
                        pii_classification="NONE",
                        dbt_tests=["not_null"],
                    )
                )
                added_this_ent.append(spec["physical_name"])
                added_col_count += 1
        if added_this_ent:
            updated_tables.append(f"- **`{ent.physical_name}`** ({ent.subject_area}): Added `{', '.join(added_this_ent)}`")

    scope_label = f"the **{target_sa}** subject area" if target_sa else "**all subject areas**"
    if not updated_tables:
        return (
            f"All tables in {scope_label} already contain `REC_CRTD_TS`, `REC_UPDT_TS`, and `SRC_SYS_CD`.",
            ["Verified enterprise audit columns across target entities"],
        )

    reply = "\n".join(
        [
            f"### Added Standard Enterprise Audit Columns to {scope_label}",
            f"Injected **{added_col_count}** audit column(s) bound to `Audit_Timestamp` and `Standard_Code` domains:",
            "",
            *updated_tables,
        ]
    )
    return reply, [f"Mutated {len(updated_tables)} entities with standard enterprise audit columns"]


def _mutate_apply_naming_glossary(model: ProjectMetamodel) -> Tuple[str, List[str]]:
    changes: List[str] = []
    for ent in model.entities.values():
        old_e = ent.physical_name
        for col in ent.columns:
            old_c = col.physical_name
            new_c = translate_logical_to_physical(col.logical_name, model.glossary)
            if old_c != new_c:
                changes.append(f"- Column `{old_e}.{old_c}` -> **`{new_c}`** (*{col.logical_name}*)")

    stats = apply_glossary_to_project(model, overwrite_existing=True)
    lines = [
        "### Enterprise Naming Standards Glossary Applied",
        f"- **Entities Standardized:** `{stats['entities_updated']}`",
        f"- **Columns Standardized:** `{stats['columns_updated']}`",
        f"- **Active Glossary Abbreviations:** `{len(model.glossary.abbreviations)}` rules",
    ]
    if changes:
        lines.append("")
        lines.append("#### Translated Identifiers:")
        lines.extend(changes[:20])
    else:
        lines.append("")
        lines.append("All existing physical names already conform 100% to the active Naming Standards Glossary.")
    return "\n".join(lines), ["Executed MCP Tool: `apply_naming_glossary()`"]


def _mutate_scaffold_star_schema(model: ProjectMetamodel, prompt: str) -> Tuple[str, List[str]]:
    """
    Create a Star Schema for Retail Orders (or custom topic) with 1 Fact table
    and 3 Dimension tables (DIM_CUSTOMER, DIM_PRODUCT, DIM_DATE) and wire non-identifying FKs.
    """
    if "Retail" not in model.subject_areas and "Finance" in model.subject_areas:
        target_sa = "Finance"
    else:
        target_sa = "Core"

    # 1. Reuse existing DIM_CUSTOMER if present, else create it
    dim_cust = next(
        (e for e in model.entities.values() if e.physical_name.upper() == "DIM_CUSTOMER"),
        None,
    )
    if not dim_cust:
        dim_cust_id = "ent-dim-customer"
        cust_pk_id = "col-cust-id"
        dim_cust = EntityModel(
            id=dim_cust_id,
            logical_name="Customer",
            physical_name="DIM_CUSTOMER",
            database_schema="CORE",
            subject_area=target_sa,
            description="Conformed Customer Dimension for Retail & Insurance analytics.",
            header_color="#2563eb",
            position=EntityPosition(x=100.0, y=100.0),
            columns=[
                ColumnModel(
                    id=cust_pk_id,
                    logical_name="Customer Identifier",
                    physical_name="CUST_ID",
                    domain_id="dom-surrogate-id",
                    data_type_snowflake="NUMBER(38,0)",
                    data_type_sql_server="BIGINT",
                    data_type_oracle="NUMBER(19,0)",
                    is_pk=True,
                    is_nullable=False,
                    is_identity=True,
                    dbt_tests=["unique", "not_null"],
                ),
                ColumnModel(
                    id="col-cust-nm",
                    logical_name="Customer Full Name",
                    physical_name="CUST_FULL_NM",
                    data_type_snowflake="VARCHAR(150)",
                    data_type_sql_server="NVARCHAR(150)",
                    data_type_oracle="VARCHAR2(150 CHAR)",
                    is_nullable=False,
                    pii_classification="RESTRICTED_PII",
                ),
            ],
        )
        model.entities[dim_cust.id] = dim_cust
    else:
        cust_pk_col = next((c for c in dim_cust.columns if c.is_pk), dim_cust.columns[0])
        cust_pk_id = cust_pk_col.id

    # 2. Create DIM_PRODUCT if not present
    dim_prod = next(
        (e for e in model.entities.values() if e.physical_name.upper() == "DIM_PRODUCT"),
        None,
    )
    if not dim_prod:
        dim_prod = EntityModel(
            id="ent-dim-product",
            logical_name="Product",
            physical_name="DIM_PRODUCT",
            database_schema="CORE",
            subject_area=target_sa,
            description="Enterprise Product Catalog Dimension with SKU, category, and unit price.",
            header_color="#059669",
            position=EntityPosition(x=80.0, y=840.0),
            dbt_materialization="table",
            dbt_layer="mart",
            dbt_unique_key="PROD_ID",
            columns=[
                ColumnModel(
                    id="col-prod-id",
                    logical_name="Product Identifier",
                    physical_name="PROD_ID",
                    domain_id="dom-surrogate-id",
                    data_type_snowflake="NUMBER(38,0)",
                    data_type_sql_server="BIGINT",
                    data_type_oracle="NUMBER(19,0)",
                    is_pk=True,
                    is_nullable=False,
                    is_identity=True,
                    description="Surrogate primary key for DIM_PRODUCT.",
                    dbt_tests=["unique", "not_null"],
                ),
                ColumnModel(
                    id="col-prod-sku",
                    logical_name="Product SKU Code",
                    physical_name="PROD_SKU_CD",
                    domain_id="dom-standard-code",
                    data_type_snowflake="VARCHAR(30)",
                    data_type_sql_server="VARCHAR(30)",
                    data_type_oracle="VARCHAR2(30 CHAR)",
                    is_nullable=False,
                    is_unique=True,
                    description="Stock keeping unit business code.",
                    dbt_tests=["unique", "not_null"],
                ),
                ColumnModel(
                    id="col-prod-name",
                    logical_name="Product Description",
                    physical_name="PROD_DESC",
                    data_type_snowflake="VARCHAR(255)",
                    data_type_sql_server="NVARCHAR(255)",
                    data_type_oracle="VARCHAR2(255 CHAR)",
                    is_nullable=False,
                    description="Commercial product display name.",
                    dbt_tests=["not_null"],
                ),
                ColumnModel(
                    id="col-prod-price",
                    logical_name="Unit List Price Amount",
                    physical_name="UNIT_LIST_PRICE_AMT",
                    domain_id="dom-monetary-amount",
                    data_type_snowflake="NUMBER(18,2)",
                    data_type_sql_server="DECIMAL(18,2)",
                    data_type_oracle="NUMBER(18,2)",
                    is_nullable=False,
                    description="Standard retail unit list price.",
                    dbt_tests=["not_null"],
                ),
            ],
        )
        model.entities[dim_prod.id] = dim_prod
    prod_pk_id = next(c.id for c in dim_prod.columns if c.is_pk)

    # 3. Create DIM_DATE if not present
    dim_date = next(
        (e for e in model.entities.values() if e.physical_name.upper() == "DIM_DATE"),
        None,
    )
    if not dim_date:
        dim_date = EntityModel(
            id="ent-dim-date",
            logical_name="Calendar Date",
            physical_name="DIM_DATE",
            database_schema="CORE",
            subject_area=target_sa,
            description="Conformed enterprise fiscal & calendar date dimension.",
            header_color="#4f46e5",
            position=EntityPosition(x=1040.0, y=840.0),
            dbt_materialization="table",
            dbt_layer="mart",
            dbt_unique_key="DT_KEY",
            columns=[
                ColumnModel(
                    id="col-date-key",
                    logical_name="Date Identifier",
                    physical_name="DT_KEY",
                    domain_id="dom-surrogate-id",
                    data_type_snowflake="NUMBER(38,0)",
                    data_type_sql_server="BIGINT",
                    data_type_oracle="NUMBER(19,0)",
                    is_pk=True,
                    is_nullable=False,
                    description="Integer YYYYMMDD smart key for date dimension.",
                    dbt_tests=["unique", "not_null"],
                ),
                ColumnModel(
                    id="col-date-cal",
                    logical_name="Calendar Date",
                    physical_name="CALENDAR_DT",
                    data_type_snowflake="DATE",
                    data_type_sql_server="DATE",
                    data_type_oracle="DATE",
                    is_nullable=False,
                    description="Actual calendar date value.",
                    dbt_tests=["not_null"],
                ),
                ColumnModel(
                    id="col-date-fisc-yr",
                    logical_name="Fiscal Year Number",
                    physical_name="FISCAL_YR_NBR",
                    data_type_snowflake="NUMBER(4,0)",
                    data_type_sql_server="SMALLINT",
                    data_type_oracle="NUMBER(4,0)",
                    is_nullable=False,
                    description="Four-digit enterprise fiscal year.",
                    dbt_tests=["not_null"],
                ),
            ],
        )
        model.entities[dim_date.id] = dim_date
    date_pk_id = next(c.id for c in dim_date.columns if c.is_pk)

    # 4. Create FCT_RETAIL_ORDER
    fct_order = next(
        (e for e in model.entities.values() if e.physical_name.upper() in ("FCT_RETAIL_ORDER", "FCT_ORDER")),
        None,
    )
    if not fct_order:
        fct_order = EntityModel(
            id="ent-fct-retail-order",
            logical_name="Retail Order Fact",
            physical_name="FCT_RETAIL_ORDER",
            database_schema="CORE",
            subject_area=target_sa,
            description="Star-schema transactional fact table capturing retail order line items, quantities, and net revenue.",
            header_color="#dc2626",
            position=EntityPosition(x=560.0, y=840.0),
            dbt_materialization="incremental",
            dbt_layer="mart",
            dbt_unique_key="ORD_ID",
            columns=[
                ColumnModel(
                    id="col-ord-id",
                    logical_name="Order Identifier",
                    physical_name="ORD_ID",
                    domain_id="dom-surrogate-id",
                    data_type_snowflake="NUMBER(38,0)",
                    data_type_sql_server="BIGINT",
                    data_type_oracle="NUMBER(19,0)",
                    is_pk=True,
                    is_nullable=False,
                    description="Surrogate primary key for the retail order fact.",
                    dbt_tests=["unique", "not_null"],
                ),
                ColumnModel(
                    id="col-ord-cust-id",
                    logical_name="Customer Identifier",
                    physical_name="CUST_ID",
                    domain_id="dom-surrogate-id",
                    data_type_snowflake="NUMBER(38,0)",
                    data_type_sql_server="BIGINT",
                    data_type_oracle="NUMBER(19,0)",
                    is_pk=False,
                    is_fk=True,
                    is_nullable=False,
                    description="Non-identifying foreign key to DIM_CUSTOMER.",
                    dbt_tests=["not_null"],
                ),
                ColumnModel(
                    id="col-ord-prod-id",
                    logical_name="Product Identifier",
                    physical_name="PROD_ID",
                    domain_id="dom-surrogate-id",
                    data_type_snowflake="NUMBER(38,0)",
                    data_type_sql_server="BIGINT",
                    data_type_oracle="NUMBER(19,0)",
                    is_pk=False,
                    is_fk=True,
                    is_nullable=False,
                    description="Non-identifying foreign key to DIM_PRODUCT.",
                    dbt_tests=["not_null"],
                ),
                ColumnModel(
                    id="col-ord-dt-key",
                    logical_name="Order Date Identifier",
                    physical_name="ORD_DT_KEY",
                    domain_id="dom-surrogate-id",
                    data_type_snowflake="NUMBER(38,0)",
                    data_type_sql_server="BIGINT",
                    data_type_oracle="NUMBER(19,0)",
                    is_pk=False,
                    is_fk=True,
                    is_nullable=False,
                    description="Non-identifying foreign key to DIM_DATE.",
                    dbt_tests=["not_null"],
                ),
                ColumnModel(
                    id="col-ord-qty",
                    logical_name="Order Quantity",
                    physical_name="ORD_QTY",
                    data_type_snowflake="NUMBER(10,0)",
                    data_type_sql_server="INT",
                    data_type_oracle="NUMBER(10,0)",
                    is_pk=False,
                    is_nullable=False,
                    description="Number of product units purchased.",
                    dbt_tests=["not_null"],
                ),
                ColumnModel(
                    id="col-ord-amt",
                    logical_name="Order Total Amount",
                    physical_name="ORD_TOTAL_AMT",
                    domain_id="dom-monetary-amount",
                    data_type_snowflake="NUMBER(18,2)",
                    data_type_sql_server="DECIMAL(18,2)",
                    data_type_oracle="NUMBER(18,2)",
                    is_pk=False,
                    is_nullable=False,
                    pii_classification="CONFIDENTIAL",
                    description="Total net revenue amount for the order line.",
                    dbt_tests=["not_null"],
                ),
                ColumnModel(
                    id="col-ord-crtd-ts",
                    logical_name="Record Created Timestamp",
                    physical_name="REC_CRTD_TS",
                    domain_id="dom-audit-timestamp",
                    data_type_snowflake="TIMESTAMP_NTZ(9)",
                    data_type_sql_server="DATETIME2(7)",
                    data_type_oracle="TIMESTAMP(6)",
                    is_pk=False,
                    is_nullable=False,
                    description="UTC audit timestamp when order row was ingested.",
                    dbt_tests=["not_null"],
                ),
            ],
        )
        model.entities[fct_order.id] = fct_order

    # 5. Wire the 3 Non-Identifying Relationships
    star_rels = [
        RelationshipModel(
            id="rel-retail-cust",
            name="FK_FCT_RETAIL_ORDER_DIM_CUSTOMER",
            parent_entity_id=dim_cust.id,
            child_entity_id=fct_order.id,
            parent_column_id=cust_pk_id,
            child_column_id="col-ord-cust-id",
            cardinality=Cardinality.ONE_TO_MANY,
            rel_type=RelationshipType.NON_IDENTIFYING,
        ),
        RelationshipModel(
            id="rel-retail-prod",
            name="FK_FCT_RETAIL_ORDER_DIM_PRODUCT",
            parent_entity_id=dim_prod.id,
            child_entity_id=fct_order.id,
            parent_column_id=prod_pk_id,
            child_column_id="col-ord-prod-id",
            cardinality=Cardinality.ONE_TO_MANY,
            rel_type=RelationshipType.NON_IDENTIFYING,
        ),
        RelationshipModel(
            id="rel-retail-date",
            name="FK_FCT_RETAIL_ORDER_DIM_DATE",
            parent_entity_id=dim_date.id,
            child_entity_id=fct_order.id,
            parent_column_id=date_pk_id,
            child_column_id="col-ord-dt-key",
            cardinality=Cardinality.ONE_TO_MANY,
            rel_type=RelationshipType.NON_IDENTIFYING,
        ),
    ]
    for sr in star_rels:
        model.relationships[sr.id] = sr

    reply = "\n".join(
        [
            "### Star Schema Scaffolded: Retail Orders (`FCT_RETAIL_ORDER`)",
            "Created and wired the complete Kimberlite Star Schema with **Enterprise Domains** and **Non-Identifying (`1:N`)** relationships:",
            "",
            "1. **Fact Table:** `FCT_RETAIL_ORDER` (*Retail Order Fact*) — Incremental Mart (`ORD_ID`, `CUST_ID`, `PROD_ID`, `ORD_DT_KEY`, `ORD_QTY`, `ORD_TOTAL_AMT`, `REC_CRTD_TS`)",
            "2. **Dimension 1:** `DIM_CUSTOMER` (*Customer*) — Linked via `FK_FCT_RETAIL_ORDER_DIM_CUSTOMER` (`1:N`, Non-Identifying)",
            "3. **Dimension 2:** `DIM_PRODUCT` (*Product*) — Linked via `FK_FCT_RETAIL_ORDER_DIM_PRODUCT` (`1:N`, Non-Identifying)",
            "4. **Dimension 3:** `DIM_DATE` (*Calendar Date*) — Linked via `FK_FCT_RETAIL_ORDER_DIM_DATE` (`1:N`, Non-Identifying)",
        ]
    )
    return reply, [
        "Created entities: FCT_RETAIL_ORDER, DIM_PRODUCT, DIM_DATE",
        "Wired 3 non-identifying 1:N foreign key relationships to DIM_CUSTOMER, DIM_PRODUCT, DIM_DATE",
    ]


def _mutate_generate_column_descriptions(model: ProjectMetamodel) -> Tuple[str, List[str]]:
    updated_cols: List[str] = []
    # Map child_column_id -> parent entity name
    fk_parent_map: Dict[str, str] = {}
    for rel in model.relationships.values():
        p_ent = model.entities.get(rel.parent_entity_id)
        if p_ent:
            fk_parent_map[rel.child_column_id] = p_ent.physical_name

    for ent in model.entities.values():
        if not ent.description or not ent.description.strip():
            ent.description = (
                f"Enterprise {ent.dbt_layer} entity representing {ent.logical_name} "
                f"within the {ent.subject_area} subject area."
            )
        for col in ent.columns:
            if not col.description or not col.description.strip():
                role_phrase = "Attribute"
                if col.is_pk and col.is_fk:
                    parent_name = fk_parent_map.get(col.id, "parent entity")
                    role_phrase = f"Composite identifying primary/foreign key referencing {parent_name}"
                elif col.is_pk:
                    role_phrase = f"Surrogate primary key uniquely identifying each {ent.logical_name} record"
                elif col.is_fk:
                    parent_name = fk_parent_map.get(col.id, "parent dimension")
                    role_phrase = f"Foreign key linking {ent.logical_name} to {parent_name}"
                elif col.pii_classification != "NONE":
                    role_phrase = f"Governed {col.pii_classification} business attribute"

                col.description = (
                    f"{role_phrase} storing {col.logical_name.lower()} for {ent.logical_name}."
                )
                updated_cols.append(f"- **`{ent.physical_name}.{col.physical_name}`**: *\"{col.description}\"*")

    if not updated_cols:
        # Also enrich any generic "Reverse-engineered..." or short descriptions if all columns already had descriptions
        for ent in model.entities.values():
            for col in ent.columns:
                if len(col.description.strip()) < 25:
                    col.description = (
                        f"Enterprise governed attribute capturing {col.logical_name.lower()} "
                        f"for {ent.logical_name} ({ent.subject_area} domain)."
                    )
                    updated_cols.append(f"- **`{ent.physical_name}.{col.physical_name}`**: *\"{col.description}\"*")

    lines = [
        "### Automated Business Metadata & Column Documentation Complete",
        f"Synthesized semantic business descriptions for **{len(updated_cols)}** column(s) based on logical names, domains, and relationship lineage.",
    ]
    if updated_cols:
        lines.append("")
        lines.extend(updated_cols[:25])
    else:
        lines.append("")
        lines.append("All columns across all entities already have complete enterprise business descriptions.")
    return "\n".join(lines), [f"Generated descriptions for {len(updated_cols)} columns"]


def _answer_general_summary(model: ProjectMetamodel) -> Tuple[str, List[str]]:
    total_cols = sum(len(e.columns) for e in model.entities.values())
    pii_cols = sum(
        1 for e in model.entities.values() for c in e.columns if c.pii_classification != "NONE"
    )
    ent_bullets = [
        f"- **`{e.physical_name}`** (*{e.logical_name}*) — `{len(e.columns)}` cols | Subject Area: `{e.subject_area}` | dbt: `{e.dbt_materialization}`"
        for e in model.entities.values()
    ]
    reply = "\n".join(
        [
            f"### {model.name} (v{model.version}) — Architecture Overview",
            f"- **Entities:** `{len(model.entities)}` | **Columns:** `{total_cols}` | **Relationships:** `{len(model.relationships)}`",
            f"- **Enterprise Domains:** `{len(model.domains)}` (`{', '.join(d.name for d in model.domains.values())}`)",
            f"- **Governed PII/Confidential Columns:** `{pii_cols}`",
            "",
            "#### Canonical Entities:",
            *ent_bullets,
            "",
            "You can ask me to:\n"
            "- *\"Which tables contain Restricted PII?\"*\n"
            "- *\"Show me the upstream and downstream lineage of FCT_CLAIM\"*\n"
            "- *\"Which foreign keys are missing indexes in Oracle?\"*\n"
            "- *\"Add standard enterprise audit columns (REC_CRTD_TS, REC_UPDT_TS, SRC_SYS_CD) to all tables in the Claims subject area.\"*\n"
            "- *\"Apply the Enterprise Naming Glossary to standardize all physical table and column names.\"*\n"
            "- *\"Create a Star Schema for Retail Orders with 1 Fact table and 3 Dimension tables (DIM_CUSTOMER, DIM_PRODUCT, DIM_DATE) and wire the non-identifying foreign keys.\"*\n"
            "- *\"Generate descriptions for all undocumented columns based on their logical names and relationships.\"*",
        ]
    )
    return reply, ["Executed MCP Tool: `get_model_summary()`"]


def _try_builtin_natural_language_mutations(
    model: ProjectMetamodel, prompt: str
) -> Optional[Tuple[str, List[str]]]:
    """Parses natural-language instructions to add/modify tables, views, relations, columns, or subject areas."""
    clean = prompt.strip()
    p_lower = clean.lower()

    # A. Add/Create Subject Area
    sa_match = re.search(r"(?:add|create)\s+subject\s+area\s+([A-Za-z0-9_ ]+)", clean, re.IGNORECASE)
    if sa_match and not any(k in p_lower for k in ("table", "view", "column", "relation")):
        sa_name = sa_match.group(1).strip()
        msg = apply_action(model, {"action": "add_subject_area", "name": sa_name})
        if msg:
            return f"### Subject Area Created\n- {msg}", [msg]

    # B. Add/Create View
    vw_match = re.search(
        r"(?:add|create)\s+(?:a\s+)?(materialized\s+)?view\s+(?:called\s+|named\s+)?([A-Za-z0-9_]+)?(?:\s+(?:as|with\s+query|with\s+sql|\:)\s+(.*?)$)?",
        clean,
        re.IGNORECASE,
    )
    if vw_match and (vw_match.group(2) or "view" in p_lower):
        is_mat = bool(vw_match.group(1))
        vw_raw_name = vw_match.group(2)
        if not vw_raw_name or vw_raw_name.upper() in ("AS", "WITH", "FOR", "FROM"):
            # Auto-infer view name from prompt context
            words = [w.upper() for w in re.findall(r"[A-Za-z0-9_]+", clean) if w.upper() not in ("CREATE", "ADD", "A", "VIEW", "FOR", "AS", "THE", "WITH", "QUERY", "MATERIALIZED")]
            vw_name = f"VW_{words[0] if words else 'ANALYTICS_SUMMARY'}"
        else:
            vw_name = vw_raw_name.upper().strip()
        
        sql = vw_match.group(3).strip() if vw_match.group(3) else "SELECT c.CLM_TXN_ID, c.CLM_LOSS_AMT, c.CLM_PAID_AMT, p.PLCY_NBR, cust.CUST_FULL_NM FROM FCT_CLAIM_TRANSACTION c INNER JOIN DIM_INSURANCE_POLICY p ON c.PLCY_ID = p.PLCY_ID INNER JOIN DIM_CUSTOMER cust ON c.CUST_ID = cust.CUST_ID WHERE c.CLM_PAID_AMT > 25000"
        msg = apply_action(
            model,
            {
                "action": "add_view",
                "physical_name": vw_name,
                "view_sql": sql,
                "materialization": "materialized_view" if is_mat else "view",
            },
        )
        if msg:
            return (
                f"### View Created Successfully\n- {msg}\n\n```sql\n{sql}\n```",
                [msg],
            )

    # C. Add/Create Table
    tbl_match = re.search(
        r"(?:add|create)\s+table\s+([A-Za-z0-9_]+)(?:\s+(?:with\s+columns?|columns?|\:|\()\s*(.*?)(?:\)|$))?",
        clean,
        re.IGNORECASE,
    )
    if tbl_match and "view" not in p_lower:
        tbl_name = tbl_match.group(1).upper().strip()
        raw_cols_str = tbl_match.group(2) or ""
        columns_list = []

        if raw_cols_str:
            # Parse comma-separated column definitions: e.g. "order_id number pk, customer_id int fk, order_date date"
            parts = [c.strip() for c in raw_cols_str.split(",") if c.strip()]
            for p in parts:
                tokens = p.split()
                if not tokens:
                    continue
                c_name = tokens[0].upper()
                c_type = tokens[1].upper() if len(tokens) > 1 and tokens[1].upper() not in ("PK", "FK", "NOT") else "VARCHAR(255)"
                is_pk = any(t.upper() == "PK" for t in tokens) or c_name.endswith("_ID") and len(columns_list) == 0
                is_fk = any(t.upper() == "FK" for t in tokens)
                columns_list.append(
                    {
                        "physical_name": c_name,
                        "data_type": c_type,
                        "is_pk": is_pk,
                        "is_fk": is_fk,
                    }
                )

        msg = apply_action(
            model,
            {
                "action": "add_table",
                "physical_name": tbl_name,
                "columns": columns_list,
            },
        )
        if msg:
            return f"### Table Created Successfully\n- {msg}", [msg]

    # D. Add/Create Relationship
    rel_match = re.search(
        r"(?:add|create|connect)\s+(?:relationship|relation|fk)\s+(?:between|from)?\s*([A-Za-z0-9_]+)\s+(?:and|to)\s+([A-Za-z0-9_]+)",
        clean,
        re.IGNORECASE,
    )
    if rel_match:
        p_name = rel_match.group(1).upper().strip()
        c_name = rel_match.group(2).upper().strip()
        msg = apply_action(
            model,
            {
                "action": "add_relationship",
                "parent_table": p_name,
                "child_table": c_name,
                "rel_type": "non_identifying",
                "cardinality": "one_to_many",
            },
        )
        if msg:
            return f"### Relationship Created Successfully\n- {msg}", [msg]

    # E. Add Column to Table
    col_match = re.search(
        r"(?:add|create)\s+column\s+([A-Za-z0-9_]+)(?:\s+([A-Za-z0-9_\(\)]+))?\s+to\s+([A-Za-z0-9_]+)",
        clean,
        re.IGNORECASE,
    )
    if col_match:
        c_name = col_match.group(1).upper().strip()
        c_type = col_match.group(2) or "VARCHAR(255)"
        tbl_name = col_match.group(3).upper().strip()
        msg = apply_action(
            model,
            {
                "action": "add_column",
                "table_name": tbl_name,
                "physical_name": c_name,
                "data_type": c_type,
            },
        )
        if msg:
            return f"### Column Added\n- {msg}", [msg]

    # F. Drop Table
    drop_tbl_match = re.search(r"(?:drop|delete)\s+table\s+([A-Za-z0-9_]+)", clean, re.IGNORECASE)
    if drop_tbl_match:
        tbl_name = drop_tbl_match.group(1).upper().strip()
        msg = apply_action(model, {"action": "drop_table", "physical_name": tbl_name})
        if msg:
            return f"### Table Dropped\n- {msg}", [msg]

    # G. Drop View
    drop_vw_match = re.search(r"(?:drop|delete)\s+view\s+([A-Za-z0-9_]+)", clean, re.IGNORECASE)
    if drop_vw_match:
        vw_name = drop_vw_match.group(1).upper().strip()
        msg = apply_action(model, {"action": "drop_view", "physical_name": vw_name})
        if msg:
            return f"### View Dropped\n- {msg}", [msg]

    return None


def execute_agent_prompt(
    model: ProjectMetamodel,
    prompt: str,
    mode: Literal["kilo-cli", "builtin-llm", "gemini"] = "builtin-llm",
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
    allow_mutations: bool = True,
) -> AgentExecutionResponse:
    """
    Execute a natural-language Q&A or model governance mutation via:
    1. Google Gemini API (`gemini-2.5-flash`, `gemini-2.5-pro`, etc.)
    2. Built-in Architect (deterministic AST mutation + natural-language parser)
    3. `kilo-cli` headless engine
    """
    # ---------------------------------------------------------
    # Mode 1: Google Gemini LLM
    # ---------------------------------------------------------
    if mode == "gemini":
        g_model = gemini_model or settings.gemini_model or "gemini-2.5-flash"
        try:
            reply, actions, mutated, updated_model = call_gemini_agent(
                model=model,
                prompt=prompt,
                api_key=gemini_api_key,
                gemini_model=g_model,
                allow_mutations=allow_mutations,
            )
            if mutated:
                write_dbt_artifacts_to_disk(updated_model, settings.exported_dbt_dir)

            return AgentExecutionResponse(
                mode_used=f"Google Gemini ({g_model})",
                mutated=mutated,
                reply=reply,
                actions_taken=actions,
                updated_model=updated_model,
            )
        except Exception as exc:
            # Fall back cleanly to the built-in natural-language architect engine
            reply, actions, mutated, updated_model = _process_builtin_agent(
                model, prompt, allow_mutations
            )
            if mutated:
                write_dbt_artifacts_to_disk(updated_model, settings.exported_dbt_dir)

            note = (
                f"> ℹ️ **Gemini Network Notice**: Backend could not reach Google Gemini API directly (`{exc}`). "
                f"Your request was automatically fulfilled by **MetaForge Built-in Architect**.\n\n"
            )
            return AgentExecutionResponse(
                mode_used="MetaForge Built-in Architect (Gemini Fallback)",
                mutated=mutated,
                reply=note + reply,
                actions_taken=actions or [f"Processed via Built-in Architect: {prompt[:80]}"],
                updated_model=updated_model,
            )

    # ---------------------------------------------------------
    # Mode 2: Kilo-CLI
    # ---------------------------------------------------------
    cli_trace: Optional[Dict[str, object]] = None
    if mode == "kilo-cli":
        cli_trace = execute_kilo_command(prompt=prompt)
        # If kilo-cli succeeded and mutated canonical_model.json on disk, reload it
        if cli_trace.get("executed_cli") and settings.canonical_model_path.exists():
            try:
                reloaded = ProjectMetamodel.model_validate_json(
                    settings.canonical_model_path.read_text(encoding="utf-8")
                )
                write_dbt_artifacts_to_disk(reloaded, settings.exported_dbt_dir)
                return AgentExecutionResponse(
                    mode_used="kilo-cli",
                    mutated=True,
                    reply=str(cli_trace.get("stdout") or "kilo-cli completed execution on workspace_model/."),
                    actions_taken=[f"Executed `{cli_trace.get('command')}`"],
                    cli_trace=cli_trace,
                    updated_model=reloaded,
                )
            except Exception:
                pass

    # ---------------------------------------------------------
    # Mode 3: Built-in Architect (Deterministic Engine)
    # ---------------------------------------------------------
    reply, actions, mutated, model = _process_builtin_agent(
        model=model,
        prompt=prompt,
        allow_mutations=allow_mutations,
    )

    return AgentExecutionResponse(
        mode_used=mode,
        mutated=mutated,
        reply=reply,
        actions_taken=actions,
        cli_trace=cli_trace,
        updated_model=model,
    )


def _process_builtin_agent(
    model: ProjectMetamodel,
    prompt: str,
    allow_mutations: bool = True,
) -> Tuple[str, List[str], bool, ProjectMetamodel]:
    p_lower = prompt.lower()
    mutated = False
    actions: List[str] = []

    # Check natural-language table/view/relation/column/subject-area mutations first
    parsed_mutation = _try_builtin_natural_language_mutations(model, prompt)
    if parsed_mutation:
        if not allow_mutations:
            reply = "RBAC Policy: Your active role does not permit structural model mutations."
        else:
            reply, actions = parsed_mutation
            mutated = True

    # Check pre-canned governance mutations
    elif any(k in p_lower for k in ("audit column", "rec_crtd_ts", "rec_updt_ts", "src_sys_cd")):
        if not allow_mutations:
            reply = "RBAC Policy: Your active role does not permit structural column mutations."
        else:
            reply, actions = _mutate_add_audit_columns(model, prompt)
            mutated = True
    elif any(k in p_lower for k in ("naming glossary", "naming standard", "standardize all physical", "apply glossary", "nsm")):
        if not allow_mutations:
            reply = "RBAC Policy: Your active role does not permit physical identifier refactoring."
        else:
            reply, actions = _mutate_apply_naming_glossary(model)
            mutated = True
    elif any(k in p_lower for k in ("star schema", "retail order", "dim_product", "dim_date")):
        if not allow_mutations:
            reply = "RBAC Policy: Your active role does not permit creating entities or relationships."
        else:
            reply, actions = _mutate_scaffold_star_schema(model, prompt)
            mutated = True
    elif any(k in p_lower for k in ("generate description", "undocumented column", "document all", "missing description")):
        if not allow_mutations:
            reply = "RBAC Policy: Your active role does not permit editing metadata descriptions."
        else:
            reply, actions = _mutate_generate_column_descriptions(model)
            mutated = True
    # Q&A intents
    elif any(k in p_lower for k in ("pii", "restricted", "confidential", "privacy", "gdpr", "sensitive")):
        reply, actions = _answer_pii_query(model)
    elif any(k in p_lower for k in ("lineage", "upstream", "downstream", "depend", "fct_claim")):
        reply, actions = _answer_lineage_query(model, prompt)
    elif any(k in p_lower for k in ("oracle", "missing index", "foreign key", "fk index", "unindexed")):
        reply, actions = _answer_oracle_fk_index_audit(model)
    else:
        reply, actions = _answer_general_summary(model)

    if mutated:
        write_dbt_artifacts_to_disk(model, settings.exported_dbt_dir)

    return reply, actions, mutated, model

