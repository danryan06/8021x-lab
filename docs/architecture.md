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
| `freeradius` | RADIUS authentication data plane (PEAP/MSCHAPv2 + basic EAP-TLS) |
| CA volume | Local openssl adapter data (step-ca adapter planned) |

## Control vs data plane

```text
Operator → Frontend → Backend API → PostgreSQL (control plane)
                              ↓
              Sync NT-Password → radcheck / NAS → nas
              Render clients.dot1x.conf + restart.request
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

### Client apply mechanism

1. Backend renders Jinja `clients.conf.j2` → shared volume `clients.dot1x.conf`.
2. Backend upserts matching rows into `nas` (mirror / ops visibility).
3. If the rendered file changed, backend writes `restart.request` on the shared volume.
4. The FreeRADIUS entrypoint supervisor performs a controlled in-container restart.

A **full restart** (not HUP) is required because FreeRADIUS 3.x only reads
`clients.conf` (and its `$INCLUDE`s) at startup — SIGHUP/`radmin hup` reloads
modules and virtual servers but explicitly not clients. The `reload.request`
flag / HUP path still exists for module-level config that HUP does honor.

Stock `localhost` / `testing123` and the Compose bridge-subnet catch-all clients remain available for local PEAP/EAP-TLS tests. The **Auth Test** API runs `eapol_test` inside the backend container against service DNS `freeradius:1812`.

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

The backend lifespan task tails `FREERADIUS_AUTH_LOG_PATH` (shared volume) and inserts into `authentication_events`. Catch-all `lab-docker-host-N` clients scoped to the container's own Docker bridge subnets (secret `FREERADIUS_LAB_SECRET`, default `testing123`) accept RADIUS from Compose published ports on the Docker host; real NAS devices need per-NAS clients created in the UI.

## CA integration seam

`CertificateAuthorityAdapter` protocol:

- `ensure_root(lab_id)`
- `issue_client_cert(lab_id, identity, days)`
- `revoke(lab_id, cert_ref)`
- `generate_crl(lab_id)`

Adapters:

- **openssl** (V1) — local PEM tree under `CA_DATA_DIR`, backed by a per-lab
  openssl CA database (`db/index.txt`, `db/newcerts/`, `serial`, `crlnumber`)
  so certificates can be tracked, revoked, and listed in a CRL
- **step-ca** (stub) — reserved for a later phase

Issuance signs CSRs with `openssl ca` (not `x509 -req`) so each cert is recorded in the CA database. `revoke()` runs `openssl ca -revoke` and regenerates the CRL with `openssl ca -gencrl`. The CRL is published into `trusted/crl-bundle.pem`; FreeRADIUS only enforces it (adds `check_crl = yes` and loads the CRL alongside the CA certs) when `FREERADIUS_ENFORCE_CRL=yes`, because enabling CRL checking requires a current CRL for every trusted lab CA.

PEAP uses FreeRADIUS lab EAP server certificates generated in the FreeRADIUS image (`certs/bootstrap`), exported to the shared volume for UI `eapol_test`. Lab openssl CAs are published into `trusted/ca-bundle.pem` for EAP-TLS client trust. The Certificates page surfaces the inventory (status, expiry, download, revoke).

## Out of scope (for now)

Active Directory, LDAP, cloud IdPs, vendor switch/WLC config generators, packet capture, classroom mode, production hardening.
