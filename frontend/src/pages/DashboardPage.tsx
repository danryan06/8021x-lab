import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  apiFetch,
  type AuthEvent,
  type FreeRadiusSyncResponse,
  type HealthResponse,
  type Lab,
} from "../api/client";
import { useMode } from "../modes/ModeContext";
import { Button, PageHeader, Panel, StatusBanner } from "../components/ui";

function statusColor(status: string): string {
  if (status === "ok") return "text-signal";
  if (status === "configured") return "text-ink/80";
  if (status === "degraded") return "text-warn";
  return "text-fail";
}

export function DashboardPage() {
  const { isAdvanced } = useMode();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [labs, setLabs] = useState<Lab[]>([]);
  const [lastEvent, setLastEvent] = useState<AuthEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  async function load() {
    const [h, l, events] = await Promise.all([
      apiFetch<HealthResponse>("/health"),
      apiFetch<Lab[]>("/labs"),
      apiFetch<AuthEvent[]>("/events?limit=1"),
    ]);
    setHealth(h);
    setLabs(l);
    setLastEvent(events[0] || null);
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
    const id = window.setInterval(() => {
      load().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(id);
  }, []);

  async function syncAll() {
    setSyncing(true);
    setSyncMsg(null);
    setError(null);
    try {
      const res = await apiFetch<FreeRadiusSyncResponse>("/freeradius/sync", { method: "POST" });
      setSyncMsg(
        `Synced ${res.users_synced} users, ${res.clients_synced} clients — reload requested`,
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="page-enter space-y-8">
      <PageHeader
        title="Dashboard"
        subtitle="Live lab status: database, API, FreeRADIUS, and the latest authentication event."
      />

      {error && <StatusBanner tone="error">{error}</StatusBanner>}
      {syncMsg && <StatusBanner tone="ok">{syncMsg}</StatusBanner>}

      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {(health?.components || []).map((c) => (
          <div key={c.name} className="ui-panel p-4">
            <p className="text-xs uppercase tracking-wide text-ink/50">{c.name}</p>
            <p className={`mt-2 font-mono text-lg ${statusColor(c.status)}`}>{c.status}</p>
            {isAdvanced && c.detail && (
              <p className="mt-2 break-all font-mono text-xs text-ink/55">{c.detail}</p>
            )}
          </div>
        ))}
      </section>

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl font-semibold">Last authentication event</h2>
          <Link className="text-sm text-signal underline-offset-2 hover:underline" to="/events">
            View all events
          </Link>
        </div>
        {!lastEvent ? (
          <p className="mt-3 text-sm text-ink/60">
            None yet. Use the{" "}
            <Link className="underline" to="/test">
              Authentication Test
            </Link>{" "}
            page or the Wizard to generate one.
          </p>
        ) : (
          <dl className="mt-3 grid gap-2 text-sm md:grid-cols-4">
            <div>
              <dt className="text-ink/50">Time</dt>
              <dd className="font-mono text-xs">
                {new Date(lastEvent.timestamp).toLocaleString()}
              </dd>
            </div>
            <div>
              <dt className="text-ink/50">Identity</dt>
              <dd>{lastEvent.identity || "—"}</dd>
            </div>
            <div>
              <dt className="text-ink/50">Method / result</dt>
              <dd>
                <span className="uppercase">{lastEvent.method}</span>{" "}
                <span
                  className={
                    lastEvent.result === "success"
                      ? "font-medium text-signal"
                      : "font-medium text-fail"
                  }
                >
                  {lastEvent.result === "success" ? "Accept" : "Reject"}
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-ink/50">Reason / NAS</dt>
              <dd>
                {lastEvent.failure_reason || "—"}{" "}
                <span className="font-mono text-xs text-ink/50">{lastEvent.nas_ip}</span>
              </dd>
            </div>
          </dl>
        )}
      </Panel>

      <Panel>
        <h2 className="font-display text-xl font-semibold">Labs</h2>
        {labs.length === 0 ? (
          <p className="mt-2 text-sm text-ink/60">
            No labs yet. Run <code>make seed</code> or use the Wizard.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {labs.map((lab) => (
              <li key={lab.id} className="flex items-center justify-between gap-4">
                <div>
                  <p className="font-medium">{lab.name}</p>
                  <p className="text-sm text-ink/60">{lab.description}</p>
                </div>
                {isAdvanced && <code className="text-xs text-ink/45">{lab.id}</code>}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <section className="flex flex-wrap gap-3">
        <Link className="ui-btn-signal" to="/wizard">
          Guided lab wizard
        </Link>
        <Link className="ui-btn-ghost" to="/test">
          Authentication Test
        </Link>
        <Link className="ui-btn-ghost" to="/users">
          Manage users
        </Link>
        <Link className="ui-btn-ghost" to="/clients">
          RADIUS clients
        </Link>
        <Button variant="ghost" disabled={syncing} onClick={syncAll}>
          {syncing ? "Syncing…" : "Sync to FreeRADIUS"}
        </Button>
      </section>
    </div>
  );
}
