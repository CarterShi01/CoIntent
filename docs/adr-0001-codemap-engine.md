# ADR-0001: Use Understand Anything as the Only Code Map Engine in 0.4

**Status:** accepted  
**Date:** 2026-09-09  
**Related design:** [CoIntent 0.4 detailed design](design-v0.4.md)

## Context

CoIntent needs a stable intermediate artifact between source code and its read-only current-system view. The product should spend its engineering budget on evidence-backed semantic projection, recursive exploration, design review, and implementation handoff rather than rebuilding parsers and code-indexing infrastructure.

[Understand Anything](https://github.com/Egonex-AI/Understand-Anything) already produces the two artifacts closest to this need:

- `.ua/knowledge-graph.json` combines deterministic Tree-sitter structure with semantic summaries, architecture layers, and graph relationships;
- `.ua/domain-graph.json` derives Domain → Business Flow → Business Step descriptions from the knowledge graph;
- both are portable JSON artifacts tied to a Git commit;
- subsequent analysis can update changed files incrementally.

The current release must optimize for one working path. It does not need a generic multi-engine framework, a second static-analysis engine, or speculative compatibility abstractions.

## Decision

**Understand Anything is the only Code Map engine supported by CoIntent 0.4.**

The initial conformance target is Understand Anything plugin **2.9.6**, repository commit
`5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc`. This exact revision was inspected on
2026-09-09. Changing it is an explicit dependency upgrade with fixture and golden-output review.

```text
immutable CodeSnapshot
    → pinned Understand Anything run
    → knowledge-graph.json + optional domain-graph.json
    → CoIntent import validation
    → immutable UnderstandAnythingSnapshot
    → evidence-backed ObservedModelRevision
```

CoIntent imports the UA schema directly. There is no public `AnalyzerAdapter`, producer registry, fact merger, generic engine capability matrix, Joern process, SCIP indexer, or engine-selection setting in this phase.

This is intentionally a product-scope decision, not a claim that UA will remain the only possible engine forever. If a second engine is actually needed later, the team will design an abstraction from two measured integrations and migrate the UA path behind it. No 0.4 API or database column should pretend that this abstraction already exists.

## Trust boundary

UA uses two kinds of computation that CoIntent must distinguish:

1. structural extraction supplies code identities and relationships such as files, functions, classes, imports, calls, containment, and source ranges;
2. LLM analysis supplies summaries, tags, architecture layers, domains, business flows, steps, and tours.

The native graph may contain both kinds in the same node. CoIntent therefore does not label the whole file as either deterministic or AI-generated. Imported claims expose their provenance at field or projection level.

`knowledge-graph.json` is the sole upstream code-map artifact. `domain-graph.json` is an optional semantic proposal derived from it; it is not independently authoritative. A visible observed node is publishable only when CoIntent can resolve it, or its descendant steps, to source locations in the matching `CodeSnapshot`. Claims without resolvable evidence remain import diagnostics and do not silently become current-system truth.

## Import constraints

- Pin the UA plugin/repository commit and record it on every imported snapshot.
- Run UA against the same immutable Git commit captured by `CodeSnapshot`.
- Reject a clean snapshot when `project.gitCommitHash` differs from the code snapshot revision.
- Require a full-repository code snapshot; backend-only legacy snapshots are insufficient.
- Reject absolute paths, parent traversal, invalid line ranges, dangling edges, duplicate IDs, and source paths absent from the code snapshot.
- Preserve the original UA JSON as an immutable asset and compute a canonical content digest.
- Never accept graph JSON supplied inside a user request to edit the current structure. Import is an operator/pipeline capability, not a conversational graph mutation tool.
- Record UA graph version, pinned tool revision, analysis time, imported time, coverage, and validation diagnostics.
- Do not permit imported native IDs to collide across projects or snapshots; observation identities include the UA snapshot coordinate.

## Projection rules

- Code entities and structural edges are evidence, not user-facing Responsibilities by default.
- Domain, Flow, and Step nodes are semantic candidates.
- A Step is bound through its `filePath` and `lineRange` only when they overlap a structural node in `knowledge-graph.json`; a plausible path supplied only by semantic analysis is insufficient.
- A Flow inherits the union of evidence from its Steps.
- A Domain inherits the union of evidence from its Flows.
- A domain branch with no resolvable evidence is omitted from the published observed model and reported as a diagnostic.
- `contains_flow` and `flow_step` edges define containment and order; their native weights are retained.
- UA linear step order must not be presented as a proven condition, loop, error, parallel, or event relationship.
- Recursive drill-down creates a new immutable projection revision over the same UA snapshot; it never changes the imported map.

## Operational model

UA execution happens outside the interactive web process. The first CoIntent implementation imports completed JSON artifacts through a CLI/pipeline command. This keeps model tokens, repository credentials, plugin installation, and long-running analysis out of the request path.

The intended production runner:

- checks out or mounts an immutable repository worktree;
- runs a pinned UA version with a pinned configuration and declared model profile;
- denies write access outside the worktree's `.ua` output area;
- captures logs and exit status;
- invokes CoIntent import only after both JSON files are complete;
- promotes an observation only after validation and projection succeed.

The browser and conversational Agent may request a scan job later, but neither can upload replacement graph content or call a graph-upsert API.

## Consequences

Positive:

- one concrete integration can ship sooner;
- UA already matches the product's code → structure → business understanding direction;
- CoIntent retains control over source binding, immutable revisions, and the read/design authority boundary;
- the product does not own language parsers or an operational graph database;
- the same JSON artifacts support local development and repeatable tests.

Costs and limitations:

- CoIntent depends on one upstream schema and release cadence;
- semantic summaries and domain models vary with model/configuration and require explicit provenance;
- UA flow ordering does not prove control flow;
- some domain claims may be omitted when source evidence is unavailable;
- exact deep data-flow analysis is outside 0.4 scope.

These limitations must appear as coverage and evidence states. They must not be hidden by fabricated precision.

## Explicitly deferred

- Joern, SCIP, CodeGraphContext, or any second code-map engine;
- generic adapter interfaces and plugin discovery;
- cross-engine entity reconciliation or confidence merging;
- engine selection in project settings;
- generalized analyzer capability negotiation;
- direct embedding or forking of UA's dashboard UI.

## Acceptance spike

Before enabling a project by default, run the pinned UA version against Idea Factory and fixtures containing backend, frontend, tests, configuration, direct calls, and dynamic code. The integration passes when:

- clean-snapshot commit coordinates match;
- every published evidence path exists in the full code snapshot;
- import and projection are byte-stable for the same two JSON inputs;
- invalid paths and dangling edges fail closed;
- evidence-free domain branches are visible in diagnostics but absent from observed truth;
- the initial two-level view loads without reading source files at request time;
- a selected Step can navigate back to exact source lines;
- no observed graph mutation operation is exposed to browser or Agent clients.
