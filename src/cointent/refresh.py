"""On-demand Understand Anything refresh jobs and the trusted worker boundary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .observation import UAKnowledgeGraph, build_ua_snapshot, project_observed_model
from .scanner import RepositorySnapshot, scan_repository, snapshot_diff


UA_VERSION = "2.9.6"
UA_REVISION = "5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc"


def now() -> str:
    return datetime.now(UTC).isoformat()


class UnderstandingRefreshJob(BaseModel):
    """Persistent public view of one explicitly requested understanding refresh."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["cointent.understanding-refresh/0.1"] = "cointent.understanding-refresh/0.1"
    id: str
    project_id: str
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    mode: Literal["unchanged", "incremental", "full"] | None = None
    requested_by: str
    changed_files: list[str] = Field(default_factory=list)
    ua_files_reanalyzed: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None
    diagnostics: list[str] = Field(default_factory=list)
    repository_revision: str | None = None
    code_snapshot_id: str | None = None
    ua_snapshot_id: str | None = None
    observed_revision_id: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class UaRunResult(BaseModel):
    """Artifacts emitted by the single pinned Understand Anything integration."""

    model_config = ConfigDict(extra="forbid")
    knowledge_graph: dict[str, Any]
    domain_graph: dict[str, Any] | None = None
    files_reanalyzed: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


UaCommand = Callable[[Path, Literal["incremental", "full"], Path], UaRunResult]


def configured_ua_command(
    project_root: Path, mode: Literal["incremental", "full"], state_root: Path,
) -> UaRunResult:
    """Invoke a configured headless Agent command that runs pinned UA skills.

    Understand Anything 2.9.6 is distributed as Agent skills rather than a normal
    non-interactive analyzer executable.  CoIntent therefore owns the job and
    artifact boundary while the deployment supplies one trusted Agent command.
    The command is a JSON argv array, never a shell expression.  It receives a
    generated instruction as its final argument and must leave complete artifacts
    in ``state_root``.
    """

    raw = os.environ.get("COINTENT_UA_AGENT_COMMAND_JSON", "")
    if not raw:
        raise RuntimeError(
            "COINTENT_UA_AGENT_COMMAND_JSON is not configured; install Understand Anything "
            f"{UA_VERSION} ({UA_REVISION}) in a trusted Agent runtime"
        )
    try:
        argv = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("COINTENT_UA_AGENT_COMMAND_JSON must be a JSON argv array") from error
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise RuntimeError("COINTENT_UA_AGENT_COMMAND_JSON must be a non-empty JSON string array")

    state_root.mkdir(parents=True, exist_ok=True)
    prompt = _ua_prompt(project_root, mode, state_root)
    started = time.monotonic()
    result = subprocess.run(
        [*argv, prompt], cwd=project_root, text=True, capture_output=True, check=False,
        env={**os.environ, "UNDERSTAND_NO_WORKTREE_REDIRECT": "1"},
    )
    log = state_root / "cointent-runner.log"
    log.write_text(
        f"duration_ms={int((time.monotonic() - started) * 1000)}\n"
        f"exit_code={result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n",
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(f"Understand Anything Agent command failed with exit code {result.returncode}")
    knowledge_path = state_root / "knowledge-graph.json"
    domain_path = state_root / "domain-graph.json"
    if not knowledge_path.is_file():
        raise RuntimeError("Understand Anything completed without knowledge-graph.json")
    files = _reanalyzed_files(state_root, mode)
    return UaRunResult(
        knowledge_graph=json.loads(knowledge_path.read_text(encoding="utf-8")),
        domain_graph=(json.loads(domain_path.read_text(encoding="utf-8")) if domain_path.is_file() else None),
        files_reanalyzed=files,
        diagnostics=["Pinned UA Agent execution completed; see cointent-runner.log."],
    )


def _ua_prompt(project_root: Path, mode: str, state_root: Path) -> str:
    flag = " --full" if mode == "full" else ""
    return (
        "Run the installed Understand Anything 2.9.6 skill against the exact repository path "
        f"{project_root}. Use /understand{flag}, then run /understand-domain in full. "
        "Do not launch the dashboard, enable auto-update, or edit source code. "
        f"CoIntent's persistent UA directory is {state_root}; ensure the completed .ua artifacts "
        "are stored there. Return non-zero on any incomplete analysis."
    )


def _reanalyzed_files(state_root: Path, mode: str) -> list[str]:
    plan = state_root / "intermediate" / "incremental-plan.json"
    if mode == "incremental" and plan.is_file():
        try:
            payload = json.loads(plan.read_text(encoding="utf-8"))
            values = payload.get("filesToReanalyze", [])
            if isinstance(values, list):
                return sorted(str(item) for item in values)
        except (OSError, json.JSONDecodeError):
            pass
    graph = state_root / "knowledge-graph.json"
    if not graph.is_file():
        return []
    try:
        payload = json.loads(graph.read_text(encoding="utf-8"))
        return sorted({str(node["filePath"]) for node in payload.get("nodes", []) if node.get("filePath")})
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return []


def ua_state_is_valid(state_root: Path) -> bool:
    required = ("knowledge-graph.json", "meta.json", "fingerprints.json", "config.json")
    try:
        if not all((state_root / name).is_file() and (state_root / name).stat().st_size > 0 for name in required):
            return False
        # Incremental mode is safe only when all persisted state is parseable.
        # In particular, a non-empty but truncated fingerprint file must be a
        # declared full fallback rather than an opaque incremental failure.
        UAKnowledgeGraph.model_validate_json(
            (state_root / "knowledge-graph.json").read_text(encoding="utf-8")
        )
        for name in ("meta.json", "fingerprints.json", "config.json"):
            payload = json.loads((state_root / name).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return False
        return True
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return False


def changed_paths(before: RepositorySnapshot | None, after: RepositorySnapshot) -> list[str]:
    delta = snapshot_diff(before, after)
    return sorted({*delta["added"], *delta["modified"], *delta["removed"]})


def copy_ua_state(source: Path, target: Path) -> None:
    """Replace persisted UA state only after a successful isolated run."""

    staging = target.with_name(f"{target.name}.staging")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(source, staging)
    if target.exists():
        backup = target.with_name(f"{target.name}.previous")
        if backup.exists():
            shutil.rmtree(backup)
        target.replace(backup)
        staging.replace(target)
        shutil.rmtree(backup)
    else:
        staging.replace(target)


def capture_repository(project_root: Path, project_id: str) -> RepositorySnapshot:
    return scan_repository(project_root, project_id, scope="full")


def run_refresh_job(
    repository: Any, job_id: str, *, ua_command: UaCommand = configured_ua_command,
) -> dict[str, Any]:
    """Run one claimed job outside the interactive HTTP process.

    Publication is deliberately last: a failed UA run or validation leaves the
    previous root Observation visible and records a failed job only.
    """

    started = time.monotonic()
    claimed = UnderstandingRefreshJob.model_validate(repository.claim_understanding_refresh(job_id))
    try:
        checkout = repository.get_project_checkout(claimed.project_id)
        snapshot = capture_repository(checkout, claimed.project_id)
        if snapshot.dirty:
            raise RuntimeError(
                "trusted refresh requires a clean Git coordinate; commit or stash working-tree changes"
            )
        coordinate = repository.observation_coordinate(claimed.project_id)
        previous_revision = coordinate.get("observed_revision")
        previous_snapshot = None
        if previous_revision is not None:
            previous_snapshot = RepositorySnapshot.model_validate(
                repository.get_snapshot(previous_revision["code_snapshot_id"])["snapshot"]
            )
        paths = changed_paths(previous_snapshot, snapshot)
        repository.ingest_snapshot(claimed.project_id, snapshot.model_dump(mode="json"))
        repository.store_snapshot_sources(snapshot, checkout)
        if previous_revision is not None and not paths:
            completed = claimed.model_copy(update={
                "status": "completed",
                "mode": "unchanged",
                "changed_files": [],
                "ua_files_reanalyzed": [],
                "repository_revision": snapshot.revision,
                "code_snapshot_id": previous_revision["code_snapshot_id"],
                "ua_snapshot_id": previous_revision["ua_snapshot_id"],
                "observed_revision_id": previous_revision["id"],
                "duration_ms": int((time.monotonic() - started) * 1000),
                "completed_at": now(),
            })
            return repository.finish_understanding_refresh(completed)

        persistent_state = repository.asset_root / claimed.project_id / "ua-runner-state"
        valid_state = ua_state_is_valid(persistent_state)
        mode: Literal["incremental", "full"] = "incremental" if valid_state else "full"
        fallback_reason = None
        if mode == "full" and previous_revision is not None:
            fallback_reason = "missing_or_invalid_ua_state"

        runner_parent = repository.asset_root / claimed.project_id / "runner-worktrees"
        runner_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="refresh-", dir=runner_parent) as temporary:
            worktree = Path(temporary) / "checkout"
            _git(checkout, "worktree", "add", "--detach", str(worktree), snapshot.revision)
            try:
                state = worktree / ".ua"
                if valid_state:
                    shutil.copytree(persistent_state, state)
                result = ua_command(worktree, mode, state)
                if _git(worktree, "status", "--porcelain", "--untracked-files=no"):
                    raise RuntimeError("Understand Anything runner modified tracked source in its isolated checkout")
                # Validate the complete candidate and its projection before
                # promoting runner state or publishing any new Observation.
                knowledge = UAKnowledgeGraph.model_validate(result.knowledge_graph)
                domain = (
                    None if result.domain_graph is None
                    else UAKnowledgeGraph.model_validate(result.domain_graph)
                )
                candidate = build_ua_snapshot(
                    project_id=claimed.project_id,
                    code_snapshot=snapshot,
                    ua_tool_revision=f"Understand Anything {UA_VERSION}@{UA_REVISION}",
                    knowledge_graph=knowledge,
                    domain_graph=domain,
                    created_at=now(),
                )
                project_observed_model(candidate, snapshot, created_at=now())
                copy_ua_state(state, persistent_state)
                imported = repository.import_understand_anything(
                    claimed.project_id,
                    snapshot.id,
                    f"Understand Anything {UA_VERSION}@{UA_REVISION}",
                    result.knowledge_graph,
                    result.domain_graph,
                )
            finally:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree)],
                    cwd=checkout, capture_output=True, check=False,
                )
        completed = claimed.model_copy(update={
            "status": "completed",
            "mode": mode,
            "changed_files": paths,
            "ua_files_reanalyzed": result.files_reanalyzed,
            "fallback_reason": fallback_reason,
            "diagnostics": result.diagnostics,
            "repository_revision": snapshot.revision,
            "code_snapshot_id": snapshot.id,
            "ua_snapshot_id": imported["ua_snapshot"]["id"],
            "observed_revision_id": imported["observed_revision"]["id"],
            "duration_ms": int((time.monotonic() - started) * 1000),
            "completed_at": now(),
        })
        return repository.finish_understanding_refresh(completed)
    except Exception as error:
        failed = claimed.model_copy(update={
            "status": "failed",
            "error": str(error),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "completed_at": now(),
        })
        repository.finish_understanding_refresh(failed)
        raise


def _git(checkout: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=checkout, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()
