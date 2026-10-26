# MetaForge Studio

> **Enterprise Cloud-Native Canonical Data Modeling, Governance Control Plane & Remote Collaboration Repository**

MetaForge Studio is an enterprise-grade data modeling and governance platform designed for modern data engineering, analytics architecture, and autonomous data stewardship. It bridges conceptual, logical, and physical modeling with multi-dialect DDL compilation, live database reverse engineering, automated data profiling, AI-assisted business metadata synthesis, Model Context Protocol (MCP) coding assistant integration, and a distributed check-in/check-out remote repository with 3-way conflict resolution.

---

## Key Capabilities

- **Tri-Level Model Duality**: Seamlessly toggle between **Conceptual**, **Logical**, and **Physical** representations with automated glossary abbreviation mapping, domain cascading, and foreign key inference.
- **Multi-Dialect Physical Compilation**: Generate native, production-ready DDL for **Snowflake Data Cloud**, **Microsoft SQL Server (T-SQL)**, and **Oracle Database (PL/SQL)**, alongside **dbt** projects (`schema.yml`, `sources.yml`, and SQL staging models) and **Open Data Contract Standard (ODCS)** YAML contracts.
- **Reverse Engineering & Sync**:
  - **Live Databases & SQLite**: Connect directly to SQLite, Snowflake, SQL Server, PostgreSQL, or Oracle; inspect multi-zone architectures (Staging, DWH / Core, Consumption); run statistical column profiling; and push synthesized business metadata back to the target database.
  - **File Ingestion**: Reverse engineer multi-sheet Excel workbooks (`.xlsx`, `.xls`) and CSV files with relational constraint detection.
  - **DDL Parser & Complete Compare**: Parse complex DDL and CTE view queries into canvas entities, compare canvas metamodels against target databases, and generate non-destructive `ALTER` migration scripts.
- **Shared Remote Repository & Check-In / Check-Out Governance**:
  - **Standalone (Local) vs. Remote Mode**: Work locally in Standalone mode with full offline editing, or connect to a shared enterprise repository.
  - **View-Only Without Checkout**: Inspect shared models in read-only mode without locking the repository.
  - **Check-Out & Locking**: Download working drafts locally and lock the model in the shared repository so concurrent editors cannot overwrite changes.
  - **Admin Force-Release & Stale Check-In Denial**: Administrators can force-release abandoned locks, automatically denying stale check-ins while safely preserving the editor's draft.
  - **3-Way Non-Conflicting Auto-Reapply**: Automatically merges non-conflicting additions, alterations, and new tables back onto the latest remote version when the model becomes available again.
  - **User-Based Access Control (ACL)**: Model-level permission matrix (`ADMIN`, `EDIT`, `VIEW`, `NONE`) managed by administrators.
- **Autonomous Governance & AI Synthesis**:
  - Synthesize rich, standardized business descriptions for tables and columns by feeding statistical profiling metrics into Google Gemini.
  - Private per-user API key management stored securely in the local SQLite database and client storage—never hardcoded or committed to version control.
- **Model Context Protocol (MCP) Integration**:
  - Built-in MCP 2024-11-05 JSON-RPC server (`mcp_server.py` and HTTP endpoints at `/api/mcp`) exposing tools, resources, and prompt templates to AI coding assistants (Claude Code, Cursor, Gemini CLI).

---

## Architecture Overview

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      MetaForge Studio Frontend                         │
 │     React 18 • TypeScript • Tailwind CSS • @xyflow/react • Vite        │
 └───────────────────▲────────────────────────────────┬───────────────────┘
                     │ REST API                       │ WebSocket / HTTP
 ┌───────────────────┴────────────────────────────────▼───────────────────┐
 │                       MetaForge FastAPI Backend                        │
 │           FastAPI • SQLAlchemy • Pydantic v2 • Uvicorn                 │
 ├────────────────────────────────┬───────────────────────────────────────┤
 │  • Remote Repo & 3-Way Merge   │  • Reverse Engineering & Profiling    │
 │  • Role-Based Access (RBAC)    │  • Multi-Dialect Compilers            │
 │  • MCP JSON-RPC 2024-11-05     │  • Gemini AI Metadata Synthesis       │
 └───────────────────┬────────────────────────────────┬───────────────────┘
                     │                                │
 ┌───────────────────▼────────────┐      ┌────────────▼───────────────────┐
 │ SQLite Metadata Control Plane  │      │ Remote Repository & Checkouts  │
 │  (Users, ACL, Models, Audits)  │      │  (workspace_model/remote_repo) │
 └────────────────────────────────┘      └────────────────────────────────┘
```

---

## Directory Structure

```
data_model/
├── backend/
│   ├── app/
│   │   ├── agent/               # Gemini AI service, LLM executor & MCP server
│   │   ├── auth/                # JWT auth, user directory, ACL models & RBAC
│   │   ├── compilers/           # Snowflake, SQL Server, Oracle & dbt generators
│   │   ├── metamodel/           # Canonical metamodel schema, domains & glossary
│   │   ├── reverse_eng/         # DDL parser, complete compare, Excel/CSV parser
│   │   ├── config.py            # Dynamic configuration & environment loader
│   │   ├── db_connector.py      # Multi-zone database connector & profiling engine
│   │   ├── main.py              # FastAPI application entrypoint & REST endpoints
│   │   └── remote_repo.py       # Remote repository, locking & 3-way merge engine
│   └── tests/                   # 37 comprehensive pytest test suites
├── frontend/
│   ├── src/
│   │   ├── components/          # ERD Canvas, toolbars, inspectors & modals
│   │   ├── services/            # Typed API client service
│   │   ├── store/               # Zustand metamodel & collaboration state store
│   │   └── types/               # Metamodel, ACL, and MCP TypeScript definitions
├── workspace_model/
│   ├── canonical_model.json     # Active local workspace model
│   ├── remote_repo/             # Shared remote models
│   └── local_checkouts/         # User local checked-out working copies
├── mcp_server.py                # Standalone MCP CLI server entrypoint
├── docker-compose.yml           # Docker deployment configuration
├── config.sample.json           # Sample JSON configuration template
├── .env.example                 # Sample environment variables template
├── .gitignore                   # Git exclusion rules for secrets, DBs & builds
└── USERGUIDE.md                 # End-to-end user and administrator guide
```

---

## Quick Start

### Prerequisites
- **Python**: 3.10+ (Python 3.12 recommended)
- **Node.js**: v18+ (Node 20 / 22 recommended) with `npm`
- **Git**

### 1. Clone & Set Up Configuration
```bash
git clone <repository-url>
cd data_model

# Copy sample configuration templates (both are gitignored)
cp .env.example .env
cp config.sample.json config.local.json
```

> **Security Note**: Never commit `.env` or `config.local.json` to Git. Both are listed in `.gitignore`. API keys can also be saved individually by each user inside the application UI.

### 2. Backend Setup
```bash
# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install backend dependencies
pip install fastapi uvicorn sqlalchemy pydantic pyjwt bcrypt httpx openpyxl pandas sqlglot pytest

# Start FastAPI backend (runs on http://127.0.0.1:8000)
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Frontend Setup
```bash
cd frontend

# Install dependencies and start Vite dev server (runs on http://127.0.0.1:5173)
npm install
npm run dev
```

Open your browser to **`http://127.0.0.1:5173`**.

---

## Default Seed Accounts

MetaForge Studio initializes with four enterprise RBAC user accounts:

| User Account | Email | Password | Role | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| **Enterprise Admin** | `admin@metaforge.local` | `password123` | **Admin** | Full system control, User Management, Model ACLs, Force-Release |
| **Principal Architect** | `architect@metaforge.local` | `password123` | **Data Architect** | Physical & logical modeling, Check-in/out, DDL export, Reverse engineering |
| **Data Steward** | `steward@metaforge.local` | `password123` | **Data Steward** | Business definitions, PII classification, glossary & DQ rules |
| **Analytics Consumer** | `viewer@metaforge.local` | `password123` | **Viewer** | View-only inspection of canvas and remote models |

---

## Model Context Protocol (MCP) Setup

MetaForge Studio features an MCP 2024-11-05 server allowing external AI coding assistants to query and mutate your canonical data models.

### Connecting Claude Code / Gemini CLI
Add MetaForge Studio to your assistant's MCP configuration:

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

Or connect over HTTP via the backend REST endpoint:
- **MCP Config**: `GET http://127.0.0.1:8000/api/mcp/config`
- **MCP Tools**: `GET http://127.0.0.1:8000/api/mcp/tools`
- **JSON-RPC Dispatcher**: `POST http://127.0.0.1:8000/api/mcp/call`

---

## Running Tests

Run the backend unit and integration test suite:
```bash
.venv/bin/pytest backend/tests -v
```

Verify the frontend build and TypeScript types:
```bash
cd frontend && npm run build
```

---

## Documentation

For step-by-step instructions on canvas modeling, reverse engineering live databases, remote repository check-outs, force-releases, and AI metadata pushback, see **[USERGUIDE.md](USERGUIDE.md)**.
