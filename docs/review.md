# MVP 0.2 Review Walkthrough

This path exercises CoIntent in its intended Agent-native shape. The browser is the human review surface; MCP is the design authoring surface.

## 1. Open the shared design

Visit <https://cointent.enjoyapier.cloud> and sign in with the operator-provided browser username and password.

In the top coordinate strip, confirm:

- **Project** is `Idea Factory`;
- **Design** is the latest accepted version;
- **Code** shows the current observed Git revision;
- **Mapping** identifies the design/snapshot mapping revision;
- **Review** counts pending proposals plus open alignment findings.

These values are intentionally independent. A code scan does not create a DesignVersion and a design acceptance does not pretend that code has already changed.

## 2. Walk from product function to implementation

1. In **Function catalog**, select **Run persona-pressure evaluation**.
2. Observe two highlighted RoleObjects: **Semantic Evaluation** owns the function and **Shared Domain Contract** governs it.
3. Select **Semantic Evaluation**.
4. In **Contract**, review its two responsibilities, three inputs, output, constraint, and collaborators.
5. In **Functions**, verify the typed ProductFunction links.
6. In **Implementation**, inspect `src/idea_eval/persona_pressure.py`, its mapping kind, origin, confidence, and evidence.
7. In **Review**, inspect any findings, proposals, or ChangeSets that touch the RoleObject.

This is the essential system view: a product promise, its accountable responsibility objects, and its observed implementation are connected without being collapsed into one model.

## 3. Walk in the reverse direction

Select another RoleObject in the map. ProductFunctions supported by that RoleObject receive a cyan highlight in the left catalog. Use the RoleObject's **Implementation** tab to move from a responsibility boundary to its code evidence.

Switch the **Design** selector to an earlier version. The workspace shows that historical accepted design while the top bar keeps the latest CodeSnapshot visible. Return to the latest version before authoring changes.

## 4. Connect an Agent host

CoIntent's production MCP server uses Streamable HTTP and reads its bearer token from an environment variable. Never put the token in Git or directly in Codex configuration.

```bash
export COINTENT_MCP_TOKEN='<operator-provided token>'
codex mcp add cointent \
  --url https://cointent.enjoyapier.cloud/mcp \
  --bearer-token-env-var COINTENT_MCP_TOKEN
codex mcp get cointent
```

Start a new Codex session after adding the server; an active tool catalog is not hot-reloaded.

Ask the Agent:

```text
Open CoIntent project idea-factory. Read the review-design Skill, inspect the
current accepted design and alignment baseline, then explain one ProductFunction
through its RoleObject contract and implementation evidence. Do not mutate state.
```

The Agent should progressively open `cointent`, choose the appropriate Role and Skill, and read the same accepted state shown in the browser.

## 5. Exercise the shared write boundary

Give the Agent one small product-level change and ask it to:

1. record your exact wording with `record-intent`;
2. start a ChangeSet with affected ProductFunction and RoleObject IDs;
3. follow `refine-product-functions` and `decompose-responsibilities`;
4. stage a typed, version-bound design proposal;
5. stop before acceptance.

Refresh the browser and open the selected RoleObject's **Review** tab. The proposal and ChangeSet should be visible while the accepted DesignVersion remains unchanged.

After reviewing, explicitly accept or reject the proposal through the Agent. Acceptance creates an immutable new DesignVersion. If accepted, attach that version to the ChangeSet, generate the implementation brief, implement, ingest a new CodeSnapshot, review findings, and close the ChangeSet only with an explicit conclusion.
