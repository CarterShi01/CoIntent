export interface Goal {
  id: string;
  title: string;
  description: string;
  parent_id: string | null;
  status: string;
}

export interface RoleRecord {
  id: string;
  name: string;
  purpose: string;
  parent_id: string | null;
  status: string;
}

export interface Responsibility {
  id: string;
  role_id: string;
  statement: string;
  goal_ids: string[];
  inputs: string[];
  outputs: string[];
  constraints: string[];
}

export interface Relation {
  id: string;
  source_role_id: string;
  target_role_id: string;
  kind: string;
  label: string;
}

export interface TraceLink {
  id: string;
  role_id: string;
  artifact_path: string;
  kind: string;
  confidence: number;
  origin: string;
  evidence: string;
}

export interface ProjectModel {
  project_id: string;
  name: string;
  summary: string;
  status: string;
  goals: Goal[];
  roles: RoleRecord[];
  responsibilities: Responsibility[];
  relations: Relation[];
  trace_links: TraceLink[];
}

export interface ModelResponse {
  version: number;
  created_at: string;
  actor: string;
  message: string;
  model: ProjectModel;
}

export interface OverviewResponse {
  version: number;
  status: string;
  counts: {
    goals: number;
    roles: number;
    responsibilities: number;
    trace_links: number;
    open_findings: number;
    pending_proposals: number;
  };
  latest_snapshot: null | {
    id: string;
    revision: string;
    branch: string;
    dirty: boolean;
    captured_at: string;
    artifact_count: number;
    relation_count: number;
  };
}

export interface Finding {
  id: string;
  kind: string;
  severity: string;
  summary: string;
  role_ids: string[];
  artifact_paths: string[];
  status: string;
}
