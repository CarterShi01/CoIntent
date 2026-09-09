"""Curated backend-logic baseline for the Idea Factory experiment."""

from __future__ import annotations

from .models import (
    ImplementationLink,
    ProjectModel,
    Responsibility,
    SpecificationItem,
    SpecificationResponsibilityLink,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
)
from .scanner import RepositorySnapshot


def idea_factory_model(snapshot: RepositorySnapshot) -> ProjectModel:
    """Lift observed backend code into recursive, product-readable Responsibilities."""
    source = [f"scan:{snapshot.id}"]
    responsibilities = [
        _r(
            "responsibility.screen-ideas", "Screen startup ideas",
            "Turn noisy market signals into a small portfolio of testable startup ideas, then learn from outcomes.",
            ["Current screening cycle", "Evaluation policy"], ["Source signals", "Founder constraints"],
            ["Selected idea portfolio", "Next experiments", "Recorded decisions"], source,
            _flow("screen-ideas", [
                ("signals", "responsibility.understand-signals"),
                ("develop", "responsibility.develop-candidates"),
                ("evaluate", "responsibility.evaluate-candidates"),
                ("learn", "responsibility.learn-from-outcomes"),
            ], [
                ("signals", "develop", "next", "qualified signals"),
                ("develop", "evaluate", "next", "ranked candidates"),
                ("evaluate", "learn", "event", "after experiments produce outcomes"),
                ("learn", "develop", "condition", "new evidence changes the next cycle"),
            ]),
        ),
        _r(
            "responsibility.understand-signals", "Understand market signals",
            "Collect source signals and turn them into corroborated evidence suitable for idea generation.",
            ["Source provenance", "Signal quality"], ["Raw source signals"], ["Qualified signals"], source,
            _flow("understand-signals", [
                ("collect", "responsibility.collect-signals"),
                ("qualify", "responsibility.qualify-signals"),
            ], [("collect", "qualify", "next", "source records")]),
        ),
        _r(
            "responsibility.collect-signals", "Collect source signals",
            "Acquire supported market, problem, persona, and demand signals through replaceable backend sources.",
            ["Enabled sources", "Source provenance"], ["Source configuration"], ["Source records"], source,
        ),
        _r(
            "responsibility.qualify-signals", "Qualify source signals",
            "Normalize, deduplicate, triage, and corroborate raw source records before they influence an idea.",
            ["Normalization rules", "Deduplication evidence"], ["Source records"], ["Qualified signals"], source,
            _flow("qualify-signals", [
                ("normalize", "responsibility.normalize-signals"),
                ("deduplicate", "responsibility.deduplicate-signals"),
                ("corroborate", "responsibility.corroborate-signals"),
            ], [
                ("normalize", "deduplicate", "next", "normalized signals"),
                ("deduplicate", "corroborate", "next", "distinct signals"),
            ]),
        ),
        _r("responsibility.normalize-signals", "Normalize signals", "Convert heterogeneous source records into shared signal semantics.", [], ["Source records"], ["Normalized signals"], source),
        _r("responsibility.deduplicate-signals", "Deduplicate signals", "Collapse repeated evidence without losing its source provenance.", [], ["Normalized signals"], ["Distinct signals"], source),
        _r("responsibility.corroborate-signals", "Corroborate signals", "Check whether independent evidence supports or weakens each signal.", [], ["Distinct signals"], ["Qualified signals"], source),
        _r(
            "responsibility.develop-candidates", "Develop idea candidates",
            "Create diverse startup candidates from qualified evidence and rank them on comparable factors.",
            ["Candidate set", "Factor scores"], ["Qualified signals"], ["Ranked candidates"], source,
            _flow("develop-candidates", [
                ("generate", "responsibility.generate-candidates"),
                ("rank", "responsibility.rank-candidates"),
            ], [("generate", "rank", "next", "candidate set")]),
        ),
        _r("responsibility.generate-candidates", "Generate idea candidates", "Synthesize multiple distinct startup ideas grounded in qualified evidence.", [], ["Qualified signals"], ["Idea candidates"], source),
        _r("responsibility.rank-candidates", "Rank idea candidates", "Calculate comparable, time-sensitive factor scores and order the candidate set.", ["Factor definitions", "Factor scores"], ["Idea candidates"], ["Ranked candidates"], source),
        _r(
            "responsibility.evaluate-candidates", "Evaluate idea candidates",
            "Reject weak candidates cheaply, examine evidence and persona fit, then select survivors with bounded experiments.",
            ["Evaluation verdicts", "Rejection reasons"], ["Ranked candidates", "Founder constraints", "Representative personas"],
            ["Selected portfolio", "Rejection decisions", "Next experiments"], source,
            _flow("evaluate-candidates", [
                ("gate", "responsibility.apply-hard-gates"),
                ("reject", "responsibility.record-rejection"),
                ("evidence", "responsibility.review-evidence"),
                ("persona", "responsibility.pressure-test-personas"),
                ("select", "responsibility.select-portfolio"),
                ("experiment", "responsibility.define-next-experiment"),
            ], [
                ("gate", "reject", "condition", "fails an explicit gate"),
                ("gate", "evidence", "condition", "passes the hard gates"),
                ("evidence", "reject", "condition", "evidence is insufficient"),
                ("evidence", "persona", "condition", "evidence is sufficient"),
                ("persona", "reject", "condition", "fit does not survive pressure"),
                ("persona", "select", "condition", "fit remains defensible"),
                ("select", "experiment", "next", "selected survivors"),
            ]),
        ),
        _r("responsibility.apply-hard-gates", "Apply deterministic gates", "Reject candidates that fail cheap, explicit screening criteria.", ["Gate thresholds"], ["Ranked candidate"], ["Gate decision", "Gate reason"], source),
        _r("responsibility.record-rejection", "Record a rejection", "Preserve a rejected candidate and the evidence-backed reason for its rejection.", [], ["Candidate", "Rejection reason"], ["Recorded rejection"], source),
        _r("responsibility.review-evidence", "Review supporting evidence", "Judge whether evidence is sufficiently grounded and corroborated for deeper evaluation.", [], ["Gate survivor", "Supporting evidence"], ["Evidence verdict"], source),
        _r("responsibility.pressure-test-personas", "Pressure-test persona fit", "Test a surviving idea against founder constraints and representative customer personas.", ["Founder profile", "Persona set"], ["Evidence-qualified candidate"], ["Fit-pressure evidence"], source),
        _r("responsibility.select-portfolio", "Select a candidate portfolio", "Choose a balanced portfolio from the candidates that survived evaluation.", [], ["Evaluated survivors"], ["Selected portfolio"], source),
        _r("responsibility.define-next-experiment", "Define the next experiment", "Attach the riskiest assumption and the cheapest bounded test to each selected candidate.", [], ["Selected candidate"], ["Next experiment"], source),
        _r(
            "responsibility.learn-from-outcomes", "Learn from outcomes",
            "Capture what happened after selection and use prediction error to improve later evaluation.",
            ["Decision history", "Outcome history", "Calibration proposals"], ["Evaluation verdicts", "Observed outcomes"],
            ["Calibration evidence"], source,
            _flow("learn-from-outcomes", [
                ("capture", "responsibility.capture-outcomes"),
                ("calibrate", "responsibility.calibrate-evaluation"),
            ], [("capture", "calibrate", "next", "prediction outcomes")]),
        ),
        _r("responsibility.capture-outcomes", "Capture decisions and outcomes", "Store verdicts, human feedback, experiments, and observed outcomes with provenance.", ["Decision ledger", "Outcome ledger"], ["Verdict", "Feedback", "Observed outcome"], ["Auditable outcome history"], source),
        _r("responsibility.calibrate-evaluation", "Calibrate evaluation", "Suggest factor or threshold changes when observed outcomes differ from earlier predictions.", ["Factor history"], ["Auditable outcome history"], ["Calibration proposal"], source),
    ]

    specifications = [
        _s("spec.screen", "Screen startup ideas", "Turn market evidence into a small set of defensible startup ideas and next experiments.", None, source),
        _s("spec.signals", "Understand demand signals", "Collect and qualify evidence about markets, problems, and representative users.", "spec.screen", source),
        _s("spec.candidates", "Develop comparable candidates", "Generate multiple ideas and rank them using comparable factors.", "spec.screen", source),
        _s("spec.evaluate", "Reject weak ideas and select survivors", "Use explicit gates and evidence-backed judgment to select a balanced portfolio.", "spec.screen", source),
        _s("spec.experiments", "Define a bounded next test", "Give each selected idea a cheap experiment for its riskiest assumption.", "spec.screen", source),
        _s("spec.learning", "Learn from real outcomes", "Preserve decisions and outcomes so later evaluation can improve.", "spec.screen", source),
    ]
    spec_links = [
        _sl("screen", "spec.screen", "responsibility.screen-ideas", source),
        _sl("signals", "spec.signals", "responsibility.understand-signals", source),
        _sl("candidates", "spec.candidates", "responsibility.develop-candidates", source),
        _sl("evaluate", "spec.evaluate", "responsibility.evaluate-candidates", source),
        _sl("experiments", "spec.experiments", "responsibility.define-next-experiment", source),
        _sl("learning", "spec.learning", "responsibility.learn-from-outcomes", source),
    ]
    paths = [
        ("screen", "responsibility.screen-ideas", "src/idea_gen/pipeline.py", ""),
        ("collect", "responsibility.collect-signals", "src/idea_gen/collect.py", ""),
        ("normalize", "responsibility.normalize-signals", "src/idea_gen/normalize.py", ""),
        ("deduplicate", "responsibility.deduplicate-signals", "src/idea_gen/dedup.py", ""),
        ("corroborate", "responsibility.corroborate-signals", "src/idea_gen/crosscheck.py", ""),
        ("generate", "responsibility.generate-candidates", "src/idea_gen/generate.py", ""),
        ("rank", "responsibility.rank-candidates", "src/idea_gen/ranks.py", ""),
        ("gate", "responsibility.apply-hard-gates", "src/idea_eval/evaluate.py", ""),
        ("reject", "responsibility.record-rejection", "src/idea_core/ledger.py", ""),
        ("evidence", "responsibility.review-evidence", "src/idea_eval/enrich.py", ""),
        ("persona", "responsibility.pressure-test-personas", "src/idea_eval/persona_pressure.py", ""),
        ("select", "responsibility.select-portfolio", "src/idea_eval/pipeline.py", ""),
        ("experiment", "responsibility.define-next-experiment", "src/idea_eval/pipeline.py", ""),
        ("outcomes", "responsibility.capture-outcomes", "src/idea_core/ledger.py", ""),
        ("calibrate", "responsibility.calibrate-evaluation", "src/idea_eval/calibrate.py", ""),
    ]
    implementation = [_implementation(*item, snapshot) for item in paths]
    return ProjectModel(
        project_id=snapshot.project_id, name="Idea Factory",
        summary="Backend program logic for turning noisy signals into tested startup candidates.",
        status="baseline", specification_items=specifications, responsibilities=responsibilities,
        specification_responsibility_links=spec_links, implementation_links=implementation,
    )


def _r(
    identifier: str, name: str, description: str, data: list[str], inputs: list[str], outputs: list[str],
    source: list[str], workflow: Workflow | None = None,
) -> Responsibility:
    return Responsibility(
        id=identifier, name=name, description=description, data_members=data, inputs=inputs,
        outputs=outputs, workflow=workflow, source_ids=source,
    )


def _flow(
    owner: str, nodes: list[tuple[str, str]], edges: list[tuple[str, str, str, str]],
) -> Workflow:
    node_records = [WorkflowNode(id=f"node.{owner}.{key}", responsibility_id=ref) for key, ref in nodes]
    node_ids = {key: f"node.{owner}.{key}" for key, _ in nodes}
    return Workflow(
        entry_node_ids=[node_records[0].id], nodes=node_records,
        edges=[
            WorkflowEdge(
                id=f"edge.{owner}.{index}", source_node_id=node_ids[source], target_node_id=node_ids[target],
                kind=kind, label=label,
            )
            for index, (source, target, kind, label) in enumerate(edges, 1)
        ],
    )


def _s(identifier: str, name: str, description: str, parent: str | None, source: list[str]) -> SpecificationItem:
    return SpecificationItem(id=identifier, name=name, description=description, parent_id=parent, source_ids=source)


def _sl(suffix: str, specification: str, responsibility: str, source: list[str]) -> SpecificationResponsibilityLink:
    return SpecificationResponsibilityLink(
        id=f"spec-resp.{suffix}", specification_id=specification, responsibility_id=responsibility,
        confidence=0.96, evidence="Curated from backend behavior and repository evidence.", source_ids=source,
    )


def _implementation(
    suffix: str, responsibility_id: str, artifact_path: str, symbol: str, snapshot: RepositorySnapshot,
) -> ImplementationLink:
    known = {item.path for item in snapshot.artifacts}
    exists = artifact_path in known or any(path.startswith(f"{artifact_path.rstrip('/')}/") for path in known)
    return ImplementationLink(
        id=f"implementation.{suffix}", responsibility_id=responsibility_id, artifact_path=artifact_path,
        symbol=symbol, confidence=0.96 if exists else 0.55, origin="agent",
        evidence=f"Derived from {snapshot.id}; backend path {'observed' if exists else 'not observed'} in the scan.",
    )
