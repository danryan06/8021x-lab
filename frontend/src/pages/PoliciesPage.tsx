import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  apiFetch,
  type AttributeCatalogEntry,
  type AuthzPolicy,
  type Lab,
  type RadiusClient,
} from "../api/client";
import { InfoTip } from "../components/ui";
import { useMode } from "../modes/ModeContext";

type AttributeRow = { name: string; value: string };

// Friendly starting points so Simple mode never asks "which VLAN?" on a blank page.
const VLAN_PRESETS = [
  { vlan: 10, label: "10 — Corporate" },
  { vlan: 20, label: "20 — Printers / IoT" },
  { vlan: 30, label: "30 — Guest" },
  { vlan: 99, label: "99 — Quarantine" },
];

const LOGIN_TIME_PRESETS = [
  { value: "", label: "Any time" },
  { value: "Wk0800-1700", label: "Weekdays 08:00–17:00" },
  { value: "Wk0800-1800", label: "Weekdays 08:00–18:00" },
  { value: "Sa-Su", label: "Weekends" },
  { value: "Al1800-0800", label: "Evenings 18:00–08:00 (overnight)" },
];

function rowsFromAttributes(attributes: Record<string, string>): AttributeRow[] {
  return Object.entries(attributes).map(([name, value]) => ({ name, value }));
}

function attributesFromRows(rows: AttributeRow[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const row of rows) {
    const name = row.name.trim();
    if (!name) continue;
    result[name] = row.value.trim();
  }
  return result;
}

export function PoliciesPage() {
  const { isAdvanced } = useMode();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [policies, setPolicies] = useState<AuthzPolicy[]>([]);
  const [clients, setClients] = useState<RadiusClient[]>([]);
  const [catalog, setCatalog] = useState<AttributeCatalogEntry[]>([]);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("Printers → VLAN 20");
  const [vlanEnabled, setVlanEnabled] = useState(true);
  const [vlan, setVlan] = useState(20);
  const [roleEnabled, setRoleEnabled] = useState(false);
  const [role, setRole] = useState("");
  const [groupName, setGroupName] = useState("");
  const [loginTimePreset, setLoginTimePreset] = useState("");
  const [loginTimeCustom, setLoginTimeCustom] = useState("");
  const [nasIp, setNasIp] = useState("");
  const [rows, setRows] = useState<AttributeRow[]>([]);
  const [enabled, setEnabled] = useState(true);

  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function refresh(selectedLab: string) {
    const [policyData, clientData] = await Promise.all([
      apiFetch<AuthzPolicy[]>(
        selectedLab ? `/authz-policies?lab_id=${selectedLab}` : "/authz-policies",
      ),
      apiFetch<RadiusClient[]>(
        selectedLab ? `/clients?lab_id=${selectedLab}` : "/clients",
      ),
    ]);
    setPolicies(policyData);
    setClients(clientData);
  }

  useEffect(() => {
    Promise.all([
      apiFetch<Lab[]>("/labs"),
      apiFetch<AttributeCatalogEntry[]>("/authz-policies/attribute-catalog"),
    ])
      .then(([labsData, catalogData]) => {
        setLabs(labsData);
        setCatalog(catalogData);
        const first = labsData[0]?.id || "";
        setLabId(first);
        if (first) return refresh(first);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  function resetForm() {
    setEditingId(null);
    setName("");
    setVlanEnabled(true);
    setVlan(20);
    setRoleEnabled(false);
    setRole("");
    setGroupName("");
    setLoginTimePreset("");
    setLoginTimeCustom("");
    setNasIp("");
    setRows([]);
    setEnabled(true);
  }

  function startEdit(policy: AuthzPolicy) {
    setEditingId(policy.id);
    setName(policy.name);
    setVlanEnabled(policy.vlan !== null);
    setVlan(policy.vlan ?? 20);
    setRoleEnabled(!!policy.role);
    setRole(policy.role || "");
    setGroupName(policy.group_name || "");
    const loginTime = policy.conditions?.login_time || "";
    const known = LOGIN_TIME_PRESETS.some((preset) => preset.value === loginTime);
    setLoginTimePreset(loginTime && !known ? "custom" : loginTime);
    setLoginTimeCustom(loginTime && !known ? loginTime : "");
    setNasIp(policy.conditions?.nas_ip || "");
    setRows(rowsFromAttributes(policy.reply_attributes || {}));
    setEnabled(policy.enabled);
    setStatus(null);
    setError(null);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!labId) return;
    setError(null);
    setStatus(null);
    const loginTime =
      loginTimePreset === "custom" ? loginTimeCustom.trim() : loginTimePreset;
    const body = {
      name,
      vlan: vlanEnabled ? vlan : null,
      role: roleEnabled ? role || null : null,
      group_name: groupName || null,
      reply_attributes: attributesFromRows(rows),
      conditions: {
        login_time: loginTime || null,
        nas_ip: nasIp.trim() || null,
      },
      enabled,
    };
    try {
      if (editingId) {
        const updated = await apiFetch<AuthzPolicy>(`/authz-policies/${editingId}`, {
          method: "PATCH",
          body: JSON.stringify({
            ...body,
            clear_vlan: !vlanEnabled,
            clear_role: !roleEnabled,
            clear_group: !groupName,
            clear_conditions: !loginTime && !nasIp.trim(),
          }),
        });
        setStatus(
          `Policy “${updated.name}” updated — ${updated.endpoint_count} endpoint(s) re-synced ` +
            `to FreeRADIUS (${updated.summary || "no attributes"}).`,
        );
      } else {
        const created = await apiFetch<AuthzPolicy>("/authz-policies", {
          method: "POST",
          body: JSON.stringify({ lab_id: labId, ...body }),
        });
        setStatus(
          `Policy “${created.name}” created — returns ${created.summary || "no attributes"}.`,
        );
      }
      resetForm();
      await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function onDelete(policy: AuthzPolicy) {
    setError(null);
    setStatus(null);
    try {
      await apiFetch(`/authz-policies/${policy.id}`, { method: "DELETE" });
      setStatus(
        `Policy “${policy.name}” deleted. Endpoints that used it keep authenticating, but ` +
          "now get a bare Access-Accept.",
      );
      if (editingId === policy.id) resetForm();
      if (labId) await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="page-enter space-y-8">
      <section>
        <h1 className="font-display text-3xl font-bold">Authorization Policies</h1>
        <p className="mt-1 max-w-3xl text-ink/70">
          Authentication answers “who are you?”; authorization answers “what do you get?”. A
          policy is the set of reply attributes FreeRADIUS returns with an Access-Accept — the
          VLAN the port moves to, the role/ACL the NAS applies. Optional conditions restrict
          when that accept is allowed (time of day) and which NAS may ask for it.
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
        <span className="text-sm text-ink/60">
          {isAdvanced
            ? "Advanced mode: edit raw RADIUS reply attributes below."
            : "Simple mode: pick a VLAN and role — switch to Advanced to edit raw attributes."}
        </span>
      </div>

      <form onSubmit={onSubmit} className="ui-panel space-y-4 p-5">
        <h2 className="flex items-center gap-2 font-semibold">
          {editingId ? "Edit policy" : "Create policy"}
          <InfoTip label="How a policy reaches FreeRADIUS">
            <span className="block font-semibold text-ink">VLAN</span>
            <span className="mt-0.5 block">
              Sent as three attributes — <code>Tunnel-Type = VLAN</code>,{" "}
              <code>Tunnel-Medium-Type = IEEE-802</code> and{" "}
              <code>Tunnel-Private-Group-Id = &lt;id&gt;</code>. A switch needs all three before
              it will move the port.
            </span>
            <span className="mt-2 block font-semibold text-ink">Role</span>
            <span className="mt-0.5 block">
              Sent as <code>Filter-Id</code>, naming an ACL/role that already exists on the
              switch or WLC.
            </span>
            <span className="mt-2 block font-semibold text-ink">Where it is stored</span>
            <span className="mt-0.5 block">
              Endpoints get these rows in <code>radreply</code>; a policy bound to a user group
              gets them in <code>radgroupreply</code>. FreeRADIUS reads both per request.
            </span>
          </InfoTip>
        </h2>

        <label className="block text-sm">
          Policy name
          <input
            className="ui-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Printers → VLAN 20"
            required
          />
        </label>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={vlanEnabled}
                onChange={(e) => setVlanEnabled(e.target.checked)}
              />
              Put the device in a VLAN
            </label>
            {vlanEnabled && (
              <div className="flex flex-wrap items-end gap-3">
                <label className="block text-sm">
                  VLAN id
                  <input
                    type="number"
                    min={1}
                    max={4094}
                    className="ui-input w-28"
                    value={vlan}
                    onChange={(e) => setVlan(Number(e.target.value))}
                  />
                </label>
                <label className="block text-sm">
                  Common labs
                  <select
                    className="ui-input"
                    value={VLAN_PRESETS.some((p) => p.vlan === vlan) ? vlan : ""}
                    onChange={(e) => setVlan(Number(e.target.value))}
                  >
                    <option value="">Custom…</option>
                    {VLAN_PRESETS.map((preset) => (
                      <option key={preset.vlan} value={preset.vlan}>
                        {preset.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={roleEnabled}
                onChange={(e) => setRoleEnabled(e.target.checked)}
              />
              Apply a role / ACL name
            </label>
            {roleEnabled && (
              <label className="block text-sm">
                Role name {isAdvanced && <span className="text-ink/50">(Filter-Id)</span>}
                <input
                  className="ui-input"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  placeholder="printers-acl"
                />
              </label>
            )}
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm">
            Also apply to user group (optional)
            <input
              className="ui-input"
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              placeholder="students"
            />
            <span className="mt-1 block text-xs text-ink/55">
              Matches the group names on{" "}
              <Link className="underline" to="/users">
                Users
              </Link>
              , so PEAP/EAP-TLS logins in that group receive the same attributes.
            </span>
          </label>
          <label className="flex items-center gap-2 self-start pt-6 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            Policy enabled
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm">
            <span className="flex items-center gap-2">
              Only at these times
              <InfoTip label="What Login-Time does">
                FreeRADIUS <code>Login-Time</code> is a check item, not a reply attribute.
                If the clock is outside this window the request is rejected even when the MAC
                or user is known. Leave as “Any time” for a 24×7 lab. Overnight windows
                (18:00–08:00) wrap midnight, which is how night-shift policies are written.
              </InfoTip>
            </span>
            <select
              className="ui-input mt-1"
              value={loginTimePreset}
              onChange={(e) => setLoginTimePreset(e.target.value)}
            >
              {LOGIN_TIME_PRESETS.map((preset) => (
                <option key={preset.value || "any"} value={preset.value}>
                  {preset.label}
                </option>
              ))}
              <option value="custom">Custom Login-Time…</option>
            </select>
            {loginTimePreset === "custom" && (
              <input
                className="ui-input mt-2 font-mono"
                value={loginTimeCustom}
                onChange={(e) => setLoginTimeCustom(e.target.value)}
                placeholder="Wk0800-1700"
              />
            )}
            {isAdvanced && (
              <span className="mt-1 block text-xs text-ink/55">
                Written to <code>radcheck</code>/<code>radgroupcheck</code> as{" "}
                <code>Login-Time == …</code>.
              </span>
            )}
          </label>
          <label className="block text-sm">
            <span className="flex items-center gap-2">
              Only from this NAS
              <InfoTip label="What NAS-IP-Address does">
                The NAS puts its own address in <code>NAS-IP-Address</code> on the
                Access-Request. Restricting the policy to one address is how you say “this VLAN
                only on this switch”. Leave blank to answer any registered client. In Compose,
                Auth Test sends the backend container’s address.
              </InfoTip>
            </span>
            <select
              className="ui-input mt-1"
              value={nasIp}
              onChange={(e) => setNasIp(e.target.value)}
            >
              <option value="">Any NAS</option>
              {clients
                .filter((client) => client.enabled)
                .map((client) => (
                  <option key={client.id} value={client.ip_address}>
                    {client.name} ({client.ip_address})
                  </option>
                ))}
            </select>
            {isAdvanced && (
              <input
                className="ui-input mt-2 font-mono"
                value={nasIp}
                onChange={(e) => setNasIp(e.target.value)}
                placeholder="10.0.0.1"
              />
            )}
          </label>
        </div>

        {isAdvanced && (
          <div className="border border-ink/10 bg-mist/30 p-4">
            <h3 className="text-sm font-semibold">Raw reply attributes</h3>
            <p className="mt-1 text-xs text-ink/60">
              Written verbatim to <code>radreply</code>/<code>radgroupreply</code> with the{" "}
              <code>=</code> operator. An entry here overrides the VLAN/role fields above if it
              uses the same attribute name.
            </p>
            <div className="mt-3 space-y-2">
              {rows.map((row, index) => (
                <div key={index} className="flex flex-wrap items-center gap-2">
                  <input
                    className="ui-input w-64 font-mono text-xs"
                    list="radius-attribute-names"
                    value={row.name}
                    placeholder="Session-Timeout"
                    onChange={(e) =>
                      setRows((prev) =>
                        prev.map((r, i) => (i === index ? { ...r, name: e.target.value } : r)),
                      )
                    }
                  />
                  <span className="font-mono text-xs text-ink/50">=</span>
                  <input
                    className="ui-input w-56 font-mono text-xs"
                    value={row.value}
                    placeholder="3600"
                    onChange={(e) =>
                      setRows((prev) =>
                        prev.map((r, i) => (i === index ? { ...r, value: e.target.value } : r)),
                      )
                    }
                  />
                  <button
                    type="button"
                    className="ui-btn-ghost px-2 py-1 text-xs text-fail"
                    onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <datalist id="radius-attribute-names">
                {catalog.map((entry) => (
                  <option key={entry.name} value={entry.name} />
                ))}
              </datalist>
              <button
                type="button"
                className="ui-btn-ghost px-2 py-1 text-xs"
                onClick={() => setRows((prev) => [...prev, { name: "", value: "" }])}
              >
                Add attribute
              </button>
            </div>

            <details className="mt-4 text-xs text-ink/70">
              <summary className="cursor-pointer">Common RADIUS reply attributes</summary>
              <ul className="mt-2 space-y-2">
                {catalog.map((entry) => (
                  <li key={entry.name}>
                    <span className="font-mono text-ink">{entry.name}</span>{" "}
                    <span className="text-ink/50">e.g. {entry.example}</span>
                    <p className="text-ink/60">{entry.description}</p>
                  </li>
                ))}
              </ul>
            </details>
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          <button type="submit" className="ui-btn-primary">
            {editingId ? "Save policy" : "Create policy"}
          </button>
          {editingId && (
            <button type="button" className="ui-btn-ghost" onClick={resetForm}>
              Cancel
            </button>
          )}
        </div>
      </form>

      <section className="overflow-x-auto ui-panel">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-ink/10 bg-mist/40">
            <tr>
              <th className="px-4 py-3">Policy</th>
              <th className="px-4 py-3">Returns</th>
              <th className="px-4 py-3">User group</th>
              <th className="px-4 py-3">Endpoints</th>
              <th className="px-4 py-3">Enabled</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((policy) => (
              <tr key={policy.id} className="border-b border-ink/5">
                <td className="px-4 py-3 font-medium">{policy.name}</td>
                <td className="px-4 py-3">
                  {isAdvanced ? (
                    <ul className="space-y-0.5 font-mono text-xs">
                      {policy.rendered_attributes.map((attr) => (
                        <li key={attr.name}>
                          {attr.name} {attr.op} {attr.value}
                        </li>
                      ))}
                      {policy.rendered_check_items?.map((item) => (
                        <li key={item.name} className="text-ink/70">
                          {item.name} {item.op} {item.value}
                        </li>
                      ))}
                      {policy.rendered_attributes.length === 0 &&
                        !policy.rendered_check_items?.length && (
                          <li className="text-ink/50">no attributes</li>
                        )}
                    </ul>
                  ) : (
                    policy.summary || "—"
                  )}
                </td>
                <td className="px-4 py-3">{policy.group_name || "—"}</td>
                <td className="px-4 py-3">{policy.endpoint_count}</td>
                <td className={`px-4 py-3 ${policy.enabled ? "" : "text-fail"}`}>
                  {policy.enabled ? "yes" : "no"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="ui-btn-ghost px-2 py-1 text-xs"
                      onClick={() => startEdit(policy)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="ui-btn-ghost px-2 py-1 text-xs text-fail"
                      onClick={() => onDelete(policy)}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {policies.length === 0 && (
              <tr>
                <td className="px-4 py-6 text-ink/50" colSpan={6}>
                  No policies yet. Create one above, then attach it to an endpoint on{" "}
                  <Link className="underline" to="/endpoints">
                    Endpoints
                  </Link>
                  .
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
