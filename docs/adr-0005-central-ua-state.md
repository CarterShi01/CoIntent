# ADR-0005: Centralize Immutable Observations and Complete UA Incremental State

**Status:** Accepted  
**Date:** 2026-09-10  
**Related:** [ADR-0003](adr-0003-mcp-control-and-artifact-data-plane.md), [ADR-0004](adr-0004-observation-provenance.md)

## Context

The scanning Agent and repository may move between machines, while the browser and CoIntent service are remote.
UA's useful state is larger than `knowledge-graph.json` and `domain-graph.json`: incremental analysis also depends
on metadata, structural fingerprints, configuration, ignore policy, the previous Git coordinate, and retained
scan state. Keeping only the displayed graph silently converts a machine change into a full scan.

SQLite is suitable for transactional metadata in the current single-application deployment, but large graphs,
source files, and checkpoint archives should not be model-mediated or stored as frequently rewritten SQLite
blobs.

## Decision

CoIntent maintains two separate central forms of UA data:

1. **Immutable published assets** — original validated UA graphs, source manifest/blobs, Observation revisions,
   diagnostics, tool revision, configuration digest, and exact Git coordinate.
2. **Mutable incremental checkpoint** — the last complete native UA state for one project/default-branch lineage,
   promoted only after the corresponding Observation publishes successfully.

SQLite is the transactional authority for identities, states, leases, digests, and current pointers. A central
content-addressed asset root stores immutable JSON, source blobs, checkpoint archives, and temporary uploads.
SQLite and the asset root are one backup/restore unit.

## Required checkpoint content

The checkpoint manifest includes every existing native state file required by the pinned UA release, including at
least:

- `knowledge-graph.json`;
- `meta.json`;
- `fingerprints.json`;
- `config.json`;
- `.understandignore`;
- `intermediate/scan-result.json`;
- any release-specific merge/subdomain state declared by the compatibility manifest.

Transient `tmp`, recent `.trash-*`, logs, local Dashboard state, and `diff-overlay.json` are not promoted.

Checkpoint reuse requires the same project, default branch, compatible UA commit, configuration/ignore profile,
and an ancestor base commit. Missing, corrupt, incompatible, or divergent state causes an explicit full fallback.
Unchanged source content reuses the current Observation and spends no UA tokens. Domain analysis may remain full
after a changed knowledge graph in this release.

## Atomic publication

1. stream artifacts into refresh-scoped staging;
2. verify size, digest, safe manifest paths, and required files;
3. validate the complete code/UA coordinate and project the Observation;
4. atomically move content-addressed assets to their final names;
5. in one SQLite transaction insert immutable rows and compare-and-swap the current pointer;
6. only then promote the new incremental checkpoint;
7. remove consumed upload staging after completion and expire abandoned staging after its lease.

No reader resolves mutable project `.ua` files. The embedded Dashboard reads only immutable central assets bound to
its short-lived viewer session.

## Privacy and scale

Central source storage is a new privacy boundary beyond UA's local-only model. Deployments require TLS, project
authorization, retention/deletion policy, encryption and backup policy, bounded uploads, safe archive handling,
and logs that exclude source and credentials.

SQLite remains supported for one application writer. Multiple application replicas or independent writers require
a transactional server database; remotely durable deployments should replace the local asset root with object
storage without changing the artifact manifest contract.
