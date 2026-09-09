import { useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { fetchObservation, fetchSession, listProjects, loadWorkspace, login, logout } from "./api";
import type {
  AlignmentBaseline, ChangeSet, DesignVersion, Finding, ImplementationLink, ModelResponse,
  ObservationCoordinate, OverviewResponse, Project, Proposal, Responsibility, SpecificationItem,
  SpecificationResponsibilityLink, Workflow,
} from "./types";

type Workspace = {
  model: ModelResponse;
  overview: OverviewResponse;
  versions: DesignVersion[];
  baseline: AlignmentBaseline;
  findings: Finding[];
  proposals: Proposal[];
  changeSets: ChangeSet[];
};
type Auth = { state: "checking" } | { state: "out" } | { state: "in"; user: string | null };
type ProcessMode = "understand" | "design";

export default function App() {
  const [auth, setAuth] = useState<Auth>({ state: "checking" });
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [designVersion, setDesignVersion] = useState<number | undefined>();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [observation, setObservation] = useState<ObservationCoordinate | undefined>();
  const [mode, setMode] = useState<ProcessMode>(() => location.pathname.endsWith("/design") ? "design" : "understand");
  const [selectedObserved, setSelectedObserved] = useState("");
  const [mobilePane, setMobilePane] = useState<"functions" | "structure" | "details">("functions");
  const [path, setPath] = useState<string[]>([]);
  const [forwardIds, setForwardIds] = useState<string[]>([]);
  const [selectedSpec, setSelectedSpec] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    fetchSession()
      .then((session) => setAuth(session.authed ? { state: "in", user: session.user } : { state: "out" }))
      .catch((reason: unknown) => setError(errorText(reason)));
  }, []);

  useEffect(() => {
    const syncPath = () => setMode(location.pathname.endsWith("/design") ? "design" : "understand");
    addEventListener("popstate", syncPath);
    return () => removeEventListener("popstate", syncPath);
  }, []);

  useEffect(() => {
    if (auth.state !== "in") return;
    listProjects().then((items) => {
      setProjects(items);
      setProjectId((current) => current || items[0]?.id || "");
    }).catch(handleFailure);
  }, [auth.state]);

  useEffect(() => {
    if (auth.state !== "in" || !projectId) return;
    setWorkspace(null);
    setObservation(undefined);
    Promise.all([loadWorkspace(projectId, designVersion), fetchObservation(projectId)]).then(([next, observed]) => {
      setWorkspace(next);
      setObservation(observed);
      setSelectedObserved(observed.observed_revision?.capabilities[0]?.responsibility_id
        ?? observed.observed_revision?.responsibilities[0]?.id ?? "");
      const model = next.model.model;
      const root = rootResponsibilities(model.responsibilities)[0] ?? model.responsibilities[0];
      setPath(root ? [root.id] : []);
      setForwardIds([]);
      setSelectedSpec(model.specification_items[0]?.id ?? "");
    }).catch(handleFailure);
  }, [auth.state, projectId, designVersion]);

  function handleFailure(reason: unknown) {
    const message = errorText(reason);
    if (message.startsWith("401 ")) setAuth({ state: "out" });
    else setError(message);
  }

  function chooseMode(next: ProcessMode) {
    if (next === mode) return;
    history.pushState({}, "", next === "design" ? "/design" : "/understand");
    setMode(next);
    setMobilePane("functions");
  }

  if (error) return <Failure message={error} />;
  if (auth.state === "checking") return <Loading label="Checking access…" />;
  if (auth.state === "out") return <LoginScreen onDone={(user) => setAuth({ state: "in", user })} />;
  if (!projectId || !workspace || observation === undefined) return <Loading label="Opening the workspace…" />;

  const response = workspace.model;
  const model = response.model;
  const responsibilityById = new Map(model.responsibilities.map((item) => [item.id, item]));
  const roots = rootResponsibilities(model.responsibilities);
  const current = responsibilityById.get(path[path.length - 1]) ?? roots[0] ?? model.responsibilities[0];
  const currentPath = path.map((id) => responsibilityById.get(id)).filter(Boolean) as Responsibility[];
  const evidence = model.implementation_links.filter((item) => item.responsibility_id === current?.id);
  const relatedFindings = workspace.findings.filter((item) => item.responsibility_ids?.includes(current?.id ?? ""));

  function enterResponsibility(id: string) {
    if (!responsibilityById.has(id)) return;
    setForwardIds([]);
    setPath((currentPathIds) => {
      const repeatedAt = currentPathIds.lastIndexOf(id);
      return repeatedAt >= 0 ? currentPathIds.slice(0, repeatedAt + 1) : [...currentPathIds, id];
    });
  }

  function chooseSpecification(id: string) {
    setSelectedSpec(id);
    setMobilePane("structure");
    const links = model.specification_responsibility_links.filter((item) => item.specification_id === id);
    const linked = links.find((item) => item.kind === "realizes") ?? links[0];
    if (linked) {
      setPath([linked.responsibility_id]);
      setForwardIds([]);
    }
  }

  function exitLevel() {
    if (path.length <= 1) return;
    setForwardIds([path[path.length - 1], ...forwardIds]);
    setPath(path.slice(0, -1));
  }

  function goForward() {
    const next = forwardIds[0];
    if (!next) return;
    setPath([...path, next]);
    setForwardIds(forwardIds.slice(1));
  }

  function exitToRoot() {
    if (path.length <= 1) return;
    setForwardIds(path.slice(1));
    setPath(path.slice(0, 1));
  }

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><IntentMark /><div><strong>CoIntent</strong><span>Program logic, made legible</span></div></div>
      <label className="project-picker"><span>Project</span><select value={projectId} onChange={(event) => { setDesignVersion(undefined); setProjectId(event.target.value); }}>
        {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select></label>
      {mode === "understand" ? <div className="model-coordinate observation-coordinate">
        <div><span>Code</span><strong>{observation.code_snapshot?.revision.slice(0, 8) ?? "No full snapshot"}</strong></div>
        <i aria-hidden="true">→</i>
        <div><span>Understand Anything</span><strong>{observation.ua_snapshot ? `graph ${observation.ua_snapshot.ua_graph_version}` : "Not imported"}</strong></div>
        <div className={observation.status === "current" ? "aligned" : "drifted"}><span>Current structure</span><strong>{observation.status === "current" ? "Read only · current" : observation.status === "stale" ? "Read only · stale" : "Not generated"}</strong></div>
      </div> : <div className="model-coordinate design-coordinate">
        <label><span>Target design</span><select value={response.version} onChange={(event) => setDesignVersion(Number(event.target.value))}>
          {workspace.versions.map((version) => <option key={version.version} value={version.version}>v{version.version} · {version.message}</option>)}
        </select></label>
        <i aria-hidden="true">←</i>
        <div><span>Baseline code</span><strong>{workspace.baseline.code_snapshot?.snapshot.revision.slice(0, 8) ?? "Not selected"}</strong></div>
        <div className="design-state"><span>Authority</span><strong>Human-owned target</strong></div>
      </div>}
      <button className="account" onClick={() => void logout().finally(() => { setWorkspace(null); setObservation(undefined); setAuth({ state: "out" }); })}>
        <span>{auth.user ?? "user"}</span><small>Sign out</small>
      </button>
    </header>

    <nav className="process-tabs" aria-label="System process">
      <button className={mode === "understand" ? "active understand" : ""} aria-current={mode === "understand" ? "page" : undefined} onClick={() => chooseMode("understand")}>
        <span>Code → current model</span><strong>Understand current</strong><small>Read only</small>
      </button>
      <button className={mode === "design" ? "active design" : ""} aria-current={mode === "design" ? "page" : undefined} onClick={() => chooseMode("design")}>
        <span>Intent → implementation diff</span><strong>Design future</strong><small>Editable target</small>
      </button>
    </nav>
    <nav className={`mobile-pane-tabs ${mode}`} aria-label="Workspace area">
      <button className={mobilePane === "functions" ? "active" : ""} onClick={() => setMobilePane("functions")}>{mode === "understand" ? "Functions" : "Expected"}</button>
      <button className={mobilePane === "structure" ? "active" : ""} onClick={() => setMobilePane("structure")}>Structure</button>
      <button className={mobilePane === "details" ? "active" : ""} onClick={() => setMobilePane("details")}>{mode === "understand" ? "Evidence" : "Details"}</button>
    </nav>

    {mode === "understand" ? <UnderstandingWorkspace coordinate={observation} selectedId={selectedObserved} onSelect={(id) => { setSelectedObserved(id); setMobilePane("structure"); }} mobilePane={mobilePane} /> : <main className="workspace design-workspace" data-mobile-pane={mobilePane}>
      <SpecificationPanel
        items={model.specification_items}
        links={model.specification_responsibility_links}
        selected={selectedSpec}
        onSelect={chooseSpecification}
        summary={model.summary}
      />

      <section className="logic-pane">
        <div className="logic-head">
          <nav className="breadcrumbs" aria-label="Responsibility path">
            {currentPath.map((item, index) => <span key={`${item.id}-${index}`}>
              {index > 0 && <i>›</i>}
              <button onClick={() => { setForwardIds(path.slice(index + 1)); setPath(path.slice(0, index + 1)); }}>{item.name}</button>
            </span>)}
          </nav>
          <div className="logic-title">
            <div><span className="eyebrow">Target responsibility</span><h1>{current?.name ?? "No responsibility"}</h1></div>
            <div className="workflow-navigation" aria-label="Workflow navigation">
              <span>Workflow navigation</span>
              <button disabled={path.length <= 1} onClick={exitLevel}><b>←</b> Exit level</button>
              <button disabled={!forwardIds.length} onClick={goForward}>Forward <b>→</b></button>
              <button disabled={path.length <= 1} onClick={exitToRoot}><b>⌂</b> Root</button>
            </div>
          </div>
          <p className="responsibility-description">{current?.description}</p>
          <div className="scope-note"><span>Inside this object</span><strong>{current?.workflow?.nodes.length ?? 0} delegated responsibilities</strong><small>Choose a node to descend one semantic level.</small></div>
        </div>
        {current?.workflow
          ? <WorkflowCanvas workflow={current.workflow} responsibilities={responsibilityById} activePathIds={new Set(path)} onEnter={enterResponsibility} />
          : <LeafResponsibility responsibility={current} evidence={evidence} />}
      </section>

      <Inspector
        responsibility={current}
        evidence={evidence}
        findings={relatedFindings}
        proposals={workspace.proposals}
        changeSets={workspace.changeSets}
        baseline={workspace.baseline}
      />
    </main>}
  </div>;
}

function UnderstandingWorkspace({ coordinate, selectedId, onSelect, mobilePane }: {
  coordinate: ObservationCoordinate;
  selectedId: string;
  onSelect: (id: string) => void;
  mobilePane: "functions" | "structure" | "details";
}) {
  const revision = coordinate.observed_revision;
  if (!revision) return <main className="observation-empty">
    <section>
      <span className="empty-kicker">No verified current model</span>
      <h1>Generate the view from code.</h1>
      <p>Capture a full repository snapshot, run Understand Anything, then import its knowledge and domain graph through the operator pipeline. A design draft is never shown here as current code.</p>
      <code>cointent scan &lt;repo&gt; --project-id {coordinate.project_id} --scope full</code>
      <code>cointent import-understand-anything --project-id {coordinate.project_id} …</code>
    </section>
  </main>;

  const byId = new Map(revision.responsibilities.map((item) => [item.id, item]));
  const selected = byId.get(selectedId) ?? revision.responsibilities[0];
  const parentById = new Map<string, string>();
  revision.responsibilities.forEach((parent) => parent.workflow?.nodes.forEach((node) => parentById.set(node.responsibility_id, parent.id)));
  const children = (selected?.workflow?.nodes ?? []).map((node) => byId.get(node.responsibility_id)).filter(Boolean) as Responsibility[];
  const evidenceBySubject = new Map(revision.bindings.map((item) => [item.subject_id, item.evidence]));
  const selectedEvidence = selected ? evidenceBySubject.get(selected.id) ?? [] : [];
  const lineage: Responsibility[] = [];
  let cursor: Responsibility | undefined = selected;
  while (cursor) {
    lineage.unshift(cursor);
    const parentId = parentById.get(cursor.id);
    cursor = parentId ? byId.get(parentId) : undefined;
  }

  return <main className="workspace observed-workspace" data-mobile-pane={mobilePane}>
    <aside className="spec-pane capability-pane">
      <div className="pane-heading"><span className="eyebrow">What the code does</span><h2>System functions</h2><p>Generated from source evidence through Understand Anything. Select a function to inspect its implemented flow.</p></div>
      <div className="spec-columns"><span>Observed function</span><span>Proof</span></div>
      <div className="spec-tree">{revision.capabilities.map((item) => <button key={item.id} className={`spec-row ${selected?.id === item.responsibility_id ? "selected" : ""}`} onClick={() => onSelect(item.responsibility_id)}>
        <span className="tree-mark">◆</span><span><strong>{item.name}</strong><small>{item.description}</small></span><em title={`${item.evidence_count} source bindings`}>{item.evidence_count}</em>
      </button>)}</div>
      <div className="observation-proof"><span>Immutable coordinate</span><code>{revision.id}</code><small>{revision.responsibilities.length} verified responsibilities · {revision.diagnostics.length} diagnostics</small></div>
    </aside>

    <section className="logic-pane observed-logic">
      <div className="logic-head">
        <nav className="breadcrumbs" aria-label="Observed structure path">{lineage.map((item, index) => <span key={item.id}>{index > 0 && <i>›</i>}<button onClick={() => onSelect(item.id)}>{item.name}</button></span>)}</nav>
        <div className="logic-title"><div><span className="eyebrow">Implemented responsibility</span><h1>{selected?.name ?? "No verified structure"}</h1></div><span className="read-only-seal">Read only<br /><b>Code-derived</b></span></div>
        <p className="responsibility-description">{selected?.description}</p>
        <div className="scope-note"><span>Inside this node</span><strong>{children.length} verified child nodes</strong><small>Every visible node resolves to captured source.</small></div>
      </div>
      <div className="observed-flow">
        <div className="workflow-toolbar"><div><span className="eyebrow">Current structure</span><strong>{children.length ? "Select a node to inspect or descend" : "Evidence-backed leaf"}</strong></div><div className="legend"><span><i className="line normal" />UA order</span></div></div>
        {children.length ? <div className="observed-node-row">{children.map((node, index) => <div className="observed-node-wrap" key={node.id}>
          {index > 0 && <span className="observed-connector" aria-hidden="true">→</span>}
          <button className="observed-node-card" onClick={() => onSelect(node.id)}><span>{node.source_ids[0]?.split(":", 1)[0] ?? "responsibility"}</span><strong>{node.name}</strong><p>{node.description}</p><small>{evidenceBySubject.get(node.id)?.length ?? 0} source binding{(evidenceBySubject.get(node.id)?.length ?? 0) === 1 ? "" : "s"} <b>→</b></small></button>
        </div>)}</div> : <div className="leaf-stage"><div className="leaf-symbol"><span /><i /><b /></div><span className="eyebrow">Verified leaf</span><h2>{selected?.name}</h2><p>This is the deepest imported semantic level. Use its source bindings to inspect the implementation.</p></div>}
      </div>
    </section>

    <aside className="inspector observed-inspector">
      <div className="inspector-heading"><span className="eyebrow">Why this is shown</span><h2>Source evidence</h2><code>{selected?.source_ids[0]}</code></div>
      <section className="evidence-block"><div className="section-title"><div><span className="eyebrow">Captured code</span><h3>Bindings</h3></div><strong>{selectedEvidence.length}</strong></div>
        {selectedEvidence.map((item) => <article className="evidence-row" key={`${item.ua_node_id}-${item.path}-${item.start_line}`}><span>{item.origin === "ua_semantic" ? "Semantic + structural proof" : "UA structural"}</span><code>{item.path}{item.start_line ? `:${item.start_line}${item.end_line && item.end_line !== item.start_line ? `–${item.end_line}` : ""}` : ""}</code><p>Anchored by {item.structural_ua_node_ids.length} structural node{item.structural_ua_node_ids.length === 1 ? "" : "s"} · digest {item.source_digest.slice(0, 12)}</p></article>)}
      </section>
      <section className="coordinate-card"><span>Provenance</span><dl><div><dt>Code</dt><dd>{coordinate.code_snapshot?.revision.slice(0, 12)}</dd></div><div><dt>UA graph</dt><dd>{coordinate.ua_snapshot?.ua_graph_version}</dd></div><div><dt>UA pin</dt><dd>{coordinate.ua_snapshot?.ua_tool_revision}</dd></div><div><dt>Status</dt><dd>{coordinate.status}</dd></div></dl></section>
    </aside>
  </main>;
}

function SpecificationPanel({ items, links, selected, onSelect, summary }: {
  items: SpecificationItem[];
  links: SpecificationResponsibilityLink[];
  selected: string;
  onSelect: (id: string) => void;
  summary: string;
}) {
  const children = useMemo(() => hierarchy(items), [items]);
  const render = (parentId: string | null, depth = 0): ReactNode => (children.get(parentId) ?? []).map((item) => {
    const mapped = links.filter((link) => link.specification_id === item.id).length;
    const hasChildren = (children.get(item.id)?.length ?? 0) > 0;
    return <div className="spec-branch" key={item.id}>
      <button className={`spec-row ${selected === item.id ? "selected" : ""}`} style={{ "--depth": depth } as CSSProperties} onClick={() => onSelect(item.id)}>
        <span className="tree-mark">{hasChildren ? "◇" : "·"}</span>
        <span><strong>{item.name}</strong><small>{item.description}</small></span>
        <em title={`${mapped} responsibility mappings`}>{mapped}</em>
      </button>
      {render(item.id, depth + 1)}
    </div>;
  });
  return <aside className="spec-pane">
    <div className="pane-heading"><span className="eyebrow">Meaning / product view</span><h2>Specification</h2><p>{summary}</p></div>
    <div className="spec-columns"><span>Plain-language capability</span><span>Map</span></div>
    <div className="spec-tree">{render(null)}</div>
    <div className="progression">
      <span>Three levels of truth</span>
      <ol><li className="active">Specification</li><li>Responsibility model</li><li>Code evidence</li></ol>
    </div>
  </aside>;
}

type PositionedNode = { id: string; responsibility_id: string; note: string; x: number; y: number; depth: number };

function WorkflowCanvas({ workflow, responsibilities, activePathIds, onEnter }: {
  workflow: Workflow;
  responsibilities: Map<string, Responsibility>;
  activePathIds: Set<string>;
  onEnter: (id: string) => void;
}) {
  const layout = useMemo(() => layoutWorkflow(workflow), [workflow]);
  const nodeById = new Map(layout.nodes.map((node) => [node.id, node]));
  return <div className="workflow-region">
    <div className="workflow-toolbar">
      <div><span className="eyebrow">Responsibility workflow</span><strong>How this object delegates its work</strong></div>
      <div className="legend"><span><i className="line normal" />forward</span><span><i className="line loop" />loop / return</span></div>
    </div>
    <div className="workflow-scroll">
      <div className="workflow-canvas" style={{ width: layout.width, height: layout.height }}>
        <svg width={layout.width} height={layout.height} aria-hidden="true">
          <defs><marker id="flow-arrow" markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto"><path d="M0,0 L0,8 L8,4 z" /></marker></defs>
          {workflow.edges.map((edge, index) => {
            const source = nodeById.get(edge.source_node_id);
            const target = nodeById.get(edge.target_node_id);
            if (!source || !target) return null;
            const loop = target.depth <= source.depth;
            const startX = source.x + 226;
            const startY = source.y + 55;
            const endX = target.x;
            const endY = target.y + 55;
            const bend = loop ? 54 + index * 7 : Math.max(42, (endX - startX) / 2);
            const path = loop
              ? `M${startX},${startY} C${startX + bend},${Math.max(16, startY - 118)} ${endX - bend},${Math.max(16, endY - 118)} ${endX},${endY}`
              : `M${startX},${startY} C${startX + bend},${startY} ${endX - bend},${endY} ${endX},${endY}`;
            return <g key={edge.id} className={loop ? "flow-edge loop-edge" : `flow-edge ${edge.kind}`}>
              <path d={path} markerEnd="url(#flow-arrow)" />
              {edge.label && <text x={(startX + endX) / 2} y={loop ? Math.max(25, Math.min(startY, endY) - 75 - index * 3) : (startY + endY) / 2 - 9}>{edge.label}</text>}
            </g>;
          })}
        </svg>
        {layout.nodes.map((node) => {
          const item = responsibilities.get(node.responsibility_id);
          const entry = workflow.entry_node_ids.includes(node.id);
          const canDescend = Boolean(item?.workflow);
          const recursive = activePathIds.has(node.responsibility_id);
          const content = <>
            <span className="node-meta">{entry ? "ENTRY · " : ""}{recursive ? "RETURN" : canDescend ? "COMPOSITE" : "LEAF"}</span>
            <strong>{item?.name ?? node.responsibility_id}</strong>
            <p>{item?.description ?? node.note}</p>
            <span className="enter-cue">{recursive ? "Return to this level" : canDescend ? "Open workflow" : "Leaf responsibility"}<b>{canDescend || recursive ? "→" : "◆"}</b></span>
          </>;
          return canDescend || recursive
            ? <button key={node.id} className="workflow-node" style={{ left: node.x, top: node.y }} onClick={() => onEnter(node.responsibility_id)}>{content}</button>
            : <article key={node.id} className="workflow-node leaf-node" style={{ left: node.x, top: node.y }} aria-label={`${item?.name ?? node.responsibility_id}, leaf responsibility`}>{content}</article>;
        })}
      </div>
    </div>
  </div>;
}

function LeafResponsibility({ responsibility, evidence }: { responsibility?: Responsibility; evidence: ImplementationLink[] }) {
  return <div className="leaf-stage">
    <div className="leaf-symbol"><span /><i /><b /></div>
    <span className="eyebrow">Atomic responsibility</span>
    <h2>{responsibility?.name}</h2>
    <p>This responsibility has no delegated workflow at the current modeling depth. Its contract and implementation evidence are still explicit.</p>
    <div><strong>{evidence.length}</strong><span>mapped backend artifacts</span></div>
  </div>;
}

function Inspector({ responsibility, evidence, findings, proposals, changeSets, baseline }: {
  responsibility?: Responsibility;
  evidence: ImplementationLink[];
  findings: Finding[];
  proposals: Proposal[];
  changeSets: ChangeSet[];
  baseline: AlignmentBaseline;
}) {
  const relatedChanges = changeSets.filter((item) => item.responsibility_ids?.includes(responsibility?.id ?? ""));
  return <aside className="inspector">
    <div className="inspector-heading"><span className="eyebrow">Object contract</span><h2>{responsibility?.name}</h2><code>{responsibility?.id}</code></div>
    <section className="contract-block data-block"><h3>Data members</h3><ValueList values={responsibility?.data_members ?? []} empty="No persistent domain state declared." /></section>
    <div className="io-grid">
      <section className="contract-block"><h3>Inputs</h3><ValueList values={responsibility?.inputs ?? []} empty="No inputs declared." /></section>
      <section className="contract-block"><h3>Outputs</h3><ValueList values={responsibility?.outputs ?? []} empty="No outputs declared." /></section>
    </div>
    <section className="evidence-block">
      <div className="section-title"><div><span className="eyebrow">Implementation mapping</span><h3>Backend evidence</h3></div><strong>{evidence.length}</strong></div>
      {evidence.length ? evidence.map((item) => <article className="evidence-row" key={item.id}>
        <span>{item.kind}</span><code>{item.artifact_path}{item.symbol ? ` · ${item.symbol}` : ""}</code><p>{item.evidence}</p>
      </article>) : <p className="empty">No backend code evidence mapped at this level.</p>}
    </section>
    <section className="review-block">
      <div className="section-title"><div><span className="eyebrow">Human ↔ Agent</span><h3>Alignment review</h3></div><span className={`alignment-pill ${baseline.is_current ? "current" : "stale"}`}>{baseline.is_current ? "Current" : "Stale"}</span></div>
      <div className="review-numbers">
        <div><strong>{findings.length}</strong><span>findings here</span></div>
        <div><strong>{proposals.filter((item) => item.status === "pending").length}</strong><span>proposals</span></div>
        <div><strong>{relatedChanges.length}</strong><span>change sets</span></div>
      </div>
      {findings.slice(0, 3).map((item) => <article className="finding" key={item.id}><span>{item.severity} · {item.kind}</span><p>{item.summary}</p></article>)}
    </section>
  </aside>;
}

function ValueList({ values, empty }: { values: string[]; empty: string }) {
  if (!values.length) return <p className="empty">{empty}</p>;
  return <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul>;
}

function LoginScreen({ onDone }: { onDone: (user: string | null) => void }) {
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const result = await login(user, password); onDone(result.user); }
    catch (reason) { setError(errorText(reason)); setBusy(false); }
  }
  return <main className="login-screen">
    <section className="login-story"><div className="login-brand"><IntentMark /><strong>CoIntent</strong></div><div className="orbit" aria-hidden="true"><i /><i /><i /><i /></div><span className="eyebrow">Shared semantic ground</span><h1>See what the program actually does.</h1><p>Explore backend logic as recursive responsibilities and workflows—then keep that human-readable model aligned with the code.</p></section>
    <section className="login-gate"><form onSubmit={(event) => void submit(event)}><span className="eyebrow">Private workspace</span><h2>Sign in</h2><p>Use the credentials assigned to this deployment.</p>
      <label>Username<input autoComplete="username" autoFocus value={user} onChange={(event) => setUser(event.target.value)} /></label>
      <label>Password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      {error && <div className="login-error" role="alert">{error}</div>}
      <button disabled={busy || !user || !password}>{busy ? "Checking…" : "Enter workspace"}<span>→</span></button>
      <small>Session cookies are HTTP-only and SameSite strict.</small>
    </form></section>
  </main>;
}

function IntentMark() {
  return <svg className="intent-mark" viewBox="0 0 42 42" aria-hidden="true"><path d="M6 8h10l9 13 11 13M6 34h10l9-13L36 8" /><circle cx="6" cy="8" r="3" /><circle cx="6" cy="34" r="3" /><circle cx="25" cy="21" r="3.5" /><circle cx="36" cy="8" r="3" /><circle cx="36" cy="34" r="3" /></svg>;
}

function Loading({ label }: { label: string }) { return <div className="state-screen"><IntentMark /><h1>CoIntent</h1><p>{label}</p></div>; }
function Failure({ message }: { message: string }) { return <div className="state-screen"><IntentMark /><h1>Could not open CoIntent</h1><p>{message}</p><button onClick={() => location.reload()}>Reload</button></div>; }
function errorText(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }

function hierarchy(items: SpecificationItem[]) {
  const result = new Map<string | null, SpecificationItem[]>();
  items.forEach((item) => result.set(item.parent_id, [...(result.get(item.parent_id) ?? []), item]));
  return result;
}

function rootResponsibilities(items: Responsibility[]) {
  const referenced = new Set(items.flatMap((item) => item.workflow?.nodes.map((node) => node.responsibility_id) ?? []));
  return items.filter((item) => !referenced.has(item.id));
}

function layoutWorkflow(workflow: Workflow) {
  const depths = new Map<string, number>();
  const queue = workflow.entry_node_ids.map((id) => ({ id, depth: 0 }));
  let steps = 0;
  while (queue.length && steps < workflow.nodes.length * 8) {
    steps += 1;
    const next = queue.shift()!;
    if (depths.has(next.id)) continue;
    depths.set(next.id, next.depth);
    workflow.edges.filter((edge) => edge.source_node_id === next.id && !depths.has(edge.target_node_id))
      .forEach((edge) => queue.push({ id: edge.target_node_id, depth: next.depth + 1 }));
  }
  const maxDepth = Math.max(0, ...depths.values());
  workflow.nodes.forEach((node) => { if (!depths.has(node.id)) depths.set(node.id, maxDepth + 1); });
  const groups = new Map<number, typeof workflow.nodes>();
  workflow.nodes.forEach((node) => { const depth = depths.get(node.id) ?? 0; groups.set(depth, [...(groups.get(depth) ?? []), node]); });
  const nodes: PositionedNode[] = [];
  [...groups.entries()].sort(([a], [b]) => a - b).forEach(([depth, members]) => {
    members.forEach((node, index) => nodes.push({ ...node, depth, x: 44 + depth * 294, y: 70 + index * 156 }));
  });
  return {
    nodes,
    width: Math.max(760, ...nodes.map((node) => node.x + 270)),
    height: Math.max(410, ...nodes.map((node) => node.y + 150)),
  };
}
