import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, type RadiusTarget } from "../api/client";
import { Button, Field, Panel, StatusBanner } from "./ui";

export function RadiusTargetPanel({
  labId,
  compact = false,
}: {
  labId?: string;
  compact?: boolean;
}) {
  const [target, setTarget] = useState<RadiusTarget | null>(null);
  const [mode, setMode] = useState<"auto" | "manual">("auto");
  const [advertiseIp, setAdvertiseIp] = useState("");
  const [authPort, setAuthPort] = useState(1812);
  const [acctPort, setAcctPort] = useState(1813);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [secretRevealed, setSecretRevealed] = useState(false);

  async function load() {
    const q = labId ? `?lab_id=${labId}` : "";
    const data = await apiFetch<RadiusTarget>(`/radius-target${q}`);
    setTarget(data);
    setMode(data.mode);
    setAdvertiseIp(data.advertise_ip || data.effective_ip || "");
    setAuthPort(data.auth_port);
    setAcctPort(data.acct_port);
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, [labId]);

  async function onSave(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const body = {
        lab_id: labId || target?.lab_id || null,
        mode,
        advertise_ip: mode === "manual" ? advertiseIp : advertiseIp || null,
        auth_port: authPort,
        acct_port: acctPort,
      };
      const data = await apiFetch<RadiusTarget>("/radius-target", {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setTarget(data);
      setMode(data.mode);
      setAdvertiseIp(data.advertise_ip || data.effective_ip || "");
      setStatus(
        data.mode === "auto"
          ? `Auto mode — advertising ${data.effective_ip || "?"} (DHCP/host detect)`
          : `Manual mode — advertising ${data.effective_ip}`,
      );
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  function useCandidate(ip: string) {
    setMode("manual");
    setAdvertiseIp(ip);
    setEditing(true);
  }

  if (!target && !error) {
    return (
      <Panel>
        <p className="text-sm text-ink/60">Loading RADIUS target…</p>
      </Panel>
    );
  }

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold">RADIUS target</h2>
          <p className="mt-1 text-sm text-ink/65">
            Address your switch/WLC/AP should use. Auto follows host DHCP/LAN detection;
            switch to Manual to pin an IP.
          </p>
        </div>
        {!editing && (
          <Button variant="ghost" onClick={() => setEditing(true)}>
            Configure
          </Button>
        )}
      </div>

      {error && (
        <div className="mt-3">
          <StatusBanner tone="error">{error}</StatusBanner>
        </div>
      )}
      {status && (
        <div className="mt-3">
          <StatusBanner tone="ok">{status}</StatusBanner>
        </div>
      )}
      {target?.warning && (
        <div className="mt-3">
          <StatusBanner tone="info">{target.warning}</StatusBanner>
        </div>
      )}

      {target && !editing && (
        <dl className="mt-4 grid gap-3 text-sm md:grid-cols-2">
          <div>
            <dt className="text-ink/50">Mode</dt>
            <dd className="font-medium capitalize">
              {target.mode}
              {target.mode === "auto" && target.auto_source
                ? ` (${target.auto_source})`
                : ""}
            </dd>
          </div>
          <div>
            <dt className="text-ink/50">Advertise IP</dt>
            <dd className="font-mono text-lg">{target.effective_ip || "— not set —"}</dd>
          </div>
          <div>
            <dt className="text-ink/50">Auth / Acct</dt>
            <dd className="font-mono">
              UDP {target.auth_port} / {target.acct_port}
            </dd>
          </div>
          <div>
            <dt className="text-ink/50">Lab shared secret</dt>
            <dd className="flex items-center gap-2 font-mono">
              {/* Masked by default: this panel is on most pages and would
                  otherwise leak the secret on any screen share. */}
              <span>{secretRevealed ? target.lab_shared_secret : "••••••••"}</span>
              <button
                type="button"
                className="text-xs font-sans text-signal underline-offset-2 hover:underline"
                onClick={() => setSecretRevealed((v) => !v)}
              >
                {secretRevealed ? "Hide" : "Reveal"}
              </button>
            </dd>
          </div>
          {!compact && (
            <div className="md:col-span-2">
              <dt className="text-ink/50">NAS setup</dt>
              <dd className="mt-1 text-ink/80">{target.nas_instructions}</dd>
              <p className="mt-2 text-sm text-ink/60">
                Also register each NAS source IP on the{" "}
                <Link className="underline" to="/clients">
                  RADIUS Clients
                </Link>{" "}
                page.
              </p>
            </div>
          )}
        </dl>
      )}

      {editing && (
        <form onSubmit={onSave} className="mt-4 space-y-4">
          <div className="flex flex-col gap-2 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="radius-mode"
                checked={mode === "auto"}
                onChange={() => setMode("auto")}
              />
              Auto (DHCP / host detect)
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="radius-mode"
                checked={mode === "manual"}
                onChange={() => setMode("manual")}
              />
              Manual IP
            </label>
          </div>

          <Field label={mode === "manual" ? "Advertise IP" : "Preferred IP (optional preset)"}>
            <input
              className="ui-input font-mono"
              value={advertiseIp}
              onChange={(e) => setAdvertiseIp(e.target.value)}
              placeholder="10.0.0.50"
              required={mode === "manual"}
            />
          </Field>

          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Auth port">
              <input
                type="number"
                className="ui-input font-mono"
                value={authPort}
                onChange={(e) => setAuthPort(Number(e.target.value))}
              />
            </Field>
            <Field label="Acct port">
              <input
                type="number"
                className="ui-input font-mono"
                value={acctPort}
                onChange={(e) => setAcctPort(Number(e.target.value))}
              />
            </Field>
          </div>

          {target && target.candidates.length > 0 && (
            <div>
              <p className="text-sm text-ink/60">Detected candidates</p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {target.candidates.map((c) => (
                  <li key={`${c.source}-${c.ip}`}>
                    <button
                      type="button"
                      className="ui-btn-ghost font-mono text-xs"
                      onClick={() => useCandidate(c.ip)}
                      title={`${c.source}${c.interface ? ` · ${c.interface}` : ""}${
                        c.likely_docker ? " · likely docker" : ""
                      }`}
                    >
                      {c.ip}
                      {c.likely_docker ? " (docker?)" : ""}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="signal" disabled={busy}>
              {busy ? "Saving…" : "Save RADIUS target"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setEditing(false);
                setError(null);
                load().catch((err: Error) => setError(err.message));
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Panel>
  );
}
