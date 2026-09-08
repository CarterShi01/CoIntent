# MVP Review Walkthrough

This walkthrough exercises the product in its intended agent-native shape. The
browser explains the accepted system and exposes pending review work; the agent
is the mutation surface.

## 1. Open the human view

Visit <https://cointent.enjoyapier.cloud>, sign in with the operator-provided
browser credential, and inspect the two synchronized projections:

- the left side is the accepted responsibility book: goals, Role hierarchy,
  responsibilities, and implementation evidence;
- the right side is the Role topology and alignment-review rail;
- selecting a Role in either projection focuses the same canonical object;
- a pending proposal appears in the review rail but cannot be accepted from the
  browser.

## 2. Connect an agent host

CoIntent's production MCP server uses Streamable HTTP and reads its bearer token
from an environment variable. Do not put the token in Git or in Codex config.

```bash
export COINTENT_MCP_TOKEN='<operator-provided token>'
codex mcp add cointent \
  --url https://cointent.enjoyapier.cloud/mcp \
  --bearer-token-env-var COINTENT_MCP_TOKEN
codex mcp get cointent
```

Start a new Codex session after adding the server. The active session's tool
catalog is not hot-reloaded.

## 3. Review without mutating intent

Ask the agent in Chinese:

```text
使用 CoIntent MCP 打开 idea-factory。先阅读 review-role-model Skill，
然后审查当前已接受模型和所有待审提案。区分人的意图、代码证据和你的推断，
不要接受或拒绝任何提案。
```

The agent should navigate the Contexture capability graph, inspect the accepted
version, read the review method, and explain the proposal with evidence.

## 4. Make one explicit decision

After reviewing the browser and the agent's explanation, ask for exactly one
decision:

```text
接受提案 <proposal-id>。在 resolution 中写明我接受的责任边界及原因，
然后比较接受前后的模型版本。
```

Or reject it:

```text
拒绝提案 <proposal-id>。保留代码证据，但说明它为什么不应成为期望设计。
```

Refresh the browser. Acceptance creates a new immutable model version; rejection
removes the item from the pending queue without changing the accepted version.

## 5. Try idea-to-Role convergence

Give the agent a small product-level idea, then ask it to preserve the wording,
apply `converge-design`, and stage—but not accept—a Role Model patch. The new
proposal should appear in the browser review rail. This demonstrates the shared
write boundary: agent writes become visible to the human, while the accepted
model changes only after an explicit decision.
