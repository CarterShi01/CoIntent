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

export interface ProductFunction {
  id: string;
  name: string;
  description: string;
  parent_id: string | null;
  status: string;
  priority: string;
  acceptance: string[];
  constraints: string[];
  source_ids: string[];
}

export interface RoleObject {
  id: string;
  name: string;
  purpose: string;
  parent_id: string | null;
  status: string;
  owns_knowledge: string[];
  inputs: string[];
  outputs: string[];
  constraints: string[];
  source_ids: string[];
}

export interface Responsibility {
  id: string;
  role_id: string;
  statement: string;
  function_ids: string[];
  inputs: string[];
  outputs: string[];
  constraints: string[];
  source_ids: string[];
}

export interface RoleRelation {
  id: string;
  source_role_id: string;
  target_role_id: string;
  kind: string;
  label: string;
}

export interface FunctionRoleLink {
  id: string;
  function_id: string;
  role_id: string;
  kind: "owns" | "contributes" | "governs";
  confidence: number;
  evidence: string;
  source_ids: string[];
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
  schema_version: "0.2";
  project_id: string;
  name: string;
  summary: string;
  status: string;
  product_functions: ProductFunction[];
  role_objects: RoleObject[];
  responsibilities: Responsibility[];
  role_relations: RoleRelation[];
  function_role_links: FunctionRoleLink[];
  trace_links: TraceLink[];
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

export interface DesignVersion {
  version: number;
  parent_version: number | null;
  actor: string;
  message: string;
  created_at: string;
}

export interface SnapshotSummary {
  id: string;
  revision: string;
  branch: string;
  dirty: boolean;
  captured_at: string;
  artifact_count?: number;
  relation_count?: number;
}

export interface OverviewResponse {
  project: Project;
  version: number;
  status: string;
  counts: {
    product_functions: number;
    role_objects: number;
    responsibilities: number;
    function_role_links: number;
    trace_links: number;
    open_findings: number;
    pending_proposals: number;
  };
  latest_snapshot: SnapshotSummary | null;
}

export interface AlignmentBaseline {
  project_id: string;
  design_version: number;
  code_snapshot: null | { id: string; created_at: string; snapshot: SnapshotSummary; diff: unknown };
  mapping_revision: null | {
    id: string;
    design_version: number;
    snapshot_id: string;
    created_at: string;
    trace_links: TraceLink[];
  };
  is_current: boolean;
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

export interface SemanticChange {
  added: string[];
  removed: string[];
  changed: string[];
}

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
  function_ids: string[];
  role_ids: string[];
  status: string;
  resolution: string;
  created_at: string;
  updated_at: string;
}
