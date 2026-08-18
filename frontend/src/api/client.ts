const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function getToken(): string | null {
  return localStorage.getItem("dot1x_token");
}

/** One entry of a FastAPI 422 body: `{"detail": [{"loc": [...], "msg": "..."}]}`. */
type ValidationIssue = {
  loc?: (string | number)[];
  msg?: string;
};

/** "body" → "name" is noise; keep the field path a reader would recognize. */
const LOCATION_PREFIXES = ["body", "query", "path", "header", "cookie"];

function issueText(issue: ValidationIssue): string {
  const message = issue.msg || "is not valid";
  const field = (issue.loc || [])
    .filter((part, index) => !(index === 0 && LOCATION_PREFIXES.includes(String(part))))
    .join(".");
  return field ? `${field}: ${message}` : message;
}

/**
 * Turn an error body into something a person can read. FastAPI answers a
 * validation failure with a list of Pydantic issue objects rather than a string,
 * and dumping that to JSON puts `[{"type":"string_too_short",…}]` on screen.
 */
function readableDetail(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail ?? body;
  if (typeof detail === "string") return detail.trim() || null;
  if (Array.isArray(detail)) {
    const parts = detail.map((issue) => issueText(issue as ValidationIssue)).filter(Boolean);
    return parts.length ? parts.join("; ") : null;
  }
  if (detail && typeof detail === "object") {
    const issue = detail as ValidationIssue;
    if (issue.msg) return issueText(issue);
  }
  return null;
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("dot1x_token", token);
  else localStorage.removeItem("dot1x_token");
}

/** Clear the expired/invalid session and send the SPA back to the login page. */
function handleUnauthorized() {
  setToken(null);
  if (window.location.pathname !== "/login") {
    window.location.assign("/login");
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    if (res.status === 401) {
      handleUnauthorized();
      throw new ApiError(401, "Session expired — please sign in again");
    }
    let detail = res.statusText;
    try {
      detail = readableDetail(await res.json()) || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Authenticated binary/download helper (PEM, P12, ZIP). */
export async function apiDownload(path: string, filename: string): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) {
    if (res.status === 401) {
      handleUnauthorized();
      throw new ApiError(401, "Session expired — please sign in again");
    }
    let detail = res.statusText;
    try {
      detail = readableDetail(await res.json()) || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail || "Download failed");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function login(username: string, password: string): Promise<string> {
  const body = new URLSearchParams();
  body.set("username", username);
  body.set("password", password);
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) throw new ApiError(res.status, "Login failed");
  const data = (await res.json()) as { access_token: string };
  setToken(data.access_token);
  return data.access_token;
}

export type WirelessSecurity = "wpa2_enterprise" | "wpa3_enterprise";

/** The SSID a lab's guided wireless flow set up, stored in `Lab.settings`. */
export type WirelessProfile = {
  ssid: string;
  security: WirelessSecurity;
  vlan: number | null;
  user_group: string | null;
};

export type Lab = {
  id: string;
  name: string;
  description: string | null;
  settings: Record<string, unknown>;
};

export type RadiusUser = {
  id: string;
  lab_id: string;
  username: string;
  first_name?: string | null;
  last_name?: string | null;
  department?: string | null;
  groups: string[];
  status: string;
  expires_at: string | null;
};

export type RadiusClient = {
  id: string;
  lab_id: string;
  name: string;
  ip_address: string;
  shared_secret: string;
  device_type: string | null;
  enabled: boolean;
};

export type AuthEvent = {
  id: string;
  lab_id: string | null;
  timestamp: string;
  identity: string | null;
  method: string;
  result: string;
  failure_reason: string | null;
  failure_summary: string | null;
  failure_hint: string | null;
  returned_attributes: Record<string, string>;
  nas_ip: string | null;
  raw_ref: string | null;
};

export type Endpoint = {
  id: string;
  lab_id: string;
  mac_address: string;
  description: string | null;
  device_type: string | null;
  authz_policy_id: string | null;
  authz_policy_name: string | null;
  enabled: boolean;
  created_at: string;
  radius_usernames: string[];
};

export type RenderedReplyAttribute = {
  name: string;
  op: string;
  value: string;
};

export type PolicyConditions = {
  login_time?: string | null;
  nas_ip?: string | null;
};

export type AuthzPolicy = {
  id: string;
  lab_id: string;
  name: string;
  vlan: number | null;
  role: string | null;
  group_name: string | null;
  reply_attributes: Record<string, string>;
  conditions: PolicyConditions;
  enabled: boolean;
  created_at: string;
  rendered_attributes: RenderedReplyAttribute[];
  rendered_check_items: RenderedReplyAttribute[];
  endpoint_count: number;
  summary: string;
};

export type AttributeCatalogEntry = {
  name: string;
  label: string;
  example: string;
  description: string;
};

export type Certificate = {
  id: string;
  lab_id: string;
  subject: string;
  issuer: string | null;
  serial: string | null;
  cert_type: string;
  status: string;
  not_before: string | null;
  not_after: string | null;
  created_at: string;
  identity: string | null;
  download_bundle: string | null;
  download_p12: string | null;
};

export type CertificateAuthorityInfo = {
  id: string;
  name: string;
  subject: string;
  adapter: string;
  created_at: string;
};

export type CertificateInventory = {
  authority: CertificateAuthorityInfo | null;
  crl_available: boolean;
  crl_enforced: boolean;
  has_intermediate: boolean;
  certificates: Certificate[];
};

export type HealthResponse = {
  status: string;
  components: { name: string; status: string; detail?: string }[];
};

export type AuthTestContext = {
  radius_host: string;
  radius_port: number;
  shared_secret_hint: string;
  note: string;
};

export type AuthTestResponse = {
  method: string;
  identity: string;
  result: string;
  expected_reject: boolean;
  matched_expectation: boolean;
  failure_reason: string | null;
  eapol_exit_code: number;
  eapol_output: string;
  radius: AuthTestContext;
  event: AuthEvent | null;
  returned_attributes: Record<string, string>;
};

export type SessionActionKind = "disconnect" | "coa";

export type SessionActionTarget = {
  id: string | null;
  name: string;
  host: string;
  port: number;
  kind: "sink" | "nas" | string;
  device_type: string | null;
  enabled: boolean;
  note: string | null;
};

export type SessionActionTargets = {
  sink: SessionActionTarget;
  clients: SessionActionTarget[];
  sink_listening: boolean;
};

export type SessionActionResponse = {
  action: SessionActionKind;
  result: "ack" | "nak" | "timeout" | "error" | string;
  packet_type: string | null;
  identity: string;
  calling_station_id: string;
  nas_ip: string;
  nas_port: number;
  nas_name: string;
  used_lab_sink: boolean;
  shared_secret_hint: string;
  attributes_sent: Record<string, string>;
  attributes_returned: Record<string, string>;
  output: string;
  failure_reason: string | null;
  last_seen_nas_ip: string | null;
  policy_name: string | null;
  note: string;
};

export type FreeRadiusSyncResponse = {
  users_synced: number;
  clients_synced: number;
  endpoints_synced: number;
  policies_synced: number;
  reload_requested: boolean;
  lab_ids: string[];
  detail: string;
};

export type RadiusTargetCandidate = {
  ip: string;
  interface: string | null;
  source: string;
  likely_docker: boolean;
  is_private: boolean;
};

export type RadiusTarget = {
  lab_id: string | null;
  mode: "auto" | "manual";
  advertise_ip: string | null;
  effective_ip: string | null;
  auth_port: number;
  acct_port: number;
  shared_secret_hint: string;
  lab_shared_secret: string;
  candidates: RadiusTargetCandidate[];
  nas_instructions: string;
  warning: string | null;
  auto_source: string | null;
};
