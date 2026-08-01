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
| `db` | PostgreSQL — app data **and** FreeRADIUS SQL tables |
| `freeradius` | RADIUS authentication data plane (PEAP/MSCHAPv2 in Phase 1) |
| CA volume | Local openssl adapter data (step-ca adapter planned) |

## Control vs data plane

```text
Operator → Frontend → Backend API → PostgreSQL (control plane)
                              ↓
              Sync NT-Password → radcheck / NAS → nas
              Render clients.dot1x.conf + reload.request
                              ↓
NAS / AP  ←——————→  FreeRADIUS (rlm_sql + EAP/PEAP)
                              ↓
                     linelog DOT1X|…
                              ↓
                     Auth event worker → authentication_events → UI
```

## FreeRADIUS integration (Phase 1)

### SQL sync model

Control-plane tables remain authoritative:

| Control plane | FreeRADIUS SQL | Sync trigger |
|---------------|----------------|--------------|
| `radius_users` | `radcheck` (`NT-Password`) + `radusergroup` | user create / update / delete |
| `radius_clients` | rendered `clients.dot1x.conf` (+ `nas` mirror) | client create / update / delete |

Alembic migration `20260801_0002` installs the stock FreeRADIUS PostgreSQL tables (`radcheck`, `radreply`, `nas`, `radacct`, …) in the same database as the app. FreeRADIUS `rlm_sql` uses dialect `postgresql` against the Compose `db` service. Users authenticate from `radcheck`. NAS rows are mirrored into `nas` for inspection, but `read_clients = no` so FreeRADIUS loads clients only from the rendered file (avoids duplicate-IP conflicts).

### Client reload mechanism

1. Backend renders Jinja `clients.conf.j2` → shared volume `clients.dot1x.conf`.
2. Backend upserts matching rows into `nas` (mirror / ops visibility).
3. Backend writes `reload.request` on the shared volume.
4. FreeRADIUS entrypoint watcher runs `radmin hup` (control socket) or sends `SIGHUP`.

Stock `localhost` / `testing123` remains available for local PEAP tests.

### Password / MSCHAPv2 strategy

PEAP/MSCHAPv2 cannot use bcrypt. On user create/update the API:

1. Stores a **bcrypt** hash in `radius_users.password_hash` (app-side only).
2. Computes **NT hash** = MD4(UTF-16LE(password)), stored as FreeRADIUS `NT-Password` value `0x` + uppercase hex in `radius_users.nt_hash`.
3. Syncs that value into `radcheck` for FreeRADIUS.

NT hashes and cleartext passwords are **never** written to application logs. Cleartext is only returned once from the bulk user generator response.

### Auth event ingestion

FreeRADIUS module `linelog_dot1x` writes:

```text
DOT1X|<unix-epoch>|<User-Name>|<NAS-IP-Address>|<EAP-Type>|<Access-Accept|Access-Reject>|<failure>
```

(`%l` epoch timestamps avoid brittle FreeRADIUS strftime xlats in linelog format strings.)

The backend lifespan task tails `FREERADIUS_AUTH_LOG_PATH` (shared volume) and inserts into `authentication_events`. A stock `lab-docker-host` client (`172.16.0.0/12`, secret `testing123`) accepts RADIUS from Compose published ports on the Docker host.

## CA integration seam

`CertificateAuthorityAdapter` protocol:

- `ensure_root(lab_id)`
- `issue_client_cert(...)`
- `revoke(serial)`

Adapters:

- **openssl** (V1) — local PEM tree under `CA_DATA_DIR`
- **step-ca** (stub) — reserved for Phase 2

PEAP uses FreeRADIUS lab EAP server certificates generated in the FreeRADIUS image (`certs/bootstrap`). Full client PKI / EAP-TLS is Phase 2.

## Out of scope (for now)

Active Directory, LDAP, cloud IdPs, vendor switch/WLC config generators, packet capture, classroom mode, production hardening.
