import json
import subprocess
from pathlib import Path

import pytest

from cointent.refresh import UaRunResult, run_refresh_job
from cointent.repository import CoIntentRepository


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


def test_refresh_is_full_then_zero_work_then_incremental(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    initialize_checkout(checkout)
    repository = CoIntentRepository(tmp_path / "cointent.db", tmp_path / "projects")
    repository.create_project("demo", "Demo")
    repository.set_project_checkout("demo", checkout)
    modes: list[str] = []

    def run(project_root: Path, mode: str, state_root: Path) -> UaRunResult:
        modes.append(mode)
        return ua_result(project_root, mode, state_root)

    first_request = repository.request_understanding_refresh("demo", requested_by="user")
    first = run_refresh_job(repository, first_request["job"]["id"], ua_command=run)
    assert first["mode"] == "full"
    assert first["fallback_reason"] is None
    assert first["observed_revision_id"]
    assert modes == ["full"]

    second_request = repository.request_understanding_refresh("demo", requested_by="user")
    second = run_refresh_job(repository, second_request["job"]["id"], ua_command=run)
    assert second["mode"] == "unchanged"
    assert second["ua_files_reanalyzed"] == []
    assert second["observed_revision_id"] == first["observed_revision_id"]
    assert modes == ["full"]

    (checkout / "service.py").write_text("def serve():\n    return 'changed'\n", encoding="utf-8")
    git(checkout, "add", "service.py")
    git(checkout, "commit", "-qm", "change")
    third_request = repository.request_understanding_refresh("demo", requested_by="user")
    third = run_refresh_job(repository, third_request["job"]["id"], ua_command=run)
    assert third["mode"] == "incremental"
    assert third["changed_files"] == ["service.py"]
    assert third["ua_files_reanalyzed"] == ["service.py"]
    assert modes == ["full", "incremental"]


def test_corrupt_incremental_state_declares_full_fallback(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    initialize_checkout(checkout)
    repository = CoIntentRepository(tmp_path / "cointent.db", tmp_path / "projects")
    repository.create_project("demo", "Demo")
    repository.set_project_checkout("demo", checkout)
    first = repository.request_understanding_refresh("demo", requested_by="user")
    run_refresh_job(repository, first["job"]["id"], ua_command=ua_result)

    persistent = repository.asset_root / "demo" / "ua-runner-state"
    (persistent / "fingerprints.json").write_text("{truncated", encoding="utf-8")
    (checkout / "service.py").write_text("def serve():\n    return 'next'\n", encoding="utf-8")
    git(checkout, "add", "service.py")
    git(checkout, "commit", "-qm", "next")
    modes: list[str] = []

    def run(project_root: Path, mode: str, state_root: Path) -> UaRunResult:
        modes.append(mode)
        return ua_result(project_root, mode, state_root)

    requested = repository.request_understanding_refresh("demo", requested_by="user")
    completed = run_refresh_job(repository, requested["job"]["id"], ua_command=run)
    assert modes == ["full"]
    assert completed["mode"] == "full"
    assert completed["fallback_reason"] == "missing_or_invalid_ua_state"


def test_viewer_session_uses_exact_snapshot_source_and_reverse_mapping(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    initialize_checkout(checkout)
    repository = CoIntentRepository(tmp_path / "cointent.db", tmp_path / "projects")
    repository.create_project("demo", "Demo")
    repository.set_project_checkout("demo", checkout)
    request = repository.request_understanding_refresh("demo", requested_by="user")
    completed = run_refresh_job(repository, request["job"]["id"], ua_command=ua_result)
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
    repository.set_project_checkout("demo", checkout)
    request = repository.request_understanding_refresh("demo", requested_by="user")
    completed = run_refresh_job(repository, request["job"]["id"], ua_command=ua_result)
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
    repository.set_project_checkout("demo", checkout)

    with pytest.raises(ValueError, match="update current understanding"):
        repository.start_structure_design("demo", "Next", actor="carter")

    requested = repository.request_understanding_refresh("demo", requested_by="carter")
    completed = run_refresh_job(repository, requested["job"]["id"], ua_command=ua_result)
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
