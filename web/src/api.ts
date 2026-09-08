import type { Finding, ModelResponse, OverviewResponse } from "./types";

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: { Accept: "application/json", ...init.headers },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}${body ? ` — ${body}` : ""}`);
  }
  return response.json() as Promise<T>;
}

export async function loadWorkspace(projectId = "idea-factory") {
  const query = new URLSearchParams({ project_id: projectId });
  const [model, overview, findings] = await Promise.all([
    call<ModelResponse>(`/api/v1/model?${query}`),
    call<OverviewResponse>(`/api/v1/overview?${query}`),
    call<{ findings: Finding[] }>(`/api/v1/findings?${query}`),
  ]);
  return { model, overview, findings: findings.findings };
}

export interface SessionState {
  login_required: boolean;
  authed: boolean;
  user: string | null;
  bypass: boolean;
}

export function fetchSession(): Promise<SessionState> {
  return call("/api/me");
}

export function login(user: string, password: string): Promise<{ ok: true; user: string }> {
  return call("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user, password }),
  });
}

export function logout(): Promise<{ ok: true }> {
  return call("/api/logout", { method: "POST" });
}
