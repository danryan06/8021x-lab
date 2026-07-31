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

export function setToken(token: string | null) {
  if (token) localStorage.setItem("dot1x_token", token);
  else localStorage.removeItem("dot1x_token");
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
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
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
  timestamp: string;
  identity: string | null;
  method: string;
  result: string;
  failure_reason: string | null;
  nas_ip: string | null;
};

export type HealthResponse = {
  status: string;
  components: { name: string; status: string; detail?: string }[];
};
