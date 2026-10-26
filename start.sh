#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$ROOT_DIR/.venv/bin:$PATH"
cd "$ROOT_DIR"

echo "=================================================================="
echo "  MetaForge Studio - Enterprise Data Modeling & Agentic dbt Platform"
echo "  Backend API:  http://127.0.0.1:8000 (Swagger Docs: /docs)"
echo "  Frontend UI:  http://127.0.0.1:5173"
echo "=================================================================="

# 1. Start FastAPI Backend (:8000)
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# 2. Start Vite Frontend (:5173)
cd "$ROOT_DIR/frontend"
if [ ! -d "node_modules" ]; then
  npm install
fi
npm run dev -- --host 127.0.0.1 --port 5173 &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" EXIT
wait
