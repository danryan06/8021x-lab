import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, type AuthEvent } from "../api/client";

const POLL_MS = 3000;

export function EventsPage() {
  const [events, setEvents] = useState<AuthEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  async function refresh() {
    try {
      const data = await apiFetch<AuthEvent[]>("/events?limit=100");
      setEvents(data);
      setLastRefresh(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load events");
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
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-bold">Authentication Events</h1>
          <p className="mt-1 text-ink/70">
            Live FreeRADIUS outcomes from the pinned DOT1X linelog (success, failure, and reason
            when available).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh
          </label>
          <button
            type="button"
            onClick={() => refresh()}
            className="border border-black/15 bg-white px-3 py-1.5"
          >
            Refresh now
          </button>
          {lastRefresh && (
            <span className="text-ink/50">Updated {lastRefresh.toLocaleTimeString()}</span>
          )}
        </div>
      </section>

      {error && <p className="text-fail">{error}</p>}

      <section className="overflow-x-auto border border-black/10 bg-white/70">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-black/10 bg-mist/80">
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
                    page (PEAP or EAP-TLS), or point a real NAS/AP at this lab&apos;s FreeRADIUS
                    (UDP 1812) with a synced client secret.
                  </p>
                </td>
              </tr>
            ) : (
              events.map((event) => {
                const ok = event.result === "success";
                return (
                  <tr
                    key={event.id}
                    className={`border-b border-black/5 ${ok ? "bg-signal/5" : "bg-fail/5"}`}
                  >
                    <td className="px-4 py-3 font-mono text-xs">
                      {new Date(event.timestamp).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">{event.identity || "—"}</td>
                    <td className="px-4 py-3 uppercase tracking-wide">{event.method}</td>
                    <td className={`px-4 py-3 font-medium ${ok ? "text-signal" : "text-fail"}`}>
                      {ok ? "Accept" : "Reject"}
                    </td>
                    <td className="px-4 py-3">{event.failure_reason || "—"}</td>
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
