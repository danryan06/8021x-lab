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
- Automatic expiry sweep: active certificates whose `not_after` has passed are
  marked `expired` on inventory list and at API startup (done)
- **Intermediate CA** (openssl): optional teaching chain — root signs an
  intermediate, the intermediate signs client certs, PKCS#12 and FreeRADIUS trust
  carry both (done)
- **step-ca adapter**: `CA_ADAPTER=step-ca` + `STEP_CA_URL` / `STEP_CA_TOKEN`
  issues via `POST /1.0/sign` against a running Smallstep CA (done; openssl stays
  the Compose default)

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
- **Policy conditions**: optional `Login-Time` (weekdays 08:00–17:00, weekends,
  overnight, or a raw FreeRADIUS string) and `NAS-IP-Address` (one registered
  client). Written as check items to `radcheck` / `radgroupcheck`, so a known
  MAC or user is still rejected outside the window or from another switch
- Policies apply to endpoints via `radreply` and to user groups via
  `radgroupreply`, so PEAP and EAP-TLS sessions get authorized too
- Returned attributes are recorded on each event and shown in the Events UI
- Dashboard endpoint/policy counts + recent MAB activity; guided **MAB wizard
  path** (policy → endpoint → client → test → events)
- **CoA / Disconnect-Request** from the Endpoints page: RADIUS originates a
  Disconnect-Request (drop the session) or CoA-Request (push the endpoint's VLAN/
  role) toward the NAS on UDP 3799. Compose has no switch listening, so a **lab
  CoA sink** in the backend ACKs the packet for demos; a registered RADIUS client
  is the path to real hardware with dynamic authorization enabled

## Phase 4 — Wizard expansions (done)

- **Guided wireless path**: choosing *wireless* reshapes the flow around an SSID
  — name it (with 802.11's 32-octet limit enforced as you type), pick
  WPA2/WPA3-Enterprise, and finish on a checklist carrying every value the AP or
  WLC asks for, built from what the run actually created
- **Dynamic VLAN assignment** for wireless PEAP: a policy bound to the wizard's
  user group, so one SSID can place clients in a VLAN via `radgroupreply` —
  proven by the returned attributes on the live test
- Wireless copy throughout: the RADIUS client step asks for the controller's
  source address rather than a switch's, and the client step can be skipped
  (in-Compose tests do not need a NAS client)
- A lab now carries a validated **wireless profile** (`settings.wireless_profile`),
  so the SSID, security mode, and VLAN survive the run
- Robustness found by running the flows: two RADIUS clients can no longer claim
  one address (which made FreeRADIUS refuse to start), the clients file covers
  every lab instead of only the one being synced, and a duplicate lab name is
  explained instead of returning a 500
- Remaining: none for the guided paths. Guest/captive-portal analogue lives on
  the **Guest** page (short-lived PEAP users in the `guests` group). The wizard
  **wired and wireless** medium runs the SSID flow and both checklists. The
  Dashboard lists each lab's stored SSID and its RADIUS clients.

## Phase 5 — Appliance packaging

- Linux one-line installer (`scripts/install.sh`) plus schema/seed on backend
  start, so a fresh machine is a single command (Compose-on-Linux path)
- In-place upgrade (`scripts/upgrade.sh`) that pulls, rebuilds, and keeps
  `.env` plus lab data volumes
- Ubuntu LTS image path, health UI, non-Docker operator UX
- Later: OVA, Proxmox, Raspberry Pi prebuilt image

## Explicitly deferred

- Active Directory / LDAP / cloud IdP
- Vendor config generators (Cisco, Aruba, Mist, Fortinet, …)
- Packet capture integration
- Classroom / certification lab packs
- Production hardening
