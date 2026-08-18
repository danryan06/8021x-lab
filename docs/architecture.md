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
| `freeradius` | RADIUS authentication data plane (PEAP/MSCHAPv2, EAP-TLS, MAB) |
| CA volume | Local openssl adapter data (step-ca adapter planned) |

## Control vs data plane

```text
Operator → Frontend → Backend API → PostgreSQL (control plane)
                              ↓
              Sync NT-Password → radcheck / NAS → nas
              Sync endpoint MACs → radcheck (Auth-Type := Accept)
              Sync policy attributes → radreply / radgroupreply
              Render clients.dot1x.conf + restart.request
                              ↓
NAS / AP  ←——————→  FreeRADIUS (rlm_sql + EAP/PEAP + MAB)
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
| `endpoints` | `radcheck` (`Auth-Type := Accept`) + `radreply` (its policy) | endpoint create / update / delete, policy edit |
| `authz_policies` | `radreply` (via endpoints) / `radgroupreply` (via `group_name`) | policy create / update / delete |

Alembic migration `20260801_0002` installs the stock FreeRADIUS PostgreSQL tables (`radcheck`, `radreply`, `nas`, `radacct`, …) in the same database as the app. FreeRADIUS `rlm_sql` uses dialect `postgresql` against the Compose `db` service. Users authenticate from `radcheck`. NAS rows are mirrored into `nas` for inspection, but `read_clients = no` so FreeRADIUS loads clients only from the rendered file (avoids duplicate-IP conflicts).

### Client apply mechanism

1. Backend renders Jinja `clients.conf.j2` → shared volume `clients.dot1x.conf`.
2. Backend upserts matching rows into `nas` (mirror / ops visibility).
3. If the rendered file changed, backend writes `restart.request` on the shared volume.
4. The FreeRADIUS entrypoint supervisor performs a controlled in-container restart.

One FreeRADIUS instance serves every lab from that one file, so the render is
always **all** clients, not the lab being synced — and it emits **one client per
address**. FreeRADIUS matches a request to a client by source address and aborts
startup if two blocks claim the same one, which would stop authentication for
every lab, so duplicates are rejected when a client is created and collapsed
again at render time for rows that predate the rule.

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

## MAB and authorization policies (Phase 3)

### How a MAC becomes a RADIUS identity

MAB has no supplicant and no password: the NAS puts the device MAC in `User-Name`
and sends `Service-Type = Call-Check`. To answer that, an **enabled** endpoint is
written to `radcheck` as `Auth-Type := Accept`, which short-circuits
authentication for that `User-Name` — the MAB trust model, expressed in one row.

Vendors spell MACs differently, so one endpoint is registered under every common
spelling of its canonical MAC (`mac_radius_usernames`): colon, hyphen, and bare
hex, each in lower and upper case — six `radcheck` rows per endpoint. Disabling
an endpoint deletes its rows rather than flagging them, so a disabled MAC fails
the same way an unregistered one does (and the control plane supplies the reason
the UI shows).

Unlike clients, endpoints and policies need **no reload or restart**: `rlm_sql`
queries `radcheck`/`radreply` per request, so a newly registered MAC works on the
next packet.

### How policy attributes reach FreeRADIUS

`AuthzPolicy` stores intent (a VLAN, a role, plus arbitrary raw pairs).
`integrations/freeradius/reply_attributes.py` is the single place that renders it
into RADIUS attributes:

| Policy field | Rendered rows |
|--------------|---------------|
| `vlan = 40` | `Tunnel-Type = VLAN`, `Tunnel-Medium-Type = IEEE-802`, `Tunnel-Private-Group-Id = 40` |
| `role = "printer-acl"` | `Filter-Id = printer-acl` |
| `reply_attributes` | each pair verbatim; a pair repeating a rendered name replaces it in place, so Advanced mode wins without emitting two rows for one attribute |

Those rows are written to one of two stock FreeRADIUS tables, depending on what
the policy is attached to:

- **`radreply`** — keyed by `username`, so an endpoint's policy is written under
  each of that endpoint's MAC spellings. This is the MAB path.
- **`radgroupreply`** — keyed by `groupname`, used when a policy sets
  `group_name`. Users already sync into `radusergroup`, so PEAP and EAP-TLS
  sessions pick up their group's attributes with no per-user rows. One policy per
  group is enforced in the service layer, because FreeRADIUS would otherwise
  merge two policies into one reply.

Attribute names and values are validated before they reach SQL or `radclient`
(dictionary-shaped names, no quotes/newlines, 253-byte limit) since both are
line-oriented formats where a stray newline would inject an extra attribute.

### MAB test path

The **Auth Test** MAB option runs `radclient` (from `freeradius-utils`, installed
in the backend image) inside the backend container against `freeradius:1812`,
building the same request a switch sends: MAC as `User-Name`/`User-Password`,
`Service-Type = Call-Check`, `Calling-Station-Id`, and the container's own address
as `NAS-IP-Address`. `radclient` exits 0 for any answered request, so the reply
packet type — not the exit code — decides accept vs reject.

### CoA / Disconnect path

Session control is the opposite direction: the backend runs `radclient` toward
the NAS (or the lab CoA sink) on UDP **3799**, with `disconnect` or `coa` as the
packet type. The document identifies the session with `User-Name` and
`Calling-Station-Id` (the endpoint MAC); a CoA-Request also carries the
authorization attributes the policy would have returned on Access-Accept.

The **lab CoA sink** is an in-process RADIUS responder bound to the backend
loopback (`127.0.0.1:3799` by default, secret `FREERADIUS_LAB_SECRET`). It is
not published to the host. It ACKs any well-formed CoA/Disconnect that includes
an identity, and NAKs (Error-Cause 404) if both `User-Name` and
`Calling-Station-Id` are missing. A registered RADIUS client is used when the
operator wants to talk to real hardware that has dynamic authorization enabled.

`POST /api/session-actions` returns 200 with `result: ack|nak|timeout|error`
rather than failing the HTTP request on NAK/timeout, matching Auth Test.

### Auth event ingestion

FreeRADIUS module `linelog_dot1x` writes:

```text
DOT1X|<unix-epoch>|<User-Name>|<NAS-IP-Address>|<EAP-Type>|<Access-Accept|Access-Reject>|<failure>|<Service-Type>|<reply attributes>
```

(`%l` epoch timestamps avoid brittle FreeRADIUS strftime xlats in linelog format strings.)

Fields 8–9 were added in Phase 3 and the parser treats them as optional, so events
written by an older FreeRADIUS container still parse:

- **`Service-Type`** — `Call-Check` with no `EAP-Type` identifies the attempt as
  MAB, which is how an event gets `method = mab`.
- **reply attributes** — `%{pairs:reply:}`, so the UI can show what the NAS
  actually received. The ingestion worker filters key material and protocol
  plumbing (`MS-MPPE-*`, `EAP-Message`, `State`, …) before storing the rest in
  `authentication_events.returned_attributes`.

A MAB reject carries no `Module-Failure-Message` — nothing failed, nothing
matched — so the worker looks the MAC up in `endpoints` and records whether it was
an unknown MAC or a disabled endpoint.

The backend lifespan task tails `FREERADIUS_AUTH_LOG_PATH` (shared volume) and inserts into `authentication_events`. Catch-all `lab-docker-host-N` clients scoped to the container's own Docker bridge subnets (secret `FREERADIUS_LAB_SECRET`, default `testing123`) accept RADIUS from Compose published ports on the Docker host; real NAS devices need per-NAS clients created in the UI.

## Wireless labs (Phase 4)

A lab's `settings` column is free-form, but a wireless lab stores a validated
**wireless profile** under `settings.wireless_profile`: the SSID, the security
mode (`wpa2_enterprise` / `wpa3_enterprise`), the VLAN its policy hands out, and
the user group that policy is bound to. It is validated on the way in — an SSID
must fit 802.11's 32-**octet** element and carry no control characters — because
these values are copied straight onto real radio hardware.
`PUT /labs/{id}/wireless-profile` merges the profile into the settings document
rather than replacing it, so recording an SSID cannot drop a lab's pinned RADIUS
target.

Nothing about the data plane changes for wireless: the AP/WLC is a RADIUS client
like any switch, and per-user VLANs come from an authorization policy bound to a
user group (`radgroupreply`), which is what lets one SSID place clients in
different VLANs.

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
