# Developer setup

## Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- Make (optional but recommended)
- Node 20+ and Python 3.12+ only if running services outside Compose

## Quick start

```bash
cp .env.example .env
make up
make migrate
```

- UI: http://localhost:3000
- API docs: http://localhost:8000/docs
- Default admin: values from `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`)

## Common commands

| Command | Purpose |
|---------|---------|
| `make up` | Start all Compose services |
| `make down` | Stop services |
| `make logs` | Tail logs |
| `make migrate` | Run Alembic migrations |
| `make seed` | Seed a default lab |
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
