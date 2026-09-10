import json
import subprocess
from pathlib import Path

import pytest

from cointent.refresh import UaRunResult, UnderstandingRefreshJob
from cointent.repository import CoIntentRepository
from cointent.scanner import scan_repository


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def initialize_checkout(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "service.py").write_text("def serve():\n    return 'current'\n", encoding="utf-8")
    git(root, "add", "service.py")
    git(root, "commit", "-qm", "initial")


def ua_result(project_root: Path, mode: str, state_root: Path) -> UaRunResult:
    revision = git(project_root, "rev-parse", "HEAD")
    lines = len((project_root / "service.py").read_text(encoding="utf-8").splitlines())
    project = {
        "name": "Demo", "languages": ["Python"], "frameworks": [],
        "description": "Demo service", "analyzedAt": "2026-09-10T00:00:00Z",
        "gitCommitHash": revision,
    }
    knowledge = {
        "version": "1.0.0", "kind": "codebase", "project": project,
        "nodes": [
            {"id": "file:service", "type": "file", "name": "service.py", "filePath": "service.py", "lineRange": [1, lines], "summary": "Service module."},
            {"id": "function:serve", "type": "function", "name": "serve", "filePath": "service.py", "lineRange": [1, lines], "summary": "Serves current behavior."},
        ],
        "edges": [{"source": "file:service", "target": "function:serve", "type": "contains"}],
        "layers": [], "tour": [],
    }
    domain = {
        "version": "1.0.0", "kind": "codebase", "project": project,
        "nodes": [
            {"id": "domain:service", "type": "domain", "name": "Service", "summary": "Own service behavior."},
            {"id": "flow:serve", "type": "flow", "name": "Serve request", "summary": "Serve current behavior."},
            {"id": "step:serve", "type": "step", "name": "Run service", "filePath": "service.py", "lineRange": [1, lines], "summary": "Call serve."},
        ],
        "edges": [
            {"source": "domain:service", "target": "flow:serve", "type": "contains_flow"},
            {"source": "flow:serve", "target": "step:serve", "type": "flow_step"},
        ],
        "layers": [], "tour": [],
    }
    state_root.mkdir(parents=True, exist_ok=True)
    for name, value in (
        ("knowledge-graph.json", knowledge), ("domain-graph.json", domain),
        ("meta.json", {"gitCommitHash": revision}), ("fingerprints.json", {"service.py": revision}),
        ("config.json", {"outputLanguage": "en", "autoUpdate": False}),
    ):
        (state_root / name).write_text(json.dumps(value), encoding="utf-8")
    return UaRunResult(
        knowledge_graph=knowledge, domain_graph=domain,
        files_reanalyzed=["service.py"], diagnostics=[f"fake {mode} run"],
    )


def publish_observation(repository: CoIntentRepository, checkout: Path, job_id: str) -> dict:
    claimed = UnderstandingRefreshJob.model_validate(repository.claim_understanding_refresh(job_id))
    snapshot = scan_repository(checkout, claimed.project_id, scope="full")
    repository.ingest_snapshot(claimed.project_id, snapshot.model_dump(mode="json"))
    repository.store_snapshot_sources(snapshot, checkout)
    generated = ua_result(checkout, "full", checkout / ".ua-test")
    imported = repository.import_understand_anything(
        claimed.project_id, snapshot.id, "test-UA@fixture",
        generated.knowledge_graph, generated.domain_graph,
    )
    completed = claimed.model_copy(update={
        "status": "completed", "mode": "full", "repository_revision": snapshot.revision,
        "repository_branch": snapshot.branch, "code_snapshot_id": snapshot.id,
        "ua_snapshot_id": imported["ua_snapshot"]["id"],
        "observed_revision_id": imported["observed_revision"]["id"],
        "completed_at": "2026-09-10T00:00:00Z", "duration_ms": 1,
    })
    return repository.finish_understanding_refresh(completed)


def test_viewer_session_uses_exact_snapshot_source_and_reverse_mapping(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    initialize_checkout(checkout)
    repository = CoIntentRepository(tmp_path / "cointent.db", tmp_path / "projects")
    repository.create_project("demo", "Demo")
    request = repository.request_understanding_refresh("demo", requested_by="user")
    completed = publish_observation(repository, checkout, request["job"]["id"])
    observed = repository.get_observed_revision(completed["observed_revision_id"])
    assert observed["implementation_refs"]
    ref = observed["implementation_refs"][0]
    assert ref["ua_snapshot_id"] == completed["ua_snapshot_id"]
    assert ref["code_snapshot_id"] == completed["code_snapshot_id"]

    issued = repository.create_ua_viewer_session(
        "demo", observed["id"], completed["ua_snapshot_id"], principal="carter",
    )
    token = issued["viewer_url"].split("session=", 1)[1].split("&", 1)[0]
    session = repository.resolve_ua_viewer_session(token, principal="carter")
    source = repository.read_snapshot_source(session, "service.py")
    assert "return 'current'" in source["content"]
    assert source["sourceDigest"]
    reverse = repository.semantic_subjects_for_ua_node(
        completed["ua_snapshot_id"], ref["preferred_focus_node_id"],
    )
    assert any(item["subject_id"] == ref["subject_id"] for item in reverse["subjects"])

    (checkout / "service.py").write_text("def serve():\n    return 'working tree must not leak'\n", encoding="utf-8")
    source_again = repository.read_snapshot_source(session, "service.py")
    assert source_again["content"] == source["content"]


def test_current_level_never_contains_grandchildren(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    initialize_checkout(checkout)
    repository = CoIntentRepository(tmp_path / "cointent.db", tmp_path / "projects")
    repository.create_project("demo", "Demo")
    request = repository.request_understanding_refresh("demo", requested_by="user")
    completed = publish_observation(repository, checkout, request["job"]["id"])
    root = repository.read_current_level("demo")
    assert all("workflow" not in item for item in root["level"]["children"])
    focus_id = root["level"]["children"][0]["id"]
    focused = repository.read_current_level("demo", focus_id=focus_id)
    assert all("workflow" not in item for item in focused["level"]["children"])
    assert set(focused["coordinate"]["observed_revision"]) == {
        "id", "parent_revision_id", "refinement_of_node_id", "content_digest", "created_at",
    }


def test_design_requires_explicit_refresh_and_exact_reviewed_diff(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    initialize_checkout(checkout)
    repository = CoIntentRepository(tmp_path / "cointent.db", tmp_path / "projects")
    repository.create_project("demo", "Demo")

    with pytest.raises(ValueError, match="update current understanding"):
        repository.start_structure_design("demo", "Next", actor="carter")

    requested = repository.request_understanding_refresh("demo", requested_by="carter")
    completed = publish_observation(repository, checkout, requested["job"]["id"])
    started = repository.start_structure_design("demo", "Next", actor="carter")
    assert started["revision"]["base_observed_revision_id"] == completed["observed_revision_id"]
    revision = started["revision"]
    changed = dict(revision["responsibilities"][0])
    changed["description"] = "Serve the explicitly designed next behavior."
    revised = repository.apply_design_operations_v04(
        started["workspace"]["id"], revision["id"], [
            {"kind": "upsert_responsibility", "responsibility": changed},
            {"kind": "set_acceptance_criteria", "acceptance_criteria": ["The next behavior is observable."]},
        ], actor="carter", rationale="Define the target and its success criterion.",
    )
    diff = repository.diff_structure_design(
        started["workspace"]["id"], to_revision_id=revised["revision"]["id"],
    )
    with pytest.raises(ValueError, match="diff digest"):
        repository.create_implementation_context(
            started["workspace"]["id"], revised["revision"]["id"], "wrong", actor="carter",
        )
    result = repository.create_implementation_context(
        started["workspace"]["id"], revised["revision"]["id"], diff["diff_digest"], actor="carter",
    )
    assert result["initiated_by"] == "carter"
    assert result["implementation_context"]["approved_by"] == "carter"
    assert "do not trigger" in result["implementation_context"]["agent_prompt"].lower()
    status_before = repository.get_design_workspace(started["workspace"]["id"])["status"]
    comparison = repository.compare_design_to_observation(
        revised["revision"]["id"], completed["observed_revision_id"],
    )
    assert comparison["kind"] == "informational_design_comparison"
    assert comparison["mutates_workspace"] is False
    assert repository.get_design_workspace(started["workspace"]["id"])["status"] == status_before
