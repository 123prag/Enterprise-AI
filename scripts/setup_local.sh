#!/usr/bin/env bash
# Local setup + verification script.
# Run this after cloning, on a machine with network access:
#
#   bash scripts/setup_local.sh
#
# It creates a venv, installs dependencies, copies .env.example -> .env,
# and runs lint + tests. Report any failures back so they can be fixed —
# this code has NOT been executed in the authoring environment (no network
# / no pre-installed packages there), only syntax-checked.
set -euo pipefail

cd "$(dirname "$0")/.."

# Windows Git Bash commonly only has `python`, not `python3`.
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "ERROR: neither python3 nor python found on PATH"
  exit 1
fi

echo "==> Creating virtual environment (.venv)"
"$PYTHON" -m venv .venv

if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate        # Linux / macOS
elif [ -f .venv/Scripts/activate ]; then
  source .venv/Scripts/activate    # Windows (Git Bash / MINGW64)
else
  echo "ERROR: could not find venv activate script in .venv/bin or .venv/Scripts"
  exit 1
fi

echo "==> Upgrading pip"
pip install --upgrade pip -q

echo "==> Installing dependencies"
pip install -r requirements.txt

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example (local/offline defaults)"
  cp .env.example .env
fi

mkdir -p data/vector_store

echo "==> Lint (ruff)"
ruff check . || true

echo "==> Type check (mypy)"
mypy app || true

echo "==> Unit tests (pytest)"
pytest -v

echo "==> Booting API for a smoke check (5s)"
uvicorn app.main:app --port 8000 &
SERVER_PID=$!
sleep 3
if command -v curl >/dev/null 2>&1; then
  curl -sf http://localhost:8000/health && echo
else
  echo "(curl not found -- skipping smoke HTTP check; server was still started)"
fi
kill $SERVER_PID 2>/dev/null || true

echo "==> Done. If anything above failed, report the output for fixes."
