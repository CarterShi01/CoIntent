"""Human review and deterministic implementation export for 0.4 target designs."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .design import DesignRevision
from .models import Responsibility, Workflow
from .observation import ObservedModelRevision


class DeliveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SemanticDesignChange(DeliveryRecord):
    id: str
    kind: Literal["expected_feature", "responsibility", "feature_mapping"]
    change_type: Literal["added", "removed", "changed"]
    design_id: str | None = None
    baseline_observed_id: str | None = None
    name: str
    fields: list[str] = Field(default_factory=list)


class AcceptanceCriterion(DeliveryRecord):
    id: str
    statement: str
    related_change_ids: list[str]


class DesignReview(DeliveryRecord):
    schema_version: Literal["cointent.design-review/0.4"] = "cointent.design-review/0.4"
    id: str
    project_id: str
    workspace_id: str
    design_revision_id: str
    base_observed_revision_id: str
    status: Literal["in_review", "approved"] = "in_review"
    changes: list[SemanticDesignChange]
    acceptance_criteria: list[AcceptanceCriterion]
    submitted_by: str
    submitted_at: str
    content_digest: str


class DesignApproval(DeliveryRecord):
    schema_version: Literal["cointent.design-approval/0.4"] = "cointent.design-approval/0.4"
    id: str
    review_id: str
    project_id: str
    workspace_id: str
    design_revision_id: str
    actor: str
    approved_at: str
    content_digest: str


class ImplementationChangeBundle(DeliveryRecord):
    schema_version: Literal["cointent.implementation-change/0.4"] = "cointent.implementation-change/0.4"
    id: str
    project_id: str
    workspace_id: str
    design_revision_id: str
    base_observed_revision_id: str
    base_code_snapshot_id: str
    review_id: str
    approval_id: str
    changes: list[SemanticDesignChange]
    acceptance_criteria: list[AcceptanceCriterion]
    evidence_context: list[dict[str, Any]]
    operation_ids: list[str]
    agent_prompt: str
    approved_by: str
    approved_at: str
    content_digest: str
    created_at: str


class VerificationClaim(DeliveryRecord):
    id: str
    kind: Literal["expected_feature", "responsibility"]
    status: Literal["matched", "missing", "unexpected", "ambiguous", "stale"]
    target_design_id: str | None = None
    observed_id: str | None = None
    name: str
    explanation: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class VerificationReport(DeliveryRecord):
    schema_version: Literal["cointent.verification-report/0.4"] = "cointent.verification-report/0.4"
    id: str
    project_id: str
    workspace_id: str
    implementation_bundle_id: str
    design_revision_id: str
    baseline_observed_revision_id: str
    observed_revision_id: str
    observed_code_snapshot_id: str
    status: Literal["awaiting_human_review"] = "awaiting_human_review"
    claims: list[VerificationClaim]
    summary: dict[str, int]
    content_digest: str
    created_at: str


class VerificationDecision(DeliveryRecord):
    schema_version: Literal["cointent.verification-decision/0.4"] = "cointent.verification-decision/0.4"
    id: str
    report_id: str
    project_id: str
    workspace_id: str
    decision: Literal["converged", "needs_revision"]
    notes: str
    actor: str
    decided_at: str
    content_digest: str


def semantic_target_diff(
    design: DesignRevision, observed: ObservedModelRevision,
) -> list[SemanticDesignChange]:
    if design.base_observed_revision_id != observed.id:
        raise ValueError("design and observed baseline coordinates do not match")
    changes: list[SemanticDesignChange] = []
    design_features = {item.id: item for item in design.expected_features}
    design_responsibilities = {item.id: item for item in design.responsibilities}
    observed_capabilities = {item.id: item for item in observed.capabilities}
    observed_responsibilities = {item.id: item for item in observed.responsibilities}
    feature_origins = {
        item.design_id: item.observed_id for item in design.baseline_links
        if item.design_kind == "expected_feature" and item.observed_kind == "capability"
    }
    responsibility_origins = {
        item.design_id: item.observed_id for item in design.baseline_links
        if item.design_kind == "responsibility" and item.observed_kind == "responsibility"
    }
    observed_to_design = {observed_id: design_id for design_id, observed_id in responsibility_origins.items()}

    for design_id, observed_id in feature_origins.items():
        current = design_features.get(design_id)
        baseline = observed_capabilities.get(observed_id)
        if baseline is None:
            continue
        if current is None:
            changes.append(_change("expected_feature", "removed", None, observed_id, baseline.name, []))
            continue
        fields = [field for field, before, after in (
            ("name", baseline.name, current.name),
            ("description", baseline.description, current.description),
        ) if before != after]
        if fields:
            changes.append(_change("expected_feature", "changed", design_id, observed_id, current.name, fields))
    for design_id, current in design_features.items():
        if design_id not in feature_origins:
            changes.append(_change("expected_feature", "added", design_id, None, current.name, ["name", "description"]))

    for design_id, observed_id in responsibility_origins.items():
        current = design_responsibilities.get(design_id)
        baseline = observed_responsibilities.get(observed_id)
        if baseline is None:
            continue
        if current is None:
            changes.append(_change("responsibility", "removed", None, observed_id, baseline.name, []))
            continue
        fields = [field for field, before, after in (
            ("name", baseline.name, current.name),
            ("description", baseline.description, current.description),
            ("data_members", baseline.data_members, current.data_members),
            ("inputs", baseline.inputs, current.inputs),
            ("outputs", baseline.outputs, current.outputs),
            ("workflow", _workflow_signature(baseline.workflow, observed_to_design),
             _workflow_signature(current.workflow, {})),
        ) if before != after]
        if fields:
            changes.append(_change("responsibility", "changed", design_id, observed_id, current.name, fields))
    for design_id, current in design_responsibilities.items():
        if design_id not in responsibility_origins:
            changes.append(_change("responsibility", "added", design_id, None, current.name,
                                   ["name", "description", "workflow"]))

    expected_mappings = {
        (design_feature_id, observed_to_design[capability.responsibility_id], "realizes")
        for design_feature_id, observed_capability_id in feature_origins.items()
        if (capability := observed_capabilities.get(observed_capability_id)) is not None
        and capability.responsibility_id in observed_to_design
    }
    target_mappings = {
        (item.expected_feature_id, item.responsibility_id, item.kind)
        for item in design.feature_responsibility_links
    }
    if expected_mappings != target_mappings:
        changes.append(_change(
            "feature_mapping", "changed", None, None, "Expected function mapping", ["links"],
        ))
    return sorted(changes, key=lambda item: (item.kind, item.change_type, item.name, item.id))


def build_design_review(
    *,
    project_id: str,
    workspace_id: str,
    design: DesignRevision,
    observed: ObservedModelRevision,
    acceptance_statements: list[str],
    submitted_by: str,
    submitted_at: str,
) -> DesignReview:
    changes = semantic_target_diff(design, observed)
    if not changes:
        raise ValueError("the target has no semantic changes to review")
    statements = [value.strip() for value in acceptance_statements if value.strip()]
    if not statements:
        raise ValueError("material design changes require at least one acceptance criterion")
    change_ids = [item.id for item in changes]
    criteria = [AcceptanceCriterion(
        id=_scoped_id("criterion", design.id, str(index), statement),
        statement=statement,
        related_change_ids=change_ids,
    ) for index, statement in enumerate(statements)]
    identity = {
        "project_id": project_id,
        "workspace_id": workspace_id,
        "design_revision_id": design.id,
        "base_observed_revision_id": observed.id,
        "changes": [item.model_dump(mode="json") for item in changes],
        "acceptance_criteria": [item.model_dump(mode="json") for item in criteria],
    }
    digest = _digest(identity)
    return DesignReview(
        id=f"review-{digest[:24]}",
        project_id=project_id,
        workspace_id=workspace_id,
        design_revision_id=design.id,
        base_observed_revision_id=observed.id,
        changes=changes,
        acceptance_criteria=criteria,
        submitted_by=submitted_by,
        submitted_at=submitted_at,
        content_digest=digest,
    )


def build_approval(review: DesignReview, *, actor: str, approved_at: str) -> DesignApproval:
    if not actor.strip():
        raise ValueError("approval actor is required")
    identity = {
        "review_id": review.id,
        "project_id": review.project_id,
        "workspace_id": review.workspace_id,
        "design_revision_id": review.design_revision_id,
        "actor": actor,
        "approved_at": approved_at,
    }
    digest = _digest(identity)
    return DesignApproval(
        id=f"approval-{digest[:24]}",
        review_id=review.id,
        project_id=review.project_id,
        workspace_id=review.workspace_id,
        design_revision_id=review.design_revision_id,
        actor=actor,
        approved_at=approved_at,
        content_digest=digest,
    )


def build_implementation_bundle(
    *,
    review: DesignReview,
    approval: DesignApproval,
    base_code_snapshot_id: str,
    evidence_context: list[dict[str, Any]],
    operation_ids: list[str],
    created_at: str,
) -> ImplementationChangeBundle:
    prompt = (
        f"Implement CoIntent change bundle for design revision {review.design_revision_id} against "
        f"code snapshot {base_code_snapshot_id}. Treat the listed semantic changes and acceptance criteria "
        "as the contract. Inspect the linked source evidence, modify code through the normal coding workflow, "
        "and do not write CoIntent observation or design storage directly. After tests pass, produce a new full "
        "code snapshot and Understand Anything observation for verification."
    )
    identity = {
        "project_id": review.project_id,
        "workspace_id": review.workspace_id,
        "design_revision_id": review.design_revision_id,
        "base_observed_revision_id": review.base_observed_revision_id,
        "base_code_snapshot_id": base_code_snapshot_id,
        "review_id": review.id,
        "approval_id": approval.id,
        "changes": [item.model_dump(mode="json") for item in review.changes],
        "acceptance_criteria": [item.model_dump(mode="json") for item in review.acceptance_criteria],
        "evidence_context": evidence_context,
        "operation_ids": operation_ids,
        "agent_prompt": prompt,
        "approved_by": approval.actor,
        "approved_at": approval.approved_at,
    }
    digest = _digest(identity)
    return ImplementationChangeBundle(
        id=f"implementation-{digest[:24]}",
        content_digest=digest,
        created_at=created_at,
        **identity,
    )


def build_verification_report(
    *,
    bundle: ImplementationChangeBundle,
    design: DesignRevision,
    baseline: ObservedModelRevision,
    observed: ObservedModelRevision,
    created_at: str,
) -> VerificationReport:
    if bundle.design_revision_id != design.id or bundle.base_observed_revision_id != baseline.id:
        raise ValueError("verification inputs do not match the implementation bundle coordinates")
    if observed.project_id != bundle.project_id:
        raise ValueError("verification observation belongs to a different project")
    claims: list[VerificationClaim] = []
    if observed.code_snapshot_id == bundle.base_code_snapshot_id:
        for kind, items in (
            ("expected_feature", design.expected_features),
            ("responsibility", design.responsibilities),
        ):
            claims.extend(VerificationClaim(
                id=_scoped_id("verification-claim", bundle.id, kind, item.id, "stale"),
                kind=kind,
                status="stale",
                target_design_id=item.id,
                name=item.name,
                explanation="The selected observation still points to the pre-implementation code snapshot.",
            ) for item in items)
    else:
        claims.extend(_match_claims(
            bundle.id,
            "expected_feature",
            [(item.id, item.name, item.description) for item in design.expected_features],
            [(item.id, item.name, item.description) for item in observed.capabilities],
            observed,
        ))
        claims.extend(_match_claims(
            bundle.id,
            "responsibility",
            [(item.id, item.name, item.description) for item in design.responsibilities],
            [(item.id, item.name, item.description) for item in observed.responsibilities],
            observed,
        ))
        target_feature_names = {_normalized(item.name) for item in design.expected_features}
        baseline_feature_names = {_normalized(item.name) for item in baseline.capabilities}
        for item in observed.capabilities:
            if _normalized(item.name) not in target_feature_names | baseline_feature_names:
                claims.append(_unexpected_claim(bundle.id, "expected_feature", item.id, item.name, observed))
        target_responsibility_names = {_normalized(item.name) for item in design.responsibilities}
        baseline_responsibility_names = {_normalized(item.name) for item in baseline.responsibilities}
        for item in observed.responsibilities:
            if _normalized(item.name) not in target_responsibility_names | baseline_responsibility_names:
                claims.append(_unexpected_claim(bundle.id, "responsibility", item.id, item.name, observed))

    claims.sort(key=lambda item: (item.status, item.kind, item.name, item.id))
    summary = {status: sum(item.status == status for item in claims) for status in (
        "matched", "missing", "unexpected", "ambiguous", "stale",
    )}
    identity = {
        "project_id": bundle.project_id,
        "workspace_id": bundle.workspace_id,
        "implementation_bundle_id": bundle.id,
        "design_revision_id": design.id,
        "baseline_observed_revision_id": baseline.id,
        "observed_revision_id": observed.id,
        "observed_code_snapshot_id": observed.code_snapshot_id,
        "claims": [item.model_dump(mode="json") for item in claims],
        "summary": summary,
    }
    digest = _digest(identity)
    return VerificationReport(
        id=f"verification-{digest[:24]}",
        content_digest=digest,
        created_at=created_at,
        **identity,
    )


def build_verification_decision(
    report: VerificationReport,
    *,
    decision: Literal["converged", "needs_revision"],
    notes: str,
    actor: str,
    decided_at: str,
) -> VerificationDecision:
    if not actor.strip() or actor in {"agent", "local-agent", "cointent-agent"}:
        raise ValueError("verification decision requires an authenticated human actor")
    blockers = sum(report.summary.get(key, 0) for key in ("missing", "ambiguous", "stale"))
    if decision == "converged" and blockers:
        raise ValueError("verification cannot converge while missing, ambiguous, or stale claims remain")
    if not notes.strip():
        raise ValueError("human verification notes are required")
    identity = {
        "report_id": report.id,
        "project_id": report.project_id,
        "workspace_id": report.workspace_id,
        "decision": decision,
        "notes": notes.strip(),
        "actor": actor,
        "decided_at": decided_at,
    }
    digest = _digest(identity)
    return VerificationDecision(
        id=f"verification-decision-{digest[:24]}", content_digest=digest, **identity,
    )


def _match_claims(
    bundle_id: str,
    kind: Literal["expected_feature", "responsibility"],
    targets: list[tuple[str, str, str]],
    observed_items: list[tuple[str, str, str]],
    observed: ObservedModelRevision,
) -> list[VerificationClaim]:
    by_name: dict[str, list[tuple[str, str, str]]] = {}
    for observed_id, name, description in observed_items:
        by_name.setdefault(_normalized(name), []).append((observed_id, name, description))
    claims = []
    for target_id, name, description in targets:
        candidates = by_name.get(_normalized(name), [])
        if not candidates:
            claims.append(VerificationClaim(
                id=_scoped_id("verification-claim", bundle_id, kind, target_id, "missing"),
                kind=kind,
                status="missing",
                target_design_id=target_id,
                name=name,
                explanation="No uniquely named claim with new-code evidence exists in the selected observation.",
            ))
        elif len(candidates) > 1:
            claims.append(VerificationClaim(
                id=_scoped_id("verification-claim", bundle_id, kind, target_id, "ambiguous"),
                kind=kind,
                status="ambiguous",
                target_design_id=target_id,
                name=name,
                explanation=f"{len(candidates)} observed claims share this semantic name; human resolution is required.",
                evidence=_evidence_for(observed, {item[0] for item in candidates}),
            ))
        else:
            observed_id, _, observed_description = candidates[0]
            wording_matches = _normalized(description) == _normalized(observed_description)
            claims.append(VerificationClaim(
                id=_scoped_id(
                    "verification-claim", bundle_id, kind, target_id, observed_id,
                    "matched" if wording_matches else "ambiguous",
                ),
                kind=kind,
                status="matched" if wording_matches else "ambiguous",
                target_design_id=target_id,
                observed_id=observed_id,
                name=name,
                explanation=(
                    "A unique same-named and same-worded observed claim is backed by the post-implementation source coordinate."
                    if wording_matches else
                    "The name matches uniquely, but the target and observed descriptions differ; human resolution is required."
                ),
                evidence=_evidence_for(observed, {observed_id}),
            ))
    return claims


def _unexpected_claim(
    bundle_id: str,
    kind: Literal["expected_feature", "responsibility"],
    observed_id: str,
    name: str,
    observed: ObservedModelRevision,
) -> VerificationClaim:
    return VerificationClaim(
        id=_scoped_id("verification-claim", bundle_id, kind, observed_id, "unexpected"),
        kind=kind,
        status="unexpected",
        observed_id=observed_id,
        name=name,
        explanation="This new-code claim exists in neither the approved target nor its observed baseline.",
        evidence=_evidence_for(observed, {observed_id}),
    )


def _evidence_for(observed: ObservedModelRevision, subject_ids: set[str]) -> list[dict[str, Any]]:
    return [
        item.model_dump(mode="json") for item in observed.bindings if item.subject_id in subject_ids
    ]


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _change(
    kind: Literal["expected_feature", "responsibility", "feature_mapping"],
    change_type: Literal["added", "removed", "changed"],
    design_id: str | None,
    baseline_id: str | None,
    name: str,
    fields: list[str],
) -> SemanticDesignChange:
    return SemanticDesignChange(
        id=_scoped_id("change", kind, change_type, design_id or "", baseline_id or "", name),
        kind=kind,
        change_type=change_type,
        design_id=design_id,
        baseline_observed_id=baseline_id,
        name=name,
        fields=fields,
    )


def _workflow_signature(workflow: Workflow | None, id_map: dict[str, str]) -> Any:
    if workflow is None:
        return None
    nodes = {item.id: id_map.get(item.responsibility_id, item.responsibility_id) for item in workflow.nodes}
    return {
        "entries": [nodes[item] for item in workflow.entry_node_ids],
        "nodes": [(nodes[item.id], item.note) for item in workflow.nodes],
        "edges": [
            (nodes[item.source_node_id], nodes[item.target_node_id], item.kind, item.label)
            for item in workflow.edges
        ],
    }


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _scoped_id(prefix: str, *parts: str) -> str:
    return f"{prefix}-{hashlib.sha256(chr(0).join(parts).encode()).hexdigest()[:20]}"
