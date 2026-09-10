import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from cointent.distribution import UA_REVISION, UA_VERSION
from cointent.remote_refresh import (
    ArtifactUploadSpec,
    NativeRefreshPreflight,
    canonical_repository_identity,
    complete_native_refresh,
    prepare_native_refresh,
    prepare_refresh_artifacts,
)
from cointent.repository import CoIntentRepository
from cointent.refresh import UnderstandingRefreshJob


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True).stdout.strip()


def commit_source(root: Path, content: str) -> str:
    (root / "service.py").write_text(content, encoding="utf-8")
    git(root, "add", "service.py")
    git(root, "commit", "-qm", "source")
    return git(root, "rev-parse", "HEAD")


def preflight(revision: str) -> NativeRefreshPreflight:
    return NativeRefreshPreflight(
        repository="git@example.test/demo.git", revision=revision, branch="master", clean=True,
        ua_version=UA_VERSION, ua_revision=UA_REVISION,
    )


def test_repository_identity_normalizes_common_git_transports() -> None:
    expected = "github.com/CarterShi01/idea-factory"
    assert canonical_repository_identity("https://github.com/CarterShi01/idea-factory") == expected
    assert canonical_repository_identity("git@github.com:CarterShi01/idea-factory.git") == expected
    assert canonical_repository_identity("ssh://git@github.com/CarterShi01/idea-factory.git") == expected


def make_bundles(root: Path, revision: str, content: str) -> tuple[Path, Path]:
    source_root = root / f"source-{revision[:7]}"
    source_root.mkdir(parents=True)
    payload = content.encode()
    (source_root / "service.py").write_bytes(payload)

    ua_root = root / f"ua-{revision[:7]}" / ".ua"
    (ua_root / "intermediate").mkdir(parents=True)
    lines = len(content.splitlines())
    project = {
        "name": "Demo", "languages": ["Python"], "frameworks": [],
        "description": "Demo", "analyzedAt": "2026-09-10T00:00:00Z", "gitCommitHash": revision,
    }
    knowledge = {
        "version": "1.0.0", "kind": "codebase", "project": project,
        "nodes": [
            {"id": "file:service", "type": "file", "name": "service.py", "filePath": "service.py", "lineRange": [1, lines], "summary": "Service."},
            {"id": "function:serve", "type": "function", "name": "serve", "filePath": "service.py", "lineRange": [1, lines], "summary": "Serve."},
        ],
        "edges": [{"source": "file:service", "target": "function:serve", "type": "contains"}],
        "layers": [], "tour": [],
    }
    domain = {
        "version": "1.0.0", "kind": "codebase", "project": project,
        "nodes": [
            {"id": "domain:service", "type": "domain", "name": "Service", "summary": "Own service."},
            {"id": "flow:serve", "type": "flow", "name": "Serve", "summary": "Serve request."},
            {"id": "step:serve", "type": "step", "name": "Run service", "filePath": "service.py", "lineRange": [1, lines], "summary": "Call serve."},
        ],
        "edges": [
            {"source": "domain:service", "target": "flow:serve", "type": "contains_flow"},
            {"source": "flow:serve", "target": "step:serve", "type": "flow_step"},
        ],
        "layers": [], "tour": [],
    }
    state = {
        "knowledge-graph.json": knowledge, "domain-graph.json": domain,
        "meta.json": {"gitCommitHash": revision}, "fingerprints.json": {"service.py": revision},
        "config.json": {"autoUpdate": False, "outputLanguage": "en"},
        "intermediate/scan-result.json": {"files": [{"path": "service.py"}]},
    }
    for name, value in state.items():
        target = ua_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value), encoding="utf-8")
    (ua_root / ".understandignore").write_text("", encoding="utf-8")

    source_archive = root / f"source-{revision[:7]}.tar.gz"
    ua_archive = root / f"ua-{revision[:7]}.tar.gz"
    with tarfile.open(
        source_archive, "w:gz", format=tarfile.PAX_FORMAT,
        pax_headers={"comment": revision},
    ) as bundle:
        bundle.add(source_root / "service.py", arcname="service.py")
    with tarfile.open(ua_archive, "w:gz") as bundle:
        bundle.add(ua_root, arcname=".ua")
    return source_archive, ua_archive


def upload_declared(repository: CoIntentRepository, job_id: str, archives: tuple[Path, Path], mode: str) -> None:
    source, ua = archives
    by_kind = {"source-snapshot": source, "ua-state": ua}
    specs = [
        ArtifactUploadSpec(kind=kind, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size_bytes=path.stat().st_size)
        for kind, path in by_kind.items()
    ]
    prepared = prepare_refresh_artifacts(repository, job_id, analysis_mode=mode, artifacts=specs)
    for transfer in prepared["uploads"]:
        record = next(item for item in repository.list_refresh_transfers(job_id) if item["id"] == transfer["id"])
        target = Path(record["asset_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(by_kind[record["kind"]], target)
        repository.complete_refresh_transfer(
            record["id"], digest=record["expected_digest"], size=int(record["expected_size"]),
        )


def test_remote_native_refresh_full_unchanged_and_incremental_without_server_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "remote-code"
    checkout.mkdir()
    git(checkout, "init", "-q", "-b", "master")
    git(checkout, "config", "user.email", "test@example.com")
    git(checkout, "config", "user.name", "Test")
    first_content = "def serve():\n    return 'first'\n"
    first_revision = commit_source(checkout, first_content)

    repository = CoIntentRepository(tmp_path / "cointent.db", tmp_path / "central-assets")
    repository.create_project("demo", "Demo", default_branch="master")
    requested = repository.request_understanding_refresh("demo", requested_by="agent")
    plan = prepare_native_refresh(repository, requested["job"]["id"], preflight(first_revision))
    assert plan["execution"]["mode"] == "full"
    assert plan["execution"]["checkpoint"] is None
    upload_declared(repository, requested["job"]["id"], make_bundles(tmp_path, first_revision, first_content), "full")
    completed = complete_native_refresh(repository, requested["job"]["id"])
    assert completed["status"] == "completed"
    assert completed["observed_revision_id"]
    assert repository.get_ua_checkpoint("demo")["base_revision"] == first_revision
    with repository.connection() as db:
        stored = db.execute(
            "SELECT snapshot_json,asset_path FROM understand_anything_snapshots WHERE id=?",
            (completed["ua_snapshot_id"],),
        ).fetchone()
    assert "knowledge_graph" not in json.loads(stored["snapshot_json"])
    assert Path(stored["asset_path"]).is_file()
    assert repository.get_understand_anything_snapshot(completed["ua_snapshot_id"])["knowledge_graph"]

    same = repository.request_understanding_refresh("demo", requested_by="agent")
    unchanged = prepare_native_refresh(repository, same["job"]["id"], preflight(first_revision))
    assert unchanged["execution"] == {"mode": "unchanged", "run_ua": False}
    assert unchanged["job"]["observed_revision_id"] == completed["observed_revision_id"]

    second_content = "def serve():\n    return 'second'\n"
    second_revision = commit_source(checkout, second_content)
    changed = repository.request_understanding_refresh("demo", requested_by="agent")
    incremental = prepare_native_refresh(repository, changed["job"]["id"], preflight(second_revision))
    assert incremental["execution"]["mode"] == "incremental"
    assert incremental["execution"]["checkpoint"]["direction"] == "download"
    upload_declared(repository, changed["job"]["id"], make_bundles(tmp_path, second_revision, second_content), "incremental")
    completed_again = complete_native_refresh(repository, changed["job"]["id"])
    assert completed_again["mode"] == "incremental"
    assert completed_again["changed_files"] == ["service.py"]
    assert completed_again["observed_revision_id"] != completed["observed_revision_id"]


def test_source_snapshot_identity_is_scoped_to_the_registered_project(tmp_path: Path) -> None:
    repository = CoIntentRepository(tmp_path / "db.sqlite", tmp_path / "assets")
    for project_id in ("first", "second"):
        repository.create_project(
            project_id, project_id.title(), repository="git@example.test/demo.git",
            default_branch="master",
        )
    revision = "d" * 40
    archives = make_bundles(tmp_path, revision, "def serve():\n    return 'same'\n")

    completed = []
    for project_id in ("first", "second"):
        job = repository.request_understanding_refresh(project_id, requested_by="agent")["job"]
        prepare_native_refresh(repository, job["id"], preflight(revision))
        upload_declared(repository, job["id"], archives, "full")
        completed.append(complete_native_refresh(repository, job["id"]))

    assert completed[0]["code_snapshot_id"] != completed[1]["code_snapshot_id"]
    assert repository.observation_coordinate("first")["status"] == "current"
    assert repository.observation_coordinate("second")["status"] == "current"


def test_published_refresh_recovers_idempotently_after_bookkeeping_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = CoIntentRepository(tmp_path / "db.sqlite", tmp_path / "assets")
    repository.create_project("demo", "Demo", repository="git@example.test/demo.git")
    revision = "e" * 40
    content = "def serve():\n    return 'stable'\n"
    job = repository.request_understanding_refresh("demo", requested_by="agent")["job"]
    prepare_native_refresh(repository, job["id"], preflight(revision))
    upload_declared(repository, job["id"], make_bundles(tmp_path, revision, content), "full")

    original_update = repository.update_native_understanding_refresh
    failed_once = False

    def fail_after_publication(candidate, *, expected_status):
        nonlocal failed_once
        if candidate.status == "completed" and not failed_once:
            failed_once = True
            raise OSError("simulated bookkeeping outage")
        return original_update(candidate, expected_status=expected_status)

    monkeypatch.setattr(repository, "update_native_understanding_refresh", fail_after_publication)
    with pytest.raises(OSError, match="bookkeeping outage"):
        complete_native_refresh(repository, job["id"])
    assert repository.get_understanding_refresh(job["id"])["status"] == "validating"

    monkeypatch.setattr(repository, "update_native_understanding_refresh", original_update)
    completed = complete_native_refresh(repository, job["id"])
    assert completed["status"] == "completed"
    snapshot_row = repository.get_snapshot(completed["code_snapshot_id"])["snapshot"]
    snapshot_asset = (
        tmp_path / "assets" / "demo" / "snapshots" / f"{completed['code_snapshot_id']}.json"
    )
    assert json.loads(snapshot_asset.read_text(encoding="utf-8")) == snapshot_row


def test_repository_startup_migrates_legacy_inline_ua_graph_to_asset(tmp_path: Path) -> None:
    database = tmp_path / "db.sqlite"
    asset_root = tmp_path / "assets"
    repository = CoIntentRepository(database, asset_root)
    repository.create_project("demo", "Demo", repository="git@example.test/demo.git")
    revision = "f" * 40
    content = "def serve():\n    return 'legacy'\n"
    job = repository.request_understanding_refresh("demo", requested_by="agent")["job"]
    prepare_native_refresh(repository, job["id"], preflight(revision))
    upload_declared(repository, job["id"], make_bundles(tmp_path, revision, content), "full")
    completed = complete_native_refresh(repository, job["id"])

    with repository.connection() as db:
        row = db.execute(
            "SELECT asset_path FROM understand_anything_snapshots WHERE id=?",
            (completed["ua_snapshot_id"],),
        ).fetchone()
        asset = Path(row["asset_path"])
        legacy_inline = asset.read_text(encoding="utf-8")
        db.execute(
            "UPDATE understand_anything_snapshots SET snapshot_json=?,asset_path='' WHERE id=?",
            (legacy_inline, completed["ua_snapshot_id"]),
        )
    asset.unlink()

    migrated = CoIntentRepository(database, asset_root)
    with migrated.connection() as db:
        stored = db.execute(
            "SELECT snapshot_json,asset_path FROM understand_anything_snapshots WHERE id=?",
            (completed["ua_snapshot_id"],),
        ).fetchone()
    assert "knowledge_graph" not in json.loads(stored["snapshot_json"])
    assert Path(stored["asset_path"]).is_file()
    assert migrated.get_understand_anything_snapshot(completed["ua_snapshot_id"])["knowledge_graph"]


def test_remote_refresh_rejects_dirty_wrong_branch_and_partial_state(tmp_path: Path) -> None:
    repository = CoIntentRepository(tmp_path / "cointent.db", tmp_path / "assets")
    repository.create_project("demo", "Demo", default_branch="master")
    job = repository.request_understanding_refresh("demo", requested_by="agent")["job"]
    dirty = preflight("a" * 40).model_copy(update={"clean": False})
    with pytest.raises(ValueError, match="clean worktree"):
        prepare_native_refresh(repository, job["id"], dirty)
    assert repository.get_understanding_refresh(job["id"])["status"] == "queued"

    wrong = preflight("a" * 40).model_copy(update={"branch": "feature"})
    with pytest.raises(ValueError, match="default branch"):
        prepare_native_refresh(repository, job["id"], wrong)

    unsupported = preflight("a" * 40).model_copy(update={"submodules_present": True})
    with pytest.raises(ValueError, match="Git submodules"):
        prepare_native_refresh(repository, job["id"], unsupported)


def test_remote_refresh_accepts_equivalent_registered_git_transport(tmp_path: Path) -> None:
    repository = CoIntentRepository(tmp_path / "cointent.db", tmp_path / "assets")
    registered = "https://github.com/CarterShi01/idea-factory"
    repository.create_project("demo", "Demo", repository=registered, default_branch="master")
    job = repository.request_understanding_refresh("demo", requested_by="agent")["job"]
    ssh_preflight = preflight("a" * 40).model_copy(update={
        "repository": "git@github.com:CarterShi01/idea-factory.git",
    })
    plan = prepare_native_refresh(repository, job["id"], ssh_preflight)
    assert plan["job"]["repository_identity"] == registered


def test_partial_native_state_fails_without_replacing_previous_observation(tmp_path: Path) -> None:
    checkout = tmp_path / "code"
    checkout.mkdir()
    git(checkout, "init", "-q", "-b", "master")
    git(checkout, "config", "user.email", "test@example.com")
    git(checkout, "config", "user.name", "Test")
    first_content = "def serve():\n    return 'first'\n"
    first_revision = commit_source(checkout, first_content)
    repository = CoIntentRepository(tmp_path / "db.sqlite", tmp_path / "assets")
    repository.create_project("demo", "Demo", default_branch="master")
    first = repository.request_understanding_refresh("demo", requested_by="agent")["job"]
    prepare_native_refresh(repository, first["id"], preflight(first_revision))
    upload_declared(repository, first["id"], make_bundles(tmp_path, first_revision, first_content), "full")
    published = complete_native_refresh(repository, first["id"])

    next_content = "def serve():\n    return 'next'\n"
    next_revision = commit_source(checkout, next_content)
    next_job = repository.request_understanding_refresh("demo", requested_by="agent")["job"]
    prepare_native_refresh(repository, next_job["id"], preflight(next_revision))
    source_archive, ua_archive = make_bundles(tmp_path, next_revision, next_content)
    ua_root = tmp_path / f"ua-{next_revision[:7]}" / ".ua"
    (ua_root / "intermediate" / "scan-result.json").unlink()
    with tarfile.open(ua_archive, "w:gz") as bundle:
        bundle.add(ua_root, arcname=".ua")
    upload_declared(repository, next_job["id"], (source_archive, ua_archive), "incremental")

    with pytest.raises(ValueError, match="incremental state is incomplete"):
        complete_native_refresh(repository, next_job["id"])
    assert repository.get_understanding_refresh(next_job["id"])["status"] == "failed"
    assert repository.observation_coordinate("demo")["observed_revision"]["id"] == published["observed_revision_id"]


def test_checkpoint_cache_failure_does_not_relabel_published_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = "def serve():\n    return 'ready'\n"
    repository = CoIntentRepository(tmp_path / "db.sqlite", tmp_path / "assets")
    repository.create_project("demo", "Demo", default_branch="master")
    job = repository.request_understanding_refresh("demo", requested_by="agent")["job"]
    revision = "c" * 40
    prepare_native_refresh(repository, job["id"], preflight(revision))
    upload_declared(repository, job["id"], make_bundles(tmp_path, revision, content), "full")

    def fail_checkpoint(*args, **kwargs):
        raise OSError("simulated cache storage outage")

    monkeypatch.setattr(repository, "promote_ua_checkpoint", fail_checkpoint)
    completed = complete_native_refresh(repository, job["id"])

    assert completed["status"] == "completed"
    assert any("checkpoint promotion failed" in item for item in completed["diagnostics"])
    assert repository.observation_coordinate("demo")["observed_revision"]["id"] == completed["observed_revision_id"]


def test_one_active_refresh_lease_covers_upload_and_validation_states(tmp_path: Path) -> None:
    repository = CoIntentRepository(tmp_path / "db.sqlite", tmp_path / "assets")
    repository.create_project("demo", "Demo")
    first = repository.request_understanding_refresh("demo", requested_by="one")
    running = repository.claim_understanding_refresh(first["job"]["id"])
    job = repository.get_understanding_refresh(running["id"])
    repository.update_native_understanding_refresh(
        UnderstandingRefreshJob.model_validate(job).model_copy(update={"status": "awaiting_upload"}),
        expected_status="running",
    )
    duplicate = repository.request_understanding_refresh("demo", requested_by="two")
    assert duplicate["duplicate"] is True
    assert duplicate["job"]["id"] == first["job"]["id"]


def test_safe_archive_rejects_path_traversal(tmp_path: Path) -> None:
    from cointent.remote_refresh import _safe_extract_tar

    archive = tmp_path / "bad.tar.gz"
    payload = tmp_path / "payload"
    payload.write_text("bad", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(payload, arcname="../escape")
    with pytest.raises(ValueError, match="unsafe archive path"):
        _safe_extract_tar(archive, tmp_path / "out")


def test_safe_archive_rejects_duplicate_paths(tmp_path: Path) -> None:
    from cointent.remote_refresh import _safe_extract_tar

    archive = tmp_path / "duplicate.tar.gz"
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(first, arcname="same.txt")
        bundle.add(second, arcname="same.txt")
    with pytest.raises(ValueError, match="duplicate path"):
        _safe_extract_tar(archive, tmp_path / "out")


def test_source_archive_must_carry_the_frozen_git_coordinate(tmp_path: Path) -> None:
    from cointent.remote_refresh import _safe_extract_tar

    archive = tmp_path / "source.tar.gz"
    payload = tmp_path / "payload"
    payload.write_text("source", encoding="utf-8")
    with tarfile.open(
        archive, "w:gz", format=tarfile.PAX_FORMAT,
        pax_headers={"comment": "a" * 40},
    ) as bundle:
        bundle.add(payload, arcname="source.py")
    with pytest.raises(ValueError, match="Git coordinate"):
        _safe_extract_tar(archive, tmp_path / "out", expected_git_revision="b" * 40)
