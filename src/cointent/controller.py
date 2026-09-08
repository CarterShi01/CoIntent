"""Contexture declaration for CoIntent's agent-native application surface."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from contexture import Channels, Contexture, Role, Skill, Tool, current_principal

from .models import ModelPatch, ProjectModel, TraceLink
from .repository import CoIntentRepository
from .scanner import RepositorySnapshot


class CoIntentChannels(Channels):
    def __init__(self) -> None:
        database = Path(os.environ.get("COINTENT_DB_PATH", "runtime/cointent.db"))
        asset_root = Path(os.environ.get("COINTENT_DATA_ROOT", str(database.parent / "projects")))
        self.repository = CoIntentRepository(database, asset_root)


def _repository(node: Tool) -> CoIntentRepository:
    if not isinstance(node.channels, CoIntentChannels):
        raise RuntimeError("CoIntent repository channel is unavailable")
    return node.channels.repository


def _actor(fallback: str = "local-agent") -> str:
    principal = current_principal()
    return principal.subject if principal is not None else fallback


class Health(Tool):
    def __init__(self) -> None:
        super().__init__(name="health", description="Report service and project-store health.", read_only=True)

    async def invoke(self) -> dict[str, Any]:
        repository = _repository(self)
        return {"ok": True, "service": "cointent", "schema_version": "0.2", "projects": len(repository.list_projects())}


class ListProjects(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-projects", description="List projects and their current design versions.", read_only=True)

    async def invoke(self) -> dict[str, Any]:
        return {"projects": _repository(self).list_projects()}


class InspectProject(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-project", description="Inspect project settings and current alignment summary.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        repository = _repository(self)
        return {"project": repository.get_project(project_id), "overview": repository.overview(project_id)}


class GetOverview(Tool):
    def __init__(self) -> None:
        super().__init__(name="get-overview", description="Summarize the active design, code, and review state.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        return _repository(self).overview(project_id)


class CreateProject(Tool):
    def __init__(self) -> None:
        super().__init__(name="create-project", description="Create an empty project and design version 1.", read_only=False)

    async def invoke(
        self, project_id: str, name: str, repository: str = "", description: str = "",
        default_branch: str = "master", language: str = "en",
    ) -> dict[str, Any]:
        return _repository(self).create_project(project_id, name, repository, description, default_branch, language)


class UpdateProjectSettings(Tool):
    def __init__(self) -> None:
        super().__init__(name="update-project-settings", description="Update non-design project settings.", read_only=False)

    async def invoke(
        self, project_id: str, name: str | None = None, description: str | None = None,
        repository: str | None = None, default_branch: str | None = None,
        language: str | None = None, status: str | None = None,
    ) -> dict[str, Any]:
        return _repository(self).update_project(
            project_id, name=name, description=description, repository=repository,
            default_branch=default_branch, language=language, status=status,
        )


class ListDesignVersions(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-design-versions", description="List immutable accepted design versions.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        return {"versions": _repository(self).list_versions(project_id)}


class InspectAlignmentBaseline(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-alignment-baseline", description="Inspect the current design, code snapshot, and mapping revision axes.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        return _repository(self).alignment_baseline(project_id)


class InspectDesign(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-design", description="Read an accepted ProductFunction and RoleObject design version.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", design_version: int | None = None) -> dict[str, Any]:
        return _repository(self).get_model(project_id, design_version)


class RecordIntent(Tool):
    def __init__(self) -> None:
        super().__init__(name="record-intent", description="Preserve a human-agent exchange in its original language.", read_only=False)

    async def invoke(self, project_id: str, speaker: str, content: str, source_ref: str = "") -> dict[str, Any]:
        return _repository(self).record_intent(project_id, speaker, content, source_ref)


class ListIntentSources(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-intent-sources", description="Read original evidence behind design decisions.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", limit: int = 100) -> dict[str, Any]:
        return {"sources": _repository(self).list_intent_sources(project_id, limit)}


class InspectFunctionTree(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-function-tree", description="Read all or part of the ProductFunction hierarchy.", read_only=True)

    async def invoke(
        self, project_id: str = "idea-factory", design_version: int | None = None,
        root_function_id: str | None = None, depth: int = 20,
    ) -> dict[str, Any]:
        return _repository(self).inspect_function_tree(project_id, design_version, root_function_id, depth)


class InspectProductFunction(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-product-function", description="Inspect one ProductFunction and its RoleObject links.", read_only=True)

    async def invoke(self, project_id: str, function_id: str, design_version: int | None = None) -> dict[str, Any]:
        return _repository(self).inspect_product_function(project_id, function_id, design_version)


class AssessFunctionCatalog(Tool):
    def __init__(self) -> None:
        super().__init__(name="assess-function-catalog", description="Report ProductFunction ownership gaps without making design verdicts.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", design_version: int | None = None) -> dict[str, Any]:
        return _repository(self).function_coverage(project_id, design_version)


class AnalyzeFunctionImpact(Tool):
    def __init__(self) -> None:
        super().__init__(name="analyze-function-impact", description="Find RoleObjects and artifacts affected by ProductFunctions.", read_only=True)

    async def invoke(self, project_id: str, function_ids: list[str], design_version: int | None = None) -> dict[str, Any]:
        response = _repository(self).get_model(project_id, design_version)
        model = ProjectModel.model_validate(response["model"])
        links = [item for item in model.function_role_links if item.function_id in function_ids]
        role_ids = sorted({item.role_id for item in links})
        return {
            "project_id": project_id, "design_version": response["version"], "function_ids": function_ids,
            "role_ids": role_ids, "function_role_links": [item.model_dump() for item in links],
            "artifact_paths": sorted({item.artifact_path for item in model.trace_links if item.role_id in role_ids}),
        }


class ProposeDesignPatch(Tool):
    def __init__(self) -> None:
        super().__init__(name="propose-design-patch", description="Validate and stage a typed design patch without changing the accepted version.", read_only=False)

    async def invoke(
        self, project_id: str, base_design_version: int, patch: ModelPatch, rationale: str,
        evidence_ids: list[str] | None = None, change_set_id: str | None = None,
    ) -> dict[str, Any]:
        repository = _repository(self)
        proposal = repository.propose_patch(
            project_id, base_design_version, patch.model_dump(), rationale=rationale,
            evidence_ids=evidence_ids or [], actor=_actor(),
        )
        if change_set_id:
            repository.update_change_set(change_set_id, proposal_id=proposal["id"])
        return proposal


class ListDesignProposals(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-design-proposals", description="List pending or resolved design proposals and semantic diffs.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", status: str = "pending") -> dict[str, Any]:
        return {"proposals": _repository(self).list_proposals(project_id, status)}


class InspectDesignProposal(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-design-proposal", description="Inspect a proposal, typed patch, and complete proposed model.", read_only=True)

    async def invoke(self, proposal_id: str) -> dict[str, Any]:
        return _repository(self).get_proposal(proposal_id)


class ResolveDesignProposal(Tool):
    def __init__(self) -> None:
        super().__init__(name="resolve-design-proposal", description="Accept or reject an explicitly reviewed proposal; acceptance creates a version.", read_only=False)

    async def invoke(self, proposal_id: str, decision: str, resolution: str = "") -> dict[str, Any]:
        if decision not in {"accept", "reject"}:
            raise ValueError("decision must be accept or reject")
        return _repository(self).resolve_proposal(proposal_id, accept=decision == "accept", actor=_actor("human"), resolution=resolution)


class InspectRoleForest(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-role-forest", description="Read the multi-root RoleObject decomposition forest and overlays.", read_only=True)

    async def invoke(
        self, project_id: str = "idea-factory", design_version: int | None = None,
        root_role_id: str | None = None, depth: int = 20,
    ) -> dict[str, Any]:
        return _repository(self).inspect_role_forest(project_id, design_version, root_role_id, depth)


class InspectRoleObject(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-role-object", description="Inspect a RoleObject's full contract, functions, collaborators, and code evidence.", read_only=True)

    async def invoke(self, project_id: str, role_id: str, design_version: int | None = None) -> dict[str, Any]:
        return _repository(self).inspect_role_object(project_id, role_id, design_version)


class AssessRoleQuality(Tool):
    def __init__(self) -> None:
        super().__init__(name="assess-role-quality", description="Report structural cohesion, coupling, contract, coverage, and mapping signals.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", design_version: int | None = None) -> dict[str, Any]:
        response = _repository(self).get_model(project_id, design_version)
        model = ProjectModel.model_validate(response["model"])
        parents = {item.parent_id for item in model.role_objects if item.parent_id}
        responsible = {item.role_id for item in model.responsibilities}
        mapped = {item.role_id for item in model.trace_links}
        related = {value for item in model.role_relations for value in (item.source_role_id, item.target_role_id)}
        linked = {item.role_id for item in model.function_role_links}
        signals: list[dict[str, str]] = []
        for role in model.role_objects:
            if role.id not in parents and role.id not in responsible:
                signals.append({"kind": "empty_leaf_role", "element_id": role.id, "message": "Leaf RoleObject owns no responsibility."})
            if role.id not in mapped:
                signals.append({"kind": "unmapped_role", "element_id": role.id, "message": "RoleObject has no implementation evidence."})
            if role.id not in linked:
                signals.append({"kind": "function_free_role", "element_id": role.id, "message": "RoleObject is not linked to a ProductFunction."})
            if role.parent_id is None and role.id not in related:
                signals.append({"kind": "isolated_root", "element_id": role.id, "message": "Root RoleObject has no declared collaboration."})
            if not role.inputs and not role.outputs and not role.constraints and role.id not in parents:
                signals.append({"kind": "thin_contract", "element_id": role.id, "message": "Leaf RoleObject has no input, output, or constraint."})
        return {"project_id": project_id, "design_version": response["version"], "verdict": "judgment_required", "signals": signals}


class IngestCodeSnapshot(Tool):
    def __init__(self) -> None:
        super().__init__(name="ingest-code-snapshot", description="Store a read-only repository fact snapshot and derive alignment findings.", read_only=False)

    async def invoke(self, project_id: str, snapshot: RepositorySnapshot) -> dict[str, Any]:
        return _repository(self).ingest_snapshot(project_id, snapshot.model_dump())


class ListCodeSnapshots(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-code-snapshots", description="List observed repository snapshots and structural deltas.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", limit: int = 20) -> dict[str, Any]:
        return {"snapshots": _repository(self).list_snapshots(project_id, limit)}


class CompareCodeSnapshots(Tool):
    def __init__(self) -> None:
        super().__init__(name="compare-code-snapshots", description="Compare two observed code snapshots.", read_only=True)

    async def invoke(self, project_id: str, from_snapshot_id: str, to_snapshot_id: str) -> dict[str, Any]:
        return _repository(self).compare_snapshots(project_id, from_snapshot_id, to_snapshot_id)


class ListMappingRevisions(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-mapping-revisions", description="List explicit DesignVersion-to-CodeSnapshot mapping revisions.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", limit: int = 20) -> dict[str, Any]:
        return {"mapping_revisions": _repository(self).list_mapping_revisions(project_id, limit)}


class RecordMappingRevision(Tool):
    def __init__(self) -> None:
        super().__init__(name="record-mapping-revision", description="Confirm the TraceLinks used to align one accepted design with one code snapshot.", read_only=False)

    async def invoke(
        self, project_id: str, design_version: int | None = None,
        snapshot_id: str | None = None, trace_links: list[TraceLink] | None = None,
    ) -> dict[str, Any]:
        return _repository(self).record_mapping_revision(
            project_id, design_version, snapshot_id,
            None if trace_links is None else [item.model_dump() for item in trace_links],
        )


class FindArtifactRoleLinks(Tool):
    def __init__(self) -> None:
        super().__init__(name="find-artifact-role-links", description="Trace implementation paths back to RoleObjects.", read_only=True)

    async def invoke(self, project_id: str, artifact_path: str, design_version: int | None = None) -> dict[str, Any]:
        response = _repository(self).get_model(project_id, design_version)
        model = ProjectModel.model_validate(response["model"])
        links = [item.model_dump() for item in model.trace_links if artifact_path == item.artifact_path or artifact_path.startswith(f"{item.artifact_path.rstrip('/')}/")]
        return {"project_id": project_id, "design_version": response["version"], "artifact_path": artifact_path, "trace_links": links}


class CompareDesignToCode(Tool):
    def __init__(self) -> None:
        super().__init__(name="compare-design-to-code", description="Summarize intended coverage, observed mapping, and open findings.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        repository = _repository(self)
        return {"baseline": repository.alignment_baseline(project_id), "coverage": repository.function_coverage(project_id), "findings": repository.list_findings(project_id)}


class ListAlignmentFindings(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-alignment-findings", description="List open or resolved design-implementation findings.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", status: str = "open") -> dict[str, Any]:
        return {"findings": _repository(self).list_findings(project_id, status)}


class ResolveAlignmentFinding(Tool):
    def __init__(self) -> None:
        super().__init__(name="resolve-alignment-finding", description="Record how an implementation alignment finding was handled.", read_only=False)

    async def invoke(self, finding_id: str, status: str, resolution: str) -> dict[str, Any]:
        return _repository(self).resolve_finding(finding_id, status, resolution)


class StartChangeSet(Tool):
    def __init__(self) -> None:
        super().__init__(name="start-change-set", description="Start a traceable product-design-implementation change loop.", read_only=False)

    async def invoke(self, project_id: str, title: str, description: str = "", function_ids: list[str] | None = None, role_ids: list[str] | None = None) -> dict[str, Any]:
        return _repository(self).start_change_set(project_id, title, description, function_ids, role_ids)


class ListChangeSets(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-change-sets", description="List product-design-implementation change loops.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", status: str = "all") -> dict[str, Any]:
        return {"change_sets": _repository(self).list_change_sets(project_id, status)}


class InspectChangeSet(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-change-set", description="Inspect one change loop and its linked versions.", read_only=True)

    async def invoke(self, change_set_id: str) -> dict[str, Any]:
        return _repository(self).get_change_set(change_set_id)


class UpdateChangeSet(Tool):
    def __init__(self) -> None:
        super().__init__(name="update-change-set", description="Attach a design version or code snapshot and update lifecycle state.", read_only=False)

    async def invoke(self, change_set_id: str, proposal_id: str | None = None, snapshot_id: str | None = None, target_design_version: int | None = None, status: str | None = None, resolution: str | None = None) -> dict[str, Any]:
        return _repository(self).update_change_set(change_set_id, proposal_id=proposal_id, snapshot_id=snapshot_id, target_design_version=target_design_version, status=status, resolution=resolution)


class GenerateImplementationBrief(Tool):
    def __init__(self) -> None:
        super().__init__(name="generate-implementation-brief", description="Generate an agent implementation brief from an accepted change loop.", read_only=True)

    async def invoke(self, change_set_id: str) -> dict[str, Any]:
        return _repository(self).implementation_brief(change_set_id)


class CompareDesignVersions(Tool):
    def __init__(self) -> None:
        super().__init__(name="compare-design-versions", description="Return a semantic diff between accepted design versions.", read_only=True)

    async def invoke(self, project_id: str, from_version: int, to_version: int) -> dict[str, Any]:
        return _repository(self).compare_versions(project_id, from_version, to_version)


class ExportDesignVersion(Tool):
    def __init__(self) -> None:
        super().__init__(name="export-design-version", description="Export a portable versioned CoIntent 0.2 JSON bundle.", read_only=True)

    async def invoke(self, project_id: str, design_version: int | None = None) -> dict[str, Any]:
        return _repository(self).export_design(project_id, design_version)


class RefineProductFunctions(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="refine-product-functions", description="Turn evolving product intent into a coherent ProductFunction catalog.",
            uses=("cointent/product-design/record-intent", "cointent/product-design/inspect-function-tree", "cointent/product-design/assess-function-catalog", "cointent/product-design/analyze-function-impact", "cointent/product-design/propose-design-patch"),
            instructions=(
                "Preserve the human's original wording before modeling. Normalize accepted design content to English. "
                "Describe what the product provides, not goals, teams, screens, or code units. Refine only while the "
                "next level changes observable behavior, acceptance, constraint, or responsibility ownership. Identify "
                "duplicates, missing acceptance conditions, and unowned leaf functions. Stage a typed, version-bound "
                "proposal; never edit the accepted design directly."
            ),
        )


class DecomposeResponsibilities(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="decompose-responsibilities", description="Decompose ProductFunctions into a multi-root RoleObject forest.",
            uses=("cointent/responsibility-design/inspect-role-forest", "cointent/responsibility-design/assess-role-quality", "cointent/product-design/analyze-function-impact", "cointent/product-design/propose-design-patch"),
            instructions=(
                "Use RDD/OOram as the core and selectively apply GRASP high cohesion, low coupling, information expert, "
                "controller, and protected variations. A RoleObject is a logical responsibility owner, not a class, "
                "folder, service, person, or agent. Keep decomposition as a forest with at most one parent; represent "
                "cross-cutting work through typed collaboration and FunctionRoleLink edges. Add knowledge, inputs, "
                "outputs, and constraints only when they clarify an encapsulated boundary. Normalize design content to English."
            ),
        )


class ReviewDesign(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="review-design", description="Review function coverage and RoleObject responsibility quality before acceptance.",
            uses=("cointent/product-design/inspect-design", "cointent/product-design/list-intent-sources", "cointent/product-design/assess-function-catalog", "cointent/responsibility-design/assess-role-quality", "cointent/product-design/propose-design-patch"),
            instructions=(
                "Review source fidelity, ProductFunction clarity and acceptance, leaf ownership, RoleObject cohesion, "
                "collaboration contracts, implementation independence, and evidence. Treat deterministic signals as "
                "questions, not verdicts. Do not force KAOS, IDEF0, UML, DDD, or SOLID ceremony. Keep code-derived "
                "hypotheses distinct from human-approved design and leave acceptance to an explicit human decision."
            ),
        )


class MapImplementation(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="map-implementation", description="Map observed code evidence to RoleObjects without copying the file tree.",
            uses=("cointent/implementation-alignment/list-code-snapshots", "cointent/implementation-alignment/find-artifact-role-links", "cointent/implementation-alignment/compare-design-to-code", "cointent/product-design/propose-design-patch"),
            instructions=(
                "Apply the Software Reflexion Model boundary: accepted design is normative, snapshots are observed, and "
                "TraceLinks are explicit hypotheses. Prefer coarse stable artifacts and many-to-many mappings. Code may "
                "support a proposal but cannot establish desired intent. Classify evidence as convergent, absent, "
                "divergent, boundary-changing, unmapped, or uncertain."
            ),
        )


class CloseAlignmentLoop(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="close-alignment-loop", description="Carry a ProductFunction change through design, implementation, and review.",
            uses=("cointent/change-lifecycle/inspect-change-set", "cointent/change-lifecycle/generate-implementation-brief", "cointent/implementation-alignment/compare-design-to-code", "cointent/change-lifecycle/update-change-set"),
            instructions=(
                "Do not close a ChangeSet until its accepted design version, implementation snapshot, affected functions "
                "and roles, verification evidence, and alignment conclusion are explicit. A code-only change may be an "
                "internal implementation, defect, exception, design evolution, or uncertainty; never silently rewrite design."
            ),
        )


class ProjectManagement(Role):
    def __init__(self) -> None:
        super().__init__(name="project-management", description="Manage projects and the independent design/code version axes.", instructions="Select the project first. Treat DesignVersion, CodeSnapshot, and MappingRevision as independent coordinates.", tools=[Health(), ListProjects(), InspectProject(), GetOverview(), CreateProject(), UpdateProjectSettings(), ListDesignVersions(), InspectAlignmentBaseline()])


class ProductDesign(Role):
    def __init__(self) -> None:
        super().__init__(name="product-design", description="Evolve the ProductFunction catalog through evidence and proposals.", instructions="Preserve original wording, work from accepted ProductFunctions, and stage changes as version-bound proposals.", skills=[RefineProductFunctions(), ReviewDesign()], tools=[InspectDesign(), RecordIntent(), ListIntentSources(), InspectFunctionTree(), InspectProductFunction(), AssessFunctionCatalog(), AnalyzeFunctionImpact(), ProposeDesignPatch(), ListDesignProposals(), InspectDesignProposal(), ResolveDesignProposal()])


class ResponsibilityDesign(Role):
    def __init__(self) -> None:
        super().__init__(name="responsibility-design", description="Design and inspect the multi-root RoleObject responsibility forest.", instructions="Model cohesive responsibility owners independently of code layout, then make contracts and collaborations explicit where useful.", skills=[DecomposeResponsibilities()], tools=[InspectRoleForest(), InspectRoleObject(), AssessRoleQuality()])


class ImplementationAlignment(Role):
    def __init__(self) -> None:
        super().__init__(name="implementation-alignment", description="Compare observed code with accepted responsibility design.", instructions="Keep repository facts, semantic mappings, and accepted design separate. Findings require review before action.", skills=[MapImplementation()], tools=[IngestCodeSnapshot(), ListCodeSnapshots(), CompareCodeSnapshots(), ListMappingRevisions(), RecordMappingRevision(), FindArtifactRoleLinks(), CompareDesignToCode(), ListAlignmentFindings(), ResolveAlignmentFinding()])


class ChangeLifecycle(Role):
    def __init__(self) -> None:
        super().__init__(name="change-lifecycle", description="Track product changes through design, implementation, and alignment closure.", instructions="Bind each significant change to affected functions, roles, accepted design, implementation evidence, and a review conclusion.", skills=[CloseAlignmentLoop()], tools=[StartChangeSet(), ListChangeSets(), InspectChangeSet(), UpdateChangeSet(), GenerateImplementationBrief()])


class HistoryAndPortability(Role):
    def __init__(self) -> None:
        super().__init__(name="history-and-portability", description="Compare and export immutable design assets.", instructions="Use immutable versions and portable JSON to explain how accepted design changed over time.", tools=[CompareDesignVersions(), ExportDesignVersion()])


class CoIntent(Role):
    def __init__(self) -> None:
        super().__init__(
            name="cointent", description="Align evolving ProductFunctions, RoleObject responsibilities, and implementation evidence.",
            instructions="Use project-management for scope, product-design for product promises, responsibility-design for ownership, implementation-alignment for code evidence, change-lifecycle for closure, and history-and-portability for versions and JSON.",
            children=[ProjectManagement(), ProductDesign(), ResponsibilityDesign(), ImplementationAlignment(), ChangeLifecycle(), HistoryAndPortability()],
        )


app = Contexture(name="cointent", roots=(CoIntent,), channels=CoIntentChannels)
