const BASE = "/api";

// Every request carries this header; the server refuses changes without it, which keeps
// other websites open in her browser from posting to AAGAM.
const HEADERS = { "X-AAGAM": "1" };

export class ApiError extends Error {
  constructor(message: string, readonly status = 0) {
    super(message);
  }
}

/** True when the server has no such API: an older AAGAM, so the part of the window that needs it stays hidden. */
export const missing = (e: unknown) => e instanceof ApiError && (e.status === 404 || e.status === 405);

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { ...init, headers: { ...HEADERS, ...init.headers } });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(message || `HTTP ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
  headers: { "Content-Type": "application/json" },
});

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown = {}) => request<T>(path, json("POST", body)),
  put: <T>(path: string, body: unknown) => request<T>(path, json("PUT", body)),
  patch: <T>(path: string, body: unknown) => request<T>(path, json("PATCH", body)),
  form: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

/** The server's health answer, without the change header or error handling: used while AAGAM restarts after an update. */
export async function health(): Promise<{ ok: boolean; version: string; commit?: string | null } | null> {
  try {
    const res = await fetch(`${BASE}/health`, { cache: "no-store" });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "" && v !== false) q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}
