# Developer setup

## Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- Make (optional but recommended)
- Node 20+ and Python 3.12+ only if running services outside Compose
- Optional for host-side PEAP verification: `eapoltest` (`sudo apt install eapoltest`)
  - Not required for UI tests — the backend image includes `eapoltest`

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
- RADIUS: UDP `1812` / `1813` (FreeRADIUS with SQL + PEAP / EAP-TLS)

**Important:** run `make migrate` before relying on RADIUS auth — it creates FreeRADIUS SQL tables (`radcheck`, `nas`, …). The FreeRADIUS container waits for those tables on startup.

## Test from the UI (preferred)

1. Bootstrap the stack (`make bootstrap`).
2. Log in at http://localhost:3000.
3. **Guided PEAP:** open **Wizard** → PEAP → create/select lab → create user → create RADIUS client → run auth test → open **Events**.
4. **Guided EAP-TLS:** Wizard → EAP-TLS → lab → ensure root CA → issue client cert (download bundle optional) → RADIUS client → run EAP-TLS test → Events.
5. **Direct path:** open **Auth Test**:
   - PEAP: select a lab user, enter the password you set at create time, run test (or wrong-password)
   - EAP-TLS: ensure CA + issue cert / download bundle, then run test
   - Confirm Accept/Reject and that an event appears under **Auth Events** (auto-refreshes)
6. **Users:** create with first/last/department, generate with “select what to configure” + easy passwords (`maple482`), choose table/list/CSV credential view, or download a CSV template and import.
7. **Dashboard** shows live DB / API / FreeRADIUS health and the last auth event. Use **Sync to FreeRADIUS** after bulk changes if you want an explicit resync/reload.
8. Toggle **Dark / Light** in the header (or on the login screen). Preference is stored in the browser.

### What syncs / reloads

| Action | FreeRADIUS effect |
|--------|-------------------|
| Create/update/delete/generate/import user | Upsert/delete `radcheck` NT-Password (+ `radusergroup`) |
| Create/update/delete client | Rewrite `clients.dot1x.conf`, mirror `nas`, controlled FreeRADIUS **restart** (FreeRADIUS 3 does not re-read clients on HUP) |
| Ensure lab CA / issue client cert | Publish lab CA into shared `trusted/ca-bundle.pem`; restart only if the bundle changed |
| Auth Test (PEAP/EAP-TLS) | Backend runs `eapol_test` → FreeRADIUS → linelog → Events |

UI PEAP/EAP-TLS tests use the Compose bridge-subnet catch-all clients (`FREERADIUS_LAB_SECRET`, default `testing123`). NAS clients you create are for real switches/APs and are applied via the controlled restart above.

### RADIUS target IP (what the NAS points to)

The Dashboard / Clients / Auth Test / Wizard show a **RADIUS target** card:

- **Auto** — uses host DHCP/LAN detection (`scripts/detect-host-ip.sh` → `RADIUS_ADVERTISE_IP` + shared `host-ip` file)
- **Manual** — pin any IPv4 in the UI

Point the switch/WLC at `effective_ip:1812` (acct `1813`), then add a **RADIUS Client** whose IP matches the NAS source address.

## CLI PEAP smoke test (optional)

```bash
make test-peap
```

Or manually with host `eapol_test` against `127.0.0.1:1812` / `testing123` (see earlier Phase 1 notes / script `scripts/test-peap.sh`).

## Common commands

| Command | Purpose |
|---------|---------|
| `make up` | Start all Compose services |
| `make down` | Stop services |
| `make logs` | Tail logs |
| `make migrate` | Run Alembic migrations (app + FreeRADIUS SQL schema) |
| `make seed` | Seed a default lab |
| `make test-peap` | CLI PEAP smoke test |
| `make backend-shell` | Shell into backend container |

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
