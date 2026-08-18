# Concepts: 802.1X, RADIUS, and PKI

This guide explains the ideas behind the lab in plain language, aimed at Wi-Fi
and network engineers who are new to enterprise authentication. It covers *what*
each piece is and *why* it exists. For step-by-step tasks, see the
[usage guide](usage.md); for the system design, see [architecture.md](architecture.md).

## The big picture: what 802.1X actually does

802.1X is a standard for **port-based network access control**. Instead of any
device that plugs into a switch port (or associates to an SSID) getting on the
network, the device must first *authenticate*. Only after it proves who it is
does the switch or access point open the port and let traffic through.

There are three roles in every 802.1X exchange:

| Role | What it is | In this lab |
|------|-----------|-------------|
| **Supplicant** | The device trying to get on the network (laptop, phone, printer) | `eapol_test` simulates this for you (`radclient` for MAB, which has no supplicant) |
| **Authenticator** | The switch or wireless access point/controller enforcing the port | Your real NAS, or the built-in test path |
| **Authentication server** | The RADIUS server that makes the accept/reject decision | FreeRADIUS, driven by this control plane |

The key idea: **the switch/AP does not decide who gets in — it asks the RADIUS
server.** The switch just enforces the answer. This separation is why you can
have one central policy for thousands of switches.

## RADIUS: the protocol between the switch and the auth server

RADIUS (Remote Authentication Dial-In User Service) is the protocol the
authenticator uses to ask the authentication server "should I let this device
on?" It runs over UDP — port **1812** for authentication and **1813** for
accounting.

When a device tries to connect, the switch packages the credentials and sends an
**Access-Request** to FreeRADIUS. FreeRADIUS replies with **Access-Accept** (let
them on, optionally with instructions like a VLAN) or **Access-Reject** (deny).

## Why you add devices as "RADIUS clients"

This is the question that trips up most newcomers, so it's worth being precise.

A **RADIUS client** is *not* an end-user device (laptop/phone). A RADIUS client
is a **network access device** — a switch, wireless controller, or access point —
that is allowed to send authentication requests to the RADIUS server. In RADIUS
terminology these are called the **NAS** (Network Access Server).

FreeRADIUS will **ignore requests from any source it does not recognize.** Two
things must line up before it will even process a request:

1. **The source IP** of the request must match a configured client, and
2. **The shared secret** (a password shared between the switch and the RADIUS
   server) must match.

The shared secret is how the RADIUS server and the switch trust each other — it
signs parts of the exchange so neither side can be spoofed. It has nothing to do
with user passwords; it's a device-to-server secret you configure on both ends.

So "add your switch as a RADIUS client" means: *tell FreeRADIUS that this
specific network device, at this IP, using this shared secret, is authorized to
ask authentication questions.* Without it, every request from that switch is
silently dropped as coming from an unknown client.

> **RADIUS target vs RADIUS clients — don't confuse them.** The **RADIUS target**
> (shown on the Dashboard) is the IP address *your switch should point at* to
> reach FreeRADIUS. A **RADIUS client** is the reverse direction: the switch's
> *own* source IP + secret that FreeRADIUS must recognize. You configure the
> target on the switch; you register the client here.

## Users vs. the admin account

There are two very different kinds of "login" in the lab:

- The **admin account** (`ADMIN_USERNAME`/`ADMIN_PASSWORD`) logs you into this
  web UI. It is not a RADIUS identity.
- **RADIUS users** are the lab identities that authenticate *through* 802.1X
  (for PEAP). They live in the database and are synced to FreeRADIUS.

## EAP methods: PEAP vs. EAP-TLS

802.1X carries an inner authentication protocol called **EAP** (Extensible
Authentication Protocol). "Extensible" means there are many EAP *methods*; this
lab focuses on the two most common in enterprise networks.

### PEAP with MSCHAPv2 (password-based)

**PEAP** wraps a username/password exchange (MSCHAPv2) inside a TLS tunnel. The
server presents a certificate to build the tunnel, and the user authenticates
with a password inside it.

- **Why use it:** easy to roll out — users just need a username and password.
- **The catch:** MSCHAPv2 can't use a modern password hash like bcrypt. It needs
  an **NT hash** (`MD4` of the password in UTF-16LE). That's why the lab computes
  and stores an NT hash for each user and syncs it to FreeRADIUS's `radcheck`
  table. (The lab also keeps a separate bcrypt hash for its own purposes and
  never logs either value.)

### EAP-TLS (certificate-based)

**EAP-TLS** uses a **client certificate** instead of a password. Both the server
*and* the client present certificates, and each verifies the other.

- **Why use it:** it's the strongest common method — there's no password to
  phish, guess, or reuse. It's the gold standard for enterprise Wi-Fi.
- **The catch:** it requires a **PKI** — someone has to issue and manage the
  certificates. That's what the lab's certificate authority is for.

## Certificates, the CA, and why they matter

A **certificate** is a small signed document that says "this public key belongs
to this identity," vouched for by a **Certificate Authority (CA)**. In EAP-TLS,
the client's certificate is its identity — presenting a valid one, issued by a CA
the server trusts, *is* the authentication.

The lab runs a small local CA so you can experience the whole PKI lifecycle
without standing up enterprise infrastructure:

- **Root CA** — the trust anchor. The lab creates one per lab environment. Its
  certificate is what FreeRADIUS trusts; any client certificate signed by it is
  accepted.
- **Client certificate** — issued to an identity (e.g. `alice`). You download it
  as a PEM bundle or a `.p12` file to import on a device.
- **Trust publishing** — for FreeRADIUS to accept EAP-TLS clients, it must trust
  the lab CA. The lab publishes the CA into FreeRADIUS's trust store, which is
  why issuing a cert also triggers a FreeRADIUS trust update.

### Revocation and the CRL

Sometimes a certificate must be invalidated *before* it expires — a laptop is
lost, an employee leaves, a key is compromised. **Revocation** is how you say
"this certificate is no longer valid," and a **Certificate Revocation List
(CRL)** is the signed list of revoked serial numbers that the server checks.

The lab implements this properly: revoking a certificate records it in the CA
database, regenerates the CRL, and publishes it. Whether FreeRADIUS *enforces*
the CRL during EAP-TLS is opt-in (`FREERADIUS_ENFORCE_CRL`), because turning on
CRL checking requires a current CRL for every trusted CA or authentication
fails — a classic real-world PKI footgun the lab lets you experiment with safely.

## MAB: for devices that cannot do 802.1X

Not every device can run a supplicant. Printers, IP cameras, badge readers,
thermostats, and older medical equipment often have no 802.1X support at all. If
your only options were "authenticate with 802.1X" or "stay off the network," you
could never turn 802.1X on.

**MAB (MAC Authentication Bypass)** is the escape hatch. When a switch port sees
no EAPOL response — the device never answers the 802.1X request — the switch
falls back to MAB: it takes the device's **MAC address**, puts it in the
`User-Name` field, and sends an ordinary Access-Request marked
`Service-Type = Call-Check` (RADIUS's way of saying "this is a MAC lookup, not a
user login"). If the RADIUS server recognizes that MAC, the device gets on.

In this lab you register a MAC as an **endpoint**. Enabled endpoints are synced
into FreeRADIUS as `Auth-Type := Accept`, which means "if the `User-Name` matches
this MAC, accept it" — there is no password to verify, because there is no
password.

### Why MAB is weak authentication

This is the part worth internalizing:

- **A MAC address is not a secret.** It is printed on the device label, broadcast
  in every frame the device sends, and visible to anyone with a laptop on the
  same segment.
- **MAC addresses are trivially spoofable.** Changing a NIC's MAC is a one-line
  command on every major operating system. Anyone who can read a MAC can *become*
  that device as far as MAB is concerned.
- **There is no cryptography anywhere in the exchange.** PEAP has a TLS tunnel
  and a password; EAP-TLS has mutual certificate validation. MAB has a string
  comparison.

So MAB is best understood as **inventory control, not authentication**. It answers
"is this a device we know about?" — not "is this device who it claims to be." The
standard mitigation is to pair MAB with restrictive authorization: put MAB
devices in their own VLAN with an ACL that only permits the traffic that kind of
device actually needs, so a spoofed printer MAC gets you onto the printer VLAN
and nowhere else.

To make this concrete, one detail matters for real hardware: **vendors spell MAC
addresses differently.** Cisco IOS sends bare hex (`aabbccddeeff`), Cisco WLC and
Juniper use colons, some Windows tooling uses hyphens, and case varies. The lab
stores one canonical form (`aa:bb:cc:dd:ee:ff`) but registers every common
spelling in FreeRADIUS, so the same endpoint authenticates whatever your switch
sends.

## Authorization: what the switch does after "yes"

**Authentication** answers "who is this?". **Authorization** answers "and what
access do they get?". They are separate questions, and RADIUS answers both in the
same packet: an Access-Accept can carry **reply attributes** that tell the switch
what to do with the session.

The lab models this as an **authorization policy**. A policy has friendly fields
(a VLAN, a role) and optionally any raw attributes you want, and it renders down
to the RADIUS attributes a switch or AP actually understands:

| You configure | FreeRADIUS returns | What the NAS does |
|---------------|-------------------|-------------------|
| VLAN `40` | `Tunnel-Type = VLAN`<br>`Tunnel-Medium-Type = IEEE-802`<br>`Tunnel-Private-Group-Id = 40` | Puts the port or client into VLAN 40 |
| Role `printer-acl` | `Filter-Id = printer-acl` | Applies the ACL/role named `printer-acl`, which must already exist on the device |
| Anything else | The attribute verbatim (e.g. `Session-Timeout`, `Cisco-AVPair`) | Vendor-specific behaviour |

Two things about this are worth calling out because they surprise people:

- **A VLAN assignment is three attributes, not one.** `Tunnel-Private-Group-Id`
  carries the VLAN, but a switch will ignore it unless `Tunnel-Type` and
  `Tunnel-Medium-Type` are also present and correct. The Simple editor fills all
  three for you; the Advanced editor shows you that it did.
- **RADIUS only names the role — it does not define it.** `Filter-Id = printer-acl`
  tells the switch "apply the thing you already call `printer-acl`". If that ACL
  doesn't exist on the switch, nothing happens. RADIUS assigns policy; the NAS
  implements it.

Policies attach in two places: to an **endpoint** (so a MAB device gets its VLAN)
and to a **user group** (so PEAP and EAP-TLS users get theirs). Every accepted
authentication records the attributes that were actually returned, and the Events
page shows them — so you can confirm the switch really received `VLAN 40` rather
than assuming it did.

## Session control: CoA and Disconnect-Request

Access-Request always travels **NAS → RADIUS** (UDP 1812). Once a session is up,
the RADIUS side can talk back to the NAS without waiting for the next
authentication:

- **Disconnect-Request** (UDP **3799**): drop this session now.
- **CoA-Request** (Change of Authorization, same port): keep the session but
  apply a new VLAN or role.

That reverse direction is the part that surprises people. The switch is still
the authenticator — it owns the port — but RADIUS can tell it to change what
the port is doing. This is how a NAC kicks a device or moves it after posture.

The lab originates these packets with `radclient` from the backend container,
using the endpoint's MAC as `User-Name` and `Calling-Station-Id`. Compose has
no switch listening on 3799, so a Disconnect aimed at `10.0.0.1` times out. The
default target is therefore a **lab CoA sink**: a small RADIUS responder in the
backend process that ACKs the packet so you can see the exchange. It does not
drop a real session.

To talk to real hardware, pick a registered RADIUS client as the target. That
device must have **dynamic authorization** enabled (Cisco IOS:
`aaa server radius dynamic-author`) and listen on UDP 3799 with the same shared
secret you stored on the client. The Endpoints page has Disconnect and Push
policy on each row.

## Wireless: the same 802.1X, with the AP as the authenticator

Nothing about RADIUS changes on Wi-Fi. The access point or wireless LAN
controller plays the role the switch plays on a wired port: it blocks traffic
until the client authenticates, relays EAP to the lab, and applies whatever the
Access-Accept says. The parts that *are* wireless-specific are worth knowing:

- **The SSID is where 802.1X is switched on.** A network advertised as
  **WPA2-Enterprise** or **WPA3-Enterprise** uses 802.1X/EAP; the "Personal"
  variants use a shared passphrase and never talk to RADIUS. WPA3-Enterprise
  additionally requires protected management frames (802.11w) and newer clients,
  but from RADIUS's point of view the two are identical.
- **The SSID name has a hard limit.** 802.11 carries it in a 32-octet field, so
  a name is capped at 32 *bytes* — accented or emoji characters cost more than
  one byte each.
- **One SSID can serve many VLANs.** This is the usual reason to build a
  wireless lab: instead of one SSID per department, every client joins the same
  network and the Access-Accept says which VLAN it lands in. In the lab that is
  an authorization policy bound to a **user group** — staff land in one VLAN,
  contractors in another, from a single SSID. The controller must have those
  VLANs and have AAA override (dynamic VLAN assignment) enabled, or it will
  authenticate everyone and ignore the VLAN.
- **The controller is the RADIUS client, not each AP.** Most controller-based
  deployments source RADIUS from the controller's management interface, so that
  is the address to register — registering individual APs is what people usually
  get wrong first.
- **MAB exists on wireless too**, as MAC filtering on an open or PSK SSID for
  devices with no supplicant. It is the same weak trust model as wired MAB.

The **Wizard → wireless** path walks all of this: name the SSID, create an
identity, give it a VLAN, register the controller, run a live test, and finish
with the exact values to type into the AP/WLC.

## Authentication events: seeing what happened

Every accept/reject decision FreeRADIUS makes is captured as an
**authentication event** and shown on the Auth Events page. This is the feedback
loop that makes the lab useful for learning: you make a change, run a test, and
see exactly whether it was accepted or rejected — and if rejected, a
plain-language explanation (untrusted CA, expired/revoked certificate, wrong
password, unknown user, unknown MAC, disabled endpoint) plus a hint on how to fix
it. Accepted events also show the reply attributes that went back to the NAS, so
authorization is visible and not just assumed.

## Simple vs. Advanced mode

The UI has a **Simple/Advanced** toggle. Simple mode hides protocol detail to
keep first-time flows approachable; Advanced mode surfaces the underlying values
(certificate serials, shared secrets, health probe detail, lab IDs) once you want
to see what's really happening. The philosophy is: *make the easy path easy,
without hiding the real machinery from someone who wants to learn it.*

Authorization policies are the clearest example. In Simple mode you pick a VLAN
and a role; in Advanced mode you edit the reply attributes directly by their
RADIUS names and can see that "VLAN 40" really means three tunnel attributes.
Both modes edit the same policy — the toggle changes how much of the protocol you
are looking at, not what the lab does.

## Where to go next

- [Usage guide](usage.md) — do these things step by step in the UI.
- [Architecture](architecture.md) — how the control plane, FreeRADIUS, and CA fit together.
- [Roadmap](roadmap.md) — what's built and what's planned (policy conditions, step-ca).
