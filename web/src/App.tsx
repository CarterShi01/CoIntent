import { useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { fetchSession, listProjects, loadWorkspace, login, logout } from "./api";
import type {
  AlignmentBaseline, ChangeSet, DesignVersion, Finding, FunctionRoleLink, ModelResponse,
  OverviewResponse, ProductFunction, Project, Proposal, Responsibility, RoleObject, RoleRelation, TraceLink,
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
type InspectorTab = "contract" | "functions" | "implementation" | "review";

function App() {
  const [auth, setAuth] = useState<Auth>({ state: "checking" });
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [designVersion, setDesignVersion] = useState<number | undefined>();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selectedFunction, setSelectedFunction] = useState("");
  const [selectedRole, setSelectedRole] = useState("");
  const [tab, setTab] = useState<InspectorTab>("contract");
  const [error, setError] = useState("");
  const [mobileView, setMobileView] = useState<"functions" | "roles">("functions");

  useEffect(() => {
    fetchSession()
      .then((session) => setAuth(session.authed ? { state: "in", user: session.user } : { state: "out" }))
      .catch((reason: unknown) => setError(errorText(reason)));
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
    loadWorkspace(projectId, designVersion).then((next) => {
      setWorkspace(next);
      const model = next.model.model;
      setSelectedFunction((current) => model.product_functions.some((item) => item.id === current)
        ? current : firstLeaf(model.product_functions)?.id ?? model.product_functions[0]?.id ?? "");
      setSelectedRole((current) => model.role_objects.some((item) => item.id === current)
        ? current : model.role_objects.find((item) => item.parent_id)?.id ?? model.role_objects[0]?.id ?? "");
    }).catch(handleFailure);
  }, [auth.state, projectId, designVersion]);

  function handleFailure(reason: unknown) {
    const message = errorText(reason);
    if (message.startsWith("401 ")) setAuth({ state: "out" });
    else setError(message);
  }

  if (error) return <Failure message={error} />;
  if (auth.state === "checking") return <Loading label="Checking access…" />;
  if (auth.state === "out") return <LoginScreen onDone={(user) => setAuth({ state: "in", user })} />;
  if (!projectId || !workspace) return <Loading label="Opening the responsibility model…" />;

  const { model: response, overview, versions, baseline, findings, proposals, changeSets } = workspace;
  const model = response.model;
  const selected = model.role_objects.find((role) => role.id === selectedRole) ?? model.role_objects[0];
  const functionLinks = model.function_role_links.filter((link) => link.function_id === selectedFunction);
  const linkedRoleIds = new Set(functionLinks.map((link) => link.role_id));
  const selectedRoleFunctionIds = new Set(model.function_role_links.filter((link) => link.role_id === selectedRole).map((link) => link.function_id));
  const latestSnapshot = baseline.code_snapshot?.snapshot;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block"><IntentMark /><div><strong>CoIntent</strong><span>shared design surface</span></div></div>
        <label className="select-field"><span>Project</span><select value={projectId} onChange={(event) => { setDesignVersion(undefined); setProjectId(event.target.value); }}>
          {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select></label>
        <div className="coordinate-strip">
          <label className="coordinate design-coordinate"><span>Design</span><select value={response.version} onChange={(event) => setDesignVersion(Number(event.target.value))}>
            {versions.map((version) => <option key={version.version} value={version.version}>v{version.version} · {version.message}</option>)}
          </select></label>
          <div className="alignment-knot" title="Design-to-code alignment coordinate">↔</div>
          <div className="coordinate"><span>Code</span><strong>{latestSnapshot?.revision.slice(0, 8) ?? "No snapshot"}</strong></div>
          <div className={`coordinate ${baseline.is_current ? "" : "stale-coordinate"}`}><span>Mapping</span><strong>{baseline.mapping_revision ? `${baseline.mapping_revision.id.replace("mapping-", "")} · ${baseline.is_current ? "current" : "stale"}` : "None"}</strong></div>
          <div className={`review-count ${overview.counts.open_findings ? "attention" : ""}`}><span>Review</span><strong>{overview.counts.open_findings + overview.counts.pending_proposals}</strong></div>
        </div>
        <button className="session-button" onClick={() => void logout().finally(() => { setWorkspace(null); setAuth({ state: "out" }); })}>
          {auth.user ?? "user"}<span>Sign out</span>
        </button>
      </header>

      <nav className="mobile-tabs" aria-label="Workspace view">
        <button className={mobileView === "functions" ? "active" : ""} onClick={() => setMobileView("functions")}>Product functions</button>
        <button className={mobileView === "roles" ? "active" : ""} onClick={() => setMobileView("roles")}>RoleObjects</button>
      </nav>

      <main className="workspace">
        <section className={`function-pane ${mobileView === "functions" ? "mobile-active" : ""}`}>
          <div className="pane-title"><div><span className="eyebrow">Product promise</span><h1>Function catalog</h1></div><span className="count-stamp">{model.product_functions.length} functions</span></div>
          <p className="model-summary">{model.summary}</p>
          <div className="catalog-rule"><span>Function</span><span>Owner coverage</span></div>
          <FunctionTree
            functions={model.product_functions}
            links={model.function_role_links}
            selected={selectedFunction}
            roleHighlights={selectedRoleFunctionIds}
            onSelect={(id) => {
              setSelectedFunction(id);
              const owner = model.function_role_links.find((link) => link.function_id === id && link.kind === "owns")
                ?? model.function_role_links.find((link) => link.function_id === id);
              if (owner) setSelectedRole(owner.role_id);
            }}
          />
          <FunctionCard item={model.product_functions.find((item) => item.id === selectedFunction)} links={functionLinks} roles={model.role_objects} onRole={setSelectedRole} />
        </section>

        <section className={`role-pane ${mobileView === "roles" ? "mobile-active" : ""}`}>
          <div className="role-map-section">
            <div className="pane-title map-title"><div><span className="eyebrow">Responsibility design</span><h1>RoleObject map</h1></div><div className="map-legend"><span className="containment-key" /> contains <span className="relation-key" /> collaboration</div></div>
            <RoleGraph roles={model.role_objects} relations={model.role_relations} selected={selectedRole} highlighted={linkedRoleIds} onSelect={setSelectedRole} />
          </div>
          <RoleInspector
            role={selected}
            functions={model.product_functions}
            responsibilities={model.responsibilities.filter((item) => item.role_id === selected?.id)}
            links={model.function_role_links.filter((item) => item.role_id === selected?.id)}
            relations={model.role_relations.filter((item) => selected && (item.source_role_id === selected.id || item.target_role_id === selected.id))}
            roles={model.role_objects}
            traces={model.trace_links.filter((item) => item.role_id === selected?.id)}
            findings={findings.filter((item) => selected && item.role_ids.includes(selected.id))}
            proposals={proposals}
            changeSets={changeSets.filter((item) => selected && (item.role_ids.includes(selected.id) || item.function_ids.some((id) => selectedRoleFunctionIds.has(id))))}
            tab={tab} onTab={setTab} onFunction={setSelectedFunction} onRole={setSelectedRole}
          />
        </section>
      </main>
    </div>
  );
}

function IntentMark() {
  return <svg className="intent-mark" viewBox="0 0 42 42" aria-hidden="true"><path d="M6 8h10l9 13 11 13M6 34h10l9-13L36 8" /><circle cx="6" cy="8" r="3" /><circle cx="6" cy="34" r="3" /><circle cx="25" cy="21" r="3.5" /><circle cx="36" cy="8" r="3" /><circle cx="36" cy="34" r="3" /></svg>;
}

function FunctionTree({ functions, links, selected, roleHighlights, onSelect }: { functions: ProductFunction[]; links: FunctionRoleLink[]; selected: string; roleHighlights: Set<string>; onSelect: (id: string) => void }) {
  const children = useMemo(() => hierarchy(functions), [functions]);
  const coverage = useMemo(() => new Map(functions.map((item) => [item.id, links.filter((link) => link.function_id === item.id)])), [functions, links]);
  const render = (parent: string | null, depth: number): ReactNode => (children.get(parent) ?? []).map((item) => {
    const itemLinks = coverage.get(item.id) ?? [];
    return <div key={item.id} className="function-branch">
      <button className={`function-row ${selected === item.id ? "selected" : ""} ${roleHighlights.has(item.id) ? "role-linked" : ""}`} style={{ "--depth": depth } as CSSProperties} onClick={() => onSelect(item.id)}>
        <span className="function-glyph">{(children.get(item.id)?.length ?? 0) > 0 ? "◇" : "·"}</span>
        <span className="function-copy"><strong>{item.name}</strong><small>{item.priority !== "unset" ? item.priority : item.status}</small></span>
        <span className={`coverage ${itemLinks.some((link) => link.kind === "owns") ? "owned" : itemLinks.length ? "linked" : "missing"}`}>{itemLinks.length}</span>
      </button>
      {render(item.id, depth + 1)}
    </div>;
  });
  return <div className="function-tree">{render(null, 0)}</div>;
}

function FunctionCard({ item, links, roles, onRole }: { item?: ProductFunction; links: FunctionRoleLink[]; roles: RoleObject[]; onRole: (id: string) => void }) {
  if (!item) return null;
  return <article className="function-card">
    <div className="card-overline"><span>Selected function</span><code>{item.id}</code></div>
    <h2>{item.name}</h2><p>{item.description}</p>
    {item.acceptance.length > 0 && <DetailList label="Acceptance" values={item.acceptance} />}
    {item.constraints.length > 0 && <DetailList label="Constraints" values={item.constraints} />}
    <div className="role-chips"><span>Responsibility links</span>{links.length ? links.map((link) => <button key={link.id} onClick={() => onRole(link.role_id)}><em>{link.kind}</em>{roles.find((role) => role.id === link.role_id)?.name ?? link.role_id}</button>) : <small>No RoleObject is linked yet.</small>}</div>
  </article>;
}

type PositionedRole = RoleObject & { x: number; y: number; width: number; height: number; depth: number };

function RoleGraph({ roles, relations, selected, highlighted, onSelect }: { roles: RoleObject[]; relations: RoleRelation[]; selected: string; highlighted: Set<string>; onSelect: (id: string) => void }) {
  const positioned = useMemo<PositionedRole[]>(() => {
    const depths = roleDepths(roles);
    const columns = new Map<number, RoleObject[]>();
    roles.forEach((role) => { const depth = depths.get(role.id) ?? 0; columns.set(depth, [...(columns.get(depth) ?? []), role]); });
    const output: PositionedRole[] = [];
    [...columns.entries()].sort(([a], [b]) => a - b).forEach(([depth, items]) => items.forEach((role, index) => output.push({ ...role, depth, x: 34 + depth * 254, y: 42 + index * 108, width: 205, height: 76 })));
    return output;
  }, [roles]);
  const byId = new Map(positioned.map((role) => [role.id, role]));
  const width = Math.max(760, ...positioned.map((role) => role.x + role.width + 40));
  const height = Math.max(390, ...positioned.map((role) => role.y + role.height + 44));
  return <div className="graph-frame"><div className="graph-canvas" style={{ width, height }}>
    <svg width={width} height={height} aria-hidden="true"><defs><marker id="relation-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0L0 6L7 3z" /></marker></defs>
      {positioned.filter((role) => role.parent_id).map((role) => { const parent = byId.get(role.parent_id!); if (!parent) return null; const active = selected === role.id || selected === parent.id; return <path key={`contains-${role.id}`} className={`containment-edge ${active ? "active" : ""}`} d={`M${parent.x + parent.width},${parent.y + parent.height / 2} C${parent.x + parent.width + 34},${parent.y + parent.height / 2} ${role.x - 34},${role.y + role.height / 2} ${role.x},${role.y + role.height / 2}`} />; })}
      {relations.map((relation) => { const source = byId.get(relation.source_role_id); const target = byId.get(relation.target_role_id); if (!source || !target) return null; const active = selected === source.id || selected === target.id; return <path key={relation.id} className={`relation-edge ${active ? "active" : ""}`} markerEnd="url(#relation-arrow)" d={`M${source.x + source.width / 2},${source.y + source.height} C${source.x + source.width / 2},${source.y + source.height + 30} ${target.x + target.width / 2},${target.y - 30} ${target.x + target.width / 2},${target.y}`} />; })}
    </svg>
    {positioned.map((role) => <button key={role.id} className={`graph-node depth-${Math.min(role.depth, 2)} ${selected === role.id ? "selected" : ""} ${highlighted.has(role.id) ? "function-linked" : ""}`} style={{ left: role.x, top: role.y, width: role.width, minHeight: role.height }} onClick={() => onSelect(role.id)}><span>{role.parent_id ? "ROLEOBJECT" : "ROOT ROLE"}</span><strong>{role.name}</strong><p>{role.purpose}</p>{highlighted.has(role.id) && <i>linked function</i>}</button>)}
  </div></div>;
}

function RoleInspector({ role, functions, responsibilities, links, relations, roles, traces, findings, proposals, changeSets, tab, onTab, onFunction, onRole }: {
  role?: RoleObject; functions: ProductFunction[]; responsibilities: Responsibility[]; links: FunctionRoleLink[]; relations: RoleRelation[]; roles: RoleObject[]; traces: TraceLink[]; findings: Finding[]; proposals: Proposal[]; changeSets: ChangeSet[]; tab: InspectorTab; onTab: (tab: InspectorTab) => void; onFunction: (id: string) => void; onRole: (id: string) => void;
}) {
  if (!role) return <section className="inspector empty">Select a RoleObject to inspect its contract.</section>;
  return <section className="inspector">
    <header className="inspector-head"><div><span className="eyebrow">RoleObject detail</span><h2>{role.name}</h2><p>{role.purpose}</p></div><code>{role.id}</code></header>
    <div className="inspector-tabs" role="tablist">{(["contract", "functions", "implementation", "review"] as InspectorTab[]).map((item) => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? "active" : ""} onClick={() => onTab(item)}>{item}<em>{item === "functions" ? links.length : item === "implementation" ? traces.length : item === "review" ? findings.length + proposals.length + changeSets.length : responsibilities.length}</em></button>)}</div>
    <div className="inspector-body">
      {tab === "contract" && <div className="detail-grid"><div className="detail-main"><h3>Responsibilities</h3>{responsibilities.length ? responsibilities.map((item, index) => <article className="responsibility" key={item.id}><span>{String(index + 1).padStart(2, "0")}</span><div><p>{item.statement}</p>{item.function_ids.length > 0 && <small>{item.function_ids.join(" · ")}</small>}</div></article>) : <Empty label="No owned responsibilities." />}</div><div className="contract-grid"><DetailList label="Owned knowledge" values={role.owns_knowledge} /><DetailList label="Inputs" values={role.inputs} /><DetailList label="Outputs" values={role.outputs} /><DetailList label="Constraints" values={role.constraints} /><div className="detail-list"><h3>Collaborators</h3>{relations.length ? relations.map((relation) => { const other = relation.source_role_id === role.id ? relation.target_role_id : relation.source_role_id; return <button className="relation-row" key={relation.id} onClick={() => onRole(other)}><em>{relation.kind}</em><span>{roles.find((item) => item.id === other)?.name ?? other}</span><small>{relation.label}</small></button>; }) : <Empty label="No explicit collaborators." />}</div></div></div>}
      {tab === "functions" && <div className="record-list"><h3>Supported ProductFunctions</h3>{links.length ? links.map((link) => <button className="linked-record" key={link.id} onClick={() => onFunction(link.function_id)}><span className={`link-kind ${link.kind}`}>{link.kind}</span><strong>{functions.find((item) => item.id === link.function_id)?.name ?? link.function_id}</strong><small>{Math.round(link.confidence * 100)}% · {link.evidence}</small></button>) : <Empty label="This RoleObject is not linked to a ProductFunction." />}</div>}
      {tab === "implementation" && <div className="record-list"><h3>Implementation evidence</h3>{traces.length ? traces.map((trace) => <article className="trace-record" key={trace.id}><span>{trace.kind}</span><code>{trace.artifact_path}</code><small>{trace.origin} · {Math.round(trace.confidence * 100)}% confidence</small><p>{trace.evidence}</p></article>) : <Empty label="No implementation evidence is mapped to this RoleObject." />}</div>}
      {tab === "review" && <div className="review-grid"><ReviewSection title="Alignment findings" items={findings.map((item) => ({ id: item.id, kind: `${item.severity} · ${item.kind}`, title: item.summary }))} empty="No open findings touch this RoleObject." /><ReviewSection title="Design proposals" items={proposals.map((item) => ({ id: item.id, kind: `base v${item.base_version}`, title: item.rationale }))} empty="No pending design proposals." /><ReviewSection title="ChangeSets" items={changeSets.map((item) => ({ id: item.id, kind: item.status, title: item.title }))} empty="No active ChangeSet touches this RoleObject." /></div>}
    </div>
  </section>;
}

function DetailList({ label, values }: { label: string; values: string[] }) { return <div className="detail-list"><h3>{label}</h3>{values.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <Empty label="Not specified." />}</div>; }
function Empty({ label }: { label: string }) { return <p className="empty-copy">{label}</p>; }
function ReviewSection({ title, items, empty }: { title: string; items: { id: string; kind: string; title: string }[]; empty: string }) { return <section className="review-section"><h3>{title}<em>{items.length}</em></h3>{items.length ? items.map((item) => <article key={item.id}><span>{item.kind}</span><strong>{item.title}</strong><code>{item.id}</code></article>) : <Empty label={empty} />}</section>; }

function LoginScreen({ onDone }: { onDone: (user: string) => void }) {
  const [user, setUser] = useState("carter");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  return <main className="login-screen"><section className="login-context"><div className="login-brand"><IntentMark /><span>CoIntent</span></div><div className="login-orbit" aria-hidden="true"><i /><i /><i /><i /></div><span className="eyebrow">Human intent / Agent implementation</span><h1>See the system<br />at responsibility scale.</h1><p>Product functions become RoleObjects. Implementation stays mapped, reviewable, and visibly separate from intent.</p></section><section className="login-gate"><form onSubmit={(event) => { event.preventDefault(); setBusy(true); setMessage(""); void login(user, password).then((result) => onDone(result.user)).catch((reason: unknown) => setMessage(errorText(reason).startsWith("429 ") ? "Too many attempts. Wait a few minutes and try again." : "The username or password is incorrect.")).finally(() => setBusy(false)); }}><span className="eyebrow">Protected workspace</span><h2>Open the design</h2><p>Human sessions and Agent MCP credentials remain independent.</p><label>Username<input name="username" autoComplete="username" value={user} onChange={(event) => setUser(event.target.value)} /></label><label>Password<input name="password" type="password" autoComplete="current-password" autoFocus value={password} onChange={(event) => setPassword(event.target.value)} /></label>{message && <div className="login-error" role="alert">{message}</div>}<button type="submit" disabled={busy || !user || !password}>{busy ? "Checking…" : "Open CoIntent"}<span>→</span></button><small>Signed session · HttpOnly · SameSite Strict</small></form></section></main>;
}

function Loading({ label }: { label: string }) { return <div className="state-screen"><IntentMark /><span>{label}</span></div>; }
function Failure({ message }: { message: string }) { return <div className="state-screen failure"><IntentMark /><h1>The workspace could not open.</h1><p>{message}</p><button onClick={() => location.reload()}>Reload</button></div>; }
function errorText(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }
function hierarchy<T extends { parent_id: string | null }>(items: T[]) { const map = new Map<string | null, T[]>(); items.forEach((item) => map.set(item.parent_id, [...(map.get(item.parent_id) ?? []), item])); return map; }
function firstLeaf(items: ProductFunction[]) { const parents = new Set(items.map((item) => item.parent_id).filter(Boolean)); return items.find((item) => !parents.has(item.id)); }
function roleDepths(roles: RoleObject[]) { const byId = new Map(roles.map((role) => [role.id, role])); const result = new Map<string, number>(); const depth = (role: RoleObject): number => { if (result.has(role.id)) return result.get(role.id)!; const value = role.parent_id && byId.has(role.parent_id) ? depth(byId.get(role.parent_id)!) + 1 : 0; result.set(role.id, value); return value; }; roles.forEach(depth); return result; }

export default App;
