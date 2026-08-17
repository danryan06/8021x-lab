import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  apiFetch,
  type AuthEvent,
  type AuthzPolicy,
  type Endpoint,
  type FreeRadiusSyncResponse,
  type HealthResponse,
  type Lab,
  type RadiusUser,
} from "../api/client";
import { useMode } from "../modes/ModeContext";
import { RadiusTargetPanel } from "../components/RadiusTargetPanel";
import {
  Button,
  PageHeader,
  Panel,
  ReplyAttributes,
  StatusBanner,
} from "../components/ui";

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
  const [users, setUsers] = useState<RadiusUser[]>([]);
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [policies, setPolicies] = useState<AuthzPolicy[]>([]);
  const [mabEvents, setMabEvents] = useState<AuthEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const loadInFlight = useRef(false);

  async function load() {
    // Skip a tick while the previous one is still running so a slow health
    // probe cannot land after (and overwrite) newer data.
    if (loadInFlight.current) return;
    loadInFlight.current = true;
    try {
      const [h, l, events, u, e, p, mab] = await Promise.all([
        apiFetch<HealthResponse>("/health"),
        apiFetch<Lab[]>("/labs"),
        apiFetch<AuthEvent[]>("/events?limit=1"),
        apiFetch<RadiusUser[]>("/users"),
        apiFetch<Endpoint[]>("/endpoints"),
        apiFetch<AuthzPolicy[]>("/authz-policies"),
        apiFetch<AuthEvent[]>("/events?method=mab&limit=5"),
      ]);
      setHealth(h);
      setLabs(l);
      setLastEvent(events[0] || null);
      setUsers(u);
      setEndpoints(e);
      setPolicies(p);
      setMabEvents(mab);
      setError(null);
    } finally {
      loadInFlight.current = false;
    }
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
        `Synced ${res.users_synced} users, ${res.clients_synced} clients, ` +
          `${res.endpoints_synced} endpoints, ${res.policies_synced} authorization policies — ` +
          "FreeRADIUS restarts automatically if client or trust config changed",
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  const enabledEndpoints = endpoints.filter((e) => e.enabled).length;

  return (
    <div className="page-enter space-y-8">
      <PageHeader
        title="Dashboard"
        subtitle="Live lab status: database, API, FreeRADIUS, lab inventory, and the latest authentication event."
      />

      {error && <StatusBanner tone="error">{error}</StatusBanner>}
      {syncMsg && <StatusBanner tone="ok">{syncMsg}</StatusBanner>}

      <RadiusTargetPanel labId={labs[0]?.id} />

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

      <section className="grid gap-4 md:grid-cols-3">
        {[
          {
            to: "/users",
            label: "Users",
            count: users.length,
            hint: "Identities that authenticate with PEAP or EAP-TLS",
          },
          {
            to: "/endpoints",
            label: "Endpoints (MAB)",
            count: endpoints.length,
            hint:
              enabledEndpoints === endpoints.length
                ? "MAC addresses registered for MAC Authentication Bypass"
                : `${enabledEndpoints} enabled · ${endpoints.length - enabledEndpoints} disabled`,
          },
          {
            to: "/policies",
            label: "Authorization policies",
            count: policies.length,
            hint: "VLAN and role attributes returned on Access-Accept",
          },
        ].map((card) => (
          <Link key={card.to} to={card.to} className="ui-panel p-4 transition hover:border-signal/40">
            <p className="text-xs uppercase tracking-wide text-ink/50">{card.label}</p>
            <p className="mt-2 font-display text-3xl font-bold">{card.count}</p>
            <p className="mt-1 text-xs text-ink/60">{card.hint}</p>
          </Link>
        ))}
      </section>

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl font-semibold">Recent MAB activity</h2>
          <Link
            className="text-sm text-signal underline-offset-2 hover:underline"
            to="/endpoints"
          >
            Manage endpoints
          </Link>
        </div>
        {mabEvents.length === 0 ? (
          <p className="mt-3 text-sm text-ink/60">
            No MAB attempts yet. Register a MAC on the{" "}
            <Link className="underline" to="/endpoints">
              Endpoints
            </Link>{" "}
            page, then run a MAB test from the{" "}
            <Link className="underline" to="/test">
              Authentication Test
            </Link>{" "}
            page.
          </p>
        ) : (
          <ul className="mt-3 space-y-2 text-sm">
            {mabEvents.map((event) => (
              <li
                key={event.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-ink/5 pb-2 last:border-0 last:pb-0"
              >
                <span className="font-mono text-xs text-ink/50">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </span>
                <span className="font-mono">{event.identity || "—"}</span>
                <span
                  className={
                    event.result === "success"
                      ? "font-medium text-signal"
                      : "font-medium text-fail"
                  }
                >
                  {event.result === "success" ? "Accept" : "Reject"}
                </span>
                {event.result === "success" ? (
                  <ReplyAttributes attributes={event.returned_attributes} />
                ) : (
                  <span className="text-ink/60">
                    {event.failure_summary || event.failure_reason || "—"}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>

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
        <Link className="ui-btn-ghost" to="/endpoints">
          Endpoints
        </Link>
        <Link className="ui-btn-ghost" to="/policies">
          Authorization
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
