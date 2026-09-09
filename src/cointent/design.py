"""Independent, immutable target-design workspaces derived from observed baselines."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Responsibility, Workflow, WorkflowEdge, WorkflowNode
from .observation import ObservedModelRevision


class DesignRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectedFeature(DesignRecord):
    id: str
    name: str
    description: str = ""
    parent_id: str | None = None
    status: Literal["draft", "questioned", "accepted", "deferred"] = "draft"


class FeatureResponsibilityLink(DesignRecord):
    id: str
    expected_feature_id: str
    responsibility_id: str
    kind: Literal["realizes", "contributes"] = "realizes"


class DesignBaselineLink(DesignRecord):
    design_kind: Literal["expected_feature", "responsibility"]
    design_id: str
    observed_kind: Literal["capability", "responsibility"]
    observed_id: str
    kind: Literal["cloned_from"] = "cloned_from"


class DesignRevision(DesignRecord):
    schema_version: Literal["cointent.target-design/0.4"] = "cointent.target-design/0.4"
    id: str
    workspace_id: str
    parent_revision_id: str | None = None
    base_observed_revision_id: str
    title: str
    summary: str = ""
    expected_features: list[ExpectedFeature] = Field(default_factory=list)
    responsibilities: list[Responsibility] = Field(default_factory=list)
    feature_responsibility_links: list[FeatureResponsibilityLink] = Field(default_factory=list)
    baseline_links: list[DesignBaselineLink] = Field(default_factory=list)
    rationale: str
    unresolved_questions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    created_by: str
    created_at: str
    content_digest: str

    @model_validator(mode="after")
    def validate_target_graph(self) -> "DesignRevision":
        feature_ids = _unique_ids(self.expected_features, "expected feature")
        responsibility_ids = _unique_ids(self.responsibilities, "design Responsibility")
        link_ids = _unique_ids(self.feature_responsibility_links, "feature link")
        if any(not item.startswith("des-feature-") for item in feature_ids):
            raise ValueError("expected feature IDs must use the des-feature namespace")
        if any(not item.startswith("des-resp-") for item in responsibility_ids):
            raise ValueError("design Responsibility IDs must use the des-resp namespace")
        if any(not item.startswith("des-link-") for item in link_ids):
            raise ValueError("design feature-link IDs must use the des-link namespace")
        for feature in self.expected_features:
            if feature.parent_id is not None and feature.parent_id not in feature_ids:
                raise ValueError(f"expected feature {feature.id!r} has an unknown parent")
        _assert_feature_acyclic(self.expected_features)
        for responsibility in self.responsibilities:
            if responsibility.source_ids:
                raise ValueError("design Responsibilities keep observed provenance in baseline_links, not source_ids")
            if responsibility.workflow is None:
                continue
            for node in responsibility.workflow.nodes:
                if not node.id.startswith("des-occ-"):
                    raise ValueError("design Workflow occurrence IDs must use the des-occ namespace")
                if node.responsibility_id not in responsibility_ids:
                    raise ValueError("design Workflow references an unknown Responsibility")
            if any(not edge.id.startswith("des-edge-") for edge in responsibility.workflow.edges):
                raise ValueError("design Workflow edge IDs must use the des-edge namespace")
        for link in self.feature_responsibility_links:
            if link.expected_feature_id not in feature_ids or link.responsibility_id not in responsibility_ids:
                raise ValueError("design feature link has an unknown endpoint")
        semantic_ids = feature_ids | responsibility_ids
        if any(link.design_id not in semantic_ids for link in self.baseline_links):
            raise ValueError("design baseline link has an unknown design endpoint")
        return self


class DesignWorkspace(DesignRecord):
    id: str
    project_id: str
    title: str
    base_observed_revision_id: str
    base_code_snapshot_id: str
    status: Literal[
        "draft", "in_review", "approved", "exported", "implementing", "verifying",
        "converged", "needs_revision", "cancelled",
    ] = "draft"
    current_design_revision_id: str
    created_by: str
    created_at: str
    updated_at: str


class DesignOperation(DesignRecord):
    kind: Literal[
        "set_intent", "upsert_expected_feature", "remove_expected_feature",
        "upsert_responsibility", "remove_responsibility", "set_workflow",
        "upsert_feature_link", "remove_feature_link", "set_unresolved_questions",
        "set_acceptance_criteria",
    ]
    summary: str | None = None
    expected_feature: ExpectedFeature | None = None
    expected_feature_id: str | None = None
    responsibility: Responsibility | None = None
    responsibility_id: str | None = None
    workflow: Workflow | None = None
    feature_link: FeatureResponsibilityLink | None = None
    feature_link_id: str | None = None
    unresolved_questions: list[str] | None = None
    acceptance_criteria: list[str] | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "DesignOperation":
        required = {
            "set_intent": self.summary is not None,
            "upsert_expected_feature": self.expected_feature is not None,
            "remove_expected_feature": self.expected_feature_id is not None,
            "upsert_responsibility": self.responsibility is not None,
            "remove_responsibility": self.responsibility_id is not None,
            "set_workflow": self.responsibility_id is not None,
            "upsert_feature_link": self.feature_link is not None,
            "remove_feature_link": self.feature_link_id is not None,
            "set_unresolved_questions": self.unresolved_questions is not None,
            "set_acceptance_criteria": self.acceptance_criteria is not None,
        }[self.kind]
        if not required:
            raise ValueError(f"design operation {self.kind!r} is missing its payload")
        identifiers = [
            self.expected_feature_id,
            self.responsibility_id,
            self.feature_link_id,
            self.expected_feature.id if self.expected_feature else None,
            self.responsibility.id if self.responsibility else None,
            self.feature_link.id if self.feature_link else None,
        ]
        if any(value and (value.startswith("obs-") or value.startswith("observed-")) for value in identifiers):
            raise ValueError("observed identities cannot be mutation targets in a design operation")
        expected_ids = [
            self.expected_feature_id,
            self.expected_feature.id if self.expected_feature else None,
        ]
        responsibility_ids = [
            self.responsibility_id,
            self.responsibility.id if self.responsibility else None,
        ]
        link_ids = [self.feature_link_id, self.feature_link.id if self.feature_link else None]
        if any(value and not value.startswith("des-feature-") for value in expected_ids):
            raise ValueError("expected feature operation targets must use the des-feature namespace")
        if any(value and not value.startswith("des-resp-") for value in responsibility_ids):
            raise ValueError("Responsibility operation targets must use the des-resp namespace")
        if any(value and not value.startswith("des-link-") for value in link_ids):
            raise ValueError("feature-link operation targets must use the des-link namespace")
        return self


class DesignOperationRecord(DesignRecord):
    id: str
    workspace_id: str
    base_design_revision_id: str
    result_design_revision_id: str
    operation_index: int = Field(ge=0)
    operation: DesignOperation
    actor: str
    rationale: str
    created_at: str


def seed_design_from_observation(
    observed: ObservedModelRevision,
    *,
    workspace_id: str,
    title: str,
    actor: str,
    rationale: str,
    created_at: str | None = None,
) -> DesignRevision:
    """Clone observed values into an independent design namespace."""
    timestamp = created_at or datetime.now(UTC).isoformat()
    responsibility_ids = {
        item.id: _scoped_id("des-resp", workspace_id, item.id) for item in observed.responsibilities
    }
    responsibilities = []
    baseline_links: list[DesignBaselineLink] = []
    for source in observed.responsibilities:
        workflow = None
        if source.workflow is not None:
            node_ids = {
                item.id: _scoped_id("des-occ", workspace_id, source.id, item.id)
                for item in source.workflow.nodes
            }
            workflow = Workflow(
                entry_node_ids=[node_ids[item] for item in source.workflow.entry_node_ids],
                nodes=[WorkflowNode(
                    id=node_ids[item.id], responsibility_id=responsibility_ids[item.responsibility_id],
                    note=item.note,
                ) for item in source.workflow.nodes],
                edges=[WorkflowEdge(
                    id=_scoped_id("des-edge", workspace_id, source.id, item.id),
                    source_node_id=node_ids[item.source_node_id],
                    target_node_id=node_ids[item.target_node_id],
                    kind=item.kind,
                    label=item.label,
                ) for item in source.workflow.edges],
            )
        design_id = responsibility_ids[source.id]
        responsibilities.append(source.model_copy(update={
            "id": design_id, "workflow": workflow, "status": "draft", "source_ids": [],
        }))
        baseline_links.append(DesignBaselineLink(
            design_kind="responsibility", design_id=design_id,
            observed_kind="responsibility", observed_id=source.id,
        ))

    expected_features = []
    feature_links = []
    for capability in observed.capabilities:
        feature_id = _scoped_id("des-feature", workspace_id, capability.id)
        expected_features.append(ExpectedFeature(
            id=feature_id, name=capability.name, description=capability.description,
        ))
        baseline_links.append(DesignBaselineLink(
            design_kind="expected_feature", design_id=feature_id,
            observed_kind="capability", observed_id=capability.id,
        ))
        feature_links.append(FeatureResponsibilityLink(
            id=_scoped_id("des-link", workspace_id, feature_id, capability.responsibility_id),
            expected_feature_id=feature_id,
            responsibility_id=responsibility_ids[capability.responsibility_id],
        ))

    return _make_revision(
        workspace_id=workspace_id,
        parent_revision_id=None,
        base_observed_revision_id=observed.id,
        title=title,
        summary=f"Target design seeded from observed revision {observed.id}.",
        expected_features=expected_features,
        responsibilities=responsibilities,
        feature_responsibility_links=feature_links,
        baseline_links=baseline_links,
        rationale=rationale,
        unresolved_questions=[],
        acceptance_criteria=[],
        created_by=actor,
        created_at=timestamp,
    )


def apply_design_operations(
    base: DesignRevision,
    operations: list[DesignOperation],
    *,
    actor: str,
    rationale: str,
    created_at: str | None = None,
) -> DesignRevision:
    if not operations:
        raise ValueError("at least one design operation is required")
    if not rationale.strip():
        raise ValueError("a rationale is required for every design revision")
    features = {item.id: item for item in base.expected_features}
    responsibilities = {item.id: item for item in base.responsibilities}
    links = {item.id: item for item in base.feature_responsibility_links}
    summary = base.summary
    questions = list(base.unresolved_questions)
    criteria = list(base.acceptance_criteria)
    for operation in operations:
        if operation.kind == "set_intent":
            summary = operation.summary or ""
        elif operation.kind == "upsert_expected_feature":
            assert operation.expected_feature is not None
            features[operation.expected_feature.id] = operation.expected_feature
        elif operation.kind == "remove_expected_feature":
            features.pop(operation.expected_feature_id or "", None)
        elif operation.kind == "upsert_responsibility":
            assert operation.responsibility is not None
            responsibilities[operation.responsibility.id] = operation.responsibility
        elif operation.kind == "remove_responsibility":
            responsibilities.pop(operation.responsibility_id or "", None)
        elif operation.kind == "set_workflow":
            target = responsibilities.get(operation.responsibility_id or "")
            if target is None:
                raise ValueError("set_workflow targets an unknown design Responsibility")
            responsibilities[target.id] = target.model_copy(update={"workflow": operation.workflow})
        elif operation.kind == "upsert_feature_link":
            assert operation.feature_link is not None
            links[operation.feature_link.id] = operation.feature_link
        elif operation.kind == "remove_feature_link":
            links.pop(operation.feature_link_id or "", None)
        elif operation.kind == "set_unresolved_questions":
            questions = operation.unresolved_questions or []
        elif operation.kind == "set_acceptance_criteria":
            criteria = [item.strip() for item in operation.acceptance_criteria or [] if item.strip()]

    return _make_revision(
        workspace_id=base.workspace_id,
        parent_revision_id=base.id,
        base_observed_revision_id=base.base_observed_revision_id,
        title=base.title,
        summary=summary,
        expected_features=list(features.values()),
        responsibilities=list(responsibilities.values()),
        feature_responsibility_links=list(links.values()),
        baseline_links=base.baseline_links,
        rationale=rationale,
        unresolved_questions=questions,
        acceptance_criteria=criteria,
        created_by=actor,
        created_at=created_at or datetime.now(UTC).isoformat(),
    )


def _make_revision(**values: Any) -> DesignRevision:
    identity = {
        key: [item.model_dump(mode="json") for item in value] if isinstance(value, list) and value and isinstance(value[0], BaseModel)
        else value
        for key, value in values.items()
        if key not in {"created_at", "created_by", "rationale"}
    }
    digest = _digest(identity)
    return DesignRevision(id=f"design-{digest[:24]}", content_digest=digest, **values)


def _unique_ids(items: list[Any], label: str) -> set[str]:
    identifiers = [item.id for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"duplicate {label} IDs")
    return set(identifiers)


def _assert_feature_acyclic(features: list[ExpectedFeature]) -> None:
    parents = {item.id: item.parent_id for item in features}
    for feature_id in parents:
        seen: set[str] = set()
        current: str | None = feature_id
        while current is not None:
            if current in seen:
                raise ValueError("expected feature hierarchy contains a cycle")
            seen.add(current)
            current = parents.get(current)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _scoped_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}-{digest}"
