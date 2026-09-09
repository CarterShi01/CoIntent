# CoIntent On-Demand Product Flow and MCP Surface

**Status:** accepted product-experience contract
**Applies to:** the default 0.4+ user journey and public MCP capability graph
**Principle:** understand on demand, design on demand.

## 1. Product posture

CoIntent is not an always-on task manager and does not require daily use. A user invokes it for one of two
reasons:

1. **Understand current** — refresh and inspect what the code implements now.
2. **Design future** — first refresh current truth, then create and review a separate target structure before
   asking a coding Agent to implement it.

No post-coding scan runs automatically. A later request to understand or design triggers the next refresh. A
historical target drawing may then be compared with the newly observed implementation on demand, but it is
never merged, promoted, or copied into current truth.

```text
CURRENT TRUTH
Code → CodeSnapshot → Understand Anything → ObservedModelRevision

TARGET DRAWING
Human intent → expected functions → target structure graph → review → semantic diff → implementation context → coding Agent

OPTIONAL LATER COMPARISON
Historical DesignRevision ↔ later ObservedModelRevision
```

## 2. User journeys

### 2.1 Learn the current system

```text
User asks to refresh or understand a project
  → refresh current understanding
  → publish a new Observation only after validation succeeds
  → user opens Understand current, or the Agent reads one page-equivalent level
  → user selects a node to read one level deeper
```

One Agent response must not dump the complete model. It returns the amount visible on one web page:

- all system functions at the current function level;
- the selected Responsibility and its direct child occurrences;
- edges among those direct children;
- a bounded evidence summary and the exact observation coordinate;
- continuation/focus identifiers for deliberate descent.

Grandchildren and unrelated branches require another call. The CoIntent System view and Agent therefore share
the same semantic disclosure budget and navigation model. The human-only UA Implementation map remains a richer
visual code explorer.

### 2.2 Design structure before code

Design begins only after explicit user intent such as “先设计结构，不要开始写代码”.

```text
refresh current understanding
  → require the latest valid root Observation
  → create an independent target workspace from that exact baseline
  → revise expected functions and the target structure graph through conversation
  → compose target Responsibilities, Workflows, contracts, and expected-function mappings
  → review the complete target graph one level at a time in web or Agent
  → preview design-version or target-versus-baseline diff
  → user confirms “按这个结构实现”
  → freeze that DesignRevision and create an implementation context
  → coding Agent designs and changes code under those constraints
  → stop; do not trigger a scan automatically
```

There are two related diff views:

- **revision diff** compares two target drawing revisions for design review;
- **implementation diff** compares the finalized target with its observed baseline and is embedded in the
  coding Agent context.

The implementation context is a constraint and rationale package, not a claim that the target graph already
exists in code.

### 2.3 Compare a historical drawing later

After a later user-triggered refresh, the user may ask how the implementation differs from a historical target.
The comparison is informational. Structural divergence is allowed; it never rewrites either side and does not
automatically create a convergence workflow. Stale code evidence blocks comparison, but a human may accept an
implementation whose internal structure differs while its expected behavior is satisfied.

## 3. Refresh policy

A complete artifact is not the same as a full recomputation. Every published Observation has a complete
repository and graph coordinate, while repeat analysis must use Understand Anything incrementally.

| Condition | Knowledge graph work | Domain graph work | Published result |
|---|---|---|---|
| Code content unchanged | skip UA; zero LLM work | skip | reuse current Observation |
| First run, missing/corrupt UA state, or explicit operator force | `/understand --full` | full `/understand-domain` | new Observation |
| Valid previous UA state and changed code | default incremental `/understand` | full `/understand-domain` | new Observation |
| Any validation or projection failure | do not publish | do not promote partial output | previous Observation remains visible as stale |

The runner must persist or restore the UA state required for incremental updates, including the complete
knowledge graph, metadata, structural fingerprints, configuration, ignore policy, and previous Git coordinate.
It must not add `--full` merely because CoIntent imports a complete final JSON artifact.

Every refresh result reports `unchanged | incremental | full`, changed-file count, UA files re-analyzed,
duration, diagnostics, and the resulting coordinate. Full fallback must carry an explicit reason.

## 4. User-visible actions

The UI exposes product verbs, not lifecycle machinery:

| Tab | Primary actions |
|---|---|
| Understand current | **Update understanding**, **open/down one semantic level**, **view evidence**, **open the UA Implementation map** |
| Design future | **Start structure design**, **revise expected functions/structure**, **view diff**, **implement this design**, **compare a historical design with current** |

“Implement this design” creates the immutable implementation context and hands it to the coding Agent. It does
not change code itself, publish an Observation, or schedule later analysis. Job polling, snapshot import,
projection, approval records, and cache recovery are implementation details rather than additional user actions.

## 5. Public Agent MCP operations

CoIntent MCP is the only product-operation surface for conversational and coding Agents. The browser uses an
authenticated HTTP application surface and directly embeds the read-only UA Dashboard. It does not load visual
UA data through MCP. Browser and Agent surfaces share domain invariants and immutable coordinates without sharing
one transport. Exact Dashboard behavior is specified in [the UA integration design](ua-dashboard-integration.md).

### Project context

| Operation | Purpose |
|---|---|
| `list-projects()` | Find projects available to the caller. |
| `inspect-project-state(project_id)` | Return current code/UA/Observation coordinates, staleness, active target drawings, and allowed next actions. |

### Understand current

| Operation | Purpose |
|---|---|
| `refresh-current-understanding(project_id)` | Start an idempotent refresh job. The server chooses unchanged, incremental, or declared full fallback; callers cannot upload graph content or force recomputation. |
| `inspect-understanding-refresh(job_id)` | Read progress, chosen mode, change counts, diagnostics, and published coordinate. |
| `read-current-level(project_id, focus_id?, observed_revision_id?)` | Return one page-equivalent function/structure level and bounded evidence. |

`read-current-level` is also the descent operation: the caller passes a returned child as the next `focus_id`.
The server resolves the necessary cached projection or bounded refinement. There is no graph-upsert operation.

### Design future

| Operation | Purpose |
|---|---|
| `start-structure-design(project_id, title)` | Create a separate target drawing from the latest valid root Observation after refresh. |
| `read-design-level(workspace_id, focus_id?, design_revision_id?)` | Return one page-equivalent expected-function/target-structure level. |
| `revise-structure-design(workspace_id, base_design_revision_id, operations, rationale)` | Publish one immutable target revision using typed `des-*` operations. |
| `diff-structure-design(workspace_id, from_revision_id?, to_revision_id?)` | Compare target revisions, or default `from` to the exact observed baseline. |
| `create-implementation-context(workspace_id, design_revision_id, expected_diff_digest)` | After explicit user instruction, freeze the drawing and return the portable implementation constraint. |
| `list-structure-design-versions(workspace_id)` | Read drawing history and rationale. |
| `compare-design-to-current(design_revision_id, observed_revision_id?)` | Optionally compare a historical drawing with a later current Observation; never merge them. |

These operations replace a large public lifecycle vocabulary of review, approval, export, implementation,
verification, and convergence tools. Internally those records may remain useful for audit, but users need only
review a drawing, inspect a diff, confirm an implementation context, and optionally compare it later.

## 6. Contexture Role graph

The default capability graph stays aligned with the two product tabs:

```text
cointent
├── project-context
│   ├── list-projects
│   └── inspect-project-state
├── understand-current
│   ├── refresh-current-understanding
│   ├── inspect-understanding-refresh
│   └── read-current-level
└── design-future
    ├── start-structure-design
    ├── read-design-level
    ├── revise-structure-design
    ├── diff-structure-design
    ├── create-implementation-context
    ├── list-structure-design-versions
    └── compare-design-to-current
```

One hidden `observation-pipeline` Role is available only to the trusted scanner/UA/projector service principal.
It may publish CodeSnapshot, UnderstandAnythingSnapshot, and ObservedModelRevision records. It is absent from
the conversational capability graph.

There is no UA Dashboard Role and no UA-specific MCP server. Agents read CoIntent's semantic current/design
models; humans use the embedded UA frontend for full visual code-map exploration.

Root Role instructions:

1. inspect project state before selecting a coordinate;
2. route questions about what exists to `understand-current`;
3. enter `design-future` only after explicit design intent;
4. refresh before creating a design and never silently rebase an existing drawing;
5. read at most one page-equivalent level per call unless the user explicitly continues;
6. never translate a conversation or target drawing into an observed write;
7. stop after producing implementation context; do not trigger post-coding analysis;
8. compare historical design and later reality only when requested.

Two orchestration Skills encode the normal call order:

- `learn-current-system`: inspect state → refresh when requested → read current level → descend only on request;
- `design-structure-first`: inspect state → refresh → start design → revise/read/diff iteratively → create
  implementation context after explicit user instruction.

## 7. Authority and audit

Role placement is not authorization. Each Tool checks `current_principal()` and derives authorship from its
subject/client/issuer; callers never submit an `actor` string.

Minimal scopes:

- `cointent.read` — inspect state and read levels/diffs/history;
- `cointent.refresh.request` — request bounded analysis jobs;
- `cointent.design.write` — create and revise target drawings;
- `cointent.design.finalize` — freeze an exact diff digest; a conversational Agent may use it only after an
  explicit user instruction;
- `cointent.observation.publish` — hidden trusted worker authority.

All commands carry an idempotency key or content-derived identity. Design writes require the expected base
revision. Finalization records the authenticated initiating principal and binds it to an exact immutable
`design_revision_id` and `diff_digest`; it never falsely labels an Agent invocation as a human action.

## 8. Product invariants

1. Current truth is produced only by code → UA → projection.
2. Refresh happens only because a user asks to understand or begins design; coding completion does not trigger it.
3. Repeat `/understand` analysis is incremental whenever valid UA state exists.
4. A target drawing never mutates or becomes an observed graph.
5. Every Agent read discloses at most one web-equivalent level by default.
6. Design starts from the latest valid root Observation and keeps that baseline immutable.
7. Coding receives an implementation context derived from an exact target diff.
8. Later design-versus-current comparison is optional, read-only, and tolerant of structural divergence.

## 9. Acceptance checks

- A second refresh with unchanged code invokes neither UA nor the domain analyzer.
- A second refresh with one changed file selects incremental UA mode and reports only impacted analyzer files.
- Missing fingerprints or a failed incremental integrity gate cause a declared full fallback, never a silent one.
- Starting design against a stale/refinement Observation fails with an actionable refresh requirement.
- Current and design level reads never contain grandchildren.
- An Agent cannot submit native graph content or mutate any observed identity.
- Agent MCP discovery exposes no UA visual-dashboard or raw-graph Role.
- Finalizing a design does not schedule a scan.
- A later refresh publishes only from new code/UA artifacts; the historical target remains unchanged.
