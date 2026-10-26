"""Google Gemini LLM Agent Service for Enterprise Data Modeling & Metadata Governance."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..config import settings
from ..metamodel.schema import ProjectMetamodel
from ..metamodel.glossary import expand_business_text, sanitize_model_business_text
from .mutation_engine import execute_mutations


GEMINI_AVAILABLE_MODELS = [
    {
        "id": "gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "description": "Recommended: Ultra-fast, highly accurate data modeling & SQL generation (1M context)",
        "is_default": True,
    },
    {
        "id": "gemini-2.5-pro",
        "name": "Gemini 2.5 Pro",
        "description": "Deep reasoning & architecture analysis for complex enterprise schemas",
        "is_default": False,
    },
    {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash",
        "description": "Fast & responsive multimodal generation",
        "is_default": False,
    },
    {
        "id": "gemini-1.5-flash",
        "name": "Gemini 1.5 Flash",
        "description": "Legacy high-speed generation model",
        "is_default": False,
    },
    {
        "id": "gemini-1.5-pro",
        "name": "Gemini 1.5 Pro",
        "description": "Legacy 2M-token context window model",
        "is_default": False,
    },
]


def _build_model_summary(model: ProjectMetamodel) -> str:
    """Builds a compact summary of the current project schema for the LLM context."""
    lines: List[str] = [
        f"Project: {model.name} (v{model.version})",
        f"Subject Areas: {', '.join(model.subject_areas)}",
        f"Total Entities: {len(model.entities)}",
        f"Total Relationships: {len(model.relationships)}",
        "",
        "### Entities in Canvas:",
    ]
    for ent in model.entities.values():
        col_summaries = []
        for c in ent.columns:
            flags = []
            if c.is_pk:
                flags.append("PK")
            if c.is_fk:
                flags.append("FK")
            flag_str = f" [{','.join(flags)}]" if flags else ""
            col_summaries.append(f"{c.physical_name} ({c.data_type_snowflake}){flag_str}")

        lines.append(
            f"- **{ent.physical_name}** ({ent.logical_name}) [{ent.entity_type}, Area: {ent.subject_area}]: "
            + ", ".join(col_summaries)
        )
        if ent.entity_type in ("view", "materialized_view") and ent.view_sql:
            lines.append(f"  SQL: {ent.view_sql}")

    lines.append("")
    lines.append("### Relationships in Canvas:")
    for rel in model.relationships.values():
        p_ent = model.entities.get(rel.parent_entity_id)
        c_ent = model.entities.get(rel.child_entity_id)
        p_name = p_ent.physical_name if p_ent else rel.parent_entity_id
        c_name = c_ent.physical_name if c_ent else rel.child_entity_id
        lines.append(f"- {rel.name}: {p_name} -> {c_name} [{rel.rel_type.value}, {rel.cardinality.value}]")

    return "\n".join(lines)


SYSTEM_INSTRUCTION = """You are the Lead Enterprise Data Architect for MetaForge Studio.
Your role is to inspect, reason over, and modify canonical data models (tables, views, columns, relationships, and subject areas).

When a user asks a question, provides refactoring instructions, or commands you to:
1. Add a model or subject area
2. Add or modify tables and columns (data types, primary keys, foreign keys, descriptions, PII classifications)
3. Add or modify relationships (identifying, non_identifying, upstream_lineage; one_to_one, one_to_many, many_to_many)
4. Add or modify a view (creating analytical view SQL, selecting columns, linking upstream lineage)

You MUST respond in valid JSON format with the following exact structure:
{
  "reply": "Markdown explanation of what you did or the answer to the user's question with formatted code blocks, bold names, and rationale.",
  "mutations": [
    // List of mutation actions to execute on the canonical model (empty if purely Q&A)
  ]
}

Supported mutation actions in the 'mutations' array:
- Add Subject Area:
  {"action": "add_subject_area", "name": "Logistics"}

- Add Table:
  {
    "action": "add_table",
    "physical_name": "DIM_SUPPLIER",
    "logical_name": "Supplier Dimension",
    "subject_area": "Core",
    "description": "Supplier enterprise dimension",
    "columns": [
      {"physical_name": "SUPPLIER_ID", "logical_name": "Supplier Identifier", "data_type": "NUMBER(38,0)", "is_pk": true},
      {"physical_name": "SUPPLIER_NM", "logical_name": "Supplier Name", "data_type": "VARCHAR(255)", "is_nullable": false},
      {"physical_name": "COUNTRY_CD", "logical_name": "Country Code", "data_type": "VARCHAR(10)"}
    ]
  }

- Modify Table:
  {
    "action": "modify_table",
    "physical_name": "DIM_CUSTOMER",
    "new_description": "Updated description",
    "columns_to_add": [{"physical_name": "PHONE_NBR", "data_type": "VARCHAR(50)", "pii_classification": "RESTRICTED_PII"}],
    "columns_to_drop": ["OBSOLETE_COL"]
  }

- Drop Table:
  {"action": "drop_table", "physical_name": "DIM_OLD_TABLE"}

- Add Column:
  {"action": "add_column", "table_name": "DIM_CUSTOMER", "physical_name": "LOYALTY_TIER", "data_type": "VARCHAR(50)"}

- Modify Column:
  {"action": "modify_column", "table_name": "DIM_CUSTOMER", "physical_name": "TAX_ID_NBR", "pii_classification": "RESTRICTED_PII"}

- Drop Column:
  {"action": "drop_column", "table_name": "DIM_CUSTOMER", "physical_name": "OLD_COLUMN"}

- Add Relationship:
  {
    "action": "add_relationship",
    "name": "FK_FCT_CLAIM_DIM_CUSTOMER",
    "parent_table": "DIM_CUSTOMER",
    "child_table": "FCT_CLAIM",
    "parent_column": "CUST_ID",
    "child_column": "CUST_ID",
    "rel_type": "non_identifying",
    "cardinality": "one_to_many"
  }

- Modify Relationship:
  {"action": "modify_relationship", "name": "FK_NAME", "cardinality": "one_to_one"}

- Drop Relationship:
  {"action": "drop_relationship", "name": "FK_NAME"}

- Add View:
  {
    "action": "add_view",
    "physical_name": "VW_HIGH_SEVERITY_CLAIMS",
    "logical_name": "High Severity Claims Summary",
    "subject_area": "Claims",
    "view_sql": "SELECT c.CLM_ID, c.LOSS_AMT, cust.CUST_FULL_NM FROM FCT_CLAIM c INNER JOIN DIM_CUSTOMER cust ON c.CUST_ID = cust.CUST_ID WHERE c.LOSS_AMT > 50000",
    "columns": [
      {"physical_name": "CLM_ID", "data_type": "NUMBER(38,0)"},
      {"physical_name": "LOSS_AMT", "data_type": "NUMBER(18,2)"},
      {"physical_name": "CUST_FULL_NM", "data_type": "VARCHAR(255)"}
    ],
    "materialization": "view"
  }

- Modify View:
  {
    "action": "modify_view",
    "physical_name": "VW_CUSTOMER_CLAIM_SUMMARY",
    "view_sql": "SELECT ... new query ..."
  }

- Drop View:
  {"action": "drop_view", "physical_name": "VW_OLD_VIEW"}

CRITICAL BUSINESS LANGUAGE & NAMING STANDARDS:
- ABSOLUTELY ZERO USE OF SHORTENED WORDS, ABBREVIATIONS, OR ACRONYMS in logical_name, description, or business explanations.
- Always expand shorthand to complete business terms: 'Policy' (not 'plcy'), 'Claim' (not 'clm'), 'Customer' (not 'cust'), 'Number' (not 'nbr'/'num'), 'Amount' (not 'amt'), 'Effective Date' (not 'eff_dt'), 'Transaction' (not 'txn'), 'Coverage' (not 'cvrg'), 'Premium' (not 'prem'), 'Indicator' (not 'ind'), etc.
- Logical names, descriptions, and view titles must make immediate, intuitive sense to non-technical business stakeholders.
Ensure all physical names adhere to standard uppercase SQL naming conventions.
Output strictly JSON without markdown backticks wrapping the whole output.
"""


def call_gemini_agent(
    model: ProjectMetamodel,
    prompt: str,
    api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash",
    allow_mutations: bool = True,
) -> Tuple[str, List[str], bool, ProjectMetamodel]:
    """
    Calls Google's Gemini API with the project metamodel context, parses the response,
    applies any structured model/table/view/relationship mutations, and returns:
    (reply_markdown, actions_taken, mutated_boolean, updated_model)
    """
    effective_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    if not effective_key:
        raise ValueError(
            "Gemini API Key is required. Please enter your Gemini API Key in the AI Agent sidebar or set GEMINI_API_KEY."
        )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={effective_key}"
    context_summary = _build_model_summary(model)

    user_payload_text = f"""### Current Data Model Context:
{context_summary}

### User Instruction / Question:
{prompt}
"""

    request_body = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_payload_text}]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2,
        }
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, json=request_body)
            if resp.status_code != 200:
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("error", {}).get("message", err_text)
                except Exception:
                    err_msg = err_text
                raise RuntimeError(f"Gemini API Error ({resp.status_code}): {err_msg}")

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("No candidate responses returned from Gemini.")

            content_parts = candidates[0].get("content", {}).get("parts", [])
            raw_text = "".join(p.get("text", "") for p in content_parts).strip()

            # Strip any accidental ```json ... ``` wrapper
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

            parsed = json.loads(raw_text)
            reply = expand_business_text(str(parsed.get("reply", "Action processed.")))
            mutations = parsed.get("mutations", [])

            actions_taken: List[str] = []
            mutated = False

            if mutations and allow_mutations:
                model, actions_taken = execute_mutations(model, mutations)
                sanitize_model_business_text(model)
                mutated = len(actions_taken) > 0
            elif mutations and not allow_mutations:
                reply = "RBAC Policy: Your active role does not permit data modeling structural mutations.\n\n" + reply

            if not actions_taken:
                actions_taken.append(f"Gemini ({gemini_model}): Processed query")

            return reply, actions_taken, mutated, model

    except json.JSONDecodeError as jde:
        raise RuntimeError(f"Gemini returned invalid JSON: {jde}\nResponse: {raw_text[:300]}")
    except httpx.RequestError as req_err:
        raise RuntimeError(f"Network error contacting Gemini API: {req_err}")


def generate_metadata_with_gemini(
    model: ProjectMetamodel,
    entity_id: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash",
    overwrite_existing: bool = True,
) -> Tuple[Dict[str, Any], ProjectMetamodel]:
    """
    Leverages Google Gemini LLM (gemini-2.5-flash, gemini-2.5-pro, etc.) to generate
    context-aware enterprise business definitions, Kimball grains, regulatory retention windows,
    PII classifications, and column descriptions across all databases (SQLite, Snowflake, SQL Server, Oracle, Postgres).
    """
    from ..metamodel.governance_engine import auto_generate_metadata

    target_entities = (
        [model.entities[entity_id]]
        if entity_id and entity_id in model.entities
        else list(model.entities.values())
    )

    if not target_entities:
        return {
            "entities_updated": 0,
            "columns_updated": 0,
            "ai_provider": f"Google Gemini ({gemini_model})",
            "live_llm": False,
            "message": "No entities found to generate metadata for.",
        }, model

    effective_key = (
        (gemini_api_key or "").strip()
        or os.getenv("GEMINI_API_KEY", "").strip()
        or getattr(settings, "gemini_api_key", "").strip()
    )

    # If no Gemini API key is provided, use the rule-based governance engine as fallback
    if not effective_key:
        stats = auto_generate_metadata(
            model,
            entity_id=entity_id,
            overwrite_existing=overwrite_existing,
        )
        stats["ai_provider"] = "MetaForge Built-in AI Synthesis (Set Gemini API Key for Live LLM)"
        stats["live_llm"] = False
        stats["message"] = (
            f"Generated metadata for {stats['entities_updated']} table(s) and {stats['columns_updated']} column(s). "
            "To use live Google Gemini 2.5 Flash, enter your Gemini API Key in the AI Agent sidebar."
        )
        return stats, model

    # Build structured schema context for Gemini prompt
    schema_payload = []
    for ent in target_entities:
        cols_summary = []
        for col in ent.columns:
            prof_str = ""
            if col.profile:
                prof_str = (
                    f" [nulls: {col.profile.null_pct}%, distinct: {col.profile.distinct_count}, "
                    f"bounds: {col.profile.min_value}..{col.profile.max_value}, samples: {col.profile.sample_values[:3]}]"
                )
            cols_summary.append({
                "physical_name": col.physical_name,
                "logical_name": col.logical_name,
                "data_type": col.data_type_snowflake or col.data_type_sql_server or col.data_type_oracle or "VARCHAR",
                "is_pk": col.is_pk,
                "is_fk": col.is_fk,
                "current_description": col.description if not overwrite_existing else "",
                "profile_stats": prof_str,
            })
        schema_payload.append({
            "id": ent.id,
            "physical_name": ent.physical_name,
            "logical_name": ent.logical_name,
            "subject_area": ent.subject_area,
            "entity_type": ent.entity_type,
            "columns": cols_summary,
        })

    prompt_text = f"""You are the Chief Enterprise Data Steward and Data Governance Architect.
Generate rich, authoritative, production-grade business metadata and data catalog definitions for these tables:

{json.dumps(schema_payload, indent=2)}

CRITICAL BUSINESS LANGUAGE & NAMING STANDARDS:
1. ABSOLUTELY ZERO USE OF SHORTENED WORDS, ABBREVIATIONS, OR ACRONYMS in logical_name, description, business_purpose, grain, or column definitions.
2. Every abbreviation MUST be fully expanded into clean, authoritative business vocabulary:
   - NEVER use 'plcy' or 'PLCY' -> ALWAYS write 'Policy'
   - NEVER use 'clm' or 'CLM' -> ALWAYS write 'Claim'
   - NEVER use 'cust' or 'CUST' -> ALWAYS write 'Customer'
   - NEVER use 'nbr', 'num', or 'no' -> ALWAYS write 'Number'
   - NEVER use 'id' or 'ID' in descriptions -> ALWAYS write 'Identifier' or 'Key'
   - NEVER use 'amt' or 'AMT' -> ALWAYS write 'Amount'
   - NEVER use 'eff' or 'EFF' -> ALWAYS write 'Effective'
   - NEVER use 'exp' or 'EXP' -> ALWAYS write 'Expiration'
   - NEVER use 'dt' or 'DT' -> ALWAYS write 'Date'
   - NEVER use 'ts' or 'TS' -> ALWAYS write 'Timestamp'
   - NEVER use 'cd' or 'CD' -> ALWAYS write 'Code'
   - NEVER use 'ind' or 'IND' or 'flg' -> ALWAYS write 'Indicator'
   - NEVER use 'stat' or 'STAT' -> ALWAYS write 'Status'
   - NEVER use 'addr' or 'ADDR' -> ALWAYS write 'Address'
   - NEVER use 'txn' or 'TXN' -> ALWAYS write 'Transaction'
   - NEVER use 'prem' or 'PREM' -> ALWAYS write 'Premium'
   - NEVER use 'cvrg' or 'CVRG' -> ALWAYS write 'Coverage'
   - NEVER use 'acct' or 'ACCT' -> ALWAYS write 'Account'
   - NEVER use 'bal' or 'BAL' -> ALWAYS write 'Balance'
   - NEVER use 'pymt' or 'PYMT' -> ALWAYS write 'Payment'
3. Logical names must be in clean Title Case (e.g. 'Policy Effective Date', NOT 'PLCY_EFF_DT' and NOT 'Plcy Eff Dt').
4. Every description and Kimball grain statement must read as polished, natural enterprise business prose that non-technical business stakeholders immediately understand.

You MUST output a valid JSON object strictly adhering to this exact schema:
{{
  "entities": [
    {{
      "id": "<matching entity id>",
      "logical_name": "<Refined, clear business title in Title Case with zero abbreviations>",
      "description": "<Comprehensive 2-3 sentence business definition explaining entity role, lifecycle, and operational/analytical usage with zero abbreviations>",
      "business_purpose": "<High-level business utility summary with zero abbreviations>",
      "grain": "<Strict Kimball grain definition using full business terms, e.g. 'One record per unique verified customer account event'>",
      "retention_period": "<e.g. '7 years (SOX/GDPR compliance)' or '90 days (staging)'>",
      "modeling_stereotype": "<e.g. DIM_SCD1 | DIM_SCD2 | FCT_TRANSACTION | ODS_STAGING | ANALYTICAL_VIEW>",
      "columns": [
        {{
          "physical_name": "<exact column physical name>",
          "logical_name": "<Refined logical name in Title Case with zero abbreviations>",
          "description": "<Detailed business description explaining meaning, calculation, units, and domain rules with zero abbreviations>",
          "pii_classification": "<NONE | INTERNAL | CONFIDENTIAL | RESTRICTED_PII>"
        }}
      ]
    }}
  ]
}}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={effective_key}"
    request_body = {
        "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2,
        },
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, json=request_body)
            if resp.status_code != 200:
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("error", {}).get("message", err_text)
                except Exception:
                    err_msg = err_text
                raise RuntimeError(f"Gemini API Error ({resp.status_code}): {err_msg}")

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("No candidate responses returned from Gemini.")

            content_parts = candidates[0].get("content", {}).get("parts", [])
            raw_text = "".join(p.get("text", "") for p in content_parts).strip()

            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

            parsed = json.loads(raw_text)
            gen_entities = parsed.get("entities", [])

            entities_updated = 0
            columns_updated = 0

            for g_ent in gen_entities:
                ent_id = g_ent.get("id")
                ent = model.entities.get(ent_id)
                if not ent:
                    # fallback by physical_name matching
                    phys = (g_ent.get("physical_name") or "").upper()
                    ent = next((e for e in model.entities.values() if e.physical_name.upper() == phys), None)

                if ent:
                    if overwrite_existing or not ent.description:
                        desc = g_ent.get("description", ent.description)
                        purpose = g_ent.get("business_purpose")
                        if purpose and purpose not in desc:
                            desc = f"{desc} Business Purpose: {purpose}" if desc else purpose
                        ent.description = expand_business_text(desc)
                    if g_ent.get("logical_name"):
                        ent.logical_name = expand_business_text(g_ent.get("logical_name"))
                    grain = g_ent.get("grain") or g_ent.get("grain_statement")
                    if grain:
                        ent.grain_statement = expand_business_text(grain)
                    
                    ret_str = str(g_ent.get("retention_period") or g_ent.get("regulatory_framework") or "").upper()
                    if "SOX" in ret_str:
                        ent.retention_policy.regulatory_framework = "SOX_7YR"
                        ent.retention_policy.archive_retention_days = 2555
                    elif "GDPR" in ret_str:
                        ent.retention_policy.regulatory_framework = "GDPR"
                    elif "HIPAA" in ret_str:
                        ent.retention_policy.regulatory_framework = "HIPAA"
                    elif "PCI" in ret_str:
                        ent.retention_policy.regulatory_framework = "PCI_DSS"

                    stereotype = g_ent.get("modeling_stereotype")
                    if stereotype in ("DIM_SCD1", "DIM_SCD2", "FCT_TRANSACTION", "FCT_SNAPSHOT", "VAULT_HUB", "VAULT_LINK", "VAULT_SATELLITE", "ODS_STAGING", "ANALYTICAL_VIEW"):
                        ent.modeling_stereotype = stereotype

                    ent.metadata_status = "AUTO_GENERATED"
                    entities_updated += 1

                    cols_map = {c.physical_name.upper(): c for c in ent.columns}
                    for g_col in g_ent.get("columns", []):
                        col_phys = (g_col.get("physical_name") or "").upper()
                        col = cols_map.get(col_phys)
                        if col:
                            if overwrite_existing or not col.description:
                                col.description = expand_business_text(g_col.get("description", col.description))
                            if g_col.get("logical_name"):
                                col.logical_name = expand_business_text(g_col.get("logical_name"))
                            pii = g_col.get("pii_classification")
                            if pii in ("NONE", "INTERNAL", "CONFIDENTIAL", "RESTRICTED_PII"):
                                col.pii_classification = pii
                            col.metadata_status = "AUTO_GENERATED"
                            columns_updated += 1

            sanitize_model_business_text(model)
            return {
                "entities_updated": entities_updated,
                "columns_updated": columns_updated,
                "ai_provider": f"Google Gemini ({gemini_model})",
                "model": gemini_model,
                "live_llm": True,
                "message": f"Successfully generated rich enterprise metadata using Google Gemini ({gemini_model}) for {entities_updated} entity(s) and {columns_updated} column(s).",
            }, model

    except Exception as exc:
        # If Gemini call fails (e.g. network/key error), fall back cleanly and report warning
        stats = auto_generate_metadata(model, entity_id=entity_id, overwrite_existing=overwrite_existing)
        stats["ai_provider"] = "MetaForge AI Synthesis Engine (Gemini fallback)"
        stats["live_llm"] = False
        stats["error_note"] = str(exc)
        stats["message"] = (
            f"Generated metadata via local AI synthesis ({stats['entities_updated']} tables). "
            f"Gemini connection attempt note: {exc}"
        )
        return stats, model

