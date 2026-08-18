import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  apiFetch,
  type AuthzPolicy,
  type Endpoint,
  type FreeRadiusSyncResponse,
  type Lab,
} from "../api/client";
import { InfoTip } from "../components/ui";
import { useMode } from "../modes/ModeContext";

type BulkResponse = {
  created: number;
  skipped: number;
  errors: string[];
  endpoints: Endpoint[];
};

type GenerateResponse = {
  created: number;
  endpoints: Endpoint[];
};

export function EndpointsPage() {
  const { isAdvanced } = useMode();
  const [searchParams] = useSearchParams();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [policies, setPolicies] = useState<AuthzPolicy[]>([]);
  const [deviceTypes, setDeviceTypes] = useState<string[]>([]);
  const [filter, setFilter] = useState(() => searchParams.get("q") || "");

  // Create form
  const [mac, setMac] = useState("");
  const [description, setDescription] = useState("");
  const [deviceType, setDeviceType] = useState("printer");
  const [policyId, setPolicyId] = useState("");

  // Bulk + generator
  const [bulkText, setBulkText] = useState("");
  const [bulkPolicyId, setBulkPolicyId] = useState("");
  const [count, setCount] = useState(5);
  const [oui, setOui] = useState("02:1a:2b");
  const [genPolicyId, setGenPolicyId] = useState("");
  const [mixedTypes, setMixedTypes] = useState(true);

  // Inline edit
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editMac, setEditMac] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editDeviceType, setEditDeviceType] = useState("");
  const [editPolicyId, setEditPolicyId] = useState("");
  const [editEnabled, setEditEnabled] = useState(true);

  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function refresh(selectedLab: string) {
    const [endpointData, policyData] = await Promise.all([
      apiFetch<Endpoint[]>(
        selectedLab ? `/endpoints?lab_id=${selectedLab}` : "/endpoints",
      ),
      apiFetch<AuthzPolicy[]>(
        selectedLab ? `/authz-policies?lab_id=${selectedLab}` : "/authz-policies",
      ),
    ]);
    setEndpoints(endpointData);
    setPolicies(policyData);
  }

  useEffect(() => {
    Promise.all([
      apiFetch<Lab[]>("/labs"),
      apiFetch<string[]>("/endpoints/device-types"),
    ])
      .then(([labsData, types]) => {
        setLabs(labsData);
        setDeviceTypes(types);
        const first = labsData[0]?.id || "";
        setLabId(first);
        if (first) return refresh(first);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return endpoints;
    return endpoints.filter((e) =>
      [e.mac_address, e.description, e.device_type, e.authz_policy_name]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }, [endpoints, filter]);

  function policyLabel(policy: AuthzPolicy): string {
    return policy.summary ? `${policy.name} — ${policy.summary}` : policy.name;
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!labId) return;
    setError(null);
    setStatus(null);
    try {
      const created = await apiFetch<Endpoint>("/endpoints", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          mac_address: mac,
          description: description || null,
          device_type: deviceType || null,
          authz_policy_id: policyId || null,
        }),
      });
      setMac("");
      setDescription("");
      setStatus(
        `Endpoint ${created.mac_address} registered for MAB — FreeRADIUS answers the next ` +
          "MAC lookup for it (no reload needed).",
      );
      await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function onBulkAdd() {
    if (!labId || !bulkText.trim()) return;
    setError(null);
    setStatus(null);
    try {
      const res = await apiFetch<BulkResponse>("/endpoints/bulk", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          mac_addresses: bulkText,
          authz_policy_id: bulkPolicyId || null,
        }),
      });
      const errNote = res.errors.length ? ` (${res.errors.length} unreadable)` : "";
      setStatus(
        `Bulk add: ${res.created} registered, ${res.skipped} already existed${errNote}.`,
      );
      if (res.errors.length) setError(res.errors.slice(0, 5).join("; "));
      setBulkText("");
      await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk add failed");
    }
  }

  async function onGenerate() {
    if (!labId) return;
    setError(null);
    setStatus(null);
    try {
      const res = await apiFetch<GenerateResponse>("/endpoints/generate", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          count,
          oui,
          mixed_device_types: mixedTypes,
          device_type: mixedTypes ? null : deviceType,
          authz_policy_id: genPolicyId || null,
        }),
      });
      setStatus(`${res.created} endpoints generated and synced to FreeRADIUS.`);
      await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generate failed");
    }
  }

  function startEdit(endpoint: Endpoint) {
    setEditingId(endpoint.id);
    setEditMac(endpoint.mac_address);
    setEditDescription(endpoint.description || "");
    setEditDeviceType(endpoint.device_type || "");
    setEditPolicyId(endpoint.authz_policy_id || "");
    setEditEnabled(endpoint.enabled);
    setStatus(null);
    setError(null);
  }

  async function saveEdit(endpointId: string) {
    setError(null);
    setStatus(null);
    try {
      await apiFetch(`/endpoints/${endpointId}`, {
        method: "PATCH",
        body: JSON.stringify({
          mac_address: editMac,
          description: editDescription || null,
          device_type: editDeviceType || null,
          authz_policy_id: editPolicyId || null,
          clear_authz_policy: !editPolicyId,
          enabled: editEnabled,
        }),
      });
      setEditingId(null);
      setStatus("Endpoint updated and re-synced to FreeRADIUS.");
      if (labId) await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function toggleEnabled(endpoint: Endpoint) {
    setError(null);
    setStatus(null);
    try {
      await apiFetch(`/endpoints/${endpoint.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !endpoint.enabled }),
      });
      setStatus(
        endpoint.enabled
          ? `${endpoint.mac_address} disabled — its MAB rows were removed from FreeRADIUS, so it now rejects.`
          : `${endpoint.mac_address} enabled — MAB rows restored in FreeRADIUS.`,
      );
      if (labId) await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function onDelete(endpoint: Endpoint) {
    setError(null);
    setStatus(null);
    try {
      await apiFetch(`/endpoints/${endpoint.id}`, { method: "DELETE" });
      setStatus(`${endpoint.mac_address} deleted and removed from FreeRADIUS.`);
      if (labId) await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
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
        `FreeRADIUS sync: ${res.endpoints_synced} endpoints, ${res.policies_synced} group policies, ` +
          `${res.users_synced} users, ${res.clients_synced} clients.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    }
  }

  return (
    <div className="page-enter space-y-8">
      <section>
        <h1 className="font-display text-3xl font-bold">Endpoints (MAB)</h1>
        <p className="mt-1 max-w-3xl text-ink/70">
          Devices that authenticate by MAC address because they cannot run 802.1X — printers,
          cameras, badge readers. Registering a MAC here lets FreeRADIUS accept it, and the
          authorization policy you attach decides which VLAN/role it lands in.
        </p>
      </section>

      {error && <p className="text-fail">{error}</p>}
      {status && <p className="text-signal">{status}</p>}

      <div className="flex flex-wrap items-end gap-4">
        <label className="text-sm">
          Lab
          <select
            className="mt-1 block ui-btn-ghost px-3 py-2"
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
        <button type="button" onClick={syncLab} className="ui-btn-ghost px-3 py-2 text-sm">
          Sync to FreeRADIUS
        </button>
        <label className="text-sm">
          Search
          <input
            className="ui-input mt-1 w-56"
            placeholder="MAC, description, policy…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </label>
      </div>

      {policies.length === 0 && (
        <p className="border border-warn/40 bg-warn/10 px-3 py-2 text-sm text-ink/80">
          No authorization policies yet. Endpoints still authenticate without one, but the NAS
          gets a bare Access-Accept with no VLAN or role. Create one on{" "}
          <Link className="underline" to="/policies">
            Policies
          </Link>
          .
        </p>
      )}

      <section className="grid gap-6 xl:grid-cols-2">
        <form onSubmit={onCreate} className="ui-panel p-5">
          <h2 className="flex items-center gap-2 font-semibold">
            Register an endpoint
            <InfoTip label="What registering an endpoint does">
              <span className="block font-semibold text-ink">MAC address</span>
              <span className="mt-0.5 block">
                Paste it in any format — <code>aa:bb:cc:dd:ee:ff</code>,{" "}
                <code>aa-bb-cc-dd-ee-ff</code>, <code>aabb.ccdd.eeff</code> or{" "}
                <code>aabbccddeeff</code>. The lab stores one canonical form and registers every
                common spelling in FreeRADIUS, because vendors send MACs differently.
              </span>
              <span className="mt-2 block font-semibold text-ink">What gets configured</span>
              <span className="mt-0.5 block">
                A <code>radcheck</code> row (<code>Auth-Type := Accept</code>) so a MAC lookup
                for this device is accepted, plus <code>radreply</code> rows for the
                authorization policy you attach. FreeRADIUS reads both per request, so there is
                no reload.
              </span>
              <span className="mt-2 block font-semibold text-ink">Remember</span>
              <span className="mt-0.5 block">
                MAB is weak authentication: there is no secret, so anyone who can spoof this MAC
                gets the same access.
              </span>
            </InfoTip>
          </h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              MAC address
              <input
                className="ui-input font-mono"
                value={mac}
                onChange={(e) => setMac(e.target.value)}
                placeholder="aa:bb:cc:dd:ee:ff"
                required
              />
            </label>
            <label className="block text-sm">
              Device type
              <select
                className="ui-input"
                value={deviceType}
                onChange={(e) => setDeviceType(e.target.value)}
              >
                {deviceTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              Description
              <input
                className="ui-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Lobby printer"
              />
            </label>
            <label className="block text-sm">
              Authorization policy
              <select
                className="ui-input"
                value={policyId}
                onChange={(e) => setPolicyId(e.target.value)}
              >
                <option value="">None (bare Access-Accept)</option>
                {policies.map((policy) => (
                  <option key={policy.id} value={policy.id}>
                    {policyLabel(policy)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button type="submit" className="mt-4 ui-btn-primary">
            Register endpoint
          </button>
        </form>

        <div className="ui-panel p-5">
          <h2 className="font-semibold">Add many at once</h2>
          <p className="mt-1 text-sm text-ink/60">
            Paste a list of MACs (one per line, or comma separated). Mixed formats are fine;
            duplicates and MACs already in the lab are skipped.
          </p>
          <textarea
            className="ui-input mt-3 h-24 w-full font-mono text-xs"
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
            placeholder={"aa:bb:cc:dd:ee:01\naabb.ccdd.ee02\nAA-BB-CC-DD-EE-03"}
          />
          <label className="mt-3 block text-sm">
            Policy for these endpoints
            <select
              className="ui-input"
              value={bulkPolicyId}
              onChange={(e) => setBulkPolicyId(e.target.value)}
            >
              <option value="">None</option>
              {policies.map((policy) => (
                <option key={policy.id} value={policy.id}>
                  {policyLabel(policy)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="mt-3 ui-btn-primary"
            disabled={!bulkText.trim()}
            onClick={onBulkAdd}
          >
            Add pasted MACs
          </button>

          <hr className="my-5 border-ink/10" />

          <h2 className="font-semibold">Generate demo endpoints</h2>
          <p className="mt-1 text-sm text-ink/60">
            Random MACs under a vendor prefix (OUI) so you can demo MAB at scale.
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              Count
              <input
                type="number"
                min={1}
                max={500}
                className="ui-input"
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
              />
            </label>
            <label className="block text-sm">
              Vendor prefix (OUI)
              <input
                className="ui-input font-mono"
                value={oui}
                onChange={(e) => setOui(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              Policy
              <select
                className="ui-input"
                value={genPolicyId}
                onChange={(e) => setGenPolicyId(e.target.value)}
              >
                <option value="">None</option>
                {policies.map((policy) => (
                  <option key={policy.id} value={policy.id}>
                    {policyLabel(policy)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 self-end text-sm">
              <input
                type="checkbox"
                checked={mixedTypes}
                onChange={(e) => setMixedTypes(e.target.checked)}
              />
              Mix device types
            </label>
          </div>
          <button type="button" className="mt-4 ui-btn-signal" onClick={onGenerate}>
            Generate {count} endpoints
          </button>
        </div>
      </section>

      <section className="overflow-x-auto ui-panel">
        <p className="border-b border-ink/10 px-4 py-2 text-xs text-ink/55">
          Disabling an endpoint removes its rows from FreeRADIUS, so the MAC starts rejecting —
          a quick way to see a MAB failure on the{" "}
          <Link className="underline" to="/events">
            Events
          </Link>{" "}
          page.
        </p>
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-ink/10 bg-mist/40">
            <tr>
              <th className="px-4 py-3">MAC</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Policy</th>
              <th className="px-4 py-3">Enabled</th>
              {isAdvanced && <th className="px-4 py-3">RADIUS usernames</th>}
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((endpoint) =>
              editingId === endpoint.id ? (
                <tr key={endpoint.id} className="border-b border-ink/5 bg-mist/30">
                  <td className="px-4 py-3">
                    <input
                      className="ui-input font-mono"
                      value={editMac}
                      onChange={(e) => setEditMac(e.target.value)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      className="ui-input"
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      className="ui-input"
                      value={editDeviceType}
                      onChange={(e) => setEditDeviceType(e.target.value)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <select
                      className="ui-input"
                      value={editPolicyId}
                      onChange={(e) => setEditPolicyId(e.target.value)}
                    >
                      <option value="">None</option>
                      {policies.map((policy) => (
                        <option key={policy.id} value={policy.id}>
                          {policy.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={editEnabled}
                      onChange={(e) => setEditEnabled(e.target.checked)}
                    />
                  </td>
                  {isAdvanced && <td className="px-4 py-3 text-xs text-ink/50">—</td>}
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="ui-btn-primary px-2 py-1 text-xs"
                        onClick={() => saveEdit(endpoint.id)}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="ui-btn-ghost px-2 py-1 text-xs"
                        onClick={() => setEditingId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={endpoint.id} className="border-b border-ink/5">
                  <td className="px-4 py-3 font-mono">{endpoint.mac_address}</td>
                  <td className="px-4 py-3">{endpoint.description || "—"}</td>
                  <td className="px-4 py-3">{endpoint.device_type || "—"}</td>
                  <td className="px-4 py-3">{endpoint.authz_policy_name || "—"}</td>
                  <td className={`px-4 py-3 ${endpoint.enabled ? "" : "text-fail"}`}>
                    {endpoint.enabled ? "yes" : "no"}
                  </td>
                  {isAdvanced && (
                    <td className="px-4 py-3 font-mono text-xs text-ink/50">
                      {endpoint.radius_usernames.join(", ")}
                    </td>
                  )}
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="ui-btn-ghost px-2 py-1 text-xs"
                        onClick={() => startEdit(endpoint)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="ui-btn-ghost px-2 py-1 text-xs"
                        onClick={() => toggleEnabled(endpoint)}
                      >
                        {endpoint.enabled ? "Disable" : "Enable"}
                      </button>
                      <button
                        type="button"
                        className="ui-btn-ghost px-2 py-1 text-xs text-fail"
                        onClick={() => onDelete(endpoint)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ),
            )}
            {filtered.length === 0 && (
              <tr>
                <td className="px-4 py-6 text-ink/50" colSpan={isAdvanced ? 7 : 6}>
                  No endpoints yet — register a MAC above, then run a MAB test from the{" "}
                  <Link className="underline" to="/test">
                    Auth Test
                  </Link>{" "}
                  page.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
