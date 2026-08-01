# 802.1X Lab

The easiest way for Wi-Fi and network engineers to learn, test, and demonstrate enterprise authentication.

**802.1X Lab** is an engineer-friendly sandbox built on proven open-source components (FreeRADIUS, a local CA, PostgreSQL, and a simple web UI). It is **not** a replacement for FreeRADIUS, a NAC platform, or an enterprise PKI.

> Lab / education focused. Not hardened for production use.

## Quick start

```bash
cp .env.example .env
./scripts/bootstrap.sh
# or: make bootstrap
```

- **UI:** http://localhost:3000  
- **API docs:** http://localhost:8000/docs  
- **Default admin:** values from `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`)

See [docs/developer-setup.md](docs/developer-setup.md) for details.

## What this is

| You get | You do not get (yet / by design) |
|---------|-----------------------------------|
| Visual lab control plane | FreeRADIUS replacement |
| Local users + PEAP/MSCHAPv2 | Active Directory / LDAP |
| RADIUS client sync into FreeRADIUS | Vendor switch/WLC generators |
| Auth events from live FreeRADIUS | Production-hardened PKI / NAC |
| CA adapter seam (EAP-TLS next) | Cloud identity providers |

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic |
| Frontend | React, TypeScript, Vite, Tailwind |
| Database | PostgreSQL 16 |
| RADIUS | FreeRADIUS |
| CA | Pluggable (`openssl` now, `step-ca` next) |
| Deploy | Docker Compose |

## Repository layout

```text
backend/          FastAPI control plane
frontend/         React SPA
services/         FreeRADIUS + CA adapter notes/templates
docs/             Architecture, setup, deployment, roadmap
scripts/          Bootstrap helpers
docker-compose.yml
```

## Documentation

- [Architecture](docs/architecture.md)
- [Developer setup](docs/developer-setup.md)
- [Deployment](docs/deployment.md)
- [Roadmap](docs/roadmap.md)
- [Contributing](CONTRIBUTING.md)

## License

Apache License 2.0 — see [LICENSE](LICENSE).
