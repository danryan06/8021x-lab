import { FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  apiDownload,
  apiFetch,
  type AuthTestContext,
  type AuthTestResponse,
  type Lab,
  type RadiusClient,
  type RadiusUser,
} from "../api/client";
import { RadiusTargetPanel } from "../components/RadiusTargetPanel";
import { InfoTip } from "../components/ui";
import { useMode } from "../modes/ModeContext";

export function AuthTestPage() {
  const { isAdvanced } = useMode();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [users, setUsers] = useState<RadiusUser[]>([]);
  const [clients, setClients] = useState<RadiusClient[]>([]);
  const [context, setContext] = useState<AuthTestContext | null>(null);
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [method, setMethod] = useState<"peap" | "eap_tls">("peap");
  const [certIdentity, setCertIdentity] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AuthTestResponse | null>(null);
  const [caNote, setCaNote] = useState<string | null>(null);
  const selectedLabRef = useRef("");

  async function loadLab(selected: string) {
    selectedLabRef.current = selected;
    const [u, c] = await Promise.all([
      apiFetch<RadiusUser[]>(`/users?lab_id=${selected}`),
      apiFetch<RadiusClient[]>(`/clients?lab_id=${selected}`),
    ]);
    // Discard responses for a lab that is no longer selected, otherwise a fast
    // lab switch can pair users from lab A with labId B in the test payload.
    if (selectedLabRef.current !== selected) return;
    setUsers(u);
    setClients(c);
    setUserId(u[0]?.id || "");
    if (!certIdentity && u[0]?.username) setCertIdentity(u[0].username);
  }

  useEffect(() => {
    Promise.all([
      apiFetch<Lab[]>("/labs"),
      apiFetch<AuthTestContext>("/auth-tests/context"),
    ])
      .then(([labsData, ctx]) => {
        setLabs(labsData);
        setContext(ctx);
        const first = labsData[0]?.id || "";
        setLabId(first);
        if (first) return loadLab(first);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  async function runTest(opts: { wrongPassword?: boolean } = {}) {
    if (!labId) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body: Record<string, unknown> = {
        lab_id: labId,
        method,
        wrong_password: !!opts.wrongPassword,
        expect_reject: !!opts.wrongPassword,
      };
      if (method === "peap") {
        body.user_id = userId;
        body.password = password || "placeholder";
      } else {
        body.cert_identity = certIdentity;
        if (userId) body.user_id = userId;
      }
      const res = await apiFetch<AuthTestResponse>("/auth-tests", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    await runTest();
  }

  async function ensureCaAndCert() {
    if (!labId || !certIdentity) return;
    setBusy(true);
    setError(null);
    setCaNote(null);
    try {
      await apiFetch("/ca/ensure-root", {
        method: "POST",
        body: JSON.stringify({ lab_id: labId }),
      });
      const issued = await apiFetch<{ freeradius_trust: string }>("/ca/issue-client", {
        method: "POST",
        body: JSON.stringify({ lab_id: labId, identity: certIdentity }),
      });
      setCaNote(`Client cert ready for ${certIdentity}. FreeRADIUS trust: ${issued.freeradius_trust}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "CA operation failed");
    } finally {
      setBusy(false);
    }
  }

  const selectedUser = users.find((u) => u.id === userId);

  return (
    <div className="page-enter space-y-8">
      <section>
        <h1 className="font-display text-3xl font-bold">Authentication Test</h1>
        <p className="mt-1 text-ink/70">
          Run PEAP/MSCHAPv2 (or EAP-TLS) against FreeRADIUS from the UI — no CLI required.
          Successful and failed attempts appear on the{" "}
          <Link className="underline" to="/events">
            Events
          </Link>{" "}
          page.
        </p>
      </section>

      {error && <p className="text-fail">{error}</p>}
      {caNote && <p className="text-signal">{caNote}</p>}

      {labId && <RadiusTargetPanel labId={labId} compact />}

      <section className="grid gap-4 ui-panel p-5 md:grid-cols-2">
        <div>
          <h2 className="font-semibold">In-Compose test context</h2>
          {context ? (
            <dl className="mt-3 space-y-2 font-mono text-sm">
              <div>
                <dt className="text-ink/50">Host</dt>
                <dd>
                  {context.radius_host}:{context.radius_port}
                </dd>
              </div>
              <div>
                <dt className="text-ink/50">Shared secret</dt>
                <dd>{context.shared_secret_hint}</dd>
              </div>
            </dl>
          ) : (
            <p className="mt-2 text-sm text-ink/50">Loading…</p>
          )}
          {isAdvanced && context && (
            <p className="mt-3 text-xs text-ink/60">{context.note}</p>
          )}
        </div>
        <div>
          <h2 className="font-semibold">Lab RADIUS clients</h2>
          {clients.length === 0 ? (
            <p className="mt-2 text-sm text-ink/60">
              No NAS clients yet. UI tests use the Compose lab-docker-host secret; add a client for
              real switches/APs on the{" "}
              <Link className="underline" to="/clients">
                Clients
              </Link>{" "}
              page.
            </p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm">
              {clients.map((c) => (
                <li key={c.id}>
                  <span className="font-medium">{c.name}</span>{" "}
                  <span className="font-mono text-ink/60">{c.ip_address}</span>
                  {isAdvanced && (
                    <span className="ml-2 font-mono text-xs text-ink/50">{c.shared_secret}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <form onSubmit={onSubmit} className="space-y-4 ui-panel p-5">
        <div className="flex flex-wrap gap-4">
          <label className="text-sm">
            Lab
            <select
              className="mt-1 block ui-btn-ghost px-3 py-2"
              value={labId}
              onChange={(e) => {
                setLabId(e.target.value);
                loadLab(e.target.value).catch((err: Error) => setError(err.message));
              }}
            >
              {labs.map((lab) => (
                <option key={lab.id} value={lab.id}>
                  {lab.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            Method
            <select
              className="mt-1 block ui-btn-ghost px-3 py-2"
              value={method}
              onChange={(e) => setMethod(e.target.value as "peap" | "eap_tls")}
            >
              <option value="peap">PEAP / MSCHAPv2</option>
              <option value="eap_tls">EAP-TLS</option>
            </select>
          </label>
        </div>

        {method === "peap" ? (
          <div className="grid gap-4 md:grid-cols-2">
            <label className="text-sm">
              Lab user
              <select
                className="mt-1 block w-full ui-btn-ghost px-3 py-2"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                required
              >
                {users.length === 0 && <option value="">No users — create one first</option>}
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.username} ({u.status})
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              Password
              <input
                type="password"
                className="ui-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password used when creating the user"
                required
              />
            </label>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              EAP-TLS certificate actions
              <InfoTip label="What the EAP-TLS actions do">
                <span className="block font-semibold text-ink">Certificate identity</span>
                <span className="mt-0.5 block">
                  The CN the certificate is issued to — it becomes the client's EAP-TLS username.
                </span>
                <span className="mt-2 block font-semibold text-ink">Ensure CA + issue client cert</span>
                <span className="mt-0.5 block">
                  Creates the lab root CA if needed, issues a client certificate for this identity,
                  and publishes the CA into FreeRADIUS trust. Run this before your first test.
                </span>
                <span className="mt-2 block font-semibold text-ink">Download PEM/P12 bundle</span>
                <span className="mt-0.5 block">
                  Downloads the client certificate + private key (PEM and .p12) to install on a real
                  device. The in-app test uses the server-side copy, so this is only for real endpoints.
                </span>
                <span className="mt-2 block font-semibold text-ink">Download root CA</span>
                <span className="mt-0.5 block">
                  Downloads the lab CA certificate to trust on a device or server (e.g. as the CA a
                  supplicant validates the RADIUS server against).
                </span>
                <span className="mt-2 block font-semibold text-ink">Run authentication test</span>
                <span className="mt-0.5 block">
                  Runs eapol_test against FreeRADIUS with this certificate and shows Accept/Reject
                  plus the ingested event.
                </span>
              </InfoTip>
            </div>
            <label className="block text-sm">
              Certificate identity
              <input
                className="ui-input"
                value={certIdentity}
                onChange={(e) => setCertIdentity(e.target.value)}
                placeholder={selectedUser?.username || "user@lab.local"}
                required
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={ensureCaAndCert}
                className="ui-btn-ghost px-3 py-2 text-sm"
              >
                Ensure CA + issue client cert
              </button>
              <button
                type="button"
                disabled={busy || !labId || !certIdentity}
                onClick={() =>
                  apiDownload(
                    `/ca/client-bundle?lab_id=${labId}&identity=${encodeURIComponent(certIdentity)}`,
                    `${certIdentity}-eap-tls.zip`,
                  ).catch((err: Error) => setError(err.message))
                }
                className="ui-btn-ghost px-3 py-2 text-sm"
              >
                Download PEM/P12 bundle
              </button>
              <button
                type="button"
                disabled={busy || !labId}
                onClick={() =>
                  apiDownload(`/ca/root.pem?lab_id=${labId}`, `lab-${labId}-root.pem`).catch(
                    (err: Error) => setError(err.message),
                  )
                }
                className="ui-btn-ghost px-3 py-2 text-sm"
              >
                Download root CA
              </button>
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          <button
            type="submit"
            disabled={busy || (method === "peap" && !userId)}
            className="ui-btn-signal disabled:opacity-50"
          >
            {busy ? "Running…" : "Run authentication test"}
          </button>
          {method === "peap" && (
            <button
              type="button"
              disabled={busy || !userId}
              onClick={() => runTest({ wrongPassword: true })}
              className="ui-btn-ghost text-fail disabled:opacity-50"
            >
              Wrong-password test
            </button>
          )}
        </div>
      </form>

      {result && (
        <section
          className={`border p-5 ${
            result.matched_expectation
              ? "border-signal/40 bg-signal/10"
              : "border-fail/40 bg-fail/5"
          }`}
        >
          <h2 className="font-display text-xl font-semibold">
            {result.result === "success" ? "Access-Accept" : "Access-Reject"}
            {result.expected_reject && (
              <span className="ml-2 text-sm font-normal text-ink/60">(negative test)</span>
            )}
          </h2>
          <p className="mt-1 text-sm">
            {result.matched_expectation
              ? "Result matched expectation."
              : "Result did not match expectation."}
          </p>
          <dl className="mt-4 grid gap-2 text-sm md:grid-cols-2">
            <div>
              <dt className="text-ink/50">Identity</dt>
              <dd className="font-mono">{result.identity}</dd>
            </div>
            <div>
              <dt className="text-ink/50">Method</dt>
              <dd>{result.method}</dd>
            </div>
            <div>
              <dt className="text-ink/50">Failure reason</dt>
              <dd>{result.failure_reason || "—"}</dd>
            </div>
            <div>
              <dt className="text-ink/50">Event ingested</dt>
              <dd>
                {result.event ? (
                  <Link className="underline" to="/events">
                    {result.event.result} @ {new Date(result.event.timestamp).toLocaleString()}
                  </Link>
                ) : (
                  "Not yet (check Events; linelog may lag a second)"
                )}
              </dd>
            </div>
          </dl>
          {isAdvanced && (
            <pre className="mt-4 max-h-64 overflow-auto border border-ink/10 bg-mist/60 p-3 font-mono text-xs">
              {result.eapol_output || "(no eapol output)"}
            </pre>
          )}
        </section>
      )}
    </div>
  );
}
