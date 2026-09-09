"""Immutable Understand Anything imports and evidence-backed observed projections."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Responsibility, Workflow, WorkflowEdge, WorkflowNode
from .scanner import RepositorySnapshot


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class UARecord(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=_camel, populate_by_name=True)


NodeType = Literal[
    "file", "function", "class", "module", "concept", "config", "document", "service",
    "table", "endpoint", "pipeline", "schema", "resource", "domain", "flow", "step",
    "article", "entity", "topic", "claim", "source", "page", "screen", "component",
    "componentSet", "instance", "token",
]

EdgeType = Literal[
    "imports", "exports", "contains", "inherits", "implements", "calls", "subscribes",
    "publishes", "middleware", "reads_from", "writes_to", "transforms", "validates",
    "depends_on", "tested_by", "configures", "related", "similar_to", "deploys", "serves",
    "provisions", "triggers", "migrates", "documents", "routes", "defines_schema",
    "contains_flow", "flow_step", "cross_domain", "cites", "contradicts", "builds_on",
    "exemplifies", "categorized_under", "authored_by", "instance_of", "variant_of", "uses_token",
]


class UAProject(UARecord):
    name: str
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    description: str = ""
    analyzed_at: str
    git_commit_hash: str


class UANode(UARecord):
    id: str
    type: NodeType
    name: str
    file_path: str | None = None
    line_range: tuple[int, int] | None = None
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    complexity: Literal["simple", "moderate", "complex"] = "simple"
    language_notes: str | None = None
    domain_meta: dict[str, Any] | None = None
    knowledge_meta: dict[str, Any] | None = None
    figma_meta: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_location(self) -> "UANode":
        if self.file_path is not None and not _safe_path(self.file_path):
            raise ValueError(f"UA node {self.id!r} has an unsafe filePath")
        if self.line_range is not None:
            start, end = self.line_range
            if self.file_path is None:
                raise ValueError(f"UA node {self.id!r} has lineRange without filePath")
            if start < 1 or end < start:
                raise ValueError(f"UA node {self.id!r} has an invalid lineRange")
        return self


class UAEdge(UARecord):
    source: str
    target: str
    type: EdgeType
    direction: Literal["forward", "backward", "bidirectional"] = "forward"
    description: str | None = None
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class UALayer(UARecord):
    id: str
    name: str
    description: str = ""
    node_ids: list[str] = Field(default_factory=list)


class UATourStep(UARecord):
    order: int
    title: str
    description: str = ""
    node_ids: list[str] = Field(default_factory=list)
    language_lesson: str | None = None


class UAKnowledgeGraph(UARecord):
    version: str
    kind: Literal["codebase", "knowledge", "design"] | None = None
    project: UAProject
    nodes: list[UANode] = Field(default_factory=list)
    edges: list[UAEdge] = Field(default_factory=list)
    layers: list[UALayer] = Field(default_factory=list)
    tour: list[UATourStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> "UAKnowledgeGraph":
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("UA graph contains duplicate node IDs")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError(f"UA edge {edge.source!r} → {edge.target!r} has a dangling endpoint")
        for layer in self.layers:
            missing = set(layer.node_ids) - known
            if missing:
                raise ValueError(f"UA layer {layer.id!r} contains unknown nodes {sorted(missing)!r}")
        for step in self.tour:
            missing = set(step.node_ids) - known
            if missing:
                raise ValueError(f"UA tour step {step.order!r} contains unknown nodes {sorted(missing)!r}")
        return self


class UACoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code_snapshot_files: int
    ua_located_nodes: int
    ua_unlocated_nodes: int
    domain_nodes: int
    evidence_backed_domain_nodes: int


class UADiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["unlocated_node", "omitted_domain_node", "missing_domain_graph"]
    subject_id: str | None = None
    message: str


class UnderstandAnythingSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["cointent.ua-snapshot/0.1"] = "cointent.ua-snapshot/0.1"
    id: str
    project_id: str
    code_snapshot_id: str
    ua_tool_revision: str
    ua_graph_version: str
    knowledge_graph: UAKnowledgeGraph
    domain_graph: UAKnowledgeGraph | None = None
    coverage: UACoverage
    diagnostics: list[UADiagnostic] = Field(default_factory=list)
    content_digest: str
    created_at: str


class EvidenceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ua_node_id: str
    path: str
    start_line: int | None = None
    end_line: int | None = None
    source_digest: str
    origin: Literal["ua_structural", "ua_semantic"]
    structural_ua_node_ids: list[str] = Field(default_factory=list)


class ClaimBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    subject_kind: Literal["responsibility", "workflow_edge", "capability"]
    subject_id: str
    predicate: Literal["implemented_by", "ordered_by", "summarized_by"]
    ua_node_ids: list[str]
    evidence: list[EvidenceBinding]
    support: Literal["direct", "aggregated", "inferred"]
    explanation: str


class ImplementationRef(BaseModel):
    """Immutable semantic-to-UA/source coordinate used by the browser bridge."""

    model_config = ConfigDict(extra="forbid")
    id: str
    project_id: str
    observed_revision_id: str
    subject_kind: Literal["system_function", "responsibility"]
    subject_id: str
    ua_snapshot_id: str
    code_snapshot_id: str
    graph_kind: Literal["structural"] = "structural"
    semantic_ua_node_id: str | None = None
    structural_ua_node_ids: list[str] = Field(default_factory=list)
    preferred_focus_node_id: str | None = None
    file_path: str
    line_range: tuple[int, int] | None = None
    symbol: str | None = None
    role: Literal["primary", "supporting"] = "supporting"
    resolution: Literal[
        "exact_symbol", "exact_span", "enclosing_symbol", "file_fallback", "inherited",
    ]


class ObservedCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    description: str = ""
    responsibility_id: str
    evidence_count: int


class ObservationRefinement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_depth: int = Field(ge=1, le=3)
    added_responsibilities: int = Field(ge=0)
    evidence_bindings: int = Field(ge=0)
    max_depth_reached: int = Field(ge=0)
    truncated: bool = False


class ObservedModelRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["cointent.observed-model/0.4"] = "cointent.observed-model/0.4"
    id: str
    project_id: str
    code_snapshot_id: str
    ua_snapshot_id: str
    parent_revision_id: str | None = None
    refinement_of_node_id: str | None = None
    projector_version: Literal["ua-domain-v1"] = "ua-domain-v1"
    capabilities: list[ObservedCapability] = Field(default_factory=list)
    responsibilities: list[Responsibility] = Field(default_factory=list)
    bindings: list[ClaimBinding] = Field(default_factory=list)
    implementation_refs: list[ImplementationRef] = Field(default_factory=list)
    diagnostics: list[UADiagnostic] = Field(default_factory=list)
    refinement: ObservationRefinement | None = None
    content_digest: str
    created_at: str

    @model_validator(mode="after")
    def validate_observation(self) -> "ObservedModelRevision":
        responsibility_ids = {item.id for item in self.responsibilities}
        if len(responsibility_ids) != len(self.responsibilities):
            raise ValueError("observed model contains duplicate Responsibility IDs")
        workflow_edge_ids: set[str] = set()
        for responsibility in self.responsibilities:
            if responsibility.workflow is None:
                continue
            workflow_edge_ids.update(edge.id for edge in responsibility.workflow.edges)
            for node in responsibility.workflow.nodes:
                if node.responsibility_id not in responsibility_ids:
                    raise ValueError(f"observed Workflow references unknown Responsibility {node.responsibility_id!r}")
        if any(item.responsibility_id not in responsibility_ids for item in self.capabilities):
            raise ValueError("observed capability points to an unknown Responsibility")
        bound_responsibilities = {
            item.subject_id for item in self.bindings if item.subject_kind == "responsibility" and item.evidence
        }
        if bound_responsibilities != responsibility_ids:
            missing = responsibility_ids - bound_responsibilities
            raise ValueError(f"observed Responsibilities lack source evidence: {sorted(missing)!r}")
        valid_subjects = responsibility_ids | workflow_edge_ids | {item.id for item in self.capabilities}
        if any(item.subject_id not in valid_subjects or not item.evidence for item in self.bindings):
            raise ValueError("claim binding has an unknown subject or no source evidence")
        capability_ids = {item.id for item in self.capabilities}
        ref_ids = [item.id for item in self.implementation_refs]
        if len(ref_ids) != len(set(ref_ids)):
            raise ValueError("observed model contains duplicate ImplementationRef IDs")
        primary_by_subject: dict[str, int] = {}
        for ref in self.implementation_refs:
            if (
                ref.project_id != self.project_id
                or ref.observed_revision_id != self.id
                or ref.ua_snapshot_id != self.ua_snapshot_id
                or ref.code_snapshot_id != self.code_snapshot_id
            ):
                raise ValueError("ImplementationRef coordinate does not match its observed revision")
            expected_subjects = capability_ids if ref.subject_kind == "system_function" else responsibility_ids
            if ref.subject_id not in expected_subjects:
                raise ValueError("ImplementationRef points to an unknown semantic subject")
            if not ref.structural_ua_node_ids:
                raise ValueError("ImplementationRef requires at least one structural UA node")
            if ref.preferred_focus_node_id not in ref.structural_ua_node_ids:
                raise ValueError("ImplementationRef focus must be one of its structural UA nodes")
            if ref.role == "primary":
                primary_by_subject[ref.subject_id] = primary_by_subject.get(ref.subject_id, 0) + 1
        if any(count > 1 for count in primary_by_subject.values()):
            raise ValueError("a semantic subject cannot have multiple primary ImplementationRefs")
        return self


class ObservationExpansionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["cointent.observation-expansion/0.1"] = "cointent.observation-expansion/0.1"
    id: str
    project_id: str
    base_observed_revision_id: str
    ua_snapshot_id: str
    target_observed_node_id: str
    target_ua_node_id: str
    depth: int = Field(ge=1, le=3)
    evidence_scope: list[EvidenceBinding]
    status: Literal["queued", "completed", "atomic_at_current_evidence", "failed"] = "queued"
    result_observed_revision_id: str | None = None
    message: str = ""
    created_at: str
    updated_at: str


def build_expansion_request(
    revision: ObservedModelRevision, *, node_id: str, depth: int = 1,
    created_at: str | None = None,
) -> ObservationExpansionRequest:
    """Create a bounded UA refinement request with no user-authored graph payload."""
    if depth < 1 or depth > 3:
        raise ValueError("expansion depth must be between 1 and 3")
    target = next((item for item in revision.responsibilities if item.id == node_id), None)
    if target is None:
        raise ValueError("expansion target is not part of the base observed revision")
    identifier = _scoped_id("expansion", revision.ua_snapshot_id, node_id, str(depth), "ua-domain-v1")
    timestamp = created_at or datetime.now(UTC).isoformat()
    return ObservationExpansionRequest(
        id=identifier, project_id=revision.project_id,
        base_observed_revision_id=revision.id, ua_snapshot_id=revision.ua_snapshot_id,
        target_observed_node_id=node_id, target_ua_node_id=target.source_ids[0],
        depth=depth,
        evidence_scope=next(
            item.evidence for item in revision.bindings
            if item.subject_kind == "responsibility" and item.subject_id == node_id
        ),
        created_at=timestamp, updated_at=timestamp,
    )


EXPANSION_EDGE_TYPES = frozenset({
    "contains", "calls", "implements", "routes", "reads_from", "writes_to", "transforms",
    "validates", "subscribes", "publishes", "triggers", "configures", "serves",
})
MAX_EXPANSION_NODES = 64


def project_observed_expansion(
    base_revision: ObservedModelRevision,
    snapshot: UnderstandAnythingSnapshot,
    code_snapshot: RepositorySnapshot,
    *,
    node_id: str,
    depth: int = 1,
    created_at: str | None = None,
) -> ObservedModelRevision | None:
    """Project a bounded structural refinement without accepting caller-authored graph data."""
    if depth < 1 or depth > 3:
        raise ValueError("expansion depth must be between 1 and 3")
    if base_revision.ua_snapshot_id != snapshot.id or snapshot.code_snapshot_id != code_snapshot.id:
        raise ValueError("expansion inputs do not share one immutable UA/code coordinate")
    target = next((item for item in base_revision.responsibilities if item.id == node_id), None)
    if target is None:
        raise ValueError("expansion target is not part of the base observed revision")
    target_binding = next(
        item for item in base_revision.bindings
        if item.subject_kind == "responsibility" and item.subject_id == node_id
    )

    graph = snapshot.knowledge_graph
    nodes = {item.id: item for item in graph.nodes}
    artifacts = {item.path: item for item in code_snapshot.artifacts}
    outgoing: dict[str, list[tuple[str, str]]] = {}
    contains: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge.type not in EXPANSION_EDGE_TYPES:
            continue
        outgoing.setdefault(edge.source, []).append((edge.type, edge.target))
        if edge.type == "contains":
            contains.setdefault(edge.source, set()).add(edge.target)
    for values in outgoing.values():
        values.sort(key=lambda item: (item[0], item[1]))

    structural_target = target.source_ids[0] if target.source_ids and target.source_ids[0] in nodes else None
    if structural_target is not None:
        initial = outgoing.get(structural_target, [])
    else:
        evidence_ids = {
            structural_id
            for evidence in target_binding.evidence
            for structural_id in evidence.structural_ua_node_ids
            if structural_id in nodes
        }
        anchors = _most_specific_nodes(evidence_ids, contains)
        initial = [("evidence_anchor", native_id) for native_id in sorted(anchors)]

    selected: dict[str, int] = {}
    relation_from_parent: dict[str, str] = {}
    frontier: list[tuple[str, str, int]] = [(kind, native_id, 1) for kind, native_id in initial]
    truncated = False
    while frontier:
        relation, native_id, level = frontier.pop(0)
        native = nodes.get(native_id)
        if native is None or native.file_path is None or native.file_path not in artifacts:
            continue
        previous = selected.get(native_id)
        if previous is not None and previous <= level:
            continue
        if len(selected) >= MAX_EXPANSION_NODES:
            truncated = True
            break
        selected[native_id] = level
        relation_from_parent.setdefault(native_id, relation)
        if level < depth:
            frontier.extend((kind, child_id, level + 1) for kind, child_id in outgoing.get(native_id, []))

    if not selected:
        return None

    def observed_id(native_id: str) -> str:
        return _scoped_id("obs-resp", snapshot.id, native_id)

    children: dict[str, list[tuple[str, str]]] = {}
    roots: list[tuple[str, str]] = []
    selected_ids = set(selected)
    if structural_target is not None:
        roots = [(kind, child_id) for kind, child_id in initial if child_id in selected_ids]
    else:
        roots = [("evidence_anchor", native_id) for native_id in sorted(selected_ids) if selected[native_id] == 1]
    for parent_id in sorted(selected_ids):
        children[parent_id] = [
            (kind, child_id) for kind, child_id in outgoing.get(parent_id, [])
            if child_id in selected_ids and selected[child_id] == selected[parent_id] + 1
        ]

    responsibilities: list[Responsibility] = []
    bindings: list[ClaimBinding] = [target_binding]
    root_workflow = _structural_workflow(snapshot.id, node_id, roots, observed_id)
    responsibilities.append(target.model_copy(update={"workflow": root_workflow}))

    for native_id in sorted(selected_ids, key=lambda item: (selected[item], item)):
        native = nodes[native_id]
        evidence = _structural_evidence(native, artifacts[native.file_path])
        workflow = _structural_workflow(snapshot.id, observed_id(native_id), children[native_id], observed_id)
        responsibilities.append(Responsibility(
            id=observed_id(native_id),
            name=native.name,
            description=native.summary or f"{native.type} discovered by Understand Anything.",
            workflow=workflow,
            status="accepted",
            source_ids=[native_id],
        ))
        bindings.append(ClaimBinding(
            id=_scoped_id("obs-binding", snapshot.id, observed_id(native_id)),
            subject_kind="responsibility",
            subject_id=observed_id(native_id),
            predicate="implemented_by",
            ua_node_ids=[native_id],
            evidence=[evidence],
            support="direct",
            explanation=(
                f"Structural refinement follows the pinned UA {relation_from_parent[native_id]} relation "
                "and resolves to the captured source file."
            ),
        ))

    refinement = ObservationRefinement(
        requested_depth=depth,
        added_responsibilities=len(selected_ids),
        evidence_bindings=len(selected_ids),
        max_depth_reached=max(selected.values()),
        truncated=truncated,
    )
    payload = {
        "project_id": snapshot.project_id,
        "code_snapshot_id": snapshot.code_snapshot_id,
        "ua_snapshot_id": snapshot.id,
        "parent_revision_id": base_revision.id,
        "refinement_of_node_id": node_id,
        "projector_version": "ua-domain-v1",
        "implementation_ref_projection_version": "implementation-ref-v1",
        "responsibilities": [item.model_dump(mode="json") for item in responsibilities],
        "bindings": [item.model_dump(mode="json") for item in bindings],
        "refinement": refinement.model_dump(mode="json"),
    }
    digest = _digest(payload)
    observed_revision_id = f"observed-{digest[:24]}"
    implementation_refs = _implementation_refs(
        project_id=snapshot.project_id,
        observed_revision_id=observed_revision_id,
        ua_snapshot_id=snapshot.id,
        code_snapshot_id=snapshot.code_snapshot_id,
        bindings=bindings,
        structural_graph=snapshot.knowledge_graph,
    )
    return ObservedModelRevision(
        id=observed_revision_id,
        project_id=snapshot.project_id,
        code_snapshot_id=snapshot.code_snapshot_id,
        ua_snapshot_id=snapshot.id,
        parent_revision_id=base_revision.id,
        refinement_of_node_id=node_id,
        responsibilities=responsibilities,
        bindings=sorted(bindings, key=lambda item: item.id),
        implementation_refs=implementation_refs,
        refinement=refinement,
        content_digest=digest,
        created_at=created_at or datetime.now(UTC).isoformat(),
    )


def _structural_workflow(
    snapshot_id: str,
    owner_id: str,
    children: list[tuple[str, str]],
    observed_id: Any,
) -> Workflow | None:
    if not children:
        return None
    occurrences = [WorkflowNode(
        id=_scoped_id("obs-occ", snapshot_id, owner_id, child_id),
        responsibility_id=observed_id(child_id),
        note="Source anchor" if relation == "evidence_anchor" else f"UA relation: {relation}",
    ) for relation, child_id in children]
    # Structural UA relationships express composition/dependency, not execution order.
    return Workflow(entry_node_ids=[item.id for item in occurrences], nodes=occurrences, edges=[])


def _structural_evidence(node: UANode, artifact: Any) -> EvidenceBinding:
    start, end = node.line_range or (None, None)
    return EvidenceBinding(
        ua_node_id=node.id,
        path=node.file_path,
        start_line=start,
        end_line=end,
        source_digest=artifact.sha256,
        origin="ua_structural",
        structural_ua_node_ids=[node.id],
    )


def _most_specific_nodes(node_ids: set[str], contains: dict[str, set[str]]) -> set[str]:
    """Drop evidence anchors that merely contain a more specific selected anchor."""
    result = set(node_ids)
    for candidate in node_ids:
        frontier = list(contains.get(candidate, set()))
        seen: set[str] = set()
        while frontier:
            child = frontier.pop()
            if child in seen:
                continue
            seen.add(child)
            if child in node_ids:
                result.discard(candidate)
                break
            frontier.extend(contains.get(child, set()))
    return result


def build_ua_snapshot(
    *, project_id: str, code_snapshot: RepositorySnapshot, ua_tool_revision: str,
    knowledge_graph: UAKnowledgeGraph, domain_graph: UAKnowledgeGraph | None = None,
    created_at: str | None = None,
) -> UnderstandAnythingSnapshot:
    """Validate native UA artifacts against one full immutable code snapshot."""
    if code_snapshot.project_id != project_id:
        raise ValueError("code snapshot project_id does not match target project")
    if code_snapshot.scope != "full":
        raise ValueError("Understand Anything import requires a full code snapshot")
    if not ua_tool_revision.strip():
        raise ValueError("ua_tool_revision must identify the pinned Understand Anything version")
    graphs = [knowledge_graph, *([domain_graph] if domain_graph is not None else [])]
    for graph in graphs:
        if not code_snapshot.dirty and graph.project.git_commit_hash != code_snapshot.revision:
            raise ValueError("Understand Anything gitCommitHash does not match the clean code snapshot")

    artifacts = {item.path: item for item in code_snapshot.artifacts}
    located = 0
    unlocated = 0
    diagnostics: list[UADiagnostic] = []
    for graph in graphs:
        for node in graph.nodes:
            if node.file_path is None:
                unlocated += 1
                continue
            artifact = artifacts.get(node.file_path)
            if artifact is None:
                raise ValueError(f"UA node {node.id!r} references path absent from code snapshot: {node.file_path}")
            if node.line_range is not None and artifact.line_count is not None:
                if node.line_range[1] > artifact.line_count:
                    raise ValueError(
                        f"UA node {node.id!r} lineRange exceeds captured file length: {node.file_path}"
                    )
            located += 1
    semantic_graph = domain_graph or knowledge_graph
    domain_ids = {node.id for node in semantic_graph.nodes if node.type in {"domain", "flow", "step"}}
    evidence_ids = _evidence_backed_ids(semantic_graph, artifacts, knowledge_graph)
    if domain_graph is None:
        diagnostics.append(UADiagnostic(
            kind="missing_domain_graph", message="No domain-graph.json was imported; only embedded domain nodes can be projected.",
        ))

    identity = {
        "project_id": project_id,
        "code_snapshot_id": code_snapshot.id,
        "ua_tool_revision": ua_tool_revision,
        "knowledge_graph": knowledge_graph.model_dump(mode="json", by_alias=True),
        "domain_graph": None if domain_graph is None else domain_graph.model_dump(mode="json", by_alias=True),
    }
    digest = _digest(identity)
    return UnderstandAnythingSnapshot(
        id=f"ua-{digest[:24]}", project_id=project_id, code_snapshot_id=code_snapshot.id,
        ua_tool_revision=ua_tool_revision, ua_graph_version=knowledge_graph.version,
        knowledge_graph=knowledge_graph, domain_graph=domain_graph,
        coverage=UACoverage(
            code_snapshot_files=len(code_snapshot.artifacts), ua_located_nodes=located,
            ua_unlocated_nodes=unlocated, domain_nodes=len(domain_ids),
            evidence_backed_domain_nodes=len(domain_ids & evidence_ids),
        ),
        diagnostics=diagnostics, content_digest=digest,
        created_at=created_at or datetime.now(UTC).isoformat(),
    )


def project_observed_model(
    snapshot: UnderstandAnythingSnapshot, code_snapshot: RepositorySnapshot, *, created_at: str | None = None,
) -> ObservedModelRevision:
    """Project UA semantics into the fixed Responsibility/Workflow graph contract."""
    if snapshot.code_snapshot_id != code_snapshot.id or snapshot.project_id != code_snapshot.project_id:
        raise ValueError("UA snapshot and code snapshot coordinates do not match")
    graph = snapshot.domain_graph or snapshot.knowledge_graph
    artifacts = {item.path: item for item in code_snapshot.artifacts}
    nodes_by_id = {node.id: node for node in graph.nodes if node.type in {"domain", "flow", "step"}}
    evidence_by_native = _evidence_by_id(graph, artifacts, snapshot.knowledge_graph)
    parent_by_native: dict[str, str] = {}
    for edge in graph.edges:
        if edge.type in {"contains_flow", "flow_step"} and edge.source in nodes_by_id and edge.target in nodes_by_id:
            parent_by_native[edge.target] = edge.source

    included = set(evidence_by_native)
    changed = True
    while changed:
        changed = False
        for child, parent in parent_by_native.items():
            if child in included and parent not in included:
                included.add(parent)
                changed = True

    def responsibility_id(native_id: str) -> str:
        return _scoped_id("obs-resp", snapshot.id, native_id)

    descendant_evidence: dict[str, list[EvidenceBinding]] = {}

    def collect(native_id: str, visiting: frozenset[str] = frozenset()) -> list[EvidenceBinding]:
        if native_id in descendant_evidence:
            return descendant_evidence[native_id]
        if native_id in visiting:
            return []
        gathered = list(evidence_by_native.get(native_id, []))
        children = [child for child, parent in parent_by_native.items() if parent == native_id and child in included]
        for child in children:
            gathered.extend(collect(child, visiting | {native_id}))
        unique = {(item.path, item.start_line, item.end_line, item.ua_node_id): item for item in gathered}
        result = [unique[key] for key in sorted(unique)]
        descendant_evidence[native_id] = result
        return result

    diagnostics = list(snapshot.diagnostics)
    publishable: dict[str, tuple[UANode, list[EvidenceBinding]]] = {}
    for native_id, native_node in sorted(nodes_by_id.items()):
        evidence = collect(native_id)
        if native_id not in included or not evidence:
            diagnostics.append(UADiagnostic(
                kind="omitted_domain_node", subject_id=native_id,
                message="UA semantic node has no resolvable source evidence and was omitted from current-system truth.",
            ))
            continue
        publishable[native_id] = (native_node, evidence)

    children_by_parent: dict[str, list[tuple[float, str]]] = {}
    for edge in graph.edges:
        if edge.type in {"contains_flow", "flow_step"} and edge.source in publishable and edge.target in publishable:
            children_by_parent.setdefault(edge.source, []).append((edge.weight, edge.target))

    responsibilities: list[Responsibility] = []
    bindings: list[ClaimBinding] = []
    for native_id, (native_node, evidence) in sorted(publishable.items()):
        children = sorted(children_by_parent.get(native_id, []), key=lambda item: (item[0], item[1]))
        workflow = None
        if children:
            workflow_nodes = [WorkflowNode(
                id=_scoped_id("obs-occ", snapshot.id, native_id, child_id),
                responsibility_id=responsibility_id(child_id), note=publishable[child_id][0].summary,
            ) for _, child_id in children]
            workflow_edges: list[WorkflowEdge] = []
            # A domain groups independent flows. Only flow steps carry UA's linear order.
            if native_node.type == "flow":
                for left, right in zip(workflow_nodes, workflow_nodes[1:]):
                    edge_id = _scoped_id("obs-wf-edge", snapshot.id, native_id, left.id, right.id)
                    workflow_edges.append(WorkflowEdge(
                        id=edge_id, source_node_id=left.id, target_node_id=right.id, kind="next",
                    ))
                    bindings.append(ClaimBinding(
                        id=_scoped_id("obs-binding", snapshot.id, edge_id),
                        subject_kind="workflow_edge", subject_id=edge_id, predicate="ordered_by",
                        ua_node_ids=[native_id],
                        evidence=evidence, support="inferred",
                        explanation="Step order follows monotonically increasing UA flow_step weights; no branch or control-flow claim is made.",
                    ))
            workflow = Workflow(
                entry_node_ids=[workflow_nodes[0].id] if native_node.type == "flow" else [item.id for item in workflow_nodes],
                nodes=workflow_nodes, edges=workflow_edges,
            )
        rid = responsibility_id(native_id)
        responsibilities.append(Responsibility(
            id=rid, name=native_node.name, description=native_node.summary,
            workflow=workflow, status="accepted", source_ids=[native_id],
        ))
        bindings.append(ClaimBinding(
            id=_scoped_id("obs-binding", snapshot.id, rid),
            subject_kind="responsibility", subject_id=rid, predicate="implemented_by",
            ua_node_ids=sorted({item.ua_node_id for item in evidence}), evidence=evidence,
            support="direct" if native_id in evidence_by_native else "aggregated",
            explanation=(
                "Source range overlaps structural nodes in the pinned UA knowledge graph."
                if native_id in evidence_by_native
                else "Evidence is the union of corroborated descendant step bindings."
            ),
        ))

    capabilities = []
    for native_id, (native_node, evidence) in sorted(publishable.items()):
        if native_node.type != "flow":
            continue
        capability = ObservedCapability(
            id=_scoped_id("obs-cap", snapshot.id, native_id), name=native_node.name,
            description=native_node.summary, responsibility_id=responsibility_id(native_id),
            evidence_count=len(evidence),
        )
        capabilities.append(capability)
        bindings.append(ClaimBinding(
            id=_scoped_id("obs-binding", snapshot.id, capability.id),
            subject_kind="capability", subject_id=capability.id, predicate="summarized_by",
            ua_node_ids=[native_id], evidence=evidence, support="inferred",
            explanation="Capability wording is supplied by the UA flow summary and backed by its descendant source evidence.",
        ))

    payload = {
        "project_id": snapshot.project_id, "code_snapshot_id": snapshot.code_snapshot_id,
        "ua_snapshot_id": snapshot.id, "projector_version": "ua-domain-v1",
        "implementation_ref_projection_version": "implementation-ref-v1",
        "capabilities": [item.model_dump(mode="json") for item in capabilities],
        "responsibilities": [item.model_dump(mode="json") for item in responsibilities],
        "bindings": [item.model_dump(mode="json") for item in bindings],
        "diagnostics": [item.model_dump(mode="json") for item in diagnostics],
    }
    digest = _digest(payload)
    observed_revision_id = f"observed-{digest[:24]}"
    implementation_refs = _implementation_refs(
        project_id=snapshot.project_id,
        observed_revision_id=observed_revision_id,
        ua_snapshot_id=snapshot.id,
        code_snapshot_id=snapshot.code_snapshot_id,
        bindings=bindings,
        structural_graph=snapshot.knowledge_graph,
    )
    return ObservedModelRevision(
        id=observed_revision_id, project_id=snapshot.project_id,
        code_snapshot_id=snapshot.code_snapshot_id, ua_snapshot_id=snapshot.id,
        capabilities=capabilities, responsibilities=responsibilities,
        bindings=sorted(bindings, key=lambda item: item.id),
        implementation_refs=implementation_refs, diagnostics=diagnostics,
        content_digest=digest, created_at=created_at or datetime.now(UTC).isoformat(),
    )


def _implementation_refs(
    *, project_id: str, observed_revision_id: str, ua_snapshot_id: str,
    code_snapshot_id: str, bindings: list[ClaimBinding], structural_graph: UAKnowledgeGraph,
) -> list[ImplementationRef]:
    """Derive deterministic refs without inventing identities from display names."""

    structural = {node.id: node for node in structural_graph.nodes}
    refs: list[ImplementationRef] = []
    for binding in bindings:
        if binding.subject_kind not in {"responsibility", "capability"}:
            continue
        candidates: list[tuple[int, EvidenceBinding, str | None, UANode | None, str]] = []
        for evidence in binding.evidence:
            focus_id, focus_node, rank, resolution = _preferred_structural_node(evidence, structural)
            if binding.support != "direct":
                resolution = "inherited"
            candidates.append((rank, evidence, focus_id, focus_node, resolution))
        best_rank = min((item[0] for item in candidates), default=99)
        best_count = sum(1 for item in candidates if item[0] == best_rank)
        for rank, evidence, focus_id, focus_node, resolution in candidates:
            subject_kind = "system_function" if binding.subject_kind == "capability" else "responsibility"
            identity = _digest({
                "observed_revision_id": observed_revision_id,
                "subject_kind": subject_kind,
                "subject_id": binding.subject_id,
                "semantic_ua_node_id": evidence.ua_node_id if evidence.origin == "ua_semantic" else None,
                "structural_ua_node_ids": evidence.structural_ua_node_ids,
                "path": evidence.path,
                "line_range": [evidence.start_line, evidence.end_line],
            })
            line_range = (
                (evidence.start_line, evidence.end_line)
                if evidence.start_line is not None and evidence.end_line is not None else None
            )
            refs.append(ImplementationRef(
                id=f"implementation-ref-{identity[:24]}",
                project_id=project_id,
                observed_revision_id=observed_revision_id,
                subject_kind=subject_kind,
                subject_id=binding.subject_id,
                ua_snapshot_id=ua_snapshot_id,
                code_snapshot_id=code_snapshot_id,
                semantic_ua_node_id=evidence.ua_node_id if evidence.origin == "ua_semantic" else None,
                structural_ua_node_ids=sorted(set(evidence.structural_ua_node_ids)),
                preferred_focus_node_id=focus_id,
                file_path=evidence.path,
                line_range=line_range,
                symbol=focus_node.name if focus_node is not None and focus_node.type != "file" else None,
                role="primary" if rank == best_rank and best_count == 1 else "supporting",
                resolution=resolution,
            ))
    return sorted(refs, key=lambda item: (item.subject_kind, item.subject_id, item.role != "primary", item.id))


def _preferred_structural_node(
    evidence: EvidenceBinding, structural: dict[str, UANode],
) -> tuple[str | None, UANode | None, int, str]:
    nodes = [structural[item] for item in evidence.structural_ua_node_ids if item in structural]
    if not nodes:
        return None, None, 9, "inherited"
    exact_types = {"function", "endpoint", "service", "class", "component"}
    located = [node for node in nodes if node.file_path == evidence.path]
    exact = [
        node for node in located
        if node.type in exact_types and node.line_range is not None
        and evidence.start_line is not None and evidence.end_line is not None
        and node.line_range[0] <= evidence.start_line <= evidence.end_line <= node.line_range[1]
    ]
    if exact:
        node = min(exact, key=lambda item: (item.line_range[1] - item.line_range[0], item.id))  # type: ignore[index]
        resolution = "exact_span" if node.line_range == (evidence.start_line, evidence.end_line) else "exact_symbol"
        return node.id, node, 1, resolution
    enclosing = [node for node in located if node.type in {"class", "module", "service", "component"}]
    if enclosing:
        node = min(
            enclosing,
            key=lambda item: (
                (item.line_range[1] - item.line_range[0]) if item.line_range is not None else 10**9,
                item.id,
            ),
        )
        return node.id, node, 2, "enclosing_symbol"
    files = [node for node in located if node.type == "file"]
    if files:
        node = min(files, key=lambda item: item.id)
        return node.id, node, 3, "file_fallback"
    return None, None, 9, "inherited"


def _evidence_backed_ids(
    graph: UAKnowledgeGraph, artifacts: dict[str, Any], structural_graph: UAKnowledgeGraph,
) -> set[str]:
    evidence = set(_evidence_by_id(graph, artifacts, structural_graph))
    parents = {
        edge.target: edge.source for edge in graph.edges
        if edge.type in {"contains_flow", "flow_step"}
    }
    for native_id in list(evidence):
        seen: set[str] = set()
        current = native_id
        while current in parents and current not in seen:
            seen.add(current)
            current = parents[current]
            evidence.add(current)
    return evidence


def _evidence_by_id(
    graph: UAKnowledgeGraph, artifacts: dict[str, Any], structural_graph: UAKnowledgeGraph,
) -> dict[str, list[EvidenceBinding]]:
    result: dict[str, list[EvidenceBinding]] = {}
    structural_nodes = [
        node for node in structural_graph.nodes
        if node.type not in {"domain", "flow", "step", "concept"} and node.file_path is not None
    ]
    for node in graph.nodes:
        if node.file_path is None or node.file_path not in artifacts:
            continue
        anchors = [candidate.id for candidate in structural_nodes if _locations_overlap(node, candidate)]
        if node.type in {"domain", "flow", "step", "concept"} and not anchors:
            continue
        artifact = artifacts[node.file_path]
        start, end = node.line_range or (None, None)
        result[node.id] = [EvidenceBinding(
            ua_node_id=node.id, path=node.file_path, start_line=start, end_line=end,
            source_digest=artifact.sha256,
            origin="ua_semantic" if node.type in {"domain", "flow", "step", "concept"} else "ua_structural",
            structural_ua_node_ids=sorted(anchors),
        )]
    return result


def _locations_overlap(left: UANode, right: UANode) -> bool:
    if left.file_path != right.file_path:
        return False
    if left.line_range is None or right.line_range is None:
        return True
    return left.line_range[0] <= right.line_range[1] and right.line_range[0] <= left.line_range[1]


def _safe_path(value: str) -> bool:
    path = PurePosixPath(value.replace("\\", "/"))
    return bool(value) and not path.is_absolute() and ".." not in path.parts and "." != str(path)


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _scoped_id(prefix: str, *parts: str) -> str:
    token = hashlib.sha256("\0".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}-{token}"
