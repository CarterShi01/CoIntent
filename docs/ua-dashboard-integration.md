# CoIntent × Understand Anything Dashboard Integration

**Status:** accepted product and architecture design
**Applies to:** CoIntent 0.4+ Understand current, Design future baseline inspection, browser HTTP surface, and UA release packaging
**Upstream baseline:** Understand Anything 2.9.6 at commit `5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc`
**Related decisions:** [on-demand product flow](on-demand-product-flow.md), [CoIntent 0.4 design](design-v0.4.md), [UA engine ADR](adr-0001-codemap-engine.md)

## 1. Decision summary

CoIntent will integrate the official Understand Anything Dashboard directly as a read-only embedded frontend.
It will run as an isolated iframe/microfrontend inside **Understand current → Implementation map**. CoIntent will
not rebuild a second code-map explorer and will not copy individual UA graph components into its main React tree.

The integration has three separate communication boundaries:

```text
Human browser
  → CoIntent authenticated HTTP
  → CoIntent System view or embedded UA Dashboard

Conversational/coding Agent
  → CoIntent MCP
  → current semantic understanding and target-design operations

Observation pipeline
  → pinned Understand Anything CLI/skills
  → UA JSON artifacts
  → CoIntent validation, immutable storage, and projection
```

The browser does not load UA data through MCP. UA does not need to provide an MCP server, and CoIntent will not
adopt a community UA MCP server. MCP remains the Agent-facing product protocol. HTTP remains the browser-facing
rendering and data protocol.

The two top-level product tabs remain unchanged:

```text
[ Understand current ] [ Design future ]
```

The embedded code map is a subview of Understand current, not a third product process:

```text
Understand current
  ├── System view          CoIntent functions, Responsibilities, and Workflows
  └── Implementation map  embedded UA Dashboard and source viewer
```

## 2. Product boundary

UA and CoIntent answer adjacent questions at different abstraction levels.

| Dimension | Understand Anything | CoIntent |
|---|---|---|
| Primary question | How is the codebase physically and logically assembled? | What behavior does the system provide, and what structure should it have next? |
| Primary objects | files, functions, classes, modules, endpoints, services, dependencies | system functions, Responsibilities, Workflows, contracts, expected functions |
| Main audience | developers and engineers onboarding to code | product owners, architects, developers, and Agents |
| Current-state role | generates the upstream code map | validates and projects a product-semantic current model |
| Design role | none in the CoIntent workflow | owns independent target structure, revisions, diff, and implementation context |
| Typical interaction | search, navigate relationships, find paths, inspect source, view code diff | learn one semantic level, design structure, review semantic diff, constrain implementation |
| Mutation authority | pipeline regenerates UA artifacts | observed truth is immutable; only target design is editable |

The complete current-system path is:

```text
Code
  → UA implementation map
  → CoIntent observed structure graph
  → current system functions
```

The browser lets a user travel both directions:

```text
System Function
  → Responsibility / Workflow
  → UA file, class, function, endpoint, and dependency
  → exact source

exact source / UA node
  → related observed Responsibilities
  → related current system functions
```

UA's optional domain graph is an upstream generated interpretation. CoIntent may expose it inside the embedded
viewer as **Raw UA domain analysis**, but it is not the CoIntent System view and is never the authority for target
design. Only an evidence-validated CoIntent projection becomes an ObservedModelRevision.

## 3. User experience

### 3.1 Understand current — System view

System view remains the default. It preserves the shared CoIntent layout:

```text
┌ Current system functions ┬ Observed structure ┬ Details and evidence ┐
│ function list            │ one graph level    │ contract             │
│                          │                    │ implementation refs  │
│                          │                    │ freshness/coordinate │
└──────────────────────────┴────────────────────┴──────────────────────┘
```

The observed structure is read-only. A user can open one semantic level, inspect evidence, request a bounded
deeper projection, or open a concrete implementation reference in the UA code map.

Agent reads remain page-equivalent to this semantic view: current functions, one selected Responsibility, its
direct children and local edges, bounded evidence, and continuation identifiers. The embedded UA Dashboard is a
human visual explorer and does not expand the public MCP response into a raw full-graph dump.

### 3.2 Understand current — Implementation map

Implementation map embeds the pinned UA Dashboard and retains the developer-facing functions that UA already
implements:

- structural graph and layer navigation;
- file, class, function, endpoint, service, and dependency exploration;
- search and filters;
- file explorer;
- node details and relationship lists;
- path finding;
- source preview with exact line highlighting;
- layout controls and mobile behavior;
- code-change diff overlay where an exact previous UA coordinate exists.

The CoIntent shell remains visible above the iframe and owns:

- project selection;
- the Understand current / Design future tabs;
- System view / Implementation map selection;
- the selected CodeSnapshot, UA snapshot, and observed revision badges;
- refresh progress and errors;
- authentication and authorization;
- navigation back to a related System Function or Responsibility.

UA controls that imply ownership of CoIntent state are hidden, disabled, or relabeled:

- no UA-triggered scan or auto-update control;
- no second Agent chat surface;
- no instruction to edit or repair `knowledge-graph.json` directly;
- no independent project selector or authentication screen;
- no freshness result calculated against an unpinned working tree;
- no presentation of raw UA domain output as CoIntent current truth;
- no target design, target diff, or implementation handoff inside UA.

Graph validation issues become either **Regenerate understanding** or **Report analyzer issue**. They never become
an instruction for a user or Agent to modify an imported graph artifact.

### 3.3 Direct semantic-to-implementation navigation

Each concrete implementation reference in the System view is clickable:

```text
Implementation references · 4

Primary
  login() · src/auth.ts:42–86               [Open in code map]

Supporting
  SessionStore · src/session.ts             [Open]
  POST /login · src/routes.ts               [Open]
  UserRepository.find()                     [Open]

                                            [Show all in code map]
```

Opening one reference:

```text
1. resolve the exact UA and code coordinates from the reference;
2. create or reuse a read-only viewer session for those coordinates;
3. switch to Understand current → Implementation map;
4. wait until the embedded viewer reports that its graph is ready;
5. focus the preferred structural UA node;
6. reveal its layer/container and clear filters that hide it;
7. select and center the node;
8. show its NodeInfo panel;
9. open or offer the exact source range.
```

**Show all in code map** focuses the primary node and highlights every supporting UA node. It does not attempt to
fit unrelated branches or replace UA's graph navigation.

### 3.4 Reverse implementation-to-semantic navigation

When a user selects a UA node, the embedded viewer reports the selected native node ID to CoIntent. CoIntent uses
the reverse mapping for the same UA snapshot and displays:

```text
This implementation supports

• Authenticate user
  ↳ Validate credentials

• Maintain user session
  ↳ Create session token

[Back to system structure]
```

Selecting a related semantic item returns to System view at the correct ObservedModelRevision and focus ID.

### 3.5 Stable browser deep links

The outer CoIntent URL captures semantic navigation state without exposing the short-lived viewer token:

```text
/understand
  ?project=idea-factory
  &view=implementation
  &observed_revision=observed-...
  &ua_snapshot=ua-...
  &node=function%3Asrc%2Fauth.ts%3Alogin
  &from=obs-responsibility-...
```

On navigation or reload, CoIntent authenticates the user, validates the coordinate chain, creates a new viewer
session, and restores the focus. History back returns to the originating Responsibility rather than resetting the
workspace.

### 3.6 Design future baseline inspection

Design future retains the matching CoIntent layout:

```text
┌ Expected functions ┬ Target structure graph ┬ Design details and diff ┐
│ desired behavior   │ target Responsibilities│ rationale               │
│                    │ and Workflows           │ acceptance criteria     │
│                    │                         │ baseline references     │
└────────────────────┴─────────────────────────┴──────────────────────────┘
```

A target node can expose **View baseline implementation** when it has a baseline link. That action opens the UA
Dashboard at the workspace's frozen baseline UA snapshot. It never silently opens the newest current snapshot.
New target nodes without a baseline show no fabricated implementation reference.

The complete design flow is:

```text
human intent
  → expected functions
  → target structure graph
      ├── target Responsibilities
      ├── target Workflows and edges
      ├── inputs, outputs, and data members
      ├── expected-function mappings
      ├── rationale and acceptance criteria
      └── links to baseline observed nodes where applicable
  → user reviews the target structure graph
  → semantic diff against the exact observed baseline
  → implementation context
  → coding Agent
  → code
```

Baseline UA relationships and source are supporting evidence while the target graph is designed:

```text
target structure node
  → baseline link
  → observed Responsibility
  → ImplementationRef
  → UA code map and exact source
```

The semantic diff is derived from the complete target structure graph. It is not a diff of one Responsibility.
The target drawing remains an immutable historical design version after handoff and never merges into observed
truth.

## 4. Integration architecture

### 4.1 Direct frontend reuse

CoIntent packages the official UA Viewer build produced from the same pinned revision as the analyzer contract.
The complete Dashboard runs in an iframe so its React, Tailwind, Zustand, React Flow, ELK, Dagre, Graphology,
styles, keyboard shortcuts, and layout workers stay isolated from the CoIntent application.

```text
CoIntent AppShell
└── UnderstandRoute
    ├── SystemView
    └── UaImplementationMap
        ├── CoordinateHeader
        ├── SemanticReturnPanel
        └── iframe: pinned UA Dashboard build
```

This is direct integration of UA's frontend. CoIntent does not reproduce GraphView, NodeInfo, FileExplorer,
PathFinder, CodeViewer, filters, or layout logic.

The upstream Dashboard is not currently an exported embeddable React library and owns a global store and app
shell. An iframe is therefore the stable integration unit. Importing its private workspace package into
CoIntent's React tree would create unnecessary build, CSS, dependency, state, and upgrade coupling.

### 4.2 Minimal downstream patch

The first usable embed can run the upstream viewer with only HTTP route adaptation. Production integration keeps
a small, explicit patch set over the pinned UA source:

1. make graph and file endpoint base URLs configurable;
2. accept the focus bridge protocol after graph validation succeeds;
3. emit selected-node events to the host;
4. accept an optional source line-range override;
5. hide or relabel the conflicting controls listed in section 3.2;
6. render an embedded mode without the standalone token gate and duplicate outer shell.

The patch must not fork UA graph semantics or layout algorithms. If upstream later exports an embedded Dashboard
component with equivalent hooks, CoIntent may replace the patch with that upstream API as an ordinary dependency
upgrade.

### 4.3 Version and license handling

The viewer, graph schema, import validator, and UA runner are upgraded as one unit. The release records:

- UA version and Git commit;
- viewer artifact digest;
- CoIntent integration-patch revision;
- graph schema/normalizer version;
- license and attribution files.

The UA repository is MIT licensed. Its license and copyright notice ship with the embedded assets. A UA upgrade
requires graph fixtures, a golden projection review, viewer build verification, focus-bridge tests, and an
Idea Factory acceptance pass.

No generic analyzer or dashboard adapter framework is introduced. This is one concrete integration with the only
0.4 code-map engine.

## 5. Browser HTTP contract

### 5.1 Viewer session

The authenticated browser creates a scoped viewer session:

```http
POST /api/projects/{project_id}/ua-viewer-sessions
Content-Type: application/json

{
  "observed_revision_id": "observed-...",
  "ua_snapshot_id": "ua-..."
}
```

The server verifies the full coordinate chain and returns:

```json
{
  "viewer_url": "/ua-viewer/?session=opaque-short-lived-token",
  "project_id": "idea-factory",
  "observed_revision_id": "observed-...",
  "ua_snapshot_id": "ua-...",
  "code_snapshot_id": "snapshot-...",
  "expires_at": "..."
}
```

The opaque token is read-only, short-lived, and bound to one authenticated user, project, UA snapshot, and code
snapshot. It is not stored in browser history after the iframe initializes and is never placed in a shareable
outer URL.

### 5.2 Viewer data

The embedded viewer loads its normal artifacts over HTTP from a configurable, namespaced base:

```text
GET /internal/ua-viewer-data/{session}/knowledge-graph.json
GET /internal/ua-viewer-data/{session}/domain-graph.json
GET /internal/ua-viewer-data/{session}/meta.json
GET /internal/ua-viewer-data/{session}/config.json
GET /internal/ua-viewer-data/{session}/diff-overlay.json
GET /internal/ua-viewer-data/{session}/staleness.json
GET /internal/ua-viewer-data/{session}/file-content.json?path=...
```

Graph endpoints return the validated immutable assets stored for `ua_snapshot_id`, never a mutable `.ua` file
from a current working directory. Missing optional artifacts return the same shapes/statuses the pinned viewer
expects.

`staleness.json` is derived from CoIntent coordinates. The embedded viewer does not run Git freshness checks
against an arbitrary process working directory.

### 5.3 Exact source content

Source preview must correspond to `code_snapshot_id`. A request is accepted only when the normalized path exists
in both the UA graph and the full CodeSnapshot manifest.

The server reads the file from the exact captured Git commit or a content-addressed source asset:

```text
viewer file request
  → validate session and normalized relative path
  → verify path belongs to UA snapshot and CodeSnapshot
  → read Git blob at CodeSnapshot.git_commit, or matching content digest
  → return source and language metadata
```

The server never falls back to the current working-tree file for a historical snapshot. If the exact blob is not
available, source preview fails explicitly while the graph remains usable.

## 6. ImplementationRef and mapping model

### 6.1 Contract

`ImplementationRef` is the stable bridge between a CoIntent semantic subject and UA/source evidence:

```yaml
ImplementationRef:
  id: implementation-ref-...
  project_id: idea-factory
  observed_revision_id: observed-...
  subject_kind: system_function | responsibility
  subject_id: obs-responsibility-...

  ua_snapshot_id: ua-...
  code_snapshot_id: snapshot-...
  graph_kind: structural

  semantic_ua_node_id: step-...       # optional domain/flow evidence
  structural_ua_node_ids:
    - function:src/auth.ts:login
    - file:src/auth.ts
  preferred_focus_node_id: function:src/auth.ts:login

  file_path: src/auth.ts
  line_range: [42, 86]
  symbol: login
  role: primary | supporting
  resolution: exact_symbol | exact_span | enclosing_symbol | file_fallback | inherited
```

Native UA IDs are always scoped by `ua_snapshot_id`. An implementation reference without that coordinate is
invalid. `observed_revision_id`, `ua_snapshot_id`, and `code_snapshot_id` must form the same validated lineage.

### 6.2 Projection rules

The projector creates refs from the same evidence corroboration that permits an observed node to publish:

- retain the semantic UA node when a Domain/Flow/Step contributes meaning;
- retain every corroborating structural node from `knowledge-graph.json`;
- prefer a callable or endpoint whose source span exactly overlaps the evidence;
- otherwise prefer the smallest enclosing class/module;
- otherwise use the exact file node;
- never invent a symbol or UA node from a plausible path;
- label inherited Domain/Flow evidence so the UI does not imply a direct symbol mapping;
- select at most one deterministic primary ref per semantic subject;
- expose ambiguity and multiple supporting refs instead of silently choosing by name similarity.

The deterministic focus priority is:

1. exact function/method/callable overlap;
2. exact endpoint, handler, service, or class overlap;
3. smallest enclosing structural node;
4. exact file node;
5. no focus node, with an evidence-unavailable state.

### 6.3 Reverse index

CoIntent maintains or derives this immutable reverse lookup:

```text
(ua_snapshot_id, structural_ua_node_id)
  → ImplementationRef IDs
  → observed Responsibility IDs
  → current system function IDs
```

Reverse results are returned only for the same snapshot as the embedded viewer. A name match across UA snapshots
is never treated as identity.

## 7. Focus bridge

### 7.1 Transport

The parent and iframe communicate through versioned browser `postMessage` events. This is UI coordination, not
MCP and not a graph mutation API.

Every event contains `protocol_version`, `request_id`, and `ua_snapshot_id`. Both sides validate the expected
origin, iframe window, session, protocol version, and snapshot before acting.

Host to viewer:

```ts
type CoIntentToUaMessage =
  | {
      type: "cointent.ua.focus-node";
      protocolVersion: 1;
      requestId: string;
      uaSnapshotId: string;
      nodeId: string;
      lineRange?: [number, number];
      openSource?: boolean;
    }
  | {
      type: "cointent.ua.focus-nodes";
      protocolVersion: 1;
      requestId: string;
      uaSnapshotId: string;
      primaryNodeId: string;
      nodeIds: string[];
    }
  | {
      type: "cointent.ua.clear-focus";
      protocolVersion: 1;
      requestId: string;
      uaSnapshotId: string;
    };
```

Viewer to host:

```ts
type UaToCoIntentMessage =
  | {
      type: "ua.cointent.ready";
      protocolVersion: 1;
      requestId: string;
      uaSnapshotId: string;
    }
  | {
      type: "ua.cointent.focus-result";
      protocolVersion: 1;
      requestId: string;
      uaSnapshotId: string;
      requestedNodeId: string;
      focusedNodeId?: string;
      status: "focused" | "fallback" | "not_found";
    }
  | {
      type: "ua.cointent.node-selected";
      protocolVersion: 1;
      requestId: string;
      uaSnapshotId: string;
      nodeId: string;
    };
```

### 7.2 Initial and repeated focus

The host queues focus until it receives `ua.cointent.ready`. The viewer emits ready only after graph validation,
store initialization, layer indexing, and initial layout are complete.

For a structural focus, the viewer:

1. selects Structural view;
2. enables the node's type if a filter hides it;
3. navigates to the owning layer;
4. expands the containing graph container;
5. calls UA's existing `navigateToNode` behavior;
6. selects and centers the node after measurement/layout;
7. highlights one-hop neighbors using UA's existing selection behavior;
8. applies the requested line range when source is opened;
9. emits a focus result.

Subsequent refs reuse the existing iframe and send another focus event. They do not reload the whole UA graph.

### 7.3 Fallback behavior

If `preferred_focus_node_id` is absent in the pinned graph, the viewer tries the remaining structural IDs in the
ref, then the exact file node. It reports `fallback` and CoIntent explains what was selected. If no node exists,
the user remains in System view with an actionable mapping diagnostic; CoIntent never opens the newest UA graph
as an implicit fallback.

## 8. MCP and Role impact

The compact CoIntent MCP surface remains Agent-facing and unchanged:

```text
cointent
├── project-context
├── understand-current
└── design-future
```

The Agent reads current functions, the CoIntent semantic structure, bounded evidence coordinates, and design
objects through these Roles. It does not drive UA pan/zoom, iframe selection, filters, or source modals.

No UA-specific MCP Role or public Tool is added. In particular, there is no:

- UA graph server exposed directly to the Agent;
- `read-implementation-level` Tool solely for mirroring the visual Dashboard;
- Tool for changing native UA graph content;
- dependency on a community UA MCP package.

A coding Agent already has repository access when implementing code. The implementation context may contain
bounded CoIntent evidence coordinates, but it does not need an MCP wrapper around the complete UA Dashboard.

## 9. Authority and lifecycle invariants

1. Current truth still originates only from code → UA → validated CoIntent projection.
2. UA Dashboard and its HTTP endpoints are read-only views of immutable stored artifacts.
3. A user, browser, or iframe cannot upload or mutate native graph JSON. A code-local Agent may transfer an opaque
   native bundle only inside an active coordinate-bound refresh; staging cannot publish or replace a graph.
4. Graph issues trigger regeneration/reporting, never direct repair of observed truth.
5. Refresh runs only when a user asks to understand or begins a new design.
6. Unchanged code skips UA work; changed code uses UA incremental analysis when valid prior state exists.
7. Coding completion schedules no scan, verification, or convergence workflow.
8. Design future always starts from the latest valid root Observation after refresh.
9. A target structure graph never becomes or merges into the observed graph.
10. Design baseline inspection always opens the frozen baseline UA snapshot.
11. A later target-versus-current comparison is optional and read-only.
12. Structural implementation may differ from the target drawing when expected behavior is satisfied.

## 10. Failure and edge states

| Condition | Product behavior |
|---|---|
| No valid UA snapshot | Implementation map says to ask the connected Agent to update understanding. |
| Refresh running | Existing valid map remains visible with a stale/running badge; no partial artifact is mounted. |
| UA import/projection failed | Last valid Observation remains visible as stale; failed artifacts cannot open as current. |
| Viewer session expired | Host creates a new session for the same immutable coordinates and restores focus. |
| Preferred UA node missing | Try supporting structural IDs, then exact file; report fallback. |
| All mapped nodes missing | Keep the semantic node visible and expose a mapping diagnostic. |
| Multiple plausible primary refs | Show ambiguity and require the user to choose; do not pick by display name alone. |
| Exact historical source unavailable | Keep graph navigation available and show **Source unavailable for this snapshot**. |
| Baseline design coordinate stale | Historical baseline UA remains viewable; design finalization requires an explicit rebase/new workspace according to product rules. |
| UA viewer build/schema mismatch | Refuse to mount it and report a release/configuration error. |
| Embedded viewer crashes | System view and all CoIntent semantic data remain usable. |

## 11. Frontend ownership and state

CoIntent owns durable and route-level state:

```text
projectId
processTab: understand | design
understandSubview: system | implementation
observedRevisionId
uaSnapshotId
originSemanticId
requestedUaNodeId
viewerSession
```

UA owns ephemeral code-map state inside the iframe:

```text
viewport
layout
expanded containers
node filters
search query/results
selected UA node
path finder state
source viewer state
```

CoIntent persists only the outer navigation coordinate. It does not mirror every UA viewport or panel action.
Switching back to System view preserves the iframe for the current session when memory permits so repeated
implementation inspection does not reload the graph.

## 12. Delivery sequence

### Phase A — direct read-only embed

- build and package the pinned official UA Viewer;
- serve it as an isolated iframe frontend;
- implement scoped viewer sessions;
- serve immutable UA JSON from CoIntent storage;
- serve exact-snapshot source content;
- add System view / Implementation map selection;
- retain the UA viewer's normal search, graph, file explorer, path, and source features;
- hide scan, repair, chat, and conflicting shell controls.

Exit: a developer can open the exact current UA map inside CoIntent without MCP or a separate terminal viewer.

### Phase B — first-class ImplementationRef and forward focus

- persist/return the complete ImplementationRef coordinate;
- implement deterministic primary/supporting selection;
- add implementation-reference lists to System view;
- add the versioned host/viewer focus bridge;
- restore focus from a shareable CoIntent deep link;
- support **Show all in code map**.

Exit: every resolvable current semantic node opens the correct pinned UA node and source range.

### Phase C — reverse navigation and Design baseline

- build the UA-node-to-semantic reverse index;
- emit UA selected-node events;
- show related Responsibilities and current functions;
- add **Back to system structure**;
- add **View baseline implementation** to linked target nodes;
- guarantee that design inspection uses the frozen baseline coordinate.

Exit: navigation is bidirectional and works from both top-level product processes without mutating either graph.

### Phase D — upgrade and production hardening

- make the UA build and license part of release artifacts;
- add CSP/frame restrictions and origin validation;
- exercise large-graph loading and iframe recovery;
- verify mobile and keyboard navigation across the host/viewer boundary;
- add UA upgrade compatibility and golden focus tests;
- complete an Idea Factory end-to-end acceptance run.

## 13. Test strategy

### Coordinate and authority

- reject a viewer session when Observation, UA, and code coordinates do not share lineage;
- serve graph assets only from the session's immutable UA snapshot;
- reject unsafe/absolute/unmapped source paths;
- prove historical source is read from the captured commit/content digest;
- prove the iframe and browser have no observed-graph mutation endpoint;
- prove a target baseline opens its frozen UA snapshot after current code advances.

### Focus and mapping

- focus an exact function ref and highlight its source span;
- focus an endpoint/class ref;
- fall back deterministically to an enclosing file;
- show primary and supporting refs without losing their roles;
- reject a cross-snapshot native node ID;
- restore focus after session renewal and browser reload;
- clear a filter hiding the requested node;
- expand a collapsed container before centering;
- focus multiple refs with one primary;
- return from a selected UA node to every linked semantic subject.

### Product flow

- the only top-level tabs remain Understand current and Design future;
- System view is the default understanding subview;
- the embedded Dashboard never exposes graph repair or scan controls;
- Agent MCP discovery contains no UA Dashboard or UA graph Role;
- an Agent current read remains bounded to one CoIntent semantic page-equivalent level;
- design follows expected functions → target structure graph → review → semantic diff → implementation context;
- implementation-context creation and code completion schedule no scan;
- a target graph never appears as current truth.

### Compatibility

- build the exact pinned UA Dashboard and viewer artifact;
- validate the pinned knowledge and domain fixtures in the embedded build;
- verify every expected viewer HTTP endpoint and optional-404 behavior;
- verify focus bridge compatibility after a UA dependency upgrade;
- ensure UA CSS, keyboard shortcuts, errors, and crashes cannot break the CoIntent AppShell.

## 14. Acceptance criteria

This integration is complete when:

1. a user can switch between CoIntent System view and the directly embedded UA Implementation map without
   leaving Understand current;
2. the embedded frontend is the official pinned UA Dashboard with a small documented integration patch, not a
   reimplementation of its code-map features;
3. browser graph/source loading uses authenticated HTTP and no browser request is routed through MCP;
4. CoIntent exposes no UA MCP server or UA-specific public Agent Role;
5. the UA graph, source preview, observed semantic graph, and header badges always share one validated immutable
   coordinate chain;
6. clicking a concrete ImplementationRef focuses the correct UA node, reveals it through layers/containers, and
   opens the exact source range;
7. multiple implementation refs retain deterministic primary/supporting meaning and can be highlighted together;
8. selecting a UA node reveals its related CoIntent Responsibilities and current system functions;
9. browser deep links restore the same semantic origin and UA focus without exposing viewer credentials;
10. Design future exposes the expected function → target structure graph → review → semantic diff → implementation
    context sequence explicitly;
11. target nodes can inspect only their exact baseline UA implementation and cannot modify observed truth;
12. UA scan/repair/chat/auto-update behavior cannot bypass CoIntent's on-demand pipeline and authority boundary;
13. coding completion causes no automatic refresh, and subsequent current truth is produced only by a later
    user-requested code → UA → projection run.

## 15. Explicit decisions and non-goals

- Directly embed the UA Dashboard; do not recreate its code-map frontend.
- Keep it as an isolated microfrontend rather than importing its private application package into CoIntent's
  React component tree.
- Use HTTP for browser data and MCP for Agent product operations.
- Do not require, build, or integrate a UA MCP server.
- Keep CoIntent's three public Agent Roles compact; add no visual-dashboard Role.
- Keep Understand current and Design future as the only top-level tabs.
- Put UA under Understand current as Implementation map.
- Treat UA domain output as visible upstream analysis, not CoIntent observed truth.
- Preserve the code → UA → observed structure → current functions authority chain.
- Make ImplementationRef and bidirectional focus part of the initial product contract, not optional polish.
- Preserve target structure as a separate, versioned drawing and derive diff from the complete graph.
- Keep the single-engine decision; introduce no speculative multi-engine or multi-dashboard abstraction.
