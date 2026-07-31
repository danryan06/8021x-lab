# 802.1X Lab

The easiest way for Wi-Fi and network engineers to learn, test, and demonstrate enterprise authentication.

**802.1X Lab** is an engineer-friendly sandbox built on proven open-source components (FreeRADIUS, a local CA, PostgreSQL, and a simple web UI). It is **not** a replacement for FreeRADIUS, a NAC platform, or an enterprise PKI.

> Lab / education focused. Not hardened for production use.

## Status

Foundation scaffolding is in progress. See [`docs/roadmap.md`](docs/roadmap.md) once added.

## Vision

- Deploy an 802.1X lab quickly
- Configure RADIUS visually
- Manage users, certificates, and RADIUS clients
- Test PEAP, EAP-TLS, and MAB
- Make authentication attempts observable and understandable

## Planned stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI |
| Frontend | React + TypeScript + Vite |
| Database | PostgreSQL |
| RADIUS | FreeRADIUS |
| CA | Pluggable (`openssl` first, `step-ca` next) |
| Deploy | Docker Compose |

## License

Apache License 2.0
