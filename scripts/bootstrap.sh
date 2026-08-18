#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

# Capture host LAN/DHCP IPv4 for NAS RADIUS targeting (Compose containers cannot see it).
HOST_IP="$(./scripts/detect-host-ip.sh 2>/dev/null || true)"
if [[ -n "${HOST_IP}" ]]; then
  if ! grep -q '^RADIUS_ADVERTISE_IP=' .env 2>/dev/null; then
    printf '\nRADIUS_ADVERTISE_IP=%s\n' "${HOST_IP}" >> .env
    echo "Set RADIUS_ADVERTISE_IP=${HOST_IP} (detected host/DHCP address)"
  else
    current="$(grep '^RADIUS_ADVERTISE_IP=' .env | head -n1 | cut -d= -f2-)"
    if [[ -z "${current}" ]]; then
      sed -i.bak "s/^RADIUS_ADVERTISE_IP=.*/RADIUS_ADVERTISE_IP=${HOST_IP}/" .env && rm -f .env.bak
      echo "Set RADIUS_ADVERTISE_IP=${HOST_IP} (detected host/DHCP address)"
    else
      echo "Keeping existing RADIUS_ADVERTISE_IP=${current} (host detected ${HOST_IP})"
    fi
  fi
else
  echo "Could not auto-detect host IP — set RADIUS_ADVERTISE_IP in .env or configure in the UI"
fi

docker compose up -d --build

# Schema + Default Lab seed run inside the backend container on start. Wait until
# the API is listening so a slow first boot cannot look "ready" too early.
echo "Waiting for the API (database schema is applied automatically)..."
ready=0
for attempt in $(seq 1 45); do
  if docker compose exec -T backend python -c \
    "import socket; s=socket.create_connection(('127.0.0.1',8000),2); s.close()"; then
    ready=1
    break
  fi
  echo "API not ready yet (attempt ${attempt}/45); retrying in 2s..."
  sleep 2
done
if [[ "${ready}" -ne 1 ]]; then
  echo "ERROR: API did not become ready after 90s. Check: docker compose logs db backend" >&2
  exit 1
fi

# Persist detected host IP into the shared runtime volume for the API auto mode.
if [[ -n "${HOST_IP}" ]]; then
  docker compose exec -T -e HOST_IP="${HOST_IP}" backend sh -c \
    'mkdir -p /var/lib/dot1x-lab/freeradius && printf "%s\n" "$HOST_IP" > /var/lib/dot1x-lab/freeradius/host-ip'
  echo "Wrote host-ip file for RADIUS advertise auto-detect: ${HOST_IP}"
fi

echo ""
echo "802.1X Lab is ready"
echo "  UI:  http://localhost:3000"
echo "  API: http://localhost:8000/docs"
echo "  Admin credentials: see .env (ADMIN_USERNAME / ADMIN_PASSWORD)"
if [[ -n "${HOST_IP}" ]]; then
  echo "  RADIUS target (NAS): ${HOST_IP}:1812"
fi
