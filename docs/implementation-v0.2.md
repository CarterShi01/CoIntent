# CoIntent 0.2 Implementation Plan and Runbook

**Status:** executable delivery plan  
**Target:** `https://cointent.enjoyapier.cloud` on the Beijing host  
**Experiment project:** local, read-only `idea-factory`

## 1. Delivery strategy

The implementation is a vertical migration from schema 0.1, not a parallel rewrite. Each phase leaves a testable boundary and retains read compatibility with existing accepted data.

### Phase 1 — Domain schema and compatibility

1. Introduce `ProductFunction`, expanded `RoleObject`, `FunctionRoleLink`, and renamed `RoleRelation`.
2. Change `Responsibility.goal_ids` to `function_ids`.
3. Change `ProjectModel` to schema `0.2`.
4. Accept legacy `goals`, `roles`, `relations`, and legacy patch fields at validation time; normalize all reads and new writes to 0.2.
5. Validate unique IDs, hierarchy endpoints and cycles, relationship endpoints, many-to-many link endpoints, and safe relative implementation paths.

Exit check: both legacy fixtures and native 0.2 models validate and semantic diffs use 0.2 collection names.

### Phase 2 — Project, persistence, and version axes

1. Add project description, default branch, canonical language, and status through an additive SQLite migration.
2. Retain immutable `model_versions` and content-addressed `snapshots`.
3. Add `mapping_revisions` and `change_sets` tables with project indexes.
4. Atomically project project metadata, accepted designs, and snapshots to JSON.
5. Backfill missing JSON projections at process startup.
6. Expose project inspection and updates, accepted design history, latest baseline, and code snapshot history separately.

Exit check: restart preserves data, old databases migrate without destructive SQL, JSON assets reconstruct from stored versions, and stale proposal acceptance fails.

### Phase 3 — Bidirectional domain operations

Human to implementation:

1. Record original `IntentSource`.
2. Inspect/refine the ProductFunction tree.
3. analyze affected RoleObjects and artifacts.
4. start a ChangeSet;
5. propose a typed patch against the current accepted version;
6. explicitly accept it to create a new DesignVersion;
7. attach that version and generate an implementation brief.

Implementation to human:

1. deterministically scan tracked repository facts;
2. ingest an idempotent CodeSnapshot;
3. materialize a MappingRevision for the current DesignVersion;
4. compare artifact and dependency deltas against TraceLinks and RoleRelations;
5. create findings for missing, crossing, changed, or unmapped evidence;
6. resolve the finding as implementation work, design evolution, mapping correction, exception, or uncertainty;
7. attach the reviewed snapshot and close the ChangeSet.

Exit check: the design and code coordinates can advance independently and are reunited only by an explicit mapping/review record.

### Phase 4 — Contexture MCP surface

Implement the following progressively disclosed Tools.

| Role | Read Tools | Mutation Tools |
| --- | --- | --- |
| `project-management` | health, list/inspect project, overview, list design versions, inspect alignment baseline | create project, update project settings |
| `product-design` | inspect design/function tree/function/proposals, list intent, assess catalog, analyze impact | record intent, propose patch, resolve proposal |
| `responsibility-design` | inspect RoleObject forest/object, assess Role quality | changes use the shared typed design proposal |
| `implementation-alignment` | list/compare snapshots and mapping revisions, find artifact links, compare design to code, list findings | ingest snapshot, record mapping revision, resolve finding |
| `change-lifecycle` | list/inspect ChangeSets, generate implementation brief | start/update ChangeSet |
| `history-and-portability` | compare design versions, export design bundle | none |

All complex request objects use Pydantic schemas so MCP clients discover complete nested contracts. Skills encode method judgment and call only the Tools required for their workflow.

Exit check: Contexture compilation succeeds, every reference is discoverable, patch and snapshot schemas reject unknown properties, and Streamable HTTP rejects a missing/invalid token.

### Phase 5 — Human review workspace

1. Replace the old Goal/Role projection with an English ProductFunction/RoleObject workspace.
2. Add project and DesignVersion selectors plus CodeSnapshot/MappingRevision indicators.
3. Render the ProductFunction tree with coverage and selected-state cues.
4. Render a multi-root RoleObject forest with containment edges and typed collaboration overlays.
5. Implement bidirectional cross-highlighting through `FunctionRoleLink`.
6. Show complete selected RoleObject details and implementation evidence below the graph.
7. Keep proposal, finding, and ChangeSet review queues visible without adding a second chat surface.
8. Preserve responsive behavior and keyboard-accessible controls.

Exit check: a user can start from one ProductFunction, see accountable RoleObjects, inspect their contracts and code evidence, switch accepted versions, and identify unresolved alignment work.

### Phase 6 — Experiment migration and release

1. Scan the sibling Idea Factory checkout read-only and ingest the new snapshot.
2. Reject any stale schema-0.1 proposal instead of trying to reinterpret it.
3. record the source intent that motivated the 0.2 redesign;
4. stage and accept one 0.2 English baseline through the same proposal path used by Agents;
5. update the project metadata without storing credentials;
6. verify JSON assets exist for the accepted version and snapshot;
7. build the frontend and backend image, deploy through the existing Beijing script, and preserve remote `.env` and runtime volume;
8. perform authenticated browser and MCP protocol smoke tests against the public domain.

Exit check: public health is green, browser login works, protected REST is not public, MCP requires its token, the accepted model is English schema 0.2, and the review path below works.

## 2. REST projection

REST is an explicit read-only allowlist backed by the same Contexture runtime:

| Route | Main parameters |
| --- | --- |
| `GET /api/health` | none |
| `GET /api/v1/projects` | none |
| `GET /api/v1/project` | `project_id` |
| `GET /api/v1/overview` | `project_id` |
| `GET /api/v1/design-versions` | `project_id` |
| `GET /api/v1/alignment-baseline` | `project_id` |
| `GET /api/v1/model` | `project_id`, optional `design_version` |
| `GET /api/v1/functions` | `project_id`, optional `design_version`, root and depth |
| `GET /api/v1/roles` | `project_id`, optional `design_version`, root and depth |
| `GET /api/v1/intent-sources` | `project_id`, optional `limit` |
| `GET /api/v1/proposals` | `project_id`, optional `status` |
| `GET /api/v1/snapshots` | `project_id`, optional `limit` |
| `GET /api/v1/findings` | `project_id`, optional `status` |
| `GET /api/v1/change-sets` | `project_id`, optional `status` |

The browser cannot mutate accepted intent. Product mutations stay on authenticated MCP and follow proposal/version rules.

## 3. Migration behavior

No destructive database migration is required. New project columns and tables are additive. Whenever a stored 0.1 model is read:

- `Goal.title` becomes `ProductFunction.name`;
- open Goals become questioned ProductFunctions;
- Roles become RoleObjects;
- `goal_ids` become `function_ids`;
- Relations become RoleRelations;
- absent expanded fields receive explicit empty defaults.

The normalized model is returned as 0.2, while the historical SQLite row remains byte-for-byte unchanged. The next accepted proposal writes native 0.2 JSON. This preserves historical evidence without making two schema versions visible to clients.

## 4. Verification matrix

Backend automated checks cover:

- native and legacy model validation;
- cycle, endpoint, and unsafe-path rejection;
- proposal isolation, acceptance, stale-base protection, and semantic diffs;
- project settings and immutable design history;
- JSON projection/backfill;
- idempotent snapshots, mapping revisions, and findings;
- ChangeSet and implementation-brief lifecycle;
- Contexture references and nested MCP schemas;
- REST dispatch, browser session protection, and MCP bearer protection.

Frontend checks cover TypeScript compilation and the production Vite build. Public smoke testing covers login, project/version selection, function-to-Role cross-navigation, RoleObject details, responsive layout, console errors, health, protected REST, and MCP rejection/acceptance.

Commands:

```bash
uv run --extra dev pytest
npm --prefix web run build
bash deploy/release-beijing.sh --skip-public
```

## 5. Operational recovery

- SQLite and `runtime/projects` are in the persistent `/data` volume.
- Release replacement never deletes the runtime directory or `.env`.
- Duplicate snapshot ingestion is safe.
- A rejected or stale proposal does not alter the current version.
- Missing JSON projections are recreated at startup from SQLite.
- Restore requires the runtime directory; JSON design exports remain independently readable audit artifacts.
- Rollback uses a previously built backend image and matching static web release; immutable accepted data needs no rollback migration.

## 6. Review path

After deployment:

1. Open `https://cointent.enjoyapier.cloud` and sign in.
2. Select **Idea Factory** and its latest accepted DesignVersion.
3. In **Product Functions**, select a leaf function and observe highlighted RoleObjects.
4. Select one highlighted RoleObject; inspect its purpose, responsibilities, knowledge, input/output contract, constraints, collaborators, function coverage, and implementation evidence.
5. Follow one implementation path to understand how the conceptual responsibility maps into a procedural/mixed repository.
6. Switch to an earlier DesignVersion to see accepted design history independently from the current CodeSnapshot.
7. Inspect pending proposals, open alignment findings, and ChangeSets to see what is agreed versus still under review.
8. From an MCP-capable Agent, open `cointent`, follow the appropriate Skill, inspect the same accepted version, and stage a proposal. Refresh the browser to see the shared state.

This route demonstrates the MVP's actual promise: both human and Agent act on the same versioned functional-responsibility model while code remains separately observed evidence.
