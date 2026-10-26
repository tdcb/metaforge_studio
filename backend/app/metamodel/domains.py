"""Enterprise Domains Manager."""
from typing import Dict, List
from .schema import EnterpriseDomain, ProjectMetamodel


DEFAULT_ENTERPRISE_DOMAINS: Dict[str, EnterpriseDomain] = {
    "dom-surrogate-id": EnterpriseDomain(
        id="dom-surrogate-id",
        name="Surrogate_ID",
        logical_type="Identifier (64-bit Integer)",
        snowflake_type="NUMBER(38,0)",
        sql_server_type="BIGINT",
        oracle_type="NUMBER(19,0)",
        nullable_default=False,
        dbt_tests=["not_null"],
        description="Enterprise surrogate key domain for dimension and fact primary/foreign keys.",
    ),
    "dom-monetary-amount": EnterpriseDomain(
        id="dom-monetary-amount",
        name="Monetary_Amount",
        logical_type="Currency / High-Precision Decimal",
        snowflake_type="NUMBER(18,2)",
        sql_server_type="DECIMAL(18,2)",
        oracle_type="NUMBER(18,2)",
        nullable_default=False,
        dbt_tests=["not_null"],
        description="Standard financial currency amount with 18 digits precision and 2 decimal places.",
    ),
    "dom-standard-code": EnterpriseDomain(
        id="dom-standard-code",
        name="Standard_Code",
        logical_type="Reference / ISO Code String",
        snowflake_type="VARCHAR(30)",
        sql_server_type="VARCHAR(30)",
        oracle_type="VARCHAR2(30 CHAR)",
        nullable_default=False,
        dbt_tests=["not_null"],
        description="Standardized enterprise reference code, status code, or ISO classification.",
    ),
    "dom-audit-timestamp": EnterpriseDomain(
        id="dom-audit-timestamp",
        name="Audit_Timestamp",
        logical_type="UTC Audit Timestamp",
        snowflake_type="TIMESTAMP_NTZ(9)",
        sql_server_type="DATETIME2(7)",
        oracle_type="TIMESTAMP(6)",
        nullable_default=False,
        dbt_tests=["not_null"],
        description="Enterprise system audit timestamp capturing creation and modification events.",
    ),
}


def cascade_domain_to_model(model: ProjectMetamodel, domain: EnterpriseDomain) -> int:
    """
    Upsert an EnterpriseDomain on the ProjectMetamodel and cascade its physical
    types and default dbt_tests to every column bound to that domain_id.
    Returns the number of columns updated.
    """
    model.domains[domain.id] = domain
    updated_count = 0
    for entity in model.entities.values():
        for col in entity.columns:
            if col.domain_id == domain.id:
                col.data_type_snowflake = domain.snowflake_type
                col.data_type_sql_server = domain.sql_server_type
                col.data_type_oracle = domain.oracle_type
                # Merge domain dbt_tests without losing existing custom tests
                merged_tests = list(dict.fromkeys(col.dbt_tests + domain.dbt_tests))
                if col.is_pk and "unique" not in merged_tests:
                    merged_tests.insert(0, "unique")
                col.dbt_tests = merged_tests
                updated_count += 1
    return updated_count


def apply_all_domains(model: ProjectMetamodel) -> int:
    """Ensure all columns with a valid domain_id have synchronized physical types."""
    total = 0
    for domain in list(model.domains.values()):
        total += cascade_domain_to_model(model, domain)
    return total
