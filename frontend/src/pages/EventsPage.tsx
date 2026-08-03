import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, type AuthEvent } from "../api/client";
import { Button, PageHeader, StatusBanner } from "../components/ui";

const POLL_MS = 3000;

export function EventsPage() {
  const [events, setEvents] = useState<AuthEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const refreshInFlight = useRef(false);

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
        subtitle="Live FreeRADIUS outcomes from the pinned DOT1X linelog (success, failure, and reason when available)."
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
              <th className="px-4 py-3">Reason</th>
              <th className="px-4 py-3">NAS</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td className="px-4 py-8 text-ink/70" colSpan={6}>
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
                return (
                  <tr
                    key={event.id}
                    className={`border-b border-ink/5 ${ok ? "bg-signal/5" : "bg-fail/5"}`}
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
                        "—"
                      ) : event.failure_summary ? (
                        <div>
                          <p className="font-medium">{event.failure_summary}</p>
                          {event.failure_hint && (
                            <p className="mt-1 text-xs text-ink/60">{event.failure_hint}</p>
                          )}
                          {event.failure_reason &&
                            event.failure_reason !== event.failure_summary && (
                              <p className="mt-1 font-mono text-xs text-ink/45">
                                {event.failure_reason}
                              </p>
                            )}
                        </div>
                      ) : (
                        event.failure_reason || "—"
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{event.nas_ip || "—"}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
