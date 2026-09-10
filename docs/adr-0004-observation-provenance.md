# ADR-0004: Publish Observations Only from an Exact Clean Git Coordinate

**Status:** Accepted  
**Date:** 2026-09-10  
**Related:** [ADR-0001](adr-0001-codemap-engine.md), [ADR-0003](adr-0003-mcp-control-and-artifact-data-plane.md)

## Context

UA labels its graph with `git rev-parse HEAD` but analyzes filesystem content. A dirty checkout can therefore
produce a graph whose declared commit does not contain the analyzed bytes. UA may also redirect analysis from an
ephemeral Git worktree to the main checkout. Finally, UA emits unsigned JSON, so a server receiving artifacts
from the same conversational Agent cannot cryptographically prove that no local process edited them.

## Decision

Every published current-system Observation is derived from a clean, committed, immutable coordinate:

1. the project default branch and exact HEAD commit are declared before analysis;
2. common transport spellings of the registered Git origin, such as GitHub SSH and HTTPS URLs, are normalized to
   one repository identity before comparison;
3. tracked modifications and non-ignored untracked files must be absent;
4. analysis runs in a detached temporary worktree for that commit;
5. `UNDERSTAND_NO_WORKTREE_REDIRECT=1` keeps UA on that worktree;
6. the standard Git archive must carry the frozen commit in its PAX metadata and the derived source manifest
   hashes every archived tracked file;
7. UA graph commit, paths, line ranges, node/edge references, schema, and source digests are validated;
8. semantic claims without resolvable structural source evidence are omitted and diagnosed;
9. candidate publication is append-only and switches the current pointer only after complete projection succeeds.

V1 supports one active default-branch analysis lineage per CoIntent project. Git submodules, LFS pointers,
tracked symbolic links, and archive-altering `export-ignore`/`export-subst` attributes are rejected before
spending UA tokens. Supporting them later requires an explicit composite-repository/source-manifest contract.

## Authority boundary

CoIntent provides three different guarantees:

| Guarantee | Contract |
|---|---|
| Product mutation authority | Strong: browser and ordinary Agent tools cannot replace or edit an Observation. |
| Code-coordinate integrity | Strong against mistakes and transport corruption: every published evidence reference resolves into the captured manifest and digest. |
| Native-UA attestation | Not claimed: upstream UA does not sign its output and the local Agent is not an attested runner. |
| Semantic completeness | Not claimed: summaries and domain interpretation include model judgment. |

The product wording is **validated code-derived observation**, not formal proof of the complete architecture.
The Git PAX marker is an integrity check, not a signature: the code-local Agent could fabricate both it and graph
JSON. Achieving adversarial source/native-UA attestation later requires a trusted CI/server runner, signed local
runner, or trusted execution environment and is intentionally outside this release.

## Public and pipeline operations

There is no `upsert-observation`, `replace-current-graph`, or raw graph mutation operation. A public refresh request
creates a coordinate-bound state machine. Transfer and completion operations can only add artifacts to that job;
the validation/projector service owns publication. Replaying a completed job is idempotent and cannot replace it.

## Failure behavior

- Dirty, wrong-branch, divergent, or mismatched coordinates fail closed.
- Partial UA output remains diagnostic staging and never becomes current.
- A stale previous Observation remains readable and visibly stale.
- Concurrent completion uses compare-and-swap against the refresh base coordinate.
- Design revisions are independent and are never merged into current truth.
