import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cointent.design import DesignOperation
from cointent.delivery import semantic_target_diff
from cointent.design import DesignRevision
from cointent.observation import ObservedModelRevision
from cointent.repository import CoIntentRepository
from cointent.refresh import UnderstandingRefreshJob
from cointent.scanner import Artifact, RepositorySnapshot


FIXTURES = Path(__file__).parent / "fixtures" / "ua"


def repository_with_observation(tmp_path: Path) -> tuple[CoIntentRepository, dict]:
    repository = CoIntentRepository(tmp_path / "model.db")
    repository.create_project("demo", "Demo")
    snapshot = RepositorySnapshot(
        id="snapshot-design-full",
        project_id="demo",
        repository="demo",
        revision="f" * 40,
        branch="main",
        dirty=True,
        scope="full",
        captured_at="2026-09-09T00:00:00+00:00",
        artifacts=[
            Artifact(path="src/cointent/repository.py", kind="source", language="Python",
                     component="src/cointent", sha256="1" * 64, size=100, line_count=1200),
            Artifact(path="src/cointent/app.py", kind="source", language="Python",
                     component="src/cointent", sha256="2" * 64, size=100, line_count=200),
        ],
    )
    repository.ingest_snapshot("demo", snapshot.model_dump())
    imported = repository.import_understand_anything(
        "demo",
        snapshot.id,
        "ua-pin",
        json.loads((FIXTURES / "knowledge-graph.json").read_text(encoding="utf-8")),
        json.loads((FIXTURES / "domain-graph.json").read_text(encoding="utf-8")),
    )
    request = repository.request_understanding_refresh("demo", requested_by="test")
    claimed = UnderstandingRefreshJob.model_validate(
        repository.claim_understanding_refresh(request["job"]["id"])
    )
    repository.finish_understanding_refresh(claimed.model_copy(update={
        "status": "completed", "mode": "full", "repository_revision": snapshot.revision,
        "repository_branch": snapshot.branch, "code_snapshot_id": snapshot.id,
        "ua_snapshot_id": imported["ua_snapshot"]["id"],
        "observed_revision_id": imported["observed_revision"]["id"],
        "completed_at": "2026-09-09T00:01:00+00:00", "duration_ms": 1,
    }))
    return repository, imported["observed_revision"]


def test_observed_baseline_is_cloned_into_an_independent_design_namespace(tmp_path: Path) -> None:
    repository, observed = repository_with_observation(tmp_path)
    created = repository.create_design_workspace(
        "demo", observed["id"], "Improve project opening", actor="human", rationale="Start from reality.",
    )
    workspace = created["workspace"]
    revision = created["revision"]

    assert workspace["base_observed_revision_id"] == observed["id"]
    assert workspace["base_code_snapshot_id"] == observed["code_snapshot_id"]
    assert workspace["current_design_revision_id"] == revision["id"]
    assert all(item["id"].startswith("des-feature-") for item in revision["expected_features"])
    assert all(item["id"].startswith("des-resp-") for item in revision["responsibilities"])
    assert all(item["id"].startswith("des-link-") for item in revision["feature_responsibility_links"])
    assert {item["name"] for item in revision["responsibilities"]} == {
        item["name"] for item in observed["responsibilities"]
    }
    assert {item["observed_id"] for item in revision["baseline_links"]} >= {
        item["id"] for item in observed["responsibilities"]
    }
    assert repository.get_design_workspace_view("demo")["revision"]["id"] == revision["id"]
    assert semantic_target_diff(
        DesignRevision.model_validate(revision), ObservedModelRevision.model_validate(observed),
    ) == []
    target = tmp_path / "projects/demo/target-design" / workspace["id"]
    assert (target / "workspace.json").is_file()
    assert (target / "revisions" / f"{revision['id']}.json").is_file()


def test_design_cannot_bypass_the_explicit_refresh_precondition(tmp_path: Path) -> None:
    repository, observed = repository_with_observation(tmp_path)
    newer = repository.request_understanding_refresh("demo", requested_by="test")
    assert newer["job"]["status"] == "queued"
    with pytest.raises(ValueError, match="explicitly completed understanding refresh"):
        repository.create_design_workspace(
            "demo", observed["id"], "Stale start", actor="human", rationale="Must be rejected.",
        )


def test_typed_operations_publish_a_new_revision_and_keep_an_audit_trail(tmp_path: Path) -> None:
    repository, observed = repository_with_observation(tmp_path)
    created = repository.create_design_workspace(
        "demo", observed["id"], "Improve project opening", actor="human", rationale="Start from reality.",
    )
    workspace = created["workspace"]
    base = created["revision"]
    result = repository.apply_design_operations_v04(
        workspace["id"],
        base["id"],
        [
            {"kind": "set_intent", "summary": "Users should reopen their last project instantly."},
            {"kind": "upsert_expected_feature", "expected_feature": {
                "id": "des-feature-resume", "name": "Resume last project",
                "description": "Open the most recent workspace without another selection.",
            }},
            {"kind": "upsert_responsibility", "responsibility": {
                "id": "des-resp-resume", "name": "Resume project",
                "description": "Resolve and load the latest project coordinate.", "status": "draft",
            }},
            {"kind": "upsert_feature_link", "feature_link": {
                "id": "des-link-resume", "expected_feature_id": "des-feature-resume",
                "responsibility_id": "des-resp-resume", "kind": "realizes",
            }},
        ],
        actor="agent",
        rationale="Add the requested resume behavior as a reviewable target.",
    )
    revision = result["revision"]

    assert revision["id"] != base["id"]
    assert revision["parent_revision_id"] == base["id"]
    assert revision["summary"] == "Users should reopen their last project instantly."
    assert repository.get_design_revision_v04(base["id"])["summary"] != revision["summary"]
    assert repository.get_design_workspace(workspace["id"])["current_design_revision_id"] == revision["id"]
    audit = repository.list_design_operations_v04(workspace["id"])
    assert len(audit) == 4
    assert {item["actor"] for item in audit} == {"agent"}
    assert {item["rationale"] for item in audit} == {
        "Add the requested resume behavior as a reviewable target."
    }

    with pytest.raises(ValueError, match="stale"):
        repository.apply_design_operations_v04(
            workspace["id"], base["id"],
            [{"kind": "set_intent", "summary": "Stale overwrite"}],
            actor="human", rationale="This must not win.",
        )


def test_design_operations_reject_observed_mutation_targets() -> None:
    with pytest.raises(ValidationError, match="observed identities"):
        DesignOperation.model_validate({
            "kind": "remove_responsibility", "responsibility_id": "obs-resp-current",
        })
    with pytest.raises(ValidationError, match="des-resp namespace"):
        DesignOperation.model_validate({
            "kind": "upsert_responsibility",
            "responsibility": {"id": "human-picked-id", "name": "Invalid"},
        })


def test_human_review_approval_and_export_are_separate_and_reproducible(tmp_path: Path) -> None:
    repository, observed = repository_with_observation(tmp_path)
    created = repository.create_design_workspace(
        "demo", observed["id"], "Improve project opening", actor="human", rationale="Start from reality.",
    )
    workspace = created["workspace"]
    base = created["revision"]
    target = dict(base["responsibilities"][0])
    target["description"] = "Own current understanding and a faster return path."
    changed = repository.apply_design_operations_v04(
        workspace["id"], base["id"],
        [{"kind": "upsert_responsibility", "responsibility": target}],
        actor="agent", rationale="Propose the requested behavior change.",
    )

    with pytest.raises(ValueError, match="acceptance criterion"):
        repository.submit_design_review_v04(workspace["id"], [], actor="carter")
    review = repository.submit_design_review_v04(
        workspace["id"], ["Opening a project exposes a verified fast return path."], actor="carter",
    )
    assert review["status"] == "in_review"
    assert any(item["kind"] == "responsibility" for item in review["changes"])
    with pytest.raises(ValueError, match="human actor"):
        repository.approve_design_review_v04(review["id"], actor="agent")
    approval = repository.approve_design_review_v04(review["id"], actor="carter")
    assert approval["actor"] == "carter"

    first = repository.create_implementation_export_v04(workspace["id"])
    second = repository.create_implementation_export_v04(workspace["id"])
    assert first == second
    assert first["design_revision_id"] == changed["revision"]["id"]
    assert first["acceptance_criteria"][0]["statement"].startswith("Opening a project")
    assert first["evidence_context"]
    assert "do not write CoIntent observation or design storage directly" in first["agent_prompt"]
    assert (tmp_path / "projects/demo/target-design" / workspace["id"]
            / "exports" / f"{first['id']}.json").is_file()

    expansion = repository.request_observation_expansion(
        "demo", observed["id"], observed["capabilities"][0]["responsibility_id"], depth=1,
    )
    with pytest.raises(ValueError, match="full root observation"):
        repository.create_verification_report_v04(
            workspace["id"], expansion["request"]["result_observed_revision_id"],
        )

    stale = repository.create_verification_report_v04(workspace["id"], observed["id"])
    assert stale["summary"]["stale"] == len(changed["revision"]["expected_features"]) + len(changed["revision"]["responsibilities"])
    repository.decide_verification_v04(
        stale["id"], decision="needs_revision",
        notes="A post-implementation observation is still required.", actor="carter",
    )
    with pytest.raises(ValueError, match="already been reviewed"):
        repository.create_verification_report_v04(workspace["id"], observed["id"])

    later_snapshot = dict(repository.get_snapshot("snapshot-design-full")["snapshot"])
    later_snapshot.update({
        "id": "snapshot-after-implementation",
        "revision": "e" * 40,
        "captured_at": "2026-09-10T00:00:00+00:00",
    })
    repository.ingest_snapshot("demo", later_snapshot)
    knowledge = json.loads((FIXTURES / "knowledge-graph.json").read_text(encoding="utf-8"))
    domain = json.loads((FIXTURES / "domain-graph.json").read_text(encoding="utf-8"))
    domain["nodes"][0]["summary"] = target["description"]
    later = repository.import_understand_anything(
        "demo", later_snapshot["id"], "ua-pin", knowledge, domain,
    )["observed_revision"]
    report = repository.create_verification_report_v04(workspace["id"], later["id"])
    assert report["summary"] == {
        "matched": len(changed["revision"]["expected_features"]) + len(changed["revision"]["responsibilities"]),
        "missing": 0,
        "unexpected": 0,
        "ambiguous": 0,
        "stale": 0,
    }
    assert repository.get_design_workspace(workspace["id"])["status"] == "verifying"
    assert repository.get_design_workspace_view("demo")["verification_decision"] is None
    with pytest.raises(ValueError, match="human actor"):
        repository.decide_verification_v04(
            report["id"], decision="converged", notes="Looks good.", actor="agent",
        )
    decision = repository.decide_verification_v04(
        report["id"], decision="converged", notes="All acceptance checks passed.", actor="carter",
    )
    assert decision["decision"] == "converged"
    assert repository.get_design_workspace(workspace["id"])["status"] == "converged"
