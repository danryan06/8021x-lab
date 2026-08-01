# Developer setup

## Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- Make (optional but recommended)
- Node 20+ and Python 3.12+ only if running services outside Compose
- Optional for PEAP verification on the host: `eapoltest` (`sudo apt install eapoltest`)

## Quick start

```bash
cp .env.example .env
make up
make migrate
make seed
```

Or one shot: `make bootstrap`.

- UI: http://localhost:3000 (nginx proxies `/api` to the backend)
- API docs: http://localhost:8000/docs (also available via http://localhost:3000/docs)
- Default admin: values from `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`)
- RADIUS: UDP `1812` / `1813` (FreeRADIUS with SQL + PEAP)

**Important:** run `make migrate` before relying on RADIUS auth — it creates FreeRADIUS SQL tables (`radcheck`, `nas`, …). The FreeRADIUS container waits for those tables on startup.

## Common commands

| Command | Purpose |
|---------|---------|
| `make up` | Start all Compose services |
| `make down` | Stop services |
| `make logs` | Tail logs |
| `make migrate` | Run Alembic migrations (app + FreeRADIUS SQL schema) |
| `make seed` | Seed a default lab |
| `make backend-shell` | Shell into backend container |

## Phase 1 — PEAP smoke test

1. Bootstrap the stack (`make bootstrap`).
2. Log in and note a lab id (`GET /api/labs`), or use the seeded Default Lab.
3. Create a RADIUS user via API/UI (password is converted to NT-hash for FreeRADIUS).
4. From the FreeRADIUS container (uses stock `localhost` / `testing123`):

```bash
# Copy the lab EAP CA out for eapol_test (once):
docker compose cp freeradius:/etc/freeradius/3.0/certs/ca.pem /tmp/dot1x-ca.pem

# Create an eapol_test config (replace USER/PASS):
cat >/tmp/peap.conf <<'EOF'
network={
  key_mgmt=WPA-EAP
  eap=PEAP
  identity="USER"
  password="PASS"
  phase2="auth=MSCHAPV2"
  # Lab only — accept the FreeRADIUS bootstrap CA:
  ca_cert="/tmp/dot1x-ca.pem"
}
EOF

# Host (if eapoltest is installed):
eapol_test -c /tmp/peap.conf -a 127.0.0.1 -p 1812 -s testing123 -r 1

# Or inside a tooling container on the Compose network:
docker compose exec freeradius bash -c 'apt-get update && apt-get install -y eapoltest'
```

5. Confirm an event: `GET /api/events` or the Events page in the UI.

### Client sync check

Creating/updating/deleting a client via `/api/clients` rewrites `clients.dot1x.conf`, upserts `nas`, and touches `reload.request` so the running FreeRADIUS process reloads. Point a NAS (or a container whose source IP matches the client) at UDP 1812 with that shared secret.

## Local backend (optional)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://dot1x:dot1x_lab_change_me@localhost:5432/dot1x_lab
uvicorn app.main:app --reload --port 8000
```

## Local frontend (optional)

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to the backend when using the provided config.

## Project layout

See the repository root README and [architecture.md](architecture.md).
