"""Contexture declaration: CoIntent's fixed agent capability graph."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from contexture import Channels, Contexture, Role, Skill, Tool, current_principal

from .models import ModelPatch, ProjectModel
from .repository import CoIntentRepository


class CoIntentChannels(Channels):
    def __init__(self) -> None:
        database = os.environ.get("COINTENT_DB_PATH", "runtime/cointent.db")
        self.repository = CoIntentRepository(Path(database))


def _repository(node: Tool) -> CoIntentRepository:
    if not isinstance(node.channels, CoIntentChannels):
        raise RuntimeError("CoIntent repository channel is unavailable")
    return node.channels.repository


def _actor(fallback: str = "local-agent") -> str:
    principal = current_principal()
    return principal.subject if principal is not None else fallback


class ListProjects(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-projects", description="List modeled projects and their current versions.", read_only=True)

    async def invoke(self) -> dict[str, Any]:
        return {"projects": _repository(self).list_projects()}


class Health(Tool):
    def __init__(self) -> None:
        super().__init__(name="health", description="Report whether the CoIntent model repository is available.", read_only=True)

    async def invoke(self) -> dict[str, Any]:
        repository = _repository(self)
        return {"ok": True, "service": "cointent", "projects": len(repository.list_projects())}


class CreateProject(Tool):
    def __init__(self) -> None:
        super().__init__(name="create-project", description="Create an empty, versioned CoIntent project.", read_only=False)

    async def invoke(self, project_id: str, name: str, repository: str = "") -> dict[str, Any]:
        return _repository(self).create_project(project_id, name, repository)


class InspectModel(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-model", description="Read the accepted goal, role, responsibility, and mapping model.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", version: int | None = None) -> dict[str, Any]:
        return _repository(self).get_model(project_id, version)


class GetOverview(Tool):
    def __init__(self) -> None:
        super().__init__(name="get-overview", description="Summarize model size, current scan, findings, and pending proposals.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        return _repository(self).overview(project_id)


class RecordIntent(Tool):
    def __init__(self) -> None:
        super().__init__(name="record-intent", description="Preserve a human-agent exchange as evidence for later model changes.", read_only=False)

    async def invoke(self, project_id: str, speaker: str, content: str, source_ref: str = "") -> dict[str, Any]:
        return _repository(self).record_intent(project_id, speaker, content, source_ref)


class ListIntentSources(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-intent-sources", description="Read the source exchanges behind design decisions.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", limit: int = 100) -> dict[str, Any]:
        return {"sources": _repository(self).list_intent_sources(project_id, limit)}


class ProposeModelPatch(Tool):
    def __init__(self) -> None:
        super().__init__(name="propose-model-patch", description="Validate and stage a semantic model patch without changing the accepted baseline.", read_only=False)

    async def invoke(
        self, project_id: str, base_version: int, patch: ModelPatch, rationale: str,
        evidence_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return _repository(self).propose_patch(
            project_id, base_version, patch.model_dump(), rationale=rationale,
            evidence_ids=evidence_ids or [], actor=_actor(),
        )


class AssessModelQuality(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="assess-model-quality",
            description="Report structural review signals without treating heuristics as design verdicts.",
            read_only=True,
        )

    async def invoke(self, project_id: str = "idea-factory", version: int | None = None) -> dict[str, Any]:
        response = _repository(self).get_model(project_id, version)
        model = ProjectModel.model_validate(response["model"])
        owned_goals = {goal_id for item in model.responsibilities for goal_id in item.goal_ids}
        roles_with_responsibility = {item.role_id for item in model.responsibilities}
        related_roles = {
            role_id
            for relation in model.relations
            for role_id in (relation.source_role_id, relation.target_role_id)
        }
        parent_roles = {role.parent_id for role in model.roles if role.parent_id is not None}
        mapped_roles = {link.role_id for link in model.trace_links}
        signals: list[dict[str, Any]] = []

        def add(kind: str, element_type: str, element_id: str, message: str) -> None:
            signals.append({
                "kind": kind,
                "element_type": element_type,
                "element_id": element_id,
                "message": message,
            })

        for goal in model.goals:
            if goal.id not in owned_goals:
                add("unowned_goal", "goal", goal.id, "目标尚未关联任何职责。")
        for role in model.roles:
            if role.id not in parent_roles and role.id not in roles_with_responsibility:
                add("empty_leaf_role", "role", role.id, "叶子 Role 尚未承担职责。")
            if role.parent_id is not None and role.id not in related_roles:
                add("isolated_role", "role", role.id, "Role 尚未声明跨边界协作关系。")
            if role.id not in mapped_roles:
                add("unmapped_role", "role", role.id, "Role 尚无实现证据映射。")
        for item in model.responsibilities:
            if not item.goal_ids:
                add("goal_free_responsibility", "responsibility", item.id, "职责尚未说明服务于哪个目标。")
            if not item.inputs and not item.outputs and not item.constraints:
                add("thin_contract", "responsibility", item.id, "职责尚未描述输入、输出或约束；请判断是否确有必要。")

        return {
            "project_id": project_id,
            "version": response["version"],
            "method": "CoIntent selective role-model review",
            "verdict": "human_or_agent_judgment_required",
            "signals": signals,
            "counts": {
                "signals": len(signals),
                "goals": len(model.goals),
                "roles": len(model.roles),
                "responsibilities": len(model.responsibilities),
            },
        }


class ListProposals(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-proposals", description="List pending or resolved model proposals with semantic diffs.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", status: str = "pending") -> dict[str, Any]:
        return {"proposals": _repository(self).list_proposals(project_id, status)}


class ResolveProposal(Tool):
    def __init__(self) -> None:
        super().__init__(name="resolve-proposal", description="Accept or reject a reviewed proposal; acceptance creates a model version.", read_only=False)

    async def invoke(self, proposal_id: str, decision: str, resolution: str = "") -> dict[str, Any]:
        if decision not in {"accept", "reject"}:
            raise ValueError("decision must be accept or reject")
        return _repository(self).resolve_proposal(
            proposal_id, accept=decision == "accept", actor=_actor("human"), resolution=resolution,
        )


class IngestSnapshot(Tool):
    def __init__(self) -> None:
        super().__init__(name="ingest-snapshot", description="Store a read-only repository fact snapshot and derive incremental alignment findings.", read_only=False)

    async def invoke(self, project_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        return _repository(self).ingest_snapshot(project_id, snapshot)


class ListSnapshots(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-snapshots", description="List observed repository snapshots and their structural deltas.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", limit: int = 20) -> dict[str, Any]:
        return {"snapshots": _repository(self).list_snapshots(project_id, limit)}


class ListFindings(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-findings", description="List open or resolved implementation-alignment findings.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", status: str = "open") -> dict[str, Any]:
        return {"findings": _repository(self).list_findings(project_id, status)}


class ResolveFinding(Tool):
    def __init__(self) -> None:
        super().__init__(name="resolve-finding", description="Record how an implementation-alignment finding was handled.", read_only=False)

    async def invoke(self, finding_id: str, status: str, resolution: str) -> dict[str, Any]:
        return _repository(self).resolve_finding(finding_id, status, resolution)


class CompareVersions(Tool):
    def __init__(self) -> None:
        super().__init__(name="compare-versions", description="Return a semantic diff between two accepted model versions.", read_only=True)

    async def invoke(self, project_id: str, from_version: int, to_version: int) -> dict[str, Any]:
        return _repository(self).compare_versions(project_id, from_version, to_version)


class ConvergeDesign(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="converge-design",
            description="Turn an incomplete idea into reviewable goals, responsibilities, and role boundaries.",
            uses=(
                "project-alignment/design-convergence/inspect-model",
                "project-alignment/design-convergence/record-intent",
                "project-alignment/design-convergence/assess-model-quality",
                "project-alignment/design-convergence/propose-model-patch",
            ),
            instructions=(
                "Write human-facing model content and rationale in Chinese; keep stable IDs and implementation paths "
                "in English. Preserve the user's relevant wording with record-intent and keep assumptions explicit. "
                "Use a selective method, not a formal-method checklist: refine goals only until an outcome is "
                "assignable and verifiable (KAOS-derived); define each Role by one coherent purpose, the behavior or "
                "knowledge it is responsible for, and its collaborators (OOram/RDD-derived); add inputs, outputs, "
                "and constraints only where they clarify a boundary (IDEF0-derived). A Role is not a class, service, "
                "directory, person, or Agent, although any of those may realize it. Inspect the current model and its "
                "quality signals, then ask only questions that could change goals, constraints, ownership, or role "
                "boundaries. Propose a semantic patch against the exact current version; never rewrite the accepted "
                "baseline directly. Explain uncertainty and ask the human to accept or reject the proposal."
            ),
        )


class ReviewRoleModel(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="review-role-model",
            description="Review a Role Model for intent fidelity, coherent ownership, useful contracts, and implementation independence.",
            uses=(
                "project-alignment/design-convergence/inspect-model",
                "project-alignment/design-convergence/list-intent-sources",
                "project-alignment/design-convergence/assess-model-quality",
                "project-alignment/design-convergence/propose-model-patch",
            ),
            instructions=(
                "Review in this order: (1) source fidelity—separate stated intent, accepted decisions, assumptions, "
                "and code-derived hypotheses; (2) goal coverage—each leaf goal should be assignable and have a "
                "credible way to verify it, without pretending formal KAOS completeness; (3) responsibility "
                "ownership—look for orphan, conflicting, fragmented, or god-role ownership using RDD cohesion; "
                "(4) collaboration—ensure boundary-crossing promises and dependencies are understandable in the "
                "OOram role network; (5) contracts—add inputs, outputs, or constraints only when they reduce ambiguity; "
                "(6) implementation independence—reject folder-tree, class-diagram, or deployment-topology mimicry; "
                "and (7) evidence—state uncertainty and preserve provenance. Treat assess-model-quality output as "
                "review prompts, never automatic failures. Return the review in Chinese. Stage fixes as a version-bound "
                "proposal and leave acceptance to the human."
            ),
        )


class MapImplementation(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="map-implementation",
            description="Interpret repository facts as evidence for a responsibility model without copying the file tree.",
            uses=(
                "project-alignment/design-convergence/inspect-model",
                "project-alignment/implementation-mapping/list-snapshots",
                "project-alignment/design-convergence/propose-model-patch",
            ),
            instructions=(
                "Apply the Software Reflexion Model pattern selectively: the accepted Role Model is normative, the "
                "repository snapshot is observed evidence, and TraceLinks are explicit mapping hypotheses. Start from "
                "purpose and responsibility, then use artifacts as supporting evidence. Prefer stable module, package, "
                "service, route, schema, and test boundaries; use many-to-many links at the coarsest useful level. "
                "Classify evidence as convergent, absent, divergent, boundary-changing, unmapped, or uncertain. Never "
                "equate a Role with a directory or class, and never infer desired intent from code alone. Write "
                "human-facing model content and rationale in Chinese; retain code paths and stable IDs in English."
            ),
        )


class ReviewImplementationChange(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="review-implementation-change",
            description="Decide whether a repository delta preserves or changes intended responsibilities.",
            uses=(
                "project-alignment/alignment-review/list-findings",
                "project-alignment/design-convergence/inspect-model",
                "project-alignment/design-convergence/propose-model-patch",
                "project-alignment/alignment-review/resolve-finding",
            ),
            instructions=(
                "Inspect each finding and its mapped roles. Classify the code change as internal implementation, "
                "design evolution, implementation defect, accepted exception, or uncertain. Never let observed code "
                "silently redefine intent. Propose a model patch only for a real design evolution, otherwise record "
                "the implementation action or uncertainty in the finding resolution. Use Reflexion-style comparison "
                "as evidence, not as authority, and write human-facing conclusions in Chinese."
            ),
        )


class DesignConvergence(Role):
    def __init__(self) -> None:
        super().__init__(
            name="design-convergence", description="Clarify intent and evolve the accepted responsibility model.",
            instructions="Use the design skill for judgment and Tools for evidence, proposals, and explicit decisions.",
            skills=[ConvergeDesign(), ReviewRoleModel()],
            tools=[Health(), ListProjects(), CreateProject(), InspectModel(), GetOverview(), RecordIntent(),
                   ListIntentSources(), AssessModelQuality(), ProposeModelPatch(), ListProposals(), ResolveProposal()],
        )


class ImplementationMapping(Role):
    def __init__(self) -> None:
        super().__init__(
            name="implementation-mapping", description="Connect observed repository facts to logical roles.",
            instructions="Ingest scanner output, inspect deltas, and map at the coarsest useful architectural level.",
            skills=[MapImplementation()], tools=[IngestSnapshot(), ListSnapshots()],
        )


class AlignmentReview(Role):
    def __init__(self) -> None:
        super().__init__(
            name="alignment-review", description="Review semantic drift between implementation and intended design.",
            instructions="Findings are evidence for review, not automatic verdicts. Resolve each with rationale.",
            skills=[ReviewImplementationChange()], tools=[ListFindings(), ResolveFinding()],
        )


class History(Role):
    def __init__(self) -> None:
        super().__init__(
            name="history", description="Explain how accepted design versions differ.",
            instructions="Compare immutable versions and connect changes to their recorded rationale.",
            tools=[CompareVersions()],
        )


class ProjectAlignment(Role):
    def __init__(self) -> None:
        super().__init__(
            name="project-alignment",
            description="Converge software intent and keep implementation aligned with accepted responsibility boundaries.",
            instructions=(
                "Choose design-convergence for intent and role changes, implementation-mapping for repository facts, "
                "alignment-review for drift, and history for accepted version differences."
            ),
            children=[DesignConvergence(), ImplementationMapping(), AlignmentReview(), History()],
        )


app = Contexture(name="cointent", roots=(ProjectAlignment,), channels=CoIntentChannels)
