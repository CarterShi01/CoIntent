# CoIntent

**Make program logic legible to humans—and keep that explanation aligned with code.**

CoIntent is an Agent-native, on-demand system with two explicit processes: understand the current program from code, and design the program humans want next. It is not an always-on task manager. A user invokes it when they want to learn the current system or explicitly design its structure before code. A product manager can begin with a plain-language capability and repeatedly drill into the structure that fulfills it. Concrete source locations remain linked as evidence without turning the primary view into a file or class diagram.

The repository contains the working **0.3 design MVP** plus the implemented **0.4 on-demand understanding and structure-first design loop**. The canonical product flow is “understand on demand, design on demand”: refresh only when a user asks to understand or starts design; expose one web-equivalent semantic level to an Agent at a time; keep target drawings as history; and never trigger analysis merely because code development finished. Version 0.4 uses only Understand Anything and intentionally has no multi-engine adapter framework.

The next production topology is fixed by ADR-0002 through ADR-0005: official UA Skills run natively in the Agent
environment that can access the code; CoIntent MCP is the sole Agent control plane; refresh-scoped signed HTTPS
transfers large artifacts without a CoIntent local client; and the central service validates an exact clean Git
coordinate before publishing immutable current truth. The former server-local checkout/headless-worker path has
been removed from normal product use.

## The model

```text
Specification
    implementation-independent product meaning
        ↓ realized by
Responsibility
    name + description + data members + inputs + outputs
        ↓ composed as
Workflow
    ordered, branching, event, error, parallel, and cyclic references
        ↓ evidenced by
Backend code
    mapped artifacts and optional symbols
```

A Responsibility is an object in the semantic sense: it encapsulates one coherent obligation and the domain state it needs. It does not require the code to use classes or object-oriented syntax. A procedural codebase can be explained by the same model.

A composite Responsibility owns a Workflow whose nodes reference smaller Responsibilities. There is no separate child hierarchy and no Function layer. A leaf has no Workflow and maps to backend evidence at the lowest product-relevant depth.

The browser appears tree-like while drilling down, but each local Workflow is a graph. Branches and loops are first-class; the same Responsibility can occur in several Workflows without being copied.

## Why it exists

Agentic development creates a two-way alignment problem:

- humans need a stable, progressively explorable explanation of what the program does;
- Agents need a precise semantic boundary between human intent and implementation evidence;
- code changes need to identify which accepted Responsibilities may have drifted;
- model changes must remain proposals until a human explicitly accepts a new version.

Most code maps foreground files, classes, functions, imports, services, or deployment. CoIntent deliberately filters those details from its primary view. The evidence snapshot still covers the full repository, including product-relevant frontend behavior; logging, telemetry, generated files, and framework plumbing stay out of the primary semantic view unless they implement visible behavior.

## Human and Agent surfaces

The web workspace has two top-level modes with the same three-area grammar:

1. **Understand current** — generated from a full Git snapshot and Understand Anything artifacts; always read-only.
2. **Design future** — expected functions and a complete target Responsibility/Workflow structure graph; human-owned and independently versioned.

Both modes use a function list, one semantic graph level at a time, and a detail/evidence inspector. An absent observation produces an explicit generation state; a legacy design is never displayed as current code. Understand current contains a default CoIntent **System view** and a secondary **Implementation map** that directly embeds the pinned Understand Anything Dashboard for code-level exploration.

Agent reads follow the same disclosure budget as the browser: one function level, one selected Responsibility,
its direct children and local edges, plus bounded evidence. Deeper descendants require an explicit follow-up.
Design begins only after explicit user intent and always uses a freshly checked root Observation. Its finalized
semantic diff constrains coding, but the drawing is never promoted into current truth.

Coding completion does not automatically run a scan. The next request to understand or design refreshes the
real code-derived graph. Comparing that later graph with a historical drawing is optional and read-only.

The browser uses authenticated HTTP for CoIntent pages, immutable UA artifacts, exact-snapshot source, and the
embedded UA Dashboard. Conversational and coding Agents use CoIntent MCP. No UA MCP server is required or
exposed. The compact Agent Role graph has `project-context`, `distribution`, `understand-current`, and
`design-future`. A refresh-scoped state machine lets the code-local Agent stage opaque native artifacts, but only
server validation and projection can publish an Observation. There is no general graph upload or replacement API.

The scanner only records deterministic repository facts. An Agent interprets those facts and stages semantic changes; observed code never silently becomes accepted design truth.

## Quick start

Server requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node.js 22+ to build the pinned UA
Dashboard. The code-local Agent needs Git, Node.js 22+, pnpm 10+, outbound HTTPS, and one of UA's verified native
Skill environments.

```bash
uv sync --extra dev
npm --prefix web install

# Build the official UA 2.9.6 Dashboard at its pinned Git commit, with the
# small CoIntent same-origin data/focus bridge applied at exact source anchors.
scripts/build-ua-viewer.sh

# Contexture MCP plus authenticated browser HTTP surface.
# Set COINTENT_UA_VIEWER_ROOT if the built viewer is deployed outside
# web/ua-viewer-dist relative to the server working directory.
uv run cointent serve

# Development UI.
npm --prefix web run dev
```

Open `http://127.0.0.1:5175`. The backend listens on `127.0.0.1:8811`. Connect the coding Agent to its Streamable
HTTP MCP endpoint. Normal users install and scan through that Agent; they do not install a CoIntent client.

In conversation, ask CoIntent to install/verify UA when needed and then ask to update understanding. The Agent
freezes a clean default-branch commit, uses the official native UA Skills in a detached worktree, restores the
central checkpoint when compatible, and transfers opaque bundles through short-lived URLs issued by MCP. No
graph or source bytes pass through the model. A matching commit skips UA; a valid checkpoint selects incremental
UA; missing or incompatible state declares a full fallback. Complete server validation is required before the
visible Observation advances.

## Agent MCP capabilities

The canonical public 0.4 surface is intentionally small:

- `project-context` — register/list projects and inspect current coordinates, staleness, drawings, and next actions;
- `distribution` — obtain and verify the official native UA installation for the current Agent environment;
- `understand-current` — request, execute, transfer, complete, and inspect an on-demand refresh, then read one
  page-equivalent current level;
- `design-future` — start, read, revise, diff, and finalize a structure drawing, inspect its history, and optionally
  compare it with later observed reality.

The exact operations and Role instructions are specified in the
[on-demand product flow and MCP surface](docs/on-demand-product-flow.md).

The Beijing release verifies or rebuilds the pinned UA Dashboard, packages it with the backend, and proxies
`/ua-viewer` plus the narrow `/internal/` viewer/refresh data plane. The latter disables proxy request buffering
and raises the request-size ceiling for digest-bound native refresh archives; it is not a general upload API.

Migration-era 0.3 capabilities remain available to the browser compatibility surface, but are not compiled into
the public MCP server:

The Contexture graph groups typed tools and four method Skills under:

- `project-management` — projects, immutable versions, and alignment coordinates;
- `current-understanding` — read-only code/UA/observation coordinates and observed revisions;
- `specification` — plain-language items, coverage, and original intent records;
- `responsibility-model` — roots, focused inspection, cyclic path tracing, quality signals, and reviewed proposals;
- `implementation-alignment` — backend snapshots, mappings, impact lookup, and findings;
- `change-lifecycle` — traceable specification → model → code change sets;
- `target-design` — separate target workspaces, typed design operations, review inspection, implementation
  export inspection, and evidence-backed post-implementation comparison; human approval and convergence
  decisions are intentionally absent;
- `history-and-portability` — semantic diffs and portable 0.3 exports.

Agent principals use explicit Streamable HTTP MCP scopes. Browser users authenticate separately for the HTTP
application surface. Tool implementations derive authorship from Contexture's authenticated principal and never
trust a caller-supplied `actor`. Secrets are deployment environment variables and are never part of the repository.

## Persistence

SQLite is the transactional authority for projects, proposals, sessions of change, snapshots, findings, and version coordinates. Each accepted design and code snapshot is also projected to readable JSON under the data root:

```text
projects/<project-id>/
├── project.json
├── design/v000001.json
├── snapshots/<snapshot-id>.json
├── source-blobs/<sha256>
├── understand-anything/<ua-snapshot-id>.json
├── ua-checkpoints/<sha256>.tar.gz
├── refresh-staging/<refresh-id>/
├── observed/<observed-revision-id>.json
└── target-design/<workspace-id>/
    ├── workspace.json
    ├── revisions/<design-revision-id>.json
    ├── operations/<operation-id>.json
    ├── reviews/<review-id>.json
    ├── approvals/<approval-id>.json
    ├── exports/<implementation-bundle-id>.json
    ├── verifications/<verification-report-id>.json
    └── verification-decisions/<verification-decision-id>.json
```

SQLite owns transactional coordinates, transfer state, and current pointers; large immutable/checkpoint/source
bytes live under the central asset root. They form one backup and restore unit.

## Verification

```bash
uv run --extra dev pytest
npm --prefix web run build
```

## Documentation

- [0.4 detailed design](docs/design-v0.4.md)
- [on-demand product flow and MCP surface](docs/on-demand-product-flow.md)
- [Understand Anything Dashboard integration](docs/ua-dashboard-integration.md)
- [Understand Anything decision](docs/adr-0001-codemap-engine.md)
- [native UA distribution](docs/adr-0002-native-ua-distribution.md)
- [MCP control and artifact data plane](docs/adr-0003-mcp-control-and-artifact-data-plane.md)
- [Observation provenance](docs/adr-0004-observation-provenance.md)
- [central UA incremental state](docs/adr-0005-central-ua-state.md)
- [native UA Agent runbook](docs/native-ua-agent-runbook.md)
- [0.4 execution path](docs/implementation-v0.4.md)
- [0.3 detailed design](docs/design-v0.3.md)
- [modeling method and prior-art boundaries](docs/method.md)
- [live review walkthrough](docs/review.md)

Earlier versioned documents remain as historical records.

## Framework dependency

CoIntent pins Contexture to the exact latest upstream `master` commit available to this build (`a108b314`, Contexture 0.14.0). The Git pin keeps deployments reproducible until a corresponding stable package release is published.

## Scope

Version 0.4 now delivers the compact scoped Agent MCP contract, native-Agent incremental UA protocol, trusted code →
UA → observed structure path, first-class `ImplementationRef` mappings, evidence-bounded recursive expansion,
independent target drawings, exact diff-bound implementation contexts, and the directly embedded official UA
Dashboard with forward/reverse semantic focus. The server-local checkout/headless-worker path has been removed;
production rollout still requires an Idea Factory acceptance scan, deployment secrets/TLS, retention policy, and
the supported Agent/platform compatibility matrix.
