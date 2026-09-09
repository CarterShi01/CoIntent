from pathlib import Path

import pytest

from cointent.models import (
    ImplementationLink, ProjectModel, Responsibility, SpecificationItem,
    SpecificationResponsibilityLink, Workflow, WorkflowEdge, WorkflowNode,
)
from cointent.repository import CoIntentRepository
from cointent.scanner import Artifact, RepositorySnapshot


def repository(tmp_path: Path) -> CoIntentRepository:
    return CoIntentRepository(tmp_path / "cointent.db")


def test_proposal_acceptance_creates_immutable_version(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project("demo", "Demo")
    intent = repo.record_intent("demo", "human", "Ship a dependable service")
    proposal = repo.propose_patch(
        "demo", 1,
        {"upsert_specification_items": [{"id": "spec.ship", "name": "Ship"}]},
        rationale="Make the product meaning explicit", evidence_ids=[intent["id"]], actor="agent",
    )
    assert repo.get_model("demo")["version"] == 1
    repo.resolve_proposal(proposal["id"], accept=True, actor="human")
    assert repo.get_model("demo", 1)["model"]["specification_items"] == []
    assert repo.get_model("demo")["model"]["specification_items"][0]["name"] == "Ship"


def test_stale_proposal_cannot_overwrite_new_baseline(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project("demo", "Demo")
    first = repo.propose_patch("demo", 1, {"summary": "one"}, rationale="one", evidence_ids=[], actor="a")
    second = repo.propose_patch("demo", 1, {"summary": "two"}, rationale="two", evidence_ids=[], actor="b")
    repo.resolve_proposal(first["id"], accept=True, actor="human")
    with pytest.raises(ValueError, match="stale"):
        repo.resolve_proposal(second["id"], accept=True, actor="human")


def test_recursive_inspection_and_loop_trace(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project("demo", "Demo")
    repo.replace_model("demo", design_model(), actor="agent", message="seed")

    roots = repo.list_root_responsibilities("demo")["responsibilities"]
    inspected = repo.inspect_responsibility("demo", "responsibility.root")
    trace = repo.trace_workflow("demo", "responsibility.root")

    assert [item["id"] for item in roots] == ["responsibility.root"]
    assert {item["id"] for item in inspected["child_responsibilities"]} == {
        "responsibility.receive", "responsibility.decide",
    }
    assert inspected["implementation_links"] == []
    assert any(path["loop"] for path in trace["paths"])


def test_incremental_snapshot_creates_mapped_change_finding(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project("demo", "Demo")
    repo.replace_model("demo", design_model(), actor="agent", message="seed")
    repo.ingest_snapshot("demo", snapshot("one", "aaa").model_dump())
    result = repo.ingest_snapshot("demo", snapshot("two", "bbb").model_dump())

    assert result["diff"]["modified"] == ["src/decision/main.py"]
    assert result["findings_created"][0]["kind"] == "BoundaryChange"
    assert result["findings_created"][0]["responsibility_ids"] == ["responsibility.decide"]
    assert repo.alignment_baseline("demo")["is_current"] is True

    repo.replace_model("demo", design_model(), actor="agent", message="new design")
    assert repo.alignment_baseline("demo")["is_current"] is False
    assert repo.record_mapping_revision("demo")["design_version"] == 3
    assert repo.record_mapping_revision("demo")["duplicate"] is True


def test_frontend_removal_never_becomes_a_responsibility_finding(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project("demo", "Demo")
    model = ProjectModel(
        project_id="demo", name="Demo",
        responsibilities=[Responsibility(id="responsibility.presentation", name="Present result")],
        implementation_links=[ImplementationLink(
            id="implementation.presentation", responsibility_id="responsibility.presentation",
            artifact_path="studio/web/src/App.tsx",
        )],
    )
    repo.replace_model("demo", model, actor="agent", message="legacy mapping")
    first = RepositorySnapshot(
        id="snapshot-frontend", project_id="demo", repository="demo", revision="one",
        branch="main", dirty=False, captured_at="2026-01-01T00:00:00+00:00",
        artifacts=[Artifact(path="studio/web/src/App.tsx", kind="source", language="TypeScript",
                            component="studio/web", sha256="aaa", size=3)],
    )
    second = RepositorySnapshot(
        id="snapshot-filtered", project_id="demo", repository="demo", revision="two",
        branch="main", dirty=False, captured_at="2026-01-02T00:00:00+00:00",
    )

    repo.ingest_snapshot("demo", first.model_dump())
    result = repo.ingest_snapshot("demo", second.model_dump())
    assert result["diff"]["removed"] == ["studio/web/src/App.tsx"]
    assert result["findings_created"] == []


def test_json_assets_change_set_and_implementation_brief(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project("demo", "Demo", "https://example.test/demo")
    repo.replace_model("demo", design_model(), actor="agent", message="seed")
    change = repo.start_change_set(
        "demo", "Improve decision", "Use stronger evidence", ["spec.decide"], ["responsibility.decide"],
    )
    repo.update_change_set(change["id"], target_design_version=2, status="approved")
    brief = repo.implementation_brief(change["id"])

    assert [item["version"] for item in repo.list_versions("demo")] == [2, 1]
    assert (tmp_path / "projects/demo/design/v000002.json").is_file()
    assert brief["specification_items"][0]["id"] == "spec.decide"
    assert brief["affected_responsibilities"][0]["responsibility"]["id"] == "responsibility.decide"
    assert "accepted design v2" in brief["agent_prompt"]


def test_stored_schema_version_reports_raw_version_before_migration(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project("demo", "Demo")
    assert repo.stored_schema_version("demo") == "0.3"


def test_unsafe_project_id_cannot_escape_asset_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe project id"):
        repository(tmp_path).create_project("../escape", "Escape")


def design_model() -> ProjectModel:
    workflow = Workflow(
        entry_node_ids=["receive"],
        nodes=[
            WorkflowNode(id="receive", responsibility_id="responsibility.receive"),
            WorkflowNode(id="decide", responsibility_id="responsibility.decide"),
        ],
        edges=[
            WorkflowEdge(id="receive-decide", source_node_id="receive", target_node_id="decide"),
            WorkflowEdge(id="decide-receive", source_node_id="decide", target_node_id="receive", kind="condition"),
        ],
    )
    return ProjectModel(
        project_id="demo", name="Demo", status="baseline",
        specification_items=[SpecificationItem(id="spec.decide", name="Make a decision")],
        responsibilities=[
            Responsibility(id="responsibility.root", name="Run decision cycle", workflow=workflow),
            Responsibility(id="responsibility.receive", name="Receive evidence", inputs=["Evidence"], outputs=["Accepted evidence"]),
            Responsibility(id="responsibility.decide", name="Decide", data_members=["Decision"], inputs=["Accepted evidence"], outputs=["Decision"]),
        ],
        specification_responsibility_links=[SpecificationResponsibilityLink(
            id="link.decide", specification_id="spec.decide", responsibility_id="responsibility.root",
        )],
        implementation_links=[ImplementationLink(
            id="implementation.decide", responsibility_id="responsibility.decide", artifact_path="src/decision",
        )],
    )


def snapshot(identifier: str, digest: str) -> RepositorySnapshot:
    return RepositorySnapshot(
        id=f"snapshot-{identifier}", project_id="demo", repository="demo", revision=identifier,
        branch="main", dirty=False, captured_at="2026-01-01T00:00:00+00:00",
        artifacts=[Artifact(path="src/decision/main.py", kind="source", language="Python",
                            component="src/decision", sha256=digest, size=3)],
    )
