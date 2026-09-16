# ADR-0006: Private Native UA Runtime and the CoIntent Role Gateway

**Status:** Accepted  
**Date:** 2026-09-17  
**Supersedes in part:** ADR-0002's use of the upstream installer as the CoIntent distribution path

## Context

CoIntent is explicit-only: a request to inspect, explain, review, design, or modify ordinary code must not
start a CoIntent or Understand Anything (UA) flow. The public CoIntent MCP tree already encodes that rule, but
the prior distribution plan invoked UA's generic platform installer. For Codex that installer links every UA
`SKILL.md` into `~/.agents/skills`. The Agent host discovers those Skills before it can enter CoIntent's Role
tree, so broad upstream descriptions such as “understand a codebase” become an unintended second control plane.

The defect is an ordering and ownership problem, not a prompt-wording problem:

```text
old: host discovers global UA Skills -> Agent routes generic code request -> CoIntent rules are bypassed
new: Agent opens explicit CoIntent Role -> refresh lease -> private UA manifest is used only for that lease
```

UA must still execute on the code-local Agent, because only that Agent has the repository, shell, Git, and
subagent facilities. Moving UA into the deployed CoIntent service would violate that boundary. Conversely,
putting UA's implementation inside an MCP Role would fork or copy upstream behavior and make pinned-version
verification meaningless.

## Decision

### 1. One public control plane

The only product-facing Agent surface is CoIntent MCP's Contexture gateway and its Role tree:

```text
cointent
├── project-context
├── distribution
├── understand-current
└── design-future
```

Contexture exposes only its fixed discover/open/read/write gateway tools. Its Role cards and orchestration
Skills are the sole source of product routing instructions. No UA `understand*` capability is registered as a
top-level host Skill or an independent UA MCP server.

### 2. Private code-local UA runtime

`distribution/prepare-ua-installation` provisions the exact pinned upstream checkout below the code-local
Agent's private CoIntent runtime root (by default `$HOME/.cointent/runtime/ua/<revision>`). It does not invoke
UA's platform installer and does not create links under a host Skill directory such as `~/.agents/skills`.

The checkout remains byte-for-byte upstream. Its `SKILL.md` files are private execution manifests, not discovered
conversation capabilities. A valid installation reports:

- its exact private runtime root and resolved `understand` manifest path;
- the pinned UA version and Git revision;
- required local prerequisites; and
- that no UA links remain in the host's global Skill catalog.

The migration retires only symbolic links that resolve into the known legacy or private UA plugin roots. It never
deletes a checkout, a non-link directory, or an unrelated Skill. Re-running the upstream UA installer remains a
user-controlled, reversible way to restore the former generic-UA behavior, but it is incompatible with CoIntent
private-runtime verification.

### 3. Lease-scoped native execution

After explicit activation, `prepare-native-refresh` returns the native UA manifest paths and invocation rules as
part of the already-authorized refresh lease. The Agent reads those private manifests only while carrying that
lease, runs UA against the detached worktree, and transfers opaque artifacts through existing signed URLs.
The server does not execute local commands, receive source or graph bytes in MCP arguments, or persist a general
client command capability.

The manifest paths are an execution hint, not an authorization token. The existing refresh owner check, scoped
MCP permission, clean Git coordinate validation, and artifact digest validation remain the authority boundaries.

## Consequences

### Positive

- Generic code work no longer discovers or auto-selects UA from the host catalog.
- The explicit CoIntent policy is evaluated before UA becomes available to the conversation.
- CoIntent retains the native UA execution model and exact upstream pin.
- The service can verify isolation as an installation property instead of assuming that a visible Skill is safe.

### Costs and limits

- A platform that has no way to execute a private manifest on an explicit instruction cannot use this flow until a
  scoped local executor or isolated refresh Agent profile is supplied.
- Existing global UA installs require a one-time link-retirement step and Agent-host reload.
- The remote service cannot independently attest to a code-local catalog; it verifies measured evidence from the
  same Agent that already performs native UA execution.

## Execution plan and release gates

1. Replace the global-installer plan with private-checkout and safe link-retirement commands.
2. Extend installation evidence and verification to require catalog isolation.
3. Add lease-scoped private-manifest metadata to native refresh plans.
4. Update the product flow, README, ADR-0002, and native-Agent runbook.
5. Add unit/contract tests for no global installer command, isolation rejection, private manifest paths, and the
   unchanged compact MCP tree.
6. Run backend tests and frontend build, commit/rebase/push, and publish via `deploy/release-beijing.sh`.
7. Test with a freshly reloaded normal coding Agent: no `understand*` Skill appears for generic code work; then
   explicitly request CoIntent understanding and confirm the private runtime/lease path completes a refresh.

## Acceptance criteria

- `prepare-ua-installation(codex, linux)` contains no platform-installer call or Skill-link creation; its only
  catalog mutation is retiring known UA symbolic links.
- `verify-ua-installation` fails closed when any UA global catalog link is reported.
- A successful `prepare-native-refresh` identifies only private UA manifests and says they may be read only under
  the active refresh lease.
- Public MCP remains the compact Contexture Role tree; no UA-native tool, Role, or host Skill is added to it.
- Deployment smoke tests pass, and the deployed service reports healthy before this ADR is handed to a user for
  host-reload and end-to-end testing.
