# CoIntent 0.4 Execution Path

**Status:** core data loop delivered; on-demand MCP surface and incremental UA runner next
**Decision baseline:** [design-v0.4](design-v0.4.md), [ADR-0001](adr-0001-codemap-engine.md)
**Delivery rule:** ship one Understand Anything path first; introduce no generic analyzer framework.

The current product-experience authority is [understand on demand, design on demand](on-demand-product-flow.md).
Coding completion does not trigger scanning or convergence. The implemented verification records remain useful
for optional later comparison, but are not a mandatory user journey.

## Current implementation checkpoint

Implemented in the first working slice:

- full-repository CodeSnapshot scope;
- pinned UA 2.9.6 JSON contracts and import validation;
- immutable UA snapshot and observed-revision storage/assets;
- semantic-to-structural source corroboration;
- evidence-backed Domain/Flow/Step projection;
- operator-only CLI import;
- read-only observation MCP/HTTP queries;
- bounded, idempotent Agent/browser expansion requests with no graph payload;
- synchronous trusted expansion worker with immutable child revisions, parent lineage, coverage deltas,
  64-node safety bounds, result caching, and explicit `atomic_at_current_evidence` outcomes;
- independent 0.4 target-design workspace/revision/operation stores with `des-*` identity enforcement;
- observed-baseline cloning, typed intent/feature/Responsibility/Workflow operations, optimistic concurrency,
  immutable revision history, and authorship/rationale audit assets;
- browser target creation, expected-function authoring, Responsibility editing/decomposition, history selection,
  and exact-baseline navigation;
- server-calculated target-minus-baseline semantic diffs with mandatory acceptance criteria;
- human-only browser approval outside the MCP tool graph, locked reviewed revisions, and auditable approval assets;
- deterministic `ImplementationChangeBundle` export with exact coordinates, semantic operations, bounded source
  context, acceptance checks, and a coding-Agent prompt that grants no model-store authority;
- optional comparison against a later observed/code coordinate with explicit matched, missing,
  unexpected, ambiguous, and stale claims;
- human-only comparison decisions outside the MCP tool graph, with evidence reports and
  decisions stored as immutable audit assets;
- desktop and mobile Understand/Design mode boundary;
- real-browser verification of current, refinement, atomic, parent-return, design, review/context-export,
  optional later comparison, and mobile flows.

The immutable data primitives are implemented. The next slice is the compact Agent MCP surface, authenticated
browser HTTP surface, directly embedded UA Dashboard, and a persistent runner that invokes UA incrementally. The
current CLI still imports externally completed UA JSON.

## 1. Target vertical loop

```text
user asks to understand or starts design
  → capture full Git snapshot
  → run pinned Understand Anything outside the web request
  → import and validate UA JSON
  → publish immutable UA snapshot
  → project evidence-backed observed revision
  → browse current functions and recursive structure read-only
  → create a design workspace from an observed baseline
  → edit/review target behavior
  → freeze the reviewed semantic diff as implementation context
  → coding Agent implements
  → stop

later user asks to understand or design
  → incremental refresh when code changed
  → publish real structure from code
  → optionally compare it with the historical target
```

The loop is delivered in thin vertical increments. Existing 0.3 data remains readable throughout. No migration step relabels legacy human-authored data as current-system truth.

## 2. Delivery sequence

### Increment A — trusted observation foundation

Deliverables:

1. add full-repository scope to `CodeSnapshot` while retaining the legacy backend-only default;
2. model the current UA `KnowledgeGraph` JSON contract used by CoIntent;
3. validate graph identity, Git coordinate, source paths, line ranges, IDs, and edges;
4. store a content-addressed immutable `UnderstandAnythingSnapshot` in SQLite metadata plus JSON assets;
5. expose operator CLI import and read-only repository methods;
6. project Domain → Flow → Step into an immutable observed graph using only resolvable source evidence;
7. expose observation coordinate and observed revision through read-only MCP/HTTP APIs;
8. test deterministic import, invalid input rejection, idempotency, and absence of mutation APIs.

Exit criteria:

- the same input imports to the same snapshot and observed revision IDs;
- a clean Git mismatch fails;
- unsafe or unknown file paths fail;
- dangling edges and duplicate IDs fail;
- evidence-free branches are diagnosed and omitted;
- published rows cannot be updated through product methods;
- every rendered observed node returns at least one source binding.

### Increment B — two product modes

Deliverables:

1. add durable `/understand` and `/design` browser modes;
2. use one shared capability-left / graph-right visual grammar;
3. make Understand load only observation APIs and render no semantic edit action;
4. identify snapshot, commit, UA version, coverage, and staleness in the header;
5. place legacy 0.3 models under Design and label their baseline provenance honestly;
6. preserve semantic focus when moving between tabs where a lineage link exists;
7. add evidence drawer navigation to exact source lines.

Exit criteria:

- direct navigation and refresh preserve the active tab;
- user and Agent cannot mutate observed nodes through either public surface;
- no-observation projects show an actionable empty state rather than a legacy design;
- mode is distinguishable without relying on color.

### Increment C — recursive understanding

**Checkpoint:** delivered in the current working slice.

Deliverables:

1. introduce bounded `ObservationExpansionRequest` with only project, revision, node, and depth parameters;
2. select a bounded UA subgraph for the requested node;
3. publish a child `ObservedModelRevision` with `parent_revision_id` and `refinement_of_node_id`;
4. cache by UA snapshot, node, depth, and projector version;
5. expose coverage deltas and preserve the parent revision unchanged.

Exit criteria:

- request payload contains no replacement nodes or edges;
- repeating a request is idempotent;
- expansion cannot escape the selected UA snapshot;
- breadcrumb navigation can return to every parent semantic level.

### Increment D — independent target design

**Checkpoint:** delivered in the current working slice.

Deliverables:

1. add separate design workspace/revision/operation stores;
2. seed a workspace from an explicit observed revision by cloning values into `des-` identities;
3. support intent, responsibility, workflow, and expected-function operations;
4. validate graph structure after every immutable revision;
5. retain authorship and rationale for every operation;
6. keep observed IDs illegal as design mutation targets.

Exit criteria:

- design editing never writes an observation table or asset;
- undo/history creates or selects revisions instead of mutating history;
- a workspace always exposes its exact observed baseline;
- legacy designs remain marked `legacy-unverified` until rebased.

### Increment E — review and implementation export

**Checkpoint:** delivered in the current working slice.

Deliverables:

1. calculate semantic target-minus-baseline changes;
2. require acceptance criteria for material changes;
3. provide human approval separate from Agent proposal;
4. export a content-addressed `ImplementationChangeBundle` containing coordinates, operations, evidence context, and acceptance checks;
5. provide a coding-Agent prompt without granting database mutation authority.

Exit criteria:

- draft or stale designs cannot export silently;
- layout-only changes never enter the implementation bundle;
- export is deterministic and portable;
- approval actor and timestamp are auditable.

### Increment F — optional later comparison primitives

**Checkpoint:** delivered in the current working slice.

Deliverables:

1. ingest a later user-requested Git/UA snapshot;
2. optionally compare the historical target with a newly projected observed revision;
3. classify matched, missing, unexpected, ambiguous, and stale claims;
4. keep any human comparison conclusion explicit;
5. link an optional human interpretation to the implementation context without rewriting either input.

Exit criteria:

- code change alone never triggers analysis or marks a design converged;
- uncertainty remains explicit;
- all comparison claims link to new-code evidence;
- failed comparison leaves the previous current observation intact.

## 3. Backend construction order

Within each increment, use this dependency order:

1. immutable Pydantic contracts and validation;
2. content IDs and canonical serialization;
3. additive SQLite tables and foreign keys;
4. repository command/query boundary;
5. CLI/operator workflow;
6. MCP read/request tools;
7. REST routes;
8. frontend state and rendering;
9. fixture, integration, authorization, and regression tests;
10. Idea Factory acceptance run.

Database changes are additive until Increment F. The old `model_versions`, `proposals`, `mapping_revisions`, and `change_sets` are not reused for observations.

## 4. Increment A data contracts

### Full CodeSnapshot

Add `scope: backend | full` with `backend` as the compatibility default. UA import requires `full`. Artifact hashes remain the proof that a path belongs to the captured repository coordinate.

### UnderstandAnythingSnapshot

```yaml
schema_version: cointent.ua-snapshot/0.1
id: ua-<content digest>
project_id: ...
code_snapshot_id: ...
ua_tool_revision: ...
ua_graph_version: ...
knowledge_graph: ...
domain_graph: ... | null
coverage:
  code_snapshot_files: 0
  ua_located_nodes: 0
  ua_unlocated_nodes: 0
  domain_nodes: 0
  evidence_backed_domain_nodes: 0
diagnostics: []
content_digest: ...
created_at: ...
```

The ID hashes canonical graph content, snapshot coordinate, and pinned UA revision. Import time is excluded from identity.

### ObservedModelRevision

```yaml
schema_version: cointent.observed-model/0.4
id: obs-<content digest>
project_id: ...
code_snapshot_id: ...
ua_snapshot_id: ...
parent_revision_id: null
refinement_of_node_id: null
projector_version: ua-domain-v1
capabilities: []
responsibilities: []
bindings: []
diagnostics: []
content_digest: ...
created_at: ...
```

Every observed node carries one or more `EvidenceBinding` records. A semantic Step binding records both its semantic UA node and the overlapping structural UA node IDs from `knowledge-graph.json`. Domain and Flow nodes inherit the unique union of descendant Step evidence. Native UA IDs are evidence references scoped by `ua_snapshot_id`, not globally stable CoIntent IDs.

## 5. Public authority matrix for the on-demand surface

The browser uses authenticated HTTP and the conversational Agent uses CoIntent MCP. Their permissions derive
from authenticated principals rather than caller-supplied actor fields, and both enforce the same aggregate
boundaries.

| Operation | Browser human (HTTP) | Agent (MCP) | Observation worker |
|---|---:|---:|---:|
| List projects and inspect state | yes | yes | read |
| Request an idempotent refresh | yes | yes | run |
| Read one current/design level | yes | yes | read |
| Publish UA or an observed revision | no API | no API | yes |
| Insert/update/delete an observed node | no API | no API | no public API |
| Revise a target-design draft | yes | scoped proposal | no |
| Finalize exact implementation context | yes | after explicit user instruction | no |
| Compare a historical design with current | yes | yes | read inputs |

The hidden worker accepts a trusted job coordinate and completed UA artifacts; it never accepts a replacement
graph from a business client. Browser HTTP and public MCP methods accept identifiers, intent, and bounded
navigation parameters, never native graph payloads. The directly embedded UA Dashboard receives only read-only
artifact/source endpoints and exposes no Agent MCP Role.

## 6. Test fixtures

Keep compact, hand-audited fixtures in `tests/fixtures/ua/`:

- valid full knowledge and domain graphs;
- knowledge-only graph;
- commit mismatch;
- unknown and unsafe paths;
- invalid line ranges;
- duplicate node IDs;
- dangling edge endpoints;
- domain branch without source evidence;
- repeated import with different JSON key order.

The fixture schema follows UA plugin 2.9.6 at commit `5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc`, pinned in ADR-0001. Upstream upgrades require updating the pin, fixtures, validation expectations, and a golden projection diff in one change.

## 7. Release gates

The project flag `observation_v04_enabled` remains false until Increment A passes on Idea Factory. Increment B may ship behind the flag. The default switches only after:

- the latest clean Idea Factory commit has a valid full snapshot and UA snapshot;
- observed graph coverage is reviewed;
- read-only authority tests pass for browser and MCP;
- frontend empty, stale, partial, and current states pass;
- existing 0.3 tests remain green.

The on-demand runner additionally must prove that an unchanged repository skips UA and domain work, a changed
repository with valid UA state uses incremental `/understand`, a missing or invalid cache reports a full
fallback, starting design refreshes the baseline first, and coding completion schedules no work.

The UA Dashboard release gate is defined in [the integration design](ua-dashboard-integration.md): exact
snapshot/source delivery, direct HTTP loading, forward/reverse ImplementationRef focus, and absence of UA MCP or
graph-mutation controls must pass before the embedded view is enabled.

Rollback hides the 0.4 routes and returns to legacy Design. It never converts an observed revision into a 0.3 editable model.
