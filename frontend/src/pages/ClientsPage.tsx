import { FormEvent, useEffect, useState } from "react";
import { apiFetch, type Lab, type RadiusClient } from "../api/client";
import { useMode } from "../modes/ModeContext";

export function ClientsPage() {
  const { isAdvanced } = useMode();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [clients, setClients] = useState<RadiusClient[]>([]);
  const [name, setName] = useState("");
  const [ip, setIp] = useState("10.0.0.1");
  const [secret, setSecret] = useState("testing123");
  const [deviceType, setDeviceType] = useState("switch");
  const [error, setError] = useState<string | null>(null);

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
      await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="font-display text-3xl font-bold">RADIUS Clients</h1>
        <p className="mt-1 text-ink/70">
          Network access devices (switches, WLCs, APs) that send RADIUS requests.
        </p>
      </section>

      {error && <p className="text-fail">{error}</p>}

      <label className="block text-sm">
        Lab
        <select
          className="mt-1 block border border-black/15 bg-white px-3 py-2"
          value={labId}
          onChange={(e) => {
            setLabId(e.target.value);
            refresh(e.target.value).catch((err: Error) => setError(err.message));
          }}
        >
          {labs.map((lab) => (
            <option key={lab.id} value={lab.id}>
              {lab.name}
            </option>
          ))}
        </select>
      </label>

      <form onSubmit={onCreate} className="grid gap-4 border border-black/10 bg-white/70 p-5 md:grid-cols-2">
        <label className="text-sm">
          Device name
          <input
            className="mt-1 w-full border border-black/15 px-3 py-2"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <label className="text-sm">
          IP / CIDR
          <input
            className="mt-1 w-full border border-black/15 px-3 py-2"
            value={ip}
            onChange={(e) => setIp(e.target.value)}
            required
          />
        </label>
        <label className="text-sm">
          Shared secret
          <input
            className="mt-1 w-full border border-black/15 px-3 py-2 font-mono"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            required
          />
        </label>
        {isAdvanced && (
          <label className="text-sm">
            Device type
            <input
              className="mt-1 w-full border border-black/15 px-3 py-2"
              value={deviceType}
              onChange={(e) => setDeviceType(e.target.value)}
            />
          </label>
        )}
        <div className="md:col-span-2">
          <button type="submit" className="bg-ink px-4 py-2 text-white">
            Add client
          </button>
        </div>
      </form>

      <section className="overflow-x-auto border border-black/10 bg-white/70">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-black/10 bg-mist/80">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">IP</th>
              <th className="px-4 py-3">Secret</th>
              <th className="px-4 py-3">Enabled</th>
            </tr>
          </thead>
          <tbody>
            {clients.map((client) => (
              <tr key={client.id} className="border-b border-black/5">
                <td className="px-4 py-3 font-medium">{client.name}</td>
                <td className="px-4 py-3 font-mono">{client.ip_address}</td>
                <td className="px-4 py-3 font-mono">
                  {isAdvanced ? client.shared_secret : "••••••••"}
                </td>
                <td className="px-4 py-3">{client.enabled ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
