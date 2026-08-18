import { Fragment, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, type AuthEvent } from "../api/client";
import { Button, InfoTip, PageHeader, ReplyAttributes, StatusBanner } from "../components/ui";
import { useMode } from "../modes/ModeContext";

const POLL_MS = 3000;
const TABLE_COLUMNS = 6;

function looksLikeMac(identity: string): boolean {
  const hex = identity.replace(/[\s:.-]/g, "");
  return hex.length === 12 && /^[0-9a-fA-F]+$/.test(hex);
}

function identityTarget(event: AuthEvent): { to: string; label: string } | null {
  if (!event.identity) return null;
  const q = encodeURIComponent(event.identity);
  if (event.method === "mab" || looksLikeMac(event.identity)) {
    return { to: `/endpoints?q=${q}`, label: `Open ${event.identity} on Endpoints` };
  }
  return { to: `/users?q=${q}`, label: `Open ${event.identity} on Users` };
}

function EventDetail({ event, verbose }: { event: AuthEvent; verbose: boolean }) {
  const ok = event.result === "success";
  const target = identityTarget(event);
  const showRawReason =
    verbose && event.failure_reason && event.failure_reason !== event.failure_summary;

  return (
    <div className="space-y-4">
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="inline-flex items-center gap-1.5 text-ink/50">
            Authorization
            <InfoTip label="About returned attributes">
              The reply attributes FreeRADIUS sent back with the Access-Accept — this is what
              the switch or AP actually acts on. A VLAN shows as{" "}
              <span className="font-mono">Tunnel-Private-Group-Id</span> and a role as{" "}
              <span className="font-mono">Filter-Id</span>. Assign them on the{" "}
              <span className="font-medium">Authorization</span> page.
            </InfoTip>
          </dt>
          <dd className="mt-1">
            {ok ? (
              <ReplyAttributes attributes={event.returned_attributes} verbose={verbose} />
            ) : (
              <span className="text-ink/50">None — Access-Reject grants no attributes.</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-ink/50">NAS</dt>
          <dd className="mt-1 font-mono text-xs">{event.nas_ip || "—"}</dd>
        </div>
        {!ok && (
          <div className="sm:col-span-2">
            <dt className="text-ink/50">Why it failed</dt>
            <dd className="mt-1">
              <p className="font-medium">{event.failure_summary || event.failure_reason || "—"}</p>
              {event.failure_hint && <p className="mt-1 text-ink/70">{event.failure_hint}</p>}
              {showRawReason && (
                <p className="mt-2 font-mono text-xs text-ink/45">{event.failure_reason}</p>
              )}
            </dd>
          </div>
        )}
        {target && (
          <div>
            <dt className="text-ink/50">Identity</dt>
            <dd className="mt-1">
              <Link className="text-signal underline-offset-2 hover:underline" to={target.to}>
                {target.label}
              </Link>
            </dd>
          </div>
        )}
        {verbose && (
          <>
            <div>
              <dt className="text-ink/50">Event ID</dt>
              <dd className="mt-1 break-all font-mono text-xs text-ink/60">{event.id}</dd>
            </div>
            <div>
              <dt className="text-ink/50">Lab ID</dt>
              <dd className="mt-1 break-all font-mono text-xs text-ink/60">
                {event.lab_id || "—"}
              </dd>
            </div>
          </>
        )}
      </dl>
      {verbose && (
        <div>
          <p className="text-sm text-ink/50">Raw linelog</p>
          <pre className="mt-1 max-h-40 overflow-auto border border-ink/10 bg-mist/60 p-3 font-mono text-xs whitespace-pre-wrap">
            {event.raw_ref || "—"}
          </pre>
        </div>
      )}
    </div>
  );
}

export function EventsPage() {
  const { isAdvanced } = useMode();
  const [events, setEvents] = useState<AuthEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const refreshInFlight = useRef(false);

  function toggleExpanded(id: string) {
    setExpandedId((current) => (current === id ? null : id));
  }

  async function refresh() {
    // Skip overlapping polls: a slow response (e.g. during a FreeRADIUS
    // restart) must not land after a newer one and roll the table backwards.
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    try {
      const data = await apiFetch<AuthEvent[]>("/events?limit=100");
      setEvents(data);
      setLastRefresh(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load events");
    } finally {
      refreshInFlight.current = false;
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = window.setInterval(() => {
      refresh();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [autoRefresh]);

  return (
    <div className="page-enter space-y-6">
      <PageHeader
        title="Authentication Events"
        subtitle="Live FreeRADIUS outcomes from the pinned DOT1X linelog. Click a row for details — Simple shows the outcome and a fix hint; Advanced adds the raw linelog and RADIUS names."
        actions={
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              Auto-refresh
            </label>
            <Button variant="ghost" onClick={() => refresh()}>
              Refresh now
            </Button>
            {lastRefresh && (
              <span className="text-ink/50">Updated {lastRefresh.toLocaleTimeString()}</span>
            )}
          </div>
        }
      />

      {error && <StatusBanner tone="error">{error}</StatusBanner>}

      <section className="ui-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-ink/10 bg-mist/50">
            <tr>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Identity</th>
              <th className="px-4 py-3">Method</th>
              <th className="px-4 py-3">Result</th>
              <th className="px-4 py-3">Summary</th>
              <th className="px-4 py-3">Details</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td className="px-4 py-8 text-ink/70" colSpan={TABLE_COLUMNS}>
                  <p className="font-medium text-ink">No authentication events yet.</p>
                  <p className="mt-2 max-w-xl">
                    Generate one from the{" "}
                    <Link className="underline" to="/test">
                      Authentication Test
                    </Link>{" "}
                    page, the{" "}
                    <Link className="underline" to="/wizard">
                      Wizard
                    </Link>
                    , or point a real NAS/AP at FreeRADIUS (UDP 1812) with a synced client secret.
                  </p>
                </td>
              </tr>
            ) : (
              events.map((event) => {
                const ok = event.result === "success";
                const open = expandedId === event.id;
                const rowTone = ok
                  ? open
                    ? "bg-signal/10"
                    : "bg-signal/5"
                  : open
                    ? "bg-fail/10"
                    : "bg-fail/5";
                return (
                  <Fragment key={event.id}>
                    <tr
                      className={`cursor-pointer border-b border-ink/5 align-top ${rowTone}`}
                      onClick={() => toggleExpanded(event.id)}
                    >
                      <td className="px-4 py-3 font-mono text-xs">
                        {new Date(event.timestamp).toLocaleString()}
                      </td>
                      <td className="px-4 py-3">{event.identity || "—"}</td>
                      <td className="px-4 py-3 uppercase tracking-wide">{event.method}</td>
                      <td className={`px-4 py-3 font-medium ${ok ? "text-signal" : "text-fail"}`}>
                        {ok ? "Accept" : "Reject"}
                      </td>
                      <td className="px-4 py-3">
                        {ok ? (
                          <ReplyAttributes attributes={event.returned_attributes} />
                        ) : (
                          event.failure_summary || event.failure_reason || "—"
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          className="text-xs text-signal underline-offset-2 hover:underline"
                          aria-expanded={open}
                          aria-label={open ? "Hide event details" : "Show event details"}
                          onClick={(click) => {
                            click.stopPropagation();
                            toggleExpanded(event.id);
                          }}
                        >
                          {open ? "Hide" : "Details"}
                        </button>
                      </td>
                    </tr>
                    {open && (
                      <tr className={rowTone}>
                        <td colSpan={TABLE_COLUMNS} className="px-4 py-4">
                          <EventDetail event={event} verbose={isAdvanced} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
