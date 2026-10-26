# MetaForge Studio — Comprehensive User Guide

Welcome to **MetaForge Studio**, an enterprise data modeling and canonical metadata governance platform. This guide provides step-by-step walkthroughs for architects, data engineers, governance stewards, and analysts.

---

## Table of Contents
1. [User Authentication & Roles](#1-user-authentication--roles)
2. [Workspace Modes: Standalone vs. Remote](#2-workspace-modes-standalone-vs-remote)
3. [Shared Remote Repository & Check-In / Check-Out](#3-shared-remote-repository--check-in--check-out)
   - [Viewing in Read-Only Mode](#viewing-in-read-only-mode)
   - [Checking Out and Locking a Model Locally](#checking-out-and-locking-a-model-locally)
   - [Saving Local Drafts vs. Checking In](#saving-local-drafts-vs-checking-in)
   - [Lock Visibility and Release](#lock-visibility-and-release)
   - [Admin Force-Release and Stale Check-In Denial](#admin-force-release-and-stale-check-in-denial)
   - [3-Way Auto-Reapply for Interrupted Sessions](#3-way-auto-reapply-for-interrupted-sessions)
   - [Admin User Access Control (ACL)](#admin-user-access-control-acl)
4. [Canonical Metamodeling on Canvas](#4-canonical-metamodeling-on-canvas)
   - [Conceptual, Logical, and Physical Views](#conceptual-logical-and-physical-views)
   - [Entities, Views, and Column Attributes](#entities-views-and-column-attributes)
   - [Relationship Modeling: Cardinality and Mandatoriness](#relationship-modeling-cardinality-and-mandatoriness)
   - [Enterprise Domains and Naming Glossary](#enterprise-domains-and-naming-glossary)
   - [Sticky Notes and Auto-Layout Engine](#sticky-notes-and-auto-layout-engine)
5. [Reverse Engineering & Schema Sync](#5-reverse-engineering--schema-sync)
   - [Live Databases & Multi-Zone SQLite](#live-databases--multi-zone-sqlite)
   - [Excel Workbooks (.xlsx) and CSV Spreadsheets](#excel-workbooks-xlsx-and-csv-spreadsheets)
   - [Paste SQL DDL & Complete Compare (ALTER Sync)](#paste-sql-ddl--complete-compare-alter-sync)
6. [Autonomous Governance & AI Metadata Synthesis](#6-autonomous-governance--ai-metadata-synthesis)
   - [Statistical Profiling and Definition Synthesis](#statistical-profiling-and-definition-synthesis)
   - [Pushing Descriptions Back to Target Databases](#pushing-descriptions-back-to-target-databases)
   - [Private Google Gemini API Key Setup](#private-google-gemini-api-key-setup)
7. [Code Compilation & Artifact Export](#7-code-compilation--artifact-export)
8. [Connecting External Coding Assistants (MCP)](#8-connecting-external-coding-assistants-mcp)

---

## 1. User Authentication & Roles

MetaForge Studio features enterprise Role-Based Access Control (RBAC).

### Signing In & Switching Accounts
1. In the top-right toolbar, click the **User Profile** dropdown and select **User Directory & RBAC** (or **Switch User / Sign Out**).
2. Choose one of the pre-configured accounts or sign in with your enterprise credentials:
   - **Admin (`admin@metaforge.local` / `password123`)**: Has full access to manage accounts, remote model ACL permissions, and force-release locks.
   - **Data Architect (`architect@metaforge.local` / `password123`)**: Can create and edit physical models, check out remote models, run reverse engineering, and compile code.
   - **Data Steward (`steward@metaforge.local` / `password123`)**: Can edit business definitions, glossary terms, PII tags, and data quality assertions. Physical structural changes are restricted.
   - **Viewer (`viewer@metaforge.local` / `password123`)**: Read-only access to inspect models and diagrams.

---

## 2. Workspace Modes: Standalone vs. Remote

MetaForge Studio lets you work in either **Standalone (Local Mode)** or **Connected Remote Repository Mode**.

```
                        ┌─────────────────────────────────────┐
                        │      Choose Your Modeling Mode      │
                        └──────────────────┬──────────────────┘
                                           │
                 ┌─────────────────────────┴─────────────────────────┐
                 ▼                                                   ▼
 ┌───────────────────────────────┐                   ┌───────────────────────────────┐
 │   Standalone (Local Mode)     │                   │   Remote Repository Mode      │
 │  • Works on local workspace   │                   │  • Connect to shared repo     │
 │  • Unrestricted local edits   │                   │  • View-only without lock     │
 │  • Standard "Save" button     │                   │  • Check Out & Lock locally   │
 │  • No remote locks required   │                   │  • Team ACLs & 3-Way Merge    │
 └───────────────────────────────┘                   └───────────────────────────────┘
```

### Standalone (Local Mode) — Default on Startup
- When you launch the application, it opens in **Local Standalone Mode**.
- The toolbar displays the **`Remote Repo [Standalone]`** badge.
- You edit your local metamodel (`workspace_model/canonical_model.json`) freely without team locking restrictions. Click **Save** (or `Ctrl+S`) to save changes locally.

### Switching Between Standalone and Remote
- To connect to the shared repository: Click **Remote Repo** in the toolbar $\rightarrow$ click **Connect to Remote Repo** (or select a model in the directory).
- To return to local standalone modeling: Click **Work Locally (Standalone)** on the status bar or inside the Remote Repo modal.

---

## 3. Shared Remote Repository & Check-In / Check-Out

When working in teams, the Remote Repository guarantees that multiple modelers do not accidentally overwrite each other's changes.

### Viewing in Read-Only Mode
1. Click the **Remote Repo** button in the top toolbar to open the Remote Model Repository modal.
2. In the **Remote Directory** tab, click **Open View-Only (No Checkout)** on any model.
3. The model loads into the canvas with a blue status banner: `Remote Directory (View-Only Mode)`.
4. You can freely inspect entities, zoom, review lineage, and compile DDL. Any attempt to modify the canvas in View-Only mode displays an informative reminder to check out the model first.

### Checking Out and Locking a Model Locally
1. In the top banner or Remote Repo modal, click **Check Out & Lock Locally**.
2. MetaForge Studio will:
   - Download a local working copy to `workspace_model/local_checkouts/<your_email>/<model_id>.json`.
   - Snapshot your starting baseline version.
   - Lock the model in the shared repository (`Locked by You`).
3. While checked out by you, the toolbar provides two buttons:
   - **Save Draft**: Saves your in-progress work to your local checkout file without checking in or releasing the lock.
   - **Check In**: Opens the check-in dialog to commit your changes to the shared repository and release the lock.

### Lock Visibility and Release
- When a model is checked out, other team members browsing the repository or viewing the model will see an amber lock banner:
  > *Checked Out by Marcus Sterling (architect@metaforge.local) since 2:15 PM — Contact Marcus to release or ask Admin to Force Release.*
- Other users are blocked from checking out the model (`409 Conflict`), but can still open it in **View-Only** mode.
- To release a lock without checking in: Click **Release Lock (Discard Uncommitted)** to discard uncommitted working changes and revert to the latest remote version.

### Admin Force-Release and Stale Check-In Denial
If a team member goes offline or forgets to release a lock:
1. An **Admin** opens the Remote Repo modal and clicks **Admin Force Release Lock**.
2. The Admin enters an explanation (e.g., *"Emergency hotfix required for billing schema"*) and confirms.
3. **Immediate Shared Unlock**: The model is immediately unlocked in the shared repository so another modeler can proceed.
4. **Stale Check-In Denial**: If the original user subsequently attempts to check in their stale session, MetaForge Studio **denies the check-in** with a `409 Conflict`:
   > *CHECKIN_DENIED_FORCE_RELEASED: Your checkout lock was force-released by Admin. Direct check-in is denied.*
5. **Safe Draft Preservation**: The user's in-progress changes are not lost; they are safely retained in their session draft for automatic non-conflicting re-application.

### 3-Way Auto-Reapply for Interrupted Sessions
When a user's checkout session was force-released and an intermediate commit has been made:
1. As soon as the model becomes unlocked again, the user sees an amber alert:
   > *Your Previous Checkout Lock Was Force-Released by Admin. Click 'Check Out & Auto-Reapply Non-Conflicting Changes'.*
2. Clicking **Check Out & Auto-Reapply Non-Conflicting Changes** invokes the **3-Way Structural Merge Engine**:
   - **Base**: Model snapshot from when the user originally checked it out.
   - **Remote**: Latest authoritative version currently in the repository.
   - **User Draft**: User's uncommitted modifications.
3. **Automated Merging**:
   - Non-conflicting additions (e.g., new tables, added columns, updated descriptions on untouched entities) are automatically merged onto the latest remote version.
   - Conflicting changes (where an intermediate commit changed the exact same property differently) are skipped in favor of the latest remote version.
4. A **3-Way Auto-Reapply Report** displays all applied changes (green checkmarks) and skipped conflicts (amber warnings). The newly merged model is checked out and locked for the user to review and check in.

### Admin User Access Control (ACL)
Administrators configure per-user model permissions in the **User Access Control (Admin ACL)** tab:
- **`ADMIN`**: Full administrative rights, lock force-release, and ACL configuration.
- **`EDIT`**: View-only loading, Check Out & Lock locally, and Check In.
- **`VIEW`**: View-only inspection; checkout is disabled.
- **`NONE`**: Model is completely hidden from the user's directory.

---

## 4. Canonical Metamodeling on Canvas

### Conceptual, Logical, and Physical Views
Switch representations using the segmented control in the center of the top toolbar:
- **Conceptual**: Displays high-level domain entities, primary business keys, and cardinalities without physical database data types.
- **Logical**: Displays normalized entity structures with business logical names (e.g., `Policy Inception Date`) and semantic types.
- **Physical**: Displays physical table names (e.g., `DIM_POLICY`), column physical names (`PLCY_INCPTN_DT`), physical SQL data types tailored to the active target dialect, surrogate keys, and foreign keys.

### Entities, Views, and Column Attributes
- **Add Table**: In the Left Explorer, click **+ Table** to create an entity.
- **Add View**: Click **+ View** to create a standard or materialized view entity. Upstream lineage relationships automatically synthesize the `SELECT` query in the Inspector.
- **Edit Columns**: Select an entity on canvas to open the **Right Inspector**. Add columns, designate Primary Keys (`PK`), Foreign Keys (`FK`), Nullability, and PII classifications (e.g., `EMAIL`, `TAX_ID`, `CONFIDENTIAL`).

### Relationship Modeling: Cardinality and Mandatoriness
1. In the Left Explorer, click **+ Link / FK** and select parent and child entities.
2. Select the relationship line on the canvas to configure:
   - **Relationship Type**: Identifying (solid line) vs. Non-Identifying (dashed line).
   - **Cardinality**: `1:N` (One-to-Many), `1:1` (One-to-One), or `N:M` (Many-to-Many).
   - **Mandatory vs. Optional**: Toggle mandatory parent participation. When mandatory is selected, the relationship notation indicates a required parent relationship.

### Enterprise Domains and Naming Glossary
- **Enterprise Domains**: Centralized reusable semantic domains (e.g., `CURRENCY_AMOUNT`, `POSTAL_CODE`, `SURROGATE_KEY`). Updating a domain cascades its data types, check constraints, and default values to all bound columns across the entire enterprise metamodel.
- **Naming Standards Glossary**: Maintain approved standard word abbreviations (e.g., `CUSTOMER` $\rightarrow$ `CUST`, `IDENTIFIER` $\rightarrow$ `ID`, `POLICY` $\rightarrow$ `PLCY`). Clicking **Apply Glossary** automatically standardizes all physical names from logical names.

### Sticky Notes and Auto-Layout Engine
- **Sticky Notes**: Click **+ Sticky Note** in the Left Explorer to place persistent documentation and architectural notes directly onto canvas subject areas.
- **Auto-Layout**: Click **Auto-Layout** in the toolbar to automatically arrange entities into clean orthogonal layers with minimized link crossings.

---

## 5. Reverse Engineering & Schema Sync

### Live Databases & Multi-Zone SQLite
1. Click **Import & Sync** in the top toolbar $\rightarrow$ **Live DB & SQLite**.
2. Select an existing registered database connection or create a new connection (SQLite, Snowflake, SQL Server, PostgreSQL, Oracle).
3. **Multi-Zone Discovery**: Inspect schemas across **Staging**, **DWH / Core**, and **Consumption** layers.
4. Click **Reverse Engineer Tables** to ingest tables, infer foreign keys from matching column naming patterns, and route them to target canvas subject areas.

### Excel Workbooks (.xlsx) and CSV Spreadsheets
1. Click **Import & Sync** $\rightarrow$ **Excel & CSV Workbooks**.
2. Drag and drop an `.xlsx` workbook or `.csv` file.
3. The parser automatically detects sheet names, analyzes column headers, profiles nullability and unique value ratios, and previews sample records.
4. Click **Commit to Metamodel** to generate canonical entities and automatically establish inferred foreign keys.

### Paste SQL DDL & Complete Compare (ALTER Sync)
- **Paste SQL DDL Script**: Select **Import & Sync** $\rightarrow$ **Paste SQL DDL Script** to parse raw `CREATE TABLE` and `CREATE VIEW` statements into canvas entities.
- **Compare & ALTER Sync**: Compare the active canvas metamodel against a live database or past revision tag. The engine generates a non-destructive `ALTER TABLE ADD COLUMN`, `MODIFY COLUMN`, and constraint migration script.

---

## 6. Autonomous Governance & AI Metadata Synthesis

### Statistical Profiling and Definition Synthesis
1. Select an entity or column on the canvas.
2. Click **AI Generate** or click **Auto-Generate Metadata** in the Left Explorer.
3. The engine extracts statistical profiling distributions (uniqueness percentage, null ratios, distinct counts, sample values) and prompts Google Gemini to synthesize comprehensive, enterprise-grade business definitions.
4. Synthesized definitions avoid short, ambiguous acronyms and explain business semantics, source provenance, and intended downstream analytical usage.

### Pushing Descriptions Back to Target Databases
Once definitions are synthesized in MetaForge Studio, push them directly to your live database:
1. Open **Import & Sync** $\rightarrow$ **Live DB & SQLite**.
2. Select your target database and click **Preview Metadata Push SQL**.
3. Review dialect-tailored SQL statements:
   - **SQLite**: Populates `_metaforge_metadata` catalog tables.
   - **Snowflake / Oracle / PostgreSQL**: Executes `COMMENT ON TABLE ...` and `COMMENT ON COLUMN ...`.
   - **SQL Server**: Executes `sp_addextendedproperty 'MS_Description'`.
4. Click **Push Metadata to Database** to apply comments directly to live database objects.

### Private Google Gemini API Key Setup
API keys are stored per-user and never shared:
1. In the top-right corner, click your **User Profile** $\rightarrow$ **AI API Keys (Gemini)**.
2. Paste your Google AI Studio API key and click **Save Key to My Account**.
3. The key is encrypted in your local SQLite account record and stored in your browser session. If no key is set, MetaForge Studio automatically falls back to deterministic rule synthesis.

---

## 7. Code Compilation & Artifact Export

### Multi-Dialect DDL & dbt Compilation
Click **DDL & dbt** in the top toolbar to open the multi-dialect code drawer:
- **Snowflake**: Micro-partition cluster keys, transient table flags, comment metadata.
- **SQL Server**: Identity columns, filegroups, schemas, table descriptions.
- **Oracle**: Tablespaces, number precision, sequences, PL/SQL view definitions.
- **dbt Project**: Generated `schema.yml`, `sources.yml`, and dbt SQL staging models saved to `workspace_model/exported_dbt/`.
- **Data Contract YAML**: Open Data Contract Standard (ODCS) specification defining schema invariants and SLAs.

### Canvas Diagram & Data Dictionary Export
Click **Export** in the top toolbar:
- **PNG Image**: 2x retina raster diagram of the current subject area.
- **SVG Vector**: Scalable vector graphic suitable for architecture documentation.
- **PDF Document**: Formatted printable PDF diagram.
- **Data Dictionary (.csv)**: Spreadsheet export containing all table and column names, logical names, domains, data types, nullability, PII tags, and descriptions.

---

## 8. Connecting External Coding Assistants (MCP)

MetaForge Studio includes a Model Context Protocol (MCP) server so coding assistants like Claude Code, Cursor, or Gemini CLI can inspect and update your data models directly.

### Step 1: Open MCP Integration Modal
Click the **MCP** button in the top toolbar to view connection snippets and test tools interactively.

### Step 2: Configure Your Assistant
Add MetaForge Studio to your assistant's MCP configuration file (e.g., `~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "metaforge-studio": {
      "command": "/path/to/data_model/.venv/bin/python3",
      "args": ["/path/to/data_model/mcp_server.py"]
    }
  }
}
```

### Step 3: Example Prompts for Coding Assistants
Once connected, your assistant can use tools like `get_model_summary`, `add_table`, `compile_ddl`, and `profile_data`:
- *"Review the canonical model and add a `FACT_PAYMENT_TRANSACTION` table linked to `DIM_CUSTOMER`."*
- *"Compile the current data warehouse model into Snowflake DDL and generate the dbt project models."*
- *"Audit the model for unclassified PII columns and recommend data quality checks."*
