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

echo "==> Creating virtual environment (.venv)"
python3 -m venv .venv
source .venv/bin/activate

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
curl -sf http://localhost:8000/health && echo
kill $SERVER_PID

echo "==> Done. If anything above failed, report the output for fixes."
