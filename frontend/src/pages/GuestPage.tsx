import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, type Lab } from "../api/client";
import { Button, Field, PageHeader, Panel, StatusBanner } from "../components/ui";
import { useMode } from "../modes/ModeContext";

type GuestProvision = {
  username: string;
  password: string;
  expires_at: string | null;
  policy_name: string;
  vlan: number | null;
  role: string | null;
  group_name: string;
  policy_created: boolean;
  note: string;
};

export function GuestPage() {
  const { isAdvanced } = useMode();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [hours, setHours] = useState(24);
  const [vlan, setVlan] = useState(40);
  const [role, setRole] = useState("guest-acl");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GuestProvision | null>(null);

  useEffect(() => {
    apiFetch<Lab[]>("/labs")
      .then((data) => {
        setLabs(data);
        setLabId(data[0]?.id || "");
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!labId) return;
    setBusy(true);
    setError(null);
    try {
      const created = await apiFetch<GuestProvision>("/guest/provision", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          display_name: displayName.trim() || null,
          hours,
          vlan,
          role: role.trim() || "guest-acl",
        }),
      });
      setResult(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create guest");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-enter space-y-8">
      <PageHeader
        title="Guest / captive portal"
        subtitle="The lab analogue of Central Web Auth: a short-lived PEAP identity in the guests group, authorized into a guest VLAN."
      />

      {error && <StatusBanner tone="error">{error}</StatusBanner>}

      <Panel>
        <h2 className="font-display text-xl font-semibold">What this is (and is not)</h2>
        <p className="mt-2 text-sm text-ink/70">
          On a real switch or WLC, a guest hits an open SSID, authenticates as a MAC (MAB), and
          is redirected to a captive portal. After they accept the terms, RADIUS sends{" "}
          <span className="font-medium">CoA</span> to move the session into a guest VLAN. This
          page cannot intercept that HTTP redirect — it <span className="font-medium">is</span>{" "}
          the portal. Creating a guest here provisions the identity the portal would have
          created; you prove it with Auth Test (PEAP) or push the VLAN with CoA from Endpoints.
        </p>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="border border-ink/10 bg-mist/40 p-6">
          <p className="text-xs uppercase tracking-wide text-ink/50">Portal preview</p>
          <h2 className="mt-2 font-display text-2xl font-bold">Welcome to Lab Wi-Fi</h2>
          <p className="mt-2 text-sm text-ink/70">
            Guests get internet access for a limited time. This is a classroom stand-in for the
            splash page a hotel or campus would show.
          </p>
          {result ? (
            <div className="mt-4 border border-signal/30 bg-signal/10 p-4 text-sm">
              <p className="font-medium text-signal">Connected</p>
              <p className="mt-2">
                Username <span className="font-mono">{result.username}</span>
              </p>
              <p>
                Password <span className="font-mono">{result.password}</span>
              </p>
              <p className="mt-1 text-xs text-ink/60">
                Shown once — copy it now. PEAP uses this pair; the password is not stored in
                plaintext.
              </p>
            </div>
          ) : (
            <p className="mt-4 text-sm text-ink/55">
              Fill in the form next to this panel and click Connect to issue a guest.
            </p>
          )}
        </section>

        <form onSubmit={onSubmit} className="ui-panel p-5 space-y-3">
          <h2 className="font-semibold">Issue a guest</h2>
          <Field label="Lab">
            <select
              className="ui-input"
              value={labId}
              onChange={(e) => setLabId(e.target.value)}
              required
            >
              {labs.map((lab) => (
                <option key={lab.id} value={lab.id}>
                  {lab.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Guest name (optional)">
            <input
              className="ui-input"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Ada Lovelace"
            />
          </Field>
          <Field label="Access duration (hours)">
            <input
              type="number"
              min={1}
              max={720}
              className="ui-input w-32 font-mono"
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            />
          </Field>
          {isAdvanced && (
            <>
              <Field label="Guest VLAN">
                <input
                  type="number"
                  min={1}
                  max={4094}
                  className="ui-input w-32 font-mono"
                  value={vlan}
                  onChange={(e) => setVlan(Number(e.target.value))}
                />
              </Field>
              <Field label="Role (Filter-Id)">
                <input
                  className="ui-input font-mono"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                />
              </Field>
            </>
          )}
          <Button type="submit" variant="signal" disabled={busy || !labId}>
            {busy ? "Connecting…" : "Connect"}
          </Button>
        </form>
      </div>

      {result && (
        <Panel>
          <h2 className="font-display text-xl font-semibold">What the lab just did</h2>
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-ink/50">Policy</dt>
              <dd>
                {result.policy_name}
                {result.policy_created ? " (created)" : " (already existed)"}
              </dd>
            </div>
            <div>
              <dt className="text-ink/50">Group</dt>
              <dd className="font-mono">{result.group_name}</dd>
            </div>
            <div>
              <dt className="text-ink/50">VLAN / role</dt>
              <dd>
                {result.vlan != null ? `VLAN ${result.vlan}` : "no VLAN"}
                {result.role ? ` · ${result.role}` : ""}
              </dd>
            </div>
            <div>
              <dt className="text-ink/50">Expires</dt>
              <dd className="font-mono text-xs">
                {result.expires_at ? new Date(result.expires_at).toLocaleString() : "—"}
              </dd>
            </div>
          </dl>
          {isAdvanced && <p className="mt-3 text-xs text-ink/55">{result.note}</p>}
          <div className="mt-4 flex flex-wrap gap-3">
            <Link className="ui-btn-signal" to="/test">
              Test PEAP as this guest
            </Link>
            <Link className="ui-btn-ghost" to="/users">
              Users
            </Link>
            <Link className="ui-btn-ghost" to="/policies">
              Authorization
            </Link>
            <Link className="ui-btn-ghost" to="/endpoints">
              CoA / Disconnect
            </Link>
          </div>
        </Panel>
      )}
    </div>
  );
}
