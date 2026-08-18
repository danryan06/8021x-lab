# Usage guide

Task-oriented walkthroughs for using the lab from the web UI. New to the
terminology (RADIUS client, PEAP, EAP-TLS, MAB, CA/CRL)? Read the
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
is an isolated set of users, endpoints, clients, authorization policies,
certificates, and events — you can run several side by side.

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

## Guide: MAB for a device that can't do 802.1X

MAB authenticates a device by its MAC address alone — the fallback for printers,
cameras, and badge readers with no supplicant. The **Wizard → MAB** path automates
policy → endpoint → test; by hand:

1. **Create an authorization policy.** On **Authorization → Add policy**, name it
   (e.g. `Printers VLAN 40`), set the **VLAN** to `40` and the **role** to
   something your switch knows (e.g. `printer-acl`). This is what FreeRADIUS
   returns when the device is accepted.
2. **Register the endpoint.** On **Endpoints → Add endpoint**, paste the MAC in
   whatever format you have it — `aa:bb:cc:dd:ee:ff`, `aa-bb-cc-dd-ee-ff`,
   `aabb.ccdd.eeff`, or `aabbccddeeff` all work — pick a device type, and attach
   the policy. Saving registers the MAC in FreeRADIUS immediately; no restart.
3. **Test it.** On **Auth Test**, choose method **MAB**, pick the endpoint, and
   **Run test**. You should get an Access-Accept with `VLAN 40 · role printer-acl`
   shown as the returned attributes.
4. **Try the negative cases.** **Unknown-MAC test** sends a MAC the lab has never
   seen; toggling an endpoint to **disabled** on the Endpoints page and re-testing
   shows the other rejection reason. Both appear on **Auth Events** with an
   explanation.

Because MAB trusts a MAC address and nothing else, treat it as inventory control
rather than authentication and give MAB devices a restricted VLAN — see
[why MAB is weak](concepts.md#why-mab-is-weak-authentication).

### Registering many endpoints at once

**Bulk add** takes a pasted list (one MAC per line, or comma/space separated),
normalizes each entry, skips duplicates, and reports any lines it could not parse
without discarding the good ones. **Generate** creates random MACs under a vendor
prefix with mixed device types, which is the quickest way to populate a demo.

## Guide: a wireless (WPA2/3-Enterprise) lab

The **Wizard** has a wireless path: pick **wireless** at the medium step and the
flow changes shape. Use it when the thing you're building is an SSID rather than
a switch port.

1. **Name the SSID.** Enter the network name your clients will join and pick
   **WPA2-Enterprise** or **WPA3-Enterprise**. The lab is the RADIUS server for
   that SSID — it does not broadcast anything itself, so this is recorded on the
   lab and replayed as a checklist at the end. The field counts bytes as you
   type, because 802.11 caps an SSID at 32 octets.
2. **Create or select the lab**, then create the identity: a PEAP user, or a CA
   plus a client certificate for EAP-TLS, or a policy plus a registered MAC for
   MAB — the same steps as the wired paths.
3. **Put SSID users in a VLAN** (PEAP). This creates an authorization policy
   bound to the `lab` user group that the wizard's user belongs to, so the
   Access-Accept carries `VLAN <id>` — dynamic VLAN assignment from a single
   SSID. The VLAN must already exist on the controller and its uplink.
4. **Register the AP/WLC** as a RADIUS client, using the address the *controller*
   sources RADIUS from (usually its management interface, not each AP). You can
   **Skip for now** — the built-in test runs inside Compose and doesn't need it.
5. **Run the test**, then read the finished page: SSID, security mode, EAP
   method, RADIUS server IP and ports, the shared secret (masked, click
   **Reveal**), the VLAN that comes back, and the client you registered — every
   value the controller asks for, in one place.

For EAP-TLS the wizard does not create a VLAN step, because certificate
identities pick up attributes through user-group membership: create the policy on
the **Authorization** page and make sure a lab user with that certificate's
identity is in the group.

## Guide: authorization policies (VLAN and role)

Authentication decides *whether* a device gets on; authorization decides *what it
gets*. The **Authorization** page edits that second half, and the Simple/Advanced
toggle changes how much protocol you see:

- **Simple** — pick a **VLAN** and a **role**. The lab renders the VLAN into the
  three tunnel attributes a switch needs, and the role into `Filter-Id`.
- **Advanced** — edit reply attributes directly by their RADIUS names, with a
  catalog of common ones (`Session-Timeout`, `Cisco-AVPair`, …) for reference. A
  raw attribute that repeats one of the rendered names replaces it, so you can
  override the VLAN with a VLAN *name* instead of an id.

Attach a policy in either of two places:

| Attach to | How | Applies to |
|-----------|-----|------------|
| An endpoint | The **Authorization policy** field on Endpoints | That MAC, over MAB |
| A user group | The **User group** field on the policy | Every user in that group, over PEAP and EAP-TLS |

One policy per user group — if two policies claimed the same group, FreeRADIUS
would merge both into one reply, which is rarely what you meant.

After a successful authentication, check the **Authorization** column on **Auth
Events** to confirm what the NAS actually received. If a device isn't landing in
the VLAN you expect, this tells you whether the problem is on the RADIUS side (no
attributes returned) or the switch side (attributes returned but not acted on —
usually a VLAN or ACL that doesn't exist on the device).

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
   **One address, one client:** FreeRADIUS identifies a NAS by its source
   address, so a second client for an address already registered (in any lab) is
   refused with a message naming the one that holds it — edit or reuse that
   client, or disable it first.
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
| Unknown MAC address | No endpoint registered for that MAC | Add it on **Endpoints** |
| Endpoint is disabled | Registered but not synced to FreeRADIUS | Re-enable it on **Endpoints** |

## Guide: keeping FreeRADIUS in sync

Most changes sync automatically, but **Sync to FreeRADIUS** (Dashboard, Users,
Clients) forces a full resync after bulk edits. What each change does:

| Action | FreeRADIUS effect |
|--------|-------------------|
| Create/update/delete/generate/import user | Upsert/delete `radcheck` NT-Password |
| Create/update/delete RADIUS client | Rewrite clients config + controlled restart |
| Create/update/delete/generate endpoint | Upsert/delete `radcheck` (`Auth-Type := Accept`) + `radreply` for every MAC spelling |
| Create/update/delete authorization policy | Rewrite `radreply` for endpoints using it and `radgroupreply` for its user group |
| Issue certificate / create lab CA | Publish CA into trust; restart if trust changed |
| Revoke certificate | Regenerate + publish CRL; restart if it changed |
| Auth Test | Runs `eapol_test` (PEAP/EAP-TLS) or `radclient` (MAB) → FreeRADIUS → event |

A controlled restart is used for client and trust changes because FreeRADIUS 3
only reads those at startup (it does not reload them on SIGHUP). Endpoints and
policies need neither a reload nor a restart — FreeRADIUS reads those tables per
request, so a MAC you just registered works on the next attempt.

## Where to go next

- [Deploying to devices](deploying-to-devices.md) — install a certificate on a real endpoint and configure a switch port or Wi-Fi SSID for 802.1X.
- [Concepts](concepts.md) — the "what and why" behind these tasks.
- [Developer setup](developer-setup.md) — commands, testing, running outside Compose.
- [Roadmap](roadmap.md) — what's built and what's planned.
