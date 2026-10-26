"""Unit tests for DDL Reverse Engineering, Complete Compare, and Agentic Control Plane."""
from backend.app.metamodel.seed import build_default_project
from backend.app.metamodel.schema import ColumnModel, TargetDialect
from backend.app.reverse_eng.ddl_parser import parse_ddl_to_metamodel
from backend.app.reverse_eng.complete_compare import run_complete_compare
from backend.app.agent.llm_service import execute_agent_prompt


def test_reverse_engineer_ddl():
    sample_ddl = """
    CREATE TABLE CORE.DIM_BROKER (
        BROKER_ID NUMBER(38,0) PRIMARY KEY,
        BROKER_CODE VARCHAR(30) NOT NULL,
        BROKER_EMAIL VARCHAR(255),
        COMMISSION_AMT NUMBER(18,2) NOT NULL
    );

    CREATE TABLE CORE.FCT_BROKER_COMMISSION (
        COMM_ID NUMBER(38,0) PRIMARY KEY,
        BROKER_ID NUMBER(38,0) NOT NULL,
        PAID_AMT NUMBER(18,2) NOT NULL
    );

    ALTER TABLE CORE.FCT_BROKER_COMMISSION
        ADD CONSTRAINT FK_COMM_BROKER FOREIGN KEY (BROKER_ID)
        REFERENCES CORE.DIM_BROKER (BROKER_ID);
    """
    entities, relationships = parse_ddl_to_metamodel(
        sample_ddl, dialect=TargetDialect.SNOWFLAKE, default_subject_area="Finance"
    )
    assert len(entities) == 2
    assert len(relationships) == 1
    names = {e.physical_name for e in entities}
    assert "DIM_BROKER" in names
    assert "FCT_BROKER_COMMISSION" in names


def test_reverse_engineer_complex_view_with_cte_and_lineage():
    complex_ddl = """
    CREATE TABLE FINANCE.DIM_REINSURER (
        REINSURER_ID NUMBER(38,0) PRIMARY KEY,
        REINSURER_LEGAL_NM VARCHAR(200) NOT NULL
    );

    CREATE TABLE FINANCE.FCT_CEDED_PREMIUM (
        CEDED_TXN_ID NUMBER(38,0) PRIMARY KEY,
        REINSURER_ID NUMBER(38,0) NOT NULL,
        CEDED_PREM_AMT NUMBER(18,2) NOT NULL
    );

    CREATE OR REPLACE VIEW FINANCE.VW_REINSURER_EXPOSURE AS
    WITH AGG_CTE AS (
        SELECT
            REINSURER_ID,
            COUNT(CEDED_TXN_ID) AS TXN_CNT,
            SUM(CEDED_PREM_AMT) AS TOTAL_CEDED_AMT
        FROM FINANCE.FCT_CEDED_PREMIUM
        GROUP BY REINSURER_ID
    )
    SELECT
        R.REINSURER_ID AS REINSURER_ID,
        R.REINSURER_LEGAL_NM AS REINSURER_LEGAL_NM,
        COALESCE(A.TXN_CNT, 0) AS CEDED_TXN_COUNT,
        COALESCE(A.TOTAL_CEDED_AMT, 0) AS TOTAL_CEDED_PREMIUM_AMT,
        CASE WHEN A.TOTAL_CEDED_AMT > 100000 THEN 'HIGH' ELSE 'LOW' END AS RISK_TIER_CD
    FROM FINANCE.DIM_REINSURER R
    LEFT JOIN AGG_CTE A ON R.REINSURER_ID = A.REINSURER_ID;
    """
    entities, relationships = parse_ddl_to_metamodel(
        complex_ddl, dialect=TargetDialect.SNOWFLAKE, default_subject_area="Finance"
    )
    assert len(entities) == 3
    view_ent = next(e for e in entities if e.physical_name == "VW_REINSURER_EXPOSURE")
    assert view_ent.entity_type == "view"
    col_names = {c.physical_name for c in view_ent.columns}
    assert "REINSURER_ID" in col_names
    assert "TOTAL_CEDED_PREMIUM_AMT" in col_names
    assert "RISK_TIER_CD" in col_names

    # Verify UPSTREAM_LINEAGE relationships from DIM_REINSURER and FCT_CEDED_PREMIUM into VW_REINSURER_EXPOSURE
    lineage_rels = [r for r in relationships if r.rel_type.value == "upstream_lineage"]
    assert len(lineage_rels) == 2


def test_complete_compare_diff_and_alter_generation():
    baseline = build_default_project()
    current = build_default_project()

    # Modify a column type and add a new column on DIM_CUSTOMER in current canvas model
    cust = current.entities["ent-dim-customer"]
    cust.columns[1].data_type_snowflake = "VARCHAR(500)"
    cust.columns.append(
        ColumnModel(
            logical_name="Customer Loyalty Tier Code",
            physical_name="CUST_LOYALTY_TIER_CD",
            data_type_snowflake="VARCHAR(20)",
            data_type_sql_server="VARCHAR(20)",
            data_type_oracle="VARCHAR2(20 CHAR)",
            is_nullable=True,
        )
    )

    diff_sf = run_complete_compare(current, baseline, dialect=TargetDialect.SNOWFLAKE)
    assert diff_sf.total_differences >= 2
    assert "DIM_CUSTOMER" in diff_sf.modified_tables
    assert "ALTER TABLE CORE.DIM_CUSTOMER ADD COLUMN CUST_LOYALTY_TIER_CD VARCHAR(20) NULL;" in diff_sf.alter_script
    assert "ALTER TABLE CORE.DIM_CUSTOMER ALTER COLUMN CUST_FULL_NM SET DATA TYPE VARCHAR(500);" in diff_sf.alter_script

    diff_ora = run_complete_compare(current, baseline, dialect=TargetDialect.ORACLE)
    assert "ALTER TABLE CORE_DATA.DIM_CUSTOMER ADD (CUST_LOYALTY_TIER_CD VARCHAR2(20 CHAR) NULL);" in diff_ora.alter_script


def test_agent_qa_and_mutations():
    model = build_default_project()

    # 1. Q&A PII
    res_pii = execute_agent_prompt(model, "Which tables contain Restricted PII?", mode="builtin-llm")
    assert not res_pii.mutated
    assert "CUST_FULL_NM" in res_pii.reply
    assert "RESTRICTED_PII" in res_pii.reply

    # 2. Q&A Lineage
    res_lin = execute_agent_prompt(
        model, "Show me the upstream and downstream lineage of FCT_CLAIM", mode="builtin-llm"
    )
    assert not res_lin.mutated
    assert "DIM_POLICY" in res_lin.reply
    assert "STG_RAW_CLAIMS" in res_lin.reply

    # 3. Bulk Mutation: Add audit columns to Claims subject area
    res_audit = execute_agent_prompt(
        model,
        "Add standard enterprise audit columns (REC_CRTD_TS, REC_UPDT_TS, SRC_SYS_CD) to all tables in the Claims subject area.",
        mode="builtin-llm",
    )
    assert res_audit.mutated
    fct_cols = {c.physical_name for c in model.entities["ent-fct-claim"].columns}
    assert "REC_UPDT_TS" in fct_cols
    assert "SRC_SYS_CD" in fct_cols

    # 4. Bulk Mutation: Create Star Schema for Retail Orders
    res_star = execute_agent_prompt(
        model,
        "Create a Star Schema for Retail Orders with 1 Fact table and 3 Dimension tables (DIM_CUSTOMER, DIM_PRODUCT, DIM_DATE) and wire the non-identifying foreign keys.",
        mode="builtin-llm",
    )
    assert res_star.mutated
    phys_tables = {e.physical_name for e in model.entities.values()}
    assert "FCT_RETAIL_ORDER" in phys_tables
    assert "DIM_PRODUCT" in phys_tables
    assert "DIM_DATE" in phys_tables
