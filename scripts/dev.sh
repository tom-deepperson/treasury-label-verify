#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
.venv/bin/pip install -r requirements.txt -q

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — set API keys and passwords before verifying labels."
fi

if [[ ! -f samples/labels/old_tom_pass.png ]]; then
  echo "Generating sample labels..."
  .venv/bin/python scripts/generate_samples.py
fi

PORT="${PORT:-8080}"
echo ""
echo "Local dev: http://127.0.0.1:${PORT}/login"
echo "Login: developer / DEVELOPER_PASSWORD from .env (unlimited tests if MAX_TESTS=0)"
echo "Press Ctrl+C to stop."
echo ""

exec .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$PORT"
