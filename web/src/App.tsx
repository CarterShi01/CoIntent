import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  applyTargetDesignOperations, createImplementationContext, createTargetDesignWorkspace,
  createUaViewerSession, fetchStructureDesignDiff,
  fetchObservation, fetchProjectState, fetchSession, fetchTargetDesignWorkspace, fetchUaNodeSubjects,
  inspectUnderstandingRefresh, listProjects, loadWorkspace, login, logout,
  requestObservationExpansion,
} from "./api";
import type {
  AlignmentBaseline, ChangeSet, DesignVersion, Finding, ImplementationLink, ModelResponse,
  ImplementationContextResult, ImplementationRef, ObservationCoordinate, OverviewResponse, Project,
  Proposal, Responsibility, SpecificationItem, SpecificationResponsibilityLink, TargetDesignOperation,
  ProjectState, StructureDesignDiff, TargetDesignView, UaSemanticSubject, UaViewerSession,
  UnderstandingRefreshJob, Workflow,
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
type UnderstandSubview = "system" | "implementation";
type ExpansionNotice = { nodeId: string; tone: "working" | "done" | "atomic" | "failed"; message: string };

export default function App() {
  const [auth, setAuth] = useState<Auth>({ state: "checking" });
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [designVersion, setDesignVersion] = useState<number | undefined>();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [observation, setObservation] = useState<ObservationCoordinate | undefined>();
  const [targetDesign, setTargetDesign] = useState<TargetDesignView | null | undefined>();
  const [mode, setMode] = useState<ProcessMode>(() => location.pathname.endsWith("/design") ? "design" : "understand");
  const [understandSubview, setUnderstandSubview] = useState<UnderstandSubview>(() =>
    new URLSearchParams(location.search).get("view") === "implementation" ? "implementation" : "system");
  const [routeKey, setRouteKey] = useState(0);
  const [refreshJob, setRefreshJob] = useState<UnderstandingRefreshJob | null>(null);
  const [projectState, setProjectState] = useState<ProjectState | null>(null);
  const [viewerSession, setViewerSession] = useState<UaViewerSession | null>(null);
  const [viewerFocus, setViewerFocus] = useState<ImplementationRef | null>(null);
  const [viewerOriginId, setViewerOriginId] = useState("");
  const [selectedObserved, setSelectedObserved] = useState("");
  const [expansionNotice, setExpansionNotice] = useState<ExpansionNotice | null>(null);
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
    const syncPath = () => {
      setMode(location.pathname.endsWith("/design") ? "design" : "understand");
      setUnderstandSubview(
        new URLSearchParams(location.search).get("view") === "implementation" ? "implementation" : "system",
      );
      setRouteKey((current) => current + 1);
    };
    addEventListener("popstate", syncPath);
    return () => removeEventListener("popstate", syncPath);
  }, []);

  useEffect(() => {
    if (auth.state !== "in") return;
    listProjects().then((items) => {
      setProjects(items);
      const requested = new URLSearchParams(location.search).get("project");
      setProjectId((current) => current || items.find((item) => item.id === requested)?.id || items[0]?.id || "");
    }).catch(handleFailure);
  }, [auth.state]);

  useEffect(() => {
    if (auth.state !== "in" || !projectId) return;
    setWorkspace(null);
    setObservation(undefined);
    setTargetDesign(undefined);
    setProjectState(null);
    setRefreshJob(null);
    setViewerSession(null);
    setViewerFocus(null);
    const query = new URLSearchParams(location.search);
    const linkedRevision = query.get("project") === projectId ? query.get("observed_revision") ?? undefined : undefined;
    Promise.all([
      loadWorkspace(projectId, designVersion),
      fetchObservation(projectId, linkedRevision),
      fetchTargetDesignWorkspace(projectId),
    ]).then(([next, observed, target]) => {
      setWorkspace(next);
      setObservation(observed);
      setTargetDesign(target);
      setSelectedObserved(observed.observed_revision?.capabilities[0]?.responsibility_id
        ?? observed.observed_revision?.responsibilities[0]?.id ?? "");
      const model = next.model.model;
      const root = rootResponsibilities(model.responsibilities)[0] ?? model.responsibilities[0];
      setPath(root ? [root.id] : []);
      setForwardIds([]);
      setSelectedSpec(model.specification_items[0]?.id ?? "");
      fetchProjectState(projectId).then((state) => {
        setProjectState(state);
        setRefreshJob(state.latest_refresh);
      }).catch((reason: unknown) => {
        if (errorText(reason).startsWith("401 ")) setAuth({ state: "out" });
      });
      if (query.get("view") === "implementation" && observed.observed_revision && observed.ua_snapshot) {
        const requestedUa = query.get("ua_snapshot");
        if (requestedUa && requestedUa !== observed.ua_snapshot.id) {
          throw new Error("The implementation-map link does not match the selected Observation.");
        }
        const requestedNode = query.get("node");
        const ref = observed.observed_revision.implementation_refs.find((item) =>
          item.preferred_focus_node_id === requestedNode || item.structural_ua_node_ids.includes(requestedNode ?? ""),
        ) ?? null;
        setViewerFocus(ref);
        setViewerOriginId(query.get("from") ?? ref?.subject_id ?? "");
        return createUaViewerSession(projectId, observed.observed_revision.id, observed.ua_snapshot.id)
          .then(setViewerSession);
      }
    }).catch(handleFailure);
  }, [auth.state, projectId, designVersion, routeKey]);

  useEffect(() => {
    if (!refreshJob || !["queued", "running", "awaiting_upload", "validating"].includes(refreshJob.status)) return;
    const timer = window.setInterval(() => {
      inspectUnderstandingRefresh(refreshJob.id).then(async (job) => {
        setRefreshJob(job);
        if (job.status === "completed") {
          const observed = await fetchObservation(projectId);
          setObservation(observed);
          setSelectedObserved(observed.observed_revision?.capabilities[0]?.responsibility_id
            ?? observed.observed_revision?.responsibilities[0]?.id ?? "");
          setViewerSession(null);
          setProjectState(await fetchProjectState(projectId));
        }
      }).catch(handleFailure);
    }, 1800);
    return () => window.clearInterval(timer);
  }, [refreshJob?.id, refreshJob?.status, projectId]);

  function handleFailure(reason: unknown) {
    const message = errorText(reason);
    if (message.startsWith("401 ")) setAuth({ state: "out" });
    else setError(message);
  }

  function chooseMode(next: ProcessMode) {
    if (next === mode) return;
    const query = new URLSearchParams({ project: projectId });
    history.pushState({}, "", `${next === "design" ? "/design" : "/understand"}?${query}`);
    setMode(next);
    setMobilePane("functions");
  }

  function chooseProject(nextProjectId: string) {
    const query = new URLSearchParams({ project: nextProjectId });
    if (mode === "understand" && understandSubview === "implementation") query.set("view", "implementation");
    history.pushState({}, "", `${mode === "design" ? "/design" : "/understand"}?${query}`);
    setDesignVersion(undefined);
    setProjectId(nextProjectId);
  }

  async function ensureViewer(nextObservation = observation): Promise<UaViewerSession | null> {
    const revision = nextObservation?.observed_revision;
    const ua = nextObservation?.ua_snapshot;
    if (!revision || !ua) return null;
    if (viewerSession?.observed_revision_id === revision.id && viewerSession.ua_snapshot_id === ua.id
        && Date.parse(viewerSession.expires_at) > Date.now() + 30_000) {
      return viewerSession;
    }
    const created = await createUaViewerSession(projectId, revision.id, ua.id);
    setViewerSession(created);
    return created;
  }

  async function chooseUnderstandSubview(next: UnderstandSubview) {
    setUnderstandSubview(next);
    const query = new URLSearchParams(location.search);
    query.set("project", projectId);
    if (next === "implementation") query.set("view", "implementation");
    else query.delete("view");
    history.pushState({}, "", `/understand${query.size ? `?${query}` : ""}`);
    if (next === "implementation") {
      try { await ensureViewer(); } catch (reason) { handleFailure(reason); }
    }
  }

  async function openImplementation(ref: ImplementationRef, originId: string) {
    try {
      setViewerFocus(ref);
      setViewerOriginId(originId);
      setUnderstandSubview("implementation");
      await ensureViewer();
      const query = new URLSearchParams({
        project: projectId,
        view: "implementation",
        observed_revision: ref.observed_revision_id,
        ua_snapshot: ref.ua_snapshot_id,
        node: ref.preferred_focus_node_id ?? "",
        from: originId,
      });
      history.pushState({}, "", `/understand?${query}`);
    } catch (reason) {
      handleFailure(reason);
    }
  }

  async function openBaselineImplementation(revisionId: string, nodeId: string) {
    try {
      const baseline = await fetchObservation(projectId, revisionId);
      const refs = baseline.observed_revision?.implementation_refs.filter((item) => item.subject_id === nodeId) ?? [];
      const ref = refs.find((item) => item.role === "primary") ?? refs[0];
      if (!ref) throw new Error("No implementation reference exists for this baseline node.");
      setObservation(baseline);
      setViewerSession(null);
      chooseMode("understand");
      setViewerFocus(ref);
      setViewerOriginId(nodeId);
      setUnderstandSubview("implementation");
      const created = await createUaViewerSession(projectId, revisionId, ref.ua_snapshot_id);
      setViewerSession(created);
      history.pushState({}, "", `/understand?${new URLSearchParams({
        project: projectId, view: "implementation", observed_revision: revisionId,
        ua_snapshot: ref.ua_snapshot_id, node: ref.preferred_focus_node_id ?? "", from: nodeId,
      })}`);
    } catch (reason) {
      handleFailure(reason);
    }
  }

  if (error) return <Failure message={error} />;
  if (auth.state === "checking") return <Loading label="Checking access…" />;
  if (auth.state === "out") return <LoginScreen onDone={(user) => setAuth({ state: "in", user })} />;
  if (!projectId || !workspace || observation === undefined || targetDesign === undefined) return <Loading label="Opening the workspace…" />;

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

  async function expandObservation(nodeId: string) {
    const revision = observation?.observed_revision;
    if (!revision || expansionNotice?.tone === "working") return;
    setExpansionNotice({ nodeId, tone: "working", message: "Reading one deeper level from the pinned UA map…" });
    try {
      const result = await requestObservationExpansion(projectId, revision.id, nodeId);
      if (result.request.status === "completed" && result.request.result_observed_revision_id) {
        const refined = await fetchObservation(projectId, result.request.result_observed_revision_id);
        setObservation(refined);
        setSelectedObserved(refined.observed_revision?.refinement_of_node_id
          ?? refined.observed_revision?.responsibilities[0]?.id ?? "");
        setExpansionNotice({
          nodeId,
          tone: "done",
          message: result.request.message || "A deeper evidence-backed view is ready.",
        });
        return;
      }
      setExpansionNotice({
        nodeId,
        tone: result.request.status === "atomic_at_current_evidence" ? "atomic" : "failed",
        message: result.request.message || "The refinement did not produce a child view.",
      });
    } catch (reason) {
      setExpansionNotice({ nodeId, tone: "failed", message: errorText(reason) });
    }
  }

  async function openObservedRevision(revisionId: string, nodeId: string) {
    setExpansionNotice(null);
    try {
      const next = await fetchObservation(projectId, revisionId);
      setObservation(next);
      setSelectedObserved(nodeId || next.observed_revision?.responsibilities[0]?.id || "");
    } catch (reason) {
      handleFailure(reason);
    }
  }

  async function createTargetFromBaseline(observedRevisionId: string) {
    const project = projects.find((item) => item.id === projectId);
    await createTargetDesignWorkspace(
      projectId,
      observedRevisionId,
      `${project?.name ?? projectId} target design`,
      "Create an independent target from the latest explicitly refreshed current structure.",
    );
    setTargetDesign(await fetchTargetDesignWorkspace(projectId));
  }

  async function startTargetDesign() {
    try {
      const baseline = observation?.observed_revision?.id;
      if (!baseline || !projectState?.allowed_next_actions.includes("start_structure_design")) {
        throw new Error("Ask your Agent to update understanding before starting a new design.");
      }
      await createTargetFromBaseline(baseline);
    } catch (reason) {
      handleFailure(reason);
    }
  }

  async function applyTargetOperations(operations: TargetDesignOperation[], rationale: string) {
    if (!targetDesign) return;
    await applyTargetDesignOperations(
      targetDesign.workspace.id,
      targetDesign.revision.id,
      operations,
      rationale,
    );
    setTargetDesign(await fetchTargetDesignWorkspace(projectId, targetDesign.workspace.id));
  }

  async function openTargetRevision(revisionId: string) {
    if (!targetDesign) return;
    try {
      setTargetDesign(await fetchTargetDesignWorkspace(
        projectId, targetDesign.workspace.id, revisionId,
      ));
    } catch (reason) {
      handleFailure(reason);
    }
  }

  async function refreshTargetDesign() {
    if (!targetDesign) return;
    setTargetDesign(await fetchTargetDesignWorkspace(projectId, targetDesign.workspace.id));
  }

  async function readTargetDiff(): Promise<StructureDesignDiff> {
    if (!targetDesign) throw new Error("No target drawing is open.");
    return fetchStructureDesignDiff(targetDesign.workspace.id, targetDesign.revision.id);
  }

  async function buildImplementationContext(diffDigest: string): Promise<ImplementationContextResult> {
    if (!targetDesign) throw new Error("No target drawing is open.");
    const result = await createImplementationContext(
      targetDesign.workspace.id, targetDesign.revision.id, diffDigest,
    );
    const blob = new Blob([`${JSON.stringify(result, null, 2)}\n`], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${result.implementation_context.id}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    await refreshTargetDesign();
    return result;
  }

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><IntentMark /><div><strong>CoIntent</strong><span>Program logic, made legible</span></div></div>
      <label className="project-picker"><span>Project</span><select value={projectId} onChange={(event) => chooseProject(event.target.value)}>
        {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select></label>
      {mode === "understand" ? <div className="model-coordinate observation-coordinate">
        <div><span>Code</span><strong>{observation.code_snapshot?.revision.slice(0, 8) ?? "No full snapshot"}</strong></div>
        <i aria-hidden="true">→</i>
        <div><span>Understand Anything</span><strong>{observation.ua_snapshot ? `graph ${observation.ua_snapshot.ua_graph_version}` : "Not imported"}</strong></div>
        <div className={observation.status === "current" ? "aligned" : "drifted"}><span>Current structure</span><strong>{observation.status === "current" ? "Read only · current" : observation.status === "stale" ? "Read only · stale" : "Not generated"}</strong></div>
      </div> : <div className="model-coordinate design-coordinate">
        <div><span>Observed baseline</span><strong>{
          targetDesign?.workspace.base_observed_revision_id.slice(0, 18)
          ?? observation.observed_revision?.id.slice(0, 18)
          ?? "Update understanding first"
        }</strong></div>
        <i aria-hidden="true">→</i>
        <div><span>Target revision</span><strong>{targetDesign?.revision.id.slice(0, 18) ?? "Start a workspace"}</strong></div>
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
        <span>Intent → target structure → diff</span><strong>Design future</strong><small>Editable target</small>
      </button>
    </nav>
    {mode === "understand" && <nav className="understand-subviews" aria-label="Current understanding view">
      <div><button className={understandSubview === "system" ? "active" : ""} onClick={() => void chooseUnderstandSubview("system")}><span>System view</span><small>Functions and Responsibilities</small></button>
      <button className={understandSubview === "implementation" ? "active" : ""} disabled={!observation.observed_revision} onClick={() => void chooseUnderstandSubview("implementation")}><span>Implementation map</span><small>UA code and dependencies</small></button></div>
      <div className="refresh-observer" aria-live="polite">
        <small>Scans run through your Agent</small>
        {refreshJob && <span className={`refresh-status ${refreshJob.status}`} title={refreshJob.error ?? refreshJob.fallback_reason ?? ""}>
          {refreshJob.status === "completed" ? `${refreshJob.mode} · ${refreshJob.changed_files.length} changed` : refreshJob.status.replace("_", " ")}
        </span>}
      </div>
    </nav>}
    {!(mode === "understand" && understandSubview === "implementation") && <nav className={`mobile-pane-tabs ${mode}${mode === "design" && !targetDesign ? " two-pane" : ""}`} aria-label="Workspace area">
      <button className={mobilePane === "functions" ? "active" : ""} onClick={() => setMobilePane("functions")}>{mode === "understand" ? "Functions" : "Expected"}</button>
      <button className={mobilePane === "structure" ? "active" : ""} onClick={() => setMobilePane("structure")}>Structure</button>
      {(mode === "understand" || targetDesign) && <button className={mobilePane === "details" ? "active" : ""} onClick={() => setMobilePane("details")}>{mode === "understand" ? "Evidence" : "Details"}</button>}
    </nav>}

    {mode === "understand" && understandSubview === "implementation" ? <UaImplementationMap
      coordinate={observation}
      session={viewerSession}
      focus={viewerFocus}
      originSemanticId={viewerOriginId}
      onRenew={() => ensureViewer()}
      onBack={(revisionId, subjectId) => { void openObservedRevision(revisionId, subjectId); void chooseUnderstandSubview("system"); }}
    /> : mode === "understand" ? <UnderstandingWorkspace
      coordinate={observation}
      selectedId={selectedObserved}
      onSelect={(id) => { setSelectedObserved(id); setExpansionNotice(null); setMobilePane("structure"); }}
      onExpand={(id) => void expandObservation(id)}
      onOpenRevision={(revisionId, nodeId) => void openObservedRevision(revisionId, nodeId)}
      expansionNotice={expansionNotice}
      mobilePane={mobilePane}
      onOpenImplementation={(ref, subjectId) => void openImplementation(ref, subjectId)}
    /> : targetDesign
      ? <TargetDesignWorkspace
          view={targetDesign}
          mobilePane={mobilePane}
          onApply={(operations, rationale) => applyTargetOperations(operations, rationale)}
          onOpenRevision={(revisionId) => void openTargetRevision(revisionId)}
          onReadDiff={readTargetDiff}
          onCreateContext={buildImplementationContext}
          onStartNew={() => void startTargetDesign()}
          onViewBaseline={(revisionId, nodeId) => void openBaselineImplementation(revisionId, nodeId)}
        />
      : <TargetDesignBaseline
          workspace={workspace}
          observation={observation}
          mobilePane={mobilePane}
          canStart={Boolean(projectState?.allowed_next_actions.includes("start_structure_design"))}
          onCreate={() => void startTargetDesign()}
        />}
  </div>;
}

function TargetDesignBaseline({ workspace, observation, mobilePane, canStart, onCreate }: {
  workspace: Workspace | null;
  observation?: ObservationCoordinate;
  mobilePane: "functions" | "structure" | "details";
  canStart: boolean;
  onCreate: () => void;
}) {
  const model = workspace?.model.model;
  const revision = observation?.observed_revision;
  const byId = useMemo(
    () => new Map((revision?.responsibilities ?? []).map((item) => [item.id, item])),
    [revision],
  );
  const roots = useMemo(() => rootResponsibilities(revision?.responsibilities ?? []), [revision]);
  const [selectedRoot, setSelectedRoot] = useState("");

  useEffect(() => {
    setSelectedRoot((current) => current && byId.has(current) ? current : roots[0]?.id ?? "");
  }, [revision?.id, byId, roots]);

  const current = byId.get(selectedRoot) ?? roots[0];
  const intents = model?.specification_items ?? [];

  return <main className="target-design-baseline design-workspace" data-mobile-pane={mobilePane}>
    <aside className="baseline-intent-pane">
      <div className="baseline-pane-heading">
        <span className="eyebrow">Latest user intent</span>
        <h1>What you most recently asked the system to be</h1>
        <p>This is the latest recorded intent layer. It remains separate from the code-derived structure on the right.</p>
      </div>
      <div className="baseline-coordinate">
        <span>Intent version</span>
        <strong>{workspace ? `v${workspace.model.version}` : "Loading"}</strong>
        <small>{workspace?.model.message ?? "Reading the latest intent…"}</small>
      </div>
      <div className="baseline-intent-list">{intents.length ? intents.map((item) => <article key={item.id}>
        <span>{item.status}</span>
        <h2>{item.name}</h2>
        <p>{item.description}</p>
      </article>) : <div className="baseline-empty-copy"><strong>No recorded intent yet</strong><p>Ask your Agent to capture the product intent before starting a target design.</p></div>}</div>
      <div className="baseline-start-design">
        <span>Explicit design boundary</span>
        <p>Starting creates a separate, human-owned target graph from this named observed revision. It never edits current truth.</p>
        <button disabled={!canStart} onClick={onCreate}>{canStart ? "Start target design from this baseline" : "Ask your Agent to update understanding"}<b>→</b></button>
      </div>
    </aside>

    <section className="baseline-structure-pane">
      <header>
        <div><span className="eyebrow">Current structure · read only</span><h1>{current?.name ?? "No scanned structure yet"}</h1></div>
        <span className="baseline-truth-seal">Code-derived<br /><b>{revision ? "Current baseline" : "Awaiting scan"}</b></span>
      </header>
      {revision ? <>
        <div className="baseline-revision-line"><span>Observation</span><code>{revision.id}</code><span>Code</span><code>{observation?.code_snapshot?.revision.slice(0, 12)}</code></div>
        {roots.length > 0 && <nav className="baseline-root-switcher" aria-label="Current structure roots">{roots.map((item) => <button key={item.id} className={item.id === current?.id ? "active" : ""} onClick={() => setSelectedRoot(item.id)}>{item.name}</button>)}</nav>}
        <p className="responsibility-description">{current?.description}</p>
        {current?.workflow
          ? <WorkflowCanvas workflow={current.workflow} responsibilities={byId} activePathIds={new Set([current.id])} onEnter={setSelectedRoot} allowLeafSelection />
          : <div className="leaf-stage baseline-leaf"><div className="leaf-symbol"><span /><i /><b /></div><span className="eyebrow">Current leaf</span><h2>{current?.name}</h2><p>This Responsibility is atomic at the current scanned evidence depth.</p></div>}
      </> : <div className="baseline-no-observation"><IntentMark /><span>Current truth is not generated</span><h2>Ask your Agent to update understanding.</h2><p>The right side will populate only after code → UA → Observation completes. A design draft can never fill this space.</p></div>}
    </section>
  </main>;
}

function TargetDesignWorkspace({
  view, mobilePane, onApply, onOpenRevision, onReadDiff, onCreateContext, onStartNew,
  onViewBaseline,
}: {
  view: TargetDesignView;
  mobilePane: "functions" | "structure" | "details";
  onApply: (operations: TargetDesignOperation[], rationale: string) => Promise<void>;
  onOpenRevision: (revisionId: string) => void;
  onReadDiff: () => Promise<StructureDesignDiff>;
  onCreateContext: (diffDigest: string) => Promise<ImplementationContextResult>;
  onStartNew: () => void;
  onViewBaseline: (revisionId: string, nodeId: string) => void;
}) {
  const revision = view.revision;
  const isCurrent = view.workspace.current_design_revision_id === revision.id;
  const editable = isCurrent && view.workspace.status === "draft";
  const targetState = !isCurrent ? "Historical revision"
    : view.workspace.status === "in_review" ? "Review locked"
    : view.workspace.status === "approved" ? "Approved target"
    : view.workspace.status === "exported" ? "Exported target"
    : view.workspace.status === "verifying" ? "Verification review"
    : view.workspace.status === "converged" ? "Converged"
    : view.workspace.status === "needs_revision" ? "Needs revision"
    : "Editable draft";
  const byId = useMemo(() => new Map(revision.responsibilities.map((item) => [item.id, item])), [revision]);
  const roots = useMemo(() => rootResponsibilities(revision.responsibilities), [revision]);
  const [path, setPath] = useState<string[]>([]);
  const [selectedFeature, setSelectedFeature] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    const nextFeature = revision.expected_features.find((item) => item.id === selectedFeature)
      ?? revision.expected_features[0];
    const linked = revision.feature_responsibility_links.find((item) =>
      item.expected_feature_id === nextFeature?.id && item.kind === "realizes")
      ?? revision.feature_responsibility_links.find((item) => item.expected_feature_id === nextFeature?.id);
    setSelectedFeature(nextFeature?.id ?? "");
    setPath((current) => {
      const retained = current.filter((id) => byId.has(id));
      return retained.length ? retained : linked ? [linked.responsibility_id] : roots[0] ? [roots[0].id] : [];
    });
  }, [revision.id, byId, roots, revision.expected_features, revision.feature_responsibility_links, selectedFeature]);

  const current = byId.get(path[path.length - 1]) ?? roots[0] ?? revision.responsibilities[0];
  const currentPath = path.map((id) => byId.get(id)).filter(Boolean) as Responsibility[];
  const baselineLink = revision.baseline_links.find((item) =>
    item.design_kind === "responsibility" && item.design_id === current?.id);

  function enter(id: string) {
    if (!byId.has(id)) return;
    setPath((currentPath) => {
      const repeated = currentPath.lastIndexOf(id);
      return repeated >= 0 ? currentPath.slice(0, repeated + 1) : [...currentPath, id];
    });
  }

  function selectFeature(id: string) {
    setSelectedFeature(id);
    const links = revision.feature_responsibility_links.filter((item) => item.expected_feature_id === id);
    const linked = links.find((item) => item.kind === "realizes") ?? links[0];
    if (linked) setPath([linked.responsibility_id]);
  }

  async function apply(operations: TargetDesignOperation[], rationale: string) {
    setBusy(true); setProblem("");
    try { await onApply(operations, rationale); }
    catch (reason) { setProblem(errorText(reason)); }
    finally { setBusy(false); }
  }

  return <main className="workspace design-workspace target-workspace" data-mobile-pane={mobilePane}>
    <aside className="spec-pane target-feature-pane">
      <div className="pane-heading"><span className="eyebrow">What should become possible</span><h2>Expected functions</h2><p>{revision.summary}</p></div>
      <div className="spec-columns"><span>Human-owned expectation</span><span>Map</span></div>
      <div className="spec-tree">{revision.expected_features.map((item) => {
        const mapped = revision.feature_responsibility_links.filter((link) => link.expected_feature_id === item.id).length;
        return <button key={item.id} className={`spec-row ${selectedFeature === item.id ? "selected" : ""}`} onClick={() => selectFeature(item.id)}>
          <span className="tree-mark">◇</span><span><strong>{item.name}</strong><small>{item.description}</small></span><em>{mapped}</em>
        </button>;
      })}</div>
      <NewExpectedFunction disabled={busy || !editable} onCreate={(name, description) => {
        const featureId = newDesignId("des-feature");
        const responsibilityId = newDesignId("des-resp");
        setSelectedFeature(featureId);
        setPath([responsibilityId]);
        void apply([
          { kind: "upsert_expected_feature", expected_feature: { id: featureId, name, description, parent_id: null, status: "draft" } },
          { kind: "upsert_responsibility", responsibility: { id: responsibilityId, name, description, data_members: [], inputs: [], outputs: [], workflow: null, status: "draft", source_ids: [] } },
          { kind: "upsert_feature_link", feature_link: { id: newDesignId("des-link"), expected_feature_id: featureId, responsibility_id: responsibilityId, kind: "realizes" } },
        ], `Add expected function “${name}” and its initial target Responsibility.`);
      }} />
      <div className="design-provenance"><span>Separate truth coordinate</span><label>Revision<select value={revision.id} onChange={(event) => onOpenRevision(event.target.value)}>{view.revisions.map((item, index) => <option value={item.id} key={item.id}>{index === 0 ? "Current · " : "History · "}{item.id.slice(0, 16)}</option>)}</select></label><small>{revision.created_by} · {revision.rationale}</small>
        {view.workspace.status !== "draft" && <button className="new-design-action" onClick={onStartNew}>Start another design from the scanned baseline</button>}
      </div>
    </aside>

    <section className="logic-pane target-logic">
      <div className="logic-head">
        <nav className="breadcrumbs" aria-label="Target structure path">{currentPath.map((item, index) => <span key={item.id}>{index > 0 && <i>›</i>}<button onClick={() => setPath(path.slice(0, index + 1))}>{item.name}</button></span>)}</nav>
        <div className="logic-title"><div><span className="eyebrow">Target responsibility</span><h1>{current?.name ?? "No target structure"}</h1></div><span className="target-seal">{targetState}<br /><b>Human-owned</b></span></div>
        <p className="responsibility-description">{current?.description}</p>
        <div className="scope-note"><span>Inside this target</span><strong>{current?.workflow?.nodes.length ?? 0} delegated responsibilities</strong><small>Every save creates a new immutable design revision.</small></div>
      </div>
      {current?.workflow
        ? <WorkflowCanvas workflow={current.workflow} responsibilities={byId} activePathIds={new Set(path)} onEnter={enter} allowLeafSelection />
        : <div className="leaf-stage target-leaf"><div className="leaf-symbol"><span /><i /><b /></div><span className="eyebrow">Target leaf</span><h2>{current?.name}</h2><p>Add a child Responsibility when this target needs a more detailed delegation.</p></div>}
    </section>

    <TargetDesignInspector
      revision={revision}
      responsibility={current}
      baselineObservedId={baselineLink?.observed_id}
      busy={busy}
      editable={editable}
      problem={problem}
      onApply={apply}
      workspaceStatus={view.workspace.status}
      implementationExport={view.implementation_export}
      onReadDiff={onReadDiff}
      onCreateContext={onCreateContext}
      onViewBaseline={(observedId) => onViewBaseline(revision.base_observed_revision_id, observedId)}
    />
  </main>;
}

function NewExpectedFunction({ disabled, onCreate }: {
  disabled: boolean;
  onCreate: (name: string, description: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  if (!open) return <button className="add-target-action" onClick={() => setOpen(true)}>＋ Add expected function</button>;
  return <form className="inline-target-form" onSubmit={(event) => {
    event.preventDefault();
    onCreate(name.trim(), description.trim());
    setName(""); setDescription(""); setOpen(false);
  }}>
    <label>Function name<input required value={name} onChange={(event) => setName(event.target.value)} /></label>
    <label>Expected outcome<textarea required value={description} onChange={(event) => setDescription(event.target.value)} /></label>
    <div><button type="button" onClick={() => setOpen(false)}>Cancel</button><button disabled={disabled || !name.trim() || !description.trim()}>Add to target</button></div>
  </form>;
}

function TargetDesignInspector({
  revision, responsibility, baselineObservedId, busy, editable, problem, workspaceStatus,
  implementationExport, onApply, onReadDiff, onCreateContext, onViewBaseline,
}: {
  revision: TargetDesignView["revision"];
  responsibility?: Responsibility;
  baselineObservedId?: string;
  busy: boolean;
  editable: boolean;
  problem: string;
  workspaceStatus: string;
  implementationExport: TargetDesignView["implementation_export"];
  onApply: (operations: TargetDesignOperation[], rationale: string) => Promise<void>;
  onReadDiff: () => Promise<StructureDesignDiff>;
  onCreateContext: (diffDigest: string) => Promise<ImplementationContextResult>;
  onViewBaseline: (observedId: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [childName, setChildName] = useState("");
  const [childDescription, setChildDescription] = useState("");
  const [criteriaText, setCriteriaText] = useState(revision.acceptance_criteria.join("\n"));
  const [designDiff, setDesignDiff] = useState<StructureDesignDiff | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewProblem, setReviewProblem] = useState("");
  useEffect(() => { setName(responsibility?.name ?? ""); setDescription(responsibility?.description ?? ""); }, [responsibility?.id, responsibility?.name, responsibility?.description]);
  useEffect(() => {
    setCriteriaText(revision.acceptance_criteria.join("\n"));
    setDesignDiff(null);
  }, [revision.id, revision.acceptance_criteria]);
  if (!responsibility) return <aside className="inspector"><p className="empty">Add an expected function to begin the target graph.</p></aside>;

  const saveResponsibility = () => onApply([{ kind: "upsert_responsibility", responsibility: {
    ...responsibility, name: name.trim(), description: description.trim(),
  }}], `Revise target Responsibility “${responsibility.name}”.`);
  const addChild = () => {
    const childId = newDesignId("des-resp");
    const occurrenceId = newDesignId("des-occ");
    const previous = responsibility.workflow;
    const workflow: Workflow = {
      entry_node_ids: [...(previous?.entry_node_ids ?? []), occurrenceId],
      nodes: [...(previous?.nodes ?? []), { id: occurrenceId, responsibility_id: childId, note: childDescription.trim() }],
      edges: previous?.edges ?? [],
    };
    void onApply([
      { kind: "upsert_responsibility", responsibility: {
        id: childId, name: childName.trim(), description: childDescription.trim(),
        data_members: [], inputs: [], outputs: [], workflow: null, status: "draft", source_ids: [],
      } },
      { kind: "set_workflow", responsibility_id: responsibility.id, workflow },
    ], `Decompose “${responsibility.name}” with child Responsibility “${childName.trim()}”.`);
    setChildName(""); setChildDescription("");
  };
  async function reviewAction(action: () => Promise<unknown>) {
    setReviewBusy(true); setReviewProblem("");
    try { await action(); }
    catch (reason) { setReviewProblem(errorText(reason)); }
    finally { setReviewBusy(false); }
  }
  const acceptanceCriteria = criteriaText.split("\n").map((item) => item.trim()).filter(Boolean);
  const criteriaUnchanged = JSON.stringify(acceptanceCriteria) === JSON.stringify(revision.acceptance_criteria);

  return <aside className="inspector target-inspector">
    <div className="inspector-heading"><span className="eyebrow">Design controls</span><h2>{responsibility.name}</h2><code>{responsibility.id}</code></div>
    <section className="target-edit-block"><h3>Responsibility wording</h3>
      <label>Name<input disabled={!editable} value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label>Desired responsibility<textarea disabled={!editable} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      <button disabled={busy || !editable || !name.trim()} onClick={() => void saveResponsibility()}>{busy ? "Creating revision…" : editable ? "Save as new revision" : "Open current revision to edit"}</button>
    </section>
    <section className="target-edit-block"><h3>Decompose target</h3><p>Add one independently reviewable child Responsibility.</p>
      <label>Child name<input disabled={!editable} value={childName} onChange={(event) => setChildName(event.target.value)} /></label>
      <label>What it owns<textarea disabled={!editable} value={childDescription} onChange={(event) => setChildDescription(event.target.value)} /></label>
      <button disabled={busy || !editable || !childName.trim()} onClick={addChild}>Add child Responsibility</button>
    </section>
    <section className="baseline-card"><span>Observed origin</span>{baselineObservedId
      ? <><code>{baselineObservedId}</code><button onClick={() => onViewBaseline(baselineObservedId)}>View exact baseline →</button></>
      : <p>Target-only node · not implemented yet</p>}</section>
    <section className="design-review-card">
      <span>Review target drawing</span>
      {workspaceStatus === "draft" ? <>
        <h3>Structure first, implementation second</h3>
        <p>Record a testable outcome, then review the complete target graph against its frozen observed baseline.</p>
        <label>Acceptance criteria<textarea value={criteriaText} onChange={(event) => setCriteriaText(event.target.value)} placeholder={"A user can…\nThe system preserves…"} /><small>One testable outcome per line.</small></label>
        <button disabled={reviewBusy || !editable || !acceptanceCriteria.length} onClick={() => void reviewAction(async () => {
          if (!criteriaUnchanged) {
            await onApply([{ kind: "set_acceptance_criteria", acceptance_criteria: acceptanceCriteria }], "Define the target drawing acceptance criteria.");
            return;
          }
          setDesignDiff(await onReadDiff());
        })}>{reviewBusy ? "Preparing review…" : criteriaUnchanged ? "Review structure diff" : "Save acceptance criteria"}</button>
        {designDiff && <div className="target-diff" aria-live="polite">
          <h3>{designDiff.changes.length} semantic changes</h3>
          <ul>{designDiff.changes.slice(0, 8).map((item) => <li key={item.id}><b>{item.change_type}</b>{item.name}<small>{item.fields.join(", ") || "removed"}</small></li>)}</ul>
          <code title={designDiff.diff_digest}>diff {designDiff.diff_digest.slice(0, 16)}</code>
          <button disabled={reviewBusy} onClick={() => void reviewAction(() => onCreateContext(designDiff.diff_digest))}>{reviewBusy ? "Freezing context…" : "Use this design for implementation"}</button>
          <small>This freezes this exact revision and diff for the coding Agent. It does not start a scan after coding.</small>
        </div>}
      </> : <>
        <h3>Implementation context ready</h3>
        <p>The reviewed target graph remains an immutable design version. It was not merged into current truth.</p>
        {implementationExport && <code>{implementationExport.id}</code>}
        <small>The next scan happens only when you later ask to understand the system or begin another design.</small>
      </>}
    </section>
    {reviewProblem && <div className="login-error" role="alert">{reviewProblem}</div>}
    <section className="revision-audit"><span>Current revision</span><code>{revision.id}</code><small>{revision.created_by} · {revision.rationale}</small></section>
    {problem && <div className="login-error" role="alert">{problem}</div>}
  </aside>;
}

function newDesignId(prefix: "des-feature" | "des-resp" | "des-link" | "des-occ") {
  return `${prefix}-${crypto.randomUUID().replaceAll("-", "").slice(0, 20)}`;
}

function UaImplementationMap({ coordinate, session, focus, originSemanticId, onRenew, onBack }: {
  coordinate: ObservationCoordinate;
  session: UaViewerSession | null;
  focus: ImplementationRef | null;
  originSemanticId: string;
  onRenew: () => Promise<UaViewerSession | null>;
  onBack: (observedRevisionId: string, subjectId: string) => void;
}) {
  const iframe = useRef<HTMLIFrameElement | null>(null);
  const [ready, setReady] = useState(false);
  const [focusStatus, setFocusStatus] = useState<"waiting" | "focused" | "fallback" | "not_found">("waiting");
  const [subjects, setSubjects] = useState<UaSemanticSubject[]>([]);
  const revision = coordinate.observed_revision;

  useEffect(() => { setReady(false); setSubjects([]); setFocusStatus("waiting"); }, [session?.viewer_url]);

  useEffect(() => {
    if (!session) return;
    const receive = (event: MessageEvent) => {
      if (event.origin !== location.origin || event.source !== iframe.current?.contentWindow) return;
      const message = event.data as Record<string, unknown>;
      if (message.protocolVersion !== 1 || message.uaSnapshotId !== session?.ua_snapshot_id) return;
      if (message.type === "ua.cointent.ready") setReady(true);
      if (message.type === "ua.cointent.focus-result") {
        setFocusStatus(message.status as "focused" | "fallback" | "not_found");
      }
      if (message.type === "ua.cointent.node-selected" && typeof message.nodeId === "string") {
        fetchUaNodeSubjects(session.ua_snapshot_id, message.nodeId)
          .then((result) => setSubjects(result.subjects))
          .catch(() => setSubjects([]));
      }
    };
    addEventListener("message", receive);
    return () => removeEventListener("message", receive);
  }, [session?.ua_snapshot_id, iframe]);

  useEffect(() => {
    if (!ready || !focus?.preferred_focus_node_id || !iframe.current?.contentWindow) return;
    setFocusStatus("waiting");
    iframe.current.contentWindow.postMessage({
      type: "cointent.ua.focus-nodes",
      protocolVersion: 1,
      requestId: crypto.randomUUID(),
      uaSnapshotId: focus.ua_snapshot_id,
      primaryNodeId: focus.preferred_focus_node_id,
      nodeIds: focus.structural_ua_node_ids,
      lineRange: focus.line_range ?? undefined,
      openSource: true,
    }, location.origin);
  }, [ready, focus?.id, iframe]);

  useEffect(() => {
    if (!session) return;
    const delay = Math.max(1000, Date.parse(session.expires_at) - Date.now() - 30_000);
    const timer = window.setTimeout(() => { void onRenew(); }, delay);
    return () => window.clearTimeout(timer);
  }, [session?.expires_at]);

  if (!revision || !coordinate.ua_snapshot) return <main className="observation-empty"><section>
    <span className="empty-kicker">Implementation map unavailable</span><h1>Ask your Agent to update understanding.</h1>
    <p>The UA Dashboard opens only against a validated immutable code and graph coordinate.</p>
  </section></main>;

  return <main className="ua-map-shell">
    <header className="ua-coordinate-header">
      <div><span>Implementation map</span><strong>Official Understand Anything Dashboard</strong></div>
      <dl><div><dt>Code</dt><dd>{coordinate.code_snapshot?.revision.slice(0, 10)}</dd></div><div><dt>UA snapshot</dt><dd>{coordinate.ua_snapshot.id.slice(0, 18)}</dd></div><div><dt>Observation</dt><dd>{revision.id.slice(0, 18)}</dd></div></dl>
      {focus && <span className={`focus-result ${focusStatus}`}>{focusStatus === "waiting" ? "Locating implementation…" : focusStatus.replace("_", " ")}</span>}
    </header>
    <section className="ua-frame-region">
      {session ? <iframe ref={(node) => { iframe.current = node; }} src={session.viewer_url} title="Understand Anything implementation map" />
        : <div className="ua-loading"><IntentMark /><strong>Opening the pinned code map…</strong></div>}
      <aside className={`semantic-return ${subjects.length ? "open" : ""}`} aria-live="polite">
        <span>Selected implementation supports</span>
        {subjects.length ? subjects.map((item) => <button key={`${item.observed_revision_id}-${item.subject_id}`} onClick={() => onBack(item.observed_revision_id, item.subject_id)}>
          <small>{item.subject_kind.replace("_", " ")}</small><strong>{item.name}</strong><b>Back to system structure →</b>
        </button>) : <p>Select a mapped UA node to see its related system functions and Responsibilities.</p>}
        {!subjects.length && originSemanticId && <button onClick={() => onBack(revision.id, originSemanticId)}><strong>Return to originating Responsibility</strong><b>← System view</b></button>}
      </aside>
    </section>
  </main>;
}

function UnderstandingWorkspace({
  coordinate, selectedId, onSelect, onExpand, onOpenRevision, onOpenImplementation, expansionNotice, mobilePane,
}: {
  coordinate: ObservationCoordinate;
  selectedId: string;
  onSelect: (id: string) => void;
  onExpand: (id: string) => void;
  onOpenRevision: (revisionId: string, nodeId: string) => void;
  onOpenImplementation: (ref: ImplementationRef, subjectId: string) => void;
  expansionNotice: ExpansionNotice | null;
  mobilePane: "functions" | "structure" | "details";
}) {
  const revision = coordinate.observed_revision;
  if (!revision) return <main className="observation-empty">
    <section>
      <span className="empty-kicker">No verified current model</span>
      <h1>Generate the view from code.</h1>
      <p>Ask your connected Agent to update understanding. It will freeze the code coordinate, run native Understand Anything where the repository is available, and publish only after central validation. This page never accepts code or graph uploads, and a design draft is never shown here as current code.</p>
    </section>
  </main>;

  const byId = new Map(revision.responsibilities.map((item) => [item.id, item]));
  const selected = byId.get(selectedId) ?? revision.responsibilities[0];
  const focus = revision.responsibilities[0];
  const functions = revision.capabilities.length ? revision.capabilities : focus ? [{
    id: `focus-${revision.id}`,
    name: focus.name,
    description: "Focused structural refinement",
    responsibility_id: focus.id,
    evidence_count: revision.refinement?.evidence_bindings ?? 1,
  }] : [];
  const parentById = new Map<string, string>();
  revision.responsibilities.forEach((parent) => parent.workflow?.nodes.forEach((node) => parentById.set(node.responsibility_id, parent.id)));
  const children = (selected?.workflow?.nodes ?? []).map((node) => byId.get(node.responsibility_id)).filter(Boolean) as Responsibility[];
  const evidenceBySubject = new Map(revision.bindings.map((item) => [item.subject_id, item.evidence]));
  const selectedEvidence = selected ? evidenceBySubject.get(selected.id) ?? [] : [];
  const selectedRefs = selected
    ? (revision.implementation_refs ?? []).filter((item) => item.subject_id === selected.id)
    : [];
  const primaryRef = selectedRefs.find((item) => item.role === "primary") ?? selectedRefs[0];
  const combinedRef = primaryRef ? {
    ...primaryRef,
    structural_ua_node_ids: Array.from(new Set(selectedRefs.flatMap((item) => item.structural_ua_node_ids))),
  } : undefined;
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
      <div className="spec-tree">{functions.map((item) => <button key={item.id} className={`spec-row ${selected?.id === item.responsibility_id ? "selected" : ""}`} onClick={() => onSelect(item.responsibility_id)}>
        <span className="tree-mark">◆</span><span><strong>{item.name}</strong><small>{item.description}</small></span><em title={`${item.evidence_count} source bindings`}>{item.evidence_count}</em>
      </button>)}</div>
      <div className="observation-proof"><span>Immutable coordinate</span><code>{revision.id}</code><small>{revision.responsibilities.length} verified responsibilities · {revision.diagnostics.length} diagnostics</small></div>
    </aside>

    <section className="logic-pane observed-logic">
      <div className="logic-head">
        <nav className="breadcrumbs" aria-label="Observed structure path">{lineage.map((item, index) => <span key={item.id}>{index > 0 && <i>›</i>}<button onClick={() => onSelect(item.id)}>{item.name}</button></span>)}</nav>
        <div className="logic-title"><div><span className="eyebrow">Implemented responsibility</span><h1>{selected?.name ?? "No verified structure"}</h1></div><div className="observed-title-actions">
          <span className="read-only-seal">Read only<br /><b>Code-derived</b></span>
          <button className="refine-action" disabled={!selected || expansionNotice?.tone === "working"} onClick={() => selected && onExpand(selected.id)}>
            <span aria-hidden="true">⌄</span>{expansionNotice?.tone === "working" ? "Reading evidence…" : "Show one level deeper"}
          </button>
        </div></div>
        <p className="responsibility-description">{selected?.description}</p>
        <div className="scope-note"><span>Inside this node</span><strong>{children.length} verified child nodes</strong><small>Every visible node resolves to captured source.</small></div>
        {revision.refinement && <div className="refinement-rail">
          <span><i />Focused refinement</span>
          <strong>+{revision.refinement.added_responsibilities} structural nodes from the same UA snapshot</strong>
          <small>Depth {revision.refinement.max_depth_reached}/{revision.refinement.requested_depth}{revision.refinement.truncated ? " · bounded at 64 nodes" : ""}</small>
          {revision.parent_revision_id && <button onClick={() => onOpenRevision(revision.parent_revision_id!, revision.refinement_of_node_id ?? "")}>← Broader view</button>}
        </div>}
        {expansionNotice && expansionNotice.nodeId === selected?.id && <div className={`expansion-notice ${expansionNotice.tone}`} role="status">{expansionNotice.message}</div>}
      </div>
      <div className="observed-flow">
        <div className="workflow-toolbar"><div><span className="eyebrow">Current structure</span><strong>{children.length ? "Select a node to inspect or descend" : "Evidence-backed leaf"}</strong></div><div className="legend"><span><i className="line normal" />{revision.refinement ? "UA structure" : "UA order"}</span></div></div>
        {children.length ? <div className="observed-node-row">{children.map((node, index) => <div className="observed-node-wrap" key={node.id}>
          {index > 0 && <span className={`observed-connector ${revision.refinement ? "structural" : ""}`} aria-hidden="true">{revision.refinement ? "·" : "→"}</span>}
          <button className="observed-node-card" onClick={() => onSelect(node.id)}><span>{node.source_ids[0]?.split(":", 1)[0] ?? "responsibility"}</span><strong>{node.name}</strong><p>{node.description}</p><small>{evidenceBySubject.get(node.id)?.length ?? 0} source binding{(evidenceBySubject.get(node.id)?.length ?? 0) === 1 ? "" : "s"} <b>→</b></small></button>
        </div>)}</div> : <div className="leaf-stage"><div className="leaf-symbol"><span /><i /><b /></div><span className="eyebrow">Verified leaf</span><h2>{selected?.name}</h2><p>This is the deepest imported semantic level. Use its source bindings to inspect the implementation.</p></div>}
      </div>
    </section>

    <aside className="inspector observed-inspector">
      <div className="inspector-heading"><span className="eyebrow">Why this is shown</span><h2>Source evidence</h2><code>{selected?.source_ids[0]}</code></div>
      <section className="implementation-ref-block"><div className="section-title"><div><span className="eyebrow">Code map bridge</span><h3>Implementation references</h3></div><strong>{selectedRefs.length}</strong></div>
        {selectedRefs.length ? selectedRefs.map((item) => <article className="implementation-ref" key={item.id}>
          <div><span className={item.role}>{item.role}</span><small>{item.resolution.replaceAll("_", " ")}</small></div>
          <strong>{item.symbol ?? item.file_path.split("/").at(-1)}</strong>
          <code>{item.file_path}{item.line_range ? `:${item.line_range[0]}–${item.line_range[1]}` : ""}</code>
          <button disabled={!item.preferred_focus_node_id} onClick={() => onOpenImplementation(item, selected!.id)}>Open in code map <b>→</b></button>
        </article>) : <p className="empty">No resolvable UA node exists for this semantic item.</p>}
        {combinedRef && selectedRefs.length > 1 && <button className="show-all-refs" onClick={() => onOpenImplementation(combinedRef, selected!.id)}>Show all in code map <b>→</b></button>}
      </section>
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

function WorkflowCanvas({ workflow, responsibilities, activePathIds, onEnter, allowLeafSelection = false }: {
  workflow: Workflow;
  responsibilities: Map<string, Responsibility>;
  activePathIds: Set<string>;
  onEnter: (id: string) => void;
  allowLeafSelection?: boolean;
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
            <span className="enter-cue">{recursive ? "Return to this level" : canDescend ? "Open workflow" : allowLeafSelection ? "Select responsibility" : "Leaf responsibility"}<b>{canDescend || recursive || allowLeafSelection ? "→" : "◆"}</b></span>
          </>;
          return canDescend || recursive || allowLeafSelection
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
