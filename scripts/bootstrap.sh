#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

docker compose up -d --build
echo "Waiting for database..."
sleep 8
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m app.seed

echo ""
echo "802.1X Lab is ready"
echo "  UI:  http://localhost:3000"
echo "  API: http://localhost:8000/docs"
echo "  Admin credentials: see .env (ADMIN_USERNAME / ADMIN_PASSWORD)"
