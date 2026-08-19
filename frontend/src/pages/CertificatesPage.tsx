import { FormEvent, useEffect, useRef, useState } from "react";
import {
  apiDownload,
  apiFetch,
  type Certificate,
  type CertificateInventory,
  type Lab,
  type RadiusUser,
} from "../api/client";
import { Button, Field, InfoTip, PageHeader, Panel, StatusBanner } from "../components/ui";
import { LabSelect } from "../components/LabSelect";
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
  const [users, setUsers] = useState<RadiusUser[]>([]);
  const [identity, setIdentity] = useState("");
  const [identitySource, setIdentitySource] = useState("");
  const [days, setDays] = useState(365);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const selectedLabRef = useRef("");

  async function loadInventory(selected: string) {
    selectedLabRef.current = selected;
    const [data, labUsers] = await Promise.all([
      apiFetch<CertificateInventory>(`/ca/certificates?lab_id=${selected}`),
      apiFetch<RadiusUser[]>(`/users?lab_id=${selected}`),
    ]);
    if (selectedLabRef.current !== selected) return;
    setInventory(data);
    setUsers(labUsers.filter((user) => user.status === "active"));
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
      setIdentitySource("");
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
          <LabSelect labs={labs} value={labId} onChange={onSelectLab} />
        }
      />

      {error && <StatusBanner tone="error">{error}</StatusBanner>}
      {status && <StatusBanner tone="ok">{status}</StatusBanner>}

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-xl font-semibold">
              Lab certificate authority{" "}
              <InfoTip label="What is a lab CA?">
                A certificate authority is the signer every EAP-TLS client and FreeRADIUS must
                trust. The lab CA is a teaching PKI: it issues client certificates and the
                FreeRADIUS trust bundle so a TLS handshake can succeed without a corporate PKI.
              </InfoTip>
            </h2>
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
              <span className="inline-flex items-center gap-1.5">
                <Button variant="signal" disabled={busy} onClick={ensureRoot}>
                  {busy ? "Working…" : "Create lab CA"}
                </Button>
                <InfoTip label="Why create a lab CA?">
                  EAP-TLS needs a signer. This creates the lab root, stores it, and publishes it
                  into FreeRADIUS trust so the server will accept certificates it issued.
                </InfoTip>
              </span>
            )}
            {inventory?.authority && (
              <span className="inline-flex items-center gap-1.5">
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
                <InfoTip label="Why download the root?">
                  Install this root on the client (or use the .p12 bundle) so the supplicant
                  trusts the lab. Without it, EAP-TLS fails with an untrusted-CA error even if
                  the client certificate is valid.
                </InfoTip>
              </span>
            )}
            {inventory?.authority && !inventory.has_intermediate && (
              <span className="inline-flex items-center gap-1.5">
                <Button variant="ghost" disabled={busy} onClick={ensureIntermediate}>
                  {busy ? "Working…" : "Create intermediate CA"}
                </Button>
                <InfoTip label="What is an intermediate CA?">
                  Optional teaching chain: the root signs an intermediate, and the intermediate
                  signs clients — the same pattern most enterprises use. You do not need one for
                  a working lab; it is here to show how a two-tier PKI is trusted.
                </InfoTip>
              </span>
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
            <span className="inline-flex items-center gap-1.5 text-ink/70">
              CRL: {inventory.crl_available ? "generated" : "none yet"}
              {inventory.crl_enforced ? " · enforced by FreeRADIUS" : " · not enforced (advisory)"}
              <InfoTip label="What is a CRL?">
                A Certificate Revocation List is how the CA publishes “this cert is no longer
                valid” before it expires. Revoking a client updates the CRL. FreeRADIUS only
                rejects revoked certs when CRL enforcement is turned on; by default the list is
                generated so you can show the concept without breaking demos.
              </InfoTip>
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
        <h2 className="font-display text-xl font-semibold">
          Issue client certificate{" "}
          <InfoTip label="Why issue a client certificate?">
            EAP-TLS authenticates with a certificate instead of a password. The identity
            (Common Name) must match the username the supplicant presents. Pick an existing
            user so the cert lines up with their RADIUS identity, or type a custom CN for a
            device that is not in the user list.
          </InfoTip>
        </h2>
        <form onSubmit={issueCert} className="mt-3 flex flex-wrap items-end gap-3">
          {users.length > 0 && (
            <Field
              label="User"
              tip={
                <InfoTip label="Why pick a user?">
                  The certificate CN should be the same name FreeRADIUS already knows. Choosing
                  a user from the database avoids a mismatch that looks like “unknown user”
                  during EAP-TLS.
                </InfoTip>
              }
            >
              <select
                className="ui-input"
                value={identitySource}
                onChange={(e) => {
                  const next = e.target.value;
                  setIdentitySource(next);
                  if (next) setIdentity(next);
                }}
              >
                <option value="">Custom identity…</option>
                {users.map((user) => (
                  <option key={user.id} value={user.username}>
                    {user.username}
                    {user.first_name || user.last_name
                      ? ` (${[user.first_name, user.last_name].filter(Boolean).join(" ")})`
                      : ""}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field
            label="Identity (CN)"
            tip={
              <InfoTip label="What is the identity / CN?">
                Common Name on the certificate — the EAP-TLS username. Letters, digits, and
                . _ @ - only. For a person this is usually their RADIUS username.
              </InfoTip>
            }
          >
            <input
              className="ui-input"
              value={identity}
              onChange={(e) => {
                setIdentity(e.target.value);
                setIdentitySource("");
              }}
              placeholder={users.length > 0 ? "alice or a device name" : "alice"}
              required
            />
          </Field>
          {isAdvanced && (
            <Field
              label="Validity (days)"
              tip={
                <InfoTip label="Why set validity?">
                  How long this client certificate is trusted. Shorter is safer for demos of
                  expiry; 365 is a typical lab default.
                </InfoTip>
              }
            >
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
              <th className="px-4 py-3">
                <span className="inline-flex items-center gap-1.5">
                  Identity
                  <InfoTip label="Identity">
                    The name this certificate belongs to — the EAP-TLS username / certificate CN.
                  </InfoTip>
                </span>
              </th>
              <th className="px-4 py-3">
                <span className="inline-flex items-center gap-1.5">
                  Type
                  <InfoTip label="Certificate type">
                    Root and intermediate are the CA itself. Client certificates are what
                    endpoints present during EAP-TLS.
                  </InfoTip>
                </span>
              </th>
              <th className="px-4 py-3">
                <span className="inline-flex items-center gap-1.5">
                  Status
                  <InfoTip label="Certificate status">
                    Active can authenticate. Expired is past its validity date. Revoked was
                    cancelled early and listed on the CRL.
                  </InfoTip>
                </span>
              </th>
              <th className="px-4 py-3">
                <span className="inline-flex items-center gap-1.5">
                  Expires
                  <InfoTip label="Expiry">
                    After this date the certificate is no longer valid, even if it was never
                    revoked. Re-issue a new one for that identity.
                  </InfoTip>
                </span>
              </th>
              {isAdvanced && (
                <th className="px-4 py-3">
                  <span className="inline-flex items-center gap-1.5">
                    Serial
                    <InfoTip label="Serial number">
                      Unique ID the CA assigned. Used to match the cert on the CRL when you
                      revoke.
                    </InfoTip>
                  </span>
                </th>
              )}
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
                          title="ZIP with PEM cert, key, and CA files — for Linux/wpa_supplicant and the Auth Test page"
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
                          title="PKCS#12 file: client cert + key + CA chain, for installing on Windows, macOS, or a phone"
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
                          title="Mark this certificate invalid before it expires. Updates the CRL so FreeRADIUS can reject it."
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
