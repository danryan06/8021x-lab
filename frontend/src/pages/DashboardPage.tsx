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
  type RadiusClient,
  type RadiusUser,
  type WirelessProfile,
} from "../api/client";
import { useMode } from "../modes/ModeContext";
import { RadiusTargetPanel } from "../components/RadiusTargetPanel";
import { SECURITY_LABELS } from "../components/WirelessSummary";
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

function wirelessProfileOf(lab: Lab): WirelessProfile | null {
  const raw = lab.settings?.wireless_profile;
  if (!raw || typeof raw !== "object") return null;
  const ssid = (raw as { ssid?: unknown }).ssid;
  if (typeof ssid !== "string" || !ssid.trim()) return null;
  return raw as WirelessProfile;
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
  const [clients, setClients] = useState<RadiusClient[]>([]);
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
      const [h, l, events, u, e, p, mab, c] = await Promise.all([
        apiFetch<HealthResponse>("/health"),
        apiFetch<Lab[]>("/labs"),
        apiFetch<AuthEvent[]>("/events?limit=1"),
        apiFetch<RadiusUser[]>("/users"),
        apiFetch<Endpoint[]>("/endpoints"),
        apiFetch<AuthzPolicy[]>("/authz-policies"),
        apiFetch<AuthEvent[]>("/events?method=mab&limit=5"),
        apiFetch<RadiusClient[]>("/clients"),
      ]);
      setHealth(h);
      setLabs(l);
      setLastEvent(events[0] || null);
      setUsers(u);
      setEndpoints(e);
      setPolicies(p);
      setMabEvents(mab);
      setClients(c);
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
  const wirelessLabs = labs
    .map((lab) => ({ lab, profile: wirelessProfileOf(lab) }))
    .filter((row): row is { lab: Lab; profile: WirelessProfile } => row.profile !== null);

  return (
    <div className="page-enter space-y-8">
      <PageHeader
        title="Dashboard"
        subtitle="Live lab status: database, API, FreeRADIUS, lab inventory, and the latest authentication event."
      />

      {error && <StatusBanner tone="error">{error}</StatusBanner>}
      {syncMsg && <StatusBanner tone="ok">{syncMsg}</StatusBanner>}

      <RadiusTargetPanel labId={labs[0]?.id} />

      {wirelessLabs.length > 0 && (
        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-xl font-semibold">Wireless SSIDs</h2>
            <Link className="text-sm text-signal underline-offset-2 hover:underline" to="/wizard">
              Guided wireless path
            </Link>
          </div>
          <p className="mt-1 text-sm text-ink/60">
            Stored on each lab from the wizard. The RADIUS clients listed are the APs/WLCs
            (and switches) FreeRADIUS will accept for that lab — one row per source address.
          </p>
          <ul className="mt-4 space-y-4">
            {wirelessLabs.map(({ lab, profile }) => {
              const labClients = clients.filter((c) => c.lab_id === lab.id && c.enabled);
              return (
                <li key={lab.id} className="border-b border-ink/5 pb-4 last:border-0 last:pb-0">
                  <p className="font-medium">
                    <span className="font-mono">{profile.ssid}</span>
                    <span className="ml-2 text-sm font-normal text-ink/60">{lab.name}</span>
                  </p>
                  <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
                    <div>
                      <dt className="text-ink/50">Security</dt>
                      <dd>{SECURITY_LABELS[profile.security] || profile.security}</dd>
                    </div>
                    <div>
                      <dt className="text-ink/50">VLAN</dt>
                      <dd className="font-mono">
                        {profile.vlan != null ? profile.vlan : "SSID default"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-ink/50">User group</dt>
                      <dd className="font-mono">{profile.user_group || "—"}</dd>
                    </div>
                    <div>
                      <dt className="text-ink/50">RADIUS clients</dt>
                      <dd>
                        {labClients.length === 0 ? (
                          <Link className="text-signal underline-offset-2 hover:underline" to="/clients">
                            None yet — add the AP/WLC
                          </Link>
                        ) : (
                          <ul className="space-y-0.5">
                            {labClients.map((client) => (
                              <li key={client.id} className="font-mono text-xs">
                                {client.name} ({client.ip_address}
                                {client.device_type ? ` · ${client.device_type}` : ""})
                              </li>
                            ))}
                          </ul>
                        )}
                      </dd>
                    </div>
                  </dl>
                </li>
              );
            })}
          </ul>
        </Panel>
      )}

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
        <Link className="ui-btn-ghost" to="/guest">
          Guest portal
        </Link>
        <Button variant="ghost" disabled={syncing} onClick={syncAll}>
          {syncing ? "Syncing…" : "Sync to FreeRADIUS"}
        </Button>
      </section>
    </div>
  );
}
