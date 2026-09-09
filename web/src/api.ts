import type {
  AlignmentBaseline, ChangeSet, DesignVersion, Finding, ModelResponse,
  ObservationCoordinate, OverviewResponse, Project, Proposal,
} from "./types";

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

export async function listProjects(): Promise<Project[]> {
  return (await call<{ projects: Project[] }>("/api/v1/projects")).projects;
}

export async function loadWorkspace(projectId: string, designVersion?: number) {
  const common = new URLSearchParams({ project_id: projectId });
  const modelQuery = new URLSearchParams(common);
  if (designVersion !== undefined) modelQuery.set("design_version", String(designVersion));
  const [model, overview, versions, baseline, findings, proposals, changeSets] = await Promise.all([
    call<ModelResponse>(`/api/v1/model?${modelQuery}`),
    call<OverviewResponse>(`/api/v1/overview?${common}`),
    call<{ versions: DesignVersion[] }>(`/api/v1/design-versions?${common}`),
    call<AlignmentBaseline>(`/api/v1/alignment-baseline?${common}`),
    call<{ findings: Finding[] }>(`/api/v1/findings?${common}`),
    call<{ proposals: Proposal[] }>(`/api/v1/proposals?${common}`),
    call<{ change_sets: ChangeSet[] }>(`/api/v1/change-sets?${common}`),
  ]);
  return {
    model, overview, versions: versions.versions, baseline,
    findings: findings.findings, proposals: proposals.proposals, changeSets: changeSets.change_sets,
  };
}

export function fetchObservation(projectId: string): Promise<ObservationCoordinate> {
  return call(`/api/v1/observation?${new URLSearchParams({ project_id: projectId })}`);
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
