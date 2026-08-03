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
| **Supplicant** | The device trying to get on the network (laptop, phone, printer) | `eapol_test` simulates this for you |
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

## Authentication events: seeing what happened

Every accept/reject decision FreeRADIUS makes is captured as an
**authentication event** and shown on the Auth Events page. This is the feedback
loop that makes the lab useful for learning: you make a change, run a test, and
see exactly whether it was accepted or rejected — and if rejected, a
plain-language explanation (untrusted CA, expired/revoked certificate, wrong
password, unknown user) plus a hint on how to fix it.

## Simple vs. Advanced mode

The UI has a **Simple/Advanced** toggle. Simple mode hides protocol detail to
keep first-time flows approachable; Advanced mode surfaces the underlying values
(certificate serials, shared secrets, health probe detail, lab IDs) once you want
to see what's really happening. The philosophy is: *make the easy path easy,
without hiding the real machinery from someone who wants to learn it.*

## Where to go next

- [Usage guide](usage.md) — do these things step by step in the UI.
- [Architecture](architecture.md) — how the control plane, FreeRADIUS, and CA fit together.
- [Roadmap](roadmap.md) — what's built and what's planned (MAB, VLAN policies, step-ca).
