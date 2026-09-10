# CoIntent 0.4 Detailed Design: Understand the Present, Design the Future

**Status:** accepted core model; on-demand experience revision accepted
**Scope:** product model, backend boundaries, incremental Understand Anything integration, recursive projection, two-tab workspace, target diff and implementation context
**Supersedes:** the parts of 0.3 that treat one accepted Responsibility model as both observed system truth and desired design  
**Implementation authority:** approved as the incremental implementation baseline

> **Normative product-flow revision:** [On-demand product flow and MCP surface](on-demand-product-flow.md)
> governs when analysis runs, how much graph an Agent reads, the compact public Role graph, and the optional
> nature of later design-versus-implementation comparison. Earlier lifecycle detail below remains useful as
> domain and audit design, but must not be interpreted as an always-on or automatically advancing workflow.
> [UA Dashboard integration](ua-dashboard-integration.md) defines the directly embedded code-map view, browser
> HTTP boundary, ImplementationRef contract, and bidirectional semantic/source focus behavior.

## 1. Executive decision

CoIntent has two different jobs and must represent them as two different processes:

```text
UNDERSTAND — what the system is now

Code
  → CodeSnapshot
  → UnderstandAnythingSnapshot
  → ObservedStructureGraph
  → ObservedCapabilityCatalog / as-built explanation
  → Human understanding


DESIGN — what the system should become

Human intent
  → ExpectedFeatureCatalog
  → TargetStructureGraph
  → Human review and semantic diff
  → Implementation context
  → Coding Agent
  → changed Code
```

CoIntent runs neither process continuously. Understanding begins when a user asks to refresh or inspect a
project. Design begins only when a user explicitly wants to design structure before code, and it first refreshes
the observed baseline. Coding completion ends the design interaction; it does not automatically scan, verify, or
advance a convergence state. A later on-demand refresh may be compared with the historical drawing if requested.

The product exposes these jobs as two top-level tabs with the same spatial grammar:

- **Understand current** (`理解现状`): derived from code and read-only.
- **Design future** (`设计未来`): derived from human intent and editable as versioned drafts.

Both tabs place functions/capabilities on the left and a recursive Responsibility/Workflow graph on the right. This similarity is intentional: users learn one way to navigate semantic altitude. The two tabs differ in provenance, available actions, version coordinates, colors, and state language.

The only legal bridges between them are:

1. create a target design from a named observed baseline;
2. copy an observed node into a target draft while preserving its origin reference;
3. finalize the reviewed target graph and semantic diff as implementation context;
4. compare a historical target with a later user-requested observed graph.

An instruction from a human can never directly mutate an observed graph.

## 2. Why the 0.3 model must be separated

In 0.3, `ProjectModel` contains specification, Responsibilities, Workflows, and implementation links in one versioned object. `ModelPatch` can upsert both Responsibilities and implementation mappings. The proposal/review mechanism protects accepted versions from silent overwrite, but it does not prove that accepted graph content is derived from code. A human can ask an Agent to propose a graph change and then accept it without changing code.

That behavior was correct while the middle model was a normative design model. It is incorrect once the graph shown in the understanding experience promises to describe the current implementation.

Version 0.4 therefore does not add an `origin` flag to the existing object. A flag is too weak because the same mutation API could still update both kinds. It introduces distinct aggregates and distinct repositories:

| Aggregate | Meaning | Truth source | Who may create revisions | Mutable in place |
|---|---|---|---|---|
| `CodeSnapshot` | exact repository coordinate | Git/worktree capture | scanner | no |
| `UnderstandAnythingSnapshot` | validated UA code and domain maps | UA output over one CodeSnapshot | import pipeline | no |
| `ObservedModelRevision` | human-readable current behavior | projector over one UA snapshot | projector only | no |
| `DesignWorkspace` / `DesignRevision` | desired behavior | human intent and design Agent | human/Agent through design tools | draft advances by new revision |
| `ImplementationChangeBundle` | approved target-minus-baseline contract | one approved DesignRevision | export service | no |
| `VerificationReport` | target-to-later-observation comparison | approved target plus later observed revision | verifier | no |

Observed and desired graphs may reuse the same value-object schema for Responsibility and Workflow rendering. They may not share an envelope, revision table, write method, or identifier namespace.

## 3. Product vocabulary

UI language should describe what users know and control, not internal storage names.

| Technical concept | English UI | Chinese UI | Notes |
|---|---|---|---|
| Observe tab | Understand current | 理解现状 | Prefer this over “Read”; it names the user goal. |
| Design tab | Design future | 设计未来 | A workspace for desired behavior, not a claim about code. |
| Observed capability | System function | 系统功能 | Generated after the graph is projected. |
| Expected feature | Expected function | 期望功能 | Human-owned product intent. |
| Observed graph | Current structure | 当前结构 | Always carries a code coordinate and freshness state. |
| Target graph | Target structure | 目标结构 | The desired Responsibility/Workflow model. |
| UA graph | Code evidence map | 代码证据图 | Normally appears in evidence details, not as the main product graph. |
| Expansion | Show one level deeper | 下钻一层 | A projection request, not a graph edit. |
| Design diff | Implementation change | 实现变更 | Semantic work requested from a coding Agent. |
| Feedback | Report analysis issue | 报告理解问题 | Does not change observed truth. |

“Architecture” should not be used in the UI unless the product later adds deployment, service topology, or infrastructure semantics. The current schema is a Responsibility/Workflow structure graph. Internally and in this document, “target structure” means the desired program-logic structure, not a class, deployment, or infrastructure diagram.

## 4. Domain boundaries

### 4.1 Shared graph value objects

The 0.3 semantic shape remains useful:

```text
SemanticGraph
├── capabilities[]
├── responsibilities[]
│   └── workflow?
│       ├── entry_node_ids[]
│       ├── nodes[] → responsibility_id
│       └── edges[]
└── capability_responsibility_links[]
```

The following invariants remain:

- Responsibility definitions are stable semantic objects.
- Workflow nodes are occurrences referencing Responsibility definitions.
- one canvas shows one semantic altitude;
- branches, loops, errors, events, and parallel relationships are first-class;
- composition exists only in Workflow node references;
- graph cycles are legal.

The word `capabilities` above is an interface abstraction. Persisted observed capabilities and expected features are intentionally separate record types because their provenance and editing rules differ.

### 4.2 CodeSnapshot

`CodeSnapshot` is an immutable input coordinate:

```yaml
CodeSnapshot:
  id: snapshot-...
  project_id: idea-factory
  repository_identity: ...
  revision: git commit
  branch: master
  dirty: false
  tracked_content_digest: ...
  captured_at: ...
  scanner_version: ...
```

A dirty snapshot is allowed for local analysis but must display `Uncommitted code` prominently. Exporting a design from a dirty baseline requires an explicit baseline acknowledgement because another Agent may not be able to reproduce it.

### 4.3 Understand Anything snapshot

CoIntent 0.4 has one code-map source: Understand Anything (UA). It imports UA's `knowledge-graph.json` and optional `domain-graph.json` directly into an immutable, validated snapshot. This phase deliberately has no generic analyzer adapter or multi-producer Code Map IR.

```yaml
UnderstandAnythingSnapshot:
  schema_version: cointent.ua-snapshot/0.1
  id: ua-...
  project_id: idea-factory
  code_snapshot_id: snapshot-...
  ua_graph_version: ...
  ua_tool_revision: pinned Git commit or release
  knowledge_graph: KnowledgeGraph
  domain_graph: KnowledgeGraph | null
  coverage: UnderstandAnythingCoverage
  diagnostics: []
  content_digest: ...
  created_at: ...
```

The imported snapshot preserves UA's native node/edge model rather than prematurely translating it into a hypothetical universal schema. Structural identity and relationships originate in UA's Tree-sitter analysis; summaries, tags, layers, domains, flows, steps, and tours are semantic analysis. CoIntent records this distinction when turning native records into observed claims.

The import validator requires a full-repository CodeSnapshot, matching Git coordinates, safe repository-relative paths, valid source ranges, unique node IDs, and non-dangling edges. A domain/flow/step becomes visible in the current-system graph only when it has direct evidence or inherits resolvable evidence from descendants. [ADR-0001](adr-0001-codemap-engine.md) defines the complete trust and execution boundary.

Future support for a second engine is deferred. When it becomes necessary, the system will introduce an adapter abstraction based on UA and that concrete second integration; 0.4 does not carry unused registries, engine enums, reconciliation logic, or generic capabilities.

### 4.4 ObservedModelRevision

An observed revision is an immutable semantic projection:

```yaml
ObservedModelRevision:
  schema_version: cointent.observed-model/0.4
  id: observed-...
  project_id: idea-factory
  code_snapshot_id: snapshot-...
  ua_snapshot_id: ua-...
  parent_revision_id: null | observed-...
  refinement_of_node_id: null | obs-resp-...
  projector_version: ua-domain-v1
  capabilities: [ObservedCapability]
  responsibilities: [Responsibility]
  bindings: [ClaimBinding]
  diagnostics: []
  content_digest: ...
  created_at: ...
```

`ClaimBinding` connects every product-readable claim to evidence:

```yaml
ClaimBinding:
  id: binding-...
  subject_kind: responsibility | workflow_edge | capability
  subject_id: ...
  predicate: implemented_by | ordered_by | summarized_by
  ua_node_ids: [...]
  evidence:
    - ua_node_id: step:...
      structural_ua_node_ids: [file:..., function:...]
      path: src/...
      start_line: 10
      end_line: 25
      source_digest: ...
  support: direct | aggregated | inferred
  explanation: ...
```

Validation rules:

1. every observed Responsibility has at least one binding corroborated by a structural UA node;
2. every observed Workflow edge has evidence and is limited to the ordering semantics UA actually supplies;
3. every source span belongs to the bound CodeSnapshot content;
4. every capability links to at least one observed Responsibility;
5. no binding may point to a different UnderstandAnythingSnapshot;
6. projection coverage lists omitted entities and the policy reason;
7. content digests are checked before a revision is made visible;
8. a revision is append-only and cannot be updated or deleted through product APIs.

This guarantees provenance and freshness, not perfect semantic interpretation. The UI must say `Generated from code` and show confidence/coverage where relevant; it must not imply that Understand Anything is infallible.

### 4.5 Progressive observed projection

Large systems are projected lazily. An initial run should normally produce roots plus two semantic levels. Deeper exploration creates refinement revisions tied to the same UnderstandAnythingSnapshot.

```text
Observed revision R1
  UA snapshot U1
  roots + two levels

User requests “show one level deeper” on node N
  → server resolves N's ClaimBindings
  → extracts the bounded UA evidence subgraph
  → projector generates children and local Workflow
  → validators reject unsupported claims
  → immutable observed revision R2, parent R1, refinement_of N
```

The request accepts only a focus and resolution policy. It never accepts graph nodes or edges supplied by the caller:

```yaml
ObservedExpansionRequest:
  project_id: idea-factory
  base_observed_revision_id: observed-...
  node_id: obs-resp-...
  depth: 1                  # initially fixed to 1; maximum 3
  reason: user_drilldown
```

If code evidence cannot support a deeper product-relevant decomposition, the result is `atomic_at_current_evidence`, not a fabricated Workflow.

Observed IDs are stable within one UnderstandAnythingSnapshot. Continuity across code snapshots is a separate lineage result with a confidence score; refactors can break identity. The UI must not silently equate nodes across snapshots merely because their names match.

### 4.6 Observed capabilities and as-built explanation

The understanding direction required by the product is explicitly:

```text
Code → UA snapshot → observed structure → observed system functions
```

Observed capabilities are therefore generated after Responsibility projection. They summarize what the observed graph exposes as product-visible behavior. They are not copied from the desired specification.

An as-built manual is a rendered projection of the observed graph and its capability catalog. It is not independently editable or separately versioned. The export carries its observed revision coordinate.

### 4.7 DesignWorkspace and DesignRevision

A design workspace is a branch of desired semantics rooted in a named baseline:

```yaml
DesignWorkspace:
  id: design-workspace-...
  project_id: idea-factory
  title: ...
  base_observed_revision_id: observed-...
  base_code_snapshot_id: snapshot-...
  status: draft | in_review | approved | exported | implementing | verifying | converged | needs_revision | cancelled
  current_design_revision_id: design-...
  created_by: ...
  created_at: ...

DesignRevision:
  schema_version: cointent.target-design/0.4
  id: design-...
  workspace_id: ...
  parent_revision_id: ...
  expected_features: [...]
  graph: SemanticGraph
  baseline_links: [DesignBaselineLink]
  rationale: ...
  unresolved_questions: [...]
  validation: ...
  created_by: human | agent
  created_at: ...
```

The persisted status vocabulary supports audit and compatibility. The default user experience exposes only
`draft`, `finalized for implementation`, and `historical`; review/export/verification records do not become
separate top-level product stages.

`DesignBaselineLink` records where target objects came from:

- `unchanged_from`: semantic intent is inherited;
- `modified_from`: target object deliberately changes an observed object;
- `replaces`: one target object supersedes one or more observed objects;
- `new`: no observed counterpart;
- `removes`: an observed object is intentionally absent from the target.

Design Responsibilities use a `des-` namespace. An observed node is cloned into the workspace rather than referenced as a mutable target. This prevents a design operation from changing the observed aggregate through shared object identity.

Design graph claims do not require current code evidence; divergence is their purpose. Instead, approval validation requires a rationale, expected effect, and testable acceptance criterion for every material change.

### 4.8 Design editing and review

Humans may express desired changes through conversation or direct structured controls. The Agent writes only design operations:

```yaml
DesignOperation:
  id: operation-...
  design_revision_id: design-...
  kind: add | remove | rename | redefine_contract | decompose | compose | reorder | change_condition | reuse
  target_id: des-...
  before: ...
  after: ...
  rationale: ...
  expected_feature_ids: [...]
  acceptance_criteria: [...]
  author: ...
```

Every operation creates a new immutable draft revision. Undo selects or creates another revision; it does not mutate history. Layout-only changes are stored in user presentation preferences and excluded from semantic diffs.

The drawing UI has three views inside Design future:

- **Draft:** edit expected functions and target graph.
- **Changes:** show target against baseline with added, removed, and changed semantics.
- **Finalize:** show affected functions, contract changes, unresolved questions, acceptance criteria, and the
  implementation-context digest.

Approval locks a DesignRevision. Further changes create a successor draft and invalidate the earlier approval for export.

### 4.9 Implementation context

The implementation context may be stored using the existing `ImplementationChangeBundle` contract. It is not
a source-code patch. It is a machine-readable semantic constraint plus a human-readable brief, created only
after the user explicitly confirms an exact drawing and diff digest.

```yaml
ImplementationChangeBundle:
  schema_version: cointent.implementation-change/0.1
  id: implementation-change-...
  project_id: idea-factory
  design_workspace_id: ...
  approved_design_revision_id: design-...
  baseline:
    observed_revision_id: observed-...
    code_snapshot_id: snapshot-...
    repository_revision: ...
    dirty: false
  target_digest: ...
  expected_feature_diff: ...
  structure_diff:
    operations: [DesignOperation]
    added_responsibilities: [...]
    removed_responsibilities: [...]
    changed_contracts: [...]
    changed_workflows: [...]
  likely_code_scopes:
    - observed_binding: ...
      status: hint_only
  acceptance_criteria: [...]
  unresolved_questions: []
  generated_at: ...
```

One export contains:

- `implementation-change.json` — canonical machine contract;
- `implementation-brief.md` — concise instructions for a coding Agent;
- `baseline-observed.json` — relevant observed slice, not necessarily the whole repository graph;
- `target-design.json` — approved target slice;
- `manifest.json` — filenames, digests, schemas, and coordinates.

Export is blocked when:

- the DesignRevision is not approved;
- unresolved blocking questions remain;
- the target graph is invalid;
- the current repository baseline differs from the workspace baseline and the workspace has not been rebased;
- the baseline is dirty and was not explicitly acknowledged;
- bundle schemas cannot be validated.

Likely code scopes are hints derived from baseline bindings. They are not commands to edit only those files; new desired behavior may require new artifacts.

### 4.10 Optional later comparison

Implementation does not convert a target graph into observed truth. Coding completion also does not trigger a
scan. When a user later asks to understand the project or starts another design, the ordinary on-demand refresh
may publish a new current Observation. The user can then request a comparison:

```text
later user request
  → refresh new code
  → new CodeSnapshot
  → new UnderstandAnythingSnapshot
  → new ObservedModelRevision
  → optionally compare against historical DesignRevision
  → read-only comparison report
```

The report classifies target claims as:

- `satisfied` — supported by the new observed graph;
- `missing` — expected behavior is not observed;
- `unexpected` — new observed behavior was not part of the target;
- `uncertain` — evidence or semantic matching is insufficient;
- `not_comparable` — UA coverage prevents a conclusion.

The comparison never merges the drawing into observed truth and does not require graph equality. Structural
divergence is expected because the drawing constrained design rather than prescribed exact implementation.
Stale evidence prevents comparison; behavioral gaps and structural deviations remain explicit for human
interpretation. The default product does not require a separate convergence state.

## 5. Two-tab frontend information architecture

### 5.1 Shared shell

The two tabs share project context and preserve the focused Responsibility when a baseline link exists.

```text
┌ CoIntent ─ Project ▾ ───────────────────────────────────── Account ┐
│ [ Understand current ] [ Design future · 1 draft ]                │
├────────────────────────────────────────────────────────────────────┤
│ mode-specific coordinates and status                               │
└────────────────────────────────────────────────────────────────────┘
```

The tab switch is the primary mode boundary and remains visible at every viewport. Browser routes are durable:

```text
/projects/:projectId/understand?observed=:revision&focus=:nodeId
/projects/:projectId/design/:workspaceId?revision=:revision&focus=:nodeId
```

Unsaved text input in Design is confirmed before leaving. Created design revisions need no warning because they are already durable.

### 5.2 Understand current

The current page evolves into a strictly read-only understanding workspace:

```text
┌ System functions ───────┬ Current structure ───────────────────────┐
│ derived from this graph │ code abc123 · generated · current       │
│                         │ breadcrumb / semantic altitude           │
│ Search                  ├───────────────────────────────────────────┤
│ Capability tree         │                                         │
│  ◇ Intake               │       recursive Workflow canvas         │
│    · Validate           │                                         │
│    · Dispatch           │                                         │
│                         │ [Show one level deeper]                  │
│ Coverage / omissions    │                                         │
├─────────────────────────┴───────────────────────────────────────────┤
│ Collapsible evidence drawer: contract · UA graph · source · issues │
└─────────────────────────────────────────────────────────────────────┘
```

Left rail:

- lists `ObservedCapability` records, never expected Specification items;
- shows that functions were generated from the selected observed graph;
- filters and searches without changing the graph;
- reports capability coverage and omitted/unresolved areas;
- selecting a function focuses its realizing root Responsibility.

Graph area:

- reuses recursive single-altitude navigation from 0.3;
- shows snapshot, projection, freshness, and coverage coordinates;
- provides `Show one level deeper` for expandable or unresolved nodes;
- never renders edit handles, editable labels, save actions, or proposal acceptance;
- offers `Design a change from here`, which switches processes by creating/opening a DesignWorkspace;
- offers `Report analysis issue`, which records feedback without changing graph data.

Evidence drawer:

- keeps UA graph detail subordinate to product logic;
- opens from an evidence badge on a node, edge, field, or capability;
- displays the binding explanation, UA node/relationship chain, import coverage, and exact source spans;
- may show a read-only source excerpt obtained from the bound snapshot;
- exposes the UA graph version, pinned tool revision, and import schema for reproducibility;
- never introduces code entities as Responsibility nodes on the primary canvas.

Freshness copy is precise:

- `Current for abc123` — latest successful graph for latest code snapshot;
- `Projection is still running` — UA snapshot exists, observed graph is pending;
- `Newer code is available` — selected observed revision is stale;
- `Partial evidence` — UA coverage has known gaps;
- `Analysis failed` — keep the last successful graph visible but never label it current.

When a user asks the Agent to modify this graph, the product response is:

> Current structure is generated from code snapshot abc123 and cannot be edited. Create a target design from this node, or report an analysis issue.

### 5.3 Design future

Design uses the same left/function and right/graph grammar, but its objects and actions are different:

```text
┌ Expected functions ─────┬ Target structure ────────────────────────┐
│ human-owned intent      │ based on current abc123 · Draft r7      │
│                         │ [Draft] [Changes] [Approval]             │
│ + Add expected function ├───────────────────────────────────────────┤
│  ◇ Faster intake        │                                         │
│    · Validate once      │       editable target graph              │
│    · Explain rejection  │       through Agent / structured actions │
│                         │                                         │
│ Coverage by target      │ selected change indicators               │
├─────────────────────────┴───────────────────────────────────────────┤
│ Design dock: conversation · object contract · rationale · review   │
└─────────────────────────────────────────────────────────────────────┘
```

Left rail:

- contains expected functions owned by the human;
- supports draft, questioned, accepted, and deferred states;
- shows which target Responsibilities realize each expected function;
- highlights functions changed since the observed baseline;
- separates product wording from code or implementation suggestions.

Graph area:

- starts as a clone/projection of the chosen observed baseline or as an empty target;
- edits only `DesignRevision` objects;
- supports conversational commands scoped to the selected node;
- supports reviewable structured actions such as rename, redefine contract, decompose, reorder, branch, remove, and add;
- displays added, changed, removed, and unchanged target semantics;
- keeps layout edits visually useful but semantically neutral;
- permits target-only nodes with no code evidence and labels them `Not implemented yet`.

Design dock:

- Conversation: explain the desired change in natural language.
- Contract: inspect/edit data, inputs, outputs, and boundary.
- Change rationale: why this change is wanted and which expected function it serves.
- Acceptance: testable conditions the implementation should satisfy.
- Review: operation list, unresolved questions, validation, approval, and export.

Direct and conversational edits use the same operation pipeline. The UI never maintains a second unsynchronized client-only graph mutation format.

### 5.4 Moving between tabs

From Understand to Design:

1. user selects a function or Responsibility;
2. chooses `Design a change from here`;
3. selects an existing compatible workspace or creates one;
4. server records the exact observed revision and code snapshot as baseline;
5. Design opens at the linked target node.

From Design to Understand:

- `View baseline` opens the exact observed revision, even if it is no longer latest;
- `View current code` opens the latest observed revision and warns if it differs from the baseline;
- `Compare after implementation` opens the VerificationReport when available.

The tabs must not use an unlabeled bidirectional arrow between “Design” and “Code”; that suggests symmetrical editing. Instead, each mode shows its own directional provenance:

```text
Understand: Code abc123 → UA map U4 → Current structure O9
Design:     Baseline O9 → Target draft D7 → Approved export E2
```

### 5.5 Visual direction

The interface should preserve the existing serious, information-dense workspace but make provenance visible before the user reads any label.

Compact token system:

| Token | Value | Use |
|---|---:|---|
| Ink | `#17212B` | shared text and structural anchors |
| Field | `#F3F6F8` | neutral working surface |
| Evidence blue | `#2866B1` | Understand mode, code-derived claims |
| Design violet | `#7351A6` | Design mode, desired semantics |
| Review amber | `#B56712` | stale, unresolved, changed |
| Rule | `#C8D1D9` | borders and graph scaffolding |

Typography:

- keep Manrope for interface and long-form readability;
- keep IBM Plex Mono for coordinates, digests, statuses, and evidence;
- replace generic decorative serif usage in working screens with a restrained humanist display face only for the focused Responsibility title; the title marks semantic focus, not marketing hierarchy;
- use tabular numerals for revisions and coverage.

Signature interaction: switching between tabs preserves the selected semantic location and briefly transforms the graph from solid evidence-blue edges into a violet tracing-paper target overlay when a baseline link exists. The motion is one 180–220 ms transition, not ambient animation. Reduced-motion users receive an immediate switch.

This “same map, different truth layer” transition is the single expressive visual device. Other surfaces remain quiet. It encodes a real product relationship and avoids decorating the workspace with unrelated gradients, orbits, or dashboard cards.

Mode is never communicated by color alone. Tab selection, provenance sentence, iconography, and editable/read-only controls all reinforce it.

### 5.6 Responsive behavior

- Desktop ≥ 1200 px: function rail and graph side by side; inspector/dock is a collapsible bottom or right drawer.
- Tablet 768–1199 px: function rail collapses to a 320 px overlay; graph remains primary.
- Mobile < 768 px: function list and graph become two internal views beneath the selected top-level process tab. The top-level Understand/Design distinction is never hidden in a menu.
- Graph nodes remain keyboard focusable; Enter opens details and a separate action triggers descent.
- Every edge meaning has a textual equivalent in the object inspector.
- Diff colors also use shape/line treatments: added solid-plus, removed dashed-minus, changed double rule.

## 6. Backend architecture

### 6.1 Pipeline

```text
Repository
   │ read only
   ▼
Scanner ──→ CodeSnapshot
               │
               ▼
Pinned Understand Anything ──→ knowledge-graph.json + domain-graph.json
               │ import + validate
               ▼
    UnderstandAnythingSnapshot
               │ bounded projection
               ▼
          ObservedModelRevision
               │ summarize
               ▼
          ObservedCapabilities / Manual
```

Each transition runs as a leased job. Concurrent requests for the same project coalesce onto the active lease.
After a job completes, a later explicit request creates a new audit record; preflight reuses the current
Observation without invoking UA when the frozen commit is unchanged. Artifact identities remain content-derived
from the project and complete code/UA coordinates.

The pipeline is started only by `refresh-current-understanding`, normally because the user wants to understand
the project or is about to start structural design. A full CodeSnapshot records the complete repository manifest,
but repeat UA computation is incremental: unchanged code skips all UA work; a valid previous UA state runs plain
`/understand`; only initial, corrupt-cache, explicit operator, or upstream `FULL_UPDATE` conditions use
`/understand --full`. When code changed, `/understand-domain` may recompute from the complete merged knowledge
graph. Coding completion alone never starts this pipeline.

### 6.2 Storage

For the first 0.4 implementation, retain SQLite transaction metadata and immutable JSON assets. Add metadata tables rather than immediately normalizing every graph node:

```text
snapshots                         # existing physical CodeSnapshot table
understand_anything_snapshots
understanding_refresh_jobs
refresh_artifact_transfers
ua_state_checkpoints
observed_model_revisions
observation_expansion_requests
observed_feedback
design_workspaces
design_revisions
design_operations
design_approvals
implementation_exports
verification_reports
```

Recommended relational keys:

- `understand_anything_snapshots.code_snapshot_id → snapshots.id`;
- `observed_model_revisions.ua_snapshot_id → understand_anything_snapshots.id`;
- `observed_model_revisions.parent_revision_id → observed_model_revisions.id`;
- `observation_expansion_requests.base_observed_revision_id → observed_model_revisions.id`;
- `design_workspaces.base_observed_revision_id → observed_model_revisions.id`;
- `design_revisions.workspace_id → design_workspaces.id`;
- `implementation_exports.approved_design_revision_id → design_revisions.id`;
- `verification_reports.export_id → implementation_exports.id`;
- `verification_reports.observed_revision_id → observed_model_revisions.id`.

JSON assets are content-addressed and written atomically. Metadata rows store the digest and schema marker. On read, digest and schema validation happen before deserialization.

The existing `model_versions`, `proposals`, `mapping_revisions`, and `change_sets` remain readable during migration but are not used for new observed revisions.

### 6.3 Write authority

Authority is enforced by capability boundaries, not Agent instructions alone:

| Principal/capability | Request refresh | Publish observation | Read one level | Revise design | Finalize implementation context |
|---|---:|---:|---:|---:|---:|
| browser human (authenticated HTTP) | no | no API | yes | yes | yes |
| Agent MCP principal | yes | no API | yes | scoped proposal | after explicit user instruction |
| observation pipeline | execute | yes | read | no | no |

There is no public or MCP tool named `upsert-observed-responsibility`, `replace-observed-model`, or `record-observed-mapping`. Expansion tools create jobs; only the projector can publish their result.

Repository methods are separated physically or by explicit interfaces:

```text
ObservationRepository     # append/read generated facts
DesignRepository          # create/read design revisions and operations
ImplementationContextRepository  # finalized diff and optional comparison records
```

The old generic `replace_model` must not be reachable in runtime product code after migration. Import and test fixtures may use a clearly named administrative migration path.

### 6.4 Freshness model

Freshness has independent coordinates:

- code freshness: is this the latest repository snapshot?
- UA freshness: was this map produced from the selected snapshot using the pinned UA revision and configuration?
- projection freshness: was this graph produced from the selected UA snapshot using the active projector policy?
- design baseline freshness: does this workspace still target the repository coordinate from which it was created?

`Current` requires all first three answers to be yes. A graph can be valid and reproducible but stale. A design
must be rebased before finalization when its baseline is no longer current.

### 6.5 Failure behavior

- An incomplete or invalid UA output publishes no UA snapshot; diagnostics remain attached to the failed job.
- Projector validation failure publishes no observed revision; the last successful graph remains visible as stale.
- Expansion failure leaves its base observed revision untouched.
- Design validation failure still saves the draft but blocks finalization.
- Implementation-context creation failure creates no partial bundle; asset creation is atomic.
- Optional comparison uncertainty never mutates the historical design or current observation.

## 7. Agent MCP public surface

MCP is the product-operation transport for conversational and coding Agents. The browser uses authenticated HTTP
for the application, UA artifacts, and exact-snapshot source. Both surfaces enforce the same aggregate and
coordinate rules without sharing one transport. The Agent capability graph is deliberately smaller than the
persisted aggregates. Exact contracts and Role instructions are normative in
[the on-demand product-flow specification](on-demand-product-flow.md).

### 7.1 Project context

- `list-projects()`
- `register-project(project_id, name, repository, default_branch, language)`
- `inspect-project-state(project_id)`

### 7.2 Distribution

- `prepare-ua-installation(platform, operating_system)`
- `verify-ua-installation(evidence)`

Distribution preserves UA's native platform installation. It verifies the exact upstream unit and prerequisites;
it does not compile UA Skills into CoIntent or execute commands on the MCP server.

### 7.3 Understand current

- `refresh-current-understanding(project_id)`
- `prepare-native-refresh(job_id, preflight)`
- `prepare-refresh-artifacts(job_id, analysis_mode, artifacts, fallback_reason?, files_reanalyzed?)`
- `complete-native-refresh(job_id)`
- `inspect-understanding-refresh(job_id)`
- `read-current-level(project_id, focus_id?, observed_revision_id?)`

The level response contains the same bounded function, structure, edge, evidence, and coordinate information
visible on one web page. Passing a returned child as `focus_id` is the ordinary descent mechanism. A caller may
stage opaque native bundles only through refresh-scoped transfer capabilities; no method accepts graph nodes or
edges as current-system mutations.

### 7.4 Design future

- `start-structure-design(project_id, title)`
- `read-design-level(workspace_id, focus_id?, design_revision_id?)`
- `revise-structure-design(workspace_id, base_design_revision_id, operations, rationale)`
- `diff-structure-design(workspace_id, from_revision_id?, to_revision_id?)`
- `create-implementation-context(workspace_id, design_revision_id, expected_diff_digest)`
- `list-structure-design-versions(workspace_id)`
- `compare-design-to-current(design_revision_id, observed_revision_id?)`

`start-structure-design` requires the latest valid root Observation. `revise-structure-design` rejects observed
IDs as mutation targets. `create-implementation-context` requires explicit user instruction, records the actual
authenticated initiating principal, binds an exact immutable design/diff coordinate, and schedules no scan.
Later comparison is optional and read-only.

### 7.5 Roles and long-running work

The default root contains only `project-context`, `distribution`, `understand-current`, and `design-future`.
Native snapshot/import/publication is not directly exposed: the Agent can stage digest-bound bundles for an active
refresh, while validator/projector code alone publishes. Broader 0.3 tools remain on a separate compatibility root
during migration.

Refresh requests return a job resource and report `unchanged | incremental | full`. The UI may poll or subscribe
through the authenticated HTTP application surface. The embedded UA Dashboard has no MCP Role and cannot publish
or repair graph content.

## 8. Frontend application architecture

The current `App.tsx` owns authentication, fetching, navigation, layout, graph rendering, and detail state in one component. The two-process product should split by route and domain:

```text
AppShell
├── ProjectHeader
├── ProcessTabs
├── UnderstandRoute
│   ├── UnderstandSubviewTabs
│   ├── SystemView
│   │   ├── ObservedCapabilityRail
│   │   ├── ObservedGraphWorkspace
│   │   └── EvidenceDrawer
│   └── UaImplementationMap
│       ├── CoordinateHeader
│       ├── SemanticReturnPanel
│       └── PinnedUaViewerIframe
└── DesignRoute
    ├── ExpectedFeatureRail
    ├── TargetGraphWorkspace
    └── DesignDock

Shared
├── ResponsibilityGraphCanvas
├── ResponsibilityBreadcrumbs
├── ContractView
├── GraphDiffOverlay
└── CoordinateBadge
```

`ResponsibilityGraphCanvas` is shared and receives an explicit mode:

```ts
type GraphMode =
  | { kind: "observed"; readOnly: true; evidence: ClaimBinding[] }
  | { kind: "design"; readOnly: false; diff: DesignDiff };
```

Do not infer mode from the presence of click handlers or CSS classes. Exhaustive types should make an observed edit action impossible to wire without a compiler error.

Browser data loading is split over authenticated HTTP while the conversational Agent uses the MCP operations in
section 7:

- System view loads the same bounded current read model exposed by `read-current-level`.
- Design view loads and mutates the same target aggregates exposed by the `design-future` Role.
- Implementation map creates a scoped viewer session and loads immutable UA/source assets directly over HTTP.
- No browser graph or source request is routed through MCP.
- Do not repeat the current all-in-one `loadWorkspace` request fan-out on every tab or version change.
- Cache immutable revisions by ID. Latest-coordinate endpoints may be refreshed; content-addressed revision responses do not need refetching.

Browser state such as open drawer, pan/zoom, selected node, and preferred layout stays local. Semantic operations
round-trip through authenticated HTTP and return the resulting DesignRevision. UA viewport/layout state remains
inside the iframe; only the pinned coordinate and selected native node cross the host/viewer bridge.

## 9. Migration from 0.3

Existing 0.3 data has ambiguous provenance and must not be relabeled as observed truth.

### Phase 0 — freeze and name the boundary

- Mark 0.3 as the final mixed-model schema.
- Add tests demonstrating the current ability to propose graph changes; these become negative security tests for observed 0.4 APIs.
- Freeze the Responsibility/Workflow value-object contract unless a required 0.4 change is identified.

### Phase 1 — introduce separate stores

- Add new tables and immutable asset roots.
- Introduce `ObservationRepository`, `DesignRepository`, and `ImplementationContextRepository`.
- Keep all existing APIs read-compatible.

### Phase 2 — integrate Understand Anything

- Capture full-repository CodeSnapshots in addition to the legacy backend-only scan mode.
- Implement the current UA JSON schema subset, canonical hashing, coordinate validation, coverage, and fixture tests.
- Import `knowledge-graph.json` and optional `domain-graph.json` as one immutable UnderstandAnythingSnapshot.
- Project only evidence-backed Domain/Flow/Step branches into an observed revision.
- Evaluate the pinned UA version against Idea Factory before allowing it to publish the project's current observation.
- Do not introduce another engine or a generic adapter framework in 0.4.

### Phase 3 — generate observed truth independently

- Run an initial full scan and UA import for Idea Factory; preserve UA state for later incremental runs.
- Project a new observed graph with evidence bindings.
- Add recursive expansion and freshness behavior.
- Never seed the observed graph using the old accepted model as truth. Old mappings may be supplied as non-authoritative projector hints and must still pass binding validation.

### Phase 4 — migrate historical design

- Import each current accepted 0.3 model as a `Legacy design` workspace/revision.
- Attach its nearest CodeSnapshot only as historical context, not provenance proof.
- Preserve proposal, actor, rationale, and version history.
- Require a user to choose a valid observed baseline before exporting a legacy design.

### Phase 5 — ship the two tabs

- Route the current read experience into Understand and remove all design mutation actions from it.
- Ship Design with expected functions, target graph, operation history, diff review, and implementation-context handoff.
- Add the controlled tab bridges.

### Phase 6 — ship the on-demand MCP surface

- Add native-UA distribution and a central checkpoint protocol that preserves the UA state needed for
  incremental `/understand` updates without a server-local checkout or CoIntent client.
- Skip all UA work when repository content is unchanged and report every full fallback reason.
- Replace broad graph reads with one-page-equivalent `read-current-level` and `read-design-level` operations.
- Expose the compact four-Role public graph. The code-local Agent may stage only refresh-scoped opaque artifacts;
  validation/projector code remains the only Observation publisher.
- Create implementation context after explicit user instruction without scheduling post-coding analysis.
- Keep historical-design versus later-observation comparison optional and read-only.
- Retire mixed 0.3 mutation tools once no active client depends on them.

### Phase 7 — embed the UA implementation map

- Package the official pinned UA Dashboard as an isolated read-only microfrontend.
- Add authenticated HTTP viewer sessions bound to exact Observation/UA/code coordinates.
- Serve immutable UA artifacts and exact-snapshot source without routing browser data through MCP.
- Add first-class primary/supporting ImplementationRefs.
- Add forward focus, reverse semantic navigation, and baseline-design inspection.
- Expose no UA MCP server, graph-repair control, scan control, or second Agent chat surface.
- Follow the delivery and acceptance contract in [the UA Dashboard integration design](ua-dashboard-integration.md).

Rollout uses a per-project feature flag until an observed revision and a migrated design workspace are both available. Rollback returns to read-only 0.3; it must not write 0.4 objects back into 0.3 tables.

## 10. Testing strategy

### 10.1 Domain and integrity

- reject observed graph insertion without a valid UnderstandAnythingSnapshot;
- reject unresolved entity, relation, source-span, and cross-snapshot bindings;
- reject updates/deletes of published observed revisions;
- reject observed IDs as design mutation targets;
- reject expansion requests containing graph payloads;
- verify content-addressed idempotency;
- verify stale state when any coordinate advances;
- verify partial coverage remains visible through every derived layer.

### 10.2 Understand Anything import conformance

- same input/version/config produces byte-stable normalized output;
- unsupported languages and parse failures are counted;
- source spans resolve to the captured content digest;
- native UA IDs are always interpreted within their immutable UA snapshot coordinate;
- duplicate IDs, dangling edges, and conflicting source coordinates fail deterministically.

### 10.3 Projection

- every visible observed node and edge has required bindings;
- initial projection respects the configured two-level budget;
- expansion is bounded to the selected node's evidence subgraph;
- expansion creates a new immutable revision and leaves its parent unchanged;
- recursion and loops do not cause infinite projection or navigation;
- identical projection jobs are idempotent.

### 10.4 Design, implementation context, and optional comparison

- operations create new draft revisions;
- layout changes do not enter semantic diff;
- finalization locks an exact digest;
- stale or invalid baselines block implementation-context creation;
- implementation-context manifests validate every bundled digest;
- later code is scanned rather than promoted from the target design;
- finalization schedules no scan or automatic convergence workflow;
- later comparison never mutates either the historical target or current Observation;
- structural divergence is reported rather than treated as an automatic implementation failure.

### 10.5 Product UI

- observed screens contain no edit affordance in DOM or keyboard flow;
- a conversational edit request in Understand offers Design or issue reporting;
- the same semantic focus survives a valid tab bridge;
- mode remains distinguishable without color;
- source evidence is reachable but does not become the primary graph;
- desktop, tablet, mobile, keyboard, and reduced-motion flows pass;
- old deep links redirect to the correct process with an explicit migration notice.

## 11. Acceptance criteria

The 0.4 redesign is complete when:

1. users can unambiguously choose between understanding current code and designing future behavior;
2. both tabs use the same function-left/structure-right navigation grammar;
3. the Understand tab is generated through CodeSnapshot → UnderstandAnythingSnapshot → ObservedModelRevision → ObservedCapability and is read-only by construction;
4. every observed claim is traceable through UA structural evidence to an immutable code snapshot;
5. users can request bounded recursive expansion without supplying graph content;
6. a human or Agent cannot mutate an observed graph through REST, MCP, repository methods, or shared object identity;
7. users can create a target design from an exact observed baseline and edit expected functions and target structure without claiming the code already implements them;
8. review clearly shows semantic additions, removals, contract changes, workflow changes, unresolved questions, and acceptance criteria;
9. only a finalized, current-baseline DesignRevision can produce an ImplementationChangeBundle;
10. a Coding Agent can consume that bundle without access to CoIntent's mutable database;
11. repeat analysis uses UA incremental mode whenever valid prior state exists, while unchanged code spends no UA tokens;
12. coding completion triggers no scan; later comparison happens only after another user-requested refresh;
13. legacy 0.3 models remain auditable but are never silently certified as observed truth.
14. users can open the directly embedded UA Dashboard at an exact implementation reference and return from a UA
    node to every mapped current semantic subject without crossing snapshot coordinates.

## 12. Product decisions captured by this design

- There are two top-level process tabs, not a single blended alignment workspace.
- The tabs look structurally similar because both explain functions through recursive structure graphs.
- Expected functions and observed system functions are separate objects.
- Desired and observed graphs share rendering semantics but not storage or write paths.
- Understand Anything is the single 0.4 code-map source; its immutable imported artifact is the boundary beneath CoIntent projection.
- The UA graph appears as drillable evidence, not as the main user-facing graph.
- The official pinned UA Dashboard is embedded directly under Understand current → Implementation map.
- Browser UA graph/source loading uses authenticated HTTP; Agent product operations use CoIntent MCP.
- CoIntent provides no UA-specific MCP Role or dependency on a UA MCP server.
- Observed graph expansion is a generation request; target graph expansion is a design operation.
- Human corrections to observed interpretation become issues and regeneration, never direct edits.
- Implementation handoff produces a semantic constraint bundle, not a source patch.
- Code earns observed status only through the analysis pipeline, which is invoked on demand and computes
  incrementally whenever valid UA state exists.
