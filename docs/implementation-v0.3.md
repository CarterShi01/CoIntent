# CoIntent 0.3 Implementation Plan

**Target:** deploy a reviewable recursive Responsibility Workflow MVP to `cointent.enjoyapier.cloud`.

## Phase 1 — Freeze the model

1. Add schema 0.3 records: `SpecificationItem`, `Responsibility`, `Workflow`, `WorkflowNode`, `WorkflowEdge`, `SpecificationResponsibilityLink`, and `ImplementationLink`.
2. Add strict endpoint, uniqueness, safe-path, and entry validation while allowing Workflow cycles.
3. Replace the 0.2 patch and semantic diff fields with 0.3 fields.
4. Add deterministic 0.2-to-0.3 read migration.

Exit checks:

- cyclic workflows validate;
- dangling Workflow references fail;
- repeated Responsibility references remain one definition;
- legacy assets parse as schema 0.3.

## Phase 2 — Repository and alignment

1. Replace function-tree and RoleObject queries with specification and Responsibility queries.
2. Add focused Responsibility inspection containing its immediate Workflow, referenced child objects, parents, specification links, and implementation evidence.
3. Add Workflow path tracing with bounded traversal for cycles.
4. Rewrite coverage and quality signals for Responsibilities.
5. Rewrite change findings and artifact impact around `responsibility_ids`.
6. Keep database columns compatible where a physical rename would add migration risk; normalize all public payloads to 0.3 vocabulary.
7. Preserve immutable version assets and mapping revisions.

Exit checks:

- project/version/proposal flows remain transactional;
- incremental backend changes identify mapped Responsibilities;
- implementation mapping current/stale semantics remain correct.

## Phase 3 — Backend-only scanner

1. Exclude frontend paths and frontend file types.
2. Classify only backend source and tests as evidence candidates.
3. Ignore observability, generated, deployment, and framework-noise paths for semantic findings.
4. Retain raw snapshot hashes and backend dependency facts needed for incremental comparison.

Exit checks:

- TSX/JSX/CSS/HTML and common frontend directories never enter snapshots;
- logging/telemetry modules do not generate unmapped semantic findings;
- Idea Factory scan remains deterministic.

## Phase 4 — MCP and REST

1. Publish Responsibility-native tools and skills through Contexture.
2. Keep mutation behind typed, version-bound proposals.
3. Add explicit REST reads for the browser workspace.
4. Update overview, export, health, and capability descriptions to schema 0.3.

Required Agent workflows:

- inspect a Responsibility and its immediate Workflow;
- traverse into a referenced child Responsibility;
- trace bounded Workflow paths, including loops;
- find Responsibilities affected by an artifact;
- propose and accept a Responsibility/Workflow update;
- compare accepted design with the latest backend snapshot.

Exit checks:

- Contexture compiles the full capability graph;
- stdio and HTTP MCP expose the typed schemas;
- protected REST reads return the same accepted model.

## Phase 5 — Idea Factory baseline

1. Replace the RoleObject fixture with a native 0.3 Responsibility model.
2. Model a top-level idea-screening Responsibility and recursively decompose acquisition, qualification, candidate development, evaluation, selection, and learning.
3. Include a real conditional rejection path and a feedback loop from outcome learning to calibration.
4. Map only backend Idea Factory artifacts; omit Studio/frontend evidence.
5. Export the new fixture and create a new accepted production DesignVersion.

Exit checks:

- every root and composite Responsibility has a meaningful Workflow;
- every leaf has backend code evidence or an explicit low-confidence gap;
- frontend paths are absent from the model.

## Phase 6 — Frontend redesign

Design direction:

- **Subject:** a product manager reading a living program logic atlas.
- **Single job:** enter one Responsibility and understand how smaller Responsibilities cooperate to fulfill it.
- **Palette:** Ink `#17211f`, Paper `#f3f5f0`, Blueprint `#dce8e3`, Signal `#e66a3d`, Current `#146b5d`, Muted `#72807b`.
- **Type:** system humanist sans for prose, compact mono for identity/evidence, restrained editorial serif for the focused Responsibility title.
- **Layout:** narrow specification rail, dominant workflow desk, contextual contract/evidence drawer.
- **Signature:** a persistent breadcrumb “responsibility spine” whose segments mirror successive graph entry, making recursive descent tangible.

Wireframe:

```text
┌ project / version / code snapshot / mapping ──────────────────────┐
├ Specification ┬ Responsibility spine + focused contract ──────────┤
│ plain language│ Root / Child / Current                            │
│ statements    │ [data] [inputs] [outputs]                         │
│               ├ Immediate Workflow canvas ────────────────────────┤
│               │ [child] → [child] ─condition→ [child] ↩           │
│               ├ Evidence / review drawer ─────────────────────────┤
└───────────────┴────────────────────────────────────────────────────┘
```

Implementation steps:

1. Replace ProductFunction/RoleObject state with specification selection and Responsibility navigation stack.
2. Render only the focused Responsibility's immediate Workflow.
3. Draw normal, conditional, event, error, parallel, and returning edges distinctly.
4. Make node selection preview and node activation enter the child.
5. Show data/input/output contract beside the canvas.
6. Keep implementation evidence and review state secondary.
7. Support empty, loading, error, keyboard-focus, reduced-motion, narrow-screen, and recursive-reference states.

Exit checks:

- the primary view contains no RoleObject vocabulary;
- at least three levels of Idea Factory can be navigated;
- browser console is clean and mobile layout remains usable.

## Phase 7 — Verification and release

1. Update and run Python unit/integration tests.
2. Run TypeScript checking and the production Vite build.
3. Run a local HTTP smoke test with login protection.
4. Use a real browser to validate selection, node entry, breadcrumb return, version switching, evidence inspection, responsive behavior, and console output.
5. Run a real MCP client session against CoIntent and traverse the new model.
6. Scan Idea Factory with the backend-only scanner and import the 0.3 model.
7. Review the Git diff for credentials and unrelated changes.
8. Commit and push `master`.
9. Deploy through the existing Beijing release path.
10. Verify public health, authentication, core REST, UI assets, and MCP authentication.

Release evidence must record:

- final commit SHA;
- test and build results;
- deployed image/version;
- public health result;
- exact human review path.
