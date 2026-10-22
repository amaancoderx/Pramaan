#!/usr/bin/env bash
# One-command local run without Docker: installs dependencies on first run, then starts API (:8000) and web (:3000).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT/backend"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python
if [ ! -d .venv ]; then
  echo "Creating Python virtualenv (backend/.venv)..."
  "$PY" -m venv .venv
fi
if [ -x .venv/bin/python ]; then VPY=.venv/bin/python; else VPY=.venv/Scripts/python; fi
if ! "$VPY" -c "import fastapi, rapidocr_onnxruntime" >/dev/null 2>&1; then
  echo "Installing backend dependencies..."
  "$VPY" -m pip install -q --upgrade pip
  "$VPY" -m pip install -q -r requirements.txt
fi
if [ ! -f storage/benchmark_results.json ] && [ ! -f storage/dataset/manifest.json ]; then
  "$VPY" ../scripts/generate_dataset.py >/dev/null
fi

cd "$ROOT/frontend"
[ -d node_modules ] || { echo "Installing frontend dependencies..."; npm ci --no-audit --no-fund; }

cd "$ROOT/backend"
"$VPY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 75 &
API_PID=$!
trap 'echo; echo "Stopping Pramaan..."; kill $API_PID 2>/dev/null || true' INT TERM EXIT

cd "$ROOT/frontend"
echo
echo "  Web app   http://localhost:3000   (demo login: merchant@pramaan.local / shopkeeper123)"
echo "  API docs  http://localhost:8000/docs"
echo
npm run dev
