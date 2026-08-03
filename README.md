# 802.1X Lab

The easiest way for Wi-Fi and network engineers to learn, test, and demonstrate enterprise authentication.

**802.1X Lab** is an engineer-friendly sandbox built on proven open-source components (FreeRADIUS, a local CA, PostgreSQL, and a simple web UI). It is **not** a replacement for FreeRADIUS, a NAC platform, or an enterprise PKI.

> Lab / education focused. Not hardened for production use.

## Quick start

Already have Docker + Git and just want it running:

```bash
git clone https://github.com/danryan06/8021x-lab.git
cd 8021x-lab
cp .env.example .env
./scripts/bootstrap.sh
# or: make bootstrap
```

- **UI:** http://localhost:3000  
- **API docs:** http://localhost:8000/docs  
- **Default admin:** values from `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`)

**Starting from a fresh machine (or a Raspberry Pi)?** Follow the
[step-by-step installation guide](docs/installation.md) — it covers installing
Docker and Git from scratch, cloning the repo, and first login.

### Test authentication from the UI

1. Log in → open **Wizard** (guided PEAP or EAP-TLS) or **Auth Test**.
2. On the Dashboard, confirm the **RADIUS target** IP (Auto from DHCP/host, or Manual).
3. Follow the wizard steps, or create a user/cert and run a test from Auth Test — no CLI required.
4. Confirm Accept/Reject and a live row under **Auth Events**.
5. Toggle **Dark / Light** in the header anytime.

**New to 802.1X?** Start with the [concepts guide](docs/concepts.md) (what/why)
and the [usage guide](docs/usage.md) (step-by-step how-to).

## What this is

| You get | You do not get (yet / by design) |
|---------|-----------------------------------|
| Visual lab control plane | FreeRADIUS replacement |
| Local users + PEAP/MSCHAPv2 | Active Directory / LDAP |
| EAP-TLS with a lab CA: issue, download, revoke (CRL) | Enterprise PKI (intermediate CAs, HSM, ACME) |
| Certificate inventory + revocation | Vendor switch/WLC generators |
| RADIUS client sync into FreeRADIUS | Production-hardened NAC |
| Auth events with plain-language failure explanations | Cloud identity providers |
| Guided PEAP + EAP-TLS wizards | MAB / VLAN authorization policies (planned) |

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

- [Installation](docs/installation.md) — from-scratch setup (Docker, Git, clone, first login), incl. Raspberry Pi
- [Concepts](docs/concepts.md) — what 802.1X, RADIUS, PEAP/EAP-TLS, and certificates are, and why
- [Usage guide](docs/usage.md) — step-by-step how-to for every feature
- [Architecture](docs/architecture.md) — how the control plane, FreeRADIUS, and CA fit together
- [Developer setup](docs/developer-setup.md) — install, commands, testing
- [Deployment](docs/deployment.md)
- [Roadmap](docs/roadmap.md)
- [Contributing](CONTRIBUTING.md)

## License

Apache License 2.0 — see [LICENSE](LICENSE).
