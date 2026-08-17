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

## Phase 3 — MAB + authorization policies (done)

- **Endpoints** page: register a device by MAC, with normalization on input
  (`aa:bb:cc:dd:ee:ff`, `aa-bb-cc-dd-ee-ff`, `aabb.ccdd.eeff`, bare hex all
  collapse to one canonical form), bulk paste, and a random-endpoint generator
- MAB end to end: enabled endpoints sync into `radcheck` as `Auth-Type := Accept`
  under every common MAC spelling, so a MAC authenticates without EAP
- MAB on the **Authentication Test** page via in-Compose `radclient`, including an
  unknown-MAC negative test; attempts land in `authentication_events` with
  `method = mab` and reasons for unknown MAC / disabled endpoint
- **Authorization** page: `AuthzPolicy` CRUD for VLAN, role (`Filter-Id`), and
  arbitrary reply attributes, with Simple (VLAN/role pickers) and Advanced (raw
  name/value editor) modes
- Policies apply to endpoints via `radreply` and to user groups via
  `radgroupreply`, so PEAP and EAP-TLS sessions get authorized too
- Returned attributes are recorded on each event and shown in the Events UI
- Dashboard endpoint/policy counts + recent MAB activity; guided **MAB wizard
  path** (policy → endpoint → client → test → events)
- Remaining: per-endpoint MAB session controls (CoA / Disconnect-Request),
  time-of-day and NAS-scoped policy conditions

## Phase 4 — Wizard expansions

- Additional guided flows (wireless-specific) beyond the PEAP / EAP-TLS / MAB
  first-lab paths

## Phase 5 — Appliance packaging

- Ubuntu LTS image path, health UI, non-Docker operator UX
- Later: OVA, Proxmox, Raspberry Pi

## Explicitly deferred

- Active Directory / LDAP / cloud IdP
- Vendor config generators (Cisco, Aruba, Mist, Fortinet, …)
- Packet capture integration
- Classroom / certification lab packs
- Production hardening
