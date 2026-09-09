# CoIntent 0.3 Design: Recursive Responsibility Workflows

**Status:** implementation baseline  
**Scope:** backend program logic, not software architecture  
**Primary audience:** product managers and founders who need to understand what a program does

## 1. Product definition

CoIntent turns backend code into a versioned, progressively explorable model of program logic. It does not make files, classes, services, infrastructure, or call graphs the primary view. It explains the program through responsibilities and the workflows that combine them.

The durable alignment chain has three levels:

```text
Specification
    plain-language, implementation-independent product meaning
        ↓ realized by
Responsibility Model
    program-shaped responsibilities with data, input, output, and recursive workflows
        ↓ implemented by
Code Evidence
    concrete backend files and symbols
```

Version 0.3 concentrates on the middle and lower levels. Specification remains a simple, read-only catalog so the model has a stable upper boundary; authoring a full product specification is a later phase.

## 2. Non-goals

CoIntent 0.3 is not:

- a software architecture or deployment diagram;
- a file, class, function, import, or call-graph explorer;
- a frontend behavior model;
- a runtime workflow engine;
- a complete requirements-authoring system;
- a UML/BPMN editor;
- a representation of logging, tracing, metrics, framework plumbing, serialization, dependency injection, or other technical noise.

## 3. Core abstraction

Only two concepts are primary in the product interface.

### 3.1 Responsibility

A `Responsibility` is a stable semantic object that owns one coherent obligation of the program.

```text
Responsibility
├── name
├── description
├── data members
├── inputs
├── outputs
└── workflow (optional)
```

The object abstraction is semantic, not a claim about implementation. One Responsibility may map to several classes or functions, and one class may support several Responsibilities.

- `description` states what the Responsibility accomplishes and where its boundary ends.
- `data_members` describe the meaningful state or knowledge encapsulated by the Responsibility. Local variables and framework state are excluded.
- `inputs` describe what crosses into the Responsibility boundary.
- `outputs` describe returned information, emitted events, persisted effects, or other meaningful results.
- `workflow` explains how the Responsibility is composed from smaller Responsibilities.

A leaf Responsibility has no Workflow. It is the lowest product-relevant explanation and maps directly to backend code evidence.

### 3.2 Workflow

A `Workflow` is the control relationship among Responsibility references inside one parent Responsibility.

```text
Parent Responsibility
    └── owns Workflow
            ├── node → references Responsibility A
            ├── node → references Responsibility B
            └── edge → describes execution semantics
```

Workflow nodes are occurrences, not copied Responsibility definitions. The same Responsibility may be referenced multiple times in one Workflow or reused by many parents.

Supported edge semantics are:

- `next`: ordinary continuation;
- `condition`: guarded alternative;
- `parallel`: fork or join participation;
- `event`: continuation after an event;
- `error`: exceptional path.

An edge may point to an earlier node. Cycles are valid and express loops, retries, or recurring behavior. The model is therefore not constrained to a DAG.

`entry_node_ids` explicitly identify where traversal begins. Multiple entries are valid for event-oriented workflows.

### 3.3 Derived sub-responsibilities

There is no separately stored `SubResponsibility` collection.

```text
sub-responsibilities(parent)
    = distinct Responsibility definitions referenced by parent.workflow.nodes
```

This prevents duplicated hierarchy state and makes Workflow the only composition truth.

## 4. Supporting records

### 4.1 SpecificationItem

A `SpecificationItem` is a plain-language product statement. It is program-independent and may form a navigable tree. Version 0.3 preserves this upper layer but does not attempt full specification authoring.

`SpecificationResponsibilityLink` records which Responsibilities realize a specification statement. The mapping is many-to-many.

### 4.2 ImplementationLink

An `ImplementationLink` connects a Responsibility to backend code evidence:

- stable relative artifact path;
- optional symbol;
- relationship kind (`realizes`, `supports`, `verifies`, or `stores`);
- origin and confidence;
- evidence explanation.

Implementation links are not members of the Responsibility object. They form the separate third level of the alignment chain.

### 4.3 WorkflowNode

`WorkflowNode` is an internal graph occurrence with its own id and a `responsibility_id` reference. It exists so reuse, repeated invocation, local layout, and edge endpoints do not mutate the referenced Responsibility.

It is not presented as an additional domain concept in the UI.

## 5. Canonical model

```text
ProjectModel 0.3
├── specification_items[]
├── responsibilities[]
│   └── workflow?
│       ├── entry_node_ids[]
│       ├── nodes[] → responsibility_id
│       └── edges[]
├── specification_responsibility_links[]
└── implementation_links[]
```

Core invariants:

1. All ids are unique within their record type.
2. Specification parent references resolve and remain acyclic.
3. Every Workflow node references an existing Responsibility.
4. Every Workflow entry references a node in that Workflow.
5. Every edge endpoint resolves within its Workflow.
6. Cycles in Workflow edges are allowed.
7. Specification and implementation link endpoints resolve.
8. Implementation paths are safe relative paths.
9. A Responsibility may reference itself or an ancestor to represent true recursion, but the UI detects the repeated reference and does not expand it infinitely.

## 6. Backend-only observation boundary

Repository scanning deliberately excludes frontend and technical noise before semantic inference.

Always excluded:

- frontend directories and browser source (`web`, `frontend`, `ui`, component/style/assets trees, JSX/TSX, CSS and HTML);
- logs, tracing, metrics, monitoring and telemetry;
- generated output, vendored dependencies and build products;
- documentation and deployment assets from program-logic inference.

Framework and cross-cutting code is collapsed unless it changes a product-visible decision or result. For example, rate-limit middleware is not shown, but a meaningful `Reject excessively frequent requests` Responsibility may be retained when that outcome matters.

The deterministic scanner produces repository facts, never semantic truth. An Agent lifts those facts into Responsibilities and Workflows, attaches evidence and confidence, and stages the result as a proposal for review.

## 7. Progressive interaction

The workspace has three coordinated surfaces:

1. **Specification rail:** plain-language statements and their Responsibility coverage.
2. **Responsibility workspace:** the selected Responsibility contract and its internal Workflow.
3. **Evidence drawer:** implementation mappings, scan state, findings, and proposals.

The central interaction is recursive focus:

```text
open Responsibility
    → inspect its data, inputs, and outputs
    → read its internal Workflow
    → select a child Responsibility node
    → enter that Responsibility
    → repeat
```

The navigation appears tree-like because the UI maintains a breadcrumb path. The underlying model remains a reusable graph. When a child reference already exists in the breadcrumb, the UI marks it as recursive and offers navigation without manufacturing another model object.

The graph obeys a single-altitude rule: one canvas displays only the immediate Workflow of the focused Responsibility. Technical evidence and deeper Workflows stay collapsed until requested.

## 8. Visual language

- Responsibility nodes use names and one-line descriptions, never class or file names.
- The primary path reads left to right.
- Conditional branches carry affirmative, plain-language labels.
- A returning edge visibly expresses a loop.
- Technical evidence never appears as graph nodes.
- An empty Workflow identifies a leaf Responsibility rather than an error.
- Node selection previews the contract; entering a node changes the focused Workflow and breadcrumb.

## 9. Versioning and bidirectional alignment

Accepted `DesignVersion`s remain immutable. JSON assets are portable projections backed by SQLite transaction and review state.

The forward chain is:

```text
SpecificationItem
    → SpecificationResponsibilityLink
    → Responsibility / Workflow
    → ImplementationLink
```

The reverse change path is:

```text
changed backend artifact
    → affected ImplementationLinks
    → affected Responsibilities
    → parent Workflows that reference them
    → linked SpecificationItems
```

A scan never silently rewrites an accepted model. It records a CodeSnapshot, derives findings against current ImplementationLinks, and lets an Agent propose a versioned semantic patch.

## 10. MCP surface

MCP is the required Agent interface. The capability graph provides:

- project and version inspection;
- specification inspection;
- Responsibility inspection and recursive traversal;
- Workflow validation and path tracing;
- typed design proposals and explicit acceptance;
- backend repository snapshot ingestion;
- artifact-to-Responsibility impact lookup;
- mapping revisions, findings, diffs, and portable export.

Agent method rules:

1. Filter frontend and technical noise before semantic modeling.
2. Name Responsibilities in product-readable language.
3. Keep each Responsibility cohesive and at one abstraction level.
4. Put composition only in Workflow node references.
5. Preserve conditions and loops that change behavior.
6. Attach implementation evidence to every inferred leaf.
7. Stage changes; never overwrite accepted design directly.

## 11. Acceptance criteria

CoIntent 0.3 is complete when:

- the persisted and portable model uses schema 0.3;
- existing 0.2 assets remain readable through migration;
- no RoleObject vocabulary remains in the primary API or UI;
- the Idea Factory baseline has recursive Responsibility Workflows and backend-only evidence;
- a user can select a specification, enter a root Responsibility, and repeatedly drill into child nodes;
- cycles render as returning Workflow edges;
- data members, inputs, outputs, and code evidence are inspectable without exposing class diagrams;
- MCP can read, validate, propose, accept, traverse, and compare the model;
- automated tests, production frontend build, browser review, remote master push, and Beijing deployment pass.
