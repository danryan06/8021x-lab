import { FormEvent, useEffect, useState } from "react";
import {
  apiFetch,
  type FreeRadiusSyncResponse,
  type Lab,
  type RadiusClient,
} from "../api/client";
import { RadiusTargetPanel } from "../components/RadiusTargetPanel";
import { LabSelect } from "../components/LabSelect";
import { useMode } from "../modes/ModeContext";

export function ClientsPage() {
  const { isAdvanced } = useMode();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [clients, setClients] = useState<RadiusClient[]>([]);
  const [revealedSecrets, setRevealedSecrets] = useState<Record<string, boolean>>({});
  const [name, setName] = useState("");
  const [ip, setIp] = useState("10.0.0.1");
  const [secret, setSecret] = useState("testing123");
  const [deviceType, setDeviceType] = useState("switch");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function refresh(selectedLab: string) {
    const data = await apiFetch<RadiusClient[]>(
      selectedLab ? `/clients?lab_id=${selectedLab}` : "/clients",
    );
    setClients(data);
  }

  useEffect(() => {
    apiFetch<Lab[]>("/labs")
      .then((labsData) => {
        setLabs(labsData);
        const first = labsData[0]?.id || "";
        setLabId(first);
        if (first) return refresh(first);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!labId) return;
    setError(null);
    setStatus(null);
    try {
      await apiFetch("/clients", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          name,
          ip_address: ip,
          shared_secret: secret,
          device_type: deviceType,
        }),
      });
      setName("");
      setStatus(
        "Client created — synced to clients.dot1x.conf + nas, FreeRADIUS reload requested.",
      );
      await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function syncLab() {
    if (!labId) return;
    setError(null);
    setStatus(null);
    try {
      const res = await apiFetch<FreeRadiusSyncResponse>(
        `/freeradius/sync?lab_id=${labId}`,
        { method: "POST" },
      );
      setStatus(
        `FreeRADIUS sync: ${res.users_synced} users, ${res.clients_synced} clients — reload requested`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    }
  }

  return (
    <div className="page-enter space-y-8">
      <section>
        <h1 className="font-display text-3xl font-bold">RADIUS Clients</h1>
        <p className="mt-1 max-w-3xl text-ink/70">
          Each row is a <span className="font-medium">NAS</span> (Network Access Server) — the
          switch, wireless LAN controller, or access point that asks RADIUS whether a device
          may join the network. FreeRADIUS will not accept requests from an address that is not
          listed here. Changes sync immediately.
        </p>
      </section>

      {error && <p className="text-fail">{error}</p>}
      {status && <p className="text-signal">{status}</p>}

      {labId && <RadiusTargetPanel labId={labId} />}

      <div className="flex flex-wrap items-end gap-4">
        <LabSelect
          labs={labs}
          value={labId}
          onChange={(next) => {
            setLabId(next);
            refresh(next).catch((err: Error) => setError(err.message));
          }}
        />
        <button
          type="button"
          onClick={syncLab}
          className="ui-btn-ghost px-3 py-2 text-sm"
        >
          Sync to FreeRADIUS
        </button>
      </div>

      <form onSubmit={onCreate} className="grid gap-4 ui-panel p-5 md:grid-cols-2">
        <label className="text-sm">
          Device name
          <input
            className="ui-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <label className="text-sm">
          IP / CIDR
          <input
            className="ui-input"
            value={ip}
            onChange={(e) => setIp(e.target.value)}
            required
          />
        </label>
        <label className="text-sm">
          Shared secret
          <input
            className="ui-input font-mono"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            required
          />
        </label>
        {isAdvanced && (
          <label className="text-sm">
            Device type
            <input
              className="ui-input"
              value={deviceType}
              onChange={(e) => setDeviceType(e.target.value)}
            />
          </label>
        )}
        <div className="md:col-span-2">
          <button type="submit" className="ui-btn-primary">
            Add client
          </button>
        </div>
      </form>

      <section className="overflow-x-auto ui-panel">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-ink/10 bg-mist/40">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">IP</th>
              <th className="px-4 py-3">Secret</th>
              <th className="px-4 py-3">Enabled</th>
            </tr>
          </thead>
          <tbody>
            {clients.map((client) => {
              const revealed = !!revealedSecrets[client.id];
              return (
                <tr key={client.id} className="border-b border-ink/5">
                  <td className="px-4 py-3 font-medium">{client.name}</td>
                  <td className="px-4 py-3 font-mono">{client.ip_address}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-mono">
                        {revealed ? client.shared_secret : "••••••••"}
                      </span>
                      <button
                        type="button"
                        className="text-xs text-signal underline-offset-2 hover:underline"
                        aria-pressed={revealed}
                        onClick={() =>
                          setRevealedSecrets((prev) => ({
                            ...prev,
                            [client.id]: !prev[client.id],
                          }))
                        }
                      >
                        {revealed ? "Hide" : "Reveal"}
                      </button>
                    </div>
                  </td>
                  <td className="px-4 py-3">{client.enabled ? "yes" : "no"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
