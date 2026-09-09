# CoIntent

**Make program logic legible to humans—and keep that explanation aligned with code.**

CoIntent is an Agent-native system with two explicit processes: understand the current program from code, and design the program humans want next. A product manager can begin with a plain-language capability and repeatedly drill into the structure that fulfills it. Concrete source locations remain linked as evidence without turning the primary view into a file or class diagram.

The repository contains the working **0.3 design MVP** plus the complete **0.4 observation → target design → implementation verification vertical loop**. Version 0.4 imports one pinned code-map source—Understand Anything—into immutable, evidence-backed current-system revisions, generates bounded child refinements, clones an exact baseline into a separately versioned `des-*` target workspace, exports only human-approved semantic diffs, and compares a later code observation with that approved target before a human declares convergence. It intentionally has no multi-engine adapter framework.

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

Most code maps foreground files, classes, functions, imports, services, or deployment. CoIntent deliberately filters those details from its primary view. It also excludes frontend code, logging, telemetry, metrics, tracing, framework plumbing, generated files, and other cross-cutting noise from program-logic inference.

## Human and Agent surfaces

The web workspace has two top-level modes with the same three-area grammar:

1. **Understand current** — generated from a full Git snapshot and Understand Anything artifacts; always read-only.
2. **Design future** — expected functions and target Responsibilities; human-owned and independently versioned.

Both modes use a function list, one semantic graph level at a time, and a detail/evidence inspector. An absent observation produces an explicit generation state; a legacy design is never displayed as current code.

MCP exposes read-only observation tools separately from the legacy design and alignment tools. The Understand Anything import is deliberately not an MCP or browser operation: only the trusted local/operator pipeline can ingest native graph JSON.

The scanner only records deterministic repository facts. An Agent interprets those facts and stages semantic changes; observed code never silently becomes accepted design truth.

## Quick start

Requirements: Git, Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node.js 20+.

```bash
uv sync --extra dev
npm --prefix web install

# Legacy backend-only scan and optional 0.3 design seed.
uv run cointent scan /path/to/idea-factory \
  --project-id idea-factory \
  --name "Idea Factory" \
  --seed-idea-factory

# 0.4: capture every tracked file for the exact UA analysis coordinate.
uv run cointent scan /path/to/idea-factory \
  --project-id idea-factory \
  --name "Idea Factory" \
  --scope full

# After pinned Understand Anything 2.9.6 has generated its JSON artifacts:
uv run cointent import-understand-anything \
  --project-id idea-factory \
  --code-snapshot-id snapshot-... \
  --knowledge-graph /path/to/idea-factory/.ua/knowledge-graph.json \
  --domain-graph /path/to/idea-factory/.ua/domain-graph.json \
  --ua-tool-revision 5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc

# Contexture MCP plus protected/read REST surface.
uv run cointent serve

# Development UI.
npm --prefix web run dev
```

Open `http://127.0.0.1:5175`. The backend listens on `127.0.0.1:8811`. A local MCP client can use `uv run cointent mcp` over stdio.

Re-running `scan` creates an incremental snapshot and compares it with the previous one. The target repository is read-only. Untracked files are omitted unless `--include-untracked` is explicitly supplied. UA import requires a `--scope full` snapshot and validates commit, paths, graph references, line ranges, and structural corroboration before publishing an observed revision.

## MCP capabilities

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

For Streamable HTTP, humans authenticate with an OC-style signed `HttpOnly` session cookie while Agents use a separate MCP bearer token. Secrets are deployment environment variables and are never part of the repository.

## Persistence

SQLite is the transactional authority for projects, proposals, sessions of change, snapshots, findings, and version coordinates. Each accepted design and code snapshot is also projected to readable JSON under the data root:

```text
projects/<project-id>/
├── project.json
├── design/v000001.json
├── snapshots/<snapshot-id>.json
├── understand-anything/<ua-snapshot-id>.json
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

This gives the application reliable concurrency and query behavior while keeping its durable model portable and diffable.

## Verification

```bash
uv run --extra dev pytest
npm --prefix web run build
```

## Documentation

- [0.4 detailed design](docs/design-v0.4.md)
- [Understand Anything decision](docs/adr-0001-codemap-engine.md)
- [0.4 execution path](docs/implementation-v0.4.md)
- [0.3 detailed design](docs/design-v0.3.md)
- [modeling method and prior-art boundaries](docs/method.md)
- [live review walkthrough](docs/review.md)

Earlier versioned documents remain as historical records.

## Framework dependency

CoIntent pins Contexture to the exact latest upstream `master` commit available to this build (`a108b314`, Contexture 0.14.0). The Git pin keeps deployments reproducible until a corresponding stable package release is published.

## Scope

Version 0.4 delivers the trusted code → UA artifact → observed structure path, evidence-bounded recursive expansion, independent target-design workspaces, human approval, semantic implementation bundles, later-observation verification, and human-only convergence decisions. Production Idea Factory UA coverage review and rollout remain release work. Infrastructure topology remains out of scope.
