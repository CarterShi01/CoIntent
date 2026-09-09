"""Contexture declaration for CoIntent's Responsibility-native MCP surface."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from contexture import Channels, Contexture, Role, Skill, Tool, current_principal

from .design import DesignOperation
from .models import ImplementationLink, ModelPatch
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
    if principal is None:
        return fallback
    issuer = principal.issuer or "unknown-issuer"
    if principal.subject:
        return f"{issuer}/subject/{principal.subject}"
    if principal.client_id:
        return f"{issuer}/client/{principal.client_id}"
    return f"{issuer}/authenticated-caller"


def _require_scope(scope: str) -> None:
    """Enforce product capabilities when a remote principal is present.

    In-process/CLI execution has no principal and remains available to the
    trusted operator runtime. Remote MCP calls are always principal-scoped.
    """
    principal = current_principal()
    if principal is not None and scope not in principal.scopes:
        raise PermissionError(f"principal lacks required scope {scope!r}")


class Health(Tool):
    def __init__(self) -> None:
        super().__init__(name="health", description="Report service and model-store health.", read_only=True)

    async def invoke(self) -> dict[str, Any]:
        repository = _repository(self)
        return {"ok": True, "service": "cointent", "schema_version": "0.3",
                "projects": len(repository.list_projects())}


class ListProjects(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-projects", description="List projects and current design versions.", read_only=True)

    async def invoke(self) -> dict[str, Any]:
        _require_scope("cointent.read")
        return {"projects": _repository(self).list_projects()}


class InspectProject(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-project", description="Inspect project settings and current summary.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        repository = _repository(self)
        return {"project": repository.get_project(project_id), "overview": repository.overview(project_id)}


class GetOverview(Tool):
    def __init__(self) -> None:
        super().__init__(name="get-overview", description="Summarize specification, Responsibilities, code, and review state.", read_only=True)

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
        super().__init__(name="inspect-alignment-baseline", description="Inspect design, backend snapshot, and mapping coordinates.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        return _repository(self).alignment_baseline(project_id)


class InspectObservationCoordinate(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="inspect-observation-coordinate",
            description="Read the immutable code, Understand Anything, and observed-model coordinate.",
            read_only=True,
        )

    async def invoke(
        self, project_id: str = "idea-factory", observed_revision_id: str | None = None,
    ) -> dict[str, Any]:
        return _repository(self).observation_coordinate(project_id, observed_revision_id)


class ListObservedRevisions(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="list-observed-revisions",
            description="List immutable current-system projections generated from Understand Anything.",
            read_only=True,
        )

    async def invoke(self, project_id: str = "idea-factory", limit: int = 20) -> dict[str, Any]:
        return {"observed_revisions": _repository(self).list_observed_revisions(project_id, limit)}


class InspectObservedRevision(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="inspect-observed-revision",
            description="Read one evidence-backed current-system projection; no mutation is available.",
            read_only=True,
        )

    async def invoke(self, observed_revision_id: str) -> dict[str, Any]:
        return _repository(self).get_observed_revision(observed_revision_id)


class RequestObservationExpansion(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="request-observation-expansion",
            description="Generate a bounded Understand Anything refinement for one observed node; accepts no graph content.",
            read_only=False,
        )

    async def invoke(
        self, project_id: str, observed_revision_id: str, node_id: str, depth: int = 1,
    ) -> dict[str, Any]:
        return _repository(self).request_observation_expansion(
            project_id, observed_revision_id, node_id, depth,
        )


class ListObservationExpansions(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="list-observation-expansions",
            description="List queued or completed Understand Anything refinement requests.",
            read_only=True,
        )

    async def invoke(self, project_id: str = "idea-factory", limit: int = 20) -> dict[str, Any]:
        return {"expansion_requests": _repository(self).list_observation_expansions(project_id, limit)}


class ListTargetDesignWorkspaces(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="list-target-design-workspaces",
            description="List independent 0.4 target-design workspaces and their observed baselines.",
            read_only=True,
        )

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        return {"workspaces": _repository(self).list_design_workspaces_v04(project_id)}


class InspectTargetDesignWorkspace(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="inspect-target-design-workspace",
            description="Read a target workspace, selected immutable revision, and revision history.",
            read_only=True,
        )

    async def invoke(
        self,
        project_id: str = "idea-factory",
        workspace_id: str | None = None,
        revision_id: str | None = None,
    ) -> dict[str, Any] | None:
        return _repository(self).get_design_workspace_view(project_id, workspace_id, revision_id)


class CreateTargetDesignWorkspace(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="create-target-design-workspace",
            description="Clone one observed baseline into an independent des-* target-design namespace.",
            read_only=False,
        )

    async def invoke(
        self,
        project_id: str,
        base_observed_revision_id: str,
        title: str,
        rationale: str,
        actor: Literal["human", "agent"] = "human",
    ) -> dict[str, Any]:
        return _repository(self).create_design_workspace(
            project_id, base_observed_revision_id, title, actor=actor, rationale=rationale,
        )


class ApplyTargetDesignOperations(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="apply-target-design-operations",
            description="Apply typed intent/feature/Responsibility/Workflow operations as one immutable revision.",
            read_only=False,
        )

    async def invoke(
        self,
        workspace_id: str,
        base_design_revision_id: str,
        operations: list[DesignOperation],
        rationale: str,
        actor: Literal["human", "agent"] = "agent",
    ) -> dict[str, Any]:
        return _repository(self).apply_design_operations_v04(
            workspace_id,
            base_design_revision_id,
            [item.model_dump(mode="json") for item in operations],
            actor=actor,
            rationale=rationale,
        )


class ListTargetDesignOperations(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="list-target-design-operations",
            description="Read the authorship and rationale audit trail for a target-design workspace.",
            read_only=True,
        )

    async def invoke(self, workspace_id: str, limit: int = 100) -> dict[str, Any]:
        return {"operations": _repository(self).list_design_operations_v04(workspace_id, limit)}


class CompareImplementationToTarget(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="compare-implementation-to-target",
            description="Create an evidence-backed verification report from an exported target and later observation.",
            read_only=False,
        )

    async def invoke(self, workspace_id: str, observed_revision_id: str) -> dict[str, Any]:
        return _repository(self).create_verification_report_v04(workspace_id, observed_revision_id)


class InspectVerificationReport(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="inspect-verification-report",
            description="Read verification claims; only a human can record the convergence decision.",
            read_only=True,
        )

    async def invoke(self, report_id: str) -> dict[str, Any]:
        return _repository(self).get_verification_report_v04(report_id)


class InspectDesign(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-design", description="Read an accepted CoIntent 0.3 design version.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", design_version: int | None = None) -> dict[str, Any]:
        return _repository(self).get_model(project_id, design_version)


class RecordIntent(Tool):
    def __init__(self) -> None:
        super().__init__(name="record-intent", description="Preserve a human-Agent exchange in its original language.", read_only=False)

    async def invoke(self, project_id: str, speaker: str, content: str, source_ref: str = "") -> dict[str, Any]:
        return _repository(self).record_intent(project_id, speaker, content, source_ref)


class ListIntentSources(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-intent-sources", description="Read original evidence behind model decisions.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", limit: int = 100) -> dict[str, Any]:
        return {"sources": _repository(self).list_intent_sources(project_id, limit)}


class InspectSpecificationTree(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-specification-tree", description="Read all or part of the plain-language specification tree.", read_only=True)

    async def invoke(
        self, project_id: str = "idea-factory", design_version: int | None = None,
        root_specification_id: str | None = None, depth: int = 20,
    ) -> dict[str, Any]:
        return _repository(self).inspect_specification_tree(
            project_id, design_version, root_specification_id, depth,
        )


class InspectSpecificationItem(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-specification-item", description="Inspect one plain-language statement and its realizing Responsibilities.", read_only=True)

    async def invoke(
        self, project_id: str, specification_id: str, design_version: int | None = None,
    ) -> dict[str, Any]:
        return _repository(self).inspect_specification_item(project_id, specification_id, design_version)


class AssessSpecificationCoverage(Tool):
    def __init__(self) -> None:
        super().__init__(name="assess-specification-coverage", description="Report specification statements without Responsibility coverage.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", design_version: int | None = None) -> dict[str, Any]:
        return _repository(self).specification_coverage(project_id, design_version)


class ListRootResponsibilities(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-root-responsibilities", description="List Responsibilities not referenced by another Responsibility Workflow.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", design_version: int | None = None) -> dict[str, Any]:
        return _repository(self).list_root_responsibilities(project_id, design_version)


class InspectResponsibility(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-responsibility", description="Inspect one Responsibility contract, immediate Workflow, children, parents, specification, and code evidence.", read_only=True)

    async def invoke(
        self, project_id: str, responsibility_id: str, design_version: int | None = None,
    ) -> dict[str, Any]:
        return _repository(self).inspect_responsibility(project_id, responsibility_id, design_version)


class TraceResponsibilityWorkflow(Tool):
    def __init__(self) -> None:
        super().__init__(name="trace-responsibility-workflow", description="Enumerate bounded paths through a Responsibility Workflow, preserving conditions and loops.", read_only=True)

    async def invoke(
        self, project_id: str, responsibility_id: str, design_version: int | None = None,
        max_steps: int = 32, max_paths: int = 64,
    ) -> dict[str, Any]:
        return _repository(self).trace_workflow(
            project_id, responsibility_id, design_version, max_steps, max_paths,
        )


class AssessResponsibilityQuality(Tool):
    def __init__(self) -> None:
        super().__init__(name="assess-responsibility-quality", description="Report missing contracts, evidence, and unreachable Workflow nodes without making design verdicts.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", design_version: int | None = None) -> dict[str, Any]:
        return _repository(self).responsibility_quality(project_id, design_version)


class ProposeDesignPatch(Tool):
    def __init__(self) -> None:
        super().__init__(name="propose-design-patch", description="Validate and stage a typed Responsibility-model patch without changing accepted design.", read_only=False)

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
        super().__init__(name="list-design-proposals", description="List pending or resolved semantic design proposals.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", status: str = "pending") -> dict[str, Any]:
        return {"proposals": _repository(self).list_proposals(project_id, status)}


class InspectDesignProposal(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-design-proposal", description="Inspect a proposal, typed patch, diff, and complete candidate model.", read_only=True)

    async def invoke(self, proposal_id: str) -> dict[str, Any]:
        return _repository(self).get_proposal(proposal_id)


class ResolveDesignProposal(Tool):
    def __init__(self) -> None:
        super().__init__(name="resolve-design-proposal", description="Accept or reject a reviewed proposal; acceptance creates an immutable version.", read_only=False)

    async def invoke(self, proposal_id: str, decision: str, resolution: str = "") -> dict[str, Any]:
        if decision not in {"accept", "reject"}:
            raise ValueError("decision must be accept or reject")
        return _repository(self).resolve_proposal(
            proposal_id, accept=decision == "accept", actor=_actor("human"), resolution=resolution,
        )


class IngestCodeSnapshot(Tool):
    def __init__(self) -> None:
        super().__init__(name="ingest-code-snapshot", description="Store a read-only backend repository snapshot and derive Responsibility findings.", read_only=False)

    async def invoke(self, project_id: str, snapshot: RepositorySnapshot) -> dict[str, Any]:
        return _repository(self).ingest_snapshot(project_id, snapshot.model_dump())


class ListCodeSnapshots(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-code-snapshots", description="List observed backend code snapshots and structural deltas.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", limit: int = 20) -> dict[str, Any]:
        return {"snapshots": _repository(self).list_snapshots(project_id, limit)}


class CompareCodeSnapshots(Tool):
    def __init__(self) -> None:
        super().__init__(name="compare-code-snapshots", description="Compare two observed backend snapshots.", read_only=True)

    async def invoke(self, project_id: str, from_snapshot_id: str, to_snapshot_id: str) -> dict[str, Any]:
        return _repository(self).compare_snapshots(project_id, from_snapshot_id, to_snapshot_id)


class FindArtifactResponsibilities(Tool):
    def __init__(self) -> None:
        super().__init__(name="find-artifact-responsibilities", description="Trace a backend artifact to Responsibilities and implementation evidence.", read_only=True)

    async def invoke(
        self, project_id: str, artifact_path: str, design_version: int | None = None,
    ) -> dict[str, Any]:
        return _repository(self).find_artifact_responsibilities(project_id, artifact_path, design_version)


class ListMappingRevisions(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-mapping-revisions", description="List explicit DesignVersion-to-CodeSnapshot mappings.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", limit: int = 20) -> dict[str, Any]:
        return {"mapping_revisions": _repository(self).list_mapping_revisions(project_id, limit)}


class RecordMappingRevision(Tool):
    def __init__(self) -> None:
        super().__init__(name="record-mapping-revision", description="Confirm ImplementationLinks for one accepted design and backend snapshot.", read_only=False)

    async def invoke(
        self, project_id: str, design_version: int | None = None, snapshot_id: str | None = None,
        implementation_links: list[ImplementationLink] | None = None,
    ) -> dict[str, Any]:
        return _repository(self).record_mapping_revision(
            project_id, design_version, snapshot_id,
            None if implementation_links is None else [item.model_dump() for item in implementation_links],
        )


class CompareDesignToCode(Tool):
    def __init__(self) -> None:
        super().__init__(name="compare-design-to-code", description="Summarize specification coverage, Responsibility quality, mappings, and findings.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        return _repository(self).compare_design_to_code(project_id)


class ListAlignmentFindings(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-alignment-findings", description="List open or resolved Responsibility-to-code findings.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", status: str = "open") -> dict[str, Any]:
        return {"findings": _repository(self).list_findings(project_id, status)}


class ResolveAlignmentFinding(Tool):
    def __init__(self) -> None:
        super().__init__(name="resolve-alignment-finding", description="Record how an implementation finding was handled.", read_only=False)

    async def invoke(self, finding_id: str, status: str, resolution: str) -> dict[str, Any]:
        return _repository(self).resolve_finding(finding_id, status, resolution)


class StartChangeSet(Tool):
    def __init__(self) -> None:
        super().__init__(name="start-change-set", description="Start a traceable specification-model-code change loop.", read_only=False)

    async def invoke(
        self, project_id: str, title: str, description: str = "",
        specification_ids: list[str] | None = None, responsibility_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return _repository(self).start_change_set(
            project_id, title, description, specification_ids, responsibility_ids,
        )


class ListChangeSets(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-change-sets", description="List specification-model-code change loops.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory", status: str = "all") -> dict[str, Any]:
        return {"change_sets": _repository(self).list_change_sets(project_id, status)}


class InspectChangeSet(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-change-set", description="Inspect one change loop and its linked versions.", read_only=True)

    async def invoke(self, change_set_id: str) -> dict[str, Any]:
        return _repository(self).get_change_set(change_set_id)


class UpdateChangeSet(Tool):
    def __init__(self) -> None:
        super().__init__(name="update-change-set", description="Attach a proposal, design version, or backend snapshot and update lifecycle state.", read_only=False)

    async def invoke(
        self, change_set_id: str, proposal_id: str | None = None, snapshot_id: str | None = None,
        target_design_version: int | None = None, status: str | None = None, resolution: str | None = None,
    ) -> dict[str, Any]:
        return _repository(self).update_change_set(
            change_set_id, proposal_id=proposal_id, snapshot_id=snapshot_id,
            target_design_version=target_design_version, status=status, resolution=resolution,
        )


class GenerateImplementationBrief(Tool):
    def __init__(self) -> None:
        super().__init__(name="generate-implementation-brief", description="Generate an Agent brief from an accepted Responsibility change.", read_only=True)

    async def invoke(self, change_set_id: str) -> dict[str, Any]:
        return _repository(self).implementation_brief(change_set_id)


class CompareDesignVersions(Tool):
    def __init__(self) -> None:
        super().__init__(name="compare-design-versions", description="Return a semantic diff between accepted design versions.", read_only=True)

    async def invoke(self, project_id: str, from_version: int, to_version: int) -> dict[str, Any]:
        return _repository(self).compare_versions(project_id, from_version, to_version)


class ExportDesignVersion(Tool):
    def __init__(self) -> None:
        super().__init__(name="export-design-version", description="Export a portable CoIntent 0.3 JSON bundle.", read_only=True)

    async def invoke(self, project_id: str, design_version: int | None = None) -> dict[str, Any]:
        return _repository(self).export_design(project_id, design_version)


# Compact 0.4+ product surface. These tools expose product verbs and bounded
# semantic levels; raw UA artifacts and observed graph writes are intentionally absent.


class InspectProjectState(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-project-state", description="Read current coordinates, refresh state, target drawings, and allowed next actions.", read_only=True)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        _require_scope("cointent.read")
        return _repository(self).project_state(project_id)


class RefreshCurrentUnderstanding(Tool):
    def __init__(self) -> None:
        super().__init__(name="refresh-current-understanding", description="Request one idempotent on-demand code → UA → Observation refresh; accepts no graph content.", read_only=False)

    async def invoke(self, project_id: str = "idea-factory") -> dict[str, Any]:
        _require_scope("cointent.refresh.request")
        return _repository(self).request_understanding_refresh(project_id, requested_by=_actor())


class InspectUnderstandingRefresh(Tool):
    def __init__(self) -> None:
        super().__init__(name="inspect-understanding-refresh", description="Read refresh progress, mode, changed files, diagnostics, and published coordinate.", read_only=True)

    async def invoke(self, job_id: str) -> dict[str, Any]:
        _require_scope("cointent.read")
        return _repository(self).get_understanding_refresh(job_id)


class ReadCurrentLevel(Tool):
    def __init__(self) -> None:
        super().__init__(name="read-current-level", description="Read one web-equivalent semantic level of current truth with bounded implementation evidence.", read_only=True)

    async def invoke(
        self, project_id: str = "idea-factory", focus_id: str | None = None,
        observed_revision_id: str | None = None,
    ) -> dict[str, Any]:
        _require_scope("cointent.read")
        return _repository(self).read_current_level(
            project_id, focus_id=focus_id, observed_revision_id=observed_revision_id,
        )


class StartStructureDesign(Tool):
    def __init__(self) -> None:
        super().__init__(name="start-structure-design", description="Create an independent target drawing from the latest explicitly refreshed root Observation.", read_only=False)

    async def invoke(self, project_id: str, title: str) -> dict[str, Any]:
        _require_scope("cointent.design.write")
        repository = _repository(self)
        return repository.start_structure_design(project_id, title, actor=_actor())


class ReadDesignLevel(Tool):
    def __init__(self) -> None:
        super().__init__(name="read-design-level", description="Read one web-equivalent expected-function and target-structure level.", read_only=True)

    async def invoke(
        self, workspace_id: str, focus_id: str | None = None,
        design_revision_id: str | None = None,
    ) -> dict[str, Any]:
        _require_scope("cointent.read")
        return _repository(self).read_design_level(
            workspace_id, focus_id=focus_id, design_revision_id=design_revision_id,
        )


class ReviseStructureDesign(Tool):
    def __init__(self) -> None:
        super().__init__(name="revise-structure-design", description="Publish typed expected-function and complete target-structure operations as one immutable revision.", read_only=False)

    async def invoke(
        self, workspace_id: str, base_design_revision_id: str,
        operations: list[DesignOperation], rationale: str,
    ) -> dict[str, Any]:
        _require_scope("cointent.design.write")
        return _repository(self).apply_design_operations_v04(
            workspace_id, base_design_revision_id,
            [item.model_dump(mode="json") for item in operations], actor=_actor(), rationale=rationale,
        )


class DiffStructureDesign(Tool):
    def __init__(self) -> None:
        super().__init__(name="diff-structure-design", description="Compare target revisions or the complete target graph with its exact observed baseline.", read_only=True)

    async def invoke(
        self, workspace_id: str, from_revision_id: str | None = None,
        to_revision_id: str | None = None,
    ) -> dict[str, Any]:
        _require_scope("cointent.read")
        return _repository(self).diff_structure_design(
            workspace_id, from_revision_id=from_revision_id, to_revision_id=to_revision_id,
        )


class CreateImplementationContext(Tool):
    def __init__(self) -> None:
        super().__init__(name="create-implementation-context", description="After explicit user confirmation, freeze an exact reviewed diff as coding constraints; schedules no scan.", read_only=False)

    async def invoke(
        self, workspace_id: str, design_revision_id: str, expected_diff_digest: str,
    ) -> dict[str, Any]:
        _require_scope("cointent.design.finalize")
        return _repository(self).create_implementation_context(
            workspace_id, design_revision_id, expected_diff_digest, actor=_actor(),
        )


class ListStructureDesignVersions(Tool):
    def __init__(self) -> None:
        super().__init__(name="list-structure-design-versions", description="Read immutable target drawing history and rationale.", read_only=True)

    async def invoke(self, workspace_id: str) -> dict[str, Any]:
        _require_scope("cointent.read")
        workspace = _repository(self).get_design_workspace(workspace_id)
        view = _repository(self).get_design_workspace_view(workspace["project_id"], workspace_id)
        return {"workspace": workspace, "versions": [] if view is None else view["revisions"]}


class CompareDesignToCurrent(Tool):
    def __init__(self) -> None:
        super().__init__(name="compare-design-to-current", description="Optionally compare a historical drawing with a later Observation without writing or merging either side.", read_only=True)

    async def invoke(self, design_revision_id: str, observed_revision_id: str | None = None) -> dict[str, Any]:
        _require_scope("cointent.read")
        repository = _repository(self)
        design = repository.get_design_revision_v04(design_revision_id)
        workspace = repository.get_design_workspace(design["workspace_id"])
        selected = observed_revision_id
        if selected is None:
            coordinate = repository.observation_coordinate(workspace["project_id"])
            if coordinate.get("observed_revision") is None:
                raise ValueError("no current Observation is available")
            selected = coordinate["observed_revision"]["id"]
        return repository.compare_design_to_observation(design_revision_id, selected)


class ModelResponsibilities(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="model-responsibilities",
            description="Lift backend program logic into recursive Responsibility Workflows.",
            uses=(
                "cointent/responsibility-model/inspect-responsibility",
                "cointent/responsibility-model/trace-responsibility-workflow",
                "cointent/responsibility-model/assess-responsibility-quality",
                "cointent/responsibility-model/propose-design-patch",
            ),
            instructions=(
                "A Responsibility is the only semantic object: one coherent obligation with meaningful data members, "
                "inputs, outputs, and an optional Workflow. Workflow nodes reference smaller Responsibilities; never "
                "store a second child hierarchy. Preserve branches and cycles that change product behavior. Filter "
                "frontend code, logs, telemetry, framework plumbing, and other technical noise. Do not invent Role, "
                "RoleObject, Function, class, service, module, or architecture nodes. Attach backend evidence to leaves "
                "and stage all changes as version-bound proposals."
            ),
        )


class ReviewResponsibilityModel(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="review-responsibility-model",
            description="Review specification fidelity, recursive composition, contracts, and backend evidence.",
            uses=(
                "cointent/specification/inspect-specification-tree",
                "cointent/specification/assess-specification-coverage",
                "cointent/responsibility-model/assess-responsibility-quality",
                "cointent/implementation-alignment/compare-design-to-code",
            ),
            instructions=(
                "Check that plain-language specification stays program-independent; Responsibilities stay cohesive and "
                "single-altitude; data, inputs, and outputs clarify boundaries; Workflow is the sole composition truth; "
                "and implementation evidence is backend-only. Treat signals as questions, not verdicts."
            ),
        )


class MapBackendImplementation(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="map-backend-implementation",
            description="Map filtered backend evidence to Responsibilities without copying the code graph.",
            uses=(
                "cointent/implementation-alignment/list-code-snapshots",
                "cointent/implementation-alignment/find-artifact-responsibilities",
                "cointent/implementation-alignment/compare-design-to-code",
                "cointent/responsibility-model/propose-design-patch",
            ),
            instructions=(
                "Repository facts are observed evidence, not semantic truth. Collapse functions and classes into "
                "product-readable Responsibilities. Exclude frontend and technical cross-cutting noise. Prefer stable "
                "backend artifacts and many-to-many mappings; preserve uncertainty and never rewrite accepted design."
            ),
        )


class CloseAlignmentLoop(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="close-alignment-loop",
            description="Carry a change through specification, Responsibility Workflow, code, and review.",
            uses=(
                "cointent/change-lifecycle/inspect-change-set",
                "cointent/change-lifecycle/generate-implementation-brief",
                "cointent/implementation-alignment/compare-design-to-code",
                "cointent/change-lifecycle/update-change-set",
            ),
            instructions=(
                "Do not close a ChangeSet until accepted design, backend snapshot, affected Responsibilities, "
                "verification evidence, and the alignment conclusion are explicit."
            ),
        )


class ProjectManagement(Role):
    def __init__(self) -> None:
        super().__init__(
            name="project-management", description="Manage projects and independent design/code/mapping coordinates.",
            instructions="Select project and version before reasoning about its model.",
            tools=[Health(), ListProjects(), InspectProject(), GetOverview(), CreateProject(),
                   UpdateProjectSettings(), ListDesignVersions(), InspectAlignmentBaseline()],
        )


class CurrentUnderstanding(Role):
    def __init__(self) -> None:
        super().__init__(
            name="current-understanding",
            description="Read the code-derived current system produced through Understand Anything.",
            instructions=(
                "This surface is read-only. Treat the observed revision as derived from its exact code and UA "
                "coordinates. Never reinterpret a user request as permission to replace observed nodes or edges; "
                "send desired changes to the design process."
            ),
            tools=[InspectObservationCoordinate(), ListObservedRevisions(), InspectObservedRevision(),
                   RequestObservationExpansion(), ListObservationExpansions()],
        )


class Specification(Role):
    def __init__(self) -> None:
        super().__init__(
            name="specification", description="Inspect the program-independent plain-language product layer.",
            instructions="Keep this layer in product language; program modeling belongs to responsibility-model.",
            tools=[InspectSpecificationTree(), InspectSpecificationItem(), AssessSpecificationCoverage(),
                   RecordIntent(), ListIntentSources()],
        )


class TargetDesign(Role):
    def __init__(self) -> None:
        super().__init__(
            name="target-design",
            description="Evolve desired functions and Responsibilities independently from observed code truth.",
            instructions=(
                "All mutable semantic identities must use the des-* namespace. Preserve the exact observed "
                "baseline and explain every operation; never target an obs-* identity."
            ),
            tools=[ListTargetDesignWorkspaces(), InspectTargetDesignWorkspace(),
                   CreateTargetDesignWorkspace(), ApplyTargetDesignOperations(),
                   ListTargetDesignOperations(), CompareImplementationToTarget(),
                   InspectVerificationReport()],
        )


class ResponsibilityModel(Role):
    def __init__(self) -> None:
        super().__init__(
            name="responsibility-model", description="Inspect and evolve recursive Responsibility Workflows.",
            instructions="Use one Responsibility concept; Workflow node references are its only child composition.",
            skills=[ModelResponsibilities(), ReviewResponsibilityModel()],
            tools=[InspectDesign(), ListRootResponsibilities(), InspectResponsibility(),
                   TraceResponsibilityWorkflow(), AssessResponsibilityQuality(), ProposeDesignPatch(),
                   ListDesignProposals(), InspectDesignProposal(), ResolveDesignProposal()],
        )


class ImplementationAlignment(Role):
    def __init__(self) -> None:
        super().__init__(
            name="implementation-alignment", description="Compare filtered backend evidence with accepted Responsibilities.",
            instructions="Keep code facts, semantic inference, and accepted design separate.",
            skills=[MapBackendImplementation()],
            tools=[IngestCodeSnapshot(), ListCodeSnapshots(), CompareCodeSnapshots(),
                   FindArtifactResponsibilities(), ListMappingRevisions(), RecordMappingRevision(),
                   CompareDesignToCode(), ListAlignmentFindings(), ResolveAlignmentFinding()],
        )


class ChangeLifecycle(Role):
    def __init__(self) -> None:
        super().__init__(
            name="change-lifecycle", description="Track specification-model-code changes through review.",
            instructions="Bind each change to accepted versions, affected Responsibilities, and backend evidence.",
            skills=[CloseAlignmentLoop()],
            tools=[StartChangeSet(), ListChangeSets(), InspectChangeSet(), UpdateChangeSet(),
                   GenerateImplementationBrief()],
        )


class HistoryAndPortability(Role):
    def __init__(self) -> None:
        super().__init__(
            name="history-and-portability", description="Compare and export immutable design assets.",
            instructions="Use immutable versions and portable JSON to explain semantic change.",
            tools=[CompareDesignVersions(), ExportDesignVersion()],
        )


class LegacyCoIntent(Role):
    def __init__(self) -> None:
        super().__init__(
            name="cointent",
            description="Compatibility surface for pre-0.4 browser routes.",
            instructions=(
                "Follow the three-level chain: specification → Responsibility Workflow → backend evidence. "
                "Never substitute an architecture or code graph for the Responsibility model."
            ),
            children=[ProjectManagement(), CurrentUnderstanding(), TargetDesign(), Specification(), ResponsibilityModel(), ImplementationAlignment(),
                      ChangeLifecycle(), HistoryAndPortability()],
        )


class LearnCurrentSystem(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="learn-current-system",
            description="Refresh and learn current truth one semantic page at a time.",
            uses=(
                "cointent/project-context/inspect-project-state",
                "cointent/understand-current/refresh-current-understanding",
                "cointent/understand-current/inspect-understanding-refresh",
                "cointent/understand-current/read-current-level",
            ),
            instructions=(
                "Inspect state first. Refresh only when the user asks to understand. Read one page-equivalent "
                "level, and descend with a returned focus identifier only when requested. Never write observed data."
            ),
        )


class DesignStructureFirst(Skill):
    def __init__(self) -> None:
        super().__init__(
            name="design-structure-first",
            description="Refresh, design the complete target graph, review its diff, then create coding context.",
            uses=(
                "cointent/project-context/inspect-project-state",
                "cointent/understand-current/refresh-current-understanding",
                "cointent/understand-current/inspect-understanding-refresh",
                "cointent/design-future/start-structure-design",
                "cointent/design-future/read-design-level",
                "cointent/design-future/revise-structure-design",
                "cointent/design-future/diff-structure-design",
                "cointent/design-future/create-implementation-context",
            ),
            instructions=(
                "Enter only after explicit structure-design intent. Refresh first, keep the baseline immutable, "
                "revise expected functions and the complete target Responsibility/Workflow graph, and show the "
                "exact diff before finalization. Create implementation context only after explicit confirmation. "
                "Stop after coding context; never trigger a post-code scan."
            ),
        )


class ProjectContext(Role):
    def __init__(self) -> None:
        super().__init__(
            name="project-context", description="Select a project and inspect its immutable coordinates.",
            instructions="Inspect project state before selecting any current or design coordinate.",
            tools=[ListProjects(), InspectProjectState()],
        )


class UnderstandCurrent(Role):
    def __init__(self) -> None:
        super().__init__(
            name="understand-current", description="Refresh and read code-derived current truth on demand.",
            instructions=(
                "Current truth is code → pinned Understand Anything → validated projection. Never accept graph "
                "content or turn conversation into an observed write. Return only one page-equivalent level."
            ),
            skills=[LearnCurrentSystem()],
            tools=[RefreshCurrentUnderstanding(), InspectUnderstandingRefresh(), ReadCurrentLevel()],
        )


class DesignFuture(Role):
    def __init__(self) -> None:
        super().__init__(
            name="design-future", description="Design and review a separate target structure before code.",
            instructions=(
                "Use only after explicit design intent. Refresh first and never rebase silently. Target drawings "
                "are independent history and never become observed truth. Finalization schedules no scan."
            ),
            skills=[DesignStructureFirst()],
            tools=[
                StartStructureDesign(), ReadDesignLevel(), ReviseStructureDesign(), DiffStructureDesign(),
                CreateImplementationContext(), ListStructureDesignVersions(), CompareDesignToCurrent(),
            ],
        )


class CoIntent(Role):
    def __init__(self) -> None:
        super().__init__(
            name="cointent",
            description="Understand current code truth on demand and design a separate future structure on demand.",
            instructions=(
                "Inspect project state first. Route what exists to understand-current. Enter design-future only "
                "after explicit design intent and refresh before a new drawing. Read one semantic page per call. "
                "Never translate conversation or target design into an observed write. Stop after implementation "
                "context and compare a historical design with later reality only when requested."
            ),
            children=[ProjectContext(), UnderstandCurrent(), DesignFuture()],
        )


app = Contexture(name="cointent", roots=(CoIntent,), channels=CoIntentChannels)
legacy_app = Contexture(name="cointent-legacy", roots=(LegacyCoIntent,), channels=CoIntentChannels)
