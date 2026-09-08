"""Curated English design baseline for the Idea Factory experiment."""

from __future__ import annotations

from .models import (
    FunctionRoleLink,
    ProductFunction,
    ProjectModel,
    Responsibility,
    RoleObject,
    RoleRelation,
    TraceLink,
)
from .scanner import RepositorySnapshot


def idea_factory_model(snapshot: RepositorySnapshot) -> ProjectModel:
    """Build a reviewable function catalog and responsibility forest from evidence."""
    evidence = [f"scan:{snapshot.id}"]
    functions = [
        _function("function.idea-screening", "Idea discovery and screening", "Turn source signals into screened startup ideas and bounded experiments.", None, evidence, priority="critical"),
        _function("function.signal-intelligence", "Signal intelligence", "Acquire and qualify market, persona, and problem signals.", "function.idea-screening", evidence),
        _function("function.signal-intake", "Collect source signals", "Collect multiple signal classes through replaceable source adapters.", "function.signal-intelligence", evidence),
        _function("function.signal-qualification", "Qualify source signals", "Normalize, deduplicate, triage, and corroborate raw signals.", "function.signal-intelligence", evidence),
        _function("function.candidate-development", "Candidate development", "Generate diverse candidates and make them comparable.", "function.idea-screening", evidence),
        _function("function.candidate-generation", "Generate idea candidates", "Create multiple startup candidates from qualified signals.", "function.candidate-development", evidence),
        _function("function.candidate-ranking", "Rank idea candidates", "Rank candidates with comparable, time-sensitive factors.", "function.candidate-development", evidence),
        _function("function.candidate-evaluation", "Candidate evaluation", "Reject weak candidates and select defensible survivors.", "function.idea-screening", evidence),
        _function("function.deterministic-gating", "Apply deterministic gates", "Reject candidates that fail cheap, explicit criteria.", "function.candidate-evaluation", evidence),
        _function("function.evidence-review", "Review supporting evidence", "Assess whether a candidate has sufficient grounded evidence.", "function.candidate-evaluation", evidence),
        _function("function.persona-pressure", "Run persona-pressure evaluation", "Test candidates against founder constraints and representative personas.", "function.candidate-evaluation", evidence),
        _function("function.portfolio-selection", "Select a candidate portfolio", "Choose a balanced portfolio from surviving candidates.", "function.candidate-evaluation", evidence),
        _function("function.next-experiment", "Define the next experiment", "Attach the riskiest assumption and a cheap bounded test.", "function.candidate-evaluation", evidence),
        _function("function.learning", "Outcome learning", "Use real outcomes to improve later scoring and judgment.", "function.idea-screening", evidence),
        _function("function.outcome-capture", "Capture decisions and outcomes", "Preserve verdicts, feedback, outcomes, and evidence.", "function.learning", evidence),
        _function("function.calibration", "Calibrate evaluation", "Suggest factor and threshold changes from prediction error.", "function.learning", evidence),
        _function("function.operations", "Operation and integration", "Operate the pipeline and integrate selected external workflows.", "function.idea-screening", evidence),
        _function("function.operator-control", "Operate the pipeline", "Inspect pipeline state, run workflows, and record human decisions.", "function.operations", evidence),
        _function("function.workflow-mirroring", "Mirror external workflows", "Keep selected Dify workflows aligned with the core pipeline contract.", "function.operations", evidence),
    ]
    roles = [
        _role("role.signal-intelligence", "Signal Intelligence", "Own the conversion of noisy sources into qualified signals.", None, evidence, inputs=["Source signals"], outputs=["Qualified signals"], knowledge=["Source provenance", "Signal quality"]),
        _role("role.signal-acquisition", "Signal Acquisition", "Collect signals through isolated and replaceable adapters.", "role.signal-intelligence", evidence, outputs=["Source records"]),
        _role("role.signal-qualification", "Signal Qualification", "Normalize, reduce, and corroborate collected signals.", "role.signal-intelligence", evidence, inputs=["Source records"], outputs=["Qualified signals"]),
        _role("role.candidate-generation", "Candidate Generation", "Own the creation and comparable ranking of idea candidates.", None, evidence, inputs=["Qualified signals"], outputs=["Ranked candidates"]),
        _role("role.idea-synthesis", "Idea Synthesis", "Generate diverse candidate ideas from qualified evidence.", "role.candidate-generation", evidence, inputs=["Qualified signals"], outputs=["Idea candidates"]),
        _role("role.candidate-ranking", "Candidate Ranking", "Score and order candidates with time-sensitive factors.", "role.candidate-generation", evidence, inputs=["Idea candidates"], outputs=["Ranked candidates"], knowledge=["Factor scores"]),
        _role("role.evaluation-gate", "Evaluation Gate", "Own efficient rejection and defensible selection decisions.", None, evidence, inputs=["Ranked candidates"], outputs=["Verdicts", "Decision memos", "Next experiments"], knowledge=["Evaluation verdicts", "Rejection reasons"]),
        _role("role.hard-gate", "Hard Gate", "Apply cheap deterministic rejection criteria before semantic judgment.", "role.evaluation-gate", evidence, inputs=["Ranked candidates"], outputs=["Gate survivors"], constraints=["Run before semantic evaluation"]),
        _role("role.semantic-evaluation", "Semantic Evaluation", "Review evidence and pressure-test survivors against founder and persona fit.", "role.evaluation-gate", evidence, inputs=["Gate survivors", "Founder constraints", "Representative personas"], outputs=["Fit-pressure evidence"], constraints=["Every judgment must cite evidence"]),
        _role("role.portfolio-selection", "Portfolio Selection", "Select survivors and attach bounded next experiments.", "role.evaluation-gate", evidence, inputs=["Evaluated survivors"], outputs=["Selected portfolio", "Next experiments"]),
        _role("role.learning-loop", "Learning Loop", "Own outcome capture and evaluation calibration.", None, evidence, inputs=["Verdicts", "Observed outcomes"], outputs=["Calibration evidence"]),
        _role("role.outcome-ledger", "Outcome Ledger", "Preserve decisions, feedback, and observed outcomes.", "role.learning-loop", evidence, inputs=["Human decisions", "Outcomes"], outputs=["Auditable outcome history"], knowledge=["Decision history", "Outcome history"]),
        _role("role.calibration", "Calibration", "Derive lessons and suggest scoring changes from prediction error.", "role.learning-loop", evidence, inputs=["Auditable outcome history"], outputs=["Calibration proposals"]),
        _role("role.domain-contract", "Shared Domain Contract", "Keep candidate, evidence, factor, persona, state, and LLM semantics consistent.", None, evidence, outputs=["Stable shared semantics"], knowledge=["Domain vocabulary", "Model contracts"]),
        _role("role.operator-surface", "Operator Surface", "Provide authenticated human inspection and control of the pipeline.", None, evidence, inputs=["Pipeline state"], outputs=["Human decisions"]),
        _role("role.workflow-mirror", "Workflow Mirror", "Mirror selected behavior into externally operated Dify workflows.", None, evidence, inputs=["Core workflow contracts"], outputs=["Validated external workflows"], constraints=["Do not redefine the core contract"]),
    ]
    responsibilities = [
        _responsibility("resp.signal-acquisition", "role.signal-acquisition", "Collect supported signal classes through replaceable adapters.", ["function.signal-intake"], evidence),
        _responsibility("resp.signal-qualification", "role.signal-qualification", "Normalize, deduplicate, triage, and corroborate source records.", ["function.signal-qualification"], evidence),
        _responsibility("resp.idea-synthesis", "role.idea-synthesis", "Generate multiple candidates from qualified signals.", ["function.candidate-generation"], evidence),
        _responsibility("resp.candidate-ranking", "role.candidate-ranking", "Compute comparable, time-decayed factor scores and rank candidates.", ["function.candidate-ranking"], evidence),
        _responsibility("resp.hard-gate", "role.hard-gate", "Apply explicit deterministic rejection criteria.", ["function.deterministic-gating"], evidence),
        _responsibility("resp.evidence-review", "role.semantic-evaluation", "Assess evidence quality before expensive judgment.", ["function.evidence-review"], evidence),
        _responsibility("resp.persona-pressure", "role.semantic-evaluation", "Pressure-test survivors against founder constraints and representative personas.", ["function.persona-pressure"], evidence),
        _responsibility("resp.portfolio-selection", "role.portfolio-selection", "Select a balanced portfolio of defensible survivors.", ["function.portfolio-selection"], evidence),
        _responsibility("resp.next-experiment", "role.portfolio-selection", "Attach the riskiest assumption and a bounded next experiment.", ["function.next-experiment"], evidence),
        _responsibility("resp.outcome-capture", "role.outcome-ledger", "Record verdicts, feedback, and observed outcomes with provenance.", ["function.outcome-capture"], evidence),
        _responsibility("resp.calibration", "role.calibration", "Suggest factor and threshold changes from observed prediction error.", ["function.calibration"], evidence),
        _responsibility("resp.domain-contract", "role.domain-contract", "Define shared domain and LLM boundary contracts.", ["function.idea-screening"], evidence),
        _responsibility("resp.operator-control", "role.operator-surface", "Present pipeline state and authenticate human control.", ["function.operator-control"], evidence),
        _responsibility("resp.workflow-mirroring", "role.workflow-mirror", "Validate external workflow mirrors against the core contract.", ["function.workflow-mirroring"], evidence),
    ]
    relations = [
        RoleRelation(id="relation.signals-to-candidates", source_role_id="role.signal-intelligence", target_role_id="role.candidate-generation", kind="exchanges_with", label="qualified signals"),
        RoleRelation(id="relation.candidates-to-evaluation", source_role_id="role.candidate-generation", target_role_id="role.evaluation-gate", kind="exchanges_with", label="ranked candidates"),
        RoleRelation(id="relation.evaluation-to-learning", source_role_id="role.evaluation-gate", target_role_id="role.learning-loop", kind="exchanges_with", label="verdicts and outcomes"),
        RoleRelation(id="relation.contract-governs-generation", source_role_id="role.domain-contract", target_role_id="role.candidate-generation", kind="governs", label="models and factors"),
        RoleRelation(id="relation.contract-governs-evaluation", source_role_id="role.domain-contract", target_role_id="role.evaluation-gate", kind="governs", label="evidence and personas"),
        RoleRelation(id="relation.operator-to-evaluation", source_role_id="role.operator-surface", target_role_id="role.evaluation-gate", kind="collaborates", label="review and control"),
        RoleRelation(id="relation.mirror-to-contract", source_role_id="role.workflow-mirror", target_role_id="role.domain-contract", kind="depends_on", label="core contract"),
    ]
    links = [
        _function_link(item.id.replace("function.", "function-role."), item.id, role_id, "owns", evidence)
        for item, role_id in (
            (_find(functions, "function.signal-intake"), "role.signal-acquisition"),
            (_find(functions, "function.signal-qualification"), "role.signal-qualification"),
            (_find(functions, "function.candidate-generation"), "role.idea-synthesis"),
            (_find(functions, "function.candidate-ranking"), "role.candidate-ranking"),
            (_find(functions, "function.deterministic-gating"), "role.hard-gate"),
            (_find(functions, "function.evidence-review"), "role.semantic-evaluation"),
            (_find(functions, "function.persona-pressure"), "role.semantic-evaluation"),
            (_find(functions, "function.portfolio-selection"), "role.portfolio-selection"),
            (_find(functions, "function.next-experiment"), "role.portfolio-selection"),
            (_find(functions, "function.outcome-capture"), "role.outcome-ledger"),
            (_find(functions, "function.calibration"), "role.calibration"),
            (_find(functions, "function.operator-control"), "role.operator-surface"),
            (_find(functions, "function.workflow-mirroring"), "role.workflow-mirror"),
        )
    ]
    links.extend([
        _function_link("function-role.idea-contract", "function.idea-screening", "role.domain-contract", "governs", evidence),
        _function_link("function-role.persona-contract", "function.persona-pressure", "role.domain-contract", "governs", evidence),
        _function_link("function-role.operator-evaluation", "function.candidate-evaluation", "role.operator-surface", "contributes", evidence),
    ])
    traces = [
        _trace("signal-acquisition", "role.signal-acquisition", "src/idea_gen/sources", snapshot),
        _trace("signal-qualification", "role.signal-qualification", "src/idea_gen/normalize.py", snapshot),
        _trace("idea-synthesis", "role.idea-synthesis", "src/idea_gen/generate.py", snapshot),
        _trace("candidate-ranking", "role.candidate-ranking", "src/idea_gen/ranks.py", snapshot),
        _trace("hard-gate", "role.hard-gate", "src/idea_eval/evaluate.py", snapshot),
        _trace("semantic-evaluation", "role.semantic-evaluation", "src/idea_eval/persona_pressure.py", snapshot),
        _trace("portfolio-selection", "role.portfolio-selection", "src/idea_eval/pipeline.py", snapshot),
        _trace("outcome-ledger", "role.outcome-ledger", "src/idea_core/ledger.py", snapshot, kind="stores"),
        _trace("calibration", "role.calibration", "src/idea_eval/calibrate.py", snapshot),
        _trace("domain-contract", "role.domain-contract", "src/idea_core", snapshot),
        _trace("operator-server", "role.operator-surface", "studio/server", snapshot, kind="presents"),
        _trace("operator-web", "role.operator-surface", "studio/web", snapshot, kind="presents"),
        _trace("workflow-mirror", "role.workflow-mirror", "dify", snapshot),
    ]
    return ProjectModel(
        project_id=snapshot.project_id,
        name="Idea Factory",
        summary="A living product-function catalog and responsibility model for screening startup ideas.",
        status="baseline",
        product_functions=functions,
        role_objects=roles,
        responsibilities=responsibilities,
        role_relations=relations,
        function_role_links=links,
        trace_links=traces,
    )


def _function(identifier: str, name: str, description: str, parent_id: str | None, evidence: list[str], *, priority: str = "unset") -> ProductFunction:
    return ProductFunction(id=identifier, name=name, description=description, parent_id=parent_id, priority=priority, source_ids=evidence)


def _role(identifier: str, name: str, purpose: str, parent_id: str | None, evidence: list[str], *, inputs: list[str] | None = None, outputs: list[str] | None = None, constraints: list[str] | None = None, knowledge: list[str] | None = None) -> RoleObject:
    return RoleObject(id=identifier, name=name, purpose=purpose, parent_id=parent_id, inputs=inputs or [], outputs=outputs or [], constraints=constraints or [], owns_knowledge=knowledge or [], source_ids=evidence)


def _responsibility(identifier: str, role_id: str, statement: str, function_ids: list[str], evidence: list[str]) -> Responsibility:
    return Responsibility(id=identifier, role_id=role_id, statement=statement, function_ids=function_ids, source_ids=evidence)


def _function_link(identifier: str, function_id: str, role_id: str, kind: str, evidence: list[str]) -> FunctionRoleLink:
    return FunctionRoleLink(id=identifier, function_id=function_id, role_id=role_id, kind=kind, confidence=0.9, evidence="Curated from the repository snapshot and responsibility review.", source_ids=evidence)


def _find(functions: list[ProductFunction], identifier: str) -> ProductFunction:
    return next(item for item in functions if item.id == identifier)


def _trace(suffix: str, role_id: str, artifact_path: str, snapshot: RepositorySnapshot, *, kind: str = "realizes") -> TraceLink:
    known = {item.path for item in snapshot.artifacts}
    exists = artifact_path in known or any(path.startswith(f"{artifact_path.rstrip('/')}/") for path in known)
    return TraceLink(
        id=f"trace.{suffix}", role_id=role_id, artifact_path=artifact_path, kind=kind,
        confidence=0.96 if exists else 0.55, origin="agent",
        evidence=f"Derived from {snapshot.id}; path {'observed' if exists else 'not observed'} in the scan.",
    )
