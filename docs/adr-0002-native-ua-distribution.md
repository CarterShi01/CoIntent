# ADR-0002: Distribute and Run Native Understand Anything in the Agent Environment

**Status:** Accepted  
**Date:** 2026-09-10  
**Depends on:** [ADR-0001](adr-0001-codemap-engine.md)  
**Related:** [ADR-0003](adr-0003-mcp-control-and-artifact-data-plane.md), [ADR-0004](adr-0004-observation-provenance.md), [ADR-0005](adr-0005-central-ua-state.md)

## Context

CoIntent may run on a different machine from the repository. Understand Anything (UA) is not a standalone
analyzer API: it is an official package of Agent Skills, supporting scripts, subagent definitions, and a
Dashboard. Its native installer clones the upstream repository and links Skills into platform-specific Agent
directories. The current Agent then interprets the Skill and performs analysis with its own shell, filesystem,
and subagent capabilities.

The previous CoIntent runner instead required a server-local checkout, a configured headless Agent command, and
a persistent worker. That topology does not match the desired product: the user should connect one Agent to
CoIntent MCP, install native UA where the code is available, and perform all product orchestration through that
conversation.

## Decision

CoIntent does not require or install an end-user/source-host CLI, UA fork, UA MCP server, or CoIntent analysis
runtime. The centrally deployed service retains its ordinary operator entrypoint for serving MCP/HTTP and
administrative recovery; that executable is not part of the code-local installation flow.

The public root Role gains a `distribution` child. It:

1. detects the MCP client and operating-system facts supplied by the Agent;
2. returns the official native UA installation path for that supported platform;
3. records no success until the Agent reports measured post-install checks;
4. verifies the resolved Skill path, UA Git revision, plugin version, runtime prerequisites, and reload state;
5. never copies UA Skill contents into a CoIntent Role or pretends to execute client-local commands itself.

Claude Code continues to use the native plugin marketplace. Platforms supported by UA's installer continue to
use the official shell or PowerShell installer. CoIntent may select an exact unmodified upstream commit after
installation, because analyzer schema, validator, and embedded Dashboard are released as one compatibility unit.
It may not patch analyzer behavior or silently track an unverified upstream `main`.

The supported-unit identity is the upstream Git commit, not only a display version. A successfully installed but
unsupported revision produces `incompatible`, not a best-effort scan.

These checks prevent accidental version/path drift; they are evidence reported by the same code-local Agent and
are not remote attestation. The trust boundary is identical to native UA execution itself.

Installation state is deliberately not stored as a global CoIntent project fact: it belongs to a particular
Agent host and can disappear when the user changes machines or agents. Each refresh resolves the local Skill and
rechecks compatibility; SQLite stores refresh evidence and results, not a misleading permanent “UA installed” bit.

The install plan is conditional and idempotent at the orchestration level: resolve and verify an existing native
installation first; do not rerun the upstream installer when the compatible checkout and Skill links already
exist. A fresh install uses the upstream installer and then selects the exact commit. Repairing an incompatible
or colliding installation is reported explicitly rather than silently overwriting an unrelated Skill directory.

## Capability contract

Skill discovery alone is insufficient. A supported execution environment must provide:

- local access to the target Git repository;
- shell and file read/write tools;
- Git, Node.js 22 or newer, and pnpm 10 or newer;
- the subagent/concurrency behavior required by the selected UA release;
- outbound HTTPS for official installation and CoIntent artifact transfer;
- enough session lifetime to complete a full first analysis.

Installation verification has three outcomes: `ready`, `installed_reload_required`, or `incompatible`. CoIntent
never promises that a running Agent host hot-loads newly installed Skills.

## Native behavior policy

CoIntent preserves UA's analysis implementation but supplies invocation policy:

- analysis is explicitly on demand;
- use `--no-auto-update`;
- provide the configured output language to avoid an avoidable prompt;
- surface UA's first-run ignore review and large-repository confirmation in the Agent conversation;
- do not launch a local Dashboard after analysis because CoIntent serves the pinned read-only Dashboard remotely;
- retain UA warnings but never publish a partial candidate.

## Consequences

- The Agent that can see the code is the execution plane; CoIntent server location is irrelevant.
- A remote MCP connection does not imply remote filesystem access. The selected Agent must actually operate where
  the code is available.
- Post-install verification is mandatory because installer exit status does not prove Skill discovery or version
  compatibility.
- Platform support is an explicit tested matrix, not the claim "every Agent that supports Skills".
- The old `bind-checkout`, `COINTENT_UA_AGENT_COMMAND_JSON`, and persistent `refresh-worker` product path is removed.
