# Architecture

802.1X Lab is a control-plane UI and API on top of FreeRADIUS and a pluggable certificate authority.

## Principles

- **Hide unnecessary complexity** in Simple Mode; expose protocol detail in Advanced Mode.
- **Backend is source of truth** for users, endpoints, clients, policies, and cert metadata.
- **FreeRADIUS is the authentication engine** — we configure and observe it; we do not replace it.
- **Make auth observable** via structured authentication events.

## Components

| Service | Role |
|---------|------|
| `frontend` | React SPA (Vite), served via nginx in Compose |
| `backend` | FastAPI control plane, config render, CA adapter, event ingestion |
| `db` | PostgreSQL — app data and FreeRADIUS SQL tables (future) |
| `freeradius` | RADIUS authentication data plane |
| CA volume | Local openssl adapter data (step-ca adapter planned) |

## Control vs data plane

```text
Operator → Frontend → Backend API → PostgreSQL
                              ↓
                     Config render / reload
                              ↓
NAS / AP  ←——————→  FreeRADIUS  ←——→ SQL / EAP material
                              ↓
                     linelog / detail
                              ↓
                     Auth event worker → PostgreSQL → UI
```

## FreeRADIUS integration seam

1. API writes identity and client records to Postgres.
2. Backend renders FreeRADIUS fragments into a mounted runtime volume.
3. Backend signals reload (command configurable via env).
4. A worker parses a pinned linelog format into `authentication_events`.

Phase 0 ships interfaces, templates, and docs — not a full PEAP/EAP-TLS path.

## CA integration seam

`CertificateAuthorityAdapter` protocol:

- `ensure_root(lab_id)`
- `issue_client_cert(...)`
- `revoke(serial)`

Adapters:

- **openssl** (V1) — local PEM tree under `CA_DATA_DIR`
- **step-ca** (stub) — reserved for Phase 2

## Password / MSCHAPv2 note

PEAP/MSCHAPv2 typically needs NT-hash (or carefully handled cleartext) in the RADIUS SQL store. Hashes must never appear in application logs. Strategy will be documented when the live RADIUS path lands (Phase 1).

## Out of scope (for now)

Active Directory, LDAP, cloud IdPs, vendor switch/WLC config generators, packet capture, classroom mode, production hardening.
