# CoIntent MVP 0.1

**Status:** implemented vertical slice

**Experiment:** local `idea-factory` checkout, read only

**Public target:** `https://cointent.enjoyapier.cloud`

## 1. What this MVP proves

This version tests one product claim: a human and an agent can share a stable responsibility model without confusing that model with the current code layout.

It implements both directions of alignment:

```text
human wording ──record──> intent evidence ──proposal/review──> intended Role Model
                                                                  │
                                                                  │ many-to-many TraceLinks
                                                                  ▼
Git repository ──read only──> fact snapshot ──incremental diff──> alignment findings
```

The first direction is agent-native. A coding agent records relevant user exchanges, uses them to propose a semantic patch, and waits for an explicit acceptance or rejection. The second direction starts with deterministic repository evidence. It reports where changed artifacts touch accepted responsibilities; an agent then performs the semantic judgment.

The web interface is deliberately not a second chat client. It is a synchronized human projection of the durable state:

- **Responsibility Book:** goals, responsibility owners, selected-role detail, and implementation evidence;
- **Role Topology:** containment and collaboration at the responsibility level, plus an alignment-review rail;
- **Version header:** accepted model version, observed Git revision, and open-finding count.

## 2. Architectural boundaries

| Boundary | Owns | Does not own |
| --- | --- | --- |
| CoIntent domain | intended model, proposals, versions, intent evidence, code snapshots, trace links, findings | agent transport or generic tool discovery |
| Contexture controller | MCP discovery, Roles/Skills/Tools, typed invocation, authorization principal, explicit REST dispatch | the modeled project's Roles |
| Git scanner | reproducible artifact hashes, coarse components, import relations, snapshot deltas | design intent or autonomous Role inference |
| External coding agent | conversation, clarification, semantic interpretation, change review | silent authority to rewrite accepted intent |
| Web client | read projection and cross-selection | model mutation or chat history creation |

There are two intentionally different `Role` concepts. A Contexture Role is a capability boundary used to route an agent. A CoIntent Role is a versioned responsibility owner in the system being designed. Neither is persisted as the other.

## 3. Implemented domain model

The canonical `ProjectModel` currently contains:

- `Goal`: intended outcome and refinement parent;
- `Role`: purpose, containment parent, state, and provenance;
- `Responsibility`: owned obligation connected to goals, inputs, outputs, and constraints;
- `Relation`: collaboration, dependency, delegation, or exchange between Roles;
- `TraceLink`: many-to-many evidence from a Role to an implementation path, with kind, origin, confidence, and explanation.

`ModelPatch` supports typed upserts and removals for every model collection. Validation rejects duplicate IDs, dangling goal/role references, self-containment, unknown relation endpoints, and unsafe implementation paths.

SQLite keeps these lifecycles separate:

- `model_versions` are immutable accepted intent;
- `intent_sources` preserve original wording and an optional host reference;
- `proposals` contain a base version, proposed result, semantic diff, rationale, and evidence IDs;
- `snapshots` are content-addressed observed facts and their structural delta;
- `alignment_findings` are review items, never automatic design decisions.

Proposal acceptance uses optimistic concurrency. If the current accepted version differs from a proposal's base version, acceptance fails instead of applying a last-writer-wins update.

## 4. Contexture capability graph

```text
project-alignment
├── design-convergence
│   ├── Skill: converge-design
│   └── Tools: health, list/create project, inspect/overview model,
│              record/list intent, propose/list/resolve proposal
├── implementation-mapping
│   ├── Skill: map-implementation
│   └── Tools: ingest/list snapshot
├── alignment-review
│   ├── Skill: review-implementation-change
│   └── Tools: list/resolve finding
└── history
    └── Tool: compare-versions
```

The three Skills encode the MVP's policy:

1. Preserve source wording before changing a model.
2. Stage a version-bound proposal; do not directly mutate the accepted baseline.
3. Treat a file tree as evidence, not as the Role decomposition.
4. Let observed implementation challenge intent, but never silently redefine it.

The same compiled Contexture runtime backs Streamable HTTP MCP at `/mcp` and a small allowlist of read-only REST routes used by the browser.

## 5. HTTP contracts

### MCP

| Endpoint | Authorization | Purpose |
| --- | --- | --- |
| `POST /mcp` | `Bearer $COINTENT_MCP_TOKEN` in network deployments | Contexture Streamable HTTP transport |
| `GET /.well-known/*` | protocol metadata | MCP authorization/resource discovery |

For a local process-based client, `cointent mcp` serves the same declaration over stdio and needs no network token.

### Read API

| Route | Required query | Projection |
| --- | --- | --- |
| `GET /api/health` | none | service health |
| `GET /api/v1/projects` | none | known projects |
| `GET /api/v1/overview` | `project_id` | counts, current version, current scan |
| `GET /api/v1/model` | `project_id`, optional `version` | accepted model version |
| `GET /api/v1/intent-sources` | `project_id` | preserved conversation evidence |
| `GET /api/v1/proposals` | `project_id`, optional `status` | proposal queue |
| `GET /api/v1/snapshots` | `project_id` | observed facts and deltas |
| `GET /api/v1/findings` | `project_id`, optional `status` | drift review queue |

REST is intentionally read-only. Production binds the application to loopback and exposes it through the host Nginx. The web UI and REST routes are protected together by Nginx Basic Auth. MCP mutation uses an independent bearer token, and MCP discovery metadata remains public so protocol clients can authenticate correctly.

## 6. Incremental scan contract

The scanner operates on Git-tracked paths by default and records:

- repository origin, branch, revision, and tracked dirty state;
- artifact path, coarse kind, language, coarse component, size, and SHA-256;
- Python package imports and JavaScript/TypeScript relative imports;
- discovered Python command entry points.

It skips Git metadata, dependency/build caches, generated Idea Factory results, and common test caches. Untracked files are opt-in.

A snapshot ID is derived from revision, artifact hashes, and relations. Repeated scans of identical evidence are idempotent. On ingestion, CoIntent compares the new snapshot with the last one:

- added, modified, and removed paths;
- added and removed observed dependency relations;
- changed paths resolved through accepted TraceLink path prefixes;
- observed dependencies whose endpoints map to different Roles.

The deterministic layer can say that mapped evidence changed. It cannot decide by itself whether the change is a valid internal implementation detail, a design evolution, a defect, an accepted exception, or uncertain. That classification belongs to the `review-implementation-change` Skill and its human review policy.

### Portable handoff

```bash
uv run cointent --database /tmp/local.db scan /path/to/repository \
  --project-id project-id --export snapshot.json
```

The produced JSON is portable. An agent can submit it to the remote `ingest-snapshot` MCP Tool. This separates local source access from the hosted alignment service: the hosted service never needs repository credentials or a writable checkout.

## 7. Idea Factory experiment

The initial scan of the local Idea Factory checkout observed 170 tracked artifacts and 67 source import relationships at revision `523395e330f7bf02bb58064ac956e29879d2a309`.

The agent-curated baseline contains eight responsibility Roles:

1. Idea Factory
2. Signal Intelligence
3. Candidate Generation
4. Evaluation Gate
5. Learning Loop
6. Shared Domain Contract
7. Operator Surface
8. Workflow Mirror

It includes three goals, nine responsibilities, seven collaborations/dependencies, and eleven implementation TraceLinks. This is explicitly an interpretation grounded in scan evidence, not scanner-generated design truth. It demonstrates that a procedural or mixed codebase can be explained by responsibility Roles without requiring one Role per directory, class, or function.

## 8. Local operation

```bash
uv sync --extra dev
npm --prefix web install

uv run cointent scan /home/claude-user/oc-hands-workspace/idea-factory \
  --project-id idea-factory --name "Idea Factory" --seed-idea-factory

uv run cointent serve
npm --prefix web run dev
```

Useful commands:

```bash
# Export accepted intent independently of observed evidence.
uv run cointent export-model --project-id idea-factory --output model.json

# Serve MCP directly to a local agent host.
uv run cointent mcp

# Verify backend and frontend.
uv run --extra dev pytest
npm --prefix web run build
```

## 9. Beijing deployment

The deployment follows the established One Creator pattern:

- build the Vite client in a pinned Node container;
- export static files and publish them to `/var/www/cointent` for the existing host Nginx;
- run only the Python service in Docker, bound to `127.0.0.1:8811`;
- scan Idea Factory locally and transfer only portable snapshot/model fixtures;
- preserve remote `.env` and SQLite data across releases;
- verify the published `index.html` hash, API health, seeded model, and unauthenticated MCP rejection.

After committing a release:

```bash
bash deploy/release-beijing.sh
```

For the first release before public DNS and TLS exist, the server-side release can be validated separately:

```bash
bash deploy/release-beijing.sh --skip-public
```

One-time host setup requires root and must run only after the DNS A/AAAA records resolve to the Beijing host:

```bash
cd /home/deploy/cointent
sudo bash deploy/install-host.sh
```

The installer asks for a real Let's Encrypt notification email. It installs the staged `carter` password hash when one is present; otherwise it securely prompts for a password of at least 20 characters. The plaintext web password is never stored by CoIntent. ACME challenges and MCP protocol routes explicitly bypass Basic Auth: certificate issuance needs the former, while `/mcp` retains its separate bearer-token boundary.

The unprivileged release path can create `/var/www/cointent` through its Docker access, matching the existing One Creator static-publish approach. It cannot safely install an Nginx site or obtain a Let's Encrypt certificate without one-time host authority.

## 10. Deliberate MVP limits

- The baseline inference for Idea Factory is curated code, not a general semantic model generator.
- The scanner understands coarse files and selected import relationships, not runtime behavior.
- Findings are path/dependency evidence; an external agent supplies semantic review.
- Conversation capture is explicit through `record-intent`; automatic host transcript hooks are not yet defined.
- The web client is read-only; proposal review happens through an agent host in this version.
- Static bearer authentication is sufficient for a single-owner MVP, not a multi-tenant product.
- SQLite is appropriate for one process and one owner; distributed workers require a different persistence/concurrency design.

These limits preserve the important boundary: CoIntent may be incomplete, but it must not claim certainty it does not have.
