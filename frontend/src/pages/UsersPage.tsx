import { FormEvent, useEffect, useState } from "react";
import {
  apiFetch,
  type FreeRadiusSyncResponse,
  type Lab,
  type RadiusUser,
} from "../api/client";
import { useMode } from "../modes/ModeContext";

type GenerateResponse = {
  created: number;
  users: RadiusUser[];
  credentials: { username: string; password: string }[];
};

export function UsersPage() {
  const { isAdvanced } = useMode();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [users, setUsers] = useState<RadiusUser[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [count, setCount] = useState(10);
  const [generated, setGenerated] = useState<GenerateResponse["credentials"]>([]);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function refresh(selectedLab: string) {
    const data = await apiFetch<RadiusUser[]>(
      selectedLab ? `/users?lab_id=${selectedLab}` : "/users",
    );
    setUsers(data);
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
      await apiFetch("/users", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          username,
          password,
          groups: ["lab"],
        }),
      });
      setUsername("");
      setPassword("");
      setStatus(`User created and synced to FreeRADIUS (radcheck NT-Password).`);
      await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function onGenerate() {
    if (!labId) return;
    setError(null);
    setStatus(null);
    try {
      const res = await apiFetch<GenerateResponse>("/users/generate", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          count,
          prefix: "user",
          groups: ["students"],
        }),
      });
      setGenerated(res.credentials);
      setStatus(`${res.created} users generated and synced to FreeRADIUS.`);
      await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generate failed");
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
    <div className="space-y-8">
      <section>
        <h1 className="font-display text-3xl font-bold">Users</h1>
        <p className="mt-1 text-ink/70">
          Local RADIUS identities for PEAP labs. Create/update syncs NT-Password into FreeRADIUS
          SQL immediately.
        </p>
      </section>

      {error && <p className="text-fail">{error}</p>}
      {status && <p className="text-signal">{status}</p>}

      <div className="flex flex-wrap items-end gap-4">
        <label className="text-sm">
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
        <button
          type="button"
          onClick={syncLab}
          className="border border-black/15 bg-white px-3 py-2 text-sm"
        >
          Sync to FreeRADIUS
        </button>
      </div>

      <section className="grid gap-6 lg:grid-cols-2">
        <form onSubmit={onCreate} className="border border-black/10 bg-white/70 p-5">
          <h2 className="font-semibold">Create user</h2>
          <label className="mt-3 block text-sm">
            Username
            <input
              className="mt-1 w-full border border-black/15 px-3 py-2"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label className="mt-3 block text-sm">
            Password
            <input
              type="password"
              className="mt-1 w-full border border-black/15 px-3 py-2"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <button type="submit" className="mt-4 bg-ink px-4 py-2 text-white">
            Create
          </button>
        </form>

        <div className="border border-black/10 bg-white/70 p-5">
          <h2 className="font-semibold">Generate test users</h2>
          <label className="mt-3 block text-sm">
            Count
            <input
              type="number"
              min={1}
              max={500}
              className="mt-1 w-32 border border-black/15 px-3 py-2"
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            />
          </label>
          <button
            type="button"
            onClick={onGenerate}
            className="mt-4 bg-signal px-4 py-2 font-medium text-ink"
          >
            Generate {count} users
          </button>
          {generated.length > 0 && (
            <div className="mt-4 max-h-48 overflow-auto border border-black/10 bg-mist p-3 font-mono text-xs">
              {generated.map((cred) => (
                <div key={cred.username}>
                  {cred.username} / {cred.password}
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="overflow-x-auto border border-black/10 bg-white/70">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-black/10 bg-mist/80">
            <tr>
              <th className="px-4 py-3">Username</th>
              <th className="px-4 py-3">Groups</th>
              <th className="px-4 py-3">Status</th>
              {isAdvanced && <th className="px-4 py-3">ID</th>}
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className="border-b border-black/5">
                <td className="px-4 py-3 font-medium">{user.username}</td>
                <td className="px-4 py-3">{(user.groups || []).join(", ")}</td>
                <td className="px-4 py-3">{user.status}</td>
                {isAdvanced && (
                  <td className="px-4 py-3 font-mono text-xs text-ink/50">{user.id}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
