# Roadmap

## Phase 0 — Foundation (done)

- Open-source baseline (license, docs, contributing)
- Docker Compose monorepo
- FastAPI + models + Alembic
- User management + random user generator
- RADIUS client management
- FreeRADIUS / CA integration architecture
- Frontend shell (dashboard, users, clients, events, wizard placeholder)
- Simple / Advanced mode toggle

## Phase 1 — RADIUS live path (current)

- FreeRADIUS SQL modules wired to Postgres
- Client sync + reload into the running FreeRADIUS container
- PEAP with local users (NT-Password / MSCHAPv2)
- Auth event ingestion (`DOT1X|…` linelog) and Events UI

## Phase 2 — PKI + EAP-TLS

- Root CA creation via adapter
- Client certificate issue / download
- FreeRADIUS EAP-TLS
- Failure explanations (unknown CA, expired cert, etc.)

## Phase 3 — MAB + policies

- Endpoint (MAC) management
- Authorization reply attributes (VLAN, Filter-Id, …)
- Simple vs Advanced policy editors

## Phase 4 — Guided wizard

- End-to-end “Create your first 802.1X lab” using real backends

## Phase 5 — Appliance packaging

- Ubuntu LTS image path, health UI, non-Docker operator UX
- Later: OVA, Proxmox, Raspberry Pi

## Explicitly deferred

- Active Directory / LDAP / cloud IdP
- Vendor config generators (Cisco, Aruba, Mist, Fortinet, …)
- Packet capture integration
- Classroom / certification lab packs
- Production hardening
