# Usage guide

Task-oriented walkthroughs for using the lab from the web UI. New to the
terminology (RADIUS client, PEAP, EAP-TLS, CA/CRL)? Read the
[concepts guide](concepts.md) first — this guide assumes you know *what* the
pieces are and focuses on *how* to use them.

For install/setup and the command reference, see
[developer-setup.md](developer-setup.md).

## Getting started

1. Bring up the stack: `make bootstrap` (or `cp .env.example .env && make up &&
   make migrate && make seed`).
2. Open the UI at http://localhost:3000 and log in with the admin credentials
   from your `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`).
3. You'll land on the **Dashboard**: live health for the database, API, and
   FreeRADIUS, the most recent auth event, and the **RADIUS target** card.

The seeded **Default Lab** gives you a working environment to start in. A *lab*
is an isolated set of users, clients, certificates, and events — you can run
several side by side.

The header has two global controls used throughout:

- **Simple / Advanced** — Advanced reveals serials, secrets, health detail, IDs.
- **Dark / Light** — theme preference, remembered in your browser.

## Guide: your first PEAP login (password-based)

The fastest way to see 802.1X work end to end. The **Wizard** automates it (hover
or tab to the **ⓘ** next to any step for a fly-out explaining what that step does,
what it configures, and what comes next), or do it by hand:

1. **Create a user.** Go to **Users → Add user**, set a username and password
   (optionally first/last/department). Saving syncs the user's NT-Password into
   FreeRADIUS automatically.
2. **Run the test.** Go to **Auth Test**, choose your lab, method **PEAP**,
   select the user, enter the password, and **Run test**.
3. **See the result.** You'll get an Accept/Reject inline, and a new row appears
   on **Auth Events**. Try the **wrong-password** button to see a Reject and its
   explanation.

You did not need to add a RADIUS client for this: UI tests run `eapol_test` from
inside the backend container over the Compose network, using the built-in lab
secret. Adding clients matters when a *real* switch is involved (below).

### Creating many users at once

On **Users**, use **Generate** to create demo identities in bulk. You choose the
username style (numbered, first.last, flast, email-like), which profile fields to
populate, and the password style — **easy** passwords are a word plus digits
(e.g. `maple482`) that are simple to type during a demo. You can view the
generated credentials as a table, list, or CSV, and copy them. There's also a
**CSV template + import** if you'd rather bring your own list.

## Guide: EAP-TLS with certificates

EAP-TLS authenticates with a client certificate instead of a password. The
**Wizard → EAP-TLS** path automates the whole chain; to understand each step,
use the **Certificates** and **Auth Test** pages directly:

1. **Create the lab CA.** On **Certificates**, if no CA exists yet, click
   **Create lab CA**. This is your trust anchor and is published into FreeRADIUS
   so it will trust certificates the CA issues.
2. **Issue a client certificate.** Enter an identity (the CN, e.g. `alice`) and
   **Issue certificate**. Download the **bundle** (PEM + key + root, for
   `eapol_test`) or the **.p12** (to import on Windows/macOS, empty passphrase).
3. **Test it.** On **Auth Test**, choose method **EAP-TLS** and the identity, then
   **Run test**. Because trust changes require a FreeRADIUS restart, the first
   EAP-TLS test after publishing a new CA waits a few seconds.
4. **See the result** on **Auth Events**, same as PEAP.

Identities must contain only letters, digits, and `. _ @ -` (they become both the
certificate CN and a filename), so pick clean names.

## Guide: managing certificates and revocation

The **Certificates** page is the CA inventory for a lab:

- **Status** — active, expired (past its validity), or revoked.
- **Download** — grab the bundle or `.p12` again at any time.
- **Revoke** — invalidate a certificate. This records it in the CA database,
  regenerates the **CRL**, and republishes trust to FreeRADIUS. Download the CRL
  with **Download CRL**.

Whether FreeRADIUS actually *rejects* a revoked certificate during EAP-TLS
depends on CRL enforcement, which is **off by default**. To try it, set
`FREERADIUS_ENFORCE_CRL=yes` for the freeradius service and restart the stack,
then revoke a cert and re-run its EAP-TLS test — it should now Reject. Leave it
off for normal use, since enforcement requires a current CRL for every trusted CA
(see [concepts](concepts.md#revocation-and-the-crl)).

## Guide: pointing a real switch or access point at the lab

To authenticate a real NAS (switch/WLC/AP) instead of the built-in test path:

1. **Find the RADIUS target.** On the **Dashboard**, the RADIUS target card shows
   the IP your NAS should send RADIUS to. **Auto** uses the detected host/DHCP
   address; switch to **Manual** to pin one. Note the auth/acct ports (UDP
   1812/1813) and the lab shared secret (click **Reveal**).
2. **Configure the NAS.** On the switch/WLC, point 802.1X/RADIUS at that IP and
   port, and set the shared secret to match.
3. **Register the NAS as a RADIUS client.** On **RADIUS Clients → Add client**,
   enter the NAS's **source IP** (the address FreeRADIUS will see the request
   come from) and the **same shared secret**. This is the step that authorizes
   the device — see [why in concepts](concepts.md#why-you-add-devices-as-radius-clients).
   Saving triggers a controlled FreeRADIUS restart so the new client is applied.
4. **Authenticate a real device** through that NAS and watch **Auth Events**.

> **Docker Desktop caveat (macOS/Windows):** published UDP ports rewrite the
> source IP, so FreeRADIUS sees an internal gateway rather than the NAS's real
> address, and per-NAS client matching won't work. Use a Linux Docker host for
> real-NAS testing. UI `eapol_test` runs are unaffected. See
> [deployment.md](deployment.md).

## Guide: reading and troubleshooting auth events

**Auth Events** auto-refreshes and colors Accept vs. Reject. For a rejected
event it shows a plain-language **summary** and a **hint**, with the raw
FreeRADIUS reason underneath (Advanced-friendly). Common ones:

| You see | Likely cause | Fix |
|---------|-------------|-----|
| Untrusted CA | Client cert not issued by a trusted lab CA | Sync/publish the lab CA (Certificates page) |
| Certificate expired / revoked | Cert past validity or on the CRL | Re-issue the certificate |
| PEAP/MSCHAPv2 password rejected | Wrong password or not synced | Confirm the password; Sync to FreeRADIUS |
| No matching user | Identity missing in FreeRADIUS | Create the user and Sync to FreeRADIUS |

## Guide: keeping FreeRADIUS in sync

Most changes sync automatically, but **Sync to FreeRADIUS** (Dashboard, Users,
Clients) forces a full resync after bulk edits. What each change does:

| Action | FreeRADIUS effect |
|--------|-------------------|
| Create/update/delete/generate/import user | Upsert/delete `radcheck` NT-Password |
| Create/update/delete RADIUS client | Rewrite clients config + controlled restart |
| Issue certificate / create lab CA | Publish CA into trust; restart if trust changed |
| Revoke certificate | Regenerate + publish CRL; restart if it changed |
| Auth Test | Runs `eapol_test` → FreeRADIUS → event |

A controlled restart is used for client and trust changes because FreeRADIUS 3
only reads those at startup (it does not reload them on SIGHUP).

## Where to go next

- [Concepts](concepts.md) — the "what and why" behind these tasks.
- [Developer setup](developer-setup.md) — commands, testing, running outside Compose.
- [Roadmap](roadmap.md) — MAB, VLAN/authorization policies, and more.
