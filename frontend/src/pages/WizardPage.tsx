import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  apiFetch,
  type AuthTestResponse,
  type Lab,
  type RadiusClient,
  type RadiusUser,
} from "../api/client";

type StepId =
  | "medium"
  | "method"
  | "lab"
  | "user"
  | "client"
  | "test"
  | "done"
  | "certs_stub";

const PEAP_STEPS: { id: StepId; label: string }[] = [
  { id: "medium", label: "Select medium" },
  { id: "method", label: "Select authentication type" },
  { id: "lab", label: "Create or select lab" },
  { id: "user", label: "Create PEAP user" },
  { id: "client", label: "Create RADIUS client" },
  { id: "test", label: "Run authentication test" },
  { id: "done", label: "View events" },
];

export function WizardPage() {
  const [stepIndex, setStepIndex] = useState(0);
  const [medium, setMedium] = useState<"wired" | "wireless" | "both">("both");
  const [method, setMethod] = useState<"peap" | "eap_tls" | "mab">("peap");
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [labName, setLabName] = useState("My first PEAP lab");
  const [username, setUsername] = useState("labuser");
  const [password, setPassword] = useState("LabPass123!");
  const [createdUser, setCreatedUser] = useState<RadiusUser | null>(null);
  const [clientName, setClientName] = useState("lab-switch");
  const [clientIp, setClientIp] = useState("10.0.0.1");
  const [clientSecret, setClientSecret] = useState("testing123");
  const [createdClient, setCreatedClient] = useState<RadiusClient | null>(null);
  const [testResult, setTestResult] = useState<AuthTestResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const steps = method === "peap" ? PEAP_STEPS : PEAP_STEPS;
  const current = steps[stepIndex]?.id || "medium";

  useEffect(() => {
    apiFetch<Lab[]>("/labs")
      .then((data) => {
        setLabs(data);
        if (data[0]) setLabId(data[0].id);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  function next() {
    setError(null);
    setStatus(null);
    if (method !== "peap" && stepIndex === 1) {
      // Jump to cert stub for non-PEAP.
      setStepIndex(steps.findIndex((s) => s.id === "lab"));
      return;
    }
    setStepIndex((i) => Math.min(i + 1, steps.length - 1));
  }

  function back() {
    setError(null);
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
    } catch (err) {
      // If username exists, try to continue with lookup.
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
      setError(err instanceof Error ? err.message : "User create failed");
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
    } catch (err) {
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
      setError(err instanceof Error ? err.message : "Client create failed");
    } finally {
      setBusy(false);
    }
  }

  async function runTest() {
    if (!labId || !createdUser) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch<AuthTestResponse>("/auth-tests", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          method: "peap",
          user_id: createdUser.id,
          password,
        }),
      });
      setTestResult(res);
      if (res.matched_expectation && res.result === "success") {
        setStatus("PEAP Accept — check Events for the ingested record.");
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

  // Non-PEAP methods show a clear Phase stub after method selection.
  if (method !== "peap" && stepIndex >= 2) {
    return (
      <div className="space-y-6">
        <h1 className="font-display text-3xl font-bold">Create your first 802.1X lab</h1>
        {method === "eap_tls" ? (
          <section className="border border-black/10 bg-white/70 p-5">
            <h2 className="font-semibold">EAP-TLS guided wizard</h2>
            <p className="mt-2 text-sm text-ink/70">
              Basic EAP-TLS is available from the Authentication Test page (ensure CA, issue
              client cert, download bundle, run test). A fully guided multi-step EAP-TLS wizard
              remains a Phase 2 polish item.
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Link className="bg-signal px-4 py-2 font-medium text-ink" to="/test">
                Open Authentication Test (EAP-TLS)
              </Link>
              <button type="button" className="border border-black/15 px-4 py-2" onClick={() => {
                setMethod("peap");
                setStepIndex(0);
              }}>
                Switch to PEAP path
              </button>
            </div>
          </section>
        ) : (
          <section className="border border-black/10 bg-white/70 p-5">
            <h2 className="font-semibold">MAB — Phase 3</h2>
            <p className="mt-2 text-sm text-ink/70">
              MAC Authentication Bypass (endpoints + reply attributes) is planned for Phase 3.
            </p>
            <button
              type="button"
              className="mt-4 border border-black/15 px-4 py-2"
              onClick={() => {
                setMethod("peap");
                setStepIndex(0);
              }}
            >
              Switch to PEAP path
            </button>
          </section>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="font-display text-3xl font-bold">Create your first 802.1X lab</h1>
        <p className="mt-1 text-ink/70">
          Guided PEAP path using real APIs — lab, user, RADIUS client, live auth test, then
          Events.
        </p>
      </section>

      <ol className="space-y-2">
        {steps.map((step, index) => (
          <li
            key={step.id}
            className={`flex gap-4 border px-4 py-2 ${
              index === stepIndex
                ? "border-signal bg-signal/10"
                : index < stepIndex
                  ? "border-black/10 bg-white/50 text-ink/60"
                  : "border-black/10 bg-white/70"
            }`}
          >
            <span className="font-mono text-signal">{index + 1}</span>
            <span>{step.label}</span>
          </li>
        ))}
      </ol>

      {error && <p className="text-fail">{error}</p>}
      {status && <p className="text-signal">{status}</p>}

      <section className="border border-black/10 bg-white/70 p-5">
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
                  ["peap", "PEAP (username / password) — recommended first lab"],
                  ["eap_tls", "EAP-TLS (certificates) — use Test page / Phase 2 polish"],
                  ["mab", "MAB — Phase 3"],
                ] as const
              ).map(([value, label]) => (
                <label key={value} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="method"
                    checked={method === value}
                    onChange={() => setMethod(value)}
                  />
                  {label}
                </label>
              ))}
            </div>
          </div>
        )}

        {current === "lab" && (
          <div className="space-y-4">
            <h2 className="font-semibold">3. Lab</h2>
            {labs.length > 0 && (
              <label className="block text-sm">
                Use existing lab
                <select
                  className="mt-1 block border border-black/15 bg-white px-3 py-2"
                  value={labId}
                  onChange={(e) => setLabId(e.target.value)}
                >
                  {labs.map((lab) => (
                    <option key={lab.id} value={lab.id}>
                      {lab.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="block text-sm">
              Or create new lab name
              <input
                className="mt-1 w-full border border-black/15 px-3 py-2"
                value={labName}
                onChange={(e) => {
                  setLabName(e.target.value);
                  setLabId("");
                }}
              />
            </label>
            <button
              type="button"
              disabled={busy}
              onClick={createOrSelectLab}
              className="bg-ink px-4 py-2 text-white disabled:opacity-50"
            >
              Continue with lab
            </button>
          </div>
        )}

        {current === "user" && (
          <div className="space-y-3">
            <h2 className="font-semibold">4. Create PEAP user</h2>
            <label className="block text-sm">
              Username
              <input
                className="mt-1 w-full border border-black/15 px-3 py-2"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              Password
              <input
                type="password"
                className="mt-1 w-full border border-black/15 px-3 py-2"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <button
              type="button"
              disabled={busy}
              onClick={createUser}
              className="bg-ink px-4 py-2 text-white disabled:opacity-50"
            >
              Create user & sync
            </button>
          </div>
        )}

        {current === "client" && (
          <div className="space-y-3">
            <h2 className="font-semibold">5. RADIUS client (for real NAS)</h2>
            <p className="text-sm text-ink/60">
              UI auth tests use the Compose lab-docker-host secret. This client is for your
              switch/AP documentation and file sync.
            </p>
            <label className="block text-sm">
              Name
              <input
                className="mt-1 w-full border border-black/15 px-3 py-2"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              IP / CIDR
              <input
                className="mt-1 w-full border border-black/15 px-3 py-2"
                value={clientIp}
                onChange={(e) => setClientIp(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              Shared secret
              <input
                className="mt-1 w-full border border-black/15 px-3 py-2 font-mono"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
              />
            </label>
            <button
              type="button"
              disabled={busy}
              onClick={createClient}
              className="bg-ink px-4 py-2 text-white disabled:opacity-50"
            >
              Create client & sync
            </button>
          </div>
        )}

        {current === "test" && (
          <div className="space-y-3">
            <h2 className="font-semibold">6. Run PEAP test</h2>
            <p className="text-sm text-ink/70">
              Tests <code>{createdUser?.username || username}</code> against FreeRADIUS via
              eapol_test inside Compose.
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={runTest}
              className="bg-signal px-4 py-2 font-medium text-ink disabled:opacity-50"
            >
              {busy ? "Running…" : "Run authentication test"}
            </button>
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
            <h2 className="font-semibold">7. Done</h2>
            <p className="text-sm text-ink/70">
              Your PEAP lab is live
              {createdClient ? ` (NAS client: ${createdClient.name})` : ""}.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link className="bg-signal px-4 py-2 font-medium text-ink" to="/events">
                Open Events
              </Link>
              <Link className="border border-black/15 px-4 py-2" to="/test">
                More tests
              </Link>
              <Link className="border border-black/15 px-4 py-2" to="/">
                Dashboard
              </Link>
            </div>
          </div>
        )}
      </section>

      {current !== "lab" &&
        current !== "user" &&
        current !== "client" &&
        current !== "test" &&
        current !== "done" && (
          <div className="flex gap-3">
            <button
              type="button"
              disabled={stepIndex === 0}
              onClick={back}
              className="border border-black/15 px-4 py-2 disabled:opacity-40"
            >
              Back
            </button>
            <button type="button" onClick={next} className="bg-ink px-4 py-2 text-white">
              Continue
            </button>
          </div>
        )}

      {(current === "user" || current === "client" || current === "test") && (
        <button type="button" onClick={back} className="border border-black/15 px-4 py-2">
          Back
        </button>
      )}
    </div>
  );
}
