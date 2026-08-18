import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  apiDownload,
  apiFetch,
  type FreeRadiusSyncResponse,
  type Lab,
  type RadiusUser,
} from "../api/client";
import { useMode } from "../modes/ModeContext";

type GeneratedCredential = {
  username: string;
  password: string;
  first_name?: string | null;
  last_name?: string | null;
  department?: string | null;
  groups?: string[];
};

type GenerateResponse = {
  created: number;
  users: RadiusUser[];
  credentials: GeneratedCredential[];
};

type ImportResponse = {
  created: number;
  skipped: number;
  errors: string[];
};

type CredentialView = "table" | "list" | "csv";

const USERNAME_STYLES = [
  { value: "numbered", label: "user001, user002…" },
  { value: "first_last", label: "first.last1" },
  { value: "flast", label: "flast1 (jsmith)" },
  { value: "emailish", label: "first.last1@lab.local" },
] as const;

export function UsersPage() {
  const { isAdvanced } = useMode();
  const [searchParams] = useSearchParams();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labId, setLabId] = useState("");
  const [users, setUsers] = useState<RadiusUser[]>([]);
  const [filter, setFilter] = useState(() => searchParams.get("q") || "");

  // Create form
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [department, setDepartment] = useState("");
  const [groupsText, setGroupsText] = useState("lab");

  // Generator
  const [count, setCount] = useState(10);
  const [usernameStyle, setUsernameStyle] = useState("first_last");
  const [prefix, setPrefix] = useState("user");
  const [includeFirstName, setIncludeFirstName] = useState(true);
  const [includeLastName, setIncludeLastName] = useState(true);
  const [includeDepartment, setIncludeDepartment] = useState(true);
  const [includeGroups, setIncludeGroups] = useState(true);
  const [genDepartment, setGenDepartment] = useState("Engineering");
  const [genGroupsText, setGenGroupsText] = useState("students");
  const [passwordStyle, setPasswordStyle] = useState<"easy" | "random">("easy");
  const [passwordLength, setPasswordLength] = useState(8);
  const [generated, setGenerated] = useState<GeneratedCredential[]>([]);
  const [credentialView, setCredentialView] = useState<CredentialView>("table");

  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [importBusy, setImportBusy] = useState(false);

  // Inline edit — username stays locked (it is the RADIUS User-Name / radcheck key).
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editFirstName, setEditFirstName] = useState("");
  const [editLastName, setEditLastName] = useState("");
  const [editDepartment, setEditDepartment] = useState("");
  const [editGroupsText, setEditGroupsText] = useState("");
  const [editStatus, setEditStatus] = useState("active");
  const [editPassword, setEditPassword] = useState("");

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

  const filteredUsers = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) => {
      const hay = [
        u.username,
        u.first_name,
        u.last_name,
        u.department,
        ...(u.groups || []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [users, filter]);

  function parseGroups(text: string): string[] {
    return text
      .split(/[,;]/)
      .map((g) => g.trim())
      .filter(Boolean);
  }

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
          first_name: firstName || null,
          last_name: lastName || null,
          department: department || null,
          groups: parseGroups(groupsText),
        }),
      });
      setUsername("");
      setPassword("");
      setFirstName("");
      setLastName("");
      setDepartment("");
      setStatus("User created and synced to FreeRADIUS (radcheck NT-Password).");
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
          username_style: usernameStyle,
          prefix,
          include_first_name: includeFirstName,
          include_last_name: includeLastName,
          include_department: includeDepartment,
          include_groups: includeGroups,
          department: includeDepartment ? genDepartment || null : null,
          groups: includeGroups ? parseGroups(genGroupsText) : [],
          password_style: passwordStyle,
          password_length: passwordLength,
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

  async function downloadTemplate() {
    setError(null);
    try {
      await apiDownload("/users/import/template", "users-import-template.csv");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Template download failed");
    }
  }

  async function onImportFile(file: File | null) {
    if (!file || !labId) return;
    setImportBusy(true);
    setError(null);
    setStatus(null);
    try {
      const token = localStorage.getItem("dot1x_token");
      const form = new FormData();
      form.append("file", file);
      const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";
      const res = await fetch(`${API_BASE}/users/import?lab_id=${labId}`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: form,
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const data = await res.json();
          detail = data.detail || detail;
        } catch {
          /* ignore */
        }
        throw new Error(typeof detail === "string" ? detail : "Import failed");
      }
      const data = (await res.json()) as ImportResponse;
      const errNote = data.errors.length ? ` (${data.errors.length} row errors)` : "";
      setStatus(
        `Import: ${data.created} created, ${data.skipped} skipped (already exist)${errNote}.`,
      );
      if (data.errors.length) {
        setError(data.errors.slice(0, 5).join("; "));
      }
      await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImportBusy(false);
    }
  }

  function copyCredentials() {
    const text = generated
      .map((c) => {
        const name = [c.first_name, c.last_name].filter(Boolean).join(" ");
        const dept = c.department ? ` (${c.department})` : "";
        return `${c.username} / ${c.password}${name ? ` — ${name}${dept}` : ""}`;
      })
      .join("\n");
    navigator.clipboard.writeText(text).then(
      () => setStatus("Credentials copied to clipboard."),
      () => setError("Could not copy to clipboard"),
    );
  }

  function credentialsAsCsv(): string {
    const header = "username,password,first_name,last_name,department,groups";
    const rows = generated.map((c) =>
      [
        c.username,
        c.password,
        c.first_name || "",
        c.last_name || "",
        c.department || "",
        (c.groups || []).join(";"),
      ]
        .map((v) => `"${String(v).replace(/"/g, '""')}"`)
        .join(","),
    );
    return [header, ...rows].join("\n");
  }

  function selectAllProfileFields(on: boolean) {
    setIncludeFirstName(on);
    setIncludeLastName(on);
    setIncludeDepartment(on);
    setIncludeGroups(on);
  }

  function startEdit(user: RadiusUser) {
    setEditingId(user.id);
    setEditFirstName(user.first_name || "");
    setEditLastName(user.last_name || "");
    setEditDepartment(user.department || "");
    setEditGroupsText((user.groups || []).join(", "));
    setEditStatus(user.status);
    setEditPassword("");
    setStatus(null);
    setError(null);
  }

  async function saveEdit(user: RadiusUser) {
    setError(null);
    setStatus(null);
    try {
      const body: Record<string, unknown> = {
        first_name: editFirstName,
        last_name: editLastName,
        department: editDepartment,
        groups: parseGroups(editGroupsText),
        status: editStatus,
      };
      if (editPassword) body.password = editPassword;
      await apiFetch(`/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setEditingId(null);
      setEditPassword("");
      setStatus(
        editPassword
          ? `${user.username} updated (password reset) and re-synced to FreeRADIUS.`
          : `${user.username} updated and re-synced to FreeRADIUS.`,
      );
      if (labId) await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function toggleStatus(user: RadiusUser) {
    setError(null);
    setStatus(null);
    const enable = user.status !== "active";
    try {
      await apiFetch(`/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: enable ? "active" : "disabled" }),
      });
      setStatus(
        enable
          ? `${user.username} enabled — NT-Password restored in FreeRADIUS.`
          : `${user.username} disabled — NT-Password removed from FreeRADIUS, so PEAP now rejects.`,
      );
      if (labId) await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function onDelete(user: RadiusUser) {
    setError(null);
    setStatus(null);
    try {
      await apiFetch(`/users/${user.id}`, { method: "DELETE" });
      if (editingId === user.id) setEditingId(null);
      setStatus(`${user.username} deleted and removed from FreeRADIUS.`);
      if (labId) await refresh(labId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="page-enter space-y-8">
      <section>
        <h1 className="font-display text-3xl font-bold">Users</h1>
        <p className="mt-1 text-ink/70">
          Local RADIUS identities for PEAP labs. Create, generate, or import — each syncs
          NT-Password into FreeRADIUS SQL immediately. Edit a row to reset a password, change
          groups, or disable the user.
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
              setEditingId(null);
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
            placeholder="name, dept, group…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </label>
      </div>

      <section className="grid gap-6 xl:grid-cols-2">
        <form onSubmit={onCreate} className="ui-panel p-5">
          <h2 className="font-semibold">Create user</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              Username
              <input
                className="ui-input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </label>
            <label className="block text-sm">
              Password
              <input
                type="text"
                className="ui-input font-mono"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="e.g. apple123"
              />
            </label>
            <label className="block text-sm">
              First name
              <input
                className="ui-input"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              Last name
              <input
                className="ui-input"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              Department
              <input
                className="ui-input"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              Groups
              <input
                className="ui-input"
                value={groupsText}
                onChange={(e) => setGroupsText(e.target.value)}
                placeholder="students, staff"
              />
            </label>
          </div>
          <button type="submit" className="mt-4 ui-btn-primary">
            Create
          </button>
        </form>

        <div className="ui-panel p-5">
          <h2 className="font-semibold">Generate test users</h2>
          <p className="mt-1 text-sm text-ink/60">
            Select what to configure, then generate demo identities with lab-friendly passwords.
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
            <span className="font-medium">Select all that you want to configure</span>
            <button
              type="button"
              className="ui-btn-ghost px-2 py-1 text-xs"
              onClick={() => selectAllProfileFields(true)}
            >
              Select all
            </button>
            <button
              type="button"
              className="ui-btn-ghost px-2 py-1 text-xs"
              onClick={() => selectAllProfileFields(false)}
            >
              Clear
            </button>
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeFirstName}
                onChange={(e) => setIncludeFirstName(e.target.checked)}
              />
              First name
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeLastName}
                onChange={(e) => setIncludeLastName(e.target.checked)}
              />
              Last name
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeDepartment}
                onChange={(e) => setIncludeDepartment(e.target.checked)}
              />
              Department
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeGroups}
                onChange={(e) => setIncludeGroups(e.target.checked)}
              />
              Groups
            </label>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              Count
              <input
                type="number"
                min={1}
                max={500}
                className="ui-input w-full"
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
              />
            </label>
            <label className="block text-sm">
              Username style
              <select
                className="ui-input"
                value={usernameStyle}
                onChange={(e) => setUsernameStyle(e.target.value)}
              >
                {USERNAME_STYLES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            {usernameStyle === "numbered" && (
              <label className="block text-sm">
                Prefix
                <input
                  className="ui-input"
                  value={prefix}
                  onChange={(e) => setPrefix(e.target.value)}
                />
              </label>
            )}
            {includeDepartment && (
              <label className="block text-sm">
                Department value
                <input
                  className="ui-input"
                  value={genDepartment}
                  onChange={(e) => setGenDepartment(e.target.value)}
                />
              </label>
            )}
            {includeGroups && (
              <label className="block text-sm">
                Groups value
                <input
                  className="ui-input"
                  value={genGroupsText}
                  onChange={(e) => setGenGroupsText(e.target.value)}
                  placeholder="students"
                />
              </label>
            )}
            <label className="block text-sm">
              Password style
              <select
                className="ui-input"
                value={passwordStyle}
                onChange={(e) => setPasswordStyle(e.target.value as "easy" | "random")}
              >
                <option value="easy">Easy (word + digits, e.g. maple482)</option>
                <option value="random">Random alphanumeric</option>
              </select>
            </label>
            {passwordStyle === "random" && (
              <label className="block text-sm">
                Password length
                <input
                  type="number"
                  min={6}
                  max={64}
                  className="ui-input"
                  value={passwordLength}
                  onChange={(e) => setPasswordLength(Number(e.target.value))}
                />
              </label>
            )}
          </div>

          <button type="button" onClick={onGenerate} className="mt-4 ui-btn-signal">
            Generate {count} users
          </button>

          {generated.length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-ink/80">
                <span className="font-semibold">Save these passwords now.</span> They are shown
                only once. For security only password hashes are stored, so they can't be looked
                up later (the users list below has no password column). The users are already
                created and synced to FreeRADIUS.
              </p>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium">How do you want to see them?</span>
                {(
                  [
                    ["table", "Table"],
                    ["list", "List"],
                    ["csv", "CSV"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={
                      credentialView === value
                        ? "ui-btn-primary px-2 py-1 text-xs"
                        : "ui-btn-ghost px-2 py-1 text-xs"
                    }
                    onClick={() => setCredentialView(value)}
                  >
                    {label}
                  </button>
                ))}
                <button
                  type="button"
                  className="ui-btn-ghost px-2 py-1 text-xs"
                  onClick={copyCredentials}
                >
                  Copy
                </button>
              </div>

              {credentialView === "table" && (
                <div className="max-h-56 overflow-auto border border-ink/10">
                  <table className="min-w-full text-left text-xs">
                    <thead className="sticky top-0 bg-mist/80">
                      <tr>
                        <th className="px-2 py-1">Username</th>
                        <th className="px-2 py-1">Password</th>
                        <th className="px-2 py-1">Name</th>
                        <th className="px-2 py-1">Dept</th>
                      </tr>
                    </thead>
                    <tbody>
                      {generated.map((cred) => (
                        <tr key={cred.username} className="border-t border-ink/5">
                          <td className="px-2 py-1 font-mono">{cred.username}</td>
                          <td className="px-2 py-1 font-mono">{cred.password}</td>
                          <td className="px-2 py-1">
                            {[cred.first_name, cred.last_name].filter(Boolean).join(" ") || "—"}
                          </td>
                          <td className="px-2 py-1">{cred.department || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {credentialView === "list" && (
                <div className="max-h-56 overflow-auto border border-ink/10 bg-mist/60 p-3 font-mono text-xs">
                  {generated.map((cred) => (
                    <div key={cred.username}>
                      {cred.username} / {cred.password}
                      {(cred.first_name || cred.last_name) &&
                        ` — ${[cred.first_name, cred.last_name].filter(Boolean).join(" ")}`}
                      {cred.department && ` (${cred.department})`}
                    </div>
                  ))}
                </div>
              )}
              {credentialView === "csv" && (
                <pre className="max-h-56 overflow-auto border border-ink/10 bg-mist/60 p-3 font-mono text-xs whitespace-pre-wrap">
                  {credentialsAsCsv()}
                </pre>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="ui-panel p-5">
        <h2 className="font-semibold">Import from CSV</h2>
        <p className="mt-1 text-sm text-ink/60">
          Download a template, fill in users, then upload. Existing usernames are skipped.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button type="button" className="ui-btn-ghost px-3 py-2 text-sm" onClick={downloadTemplate}>
            Download template
          </button>
          <label className="ui-btn-primary cursor-pointer px-3 py-2 text-sm">
            {importBusy ? "Importing…" : "Upload CSV"}
            <input
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              disabled={importBusy || !labId}
              onChange={(e) => {
                const f = e.target.files?.[0] || null;
                void onImportFile(f);
                e.target.value = "";
              }}
            />
          </label>
        </div>
      </section>

      <section className="overflow-x-auto ui-panel">
        <p className="border-b border-ink/10 px-4 py-2 text-xs text-ink/55">
          Passwords aren't shown here — only hashes are stored. Capture generated passwords from
          the panel above when you create users, or reset a password by editing the user.
          Username is the RADIUS User-Name and cannot be renamed; delete and recreate to change
          it. Disabling a user removes their NT-Password from FreeRADIUS, so the next PEAP
          attempt rejects.
        </p>
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-ink/10 bg-mist/40">
            <tr>
              <th className="px-4 py-3">Username</th>
              <th className="px-4 py-3">First name</th>
              <th className="px-4 py-3">Last name</th>
              <th className="px-4 py-3">Department</th>
              <th className="px-4 py-3">Groups</th>
              <th className="px-4 py-3">Status</th>
              {isAdvanced && <th className="px-4 py-3">ID</th>}
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.map((user) =>
              editingId === user.id ? (
                <tr key={user.id} className="border-b border-ink/5 bg-mist/30 align-top">
                  <td className="px-4 py-3">
                    <p className="font-medium">{user.username}</p>
                    <label className="mt-2 block text-xs text-ink/60">
                      New password
                      <input
                        type="text"
                        className="ui-input mt-1 font-mono"
                        value={editPassword}
                        onChange={(e) => setEditPassword(e.target.value)}
                        placeholder="leave blank to keep"
                        autoComplete="new-password"
                      />
                    </label>
                  </td>
                  <td className="px-4 py-3">
                    <input
                      className="ui-input"
                      value={editFirstName}
                      onChange={(e) => setEditFirstName(e.target.value)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      className="ui-input"
                      value={editLastName}
                      onChange={(e) => setEditLastName(e.target.value)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      className="ui-input"
                      value={editDepartment}
                      onChange={(e) => setEditDepartment(e.target.value)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      className="ui-input"
                      value={editGroupsText}
                      onChange={(e) => setEditGroupsText(e.target.value)}
                      placeholder="students, staff"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <select
                      className="ui-input"
                      value={editStatus}
                      onChange={(e) => setEditStatus(e.target.value)}
                    >
                      <option value="active">active</option>
                      <option value="disabled">disabled</option>
                      {user.status === "expired" && <option value="expired">expired</option>}
                    </select>
                  </td>
                  {isAdvanced && (
                    <td className="px-4 py-3 font-mono text-xs text-ink/50">{user.id}</td>
                  )}
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="ui-btn-primary px-2 py-1 text-xs"
                        onClick={() => saveEdit(user)}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="ui-btn-ghost px-2 py-1 text-xs"
                        onClick={() => {
                          setEditingId(null);
                          setEditPassword("");
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={user.id} className="border-b border-ink/5">
                  <td className="px-4 py-3 font-medium">{user.username}</td>
                  <td className="px-4 py-3">{user.first_name || "—"}</td>
                  <td className="px-4 py-3">{user.last_name || "—"}</td>
                  <td className="px-4 py-3">{user.department || "—"}</td>
                  <td className="px-4 py-3">{(user.groups || []).join(", ") || "—"}</td>
                  <td
                    className={`px-4 py-3 ${user.status === "active" ? "" : "text-fail"}`}
                  >
                    {user.status}
                  </td>
                  {isAdvanced && (
                    <td className="px-4 py-3 font-mono text-xs text-ink/50">{user.id}</td>
                  )}
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="ui-btn-ghost px-2 py-1 text-xs"
                        onClick={() => startEdit(user)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="ui-btn-ghost px-2 py-1 text-xs"
                        onClick={() => toggleStatus(user)}
                      >
                        {user.status === "active" ? "Disable" : "Enable"}
                      </button>
                      <button
                        type="button"
                        className="ui-btn-ghost px-2 py-1 text-xs text-fail"
                        onClick={() => onDelete(user)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ),
            )}
            {filteredUsers.length === 0 && (
              <tr>
                <td className="px-4 py-6 text-ink/50" colSpan={isAdvanced ? 8 : 7}>
                  No users yet — create, generate, or import to get started.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
