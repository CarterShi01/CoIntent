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

export interface EvidenceBinding {
  ua_node_id: string;
  path: string;
  start_line: number | null;
  end_line: number | null;
  source_digest: string;
  origin: "ua_structural" | "ua_semantic";
  structural_ua_node_ids: string[];
}

export interface ClaimBinding {
  id: string;
  subject_kind: "responsibility" | "workflow_edge" | "capability";
  subject_id: string;
  predicate: "implemented_by" | "ordered_by" | "summarized_by";
  ua_node_ids: string[];
  evidence: EvidenceBinding[];
  support: "direct" | "aggregated" | "inferred";
  explanation: string;
}

export interface ObservedCapability {
  id: string;
  name: string;
  description: string;
  responsibility_id: string;
  evidence_count: number;
}

export interface ObservedRevision {
  schema_version: "cointent.observed-model/0.4";
  id: string;
  project_id: string;
  code_snapshot_id: string;
  ua_snapshot_id: string;
  parent_revision_id: string | null;
  refinement_of_node_id: string | null;
  projector_version: string;
  capabilities: ObservedCapability[];
  responsibilities: Responsibility[];
  bindings: ClaimBinding[];
  diagnostics: Array<{ kind: string; subject_id: string | null; message: string }>;
  refinement: null | {
    requested_depth: number;
    added_responsibilities: number;
    evidence_bindings: number;
    max_depth_reached: number;
    truncated: boolean;
  };
  content_digest: string;
  created_at: string;
}

export interface ObservationExpansionRequest {
  id: string;
  project_id: string;
  base_observed_revision_id: string;
  ua_snapshot_id: string;
  target_observed_node_id: string;
  target_ua_node_id: string;
  depth: number;
  evidence_scope: EvidenceBinding[];
  status: "queued" | "completed" | "atomic_at_current_evidence" | "failed";
  result_observed_revision_id: string | null;
  message: string;
  created_at: string;
  updated_at: string;
}

export interface ObservationCoordinate {
  project_id: string;
  status: "not_generated" | "current" | "stale";
  code_snapshot?: {
    id: string;
    revision: string;
    branch: string;
    dirty: boolean;
    scope: "full";
  };
  ua_snapshot?: {
    id: string;
    ua_graph_version: string;
    ua_tool_revision: string;
    coverage: {
      code_snapshot_files: number;
      ua_located_nodes: number;
      ua_unlocated_nodes: number;
      domain_nodes: number;
      evidence_backed_domain_nodes: number;
    };
  };
  observed_revision: ObservedRevision | null;
}

export interface ExpectedFeature {
  id: string;
  name: string;
  description: string;
  parent_id: string | null;
  status: "draft" | "questioned" | "accepted" | "deferred";
}

export interface FeatureResponsibilityLink {
  id: string;
  expected_feature_id: string;
  responsibility_id: string;
  kind: "realizes" | "contributes";
}

export interface TargetDesignRevision {
  schema_version: "cointent.target-design/0.4";
  id: string;
  workspace_id: string;
  parent_revision_id: string | null;
  base_observed_revision_id: string;
  title: string;
  summary: string;
  expected_features: ExpectedFeature[];
  responsibilities: Responsibility[];
  feature_responsibility_links: FeatureResponsibilityLink[];
  baseline_links: Array<{
    design_kind: "expected_feature" | "responsibility";
    design_id: string;
    observed_kind: "capability" | "responsibility";
    observed_id: string;
    kind: "cloned_from";
  }>;
  rationale: string;
  unresolved_questions: string[];
  created_by: "human" | "agent";
  created_at: string;
  content_digest: string;
}

export interface TargetDesignWorkspace {
  id: string;
  project_id: string;
  title: string;
  base_observed_revision_id: string;
  base_code_snapshot_id: string;
  status: string;
  current_design_revision_id: string;
  created_by: "human" | "agent";
  created_at: string;
  updated_at: string;
}

export interface TargetDesignView {
  workspace: TargetDesignWorkspace;
  revision: TargetDesignRevision;
  revisions: TargetDesignRevision[];
  review: DesignReview | null;
  implementation_export: ImplementationChangeBundle | null;
  verification_report: VerificationReport | null;
  verification_decision: VerificationDecision | null;
}

export interface SemanticDesignChange {
  id: string;
  kind: "expected_feature" | "responsibility" | "feature_mapping";
  change_type: "added" | "removed" | "changed";
  design_id: string | null;
  baseline_observed_id: string | null;
  name: string;
  fields: string[];
}

export interface DesignReview {
  id: string;
  project_id: string;
  workspace_id: string;
  design_revision_id: string;
  base_observed_revision_id: string;
  status: "in_review" | "approved";
  changes: SemanticDesignChange[];
  acceptance_criteria: Array<{ id: string; statement: string; related_change_ids: string[] }>;
  submitted_by: string;
  submitted_at: string;
  content_digest: string;
}

export interface ImplementationChangeBundle {
  id: string;
  project_id: string;
  workspace_id: string;
  design_revision_id: string;
  base_observed_revision_id: string;
  base_code_snapshot_id: string;
  review_id: string;
  approval_id: string;
  changes: SemanticDesignChange[];
  acceptance_criteria: DesignReview["acceptance_criteria"];
  evidence_context: ClaimBinding[];
  operation_ids: string[];
  agent_prompt: string;
  approved_by: string;
  approved_at: string;
  content_digest: string;
  created_at: string;
}

export interface VerificationReport {
  id: string;
  project_id: string;
  workspace_id: string;
  implementation_bundle_id: string;
  design_revision_id: string;
  baseline_observed_revision_id: string;
  observed_revision_id: string;
  observed_code_snapshot_id: string;
  status: "awaiting_human_review";
  claims: Array<{
    id: string;
    kind: "expected_feature" | "responsibility";
    status: "matched" | "missing" | "unexpected" | "ambiguous" | "stale";
    target_design_id: string | null;
    observed_id: string | null;
    name: string;
    explanation: string;
    evidence: ClaimBinding[];
  }>;
  summary: Record<"matched" | "missing" | "unexpected" | "ambiguous" | "stale", number>;
  content_digest: string;
  created_at: string;
}

export interface VerificationDecision {
  id: string;
  report_id: string;
  project_id: string;
  workspace_id: string;
  decision: "converged" | "needs_revision";
  notes: string;
  actor: string;
  decided_at: string;
  content_digest: string;
}

export type TargetDesignOperation =
  | { kind: "set_intent"; summary: string }
  | { kind: "upsert_expected_feature"; expected_feature: ExpectedFeature }
  | { kind: "remove_expected_feature"; expected_feature_id: string }
  | { kind: "upsert_responsibility"; responsibility: Responsibility }
  | { kind: "remove_responsibility"; responsibility_id: string }
  | { kind: "set_workflow"; responsibility_id: string; workflow: Workflow | null }
  | { kind: "upsert_feature_link"; feature_link: FeatureResponsibilityLink }
  | { kind: "remove_feature_link"; feature_link_id: string }
  | { kind: "set_unresolved_questions"; unresolved_questions: string[] };
