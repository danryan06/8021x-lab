#!/usr/bin/env bash
# Stop the lab and delete its data volumes (database, RADIUS logs, CA material).
#
# install.sh runs this so a re-install is a clean slate. upgrade.sh and
# `make bootstrap` do not — those paths keep the database, logs, and certs.
#
# Also removes leftover volumes from older project names (the directory name
# `8021x-lab` vs COMPOSE_PROJECT_NAME=dot1x-lab), which is why Auth Events and
# auth.log can survive a rebuild.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not on PATH" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: cannot talk to the Docker daemon" >&2
  exit 1
fi

if [[ ! -f docker-compose.yml ]]; then
  echo "No docker-compose.yml in ${ROOT}; nothing to reset."
  exit 0
fi

echo "Stopping the lab and deleting data volumes..."

# Current Compose project (.env COMPOSE_PROJECT_NAME, else the directory name).
docker compose down -v --remove-orphans

# Unique list of names this stack has used (dir name vs COMPOSE_PROJECT_NAME).
projects=""
add_project() {
  local name="${1:-}"
  [[ -z "${name}" ]] && return 0
  case $'\n'"${projects}"$'\n' in
    *$'\n'"${name}"$'\n'*) return 0 ;;
  esac
  if [[ -n "${projects}" ]]; then
    projects="${projects}"$'\n'"${name}"
  else
    projects="${name}"
  fi
}

if [[ -f .env ]]; then
  add_project "$(grep -E '^COMPOSE_PROJECT_NAME=' .env | tail -n1 | cut -d= -f2- | tr -d '\r' || true)"
fi
add_project "$(basename "${ROOT}")"
add_project "dot1x-lab"
add_project "8021x-lab"

while IFS= read -r project; do
  [[ -z "${project}" ]] && continue
  docker compose -p "${project}" down -v --remove-orphans >/dev/null 2>&1 || true
  docker volume rm -f \
    "${project}_pgdata" \
    "${project}_freeradius_runtime" \
    "${project}_ca_data" >/dev/null 2>&1 || true
done <<< "${projects}"

echo "Previous lab database, RADIUS logs, and CA material are gone."
