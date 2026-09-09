export interface Project {
  id: string;
  name: string;
  description: string;
  repository: string;
  current_version: number;
  default_branch: string;
  language: string;
  status: string;
  created_at: string;
}

export interface SpecificationItem {
  id: string;
  name: string;
  description: string;
  parent_id: string | null;
  status: "draft" | "accepted" | "questioned" | "deferred";
  source_ids: string[];
}

export interface WorkflowNode { id: string; responsibility_id: string; note: string; }
export interface WorkflowEdge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  kind: "next" | "condition" | "parallel" | "event" | "error";
  label: string;
}
export interface Workflow { entry_node_ids: string[]; nodes: WorkflowNode[]; edges: WorkflowEdge[]; }

export interface Responsibility {
  id: string;
  name: string;
  description: string;
  data_members: string[];
  inputs: string[];
  outputs: string[];
  workflow: Workflow | null;
  status: "draft" | "accepted" | "questioned";
  source_ids: string[];
}

export interface SpecificationResponsibilityLink {
  id: string;
  specification_id: string;
  responsibility_id: string;
  kind: "realizes" | "contributes";
  confidence: number;
  evidence: string;
  source_ids: string[];
}

export interface ImplementationLink {
  id: string;
  responsibility_id: string;
  artifact_path: string;
  symbol: string;
  kind: "realizes" | "supports" | "verifies" | "stores";
  confidence: number;
  origin: "human" | "agent" | "scanner" | "runtime";
  evidence: string;
}

export interface ProjectModel {
  schema_version: "0.3";
  project_id: string;
  name: string;
  summary: string;
  status: string;
  specification_items: SpecificationItem[];
  responsibilities: Responsibility[];
  specification_responsibility_links: SpecificationResponsibilityLink[];
  implementation_links: ImplementationLink[];
}

export interface ModelResponse {
  project: Project;
  version: number;
  parent_version: number | null;
  created_at: string;
  actor: string;
  message: string;
  model: ProjectModel;
}

export interface DesignVersion { version: number; parent_version: number | null; actor: string; message: string; created_at: string; }
export interface SnapshotSummary { id: string; revision: string; branch: string; dirty: boolean; captured_at: string; artifact_count?: number; relation_count?: number; }

export interface OverviewResponse {
  project: Project;
  version: number;
  status: string;
  counts: {
    specification_items: number;
    responsibilities: number;
    workflows: number;
    leaf_responsibilities: number;
    specification_links: number;
    implementation_links: number;
    open_findings: number;
    pending_proposals: number;
  };
  latest_snapshot: SnapshotSummary | null;
}

export interface AlignmentBaseline {
  project_id: string;
  design_version: number;
  code_snapshot: null | { id: string; created_at: string; snapshot: SnapshotSummary; diff: unknown };
  mapping_revision: null | { id: string; design_version: number; snapshot_id: string; created_at: string; implementation_links: ImplementationLink[]; };
  is_current: boolean;
}

export interface Finding {
  id: string;
  kind: string;
  severity: string;
  summary: string;
  responsibility_ids: string[];
  artifact_paths: string[];
  status: string;
}

export interface SemanticChange { added: string[]; removed: string[]; changed: string[]; }
export interface Proposal {
  id: string;
  project_id: string;
  base_version: number;
  rationale: string;
  actor: string;
  status: string;
  created_at: string;
  evidence_ids: string[];
  diff: Record<string, SemanticChange | boolean>;
}

export interface ChangeSet {
  id: string;
  project_id: string;
  title: string;
  description: string;
  base_design_version: number;
  target_design_version: number | null;
  proposal_id: string | null;
  snapshot_id: string | null;
  specification_ids: string[];
  responsibility_ids: string[];
  status: string;
  resolution: string;
  created_at: string;
  updated_at: string;
}
