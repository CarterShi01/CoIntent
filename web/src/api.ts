import type {
  AlignmentBaseline, ChangeSet, DesignVersion, Finding, ModelResponse,
  ObservationCoordinate, ObservationExpansionRequest, OverviewResponse, Project, Proposal,
  DesignReview, ImplementationChangeBundle, TargetDesignOperation, TargetDesignView,
  VerificationDecision, VerificationReport,
  ProjectState, UnderstandingRefreshJob, UaSemanticSubject, UaViewerSession,
  ImplementationContextResult, StructureDesignDiff,
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

export function fetchObservation(projectId: string, observedRevisionId?: string): Promise<ObservationCoordinate> {
  const query = new URLSearchParams({ project_id: projectId });
  if (observedRevisionId) query.set("observed_revision_id", observedRevisionId);
  return call(`/api/v1/observation?${query}`);
}

export function fetchProjectState(projectId: string): Promise<ProjectState> {
  return call(`/api/v1/project-state?${new URLSearchParams({ project_id: projectId })}`);
}

export function inspectUnderstandingRefresh(jobId: string): Promise<UnderstandingRefreshJob> {
  return call(`/api/v1/understanding-refresh?${new URLSearchParams({ job_id: jobId })}`);
}

export function createUaViewerSession(
  projectId: string, observedRevisionId: string, uaSnapshotId: string,
): Promise<UaViewerSession> {
  return call(`/api/projects/${encodeURIComponent(projectId)}/ua-viewer-sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ observed_revision_id: observedRevisionId, ua_snapshot_id: uaSnapshotId }),
  });
}

export function fetchUaNodeSubjects(uaSnapshotId: string, nodeId: string): Promise<{ subjects: UaSemanticSubject[] }> {
  return call(`/api/v1/ua-node-subjects?${new URLSearchParams({ ua_snapshot_id: uaSnapshotId, node_id: nodeId })}`);
}

export function fetchStructureDesignDiff(
  workspaceId: string, toRevisionId?: string, fromRevisionId?: string,
): Promise<StructureDesignDiff> {
  const query = new URLSearchParams({ workspace_id: workspaceId });
  if (toRevisionId) query.set("to_revision_id", toRevisionId);
  if (fromRevisionId) query.set("from_revision_id", fromRevisionId);
  return call(`/api/v1/structure-design-diff?${query}`);
}

export function createImplementationContext(
  workspaceId: string, designRevisionId: string, expectedDiffDigest: string,
): Promise<ImplementationContextResult> {
  return call("/api/v1/implementation-contexts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: workspaceId,
      design_revision_id: designRevisionId,
      expected_diff_digest: expectedDiffDigest,
    }),
  });
}

export function requestObservationExpansion(
  projectId: string, observedRevisionId: string, nodeId: string, depth = 1,
): Promise<{ duplicate: boolean; request: ObservationExpansionRequest }> {
  return call("/api/v1/observation-expansions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      observed_revision_id: observedRevisionId,
      node_id: nodeId,
      depth,
    }),
  });
}

export function fetchTargetDesignWorkspace(
  projectId: string, workspaceId?: string, revisionId?: string,
): Promise<TargetDesignView | null> {
  const query = new URLSearchParams({ project_id: projectId });
  if (workspaceId) query.set("workspace_id", workspaceId);
  if (revisionId) query.set("revision_id", revisionId);
  return call(`/api/v1/target-design-workspace?${query}`);
}

export function createTargetDesignWorkspace(
  projectId: string, baseObservedRevisionId: string, title: string, rationale: string,
): Promise<{ workspace: TargetDesignView["workspace"]; revision: TargetDesignView["revision"] }> {
  return call("/api/v1/target-design-workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      base_observed_revision_id: baseObservedRevisionId,
      title,
      rationale,
    }),
  });
}

export function applyTargetDesignOperations(
  workspaceId: string,
  baseDesignRevisionId: string,
  operations: TargetDesignOperation[],
  rationale: string,
): Promise<unknown> {
  return call("/api/v1/target-design-operations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: workspaceId,
      base_design_revision_id: baseDesignRevisionId,
      operations,
      rationale,
    }),
  });
}

export function submitTargetDesignReview(
  workspaceId: string, acceptanceCriteria: string[],
): Promise<DesignReview> {
  return call("/api/v1/target-design-reviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace_id: workspaceId, acceptance_criteria: acceptanceCriteria }),
  });
}

export function approveTargetDesignReview(reviewId: string): Promise<{ id: string }> {
  return call("/api/v1/target-design-approvals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ review_id: reviewId }),
  });
}

export function exportImplementationBundle(workspaceId: string): Promise<ImplementationChangeBundle> {
  return call("/api/v1/implementation-exports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace_id: workspaceId }),
  });
}

export function createVerificationReport(
  workspaceId: string, observedRevisionId: string,
): Promise<VerificationReport> {
  return call("/api/v1/verifications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace_id: workspaceId, observed_revision_id: observedRevisionId }),
  });
}

export function decideVerification(
  reportId: string, decision: "converged" | "needs_revision", notes: string,
): Promise<VerificationDecision> {
  return call("/api/v1/verification-decisions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report_id: reportId, decision, notes }),
  });
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
