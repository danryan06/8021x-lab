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

## Phase 1 — RADIUS live path (done)

- FreeRADIUS SQL modules wired to Postgres
- Client sync + reload into the running FreeRADIUS container
- PEAP with local users (NT-Password / MSCHAPv2)
- Auth event ingestion (`DOT1X|…` linelog) and Events UI

## Phase 1.5 — Testing-ready UI (done)

- **Authentication Test** page: PEAP (and basic EAP-TLS) via in-Compose `eapol_test`
- Events auto-refresh, Accept/Reject styling, empty-state guidance
- Dashboard health probes for DB / API / FreeRADIUS + last auth event
- Users/Clients sync confirmation + “Sync to FreeRADIUS”
- Guided PEAP + **guided EAP-TLS** wizard wired to real APIs
- Lab CA ensure/issue/download + FreeRADIUS trust publish for EAP-TLS
- UI polish + light/dark theme
- Users: profile fields, configurable generator, easy passwords, credential view modes, CSV template/import

## Phase 2 — PKI polish

- Dedicated Certificates / CA inventory page: list, status, expiry, download, revoke (done)
- Revocation + CRL generation via a per-lab openssl CA database (done); FreeRADIUS
  CRL enforcement is opt-in via `FREERADIUS_ENFORCE_CRL`
- TLS/PEAP failure explanations (unknown CA, expired, revoked, bad password) (done)
- Remaining: step-ca adapter beyond stub, intermediate CAs, automatic expiry sweeps

> **Note:** Basic lab CA already shipped in Phase 1.5 (Wizard + Auth Test: ensure root, issue client cert, PEM/P12 download, FreeRADIUS trust). Phase 2 adds the inventory, real revocation/CRL, and failure explanations.

## Phase 3 — MAB + policies

- Endpoint (MAC) management
- Authorization reply attributes (VLAN, Filter-Id, …)
- Simple vs Advanced policy editors

## Phase 4 — Wizard expansions

- Additional guided flows (wireless-specific, MAB) beyond the PEAP / EAP-TLS first-lab paths

## Phase 5 — Appliance packaging

- Ubuntu LTS image path, health UI, non-Docker operator UX
- Later: OVA, Proxmox, Raspberry Pi

## Explicitly deferred

- Active Directory / LDAP / cloud IdP
- Vendor config generators (Cisco, Aruba, Mist, Fortinet, …)
- Packet capture integration
- Classroom / certification lab packs
- Production hardening
