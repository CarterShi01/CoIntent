# CoIntent

**Make program logic legible to humans—and keep that explanation aligned with code.**

CoIntent is an Agent-native system for modeling backend program logic as recursive `Responsibility` objects and `Workflow`s. A product manager can begin with a plain-language capability, enter the Responsibility that realizes it, and repeatedly drill into the smaller Responsibilities that cooperate to fulfill it. Concrete backend files remain linked as evidence without turning the model into a code or architecture diagram.

The current repository is a working **0.3 MVP**: Contexture-powered MCP, an English review workspace, project and immutable design-version management, SQLite plus portable JSON assets, a backend-only Git scanner, bidirectional change findings, and an Idea Factory experiment model.

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

The web workspace has three coordinated areas:

1. **Specification** — a compact, plain-language capability catalog.
2. **Responsibility Workflow** — one semantic level at a time, with breadcrumb descent.
3. **Object contract and evidence** — data members, inputs, outputs, backend mappings, and alignment review state.

MCP is the authoring and alignment surface. Agents can inspect and trace Responsibilities, assess structural signals, record original human wording, stage typed patches, accept or reject proposals, ingest code snapshots, find artifact impact, and close a versioned change loop.

The scanner only records deterministic repository facts. An Agent interprets those facts and stages semantic changes; observed code never silently becomes accepted design truth.

## Quick start

Requirements: Git, Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node.js 20+.

```bash
uv sync --extra dev
npm --prefix web install

# Read an existing repository and seed the bundled Idea Factory interpretation.
uv run cointent scan /path/to/idea-factory \
  --project-id idea-factory \
  --name "Idea Factory" \
  --seed-idea-factory

# Contexture MCP plus protected/read REST surface.
uv run cointent serve

# Development UI.
npm --prefix web run dev
```

Open `http://127.0.0.1:5175`. The backend listens on `127.0.0.1:8811`. A local MCP client can use `uv run cointent mcp` over stdio.

Re-running `scan` creates an incremental snapshot and compares it with the previous one. The target repository is read-only. Untracked files are omitted unless `--include-untracked` is explicitly supplied.

## MCP capabilities

The Contexture graph groups typed tools and four method Skills under:

- `project-management` — projects, immutable versions, and alignment coordinates;
- `specification` — plain-language items, coverage, and original intent records;
- `responsibility-model` — roots, focused inspection, cyclic path tracing, quality signals, and reviewed proposals;
- `implementation-alignment` — backend snapshots, mappings, impact lookup, and findings;
- `change-lifecycle` — traceable specification → model → code change sets;
- `history-and-portability` — semantic diffs and portable 0.3 exports.

For Streamable HTTP, humans authenticate with an OC-style signed `HttpOnly` session cookie while Agents use a separate MCP bearer token. Secrets are deployment environment variables and are never part of the repository.

## Persistence

SQLite is the transactional authority for projects, proposals, sessions of change, snapshots, findings, and version coordinates. Each accepted design and code snapshot is also projected to readable JSON under the data root:

```text
projects/<project-id>/
├── project.json
├── design/v000001.json
└── snapshots/<snapshot-id>.json
```

This gives the application reliable concurrency and query behavior while keeping its durable model portable and diffable.

## Verification

```bash
uv run --extra dev pytest
npm --prefix web run build
```

## Documentation

- [0.3 detailed design](docs/design-v0.3.md)
- [0.3 implementation and release plan](docs/implementation-v0.3.md)
- [modeling method and prior-art boundaries](docs/method.md)
- [live review walkthrough](docs/review.md)

Earlier versioned documents remain as historical records; they are not the current public model.

## Framework dependency

CoIntent pins Contexture to the exact latest upstream `master` commit available to this build (`a108b314`, Contexture 0.14.0). The Git pin keeps deployments reproducible until a corresponding stable package release is published.

## Scope

Version 0.3 focuses on code → Responsibility modeling and ongoing model ↔ code alignment. Full conversational specification authoring is intentionally a later phase. Software architecture and infrastructure views are out of scope: CoIntent currently explains program logic for product-level readers.
