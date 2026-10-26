"""dbt Package & Artifact Compiler (sources.yml, schema.yml, and modular .sql models)."""
from pathlib import Path
from typing import Dict, List, Any
import yaml
from ..metamodel.schema import EntityModel, ProjectMetamodel


def _generate_sources_yml(model: ProjectMetamodel) -> str:
    """Build models/sources.yml mapping source and staging tables with freshness blocks."""
    schemas_map: Dict[str, List[EntityModel]] = {}
    for entity in model.entities.values():
        if entity.dbt_layer in ("source", "staging"):
            schema_key = (entity.database_schema or "RAW").upper()
            schemas_map.setdefault(schema_key, []).append(entity)

    # Also ensure at least one raw source exists so {{ source() }} references resolve cleanly
    if not schemas_map:
        for entity in model.entities.values():
            schema_key = (entity.database_schema or "CORE").upper()
            schemas_map.setdefault(schema_key, []).append(entity)

    sources_list: List[Dict[str, Any]] = []
    for schema_name, ents in schemas_map.items():
        tables_list: List[Dict[str, Any]] = []
        for ent in ents:
            cols_list = [
                {
                    "name": col.physical_name.upper(),
                    "description": col.description or f"{col.logical_name} column",
                    "meta": {
                        "logical_name": col.logical_name,
                        "pii_classification": col.pii_classification,
                    },
                }
                for col in ent.columns
            ]
            tables_list.append(
                {
                    "name": ent.physical_name.lower(),
                    "identifier": ent.physical_name.upper(),
                    "description": ent.description or f"Source feed for {ent.logical_name}",
                    "loaded_at_field": next(
                        (
                            c.physical_name.upper()
                            for c in ent.columns
                            if "TS" in c.physical_name.upper() or "DATE" in c.physical_name.upper()
                        ),
                        "INGESTED_TS",
                    ),
                    "freshness": {
                        "warn_after": {
                            "count": max(1, ent.data_contract.freshness_sla_hours // 2),
                            "period": "hour",
                        },
                        "error_after": {
                            "count": ent.data_contract.freshness_sla_hours,
                            "period": "hour",
                        },
                    },
                    "columns": cols_list,
                }
            )

        sources_list.append(
            {
                "name": schema_name.lower(),
                "database": "ENTERPRISE_RAW_DB",
                "schema": schema_name,
                "description": f"Upstream raw source tables in schema {schema_name}",
                "tables": tables_list,
            }
        )

    payload = {"version": 2, "sources": sources_list}
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


def _generate_schema_yml(model: ProjectMetamodel) -> str:
    """
    Build models/schema.yml including model descriptions, column descriptions,
    meta tags (pii_classification, logical_name, domain, retention_policy, data_contract), and automated data tests.
    """
    # Map child_column_id -> (parent_entity, parent_column)
    fk_lookup: Dict[str, Any] = {}
    for rel in model.relationships.values():
        p_ent = model.entities.get(rel.parent_entity_id)
        if not p_ent:
            continue
        p_col = next((c for c in p_ent.columns if c.id == rel.parent_column_id), None)
        if p_col:
            fk_lookup[rel.child_column_id] = (p_ent, p_col)

    models_list: List[Dict[str, Any]] = []
    for ent in model.entities.values():
        cols_yaml: List[Dict[str, Any]] = []
        for col in ent.columns:
            tests: List[Any] = []
            # PK tests
            if col.is_pk:
                tests.append("unique")
                tests.append("not_null")
            elif not col.is_nullable:
                tests.append("not_null")

            # Custom/domain dbt tests
            for t in col.dbt_tests:
                if t not in tests:
                    tests.append(t)

            # FK relationship test
            if col.id in fk_lookup:
                p_ent, p_col = fk_lookup[col.id]
                tests.append(
                    {
                        "relationships": {
                            "to": f"ref('{p_ent.physical_name.lower()}')",
                            "field": p_col.physical_name.upper(),
                        }
                    }
                )

            domain_obj = model.domains.get(col.domain_id) if col.domain_id else None
            col_entry: Dict[str, Any] = {
                "name": col.physical_name.upper(),
                "description": col.description or f"{col.logical_name}",
                "meta": {
                    "logical_name": col.logical_name,
                    "pii_classification": col.pii_classification,
                    "metadata_status": col.metadata_status,
                    "domain": domain_obj.name if domain_obj else "Custom",
                },
            }
            if tests:
                col_entry["tests"] = tests
            cols_yaml.append(col_entry)

        models_list.append(
            {
                "name": ent.physical_name.lower(),
                "description": ent.description or f"{ent.logical_name} ({ent.subject_area})",
                "meta": {
                    "logical_name": ent.logical_name,
                    "subject_area": ent.subject_area,
                    "stereotype": ent.modeling_stereotype,
                    "grain": ent.grain_statement,
                    "dbt_layer": ent.dbt_layer,
                    "materialized": ent.dbt_materialization,
                    "owner": ent.data_contract.data_owner,
                    "freshness_sla_hours": ent.data_contract.freshness_sla_hours,
                    "retention_framework": ent.retention_policy.regulatory_framework,
                    "retention_days_hot": ent.retention_policy.active_retention_days,
                    "retention_days_archive": ent.retention_policy.archive_retention_days,
                },
                "columns": cols_yaml,
            }
        )

    payload = {"version": 2, "models": models_list}
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


def _generate_model_sql(entity: EntityModel, model: ProjectMetamodel) -> str:
    """
    Generate modular dbt Jinja SQL with {{ config(...) }} and {{ source() }} or {{ ref() }} CTEs
    based on upstream relationships.
    """
    tags_list = list(dict.fromkeys([entity.subject_area.lower(), entity.dbt_layer] + entity.tags))
    tags_repr = "[" + ", ".join(f"'{t}'" for t in tags_list) + "]"

    config_parts = [f"    materialized='{entity.dbt_materialization}'"]
    if entity.dbt_unique_key or any(c.is_pk for c in entity.columns):
        uk = entity.dbt_unique_key or next(c.physical_name.upper() for c in entity.columns if c.is_pk)
        config_parts.append(f"    unique_key='{uk}'")
    config_parts.append(f"    schema='{entity.database_schema.lower()}'")
    config_parts.append(f"    tags={tags_repr}")

    config_block = "{{\n  config(\n" + ",\n".join(config_parts) + "\n  )\n}}"

    # Discover upstream parent entities linked to this entity
    parent_entities: List[EntityModel] = []
    for rel in model.relationships.values():
        if rel.child_entity_id == entity.id and rel.parent_entity_id in model.entities:
            p_ent = model.entities[rel.parent_entity_id]
            if p_ent.id != entity.id and all(x.id != p_ent.id for x in parent_entities):
                parent_entities.append(p_ent)

    ctes: List[str] = []
    if entity.dbt_layer in ("source", "staging"):
        src_schema = (entity.database_schema or "staging").lower()
        ctes.append(
            f"source_data AS (\n"
            f"    SELECT *\n"
            f"    FROM {{{{ source('{src_schema}', '{entity.physical_name.lower()}') }}}}\n"
            f")"
        )
        base_cte = "source_data"
    else:
        src_schema = (entity.database_schema or "core").lower()
        ctes.append(
            f"base_{entity.physical_name.lower()} AS (\n"
            f"    SELECT *\n"
            f"    FROM {{{{ source('{src_schema}', '{entity.physical_name.lower()}') }}}}\n"
            f")"
        )
        base_cte = f"base_{entity.physical_name.lower()}"

    for p_ent in parent_entities:
        p_alias = p_ent.physical_name.lower()
        ctes.append(
            f"ref_{p_alias} AS (\n"
            f"    SELECT *\n"
            f"    FROM {{{{ ref('{p_alias}') }}}}\n"
            f")"
        )

    select_cols: List[str] = []
    for col in entity.columns:
        col_phys = col.physical_name.upper()
        dtype_sf = col.data_type_snowflake or "VARCHAR(255)"
        comment = f" -- {col.logical_name}" + (
            f" [{col.pii_classification}]" if col.pii_classification != "NONE" else ""
        )
        select_cols.append(f"        CAST({col_phys} AS {dtype_sf}) AS {col_phys},{comment}")

    if select_cols:
        # Remove trailing comma before inline comment on the last column
        last_line = select_cols[-1]
        idx = last_line.find(", --")
        if idx != -1:
            select_cols[-1] = last_line[:idx] + last_line[idx + 1 :]

    incremental_filter = ""
    if entity.dbt_materialization == "incremental":
        ts_col = next(
            (
                c.physical_name.upper()
                for c in entity.columns
                if "TS" in c.physical_name.upper() or "DT" in c.physical_name.upper()
            ),
            None,
        )
        if ts_col:
            incremental_filter = (
                f"\n    {{% if is_incremental() %}}\n"
                f"    WHERE {ts_col} > (SELECT COALESCE(MAX({ts_col}), '1900-01-01') FROM {{{{ this }}}})\n"
                f"    {{% endif %}}"
            )

    ctes.append(
        f"final AS (\n"
        f"    SELECT\n"
        + "\n".join(select_cols)
        + f"\n    FROM {base_cte}{incremental_filter}\n)"
    )

    sql_lines = [
        f"-- dbt Model: {entity.physical_name.lower()}",
        f"-- Logical Entity: {entity.logical_name} | Subject Area: {entity.subject_area}",
        config_block,
        "",
        "WITH " + ",\n\n".join(ctes),
        "",
        "SELECT * FROM final",
        "",
    ]
    return "\n".join(sql_lines)


def compile_dbt_artifacts(model: ProjectMetamodel) -> Dict[str, str]:
    """
    Generate the complete dbt artifact dictionary mapping relative file paths to contents:
      - dbt_project.yml
      - models/sources.yml
      - models/schema.yml
      - models/<subject_area>/<model_name>.sql
    """
    artifacts: Dict[str, str] = {}

    dbt_project_yml = {
        "name": "metaforge_enterprise_dw",
        "version": model.version,
        "config-version": 2,
        "profile": "metaforge_snowflake",
        "model-paths": ["models"],
        "models": {
            "metaforge_enterprise_dw": {
                "+materialized": "table",
            }
        },
    }
    artifacts["dbt_project.yml"] = yaml.safe_dump(dbt_project_yml, sort_keys=False)
    artifacts["models/sources.yml"] = _generate_sources_yml(model)
    artifacts["models/schema.yml"] = _generate_schema_yml(model)

    for entity in model.entities.values():
        sa_folder = (entity.subject_area or "core").lower().replace(" ", "_")
        model_filename = f"{entity.physical_name.lower()}.sql"
        rel_path = f"models/{sa_folder}/{model_filename}"
        artifacts[rel_path] = _generate_model_sql(entity, model)

    return artifacts


def write_dbt_artifacts_to_disk(model: ProjectMetamodel, output_dir: Path) -> List[str]:
    """Write all compiled dbt files to workspace_model/exported_dbt/."""
    artifacts = compile_dbt_artifacts(model)
    written_files: List[str] = []
    for rel_path, content in artifacts.items():
        target_path = output_dir / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        written_files.append(rel_path)
    return written_files
