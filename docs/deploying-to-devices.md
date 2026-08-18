# Deploying to real devices

You've proven authentication works in the lab — now here's how to take it to real
hardware: installing an EAP-TLS certificate on an endpoint, and configuring a
switch port or a wireless SSID to use the lab as its RADIUS server.

This is a **lab/education** walkthrough. Command syntax varies by vendor and
version; the examples use common platforms to illustrate the ideas. New to the
terms used here (RADIUS client, EAP-TLS, CA)? See [concepts.md](concepts.md).

## Before you start: three things must line up

1. **The RADIUS target** — the IP address your device/switch/AP sends RADIUS to.
   Find it on the **Dashboard → RADIUS target** card (and the UDP ports, default
   `1812`/`1813`, and the lab shared secret — click **Reveal**).
2. **The RADIUS client** — the switch/AP must be registered under **RADIUS
   Clients** with its **source IP** and the **shared secret**, or FreeRADIUS will
   ignore it. ([Why?](concepts.md#why-you-add-devices-as-radius-clients))
3. **Trust** — for **EAP-TLS**, the client needs a certificate issued by the lab
   CA (which FreeRADIUS already trusts), and the client should trust the lab CA so
   it can validate the RADIUS server. For **PEAP**, the client just needs a
   username/password that exists in the lab.

> **Where to run this:** use a Linux host (like a Raspberry Pi) for real-device
> testing. On Docker Desktop for macOS/Windows the RADIUS source IP is rewritten,
> so per-device client matching won't work — see [deployment.md](deployment.md).

---

## Part A — Deploy an EAP-TLS certificate to an endpoint

### 1. Get the certificate material

From the **Certificates** page (or the **Auth Test** page's EAP-TLS actions):

- **Issue** a client certificate for an identity (e.g. `alice`).
- **Download PEM/P12 bundle** — a ZIP with the client cert + key as PEM and a
  `.p12` (empty passphrase) for easy import.
- **Download root CA** — the lab CA certificate the device should trust.

### 2. Install it on the device

**Windows**

1. Double-click the `.p12` → import into **Current User → Personal**. (Empty
   password.)
2. Import the **root CA** `.pem` into **Trusted Root Certification Authorities**
   (run `certlm.msc` / `certmgr.msc`).
3. Wi-Fi/wired adapter → 802.1X settings → choose **Microsoft: Smart Card or other
   certificate (EAP-TLS)** → select the imported client certificate and validate
   the server against the lab CA.

**macOS**

1. Double-click the `.p12` and the root CA `.pem` to add them to **Keychain
   Access** (login keychain); mark the root CA as trusted.
2. Join the network and pick the client certificate when prompted (or push a
   configuration profile for a repeatable setup).

**Linux (NetworkManager)**

Wi-Fi security → **WPA/WPA2 Enterprise**, Authentication **TLS**, then set:
identity, **User certificate** (client cert PEM), **CA certificate** (lab root
PEM), and **Private key** (key PEM). For wired, use the 802.1X tab with the same
fields.

**iOS / Android**

Install the `.p12` (and root CA) via a configuration profile / "install a
certificate", then select EAP-TLS and the client certificate in the Wi-Fi
settings. Managed fleets push this with an MDM profile.

> The lab-issued `.p12` uses an **empty passphrase** for convenience. That's a
> lab shortcut — real deployments protect the private key.

---

## Part B — Configure a wired switch port for 802.1X

The switch is the **authenticator**: it forces the connected device to
authenticate to the lab (the RADIUS server) before opening the port. Example
using Cisco IOS-style syntax — adapt to your vendor:

```text
! 1) Point the switch at the lab as its RADIUS server
aaa new-model
radius server DOT1X-LAB
 address ipv4 <RADIUS_TARGET_IP> auth-port 1812 acct-port 1813
 key <LAB_SHARED_SECRET>

aaa authentication dot1x default group radius
aaa authorization network default group radius
dot1x system-auth-control

! 2) Enable 802.1X on the access port
interface GigabitEthernet0/1
 switchport mode access
 authentication port-control auto      ! newer IOS: access-session / "authentication" cmds vary
 dot1x pae authenticator
```

Then, in the lab UI, register this switch under **RADIUS Clients** with the
switch's **source IP** (the interface it sources RADIUS from) and the same
**shared secret**. Connect a configured endpoint and watch **Auth Events**.

To send a Disconnect-Request or CoA from the lab, enable **dynamic authorization**
on the switch (Cisco: `aaa server radius dynamic-author`, client = the lab's
RADIUS target IP, port 3799, same secret) and use **Endpoints → Disconnect** /
**Push policy** with that RADIUS client selected as the target. Compose-only
demos use the lab CoA sink instead — see
[session control](concepts.md#session-control-coa-and-disconnect-request).

---

## Part C — Configure a wireless SSID for WPA2/3-Enterprise

The access point or wireless LAN controller is the authenticator. The exact menus
differ by vendor, but every controller needs the same inputs.

> **Shortcut:** the **Wizard → wireless** path ends on a page listing these
> values for the lab you just built — SSID, security mode, RADIUS server IP and
> ports, shared secret, and the VLAN that comes back. See
> [usage.md](usage.md#guide-a-wireless-wpa23-enterprise-lab).


1. **Create/define a RADIUS server** pointing at the **RADIUS target IP**, auth
   port `1812` (accounting `1813`), with the **lab shared secret**.
2. **Create an SSID** with security **WPA2-Enterprise** (or WPA3-Enterprise) /
   **802.1X**, and set its authentication (AAA) server to the RADIUS server above.
3. Choose the EAP method on the client side: **EAP-TLS** (certificate) or **PEAP**
   (username/password) — both are supported by the lab.
4. Register the AP/WLC (its RADIUS **source IP**) under **RADIUS Clients** with the
   shared secret.

Connect a device to the SSID:

- **PEAP:** enter a lab username/password.
- **EAP-TLS:** select the installed client certificate (Part A).

Watch **Auth Events** for the Accept/Reject and, on failure, the plain-language
explanation.

---

## Troubleshooting

| Symptom | Likely cause | Where to look |
|---------|-------------|---------------|
| Nothing appears in Auth Events | Switch/AP not registered, or wrong RADIUS target IP | RADIUS Clients (source IP + secret); Dashboard RADIUS target |
| "Untrusted CA" reject | Client cert not from the lab CA, or CA not published | Certificates page → issue from lab CA / Sync |
| PEAP password rejected | Wrong password or user not synced | Users page → Edit (reset password) or Enable; Sync to FreeRADIUS |
| Client won't trust the server | Device doesn't trust the lab CA | Install the root CA (Part A step 2) |

See [usage.md](usage.md#guide-reading-and-troubleshooting-auth-events) for reading
events, and [concepts.md](concepts.md) for the underlying ideas.
