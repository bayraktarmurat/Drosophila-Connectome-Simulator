#!/usr/bin/env bash
# Start the FastAPI backend and the Vite frontend together; Ctrl+C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT}/.venv/bin"

if [ ! -x "${PYTHON_BIN}/uvicorn" ]; then
  echo "No .venv found. Run: make install" >&2
  exit 1
fi
if [ ! -d "${ROOT}/frontend/node_modules" ]; then
  echo "Frontend dependencies missing. Run: make install" >&2
  exit 1
fi

"${PYTHON_BIN}/uvicorn" connectome_app.api:app --app-dir "${ROOT}/backend" --port 8000 &
BACKEND_PID=$!
trap 'kill ${BACKEND_PID} 2>/dev/null || true' EXIT INT TERM

echo "Backend:  http://127.0.0.1:8000/docs"
echo "Frontend: http://localhost:5173"
npm --prefix "${ROOT}/frontend" run dev
