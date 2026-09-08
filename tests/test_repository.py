from pathlib import Path

import pytest

from cointent.models import ProductFunction, ProjectModel, RoleObject, TraceLink
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
        {"upsert_goals": [{"id": "goal.ship", "title": "Ship"}]},
        rationale="Make the desired outcome explicit", evidence_ids=[intent["id"]], actor="agent",
    )

    assert repo.get_model("demo")["version"] == 1
    accepted = repo.resolve_proposal(proposal["id"], accept=True, actor="human")
    assert accepted["status"] == "accepted"
    assert repo.get_model("demo")["version"] == 2
    assert repo.get_model("demo", 1)["model"]["product_functions"] == []
    assert repo.get_model("demo")["model"]["product_functions"][0]["name"] == "Ship"


def test_stale_proposal_cannot_overwrite_new_baseline(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project("demo", "Demo")
    first = repo.propose_patch("demo", 1, {"summary": "one"}, rationale="one", evidence_ids=[], actor="a")
    second = repo.propose_patch("demo", 1, {"summary": "two"}, rationale="two", evidence_ids=[], actor="b")
    repo.resolve_proposal(first["id"], accept=True, actor="human")

    with pytest.raises(ValueError, match="stale"):
        repo.resolve_proposal(second["id"], accept=True, actor="human")


def test_incremental_snapshot_creates_mapped_change_finding(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project("demo", "Demo")
    model = ProjectModel(
        project_id="demo", name="Demo",
        product_functions=[ProductFunction(id="function.ship", name="Ship")],
        role_objects=[RoleObject(id="role.api", name="API", purpose="Own the API")],
        trace_links=[TraceLink(id="trace.api", role_id="role.api", artifact_path="src/api")],
    )
    repo.replace_model("demo", model, actor="agent", message="seed")
    first = snapshot("one", "aaa")
    second = snapshot("two", "bbb")
    repo.ingest_snapshot("demo", first.model_dump())
    result = repo.ingest_snapshot("demo", second.model_dump())

    assert result["diff"]["modified"] == ["src/api/main.py"]
    assert result["findings_created"][0]["kind"] == "BoundaryChange"
    assert result["findings_created"][0]["role_ids"] == ["role.api"]
    baseline = repo.alignment_baseline("demo")
    assert baseline["mapping_revision"]["snapshot_id"] == "snapshot-two"
    assert baseline["mapping_revision"]["design_version"] == 2


def test_reingesting_identical_snapshot_is_idempotent(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project("demo", "Demo")
    first = snapshot("one", "aaa")

    assert repo.ingest_snapshot("demo", first.model_dump())["duplicate"] is False
    assert repo.ingest_snapshot("demo", first.model_dump())["duplicate"] is True
    assert len(repo.list_snapshots("demo")) == 1
    assert repo.overview("demo")["latest_snapshot"]["artifact_count"] == 1
    assert "artifacts" not in repo.overview("demo")["latest_snapshot"]


def test_project_versions_json_assets_and_change_set(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.create_project(
        "demo", "Demo", "https://example.test/demo", "A demo", "main", "en",
    )
    project = repo.update_project("demo", description="Updated", status="active")
    proposal = repo.propose_patch(
        "demo", 1,
        {
            "upsert_product_functions": [{"id": "function.ship", "name": "Ship"}],
            "upsert_role_objects": [{"id": "role.delivery", "name": "Delivery", "purpose": "Own delivery"}],
            "upsert_function_role_links": [{
                "id": "link.ship", "function_id": "function.ship", "role_id": "role.delivery", "kind": "owns",
            }],
        },
        rationale="Create an accountable product function", evidence_ids=[], actor="agent",
    )
    repo.resolve_proposal(proposal["id"], accept=True, actor="human")
    change = repo.start_change_set(
        "demo", "Improve shipping", "Make shipping observable", ["function.ship"], ["role.delivery"],
    )
    change = repo.update_change_set(change["id"], target_design_version=2, status="approved")
    brief = repo.implementation_brief(change["id"])

    assert project["description"] == "Updated"
    assert [item["version"] for item in repo.list_versions("demo")] == [2, 1]
    assert (tmp_path / "projects/demo/project.json").is_file()
    assert (tmp_path / "projects/demo/design/v000001.json").is_file()
    assert (tmp_path / "projects/demo/design/v000002.json").is_file()
    assert brief["product_functions"][0]["id"] == "function.ship"
    assert brief["affected_roles"][0]["role_object"]["id"] == "role.delivery"
    assert "accepted design v2" in brief["agent_prompt"]


def test_unsafe_project_id_cannot_escape_asset_root(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    with pytest.raises(ValueError, match="unsafe project id"):
        repo.create_project("../escape", "Escape")


def snapshot(identifier: str, digest: str) -> RepositorySnapshot:
    return RepositorySnapshot(
        id=f"snapshot-{identifier}", project_id="demo", repository="demo", revision=identifier,
        branch="main", dirty=False, captured_at="2026-01-01T00:00:00+00:00",
        artifacts=[Artifact(path="src/api/main.py", kind="source", language="Python",
                            component="src/api", sha256=digest, size=3)],
    )
