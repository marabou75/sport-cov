const TOKEN_KEY = "sportcov_token";
const USER_KEY = "sportcov_user";

export type AuthUser = {
  email: string;
  full_name: string;
  is_admin: boolean;
  role: "admin" | "coach";
  access_token: string;
};

export function saveAuth(user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, user.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Wrapper fetch qui gère les 401 → redirect /login
export async function apiFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const headers = { ...authHeaders(), ...(init?.headers ?? {}) };
  const res = await fetch(input, { ...init, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    clearAuth();
    window.location.href = "/login";
    return res;
  }
  return res;
}
