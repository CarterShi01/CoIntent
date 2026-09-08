import type { Finding, ModelResponse, OverviewResponse } from "./types";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}${body ? ` — ${body}` : ""}`);
  }
  return response.json() as Promise<T>;
}

export async function loadWorkspace(projectId = "idea-factory") {
  const query = new URLSearchParams({ project_id: projectId });
  const [model, overview, findings] = await Promise.all([
    get<ModelResponse>(`/api/v1/model?${query}`),
    get<OverviewResponse>(`/api/v1/overview?${query}`),
    get<{ findings: Finding[] }>(`/api/v1/findings?${query}`),
  ]);
  return { model, overview, findings: findings.findings };
}
