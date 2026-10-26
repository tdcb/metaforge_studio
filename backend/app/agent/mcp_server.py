"""Model Context Protocol (MCP) Server & Tool Definitions for MetaForge Studio.

Compliant with the MCP 2024-11-05 Specification (JSON-RPC 2.0).
Provides capabilities for external AI coding assistants (Claude Code, Cursor, Kiro, Gemini CLI, Windsurf):
  - Model inspection (summary, table schema, metadata search)
  - Schema design (add/modify/drop tables, columns, relationships, views)
  - Multi-dialect DDL compilation (Snowflake, SQL Server, Oracle)
  - Autonomous dbt project generation (models, schema.yml, sources.yml)
  - Complete Compare (AST schema diffing and safe ALTER script generation)
  - Reverse engineering (SQLGlot DDL parsing)
  - Enterprise Naming Standards Glossary (NSM) translation
  - Data Profiling & DQ recommendations
  - MCP Resources (model://canonical, model://ddl/*, model://dbt/*, model://datacontract)
  - MCP Prompts (design_star_schema, audit_pii_and_governance, refactor_kimball_scd2)
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from typing import Any, Callable, Dict, List, Optional

from ..compilers.dbt_generator import compile_dbt_artifacts, write_dbt_artifacts_to_disk
from ..compilers.oracle import compile_oracle_ddl
from ..compilers.snowflake import compile_snowflake_ddl
from ..compilers.sql_server import compile_sql_server_ddl
from ..compilers.view_builder import compile_view_ddl, synthesize_view_select_sql
from ..config import settings
from ..metamodel.glossary import apply_glossary_to_project
from ..metamodel.governance_engine import (
    apply_modeling_pattern,
    apply_recommended_dq_rules,
    compile_open_data_contract_yaml,
    run_data_profiler,
)
from ..metamodel.schema import (
    Cardinality,
    ColumnModel,
    EntityModel,
    ProjectMetamodel,
    RelationshipModel,
    RelationshipType,
    TargetDialect,
)
from ..metamodel.seed import ensure_seed_workspace, save_workspace_model
from ..reverse_eng.complete_compare import run_complete_compare
from ..reverse_eng.ddl_parser import parse_ddl_to_metamodel
from .mutation_engine import execute_mutations

logger = logging.getLogger("metaforge.mcp")


class MCPToolRegistry:
    """Enterprise Model Context Protocol (MCP) Registry for MetaForge Studio."""

    def __init__(self) -> None:
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.resources: Dict[str, Dict[str, Any]] = {}
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self._register_all_tools()
        self._register_all_resources()
        self._register_all_prompts()

    def _register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        self.tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "handler": handler,
        }

    def _register_all_tools(self) -> None:
        # 1. get_model_summary
        self._register_tool(
            name="get_model_summary",
            description="Returns high-level summary of entities, views, relationships, subject areas, and domains in the canonical model.",
            input_schema={"type": "object", "properties": {}},
            handler=self.get_model_summary,
        )

        # 2. get_model
        self._register_tool(
            name="get_model",
            description="Returns the active canonical model JSON, optionally filtered by a specific subject area.",
            input_schema={
                "type": "object",
                "properties": {
                    "subject_area": {
                        "type": "string",
                        "description": "Optional subject area to filter entities and relationships.",
                    }
                },
            },
            handler=self.get_model,
        )

        # 3. get_table_schema
        self._register_tool(
            name="get_table_schema",
            description="Returns detailed column specifications, data types across dialects, primary/foreign key flags, nullability, descriptions, and PII classifications for a table.",
            input_schema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Physical or logical name of the table to inspect (e.g. 'DIM_CUSTOMER').",
                    }
                },
                "required": ["table_name"],
            },
            handler=self.get_table_schema,
        )

        # 4. search_metadata
        self._register_tool(
            name="search_metadata",
            description="Search tables, views, and columns across the canonical model by keyword, PII classification, or subject area.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keyword to search in physical names, logical names, or descriptions.",
                    },
                    "pii_classification": {
                        "type": "string",
                        "description": "Filter by classification: RESTRICTED_PII, CONFIDENTIAL_PII, INTERNAL, PUBLIC.",
                    },
                    "subject_area": {
                        "type": "string",
                        "description": "Filter by subject area name.",
                    },
                },
            },
            handler=self.search_metadata,
        )

        # 5. add_table
        self._register_tool(
            name="add_table",
            description="Add a new table (entity) to the canonical data model with column definitions, data types, primary keys, and description.",
            input_schema={
                "type": "object",
                "properties": {
                    "physical_name": {
                        "type": "string",
                        "description": "Physical uppercase table name (e.g. 'DIM_PRODUCT').",
                    },
                    "logical_name": {
                        "type": "string",
                        "description": "Business friendly name (e.g. 'Product Dimension').",
                    },
                    "subject_area": {
                        "type": "string",
                        "description": "Subject area group (e.g. 'Core', 'Retail', 'Finance'). Default is 'Core'.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Business definition and purpose of this table.",
                    },
                    "columns": {
                        "type": "array",
                        "description": "List of column objects to create in this table.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "physical_name": {"type": "string"},
                                "logical_name": {"type": "string"},
                                "data_type": {
                                    "type": "string",
                                    "description": "e.g. NUMBER(38,0), VARCHAR(255), TIMESTAMP_NTZ, BOOLEAN.",
                                },
                                "is_pk": {"type": "boolean"},
                                "is_nullable": {"type": "boolean"},
                                "description": {"type": "string"},
                                "pii_classification": {"type": "string"},
                            },
                            "required": ["physical_name"],
                        },
                    },
                },
                "required": ["physical_name"],
            },
            handler=self.add_table,
        )

        # 6. modify_table
        self._register_tool(
            name="modify_table",
            description="Modify an existing table in the canonical model: add new columns, drop columns, modify column properties, or update descriptions.",
            input_schema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Physical name of the table to modify.",
                    },
                    "description": {
                        "type": "string",
                        "description": "New table description (optional).",
                    },
                    "columns_to_add": {
                        "type": "array",
                        "description": "Columns to add to this table.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "physical_name": {"type": "string"},
                                "logical_name": {"type": "string"},
                                "data_type": {"type": "string"},
                                "is_pk": {"type": "boolean"},
                                "is_nullable": {"type": "boolean"},
                                "description": {"type": "string"},
                                "pii_classification": {"type": "string"},
                            },
                            "required": ["physical_name"],
                        },
                    },
                    "columns_to_drop": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of physical column names to drop.",
                    },
                },
                "required": ["table_name"],
            },
            handler=self.modify_table,
        )

        # 7. drop_table
        self._register_tool(
            name="drop_table",
            description="Safely removes a table from the canonical model and cascades the deletion of connected relationships.",
            input_schema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Physical name of the table to drop.",
                    }
                },
                "required": ["table_name"],
            },
            handler=self.drop_table,
        )

        # 8. add_relationship
        self._register_tool(
            name="add_relationship",
            description="Create a Crow's Foot relationship constraint between two tables. Supports Mandatory (Solid) vs Optional (Dashed) enforcement and cardinalities.",
            input_schema={
                "type": "object",
                "properties": {
                    "parent_table": {
                        "type": "string",
                        "description": "Physical name of the parent / referenced table (e.g. 'DIM_CUSTOMER').",
                    },
                    "child_table": {
                        "type": "string",
                        "description": "Physical name of the child / referencing table (e.g. 'FCT_ORDER').",
                    },
                    "parent_column": {
                        "type": "string",
                        "description": "Primary key column in parent table (e.g. 'CUSTOMER_ID').",
                    },
                    "child_column": {
                        "type": "string",
                        "description": "Foreign key column in child table (e.g. 'CUSTOMER_ID').",
                    },
                    "name": {
                        "type": "string",
                        "description": "Constraint name (e.g. 'FK_FCT_ORDER_DIM_CUSTOMER'). Auto-generated if omitted.",
                    },
                    "cardinality": {
                        "type": "string",
                        "enum": ["1:N", "1:1", "0:N", "0:1"],
                        "description": "Cardinality notation. Default is '1:N'.",
                    },
                    "is_mandatory": {
                        "type": "boolean",
                        "description": "True for Mandatory (Solid line, FK is NOT NULL); False for Optional (Dashed line, FK is NULLABLE). Default is True.",
                    },
                    "rel_type": {
                        "type": "string",
                        "enum": ["non_identifying", "identifying", "upstream_lineage"],
                        "description": "Relationship type. Default is 'non_identifying'.",
                    },
                },
                "required": ["parent_table", "child_table"],
            },
            handler=self.add_relationship,
        )

        # 9. drop_relationship
        self._register_tool(
            name="drop_relationship",
            description="Remove a relationship constraint by name or by specifying the parent and child tables.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Relationship constraint name."},
                    "parent_table": {"type": "string"},
                    "child_table": {"type": "string"},
                },
            },
            handler=self.drop_relationship,
        )

        # 10. add_view
        self._register_tool(
            name="add_view",
            description="Create an analytical SQL View or Materialized View in the canonical model with background SELECT SQL and upstream lineage mapping.",
            input_schema={
                "type": "object",
                "properties": {
                    "physical_name": {
                        "type": "string",
                        "description": "Physical view name (e.g. 'VW_MONTHLY_SALES_SUMMARY').",
                    },
                    "view_sql": {
                        "type": "string",
                        "description": "SELECT SQL query definition for the view.",
                    },
                    "logical_name": {"type": "string"},
                    "subject_area": {"type": "string"},
                    "is_materialized": {"type": "boolean", "default": False},
                    "columns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "physical_name": {"type": "string"},
                                "data_type": {"type": "string"},
                                "source_expression": {"type": "string"},
                            },
                            "required": ["physical_name"],
                        },
                    },
                },
                "required": ["physical_name", "view_sql"],
            },
            handler=self.add_view,
        )

        # 11. apply_mutations
        self._register_tool(
            name="apply_mutations",
            description="Atomically execute a list of structured mutation actions on the model (e.g. batch adding tables, columns, relations, and views in one call).",
            input_schema={
                "type": "object",
                "properties": {
                    "mutations": {
                        "type": "array",
                        "description": "List of mutation action objects (add_table, add_column, add_relationship, add_view, etc.).",
                        "items": {"type": "object"},
                    }
                },
                "required": ["mutations"],
            },
            handler=self.apply_mutations,
        )

        # 12. compile_ddl
        self._register_tool(
            name="compile_ddl",
            description="Compile the canonical data model into production-grade executable DDL SQL for Snowflake, Microsoft SQL Server (T-SQL), or Oracle.",
            input_schema={
                "type": "object",
                "properties": {
                    "dialect": {
                        "type": "string",
                        "enum": ["snowflake", "sql_server", "oracle"],
                        "description": "Target SQL dialect. Default is 'snowflake'.",
                    },
                    "subject_area": {
                        "type": "string",
                        "description": "Optional subject area to compile only a subset of entities.",
                    },
                },
            },
            handler=self.compile_ddl,
        )

        # 13. generate_dbt_project
        self._register_tool(
            name="generate_dbt_project",
            description="Compile the model into a complete, modular dbt project (models/staging/*.sql, models/marts/*.sql, schema.yml with test assertions, sources.yml, and datacontract.yaml).",
            input_schema={
                "type": "object",
                "properties": {
                    "write_to_disk": {
                        "type": "boolean",
                        "description": "Whether to write the generated files to workspace_model/exported_dbt/. Default is True.",
                    }
                },
            },
            handler=self.generate_dbt_project,
        )

        # 14. run_complete_compare
        self._register_tool(
            name="run_complete_compare",
            description="Run AST schema diffing between the active canonical model and a target SQL DDL script, generating safe non-destructive ALTER scripts.",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ddl": {
                        "type": "string",
                        "description": "Raw CREATE TABLE / VIEW SQL script to compare against.",
                    },
                    "dialect": {
                        "type": "string",
                        "enum": ["snowflake", "sql_server", "oracle"],
                        "description": "SQL dialect. Default is 'snowflake'.",
                    },
                },
                "required": ["target_ddl"],
            },
            handler=self.run_complete_compare_tool,
        )

        # 15. reverse_engineer_ddl
        self._register_tool(
            name="reverse_engineer_ddl",
            description="Parse raw SQL DDL statements (Snowflake, T-SQL, Postgres) using SQLGlot AST and import tables, columns, and foreign keys into the visual canvas.",
            input_schema={
                "type": "object",
                "properties": {
                    "ddl_script": {
                        "type": "string",
                        "description": "Raw SQL script containing CREATE TABLE / VIEW statements.",
                    },
                    "dialect": {
                        "type": "string",
                        "enum": ["snowflake", "sql_server", "oracle"],
                        "default": "snowflake",
                    },
                    "subject_area": {
                        "type": "string",
                        "description": "Subject area to place imported tables. Default is 'Staging'.",
                    },
                    "merge_into_project": {
                        "type": "boolean",
                        "description": "If True, merge with existing model. If False, replace current model. Default is True.",
                    },
                },
                "required": ["ddl_script"],
            },
            handler=self.reverse_engineer_ddl,
        )

        # 16. apply_naming_glossary
        self._register_tool(
            name="apply_naming_glossary",
            description="Translate and standardize all logical and physical entity and column names using the Enterprise Naming Standards Glossary (NSM).",
            input_schema={
                "type": "object",
                "properties": {
                    "overwrite_existing": {
                        "type": "boolean",
                        "description": "Whether to re-standardize already populated physical names. Default is True.",
                    }
                },
            },
            handler=self.apply_naming_glossary,
        )

        # 17. profile_data
        self._register_tool(
            name="profile_data",
            description="Run the Data Profiler across a table or the entire model to detect volumetrics, nullability ratios, distinct counts, and recommended DQ rules.",
            input_schema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Optional physical table name to profile.",
                    }
                },
            },
            handler=self.profile_data,
        )

    def _register_all_resources(self) -> None:
        self.resources = {
            "model://canonical": {
                "uri": "model://canonical",
                "name": "Canonical Metamodel",
                "description": "Full canonical model JSON containing entities, columns, relationships, views, and subject areas.",
                "mimeType": "application/json",
            },
            "model://ddl/snowflake": {
                "uri": "model://ddl/snowflake",
                "name": "Snowflake DDL",
                "description": "Production Snowflake DDL SQL compiled from the active metamodel.",
                "mimeType": "text/x-sql",
            },
            "model://ddl/sql_server": {
                "uri": "model://ddl/sql_server",
                "name": "Microsoft SQL Server DDL",
                "description": "Production Microsoft SQL Server (T-SQL) DDL compiled from the active metamodel.",
                "mimeType": "text/x-sql",
            },
            "model://ddl/oracle": {
                "uri": "model://ddl/oracle",
                "name": "Oracle DDL",
                "description": "Production Oracle Database (PL/SQL) DDL compiled from the active metamodel.",
                "mimeType": "text/x-sql",
            },
            "model://dbt/schema": {
                "uri": "model://dbt/schema",
                "name": "dbt schema.yml",
                "description": "Compiled dbt schema documentation and test assertions.",
                "mimeType": "text/yaml",
            },
            "model://dbt/sources": {
                "uri": "model://dbt/sources",
                "name": "dbt sources.yml",
                "description": "Compiled dbt staging source definitions.",
                "mimeType": "text/yaml",
            },
            "model://datacontract": {
                "uri": "model://datacontract",
                "name": "Open Data Contract YAML",
                "description": "Compiled Open Data Contract specification with SLA and column definitions.",
                "mimeType": "text/yaml",
            },
        }

    def _register_all_prompts(self) -> None:
        self.prompts = {
            "design_star_schema": {
                "name": "design_star_schema",
                "description": "Design a Kimball star schema (Fact table and conforming Dimensions) for a business process.",
                "arguments": [
                    {
                        "name": "business_process",
                        "description": "Business process name (e.g. 'E-Commerce Order Fulfillment', 'Patient Hospitalization', 'Policy Claims').",
                        "required": True,
                    }
                ],
            },
            "audit_pii_and_governance": {
                "name": "audit_pii_and_governance",
                "description": "Audit all columns in the canonical model for sensitive PII (emails, phone numbers, SSNs, credit cards) and recommend classifications and masking.",
                "arguments": [],
            },
            "refactor_kimball_scd2": {
                "name": "refactor_kimball_scd2",
                "description": "Refactor a target dimension table to support Kimball Slowly Changing Dimension (SCD) Type 2 tracking.",
                "arguments": [
                    {
                        "name": "table_name",
                        "description": "Physical table name of the dimension to refactor (e.g. 'DIM_CUSTOMER').",
                        "required": True,
                    }
                ],
            },
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["inputSchema"],
            }
            for t in self.tools.values()
        ]

    def list_resources(self) -> List[Dict[str, Any]]:
        return list(self.resources.values())

    def read_resource(self, uri: str) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        if uri == "model://canonical":
            return {
                "uri": uri,
                "mimeType": "application/json",
                "text": model.model_dump_json(indent=2),
            }
        elif uri == "model://ddl/snowflake":
            ddl = compile_snowflake_ddl(model)
            return {"uri": uri, "mimeType": "text/x-sql", "text": ddl}
        elif uri == "model://ddl/sql_server":
            ddl = compile_sql_server_ddl(model)
            return {"uri": uri, "mimeType": "text/x-sql", "text": ddl}
        elif uri == "model://ddl/oracle":
            ddl = compile_oracle_ddl(model)
            return {"uri": uri, "mimeType": "text/x-sql", "text": ddl}
        elif uri in ("model://dbt/schema", "model://dbt/sources"):
            dbt_files = compile_dbt_artifacts(model)
            fname = "schema.yml" if uri == "model://dbt/schema" else "sources.yml"
            return {"uri": uri, "mimeType": "text/yaml", "text": dbt_files.get(fname, "")}
        elif uri == "model://datacontract":
            contract = compile_open_data_contract_yaml(model)
            return {"uri": uri, "mimeType": "text/yaml", "text": contract}
        else:
            raise ValueError(f"Unknown resource URI: {uri}")

    def list_prompts(self) -> List[Dict[str, Any]]:
        return list(self.prompts.values())

    def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = arguments or {}
        if name == "design_star_schema":
            bp = args.get("business_process", "Retail Orders")
            return {
                "description": f"Design star schema for {bp}",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": (
                                f"Design a production Kimball Star Schema for '{bp}'.\n"
                                "1. Inspect current model with get_model_summary.\n"
                                "2. Use add_table to create 1 Fact table (with additive metrics and surrogate keys) and 2-3 Conformed Dimensions.\n"
                                "3. Use add_relationship to wire non-identifying 1:N mandatory relationships.\n"
                                "4. Use compile_ddl to verify Snowflake DDL."
                            ),
                        },
                    }
                ],
            }
        elif name == "audit_pii_and_governance":
            return {
                "description": "Audit model for PII and compliance",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": (
                                "Inspect all tables using get_model, identify all columns storing PII (names, emails, phones, SSNs, addresses), "
                                "and use modify_table to tag them with pii_classification ('RESTRICTED_PII' or 'CONFIDENTIAL_PII')."
                            ),
                        },
                    }
                ],
            }
        elif name == "refactor_kimball_scd2":
            tbl = args.get("table_name", "DIM_CUSTOMER")
            return {
                "description": f"Refactor {tbl} to SCD Type 2",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": (
                                f"Refactor table `{tbl}` to support Slowly Changing Dimension (SCD) Type 2.\n"
                                "Use modify_table to add START_TS (TIMESTAMP_NTZ), END_TS (TIMESTAMP_NTZ), IS_CURRENT_FLG (BOOLEAN), "
                                "and RECORD_HASH (VARCHAR(64))."
                            ),
                        },
                    }
                ],
            }
        else:
            raise ValueError(f"Unknown prompt template: {name}")

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self.tools:
            raise ValueError(f"Unknown MCP tool: {name}. Available tools: {list(self.tools.keys())}")
        handler: Callable[..., Any] = self.tools[name]["handler"]
        return handler(**arguments)

    # -------------------------------------------------------------------------
    # Tool Handlers Implementation
    # -------------------------------------------------------------------------
    def get_model_summary(self) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        tables = [e for e in model.entities.values() if e.entity_type != "view" and e.entity_type != "materialized_view"]
        views = [e for e in model.entities.values() if e.entity_type in ("view", "materialized_view")]
        total_cols = sum(len(e.columns) for e in model.entities.values())
        return {
            "project_name": model.name,
            "version": model.version,
            "subject_areas": model.subject_areas,
            "total_entities": len(model.entities),
            "table_count": len(tables),
            "view_count": len(views),
            "relationship_count": len(model.relationships),
            "total_columns": total_cols,
            "tables": [
                {
                    "physical_name": e.physical_name,
                    "logical_name": e.logical_name,
                    "subject_area": e.subject_area,
                    "column_count": len(e.columns),
                    "primary_keys": [c.physical_name for c in e.columns if c.is_pk],
                    "entity_type": e.entity_type,
                }
                for e in model.entities.values()
            ],
            "relationships": [
                {
                    "name": r.name,
                    "parent_table": model.entities.get(r.parent_entity_id, EntityModel(id="", logical_name="", physical_name=r.parent_entity_id)).physical_name,
                    "child_table": model.entities.get(r.child_entity_id, EntityModel(id="", logical_name="", physical_name=r.child_entity_id)).physical_name,
                    "cardinality": r.cardinality.value if hasattr(r.cardinality, "value") else str(r.cardinality),
                    "is_mandatory": getattr(r, "is_mandatory", True),
                    "rel_type": r.rel_type.value if hasattr(r.rel_type, "value") else str(r.rel_type),
                }
                for r in model.relationships.values()
            ],
        }

    def get_model(self, subject_area: Optional[str] = None) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        data = model.model_dump(mode="json")
        if subject_area and subject_area != "All":
            filtered_ents = {
                k: v for k, v in data["entities"].items() if v.get("subject_area", "").lower() == subject_area.lower()
            }
            ent_ids = set(filtered_ents.keys())
            filtered_rels = {
                k: v
                for k, v in data["relationships"].items()
                if v.get("parent_entity_id") in ent_ids and v.get("child_entity_id") in ent_ids
            }
            data["entities"] = filtered_ents
            data["relationships"] = filtered_rels
        return data

    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        target = next(
            (
                e
                for e in model.entities.values()
                if e.physical_name.upper() == table_name.upper()
                or e.logical_name.lower() == table_name.lower()
            ),
            None,
        )
        if not target:
            available = [e.physical_name for e in model.entities.values()]
            raise ValueError(f"Table '{table_name}' not found. Available tables: {available}")

        return {
            "physical_name": target.physical_name,
            "logical_name": target.logical_name,
            "subject_area": target.subject_area,
            "description": target.description,
            "entity_type": target.entity_type,
            "view_sql": target.view_sql if target.entity_type in ("view", "materialized_view") else None,
            "volumetrics": target.volumetrics.model_dump() if target.volumetrics else None,
            "columns": [
                {
                    "physical_name": c.physical_name,
                    "logical_name": c.logical_name,
                    "snowflake_type": c.data_type_snowflake,
                    "sql_server_type": c.data_type_sql_server,
                    "oracle_type": c.data_type_oracle,
                    "is_pk": c.is_pk,
                    "is_fk": c.is_fk,
                    "is_nullable": c.is_nullable,
                    "description": c.description,
                    "pii_classification": c.pii_classification,
                    "sample_values": c.profile.sample_values if c.profile else [],
                    "dbt_tests": c.dbt_tests,
                }
                for c in target.columns
            ],
        }

    def search_metadata(
        self,
        query: str = "",
        pii_classification: str = "",
        subject_area: str = "",
    ) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        matches: List[Dict[str, Any]] = []
        q = query.lower().strip()
        for ent in model.entities.values():
            if subject_area and ent.subject_area.lower() != subject_area.lower():
                continue
            for col in ent.columns:
                if pii_classification and col.pii_classification != pii_classification:
                    continue
                if q and not (
                    q in col.physical_name.lower()
                    or q in col.logical_name.lower()
                    or q in ent.physical_name.lower()
                    or q in col.description.lower()
                ):
                    continue
                matches.append(
                    {
                        "table_physical": ent.physical_name,
                        "table_logical": ent.logical_name,
                        "subject_area": ent.subject_area,
                        "column_physical": col.physical_name,
                        "column_logical": col.logical_name,
                        "snowflake_type": col.data_type_snowflake,
                        "is_pk": col.is_pk,
                        "is_fk": col.is_fk,
                        "pii_classification": col.pii_classification,
                        "description": col.description,
                    }
                )
        return {"count": len(matches), "matches": matches}

    def add_table(
        self,
        physical_name: str,
        logical_name: str = "",
        subject_area: str = "Core",
        description: str = "",
        columns: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        mutation = {
            "action": "add_table",
            "physical_name": physical_name.upper().strip(),
            "logical_name": logical_name.strip() or physical_name.replace("_", " ").title(),
            "subject_area": subject_area.strip() or "Core",
            "description": description.strip(),
            "columns": columns or [],
        }
        return self.apply_mutations(mutations=[mutation])

    def modify_table(
        self,
        table_name: str,
        description: Optional[str] = None,
        columns_to_add: Optional[List[Dict[str, Any]]] = None,
        columns_to_drop: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        mutation: Dict[str, Any] = {
            "action": "modify_table",
            "physical_name": table_name.upper().strip(),
        }
        if description is not None:
            mutation["new_description"] = description
        if columns_to_add:
            mutation["columns_to_add"] = columns_to_add
        if columns_to_drop:
            mutation["columns_to_drop"] = columns_to_drop
        return self.apply_mutations(mutations=[mutation])

    def drop_table(self, table_name: str) -> Dict[str, Any]:
        mutation = {"action": "drop_table", "physical_name": table_name.upper().strip()}
        return self.apply_mutations(mutations=[mutation])

    def add_relationship(
        self,
        parent_table: str,
        child_table: str,
        parent_column: str = "",
        child_column: str = "",
        name: str = "",
        cardinality: str = "1:N",
        is_mandatory: bool = True,
        rel_type: str = "non_identifying",
    ) -> Dict[str, Any]:
        mutation = {
            "action": "add_relationship",
            "parent_table": parent_table.upper().strip(),
            "child_table": child_table.upper().strip(),
            "parent_column": parent_column.upper().strip() if parent_column else "",
            "child_column": child_column.upper().strip() if child_column else "",
            "name": name.strip() if name else f"FK_{child_table.upper()}_{parent_table.upper()}",
            "cardinality": cardinality,
            "is_mandatory": is_mandatory,
            "rel_type": rel_type,
        }
        return self.apply_mutations(mutations=[mutation])

    def drop_relationship(
        self,
        name: str = "",
        parent_table: str = "",
        child_table: str = "",
    ) -> Dict[str, Any]:
        mutation = {
            "action": "drop_relationship",
            "name": name,
            "parent_table": parent_table.upper().strip() if parent_table else "",
            "child_table": child_table.upper().strip() if child_table else "",
        }
        return self.apply_mutations(mutations=[mutation])

    def add_view(
        self,
        physical_name: str,
        view_sql: str,
        logical_name: str = "",
        subject_area: str = "Reporting",
        is_materialized: bool = False,
        columns: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        mutation = {
            "action": "add_view",
            "physical_name": physical_name.upper().strip(),
            "logical_name": logical_name.strip() or physical_name.replace("_", " ").title(),
            "view_sql": view_sql.strip(),
            "subject_area": subject_area.strip() or "Reporting",
            "materialization": "materialized_view" if is_materialized else "view",
            "columns": columns or [],
        }
        return self.apply_mutations(mutations=[mutation])

    def apply_mutations(self, mutations: List[Dict[str, Any]]) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        updated_model, actions_taken = execute_mutations(model, mutations)
        save_workspace_model(settings.canonical_model_path, updated_model)
        write_dbt_artifacts_to_disk(updated_model, settings.exported_dbt_dir)
        return {
            "success": True,
            "actions_executed": len(actions_taken),
            "log": actions_taken,
            "entity_count": len(updated_model.entities),
            "relationship_count": len(updated_model.relationships),
        }

    def compile_ddl(
        self,
        dialect: str = "snowflake",
        subject_area: Optional[str] = None,
    ) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        d = dialect.lower().strip()
        sa = subject_area if subject_area and subject_area != "All" else None

        if d == "snowflake":
            sql = compile_snowflake_ddl(model, subject_area=sa)
        elif d in ("sql_server", "tsql", "mssql"):
            sql = compile_sql_server_ddl(model, subject_area=sa)
        elif d in ("oracle", "plsql"):
            sql = compile_oracle_ddl(model, subject_area=sa)
        else:
            raise ValueError(f"Unsupported dialect: {dialect}. Supported: snowflake, sql_server, oracle")

        return {
            "dialect": d,
            "subject_area": sa or "All",
            "entity_count": len(model.entities),
            "ddl_sql": sql,
        }

    def generate_dbt_project(self, write_to_disk: bool = True) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        artifacts = compile_dbt_artifacts(model)
        contract = compile_open_data_contract_yaml(model)
        artifacts["datacontract.yaml"] = contract

        written_paths: List[str] = []
        if write_to_disk:
            written_paths = write_dbt_artifacts_to_disk(model, settings.exported_dbt_dir)

        return {
            "success": True,
            "exported_files": list(artifacts.keys()),
            "written_paths": written_paths,
            "output_directory": str(settings.exported_dbt_dir),
            "sample_schema_yml": artifacts.get("schema.yml", "")[:500] + "...",
        }

    def run_complete_compare_tool(
        self,
        target_ddl: str,
        dialect: str = "snowflake",
    ) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        td = TargetDialect(dialect.lower())
        parsed_ents, parsed_rels = parse_ddl_to_metamodel(target_ddl, dialect=td)
        baseline = ProjectMetamodel(
            name="Target Baseline DDL",
            entities={e.id: e for e in parsed_ents},
            relationships={r.id: r for r in parsed_rels},
        )
        diff = run_complete_compare(model, baseline, dialect=td)
        return {
            "identical": diff.identical,
            "summary": diff.summary,
            "added_entities": [e.physical_name for e in diff.added_entities],
            "dropped_entities": [e.physical_name for e in diff.dropped_entities],
            "modified_entities_count": len(diff.modified_entities),
            "forward_alter_script": diff.forward_alter_script,
            "rollback_alter_script": diff.rollback_alter_script,
        }

    def reverse_engineer_ddl(
        self,
        ddl_script: str,
        dialect: str = "snowflake",
        subject_area: str = "Staging",
        merge_into_project: bool = True,
    ) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        td = TargetDialect(dialect.lower())
        entities, relationships = parse_ddl_to_metamodel(
            ddl_script=ddl_script,
            dialect=td,
            default_subject_area=subject_area,
            existing_entities=model.entities if merge_into_project else None,
        )
        if not entities:
            raise ValueError("No CREATE TABLE or CREATE VIEW statements could be parsed from the supplied DDL script.")

        if not merge_into_project:
            model.entities = {}
            model.relationships = {}

        if subject_area not in model.subject_areas:
            model.subject_areas.append(subject_area)

        for ent in entities:
            model.entities[ent.id] = ent
        for rel in relationships:
            model.relationships[rel.id] = rel

        save_workspace_model(settings.canonical_model_path, model)
        write_dbt_artifacts_to_disk(model, settings.exported_dbt_dir)

        return {
            "success": True,
            "entities_imported": len(entities),
            "relationships_imported": len(relationships),
            "imported_tables": [e.physical_name for e in entities],
            "subject_area": subject_area,
        }

    def apply_naming_glossary(self, overwrite_existing: bool = True) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        stats = apply_glossary_to_project(model, overwrite_existing=overwrite_existing)
        save_workspace_model(settings.canonical_model_path, model)
        write_dbt_artifacts_to_disk(model, settings.exported_dbt_dir)
        return {
            "success": True,
            "entities_updated": stats.get("entities_updated", 0),
            "columns_updated": stats.get("columns_updated", 0),
            "message": "Applied Enterprise Naming Standards Glossary across entities and columns.",
        }

    def profile_data(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        model = ensure_seed_workspace(settings.canonical_model_path)
        ent_id: Optional[str] = None
        if table_name:
            target = next(
                (e for e in model.entities.values() if e.physical_name.upper() == table_name.upper()),
                None,
            )
            if not target:
                raise ValueError(f"Table '{table_name}' not found.")
            ent_id = target.id

        stats = run_data_profiler(model, entity_id=ent_id)
        save_workspace_model(settings.canonical_model_path, model)
        return stats


mcp_registry = MCPToolRegistry()


# -----------------------------------------------------------------------------
# JSON-RPC 2.0 Dispatcher (Used by both stdio and HTTP endpoints)
# -----------------------------------------------------------------------------
def dispatch_jsonrpc_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process a single JSON-RPC 2.0 MCP request and return the JSON-RPC response dict."""
    method = req.get("method")
    req_id = req.get("id")

    # Notification check: requests without 'id' are notifications and need no reply
    is_notification = req_id is None

    try:
        # 1. initialize
        if method == "initialize":
            params = req.get("params", {})
            protocol_version = params.get("protocolVersion", "2024-11-05")
            result = {
                "protocolVersion": protocol_version,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                    "logging": {},
                },
                "serverInfo": {
                    "name": "metaforge-data-modeling-mcp",
                    "version": "1.0.0",
                },
                "instructions": (
                    "MetaForge Studio MCP Server provides full canonical data modeling, DDL compilation "
                    "(Snowflake, SQL Server, Oracle), dbt generation, complete compare, data profiling, "
                    "and schema mutation capabilities for AI coding assistants. Call get_model_summary "
                    "to inspect the model, add_table or modify_table to refactor tables, add_relationship "
                    "to wire foreign keys, compile_ddl to generate DDL, and generate_dbt_project to compile dbt assets."
                ),
            }
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        # 2. notifications/initialized
        if method in ("notifications/initialized", "initialized"):
            return None  # No reply to notifications

        # 3. ping
        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        # 4. tools/list
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": mcp_registry.list_tools()},
            }

        # 5. tools/call
        if method == "tools/call":
            params = req.get("params", {})
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            out = mcp_registry.call_tool(name, arguments)
            text_result = json.dumps(out, indent=2) if isinstance(out, (dict, list)) else str(out)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text_result}],
                    "isError": False,
                },
            }

        # 6. resources/list
        if method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"resources": mcp_registry.list_resources()},
            }

        # 7. resources/read
        if method == "resources/read":
            params = req.get("params", {})
            uri = params.get("uri", "")
            res = mcp_registry.read_resource(uri)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [res],
                },
            }

        # 8. prompts/list
        if method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"prompts": mcp_registry.list_prompts()},
            }

        # 9. prompts/get
        if method == "prompts/get":
            params = req.get("params", {})
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            prompt_res = mcp_registry.get_prompt(name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": prompt_res,
            }

        # Unknown method
        if is_notification:
            return None
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: '{method}'",
            },
        }

    except Exception as exc:
        logger.exception("Error executing MCP method %s: %s", method, exc)
        if is_notification:
            return None
        # Return structured error in result or error object
        if method == "tools/call":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {exc}"}],
                    "isError": True,
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32000,
                "message": str(exc),
            },
        }


# -----------------------------------------------------------------------------
# Stdio Server Loop (Entry point for Claude Code, Cursor, Kiro, Gemini CLI)
# -----------------------------------------------------------------------------
def run_stdio_mcp_server() -> None:
    """Standard I/O JSON-RPC 2.0 loop for external MCP hosts."""
    # Write initial log message to stderr (never pollute stdout which is reserved for JSON-RPC)
    sys.stderr.write("MetaForge Studio MCP Server started on stdio.\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            res = dispatch_jsonrpc_request(req)
            if res is not None:
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as err:
            err_res = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {err}"},
            }
            sys.stdout.write(json.dumps(err_res) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            err_res = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": str(exc)},
            }
            sys.stdout.write(json.dumps(err_res) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_mcp_server()
