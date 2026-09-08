"""Curated experiment baselines built from scanner evidence."""

from __future__ import annotations

from .models import Goal, ProjectModel, Relation, Responsibility, RoleRecord, TraceLink
from .scanner import RepositorySnapshot


def idea_factory_model(snapshot: RepositorySnapshot) -> ProjectModel:
    """Return the first agent-produced responsibility model for Idea Factory.

    The model is intentionally curated rather than claimed as deterministic truth.
    Its trace links are grounded in the supplied scan and remain reviewable.
    """

    evidence = [f"scan:{snapshot.id}"]
    goals = [
        Goal(id="goal.screen-ideas", title="Produce screened startup ideas",
             description="Turn multiple signal sources into a daily set of startup ideas with verdicts and cheap next tests.",
             source_ids=evidence),
        Goal(id="goal.cost-gradient", title="Spend judgment cost down the funnel",
             description="Use cheap deterministic filtering early and reserve expensive semantic judgment for survivors.",
             parent_id="goal.screen-ideas", source_ids=evidence),
        Goal(id="goal.explainability", title="Keep every decision explainable",
             description="Preserve evidence, scores, verdicts, and feedback so a result can be audited and improved.",
             parent_id="goal.screen-ideas", source_ids=evidence),
    ]
    roles = [
        RoleRecord(id="role.idea-factory", name="Idea Factory", parent_id=None,
                   purpose="Own the end-to-end conversion of signals into screened, testable startup ideas.", source_ids=evidence),
        RoleRecord(id="role.signal-intelligence", name="Signal Intelligence", parent_id="role.idea-factory",
                   purpose="Acquire, normalize, corroborate, and reduce noisy source signals.", source_ids=evidence),
        RoleRecord(id="role.candidate-generation", name="Candidate Generation", parent_id="role.idea-factory",
                   purpose="Generate diverse idea candidates and rank them using time-sensitive factors.", source_ids=evidence),
        RoleRecord(id="role.evaluation-gate", name="Evaluation Gate", parent_id="role.idea-factory",
                   purpose="Reject weak candidates efficiently and produce grounded verdicts and next tests.", source_ids=evidence),
        RoleRecord(id="role.learning-loop", name="Learning Loop", parent_id="role.idea-factory",
                   purpose="Capture outcomes and feedback to calibrate future scoring and decisions.", source_ids=evidence),
        RoleRecord(id="role.domain-contract", name="Shared Domain Contract", parent_id="role.idea-factory",
                   purpose="Keep models, factors, LLM boundaries, state, and evidence semantics consistent across the system.", source_ids=evidence),
        RoleRecord(id="role.operator-surface", name="Operator Surface", parent_id="role.idea-factory",
                   purpose="Let the founder inspect the funnel, run it, and record decisions and outcomes.", source_ids=evidence),
        RoleRecord(id="role.workflow-mirror", name="Workflow Mirror", parent_id="role.idea-factory",
                   purpose="Mirror selected pipeline behavior into externally operated Dify workflows without changing the core contract.", source_ids=evidence),
    ]
    responsibilities = [
        Responsibility(id="resp.signal-acquisition", role_id="role.signal-intelligence",
                       statement="Collect three classes of signal through isolated and replaceable source adapters.",
                       goal_ids=["goal.screen-ideas"], outputs=["Normalized source records"], source_ids=evidence),
        Responsibility(id="resp.signal-reduction", role_id="role.signal-intelligence",
                       statement="Normalize, deduplicate, triage, and corroborate signals before candidate generation.",
                       goal_ids=["goal.cost-gradient"], inputs=["Raw signals"], outputs=["Qualified signals"], source_ids=evidence),
        Responsibility(id="resp.generate", role_id="role.candidate-generation",
                       statement="Generate multiple candidates and compute comparable, time-decayed factor scores.",
                       goal_ids=["goal.screen-ideas", "goal.cost-gradient"], inputs=["Qualified signals"], outputs=["Ranked candidates"], source_ids=evidence),
        Responsibility(id="resp.evaluate", role_id="role.evaluation-gate",
                       statement="Apply hard gates, evidence checks, adversarial judgment, and portfolio selection.",
                       goal_ids=["goal.screen-ideas", "goal.cost-gradient"], inputs=["Ranked candidates"], outputs=["Verdicts and decision memos"], source_ids=evidence),
        Responsibility(id="resp.next-test", role_id="role.evaluation-gate",
                       statement="Attach the riskiest assumption and a cheap bounded experiment to surviving ideas.",
                       goal_ids=["goal.screen-ideas"], outputs=["Testable next action"], source_ids=evidence),
        Responsibility(id="resp.learn", role_id="role.learning-loop",
                       statement="Record outcomes, derive lessons, and suggest calibration changes from observed prediction error.",
                       goal_ids=["goal.explainability"], inputs=["Verdicts and outcomes"], outputs=["Calibration evidence"], source_ids=evidence),
        Responsibility(id="resp.contract", role_id="role.domain-contract",
                       statement="Define the shared candidate, evidence, factor, ledger, state, and LLM contracts used across roles.",
                       goal_ids=["goal.explainability"], outputs=["Stable shared semantics"], source_ids=evidence),
        Responsibility(id="resp.operate", role_id="role.operator-surface",
                       statement="Present pipeline state and provide authenticated human control over runs, feedback, and outcomes.",
                       goal_ids=["goal.explainability"], inputs=["Model and pipeline outputs"], outputs=["Human decisions"], source_ids=evidence),
        Responsibility(id="resp.mirror", role_id="role.workflow-mirror",
                       statement="Maintain an explicitly validated mirror of selected generation and evaluation workflows.",
                       goal_ids=["goal.explainability"], source_ids=evidence),
    ]
    relations = [
        Relation(id="rel.signal-to-generation", source_role_id="role.signal-intelligence",
                 target_role_id="role.candidate-generation", kind="exchanges_with", label="qualified signals"),
        Relation(id="rel.generation-to-evaluation", source_role_id="role.candidate-generation",
                 target_role_id="role.evaluation-gate", kind="exchanges_with", label="ranked candidates"),
        Relation(id="rel.evaluation-to-learning", source_role_id="role.evaluation-gate",
                 target_role_id="role.learning-loop", kind="exchanges_with", label="verdicts and outcomes"),
        Relation(id="rel.all-to-contract", source_role_id="role.candidate-generation",
                 target_role_id="role.domain-contract", kind="depends_on", label="models and factors"),
        Relation(id="rel.eval-to-contract", source_role_id="role.evaluation-gate",
                 target_role_id="role.domain-contract", kind="depends_on", label="models and evidence"),
        Relation(id="rel.surface-to-roles", source_role_id="role.operator-surface",
                 target_role_id="role.evaluation-gate", kind="collaborates", label="review and control"),
        Relation(id="rel.mirror-to-generation", source_role_id="role.workflow-mirror",
                 target_role_id="role.candidate-generation", kind="depends_on", label="mirrored contract"),
    ]
    trace_links = [
        _trace("signal", "role.signal-intelligence", "src/idea_gen/collect.py", snapshot),
        _trace("sources", "role.signal-intelligence", "src/idea_gen/sources", snapshot),
        _trace("generation", "role.candidate-generation", "src/idea_gen/generate.py", snapshot),
        _trace("ranking", "role.candidate-generation", "src/idea_gen/ranks.py", snapshot),
        _trace("evaluation", "role.evaluation-gate", "src/idea_eval", snapshot),
        _trace("learning", "role.learning-loop", "src/idea_eval/retro.py", snapshot),
        _trace("calibration", "role.learning-loop", "src/idea_eval/calibrate.py", snapshot),
        _trace("contract", "role.domain-contract", "src/idea_core", snapshot),
        _trace("studio-server", "role.operator-surface", "studio/server", snapshot, kind="presents"),
        _trace("studio-web", "role.operator-surface", "studio/web", snapshot, kind="presents"),
        _trace("dify", "role.workflow-mirror", "dify", snapshot),
    ]
    return ProjectModel(
        project_id=snapshot.project_id,
        name="Idea Factory",
        summary="A responsibility model for the pipeline that turns source signals into screened startup ideas and bounded experiments.",
        status="baseline",
        goals=goals,
        roles=roles,
        responsibilities=responsibilities,
        relations=relations,
        trace_links=trace_links,
    )


def _trace(
    suffix: str, role_id: str, artifact_path: str, snapshot: RepositorySnapshot,
    *, kind: str = "realizes",
) -> TraceLink:
    known = {item.path for item in snapshot.artifacts}
    exists = artifact_path in known or any(path.startswith(f"{artifact_path.rstrip('/')}/") for path in known)
    return TraceLink(
        id=f"trace.{suffix}", role_id=role_id, artifact_path=artifact_path,
        kind=kind, confidence=0.96 if exists else 0.55, origin="agent",
        evidence=f"Derived from {snapshot.id}; path {'observed' if exists else 'not observed'} in the scan.",
    )
