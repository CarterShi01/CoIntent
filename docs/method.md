# CoIntent Modeling Method

**Status:** MVP operating method

**Audience:** agents and humans reviewing a CoIntent Role Model

CoIntent does not invent a new universal software-design notation. It combines a
small, deliberately selected part of four established approaches around the
product's actual job: converge intent into a responsibility model, then compare
implementation evidence with that accepted model.

## Method composition

| Need in CoIntent | Concept borrowed | What CoIntent keeps | What CoIntent leaves out |
| --- | --- | --- | --- |
| Idea to ProductFunctions | KAOS / goal-oriented requirements engineering | progressive clarification, responsibility assignment, obstacles as questions, and an assignable/verifiable stopping condition | temporal logic, proof obligations, a separate Goal tree, and claims of formal completeness |
| ProductFunctions to RoleObjects | OOram role modeling | systems as networks of collaborating roles; roles are positions in a collaboration and are independent of classes | the complete OOram process and notation set |
| Role boundary quality | Responsibility-Driven Design | purpose, cohesive responsibilities, knowledge/behavior ownership, and explicit collaborators | class-card ceremonies and a requirement to implement with objects |
| Boundary contracts | IDEF0 | meaningful inputs, outputs, and constraints; hierarchical decomposition when useful | full ICOM diagram syntax and treating every Role as a function box |
| Code to Role Model | Software Reflexion Models | a normative high-level model, an observed source model, explicit mappings, and convergence/divergence/absence findings | automatic promotion of observed code structure into intended design |

The approaches are lenses, not badges. A field should remain empty when adding
it would not clarify responsibility or reduce uncertainty.

## Canonical review order

An agent reviews a model in the following order because later checks depend on
the authority established by earlier checks.

1. **Source fidelity.** Separate words supplied by the human, accepted
   decisions, assumptions, and code-derived hypotheses. Preserve exact intent
   evidence before proposing a change.
2. **ProductFunction coverage.** Refine a function only while the next level changes ownership,
   observable behavior, constraints, or verification. A leaf function should be assignable and have a
   credible way to recognize success.
3. **Responsibility ownership.** Every required outcome needs a clear owner.
   Challenge orphan responsibilities, conflicting owners, fragmented ownership,
   and Roles whose purpose is too broad to explain.
4. **Collaboration.** State the promises or dependencies that cross Role
   boundaries. A Role is understood through both its responsibilities and the
   collaborators it needs.
5. **Operational contract.** Add inputs, outputs, and constraints when they make
   a promise testable or prevent ambiguity. Do not fill fields mechanically.
6. **Implementation independence.** Reject a decomposition that merely renames
   directories, classes, services, people, or Agents. Any of those may realize a
   Role, and mappings are many-to-many.
7. **Evidence and uncertainty.** Cite intent sources, snapshots, tests, paths, or
   decisions. State what the evidence cannot establish.

## Two directional workflows

### Human idea to accepted Role Model

```text
conversation
  -> preserved intent source
  -> goal clarification
  -> responsibility assignment
  -> Role and collaboration proposal
  -> method review
  -> explicit human decision
  -> immutable accepted version
```

The stopping condition is practical rather than formal: the model is ready for
a baseline when the important outcomes have intelligible owners, boundary
promises, and a credible verification path, while remaining uncertainties are
visible.

### Implementation to alignment view

```text
repository scan
  -> observed artifact snapshot
  -> explicit many-to-many TraceLinks
  -> intended/observed comparison
  -> convergent, absent, divergent, boundary-change, unmapped, or uncertain finding
  -> agent explanation
  -> human-reviewed model patch or implementation action
```

Code is evidence of what exists. It is not authority for what should exist. A
stable implementation pattern may justify a design proposal, but it cannot
silently edit the accepted Role Model.

## Runtime enforcement in the MVP

The Contexture capability graph makes this method available to MCP agents:

- `converge-design` applies the method while turning dialogue into a proposal;
- `review-role-model` performs the seven-stage semantic review;
- `map-implementation` applies the Reflexion Model boundary to code evidence;
- `review-implementation-change` classifies implementation drift before action;
- `assess-model-quality` reports deterministic structural signals such as an
  unowned goal or an empty leaf Role.

Quality signals are prompts for judgment, not validation failures. Semantic
changes remain version-bound proposals, and only an explicit acceptance creates
a new intended-model version.

## Language and identifier policy

The web interface and canonical accepted model content are English. Stable IDs,
repository paths, protocol enum values, and source-code identifiers are also
English. `IntentSource` preserves the original human or Agent wording in any
language so translation never replaces provenance.

## Primary references

- A. van Lamsweerde, [KAOS tutorial](https://objectiver.com/fileadmin/download/documents/KaosTutorial.pdf)
- Trygve Reenskaug et al., [Working with Objects: The OOram Software Engineering Method](https://www.manning.com/books/working-with-objects)
- Rebecca Wirfs-Brock and Alan McKean, [Responsibility-Driven Design](https://www.wirfs-brock.com/Design.html)
- NIST, [Integration Definition for Function Modeling (IDEF0), FIPS 183](https://www.govinfo.gov/app/details/GOVPUB-C13-ba43579ec72306f00c01305771ffdf3b)
- Gail C. Murphy, David Notkin, and Kevin Sullivan, [Software Reflexion Models](https://www.cs.ubc.ca/~murphy/papers/rm/fse95.html)
