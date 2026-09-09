import { useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  applyTargetDesignOperations, approveTargetDesignReview, createTargetDesignWorkspace,
  createVerificationReport, decideVerification, exportImplementationBundle, fetchObservation, fetchSession, fetchTargetDesignWorkspace,
  listProjects, loadWorkspace, login, logout, requestObservationExpansion, submitTargetDesignReview,
} from "./api";
import type {
  AlignmentBaseline, ChangeSet, DesignVersion, Finding, ImplementationLink, ModelResponse,
  ImplementationChangeBundle, ObservationCoordinate, OverviewResponse, Project, Proposal, Responsibility, SpecificationItem,
  SpecificationResponsibilityLink, TargetDesignOperation, TargetDesignView, Workflow,
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
    setTargetDesign(undefined);
    Promise.all([
      loadWorkspace(projectId, designVersion),
      fetchObservation(projectId),
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

  async function startTargetDesign() {
    const observed = observation?.observed_revision;
    if (!observed) return;
    try {
      const project = projects.find((item) => item.id === projectId);
      await createTargetDesignWorkspace(
        projectId,
        observed.id,
        `${project?.name ?? projectId} target design`,
        "Create an independent target from the selected code-derived baseline.",
      );
      setTargetDesign(await fetchTargetDesignWorkspace(projectId));
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

  async function submitTargetReview(criteria: string[]) {
    if (!targetDesign) return;
    await submitTargetDesignReview(targetDesign.workspace.id, criteria);
    await refreshTargetDesign();
  }

  async function approveTargetReview(reviewId: string) {
    await approveTargetDesignReview(reviewId);
    await refreshTargetDesign();
  }

  async function exportTargetBundle(): Promise<ImplementationChangeBundle | null> {
    if (!targetDesign) return null;
    const bundle = await exportImplementationBundle(targetDesign.workspace.id);
    const blob = new Blob([`${JSON.stringify(bundle, null, 2)}\n`], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${bundle.id}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    await refreshTargetDesign();
    return bundle;
  }

  async function verifyTargetImplementation() {
    if (!targetDesign?.implementation_export) return;
    const latest = await fetchObservation(projectId);
    const observed = latest.observed_revision;
    if (!observed || observed.code_snapshot_id === targetDesign.implementation_export.base_code_snapshot_id) {
      throw new Error("No post-implementation observation exists yet. Import a new full snapshot and UA map first.");
    }
    if (targetDesign.verification_report?.observed_revision_id === observed.id) {
      throw new Error("This observation was already reviewed. Import a later full snapshot and UA map first.");
    }
    await createVerificationReport(targetDesign.workspace.id, observed.id);
    await refreshTargetDesign();
  }

  async function decideTargetVerification(
    reportId: string, decision: "converged" | "needs_revision", notes: string,
  ) {
    await decideVerification(reportId, decision, notes);
    await refreshTargetDesign();
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
        <div><span>Observed baseline</span><strong>{targetDesign?.workspace.base_observed_revision_id.slice(0, 18) ?? "Not created"}</strong></div>
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
        <span>Intent → implementation diff</span><strong>Design future</strong><small>Editable target</small>
      </button>
    </nav>
    <nav className={`mobile-pane-tabs ${mode}`} aria-label="Workspace area">
      <button className={mobilePane === "functions" ? "active" : ""} onClick={() => setMobilePane("functions")}>{mode === "understand" ? "Functions" : "Expected"}</button>
      <button className={mobilePane === "structure" ? "active" : ""} onClick={() => setMobilePane("structure")}>Structure</button>
      <button className={mobilePane === "details" ? "active" : ""} onClick={() => setMobilePane("details")}>{mode === "understand" ? "Evidence" : "Details"}</button>
    </nav>

    {mode === "understand" ? <UnderstandingWorkspace
      coordinate={observation}
      selectedId={selectedObserved}
      onSelect={(id) => { setSelectedObserved(id); setExpansionNotice(null); setMobilePane("structure"); }}
      onExpand={(id) => void expandObservation(id)}
      onOpenRevision={(revisionId, nodeId) => void openObservedRevision(revisionId, nodeId)}
      expansionNotice={expansionNotice}
      mobilePane={mobilePane}
    /> : targetDesign
      ? <TargetDesignWorkspace
          view={targetDesign}
          mobilePane={mobilePane}
          onApply={(operations, rationale) => applyTargetOperations(operations, rationale)}
          onOpenRevision={(revisionId) => void openTargetRevision(revisionId)}
          onSubmitReview={submitTargetReview}
          onApproveReview={approveTargetReview}
          onExport={exportTargetBundle}
          onVerify={verifyTargetImplementation}
          onDecideVerification={decideTargetVerification}
          onViewBaseline={(revisionId, nodeId) => { chooseMode("understand"); void openObservedRevision(revisionId, nodeId); }}
        />
      : <TargetDesignEmpty
          hasObservation={Boolean(observation.observed_revision)}
          onCreate={() => void startTargetDesign()}
        />}
  </div>;
}

function TargetDesignEmpty({ hasObservation, onCreate }: { hasObservation: boolean; onCreate: () => void }) {
  return <main className="target-design-empty">
    <section>
      <span className="empty-kicker">Independent target space</span>
      <h1>Design what should exist next.</h1>
      <p>The target starts as a value clone of one named current-system revision. From then on it advances through its own immutable <code>des-*</code> revisions; changing it never changes the code-derived view.</p>
      <button disabled={!hasObservation} onClick={onCreate}>{hasObservation ? "Create target from current structure" : "Generate a current structure first"}<b>→</b></button>
    </section>
  </main>;
}

function TargetDesignWorkspace({
  view, mobilePane, onApply, onOpenRevision, onSubmitReview, onApproveReview, onExport, onViewBaseline,
  onVerify, onDecideVerification,
}: {
  view: TargetDesignView;
  mobilePane: "functions" | "structure" | "details";
  onApply: (operations: TargetDesignOperation[], rationale: string) => Promise<void>;
  onOpenRevision: (revisionId: string) => void;
  onSubmitReview: (criteria: string[]) => Promise<void>;
  onApproveReview: (reviewId: string) => Promise<void>;
  onExport: () => Promise<ImplementationChangeBundle | null>;
  onVerify: () => Promise<void>;
  onDecideVerification: (
    reportId: string, decision: "converged" | "needs_revision", notes: string,
  ) => Promise<void>;
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
      <div className="design-provenance"><span>Separate truth coordinate</span><label>Revision<select value={revision.id} onChange={(event) => onOpenRevision(event.target.value)}>{view.revisions.map((item, index) => <option value={item.id} key={item.id}>{index === 0 ? "Current · " : "History · "}{item.id.slice(0, 16)}</option>)}</select></label><small>{revision.created_by} · {revision.rationale}</small></div>
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
      review={view.review}
      workspaceStatus={view.workspace.status}
      implementationExport={view.implementation_export}
      verificationReport={view.verification_report}
      verificationDecision={view.verification_decision}
      onSubmitReview={onSubmitReview}
      onApproveReview={onApproveReview}
      onExport={onExport}
      onVerify={onVerify}
      onDecideVerification={onDecideVerification}
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
  revision, responsibility, baselineObservedId, busy, editable, problem, review, workspaceStatus,
  implementationExport, verificationReport, verificationDecision, onApply, onSubmitReview,
  onApproveReview, onExport, onVerify, onDecideVerification, onViewBaseline,
}: {
  revision: TargetDesignView["revision"];
  responsibility?: Responsibility;
  baselineObservedId?: string;
  busy: boolean;
  editable: boolean;
  problem: string;
  review: TargetDesignView["review"];
  workspaceStatus: string;
  implementationExport: TargetDesignView["implementation_export"];
  verificationReport: TargetDesignView["verification_report"];
  verificationDecision: TargetDesignView["verification_decision"];
  onApply: (operations: TargetDesignOperation[], rationale: string) => Promise<void>;
  onSubmitReview: (criteria: string[]) => Promise<void>;
  onApproveReview: (reviewId: string) => Promise<void>;
  onExport: () => Promise<ImplementationChangeBundle | null>;
  onVerify: () => Promise<void>;
  onDecideVerification: (
    reportId: string, decision: "converged" | "needs_revision", notes: string,
  ) => Promise<void>;
  onViewBaseline: (observedId: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [childName, setChildName] = useState("");
  const [childDescription, setChildDescription] = useState("");
  const [criterion, setCriterion] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewProblem, setReviewProblem] = useState("");
  const [verificationNotes, setVerificationNotes] = useState("");
  useEffect(() => { setName(responsibility?.name ?? ""); setDescription(responsibility?.description ?? ""); }, [responsibility?.id, responsibility?.name, responsibility?.description]);
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
      <span>Human review gate</span>
      {workspaceStatus === "draft" && <>
        <h3>Define success before approval</h3>
        <p>The semantic diff is calculated by the server. Add a behavior that the implementation can prove.</p>
        <label>Acceptance criterion<textarea value={criterion} onChange={(event) => setCriterion(event.target.value)} placeholder="A user can…" /></label>
        <button disabled={reviewBusy || !editable || !criterion.trim()} onClick={() => void reviewAction(() => onSubmitReview([criterion.trim()]))}>{reviewBusy ? "Calculating diff…" : "Submit target for review"}</button>
      </>}
      {review && workspaceStatus === "in_review" && <>
        <h3>{review.changes.length} semantic changes awaiting approval</h3>
        <ul>{review.changes.slice(0, 6).map((item) => <li key={item.id}><b>{item.change_type}</b>{item.name}<small>{item.fields.join(", ") || "removed"}</small></li>)}</ul>
        <p>{review.acceptance_criteria[0]?.statement}</p>
        <button disabled={reviewBusy} onClick={() => void reviewAction(() => onApproveReview(review.id))}>{reviewBusy ? "Recording approval…" : "Approve implementation change"}</button>
      </>}
      {review && ["approved", "exported", "verifying", "converged", "needs_revision"].includes(workspaceStatus) && <>
        <h3>{workspaceStatus === "exported" ? "Implementation bundle ready" : workspaceStatus === "approved" ? "Target approved" : "Approved implementation contract"}</h3>
        <p>{review.changes.length} semantic changes · {review.acceptance_criteria.length} acceptance checks.</p>
        {implementationExport && <code>{implementationExport.id}</code>}
        {!["verifying", "converged", "needs_revision"].includes(workspaceStatus) && <button disabled={reviewBusy} onClick={() => void reviewAction(onExport)}>{reviewBusy ? "Building bundle…" : implementationExport ? "Download bundle again" : "Export for coding Agent"}</button>}
      </>}
    </section>
    {implementationExport && <section className="verification-card">
      <span>Implementation verification</span>
      {workspaceStatus === "exported" && !verificationReport && <>
        <h3>Compare the implementation</h3>
        <p>Import a later full code snapshot and Understand Anything map, then compare that observed truth with the approved target.</p>
        <button disabled={reviewBusy} onClick={() => void reviewAction(onVerify)}>{reviewBusy ? "Reading latest observation…" : "Verify latest observed revision"}</button>
      </>}
      {verificationReport && !verificationDecision && <>
        <h3>Evidence comparison awaiting you</h3>
        {review && <div className="verification-criteria"><span>Acceptance checks</span>{review.acceptance_criteria.map((item) => <p key={item.id}>{item.statement}</p>)}</div>}
        <div className="verification-summary">
          {(["matched", "missing", "unexpected", "ambiguous", "stale"] as const).map((status) => <div className={status} key={status}><strong>{verificationReport.summary[status] ?? 0}</strong><span>{status}</span></div>)}
        </div>
        <div className="verification-claims">{verificationReport.claims.slice(0, 8).map((claim) => <article key={claim.id} className={claim.status}>
          <span>{claim.status} · {claim.kind.replace("_", " ")}</span><strong>{claim.name}</strong><p>{claim.explanation}</p>
        </article>)}</div>
        <label>Human conclusion<textarea value={verificationNotes} onChange={(event) => setVerificationNotes(event.target.value)} placeholder="What was verified, and what should happen next?" /></label>
        <div className="verification-actions">
          <button disabled={reviewBusy || !verificationNotes.trim()} onClick={() => void reviewAction(() => onDecideVerification(verificationReport.id, "needs_revision", verificationNotes))}>Needs revision</button>
          <button disabled={reviewBusy || !verificationNotes.trim() || (["missing", "ambiguous", "stale"] as const).some((status) => (verificationReport.summary[status] ?? 0) > 0)} onClick={() => void reviewAction(() => onDecideVerification(verificationReport.id, "converged", verificationNotes))}>Accept as converged</button>
        </div>
      </>}
      {verificationReport && verificationDecision && <>
        <h3>{verificationDecision.decision === "converged" ? "Implementation accepted" : "Revision requested"}</h3>
        <p>{verificationDecision.notes}</p>
        <code>{verificationReport.observed_revision_id}</code>
        <small>{verificationDecision.actor} · {new Date(verificationDecision.decided_at).toLocaleString()}</small>
        {verificationDecision.decision === "needs_revision" && <button disabled={reviewBusy} onClick={() => void reviewAction(onVerify)}>{reviewBusy ? "Reading latest observation…" : "Verify another observed revision"}</button>}
      </>}
    </section>}
    {reviewProblem && <div className="login-error" role="alert">{reviewProblem}</div>}
    <section className="revision-audit"><span>Current revision</span><code>{revision.id}</code><small>{revision.created_by} · {revision.rationale}</small></section>
    {problem && <div className="login-error" role="alert">{problem}</div>}
  </aside>;
}

function newDesignId(prefix: "des-feature" | "des-resp" | "des-link" | "des-occ") {
  return `${prefix}-${crypto.randomUUID().replaceAll("-", "").slice(0, 20)}`;
}

function UnderstandingWorkspace({
  coordinate, selectedId, onSelect, onExpand, onOpenRevision, expansionNotice, mobilePane,
}: {
  coordinate: ObservationCoordinate;
  selectedId: string;
  onSelect: (id: string) => void;
  onExpand: (id: string) => void;
  onOpenRevision: (revisionId: string, nodeId: string) => void;
  expansionNotice: ExpansionNotice | null;
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
