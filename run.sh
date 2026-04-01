#!/usr/bin/env bash
# Локальная разработка: два терминала — backend и frontend (см. README).
set -e
cd "$(dirname "$0")"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
pip install -q -r requirements.txt
if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm ci)
fi
echo "1) Backend:  uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000"
echo "2) Frontend: cd frontend && npm run dev"
echo "   UI: http://127.0.0.1:5173  (прокси /api → :8000)"
