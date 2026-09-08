# CoIntent Detailed Design 0.2

**Status:** implementation baseline  
**Date:** 2026-09-08  
**Product definition:** CoIntent is a human–Agent software design convergence and implementation alignment system. Through continuing exchange, it turns a fuzzy idea into versioned ProductFunctions, responsibilities, and a RoleObject graph, then detects semantic drift between that accepted design and observed code.

## 1. Product boundary

CoIntent is the alignment officer between a product owner and implementation Agents. It owns neither ideation nor code generation. It preserves what the human asked for, makes the current software design intelligible, and forces a visible decision whenever design and implementation diverge.

The primary granularity is a functional responsibility, not a file, class, function, screen, service, team, or Agent. A procedural codebase can therefore be described with the same model as an object-oriented codebase. “Object” in `RoleObject` means a stable conceptual owner of responsibility; it does not prescribe an implementation paradigm.

The system has two directions that meet at one accepted design:

```text
Human intent -> ProductFunction refinement -> RoleObject responsibility design
                                                       ^
                                                       | explicit mappings and review
Repository facts -> code snapshots -> implementation evidence
```

Code-derived hypotheses never silently become product truth. Every semantic design mutation is a proposal against an exact accepted version and becomes authoritative only after explicit acceptance.

## 2. Human experience

The main workspace uses three regions:

1. **Product Function Catalog (left):** a navigable tree of what the product provides. It supports continued addition and refinement as a product manager would maintain a functional specification.
2. **RoleObject Map (right/top):** a multi-root responsibility forest. Containment answers “what is this responsibility made of?” Typed overlays answer “which Roles collaborate or depend on each other?”
3. **RoleObject Inspector (right/bottom):** the selected RoleObject's purpose, responsibilities, owned knowledge, inputs, outputs, constraints, collaborators, supported ProductFunctions, implementation evidence, and provenance.

Selecting a ProductFunction highlights every RoleObject that owns, contributes to, or governs it. Selecting a RoleObject highlights its supported ProductFunctions. This many-to-many navigation is the central visual expression of human–Agent alignment.

The header makes two independent coordinates explicit:

- project and accepted `DesignVersion`;
- latest `CodeSnapshot` and associated `MappingRevision`.

Pending proposals, open findings, and active ChangeSets remain visible as review work; they are not blended into the accepted model.

The web application is an English projection. Stable identifiers, protocol fields, source paths, and canonical accepted descriptions are English. `IntentSource.content` preserves original wording in any language.

## 3. Selective method composition

CoIntent borrows only the parts of established methods that solve its concrete problem.

| CoIntent need | Source | Adopted concept | Deliberately omitted |
| --- | --- | --- | --- |
| Refine an idea until it is implementable | KAOS / goal-oriented requirements engineering | progressive refinement, obstacles as questions, responsibility assignment, practical stopping condition | temporal logic, proof obligations, a permanent Goal layer in the UI |
| Explain a system independently of code shape | OOram | systems as collaborating Roles; Role composition; implementation-independent responsibility | full notation and process ceremony |
| Choose good responsibility boundaries | Responsibility-Driven Design and GRASP | cohesive responsibilities, information expert, low coupling, high cohesion, controller/polymorphism as review lenses | class-first CRC ceremony and forced OO implementation |
| Make a boundary testable | IDEF0 | inputs, outputs, and constraints when they clarify a promise | mandatory ICOM boxes and complete function-model notation |
| Compare design with code | Software Reflexion Models | normative high-level model, observed source model, explicit mapping, convergence/divergence/absence | automatic recovery of intended architecture from code |

KAOS informs the conversation but is not persisted as a separate Goal tree. The durable left-hand model is a unified ProductFunction catalog. Decomposition should stop when another level would no longer change observable behavior, acceptance, a constraint, or responsibility ownership.

Quality rules are diagnostic prompts, not automatic verdicts. A structural check may identify an unowned leaf function, an empty leaf RoleObject, weak contracts, suspicious coupling, or missing evidence; an Agent explains the signal and a human decides.

## 4. Canonical domain model

### 4.1 Project and version axes

`Project` is the isolation and navigation boundary. It contains repository settings, preferred language, current design version, snapshots, proposals, mappings, findings, and ChangeSets.

`DesignVersion` is an immutable accepted `ProjectModel`. It has a parent version, actor, message, and timestamp. Version creation is serialized with optimistic concurrency.

`CodeSnapshot` is an immutable observation of a Git repository: revision, branch, dirty state, artifacts, hashes, entrypoints, language counts, and selected dependency relations. Snapshot identity is content-derived and ingestion is idempotent.

`MappingRevision` records which `TraceLinks` were compared for one `(DesignVersion, CodeSnapshot)` pair. A new snapshot does not create a new design version.

The current alignment coordinate is valid only when the latest MappingRevision names both the selected accepted DesignVersion and latest CodeSnapshot. Accepting a design therefore makes the mapping visibly stale until an Agent explicitly records a reviewed MappingRevision.

`AlignmentFinding` records an observed convergence problem or uncertainty. Resolution does not rewrite history.

### 4.2 Product design

`IntentSource` preserves the original human or Agent evidence and an optional source reference.

`ProductFunction` describes an externally meaningful product provision:

- stable ID and English name;
- description and optional parent;
- draft, accepted, questioned, or deferred state;
- priority;
- acceptance statements and constraints;
- source evidence IDs.

The parent relation creates a tree for product navigation. It is not a call graph, organization chart, or list of implementation components.

### 4.3 Responsibility design

`RoleObject` is a logical responsibility owner with:

- purpose and optional containment parent;
- owned knowledge;
- boundary inputs and outputs;
- constraints and evidence;
- lifecycle state.

`Responsibility` is a testable obligation owned by exactly one RoleObject and connected to zero or more ProductFunctions. It may refine its own inputs, outputs, and constraints.

`RoleRelation` is a typed overlay between RoleObjects: collaboration, dependency, delegation, exchange, or governance. Containment remains separate so the UI can render a forest without pretending every relationship is hierarchical.

`FunctionRoleLink` is the explicit many-to-many bridge from ProductFunctions to RoleObjects. Its kind is `owns`, `contributes`, or `governs`; confidence, evidence, and provenance prevent an inference from appearing certain.

`TraceLink` connects a RoleObject to a stable implementation artifact path and describes how the path realizes, supports, verifies, stores, or presents the responsibility. Mappings may be many-to-many and should prefer stable coarse boundaries over copying a file tree.

### 4.4 Change loop

`ChangeSet` is the unit that closes the bidirectional loop:

```text
designing -> approved -> implementing -> reviewing -> closed
                                           \-> cancelled
```

It binds a product change to its base and target design versions, proposal, affected ProductFunctions and RoleObjects, implementation snapshot, review state, and resolution. An implementation brief is generated from the accepted target design rather than from transient conversation alone.

A ChangeSet is closed only when the design coordinate, implementation coordinate, verification evidence, and alignment conclusion are explicit.

## 5. Persistence and portability

CoIntent uses SQLite plus JSON intentionally:

- **SQLite** is the transactional operational store for project indexes, immutable design rows, intent sources, proposals, snapshots, mapping revisions, findings, and ChangeSets.
- **JSON assets** are stable, readable, portable projections under `projects/<project-id>/`. Project metadata, every accepted design, and every code snapshot are atomically written. Missing projections are rebuilt from SQLite on startup.

There is no pair of independently editable masters. In 0.2, all mutations pass through the repository transaction and JSON is its immutable interoperability/audit projection. A future repository-backed workflow may promote reviewed JSON commits as the acceptance mechanism without changing the domain schema.

Layout:

```text
runtime/
├── cointent.db
└── projects/<project-id>/
    ├── project.json
    ├── design/v000001.json
    └── snapshots/snapshot-<digest>.json
```

Writes use a temporary sibling followed by an atomic rename. Project IDs cannot contain paths or traversal segments. TraceLink artifact paths must be safe relative paths.

## 6. Agent-native interface

Contexture is the application framework and MCP is the primary authoring plane. The root capability is `cointent`, progressively disclosed into six Roles:

```text
cointent
├── project-management
├── product-design
├── responsibility-design
├── implementation-alignment
├── change-lifecycle
└── history-and-portability
```

The capability graph exposes five operating Skills:

- `refine-product-functions` preserves source wording and stages ProductFunction changes;
- `decompose-responsibilities` applies OOram/RDD/GRASP lenses to build the RoleObject forest;
- `review-design` checks fidelity, coverage, ownership, contracts, independence, and evidence;
- `map-implementation` applies the Reflexion Model boundary to snapshots and TraceLinks;
- `close-alignment-loop` prevents a ChangeSet from disappearing between design and implementation.

Mutation Tools are explicit and narrow. The browser uses only an allowlisted read projection from the same Contexture runtime, so it cannot accidentally acquire different mutation semantics.

## 7. Alignment rules

The deterministic scanner may establish that an artifact or dependency changed. It may not establish why that code should exist. Comparison therefore reports evidence classes:

- `Convergent`: observed structure agrees with a declared mapping;
- `Absent`: expected mapped implementation disappeared or was not observed;
- `Divergent`: an observed dependency conflicts with declared RoleObject relationships;
- `BoundaryChange`: code changed inside a mapped responsibility boundary;
- `Unmapped`: architectural code has no RoleObject evidence;
- `Uncertain`: evidence is insufficient for a stronger classification.

The correct response may be an implementation fix, a design proposal, an accepted exception, a mapping correction, or no semantic change. The review record makes this decision visible.

## 8. Security and deployment

The public deployment follows One Creator's sufficient authorization pattern:

- browser users authenticate with username/password and receive a signed, stateless, `HttpOnly; Secure; SameSite=Strict` cookie;
- MCP clients use an independent bearer token;
- secrets live only in the server's mode-0600 `.env`, never in Git, images, JSON assets, logs, or the browser bundle;
- application and MCP listen behind host Nginx; the backend container binds only to loopback;
- Idea Factory is scanned locally and only its portable facts are transferred. The hosted service has no source credentials and no write access to that repository.

SQLite assumes one application process. Moving to multiple writers requires a transactional database and the same repository-level concurrency contract.

## 9. Acceptance criteria for 0.2

The release is complete when:

- legacy 0.1 models migrate read-only into schema 0.2;
- projects and independent design/code versions are visible;
- ProductFunction-to-RoleObject cross-highlighting works;
- a RoleObject's full detail is visible without opening source code;
- MCP exposes typed inspect, propose, review, snapshot, mapping, ChangeSet, compare, and export capabilities;
- a proposal cannot overwrite a newer accepted version;
- a scan can create review findings without mutating design;
- accepted designs and snapshots produce JSON assets;
- backend tests, frontend build, authenticated browser review, MCP authorization, and public health verification pass.
