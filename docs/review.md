# CoIntent 0.3 Review Walkthrough

The browser is the human review surface; MCP is the Agent inspection and authoring surface.

## 1. Open the shared model

Visit <https://cointent.enjoyapier.cloud> and sign in with the operator-provided username and password.

Confirm the top bar shows:

- Project: **Idea Factory**;
- Design: the latest accepted immutable version;
- Code: the current observed Git revision;
- Alignment: **Current** or an explicit review-needed state.

Design and code coordinates are independent. A scan never creates a design version, and accepting a design never claims the code already implements it.

## 2. Follow the primary product path

1. In **Specification**, choose **Screen and compare startup ideas**.
2. The center opens **Screen startup ideas**, the Responsibility that realizes it.
3. Read its description and its four-node Workflow: understand signals → develop candidates → evaluate candidates → learn from outcomes.
4. Notice the returning edge from learning to development. This is a real feedback loop, not an invalid tree edge.
5. Choose **Evaluate idea candidates** to descend one level.
6. Read the conditional rejection and survivor branches, then enter a child such as **Apply hard gates**.
7. Use the breadcrumb to return to any earlier Responsibility.

At every level, the graph contains only the focused object's immediate delegated Responsibilities. This prevents code-scale graph noise.

## 3. Inspect the object contract and evidence

For each focused Responsibility, use the right side to inspect:

- **Data members** — meaningful state or knowledge encapsulated by the object;
- **Inputs** — semantic information entering the boundary;
- **Outputs** — results, effects, decisions, or events leaving it;
- **Backend evidence** — code paths and optional symbols that implement or support it;
- **Alignment review** — findings, pending proposals, and related change sets.

Enter an atomic Responsibility and confirm the center explicitly identifies it as a leaf. It is still a complete Responsibility object; it simply has no further product-relevant Workflow at this modeling depth.

## 4. Verify the implementation filter

Scan the evidence shown for several leaves. Paths should refer to Idea Factory backend logic. Frontend/Studio files, styles, logging, tracing, metrics, framework wiring, and deployment files must not appear as Responsibility nodes or implementation mappings.

## 5. Connect an Agent

Keep the bearer token out of Git and pass it through an environment variable:

```bash
export COINTENT_MCP_TOKEN='<operator-provided token>'
codex mcp add cointent \
  --url https://cointent.enjoyapier.cloud/mcp \
  --bearer-token-env-var COINTENT_MCP_TOKEN
codex mcp get cointent
```

Start a fresh Codex session so the capability catalog is loaded, then ask:

```text
Use CoIntent project idea-factory. Follow the model-responsibilities Skill.
List the root Responsibilities, inspect Screen startup ideas, trace its Workflow,
then enter Evaluate idea candidates and explain its contract and backend evidence.
Do not mutate accepted state.
```

The Agent should read the same version and recursive model shown in the browser, including a bounded path that reports the feedback loop.

## 6. Exercise the reviewed write boundary

For a small product-logic change, ask the Agent to:

1. preserve the original wording with `record-intent`;
2. start a ChangeSet naming affected Specification and Responsibility IDs;
3. follow `model-responsibilities` and `review-responsibility-model`;
4. stage a typed patch against the exact current design version;
5. stop before acceptance.

The accepted browser model must remain unchanged while the proposal is pending. Explicit acceptance creates a new immutable DesignVersion. After implementation, a new backend snapshot exposes mapped changes or gaps for review before the ChangeSet is closed.
