import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  apiDownload,
  apiFetch,
  type AuthTestResponse,
  type Lab,
  type RadiusClient,
  type RadiusUser,
} from "../api/client";
import { Button, Field, PageHeader, Panel, StatusBanner } from "../components/ui";

type AuthMethod = "peap" | "eap_tls" | "mab";
type Medium = "wired" | "wireless" | "both";

type StepId =
  | "medium"
  | "method"
  | "lab"
  | "user"
  | "ca"
  | "cert"
  | "client"
  | "test"
  | "done";

type Step = { id: StepId; label: string };

const PEAP_STEPS: Step[] = [
  { id: "medium", label: "Select medium" },
  { id: "method", label: "Select authentication type" },
  { id: "lab", label: "Create or select lab" },
  { id: "user", label: "Create PEAP user" },
  { id: "client", label: "Create RADIUS client" },
  { id: "test", label: "Run authentication test" },
  { id: "done", label: "View events" },
];

const TLS_STEPS: Step[] = [
  { id: "medium", label: "Select medium" },
  { id: "method", label: "Select authentication type" },
  { id: "lab", label: "Create or select lab" },
  { id: "ca", label: "Ensure lab root CA" },
  { id: "cert", label: "Issue client certificate" },
  { id: "client", label: "Create RADIUS client" },
  { id: "test", label: "Run EAP-TLS test" },
  { id: "done", label: "View events" },
];

export function WizardPage() {
  const [stepIndex, setStepIndex] = useState(0);
  const [medium, setMedium] = useState<Medium>("both");
  const [method, setMethod] = useState<AuthMethod>("peap");
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [labName, setLabName] = useState("My first PEAP lab");
  const [username, setUsername] = useState("labuser");
  const [password, setPassword] = useState("LabPass123!");
  const [createdUser, setCreatedUser] = useState<RadiusUser | null>(null);
  const [certIdentity, setCertIdentity] = useState("tlsuser");
  const [caInfo, setCaInfo] = useState<string | null>(null);
  const [certInfo, setCertInfo] = useState<string | null>(null);
  const [clientName, setClientName] = useState("lab-switch");
  const [clientIp, setClientIp] = useState("10.0.0.1");
  const [clientSecret, setClientSecret] = useState("testing123");
  const [createdClient, setCreatedClient] = useState<RadiusClient | null>(null);
  const [testResult, setTestResult] = useState<AuthTestResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const steps = useMemo(() => {
    if (method === "eap_tls") return TLS_STEPS;
    return PEAP_STEPS;
  }, [method]);

  const current = steps[Math.min(stepIndex, steps.length - 1)]?.id || "medium";

  useEffect(() => {
    apiFetch<Lab[]>("/labs")
      .then((data) => {
        setLabs(data);
        if (data[0]) setLabId(data[0].id);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    // Keep step index valid when switching method mid-flow.
    setStepIndex((i) => Math.min(i, steps.length - 1));
    if (method === "peap") setLabName((n) => (n.includes("EAP-TLS") ? "My first PEAP lab" : n));
    if (method === "eap_tls") {
      setLabName((n) => (n.includes("PEAP") ? "My first EAP-TLS lab" : n));
    }
  }, [method, steps.length]);

  function next() {
    setError(null);
    setStatus(null);
    setStepIndex((i) => Math.min(i + 1, steps.length - 1));
  }

  function back() {
    setError(null);
    setStatus(null);
    setStepIndex((i) => Math.max(i - 1, 0));
  }

  async function createOrSelectLab() {
    setBusy(true);
    setError(null);
    try {
      if (labId) {
        setStatus("Using selected lab.");
        next();
        return;
      }
      const lab = await apiFetch<Lab>("/labs", {
        method: "POST",
        body: JSON.stringify({
          name: labName,
          description: `Guided ${method.toUpperCase()} lab (${medium})`,
          settings: { medium, method },
        }),
      });
      setLabs((prev) => [...prev, lab]);
      setLabId(lab.id);
      setStatus(`Lab “${lab.name}” created.`);
      next();
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
          groups: ["lab"],
        }),
      });
      setCreatedUser(user);
      setStatus(`User ${user.username} created and synced to FreeRADIUS.`);
      next();
    } catch {
      try {
        const users = await apiFetch<RadiusUser[]>(`/users?lab_id=${labId}`);
        const existing = users.find((u) => u.username === username);
        if (existing) {
          await apiFetch(`/users/${existing.id}`, {
            method: "PATCH",
            body: JSON.stringify({ password, status: "active" }),
          });
          setCreatedUser(existing);
          setStatus(`Updated existing user ${username} and synced to FreeRADIUS.`);
          next();
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
      setStatus("Lab root CA ready and published to FreeRADIUS trust store.");
      next();
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
      setStatus("Client certificate issued. Download the bundle for your endpoint if needed.");
      next();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Certificate issue failed");
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
      setStatus("RADIUS client synced — FreeRADIUS reload requested.");
      next();
    } catch {
      try {
        const clients = await apiFetch<RadiusClient[]>(`/clients?lab_id=${labId}`);
        const existing = clients.find((c) => c.name === clientName);
        if (existing) {
          setCreatedClient(existing);
          setStatus("Using existing RADIUS client.");
          next();
          return;
        }
      } catch {
        /* fall through */
      }
      setError("Client create failed");
    } finally {
      setBusy(false);
    }
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
        setStatus(
          `${method === "eap_tls" ? "EAP-TLS" : "PEAP"} Accept — check Events for the ingested record.`,
        );
        next();
      } else {
        setError(res.failure_reason || "Authentication did not succeed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth test failed");
    } finally {
      setBusy(false);
    }
  }

  // MAB remains deferred after method selection.
  if (method === "mab" && stepIndex >= 2) {
    return (
      <div className="page-enter space-y-6">
        <PageHeader
          title="Create your first 802.1X lab"
          subtitle="MAB (MAC Authentication Bypass) arrives in Phase 3."
        />
        <Panel>
          <h2 className="font-semibold">MAB — Phase 3</h2>
          <p className="mt-2 text-sm text-ink/70">
            Endpoint (MAC) management and authorization reply attributes are planned next.
            PEAP and EAP-TLS first-lab paths are available now.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button
              variant="signal"
              onClick={() => {
                setMethod("peap");
                setStepIndex(0);
              }}
            >
              Switch to PEAP path
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setMethod("eap_tls");
                setStepIndex(0);
              }}
            >
              Switch to EAP-TLS path
            </Button>
          </div>
        </Panel>
      </div>
    );
  }

  const showGenericNav = current === "medium" || current === "method";
  const showBackOnly =
    current === "lab" ||
    current === "user" ||
    current === "ca" ||
    current === "cert" ||
    current === "client" ||
    current === "test";

  return (
    <div className="page-enter space-y-8">
      <PageHeader
        title="Create your first 802.1X lab"
        subtitle={
          method === "eap_tls"
            ? "Guided EAP-TLS path — lab CA, client cert, RADIUS client, live test, then Events."
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
              <span className={active ? "font-medium" : undefined}>{step.label}</span>
            </li>
          );
        })}
      </ol>

      {error && <StatusBanner tone="error">{error}</StatusBanner>}
      {status && <StatusBanner tone="ok">{status}</StatusBanner>}

      <Panel className="step-enter" key={`${method}-${current}`}>
        {current === "medium" && (
          <div>
            <h2 className="font-semibold">1. Medium</h2>
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
          </div>
        )}

        {current === "method" && (
          <div>
            <h2 className="font-semibold">2. Authentication type</h2>
            <div className="mt-3 flex flex-col gap-2">
              {(
                [
                  ["peap", "PEAP (username / password)"],
                  ["eap_tls", "EAP-TLS (certificates)"],
                  ["mab", "MAB — Phase 3"],
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

        {current === "lab" && (
          <div className="space-y-4">
            <h2 className="font-semibold">Lab</h2>
            {labs.length > 0 && (
              <Field label="Use existing lab">
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
            )}
            <Field label="Or create new lab name">
              <input
                className="ui-input"
                value={labName}
                onChange={(e) => {
                  setLabName(e.target.value);
                  setLabId("");
                }}
              />
            </Field>
            <Button disabled={busy} onClick={createOrSelectLab}>
              Continue with lab
            </Button>
          </div>
        )}

        {current === "user" && (
          <div className="space-y-3">
            <h2 className="font-semibold">Create PEAP user</h2>
            <Field label="Username">
              <input
                className="ui-input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field label="Password">
              <input
                type="password"
                className="ui-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <Button disabled={busy} onClick={createUser}>
              Create user & sync
            </Button>
          </div>
        )}

        {current === "ca" && (
          <div className="space-y-3">
            <h2 className="font-semibold">Ensure lab root CA</h2>
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
            <h2 className="font-semibold">Issue client certificate</h2>
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

        {current === "client" && (
          <div className="space-y-3">
            <h2 className="font-semibold">RADIUS client (for real NAS)</h2>
            <p className="text-sm text-ink/60">
              UI auth tests use the Compose lab-docker-host secret. This client is for your
              switch/AP documentation and file sync.
            </p>
            <Field label="Name">
              <input
                className="ui-input"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
              />
            </Field>
            <Field label="IP / CIDR">
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
            <Button disabled={busy} onClick={createClient}>
              Create client & sync
            </Button>
          </div>
        )}

        {current === "test" && (
          <div className="space-y-3">
            <h2 className="font-semibold">
              Run {method === "eap_tls" ? "EAP-TLS" : "PEAP"} test
            </h2>
            <p className="text-sm text-ink/70">
              {method === "eap_tls" ? (
                <>
                  Tests certificate identity <code>{certIdentity}</code> against FreeRADIUS via
                  eapol_test inside Compose.
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
              <p className={testResult.result === "success" ? "text-signal" : "text-fail"}>
                {testResult.result === "success" ? "Access-Accept" : "Access-Reject"}
                {testResult.failure_reason ? ` — ${testResult.failure_reason}` : ""}
              </p>
            )}
          </div>
        )}

        {current === "done" && (
          <div className="space-y-3">
            <h2 className="font-semibold">Done</h2>
            <p className="text-sm text-ink/70">
              Your {method === "eap_tls" ? "EAP-TLS" : "PEAP"} lab is live
              {createdClient ? ` (NAS client: ${createdClient.name})` : ""}.
              {method === "eap_tls" && certIdentity
                ? ` Client identity: ${certIdentity}.`
                : ""}
            </p>
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
          <Button onClick={next}>Continue</Button>
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
