# ADR-0003: MCP Is the Control Plane; Signed HTTPS Is the Artifact Data Plane

**Status:** Accepted  
**Date:** 2026-09-10  
**Related:** [ADR-0002](adr-0002-native-ua-distribution.md), [ADR-0005](adr-0005-central-ua-state.md)

## Context

CoIntent MCP is the only Agent-facing product interface. UA graphs may exceed normal model context and tool
argument limits, and a complete incremental checkpoint plus exact source content can be much larger. Making the
model reproduce those bytes as MCP JSON arguments is slow, expensive, fragile, and impossible to resume safely.
MCP also has no standard server operation that reads an arbitrary client-local file.

## Decision

MCP remains the only control, identity, and product-operation plane. Bulk bytes use a narrow HTTPS data plane
authorized exclusively by an MCP operation.

```text
MCP begin/inspect/complete
        │ issues a short-lived transfer capability
        ▼
direct HTTPS upload/download of opaque artifacts
        │ digest-bound staging
        ▼
MCP complete → validate → atomically publish
```

No permanent upload credential, general file API, local CoIntent client, or browser upload form is introduced.
The Agent uses ordinary platform tools such as `curl` to transfer an archive without passing its contents through
the language model.

## Transfer capability

Each capability is:

- random, opaque, stored only as a digest, and time limited;
- bound to one refresh, project, initiating MCP principal, direction, artifact kind, expected size, and SHA-256
  digest at issuance;
- single-purpose; uploads are single-completion and idempotent for the same digest, while checkpoint downloads
  may be retried until expiry;
- unusable to name an arbitrary server path;
- subject to configured byte limits and streaming digest verification.

The URL itself is deliberately a bearer capability so ordinary `curl` does not need the Agent's long-lived MCP
credential. Possession authorizes only that one transfer until expiry; MCP preparation/completion calls remain
restricted to the principal that requested the refresh lease. A leaked live URL is therefore a bounded but real
risk and must not be logged or pasted into chat.

The server stages bytes outside SQLite. `complete-refresh` succeeds only after every required artifact is present
and verified. Failed, expired, or abandoned staging never changes the visible Observation.

Browser graph/source loading remains authenticated read-only HTTP as already designed. It is not routed through
MCP and is not an Agent product-operation channel.

## Source acquisition

In V1 the Agent uploads a standard `git archive --format=tar.gz` of the frozen commit through the signed data
plane. The server checks Git's embedded commit marker, derives the content manifest, and hashes every extracted
file. A future central-origin fetch may eliminate that upload when the service independently has repository
credentials, but it is not part of the V1 contract and cannot be assumed during onboarding.

The server never accepts the current working directory as a source coordinate. Archive paths, sizes, entry count,
file types, and expansion ratio are validated before extraction.

V1 rejects repositories whose frozen tree contains submodules, Git LFS pointers, symbolic links, or
`export-ignore`/`export-subst` attributes. Those cases need a richer manifest that binds non-regular and external
objects to the top-level commit; pretending that ordinary `git archive` represents them would weaken provenance.

## Rejected alternatives

- **Large MCP arguments:** model-mediated, token-expensive, prone to truncation, and not resumable.
- **UA MCP server:** unnecessary; humans use UA's visual Dashboard and CoIntent owns product semantics.
- **CoIntent local CLI:** duplicates Agent distribution and adds a second user installation concept.
- **Permanent generic upload endpoint:** expands authority beyond a refresh-scoped pipeline.

## Consequences

"MCP only" means one Agent-visible control surface, not that multi-megabyte binary data is encoded into model tool
calls. A deployment that forbids the signed HTTPS data plane supports inspection/design but cannot support remote
publication at production scale.
