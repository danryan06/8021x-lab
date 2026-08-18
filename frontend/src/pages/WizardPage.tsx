import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  apiDownload,
  apiFetch,
  type AuthTestResponse,
  type AuthzPolicy,
  type Endpoint,
  type Lab,
  type RadiusClient,
  type RadiusUser,
  type WirelessProfile,
  type WirelessSecurity,
} from "../api/client";
import { RadiusTargetPanel } from "../components/RadiusTargetPanel";
import { WirelessSummary } from "../components/WirelessSummary";
import {
  Button,
  Field,
  InfoTip,
  PageHeader,
  Panel,
  PasswordInput,
  ReplyAttributes,
  StatusBanner,
} from "../components/ui";

type AuthMethod = "peap" | "eap_tls" | "mab";
type Medium = "wired" | "wireless" | "both";

const METHOD_LABELS: Record<AuthMethod, string> = {
  peap: "PEAP",
  eap_tls: "EAP-TLS",
  mab: "MAB",
};

type StepId =
  | "medium"
  | "method"
  | "ssid"
  | "lab"
  | "user"
  | "ca"
  | "cert"
  | "policy"
  | "endpoint"
  | "wlan_policy"
  | "client"
  | "test"
  | "done";

type Step = { id: StepId; label: string };

// Every wizard user gets this group, so a policy bound to it authorizes the
// identities this flow creates without any per-user rows.
const WIZARD_USER_GROUP = "lab";

// 802.11 carries the SSID in a 32-octet element; the backend enforces the same
// limit, but saying so while typing beats a rejected request.
const SSID_MAX_BYTES = 32;

/**
 * The steps for one run. Wireless adds an SSID up front and, for PEAP, a VLAN
 * for the people joining it — the two things a wireless lab needs that a wired
 * one does not.
 */
function buildSteps(method: AuthMethod, medium: Medium): Step[] {
  const wireless = medium === "wireless";
  const steps: Step[] = [
    { id: "medium", label: "Select medium" },
    { id: "method", label: "Select authentication type" },
  ];
  if (wireless) steps.push({ id: "ssid", label: "Define the SSID" });
  steps.push({ id: "lab", label: "Create or select lab" });
  if (method === "peap") steps.push({ id: "user", label: "Create PEAP user" });
  if (method === "eap_tls") {
    steps.push(
      { id: "ca", label: "Ensure lab root CA" },
      { id: "cert", label: "Issue client certificate" },
    );
  }
  if (method === "mab") {
    steps.push(
      { id: "policy", label: "Create authorization policy" },
      { id: "endpoint", label: "Register endpoint MAC" },
    );
  }
  if (wireless && method === "peap") {
    steps.push({ id: "wlan_policy", label: "Put SSID users in a VLAN" });
  }
  steps.push({
    id: "client",
    label: wireless ? "Create RADIUS client (WLC/AP)" : "Create RADIUS client",
  });
  steps.push({
    id: "test",
    label:
      method === "eap_tls"
        ? "Run EAP-TLS test"
        : method === "mab"
          ? "Run MAB test"
          : "Run authentication test",
  });
  steps.push({ id: "done", label: wireless ? "Configure the SSID" : "View events" });
  return steps;
}

type StepHelp = { what: string; configuring: string; next: string };

// Per-step explanations shown in the fly-out: what the step does, what it
// actually configures, and what to do next. Kept plain-language for newcomers.
function stepHelp(id: StepId, method: AuthMethod, medium: Medium): StepHelp {
  const peap = method === "peap";
  const mab = method === "mab";
  const wireless = medium === "wireless";
  switch (id) {
    case "medium":
      return {
        what: "Records whether this lab targets wired switches, wireless APs/controllers, or both.",
        configuring:
          "Which steps you'll see and the device-type default (“wlc” vs “switch”). Wireless adds an SSID step and ends with a controller checklist; it does not change how authentication works.",
        next: "Choose the authentication type.",
      };
    case "ssid":
      return {
        what: "Records the wireless network your clients will join, so the rest of the flow can be described in SSID terms.",
        configuring:
          "Lab metadata only — the lab is the RADIUS server, not the access point, so nothing here starts broadcasting. It is stored on the lab and replayed as a controller checklist at the end.",
        next: "Create or select the lab that will own this SSID's users and clients.",
      };
    case "wlan_policy":
      return {
        what: `Assigns a VLAN to everyone who joins the SSID by authorizing the “${WIZARD_USER_GROUP}” user group.`,
        configuring:
          "An authorization policy bound to a user group, written to radgroupreply. Because the wizard's user is in that group, its Access-Accept carries the VLAN — this is dynamic VLAN assignment, the usual reason a wireless lab exists.",
        next: "Register the WLC/AP as a RADIUS client, or skip ahead to the test.",
      };
    case "method":
      return {
        what: "Chooses how this lab authenticates: PEAP (username/password), EAP-TLS (client certificates), or MAB (MAC address only).",
        configuring:
          "Which steps you'll see next — PEAP adds a user; EAP-TLS adds a CA plus a client certificate; MAB adds an authorization policy plus a registered MAC.",
        next: wireless
          ? "Name the SSID these clients will join."
          : "Create or select the lab that will own these objects.",
      };
    case "lab":
      return {
        what: "Creates or reuses an isolated lab environment that owns your users, clients, certificates, and events.",
        configuring: wireless
          ? "A Lab record, including the SSID you just named — nothing is sent to FreeRADIUS yet. Reusing a lab keeps everything already in it."
          : "A Lab record in the database only — nothing is sent to FreeRADIUS yet. Reusing a lab keeps everything already in it.",
        next: mab
          ? "Create the authorization policy that says which VLAN and role the device gets."
          : peap
            ? "Add a PEAP user."
            : "Create the lab's root certificate authority.",
      };
    case "policy":
      return {
        what: "Creates an authorization policy — the VLAN and role FreeRADIUS returns when this device is accepted.",
        configuring:
          "A policy record whose VLAN becomes the Tunnel-Type / Tunnel-Medium-Type / Tunnel-Private-Group-Id triplet, and whose role becomes Filter-Id. Nothing reaches FreeRADIUS until an endpoint or group uses the policy.",
        next: "Register the MAC address that this policy should apply to.",
      };
    case "endpoint":
      return {
        what: "Registers a device's MAC address so MAB can authenticate it, and attaches the authorization policy.",
        configuring:
          "An endpoint row, plus radcheck entries (Auth-Type := Accept) under every common MAC spelling and radreply entries carrying the policy's attributes. This takes effect on the next request — no FreeRADIUS restart needed.",
        next: "Register the RADIUS client for your switch/AP, or skip ahead to the test.",
      };
    case "user":
      return {
        what: "Creates a RADIUS identity that authenticates over PEAP/MSCHAPv2 (separate from your admin login).",
        configuring:
          "A user row plus its NT-Password hash, synced into FreeRADIUS's radcheck table so the server can verify the password.",
        next: "Register the RADIUS client for your switch/AP, or skip ahead to the test.",
      };
    case "ca":
      return {
        what: "Creates the lab's root Certificate Authority — the trust anchor for EAP-TLS.",
        configuring:
          "A root key/cert on disk, published into FreeRADIUS's client trust store (a brief FreeRADIUS restart applies it). Any client cert signed by this CA is then trusted.",
        next: "Issue a client certificate for an identity.",
      };
    case "cert":
      return {
        what: "Issues a client certificate signed by the lab CA — this cert is the endpoint's identity in EAP-TLS.",
        configuring:
          "A certificate + private key recorded in the CA database (so it can later be revoked). Download the bundle/.p12 to import on a real device; the in-app test uses the server-side copy.",
        next: "Register the RADIUS client, or run the test.",
      };
    case "client":
      return {
        what: wireless
          ? "Registers the WLC or AP that is allowed to send RADIUS requests for this SSID."
          : "Registers the network access device (switch/WLC/AP) that is allowed to send RADIUS requests.",
        configuring: wireless
          ? "A RADIUS client entry — the address the controller sources RADIUS from, plus the shared secret. On a controller that is usually its management interface, not the AP's own address. Saving triggers a controlled FreeRADIUS restart."
          : "A RADIUS client entry — the NAS source IP + shared secret FreeRADIUS must recognize. Saving triggers a controlled FreeRADIUS restart to apply it. This is different from the RADIUS target above (the IP the NAS points at).",
        next: "Run the authentication test. For a real device, also point its RADIUS settings at the target IP/secret shown above.",
      };
    case "test":
      return {
        what: mab
          ? "Sends a real MAB Access-Request with radclient from inside the backend container — the MAC as User-Name and Service-Type = Call-Check, exactly as a switch would."
          : "Runs a live authentication against FreeRADIUS using eapol_test from inside the backend container.",
        configuring:
          "Nothing new — it exercises everything you just set up and produces a real Access-Accept/Reject plus an authentication event.",
        next: mab
          ? "On success, check the returned VLAN and role, then view the ingested record under Events."
          : "On success, view the ingested record under Events.",
      };
    case "done":
      return {
        what: "Your lab is live and has produced at least one authentication event.",
        configuring: "Nothing — this is a summary of what you built.",
        next: wireless
          ? "Copy the SSID checklist onto your AP/WLC, then join a device and watch Events."
          : "Explore Events, run more tests from Auth Test, or point a real NAS at the lab.",
      };
  }
}

function StepTip({
  id,
  method,
  medium,
  label,
}: {
  id: StepId;
  method: AuthMethod;
  medium: Medium;
  label: string;
}) {
  const help = stepHelp(id, method, medium);
  return (
    <InfoTip label={`What the “${label}” step does`}>
      <span className="block font-semibold text-ink">What this step does</span>
      <span className="mt-0.5 block">{help.what}</span>
      <span className="mt-2 block font-semibold text-ink">What you're configuring</span>
      <span className="mt-0.5 block">{help.configuring}</span>
      <span className="mt-2 block font-semibold text-ink">Next</span>
      <span className="mt-0.5 block">{help.next}</span>
    </InfoTip>
  );
}

export function WizardPage() {
  const [stepIndex, setStepIndex] = useState(0);
  const [medium, setMedium] = useState<Medium>("both");
  const [method, setMethod] = useState<AuthMethod>("peap");
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [labName, setLabName] = useState("My first PEAP lab");
  // Which of the two lab paths "Continue with lab" will take. Explicit, so
  // editing the name can never leave the step with neither a lab nor a name.
  const [labChoice, setLabChoice] = useState<"existing" | "new">("new");
  const [ssid, setSsid] = useState("Lab-Corp");
  const [security, setSecurity] = useState<WirelessSecurity>("wpa2_enterprise");
  const [wlanPolicyName, setWlanPolicyName] = useState("SSID users → VLAN 20");
  const [wlanVlan, setWlanVlan] = useState("20");
  const [username, setUsername] = useState("labuser");
  const [password, setPassword] = useState("LabPass123!");
  const [createdUser, setCreatedUser] = useState<RadiusUser | null>(null);
  const [certIdentity, setCertIdentity] = useState("tlsuser");
  const [caInfo, setCaInfo] = useState<string | null>(null);
  const [certInfo, setCertInfo] = useState<string | null>(null);
  const [policyName, setPolicyName] = useState("Printers VLAN 40");
  const [policyVlan, setPolicyVlan] = useState("40");
  const [policyRole, setPolicyRole] = useState("printer-acl");
  const [createdPolicy, setCreatedPolicy] = useState<AuthzPolicy | null>(null);
  const [endpointMac, setEndpointMac] = useState("aa:bb:cc:dd:ee:ff");
  const [endpointDescription, setEndpointDescription] = useState("Lobby printer");
  const [createdEndpoint, setCreatedEndpoint] = useState<Endpoint | null>(null);
  const [clientName, setClientName] = useState("lab-switch");
  const [clientIp, setClientIp] = useState("10.0.0.1");
  const [clientSecret, setClientSecret] = useState("testing123");
  const [createdClient, setCreatedClient] = useState<RadiusClient | null>(null);
  const [testResult, setTestResult] = useState<AuthTestResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const steps = useMemo(() => buildSteps(method, medium), [method, medium]);

  const current = steps[Math.min(stepIndex, steps.length - 1)]?.id || "medium";

  const useExistingLab = labChoice === "existing" && labs.length > 0;
  const newLabName = labName.trim();
  const selectedLab = labs.find((lab) => lab.id === labId);
  const wireless = medium === "wireless";
  const trimmedSsid = ssid.trim();
  const ssidBytes = new TextEncoder().encode(trimmedSsid).length;

  useEffect(() => {
    apiFetch<Lab[]>("/labs")
      .then((data) => {
        setLabs(data);
        if (data[0]) {
          setLabId(data[0].id);
          setLabChoice("existing");
        }
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    // Keep step index valid when switching method mid-flow.
    setStepIndex((i) => Math.min(i, steps.length - 1));
    const defaultNames: Record<AuthMethod, string> = {
      peap: "My first PEAP lab",
      eap_tls: "My first EAP-TLS lab",
      mab: "My first MAB lab",
    };
    setLabName((current) =>
      Object.values(defaultNames).includes(current) ? defaultNames[method] : current,
    );
  }, [method, steps.length]);

  useEffect(() => {
    // A wireless lab registers a controller, not a switch — say so by default,
    // and give it its own address, since one address can hold one client.
    const wirelessMedium = medium === "wireless";
    setClientName((current) =>
      current === "lab-switch" || current === "lab-wlc"
        ? wirelessMedium
          ? "lab-wlc"
          : "lab-switch"
        : current,
    );
    setClientIp((current) =>
      current === "10.0.0.1" || current === "10.0.0.2"
        ? wirelessMedium
          ? "10.0.0.2"
          : "10.0.0.1"
        : current,
    );
  }, [medium]);

  /**
   * Move to the next step, carrying a note about what just happened. The note
   * belongs to the step you land on: setting it before advancing lost it, since
   * both updates batch and the move cleared the banner.
   */
  function next(done?: string) {
    setError(null);
    setStatus(done || null);
    setStepIndex((i) => Math.min(i + 1, steps.length - 1));
  }

  function back() {
    setError(null);
    setStatus(null);
    setStepIndex((i) => Math.max(i - 1, 0));
  }

  function wirelessProfile(vlan: number | null, userGroup: string | null): WirelessProfile {
    return { ssid: trimmedSsid, security, vlan, user_group: userGroup };
  }

  /** Record the SSID (and whatever VLAN it hands out) on the lab itself. */
  async function saveWirelessProfile(labIdToUse: string, vlan: number | null, group: string | null) {
    const lab = await apiFetch<Lab>(`/labs/${labIdToUse}/wireless-profile`, {
      method: "PUT",
      body: JSON.stringify(wirelessProfile(vlan, group)),
    });
    setLabs((prev) => prev.map((item) => (item.id === lab.id ? lab : item)));
    return lab;
  }

  function continueSsid() {
    setError(null);
    if (!trimmedSsid) {
      setError("Enter the SSID clients will join.");
      return;
    }
    if (ssidBytes > SSID_MAX_BYTES) {
      setError(
        `That SSID is ${ssidBytes} bytes — 802.11 allows at most ${SSID_MAX_BYTES}. Shorten it.`,
      );
      return;
    }
    next();
  }

  async function createOrSelectLab() {
    setError(null);
    if (useExistingLab) {
      if (!labId) {
        setError("Select a lab to continue, or choose “Create a new lab”.");
        return;
      }
      if (wireless) {
        // Reusing a lab still needs to learn which SSID this run is about.
        setBusy(true);
        try {
          await saveWirelessProfile(labId, null, null);
        } catch (err) {
          setError(err instanceof Error ? err.message : "Could not record the SSID");
          return;
        } finally {
          setBusy(false);
        }
      }
      next("Using selected lab.");
      return;
    }
    if (!newLabName) {
      setError(
        labs.length > 0
          ? "Enter a name for the new lab, or choose “Use an existing lab”."
          : "Enter a name for the new lab.",
      );
      return;
    }
    setBusy(true);
    try {
      const lab = await apiFetch<Lab>("/labs", {
        method: "POST",
        body: JSON.stringify({
          name: newLabName,
          description: `Guided ${method.toUpperCase()} lab (${medium})`,
          settings: {
            medium,
            method,
            ...(wireless ? { wireless_profile: wirelessProfile(null, null) } : {}),
          },
        }),
      });
      setLabs((prev) => [...prev, lab]);
      setLabId(lab.id);
      setLabChoice("existing");
      next(`Lab “${lab.name}” created.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lab create failed");
    } finally {
      setBusy(false);
    }
  }

  async function createUser() {
    if (!labId) return;
    setBusy(true);
    setError(null);
    try {
      const user = await apiFetch<RadiusUser>("/users", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          username,
          password,
          groups: [WIZARD_USER_GROUP],
        }),
      });
      setCreatedUser(user);
      next(`User ${user.username} created and synced to FreeRADIUS.`);
    } catch {
      try {
        const users = await apiFetch<RadiusUser[]>(`/users?lab_id=${labId}`);
        const existing = users.find((u) => u.username === username);
        if (existing) {
          // Re-assert the group too: a policy bound to it is how this user gets
          // a VLAN, and a user made by hand may not be in it.
          await apiFetch(`/users/${existing.id}`, {
            method: "PATCH",
            body: JSON.stringify({
              password,
              status: "active",
              groups: [WIZARD_USER_GROUP],
            }),
          });
          setCreatedUser(existing);
          next(`Updated existing user ${username} and synced to FreeRADIUS.`);
          return;
        }
      } catch {
        /* fall through */
      }
      setError("User create failed");
    } finally {
      setBusy(false);
    }
  }

  async function ensureRootCa() {
    if (!labId) return;
    setBusy(true);
    setError(null);
    try {
      const info = await apiFetch<{
        name: string;
        freeradius_trust: string;
        subject: string;
      }>("/ca/ensure-root", {
        method: "POST",
        body: JSON.stringify({ lab_id: labId, common_name: "802.1X Lab Root CA" }),
      });
      setCaInfo(`${info.name} · FreeRADIUS trust: ${info.freeradius_trust}`);
      next("Lab root CA ready and published to FreeRADIUS trust store.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "CA ensure failed");
    } finally {
      setBusy(false);
    }
  }

  async function issueClientCert() {
    if (!labId || !certIdentity) return;
    setBusy(true);
    setError(null);
    try {
      const issued = await apiFetch<{
        serial: string;
        freeradius_trust: string;
        subject: string;
      }>("/ca/issue-client", {
        method: "POST",
        body: JSON.stringify({ lab_id: labId, identity: certIdentity }),
      });
      setCertInfo(`${issued.subject} · serial ${issued.serial}`);
      next("Client certificate issued. Download the bundle for your endpoint if needed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Certificate issue failed");
    } finally {
      setBusy(false);
    }
  }

  async function createPolicy() {
    if (!labId) return;
    setBusy(true);
    setError(null);
    try {
      const policy = await apiFetch<AuthzPolicy>("/authz-policies", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          name: policyName,
          vlan: policyVlan ? Number(policyVlan) : null,
          role: policyRole || null,
        }),
      });
      setCreatedPolicy(policy);
      if (wireless) await saveWirelessProfile(labId, policy.vlan, null);
      next(`Policy “${policy.name}” created — returns ${policy.summary}.`);
    } catch {
      // A repeated run of the guided flow should reuse the policy it made last time.
      try {
        const policies = await apiFetch<AuthzPolicy[]>(`/authz-policies?lab_id=${labId}`);
        const existing = policies.find((p) => p.name === policyName);
        if (existing) {
          setCreatedPolicy(existing);
          if (wireless) await saveWirelessProfile(labId, existing.vlan, null);
          next(`Using existing policy “${existing.name}” — returns ${existing.summary}.`);
          return;
        }
      } catch {
        /* fall through */
      }
      setError("Authorization policy create failed");
    } finally {
      setBusy(false);
    }
  }

  async function createWlanPolicy() {
    if (!labId) return;
    setError(null);
    const name = wlanPolicyName.trim();
    const vlan = Number(wlanVlan);
    if (!name) {
      setError("Name the policy so you can find it again on the Authorization page.");
      return;
    }
    if (!Number.isInteger(vlan) || vlan < 1 || vlan > 4094) {
      setError("Enter a VLAN id between 1 and 4094 — the range 802.1Q allows.");
      return;
    }
    setBusy(true);
    try {
      const policy = await apiFetch<AuthzPolicy>("/authz-policies", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          name,
          vlan,
          group_name: WIZARD_USER_GROUP,
        }),
      });
      setCreatedPolicy(policy);
      await saveWirelessProfile(labId, vlan, WIZARD_USER_GROUP);
      next(`Policy “${policy.name}” created — returns ${policy.summary}.`);
    } catch {
      // Only one policy may claim a group, so a repeat run re-points the policy
      // that already owns it rather than failing on the second attempt.
      try {
        const policies = await apiFetch<AuthzPolicy[]>(`/authz-policies?lab_id=${labId}`);
        const existing = policies.find((p) => p.group_name === WIZARD_USER_GROUP);
        if (existing) {
          const updated = await apiFetch<AuthzPolicy>(`/authz-policies/${existing.id}`, {
            method: "PATCH",
            body: JSON.stringify({ vlan, enabled: true }),
          });
          setCreatedPolicy(updated);
          await saveWirelessProfile(labId, vlan, WIZARD_USER_GROUP);
          next(
            `Reused policy “${updated.name}” for the ${WIZARD_USER_GROUP} group — returns ` +
              `${updated.summary}.`,
          );
          return;
        }
      } catch {
        /* fall through */
      }
      setError("Could not create the VLAN policy for this SSID");
    } finally {
      setBusy(false);
    }
  }

  async function createEndpoint() {
    if (!labId) return;
    setBusy(true);
    setError(null);
    try {
      const endpoint = await apiFetch<Endpoint>("/endpoints", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          mac_address: endpointMac,
          description: endpointDescription || null,
          device_type: "printer",
          authz_policy_id: createdPolicy?.id || null,
          enabled: true,
        }),
      });
      setCreatedEndpoint(endpoint);
      next(`Endpoint ${endpoint.mac_address} registered and synced to FreeRADIUS.`);
    } catch {
      try {
        const endpoints = await apiFetch<Endpoint[]>(`/endpoints?lab_id=${labId}`);
        const digits = endpointMac.replace(/[^0-9a-f]/gi, "").toLowerCase();
        const existing = endpoints.find((e) => e.mac_address.replace(/:/g, "") === digits);
        if (existing) {
          // Re-point the existing endpoint at this run's policy so the test shows it.
          const updated = await apiFetch<Endpoint>(`/endpoints/${existing.id}`, {
            method: "PATCH",
            body: JSON.stringify({
              authz_policy_id: createdPolicy?.id || null,
              enabled: true,
            }),
          });
          setCreatedEndpoint(updated);
          next(`Reused endpoint ${updated.mac_address} and synced to FreeRADIUS.`);
          return;
        }
      } catch {
        /* fall through */
      }
      setError("Endpoint create failed");
    } finally {
      setBusy(false);
    }
  }

  async function createClient() {
    if (!labId) return;
    setBusy(true);
    setError(null);
    try {
      const client = await apiFetch<RadiusClient>("/clients", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          name: clientName,
          ip_address: clientIp,
          shared_secret: clientSecret,
          device_type: medium === "wireless" ? "wlc" : "switch",
        }),
      });
      setCreatedClient(client);
      next("RADIUS client synced — FreeRADIUS reload requested.");
    } catch (err) {
      try {
        // One address can only hold one client, and FreeRADIUS serves every lab
        // from that one entry — so continue with whichever client already
        // answers for this NAS, wherever it lives.
        const clients = await apiFetch<RadiusClient[]>("/clients");
        const wanted = clientIp.trim().toLowerCase();
        const existing =
          clients.find((c) => c.ip_address.trim().toLowerCase() === wanted) ||
          clients.find((c) => c.lab_id === labId && c.name === clientName);
        if (existing) {
          setCreatedClient(existing);
          const owner = labs.find((lab) => lab.id === existing.lab_id);
          const elsewhere =
            existing.lab_id !== labId && owner ? ` — registered in lab “${owner.name}”` : "";
          next(`Using existing RADIUS client “${existing.name}” (${existing.ip_address})${elsewhere}.`);
          return;
        }
      } catch {
        /* fall through */
      }
      setError(err instanceof Error ? err.message : "Client create failed");
    } finally {
      setBusy(false);
    }
  }

  function skipClient() {
    next("No RADIUS client registered — the in-Compose test does not need one.");
  }

  async function runTest() {
    if (!labId) return;
    setBusy(true);
    setError(null);
    try {
      const body =
        method === "eap_tls"
          ? {
              lab_id: labId,
              method: "eap_tls" as const,
              cert_identity: certIdentity,
            }
          : method === "mab"
            ? {
                lab_id: labId,
                method: "mab" as const,
                endpoint_id: createdEndpoint?.id,
                mac_address: createdEndpoint ? undefined : endpointMac,
              }
            : {
                lab_id: labId,
                method: "peap" as const,
                user_id: createdUser?.id,
                password,
              };
      const res = await apiFetch<AuthTestResponse>("/auth-tests", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setTestResult(res);
      if (res.matched_expectation && res.result === "success") {
        next(`${METHOD_LABELS[method]} Accept — check Events for the ingested record.`);
      } else {
        setError(res.failure_reason || "Authentication did not succeed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth test failed");
    } finally {
      setBusy(false);
    }
  }

  const showGenericNav = current === "medium" || current === "method";
  const showBackOnly =
    current === "ssid" ||
    current === "lab" ||
    current === "user" ||
    current === "ca" ||
    current === "cert" ||
    current === "policy" ||
    current === "endpoint" ||
    current === "wlan_policy" ||
    current === "client" ||
    current === "test";

  return (
    <div className="page-enter space-y-8">
      <PageHeader
        title="Create your first 802.1X lab"
        subtitle={
          wireless
            ? `Guided wireless path — ${METHOD_LABELS[method]} on a WPA2/3-Enterprise SSID, ` +
              "ending with the settings to enter on your AP/WLC."
            : method === "eap_tls"
              ? "Guided EAP-TLS path — lab CA, client cert, RADIUS client, live test, then Events."
              : method === "mab"
                ? "Guided MAB path — authorization policy, endpoint MAC, RADIUS client, live test, then Events."
                : "Guided PEAP path — lab, user, RADIUS client, live auth test, then Events."
        }
      />

      <ol className="space-y-2">
        {steps.map((step, index) => {
          const active = index === stepIndex;
          const done = index < stepIndex;
          return (
            <li
              key={`${method}-${step.id}`}
              className={`flex gap-4 border px-4 py-2.5 transition ${
                active
                  ? "border-signal/50 bg-signal/10"
                  : done
                    ? "border-ink/10 bg-panel/40 text-ink/55"
                    : "ui-panel !p-0 border-ink/10 px-4 py-2.5"
              }`}
            >
              <span className="font-mono text-signal">{index + 1}</span>
              <span className={`flex items-center gap-1.5 ${active ? "font-medium" : ""}`}>
                {step.label}
                <StepTip id={step.id} method={method} medium={medium} label={step.label} />
              </span>
            </li>
          );
        })}
      </ol>

      {error && <StatusBanner tone="error">{error}</StatusBanner>}
      {status && <StatusBanner tone="ok">{status}</StatusBanner>}

      <Panel className="step-enter" key={`${method}-${current}`}>
        {current === "medium" && (
          <div>
            <h2 className="flex items-center gap-2 font-semibold">
              1. Medium
              <StepTip id="medium" method={method} medium={medium} label="Select medium" />
            </h2>
            <div className="mt-3 flex flex-col gap-2">
              {(["wired", "wireless", "both"] as const).map((value) => (
                <label key={value} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="medium"
                    checked={medium === value}
                    onChange={() => setMedium(value)}
                  />
                  {value}
                </label>
              ))}
            </div>
            <p className="mt-3 text-sm text-ink/60">
              Wireless adds an SSID step and ends with the settings to enter on your AP/WLC. The
              lab is the RADIUS server for that SSID — it does not broadcast anything itself.
            </p>
          </div>
        )}

        {current === "method" && (
          <div>
            <h2 className="flex items-center gap-2 font-semibold">
              2. Authentication type
              <StepTip id="method" method={method} medium={medium} label="Select authentication type" />
            </h2>
            <div className="mt-3 flex flex-col gap-2">
              {(
                [
                  ["peap", "PEAP (username / password)"],
                  ["eap_tls", "EAP-TLS (certificates)"],
                  ["mab", "MAB (MAC address only — for devices that cannot do 802.1X)"],
                ] as const
              ).map(([value, label]) => (
                <label key={value} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="method"
                    checked={method === value}
                    onChange={() => {
                      setMethod(value);
                      setTestResult(null);
                      setStatus(null);
                      setError(null);
                    }}
                  />
                  {label}
                </label>
              ))}
            </div>
          </div>
        )}

        {current === "ssid" && (
          <div className="space-y-4">
            <h2 className="flex items-center gap-2 font-semibold">
              SSID
              <StepTip id="ssid" method={method} medium={medium} label="Define the SSID" />
            </h2>
            <p className="text-sm text-ink/70">
              The network name your clients will join. The lab does not broadcast it — your AP or
              controller does, and points at this lab for authentication. Naming it here lets the
              rest of the flow talk in SSID terms and produces a checklist at the end.
            </p>
            <Field label="SSID (network name)">
              <input
                className="ui-input"
                value={ssid}
                onChange={(e) => {
                  setSsid(e.target.value);
                  setError(null);
                }}
                placeholder="Lab-Corp"
              />
            </Field>
            <p className={`text-xs ${ssidBytes > SSID_MAX_BYTES ? "text-fail" : "text-ink/55"}`}>
              {ssidBytes} of {SSID_MAX_BYTES} bytes — 802.11 carries the SSID in a 32-octet field,
              and accented or emoji characters cost more than one byte each.
            </p>
            <div className="space-y-2">
              <span className="text-sm text-ink/80">Security</span>
              {(
                [
                  ["wpa2_enterprise", "WPA2-Enterprise — works with essentially every client"],
                  [
                    "wpa3_enterprise",
                    "WPA3-Enterprise — requires protected management frames and newer clients",
                  ],
                ] as const
              ).map(([value, label]) => (
                <label key={value} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="wlan-security"
                    checked={security === value}
                    onChange={() => setSecurity(value)}
                  />
                  {label}
                </label>
              ))}
            </div>
            <p className="text-sm text-ink/60">
              Both carry 802.1X/EAP the same way, so {METHOD_LABELS[method]} works with either —
              the difference is on the air, not in RADIUS.
            </p>
            <Button disabled={busy} onClick={continueSsid}>
              Continue with SSID
            </Button>
          </div>
        )}

        {current === "lab" && (
          <div className="space-y-4">
            <h2 className="flex items-center gap-2 font-semibold">
              Lab
              <StepTip id="lab" method={method} medium={medium} label="Create or select lab" />
            </h2>
            {labs.length > 0 && (
              <div className="flex flex-col gap-2">
                {(
                  [
                    ["existing", "Use an existing lab"],
                    ["new", "Create a new lab"],
                  ] as const
                ).map(([value, label]) => (
                  <label key={value} className="flex items-center gap-2 text-sm">
                    <input
                      type="radio"
                      name="lab-choice"
                      checked={labChoice === value}
                      onChange={() => {
                        setLabChoice(value);
                        setError(null);
                      }}
                    />
                    {label}
                  </label>
                ))}
              </div>
            )}
            {useExistingLab ? (
              <Field label="Existing lab">
                <select
                  className="ui-input"
                  value={labId}
                  onChange={(e) => setLabId(e.target.value)}
                >
                  {labs.map((lab) => (
                    <option key={lab.id} value={lab.id}>
                      {lab.name}
                    </option>
                  ))}
                </select>
              </Field>
            ) : (
              <Field label="New lab name">
                <input
                  className="ui-input"
                  value={labName}
                  onChange={(e) => {
                    setLabName(e.target.value);
                    setError(null);
                  }}
                />
              </Field>
            )}
            <p className="text-sm text-ink/60">
              {useExistingLab
                ? selectedLab
                  ? `Continue uses “${selectedLab.name}” and everything already in it.`
                  : "Select a lab to continue."
                : newLabName
                  ? `Continue creates a new lab named “${newLabName}”.`
                  : "Enter a name for the new lab to continue."}
            </p>
            <Button disabled={busy} onClick={createOrSelectLab}>
              Continue with lab
            </Button>
          </div>
        )}

        {current === "user" && (
          <div className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              Create PEAP user
              <StepTip id="user" method={method} medium={medium} label="Create PEAP user" />
            </h2>
            <Field label="Username">
              <input
                className="ui-input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field label="Password">
              <PasswordInput
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </Field>
            <Button disabled={busy} onClick={createUser}>
              Create user & sync
            </Button>
          </div>
        )}

        {current === "ca" && (
          <div className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              Ensure lab root CA
              <StepTip id="ca" method={method} medium={medium} label="Ensure lab root CA" />
            </h2>
            <p className="text-sm text-ink/70">
              Creates an openssl lab root CA and publishes it into FreeRADIUS client trust
              (`trusted/ca-bundle.pem`). FreeRADIUS restarts briefly to load the new trust.
            </p>
            {caInfo && <p className="font-mono text-xs text-ink/60">{caInfo}</p>}
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy} variant="signal" onClick={ensureRootCa}>
                {busy ? "Working…" : "Ensure root CA"}
              </Button>
              {labId && (
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    apiDownload(`/ca/root.pem?lab_id=${labId}`, `lab-${labId}-root.pem`).catch(
                      (err: Error) => setError(err.message),
                    )
                  }
                >
                  Download root PEM
                </Button>
              )}
            </div>
          </div>
        )}

        {current === "cert" && (
          <div className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              Issue client certificate
              <StepTip id="cert" method={method} medium={medium} label="Issue client certificate" />
            </h2>
            <p className="text-sm text-ink/70">
              Issues a client cert under the lab CA. Download the PEM/P12 bundle for real
              endpoints; the Auth Test step uses the server-side material directly.
            </p>
            <Field label="Certificate identity (CN)">
              <input
                className="ui-input"
                value={certIdentity}
                onChange={(e) => setCertIdentity(e.target.value)}
              />
            </Field>
            {certInfo && <p className="font-mono text-xs text-ink/60">{certInfo}</p>}
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy || !certIdentity} variant="signal" onClick={issueClientCert}>
                {busy ? "Issuing…" : "Issue client cert"}
              </Button>
              <Button
                variant="ghost"
                disabled={busy || !labId || !certIdentity}
                onClick={() =>
                  apiDownload(
                    `/ca/client-bundle?lab_id=${labId}&identity=${encodeURIComponent(certIdentity)}`,
                    `${certIdentity}-eap-tls.zip`,
                  ).catch((err: Error) => setError(err.message))
                }
              >
                Download PEM/P12 bundle
              </Button>
            </div>
          </div>
        )}

        {current === "policy" && (
          <div className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              Create authorization policy
              <StepTip id="policy" method={method} medium={medium} label="Create authorization policy" />
            </h2>
            <p className="text-sm text-ink/70">
              Authentication answers “is this device allowed?”. Authorization answers “and what
              access does it get?” — the VLAN and role FreeRADIUS returns with the Access-Accept.
            </p>
            <Field label="Policy name">
              <input
                className="ui-input"
                value={policyName}
                onChange={(e) => setPolicyName(e.target.value)}
              />
            </Field>
            <Field label="VLAN">
              <input
                className="ui-input"
                inputMode="numeric"
                value={policyVlan}
                onChange={(e) => setPolicyVlan(e.target.value)}
                placeholder="40"
              />
            </Field>
            <Field label="Role (returned as Filter-Id)">
              <input
                className="ui-input"
                value={policyRole}
                onChange={(e) => setPolicyRole(e.target.value)}
                placeholder="printer-acl"
              />
            </Field>
            {createdPolicy && (
              <p className="text-xs text-ink/60">
                Returns: <ReplyAttributes
                  attributes={Object.fromEntries(
                    createdPolicy.rendered_attributes.map((a) => [a.name, a.value]),
                  )}
                />
              </p>
            )}
            <Button disabled={busy || !policyName} variant="signal" onClick={createPolicy}>
              {busy ? "Working…" : "Create policy"}
            </Button>
          </div>
        )}

        {current === "endpoint" && (
          <div className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              Register endpoint MAC
              <StepTip id="endpoint" method={method} medium={medium} label="Register endpoint MAC" />
            </h2>
            <p className="text-sm text-ink/70">
              MAB authenticates a device by its MAC address alone — no certificate, no password.
              That makes it easy to spoof, so treat it as inventory control for devices that cannot
              run a supplicant, and give those devices a restricted VLAN.
            </p>
            <Field label="MAC address">
              <input
                className="ui-input font-mono"
                value={endpointMac}
                onChange={(e) => setEndpointMac(e.target.value)}
                placeholder="aa:bb:cc:dd:ee:ff"
              />
            </Field>
            <Field label="Description">
              <input
                className="ui-input"
                value={endpointDescription}
                onChange={(e) => setEndpointDescription(e.target.value)}
              />
            </Field>
            <p className="text-sm text-ink/60">
              Authorization policy:{" "}
              {createdPolicy ? (
                <span className="font-medium text-ink">{createdPolicy.name}</span>
              ) : (
                "none (the device will be accepted with no VLAN or role)"
              )}
            </p>
            {createdEndpoint && (
              <p className="font-mono text-xs text-ink/60">
                Registered in FreeRADIUS as: {createdEndpoint.radius_usernames.join(", ")}
              </p>
            )}
            <Button disabled={busy || !endpointMac} variant="signal" onClick={createEndpoint}>
              {busy ? "Working…" : "Register endpoint & sync"}
            </Button>
          </div>
        )}

        {current === "wlan_policy" && (
          <div className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              Put SSID users in a VLAN
              <StepTip
                id="wlan_policy"
                method={method}
                medium={medium}
                label="Put SSID users in a VLAN"
              />
            </h2>
            <p className="text-sm text-ink/70">
              One SSID can serve several VLANs: the controller puts each client wherever the
              Access-Accept says. This policy authorizes the{" "}
              <code>{WIZARD_USER_GROUP}</code> user group — the group the user you just created
              belongs to — so anyone in it lands in the same VLAN, without a rule per person.
            </p>
            <Field label="Policy name">
              <input
                className="ui-input"
                value={wlanPolicyName}
                onChange={(e) => {
                  setWlanPolicyName(e.target.value);
                  setError(null);
                }}
              />
            </Field>
            <Field label="VLAN for people on this SSID">
              <input
                className="ui-input"
                inputMode="numeric"
                value={wlanVlan}
                onChange={(e) => {
                  setWlanVlan(e.target.value);
                  setError(null);
                }}
                placeholder="20"
              />
            </Field>
            {createdPolicy && (
              <p className="flex flex-wrap items-center gap-2 text-xs text-ink/60">
                Returns:{" "}
                <ReplyAttributes
                  attributes={Object.fromEntries(
                    createdPolicy.rendered_attributes.map((a) => [a.name, a.value]),
                  )}
                />
              </p>
            )}
            <Button disabled={busy} variant="signal" onClick={createWlanPolicy}>
              {busy ? "Working…" : "Create VLAN policy"}
            </Button>
            <p className="text-sm text-ink/55">
              The VLAN must already exist on the AP/WLC and its uplink switch — RADIUS only names
              it.
            </p>
          </div>
        )}

        {current === "client" && (
          <div className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              {wireless ? "RADIUS client (your AP or WLC)" : "RADIUS client (for real NAS)"}
              <StepTip id="client" method={method} medium={medium} label="Create RADIUS client" />
            </h2>
            <p className="text-sm text-ink/60">
              {wireless
                ? "First confirm the lab RADIUS target IP (what the controller points to). Then add the address the controller sends RADIUS from — on most WLCs that is the management interface, not each AP."
                : "First confirm the lab RADIUS target IP (what the NAS points to). Then add this client as the NAS source IP FreeRADIUS will accept."}
            </p>
            {labId && <RadiusTargetPanel labId={labId} compact />}
            <Field label="Name">
              <input
                className="ui-input"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
              />
            </Field>
            <Field label={wireless ? "AP / WLC source IP or CIDR" : "IP / CIDR"}>
              <input
                className="ui-input"
                value={clientIp}
                onChange={(e) => setClientIp(e.target.value)}
              />
            </Field>
            <Field label="Shared secret">
              <input
                className="ui-input font-mono"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
              />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy} onClick={createClient}>
                Create client & sync
              </Button>
              <Button variant="ghost" disabled={busy} onClick={skipClient}>
                Skip for now
              </Button>
            </div>
            <p className="text-sm text-ink/55">
              The test on the next step runs inside Compose and does not need this client — it is
              for the real {wireless ? "AP/WLC" : "switch"} when you have one.
            </p>
          </div>
        )}

        {current === "test" && (
          <div className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              Run {METHOD_LABELS[method]} test
              <StepTip id="test" method={method} medium={medium} label="Run authentication test" />
            </h2>
            <p className="text-sm text-ink/70">
              {method === "eap_tls" ? (
                <>
                  Tests certificate identity <code>{certIdentity}</code> against FreeRADIUS via
                  eapol_test inside Compose.
                </>
              ) : method === "mab" ? (
                <>
                  Tests MAC <code>{createdEndpoint?.mac_address || endpointMac}</code> against
                  FreeRADIUS via radclient inside Compose.
                </>
              ) : (
                <>
                  Tests <code>{createdUser?.username || username}</code> against FreeRADIUS via
                  eapol_test inside Compose.
                </>
              )}
            </p>
            <Button disabled={busy} variant="signal" onClick={runTest}>
              {busy ? "Running…" : "Run authentication test"}
            </Button>
            {testResult && (
              <div className="space-y-2">
                <p className={testResult.result === "success" ? "text-signal" : "text-fail"}>
                  {testResult.result === "success" ? "Access-Accept" : "Access-Reject"}
                  {testResult.failure_reason ? ` — ${testResult.failure_reason}` : ""}
                </p>
                {testResult.result === "success" && (
                  <p className="flex flex-wrap items-center gap-2 text-sm text-ink/70">
                    The NAS received:
                    <ReplyAttributes
                      attributes={
                        Object.keys(testResult.returned_attributes).length > 0
                          ? testResult.returned_attributes
                          : testResult.event?.returned_attributes
                      }
                    />
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {current === "done" && (
          <div className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              Done
              <StepTip id="done" method={method} medium={medium} label="View events" />
            </h2>
            <p className="text-sm text-ink/70">
              Your {METHOD_LABELS[method]} lab is live
              {wireless ? ` on SSID ${trimmedSsid}` : ""}
              {createdClient ? ` (NAS client: ${createdClient.name})` : ""}.
              {method === "eap_tls" && certIdentity ? ` Client identity: ${certIdentity}.` : ""}
              {method === "mab" && createdEndpoint
                ? ` Endpoint: ${createdEndpoint.mac_address}${
                    createdEndpoint.authz_policy_name
                      ? ` · policy ${createdEndpoint.authz_policy_name}`
                      : ""
                  }.`
                : ""}
            </p>
            {wireless && labId && (
              <WirelessSummary
                labId={labId}
                ssid={trimmedSsid}
                security={security}
                methodLabel={METHOD_LABELS[method]}
                credential={
                  method === "eap_tls"
                    ? `the client certificate for ${certIdentity}`
                    : method === "mab"
                      ? `the registered MAC ${createdEndpoint?.mac_address || endpointMac}`
                      : `username ${createdUser?.username || username} and its password`
                }
                vlan={createdPolicy?.vlan ?? null}
                clientName={createdClient?.name || null}
                clientIp={createdClient?.ip_address || null}
              />
            )}
            {!wireless && (
            <div className="border border-ink/10 bg-mist/40 p-4 text-sm">
              <p className="font-medium">Take it to real hardware</p>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-ink/75">
                <li>
                  Confirm the <strong>RADIUS target</strong> IP + shared secret on the Dashboard —
                  that's what your switch/AP points at.
                </li>
                <li>
                  Register the switch/AP under <Link className="underline" to="/clients">RADIUS
                  Clients</Link> (its source IP + the shared secret).
                </li>
                {method === "eap_tls" ? (
                  <li>
                    Install the client certificate and lab root CA on the device (download them from{" "}
                    <Link className="underline" to="/certificates">Certificates</Link>).
                  </li>
                ) : method === "mab" ? (
                  <li>
                    Enable MAB on the switch port (as a fallback after 802.1X times out) and make
                    sure the VLAN this policy returns exists on the switch.
                  </li>
                ) : (
                  <li>Enter a lab username/password on the device when it prompts for PEAP.</li>
                )}
                <li>Configure the switch port or WPA2/3-Enterprise SSID to use the lab RADIUS server.</li>
              </ol>
              <a
                className="mt-2 inline-block underline"
                href="https://github.com/danryan06/8021x-lab/blob/main/docs/deploying-to-devices.md"
                target="_blank"
                rel="noreferrer"
              >
                Full guide: deploying to real devices →
              </a>
            </div>
            )}
            {wireless && method === "eap_tls" && (
              <p className="text-sm text-ink/60">
                To hand certificate users a VLAN as well, create an authorization policy bound to a{" "}
                <Link className="underline" to="/policies">
                  user group
                </Link>{" "}
                and make sure the certificate's identity is a lab user in that group — EAP-TLS
                reads group membership the same way PEAP does.
              </p>
            )}
            <div className="flex flex-wrap gap-3">
              <Link className="ui-btn-signal" to="/events">
                Open Events
              </Link>
              <Link className="ui-btn-ghost" to="/test">
                More tests
              </Link>
              <Link className="ui-btn-ghost" to="/">
                Dashboard
              </Link>
            </div>
          </div>
        )}
      </Panel>

      {showGenericNav && (
        <div className="flex gap-3">
          <Button variant="ghost" disabled={stepIndex === 0} onClick={back}>
            Back
          </Button>
          <Button onClick={() => next()}>Continue</Button>
        </div>
      )}

      {showBackOnly && (
        <Button variant="ghost" onClick={back}>
          Back
        </Button>
      )}
    </div>
  );
}
