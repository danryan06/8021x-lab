import { useEffect, useState } from "react";
import { apiFetch, type AuthEvent } from "../api/client";
import { useMode } from "../modes/ModeContext";

export function EventsPage() {
  const { isAdvanced } = useMode();
  const [events, setEvents] = useState<AuthEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<AuthEvent[]>("/events")
      .then(setEvents)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="space-y-6">
      <section>
        <h1 className="font-display text-3xl font-bold">Authentication Events</h1>
        <p className="mt-1 text-ink/70">
          Live FreeRADIUS outcomes from the pinned DOT1X linelog (success, failure, and reason
          when available).
        </p>
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
              {isAdvanced && <th className="px-4 py-3">NAS IP</th>}
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td className="px-4 py-8 text-ink/50" colSpan={isAdvanced ? 6 : 5}>
                  No events yet.
                </td>
              </tr>
            ) : (
              events.map((event) => (
                <tr key={event.id} className="border-b border-black/5">
                  <td className="px-4 py-3 font-mono text-xs">
                    {new Date(event.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">{event.identity || "—"}</td>
                  <td className="px-4 py-3">{event.method}</td>
                  <td
                    className={`px-4 py-3 font-medium ${
                      event.result === "success" ? "text-signal" : "text-fail"
                    }`}
                  >
                    {event.result}
                  </td>
                  <td className="px-4 py-3">{event.failure_reason || "—"}</td>
                  {isAdvanced && (
                    <td className="px-4 py-3 font-mono text-xs">{event.nas_ip || "—"}</td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
