import { FormEvent, useEffect, useRef, useState } from "react";
import {
  apiDownload,
  apiFetch,
  type Certificate,
  type CertificateInventory,
  type Lab,
} from "../api/client";
import { Button, Field, PageHeader, Panel, StatusBanner } from "../components/ui";
import { useMode } from "../modes/ModeContext";

function statusClass(status: string): string {
  if (status === "active") return "text-signal";
  if (status === "revoked") return "text-fail";
  if (status === "expired") return "text-warn";
  return "text-ink/60";
}

export function CertificatesPage() {
  const { isAdvanced } = useMode();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [inventory, setInventory] = useState<CertificateInventory | null>(null);
  const [identity, setIdentity] = useState("");
  const [days, setDays] = useState(365);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const selectedLabRef = useRef("");

  async function loadInventory(selected: string) {
    selectedLabRef.current = selected;
    const data = await apiFetch<CertificateInventory>(`/ca/certificates?lab_id=${selected}`);
    if (selectedLabRef.current !== selected) return;
    setInventory(data);
  }

  useEffect(() => {
    apiFetch<Lab[]>("/labs")
      .then((labsData) => {
        setLabs(labsData);
        const first = labsData[0]?.id || "";
        setLabId(first);
        if (first) return loadInventory(first);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  function onSelectLab(next: string) {
    setLabId(next);
    setError(null);
    setStatus(null);
    loadInventory(next).catch((err: Error) => setError(err.message));
  }

  async function ensureRoot() {
    if (!labId) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await apiFetch("/ca/ensure-root", {
        method: "POST",
        body: JSON.stringify({ lab_id: labId }),
      });
      setStatus("Lab root CA is ready and published to FreeRADIUS trust.");
      await loadInventory(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create lab CA");
    } finally {
      setBusy(false);
    }
  }

  async function ensureIntermediate() {
    if (!labId) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await apiFetch("/ca/ensure-intermediate", {
        method: "POST",
        body: JSON.stringify({ lab_id: labId }),
      });
      setStatus(
        "Intermediate CA is ready. New client certificates are signed by it; FreeRADIUS still trusts the root.",
      );
      await loadInventory(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create intermediate CA");
    } finally {
      setBusy(false);
    }
  }

  async function issueCert(e?: FormEvent) {
    e?.preventDefault();
    if (!labId || !identity.trim()) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await apiFetch("/ca/issue-client", {
        method: "POST",
        body: JSON.stringify({ lab_id: labId, identity: identity.trim(), days }),
      });
      setStatus(`Issued client certificate for "${identity.trim()}".`);
      setIdentity("");
      await loadInventory(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Certificate issue failed");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(cert: Certificate) {
    if (!labId) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await apiFetch("/ca/revoke", {
        method: "POST",
        body: JSON.stringify({ lab_id: labId, certificate_id: cert.id }),
      });
      setStatus(`Revoked ${cert.identity || cert.subject}. The CRL was updated.`);
      await loadInventory(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Revocation failed");
    } finally {
      setBusy(false);
    }
  }

  const certs = inventory?.certificates || [];

  return (
    <div className="page-enter space-y-6">
      <PageHeader
        title="Certificates"
        subtitle="Lab CA inventory for EAP-TLS: issue client certificates, download bundles, and revoke (with CRL)."
        actions={
          labs.length > 0 && (
            <label className="text-sm">
              <span className="mr-2 text-ink/70">Lab</span>
              <select
                className="ui-input"
                value={labId}
                onChange={(e) => onSelectLab(e.target.value)}
              >
                {labs.map((lab) => (
                  <option key={lab.id} value={lab.id}>
                    {lab.name}
                  </option>
                ))}
              </select>
            </label>
          )
        }
      />

      {error && <StatusBanner tone="error">{error}</StatusBanner>}
      {status && <StatusBanner tone="ok">{status}</StatusBanner>}

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-xl font-semibold">Lab certificate authority</h2>
            {inventory?.authority ? (
              <p className="mt-1 text-sm text-ink/70">
                {inventory.authority.name}
                {isAdvanced && (
                  <span className="ml-2 font-mono text-xs text-ink/50">
                    {inventory.authority.subject}
                  </span>
                )}
              </p>
            ) : (
              <p className="mt-1 text-sm text-ink/60">
                No lab CA yet. Create one to issue EAP-TLS client certificates.
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {!inventory?.authority && (
              <Button variant="signal" disabled={busy} onClick={ensureRoot}>
                {busy ? "Working…" : "Create lab CA"}
              </Button>
            )}
            {inventory?.authority && (
              <Button
                variant="ghost"
                onClick={() =>
                  apiDownload(`/ca/root.pem?lab_id=${labId}`, `lab-${labId}-root.pem`).catch(
                    (err: Error) => setError(err.message),
                  )
                }
              >
                Download root PEM
              </Button>
            )}
            {inventory?.authority && !inventory.has_intermediate && (
              <Button variant="ghost" disabled={busy} onClick={ensureIntermediate}>
                {busy ? "Working…" : "Create intermediate CA"}
              </Button>
            )}
            {inventory?.authority && inventory.has_intermediate && (
              <span className="self-center text-xs text-ink/55">
                Clients are signed by the intermediate CA
              </span>
            )}
          </div>
        </div>

        {inventory?.authority && (
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-ink/10 pt-4 text-sm">
            <span className="text-ink/70">
              CRL: {inventory.crl_available ? "generated" : "none yet"}
              {inventory.crl_enforced ? " · enforced by FreeRADIUS" : " · not enforced (advisory)"}
            </span>
            {inventory.crl_available && (
              <Button
                variant="ghost"
                onClick={() =>
                  apiDownload(`/ca/crl.pem?lab_id=${labId}`, `lab-${labId}-crl.pem`).catch(
                    (err: Error) => setError(err.message),
                  )
                }
              >
                Download CRL
              </Button>
            )}
          </div>
        )}
      </Panel>

      <Panel>
        <h2 className="font-display text-xl font-semibold">Issue client certificate</h2>
        <form onSubmit={issueCert} className="mt-3 flex flex-wrap items-end gap-3">
          <Field label="Identity (CN)">
            <input
              className="ui-input"
              value={identity}
              onChange={(e) => setIdentity(e.target.value)}
              placeholder="alice"
              required
            />
          </Field>
          {isAdvanced && (
            <Field label="Validity (days)">
              <input
                type="number"
                className="ui-input w-28 font-mono"
                min={1}
                max={3650}
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              />
            </Field>
          )}
          <Button type="submit" variant="signal" disabled={busy || !identity.trim()}>
            {busy ? "Issuing…" : "Issue certificate"}
          </Button>
        </form>
        <p className="mt-2 text-xs text-ink/55">
          Letters, digits, and <code>. _ @ -</code> only. The identity becomes the certificate CN
          and its EAP-TLS username.
        </p>
      </Panel>

      <section className="ui-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-ink/10 bg-mist/50">
            <tr>
              <th className="px-4 py-3">Identity</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Expires</th>
              {isAdvanced && <th className="px-4 py-3">Serial</th>}
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {certs.length === 0 ? (
              <tr>
                <td className="px-4 py-8 text-ink/70" colSpan={isAdvanced ? 6 : 5}>
                  No certificates issued yet in this lab.
                </td>
              </tr>
            ) : (
              certs.map((cert) => (
                <tr key={cert.id} className="border-b border-ink/5">
                  <td className="px-4 py-3">{cert.identity || cert.subject}</td>
                  <td className="px-4 py-3 uppercase tracking-wide text-ink/70">
                    {cert.cert_type}
                  </td>
                  <td className={`px-4 py-3 font-medium capitalize ${statusClass(cert.status)}`}>
                    {cert.status}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {cert.not_after ? new Date(cert.not_after).toLocaleDateString() : "—"}
                  </td>
                  {isAdvanced && (
                    <td className="px-4 py-3 font-mono text-xs text-ink/60">{cert.serial || "—"}</td>
                  )}
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      {cert.download_bundle && (
                        <button
                          type="button"
                          className="text-xs text-signal underline-offset-2 hover:underline"
                          onClick={() =>
                            apiDownload(
                              cert.download_bundle!.replace(/^\/api/, ""),
                              `${cert.identity || "client"}-eap-tls.zip`,
                            ).catch((err: Error) => setError(err.message))
                          }
                        >
                          Bundle
                        </button>
                      )}
                      {cert.download_p12 && (
                        <button
                          type="button"
                          className="text-xs text-signal underline-offset-2 hover:underline"
                          onClick={() =>
                            apiDownload(
                              cert.download_p12!.replace(/^\/api/, ""),
                              `${cert.identity || "client"}.p12`,
                            ).catch((err: Error) => setError(err.message))
                          }
                        >
                          .p12
                        </button>
                      )}
                      {cert.cert_type === "client" && cert.status !== "revoked" && (
                        <button
                          type="button"
                          className="text-xs text-fail underline-offset-2 hover:underline disabled:opacity-50"
                          disabled={busy}
                          onClick={() => revoke(cert)}
                        >
                          Revoke
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
