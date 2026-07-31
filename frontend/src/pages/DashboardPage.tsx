import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, type HealthResponse, type Lab } from "../api/client";
import { useMode } from "../modes/ModeContext";

export function DashboardPage() {
  const { isAdvanced } = useMode();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [labs, setLabs] = useState<Lab[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<HealthResponse>("/health"),
      apiFetch<Lab[]>("/labs"),
    ])
      .then(([h, l]) => {
        setHealth(h);
        setLabs(l);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="space-y-8">
      <section>
        <h1 className="font-display text-3xl font-bold">Dashboard</h1>
        <p className="mt-1 text-ink/70">
          Lab status and quick entry points. Full RADIUS/EAP paths arrive in later phases.
        </p>
      </section>

      {error && <p className="text-fail">{error}</p>}

      <section className="grid gap-4 md:grid-cols-3">
        {(health?.components || []).map((c) => (
          <div key={c.name} className="border border-black/10 bg-white/70 p-4">
            <p className="text-xs uppercase tracking-wide text-ink/50">{c.name}</p>
            <p className="mt-2 font-mono text-lg">{c.status}</p>
            {isAdvanced && c.detail && (
              <p className="mt-2 break-all font-mono text-xs text-ink/60">{c.detail}</p>
            )}
          </div>
        ))}
      </section>

      <section className="border border-black/10 bg-white/70 p-5">
        <h2 className="font-display text-xl font-semibold">Labs</h2>
        {labs.length === 0 ? (
          <p className="mt-2 text-sm text-ink/60">No labs yet. Run <code>make seed</code>.</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {labs.map((lab) => (
              <li key={lab.id} className="flex items-center justify-between gap-4">
                <div>
                  <p className="font-medium">{lab.name}</p>
                  <p className="text-sm text-ink/60">{lab.description}</p>
                </div>
                {isAdvanced && (
                  <code className="text-xs text-ink/50">{lab.id}</code>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-wrap gap-3">
        <Link className="bg-signal px-4 py-2 font-medium text-ink" to="/wizard">
          Create your first lab
        </Link>
        <Link className="border border-black/15 bg-white px-4 py-2" to="/users">
          Manage users
        </Link>
        <Link className="border border-black/15 bg-white px-4 py-2" to="/clients">
          RADIUS clients
        </Link>
      </section>
    </div>
  );
}
