# CoIntent Modeling Method

**Status:** 0.3 operating method

**Purpose:** lift backend program logic into a product-readable Responsibility model without inventing a new universal notation

CoIntent begins with a deliberately small assumption: program logic can be explained as objects that own coherent responsibilities, plus workflows that show how those objects cooperate. “Object” is a modeling lens, not an implementation constraint.

## What is borrowed

| CoIntent need | Established source | Selectively retained | Deliberately omitted |
| --- | --- | --- | --- |
| Define a semantic object | object modeling, Responsibility-Driven Design, and GRASP | encapsulated domain state, cohesive responsibility, Information Expert, explicit boundary contracts | class diagrams, method catalogs, inheritance, and one model object per code class |
| Decompose a larger responsibility | RDD and hierarchical functional modeling | progressively delegate coherent work while maintaining one abstraction altitude | separate Role, RoleObject, Function, and SubResponsibility entities |
| Describe control behavior | workflow/state-graph ideas from UML Activity and BPMN | explicit entries, sequence, condition, parallel, event, error, and cycles | executable workflow semantics, token simulation, lanes, timers, and notation conformance |
| Clarify boundaries | IDEF0 | meaningful input and output thinking, plus hierarchical refinement | full ICOM boxes, mechanisms, and controls as mandatory fields |
| Compare explanation with code | Software Reflexion Models | a high-level accepted model, observed source facts, explicit mappings, and classified gaps | treating discovered dependencies as architecture truth or automatically rewriting the model |
| Refine future product meaning | KAOS / goal-oriented requirements | questioning, obstacle discovery, and practical stopping criteria when specification authoring arrives | a Goal entity in the 0.3 model, temporal logic, and proof obligations |

These are design lenses, not badges. CoIntent keeps only concepts that improve its own job.

## Canonical Responsibility

```text
Responsibility
├── Name
├── Description
├── Data Members
├── Inputs
├── Outputs
└── Workflow? ── nodes reference other Responsibilities
```

The fields answer six product-readable questions:

1. What coherent work is owned here?
2. What meaningful state or knowledge is encapsulated here?
3. What crosses into the boundary?
4. What result, effect, or event leaves it?
5. If the work is composite, which smaller Responsibilities perform it?
6. In what sequence, branch, event path, error path, parallel path, or loop do they cooperate?

Data Members are not local variables. Inputs and Outputs are not forced to mirror function signatures. All three describe the semantic contract at the current modeling altitude.

## Decomposition rules

An Agent proposes a child Responsibility only when it creates a useful semantic boundary. Typical evidence is a distinct business decision, meaningful transformation, owned state, reusable capability, observable outcome, or conditional path.

Each Workflow canvas stays at one altitude. It contains only immediate delegated Responsibilities. Deeper details are available by entering a node, not by expanding an entire system into one graph.

Stop decomposing when the next level would mainly expose code mechanics, file structure, framework plumbing, generic CRUD, functions, or local algorithms. The resulting leaf is the lowest explanation that remains useful to a product reader.

Workflow is the sole composition truth:

```text
children(parent) = unique responsibility references in parent.workflow.nodes
```

There is no second stored tree to drift from it. Cycles remain valid because real product behavior includes retry, recurring evaluation, calibration, and feedback.

## Observation filter

Code scanning is upstream evidence collection, not semantic inference. Before modeling, Agents exclude:

- frontend and presentation code;
- logging, tracing, metrics, monitoring, and telemetry;
- dependency injection, serialization, generated clients, configuration wiring, and deployment;
- incidental Controller, Middleware, Repository, Adapter, Listener, file, class, and function names.

An implementation detail may influence a Responsibility only when it represents product-visible logic. For example, a framework validator is omitted, while “Reject an ineligible refund” can remain because it is a meaningful decision.

## Two-way operating loop

```text
human meaning
  → SpecificationItem
  → accepted Responsibility / Workflow
  → ImplementationLink
  → observed backend code

changed backend code
  → impacted ImplementationLink
  → affected Responsibility
  → parent Workflow occurrences
  → linked SpecificationItem
  → finding, explanation, and reviewed proposal
```

The upper model is normative: it records the explanation humans and Agents accepted. The source snapshot is descriptive: it records evidence of what exists. A semantic Agent judges the gap, and all changes remain version-bound proposals until explicitly accepted.

## Review questions

Review a proposed model in this order:

1. Is every name understandable without seeing code?
2. Does each Responsibility own one coherent obligation?
3. Do Data Members describe meaningful encapsulated state?
4. Do Inputs and Outputs clarify its boundary?
5. Does its Workflow contain only immediate peers at one altitude?
6. Are product-significant conditions and loops preserved?
7. Has frontend and cross-cutting technical noise been removed?
8. Does every inferred leaf have credible backend evidence or an explicit uncertainty?
9. Is the model explaining logic rather than copying code or architecture?

Deterministic quality checks report signals, not design verdicts. Human judgment remains the authority for accepted versions.

## Primary references

- Rebecca Wirfs-Brock and Alan McKean, [Responsibility-Driven Design](https://www.wirfs-brock.com/Design.html)
- Craig Larman, *Applying UML and Patterns* (GRASP)
- Object Management Group, [UML specification](https://www.omg.org/spec/UML/)
- Object Management Group, [BPMN specification](https://www.omg.org/spec/BPMN/)
- NIST, [IDEF0, FIPS 183](https://www.govinfo.gov/app/details/GOVPUB-C13-ba43579ec72306f00c01305771ffdf3b)
- Gail C. Murphy, David Notkin, and Kevin Sullivan, [Software Reflexion Models](https://www.cs.ubc.ca/~murphy/papers/rm/fse95.html)
- Axel van Lamsweerde, [KAOS tutorial](https://objectiver.com/fileadmin/download/documents/KaosTutorial.pdf)
