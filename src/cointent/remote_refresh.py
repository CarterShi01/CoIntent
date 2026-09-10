"""Refresh protocol for native UA running in the Agent's code environment."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tarfile
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .distribution import UA_REVISION, UA_VERSION
from .observation import UAKnowledgeGraph, build_ua_snapshot, project_observed_model
from .refresh import UnderstandingRefreshJob
from .scanner import Artifact, RepositorySnapshot, snapshot_diff


MAX_ARCHIVE_ENTRIES = 100_000
MAX_EXPANDED_BYTES = int(os.environ.get("COINTENT_MAX_REFRESH_EXPANDED_BYTES", str(2 * 1024**3)))
UA_TOOL_REVISION = f"Understand Anything {UA_VERSION}@{UA_REVISION}"


def canonical_repository_identity(value: str) -> str:
    """Normalize common Git transports without weakening repository ownership checks."""

    raw = value.strip()
    if not raw:
        return raw
    scp = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(.+)", raw)
    if scp and "://" not in raw:
        host, path = scp.groups()
        path = path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return f"{host.lower()}/{path}"
    parsed = urlsplit(raw)
    if parsed.scheme in {"http", "https", "ssh", "git"} and parsed.hostname:
        host = parsed.hostname.lower()
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return f"{host}/{path}"
    return raw.rstrip("/")


class NativeRefreshPreflight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository: str
    revision: str
    branch: str
    clean: bool
    untracked_files: list[str] = Field(default_factory=list)
    submodules_present: bool = False
    lfs_pointers_present: bool = False
    symlinks_present: bool = False
    archive_attributes_present: bool = False
    ua_version: str
    ua_revision: str

    @model_validator(mode="after")
    def validate_coordinate(self) -> "NativeRefreshPreflight":
        if not re.fullmatch(r"[0-9a-f]{40}", self.revision):
            raise ValueError("repository revision must be a full lowercase Git SHA")
        if not self.repository.strip():
            raise ValueError("repository identity is required")
        return self


class ArtifactUploadSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ua-state", "source-snapshot"]
    sha256: str
    size_bytes: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_digest(self) -> "ArtifactUploadSpec":
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("artifact sha256 must be a full lowercase digest")
        return self


def analysis_profile_digest(project: dict[str, Any]) -> str:
    identity = {
        "ua_revision": UA_REVISION,
        "output_language": project.get("language", "en"),
        "auto_update": False,
        "branch": project.get("default_branch", "master"),
        "profile_version": "cointent-native-ua/0.1",
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def prepare_native_refresh(repository: Any, job_id: str, preflight: NativeRefreshPreflight) -> dict[str, Any]:
    """Freeze the execution coordinate and return an Agent-local native UA plan."""

    job = UnderstandingRefreshJob.model_validate(repository.get_understanding_refresh(job_id))
    if job.status != "queued":
        if job.status == "completed":
            return {"job": job.model_dump(mode="json"), "duplicate": True, "execution": None}
        raise ValueError("understanding refresh is not awaiting native execution")
    project = repository.get_project(job.project_id)
    if project.get("repository") and canonical_repository_identity(
        preflight.repository
    ) != canonical_repository_identity(project["repository"]):
        raise ValueError("preflight repository identity does not match the registered project")
    if preflight.branch != project["default_branch"]:
        raise ValueError("V1 refresh must analyze the project's configured default branch")
    if not preflight.clean or preflight.untracked_files:
        raise ValueError("refresh requires a clean worktree with no non-ignored untracked files")
    unsupported = [
        name for name, present in (
            ("Git submodules", preflight.submodules_present),
            ("Git LFS pointers", preflight.lfs_pointers_present),
            ("tracked symbolic links", preflight.symlinks_present),
            ("export-ignore/export-subst attributes", preflight.archive_attributes_present),
        ) if present
    ]
    if unsupported:
        raise ValueError(f"V1 source snapshot does not support {', '.join(unsupported)}")
    if preflight.ua_version != UA_VERSION or preflight.ua_revision != UA_REVISION:
        raise ValueError("native UA installation is not the supported analyzer/validator/Viewer unit")

    profile = analysis_profile_digest(project)
    started = repository.start_native_understanding_refresh(
        job_id, repository_revision=preflight.revision, repository_branch=preflight.branch,
        analysis_profile_digest=profile,
    )
    running = UnderstandingRefreshJob.model_validate(started["job"])
    coordinate = repository.observation_coordinate(job.project_id)
    previous = coordinate.get("observed_revision")
    running = running.model_copy(update={
        "repository_identity": project.get("repository") or preflight.repository,
        "base_observed_revision_id": None if previous is None else previous["id"],
    })
    if previous is not None:
        previous_snapshot = repository.get_snapshot(previous["code_snapshot_id"])["snapshot"]
        if previous_snapshot["revision"] == preflight.revision:
            completed = running.model_copy(update={
                "status": "completed", "mode": "unchanged", "changed_files": [],
                "ua_files_reanalyzed": [], "code_snapshot_id": previous["code_snapshot_id"],
                "ua_snapshot_id": previous["ua_snapshot_id"], "observed_revision_id": previous["id"],
                "completed_at": _now(), "duration_ms": 0,
            })
            return {
                "job": repository.finish_understanding_refresh(completed), "duplicate": False,
                "execution": {"mode": "unchanged", "run_ua": False},
            }

    checkpoint = started["checkpoint"]
    compatible_checkpoint = bool(
        checkpoint
        and checkpoint["branch"] == preflight.branch
        and checkpoint["ua_tool_revision"] == UA_TOOL_REVISION
        and checkpoint["profile_digest"] == profile
    )
    mode: Literal["incremental", "full"] = "incremental" if compatible_checkpoint else "full"
    fallback = None if compatible_checkpoint or previous is None else "missing_or_incompatible_central_ua_state"
    running = running.model_copy(update={"mode": mode, "fallback_reason": fallback})
    repository.update_native_understanding_refresh(running, expected_status="running")
    checkpoint_transfer = None
    if compatible_checkpoint:
        checkpoint_transfer = repository.issue_refresh_transfer(
            job_id, kind="checkpoint", direction="download",
            expected_digest=checkpoint["content_digest"], expected_size=int(checkpoint["size_bytes"]),
            source_path=Path(checkpoint["asset_path"]),
        )
        checkpoint_transfer["url"] = _public_url(checkpoint_transfer["url"])

    return {
        "job": running.model_dump(mode="json"), "duplicate": False,
        "execution": {
            "mode": mode,
            "run_ua": True,
            "repository_revision": preflight.revision,
            "repository_branch": preflight.branch,
            "analysis_profile_digest": profile,
            "checkpoint": checkpoint_transfer,
            "checkpoint_base_revision": running.checkpoint_base_revision,
            "instructions": [
                "Create a detached temporary Git worktree at the exact repository revision.",
                "If a checkpoint is supplied, verify its base commit is an ancestor, download it, and restore .ua; otherwise run full.",
                "Set UNDERSTAND_NO_WORKTREE_REDIRECT=1.",
                f"Run the native UA understand Skill with --no-auto-update and output language {project.get('language', 'en')}.",
                "Run the native understand-domain Skill after a changed knowledge graph; do not launch the local Dashboard.",
                "Create the documented source-snapshot and complete UA-state tar.gz bundles, then request upload capabilities.",
            ],
            "bundle_contract": {
                "ua_state": "tar.gz containing .ua/ (or legacy .understand-anything/) with complete incremental state",
                "source_snapshot": "standard git archive --format=tar.gz of the frozen revision, with files at archive root",
            },
        },
    }


def prepare_refresh_artifacts(
    repository: Any, job_id: str, *, analysis_mode: Literal["incremental", "full"],
    artifacts: list[ArtifactUploadSpec], fallback_reason: str | None = None,
    files_reanalyzed: list[str] | None = None,
) -> dict[str, Any]:
    job = UnderstandingRefreshJob.model_validate(repository.get_understanding_refresh(job_id))
    if job.status not in {"running", "awaiting_upload"}:
        raise ValueError("understanding refresh is not running native UA or awaiting renewed uploads")
    if job.status == "awaiting_upload" and job.mode != analysis_mode:
        raise ValueError("upload renewal cannot change the already declared native analysis mode")
    by_kind = {item.kind: item for item in artifacts}
    if len(by_kind) != len(artifacts) or set(by_kind) != {"ua-state", "source-snapshot"}:
        raise ValueError("exactly one ua-state and one source-snapshot artifact are required")
    if analysis_mode == "incremental" and job.checkpoint_base_revision is None:
        raise ValueError("incremental completion requires a supplied central checkpoint")
    if job.mode == "incremental" and analysis_mode == "full" and not fallback_reason:
        raise ValueError("a native incremental-to-full fallback must report its reason")
    analyzed = sorted({_safe_relative_path(path) for path in (files_reanalyzed or [])})
    upload_limit = int(os.environ.get("COINTENT_MAX_REFRESH_UPLOAD_BYTES", str(1024**3)))
    if any(item.size_bytes > upload_limit for item in artifacts):
        raise ValueError("refresh artifact exceeds the configured upload limit")
    transfers = [
        repository.issue_refresh_transfer(
            job_id, kind=item.kind, direction="upload", expected_digest=item.sha256,
            expected_size=item.size_bytes,
        )
        for item in artifacts
    ]
    for transfer in transfers:
        transfer["url"] = _public_url(transfer["url"])
    awaiting = job.model_copy(update={
        "status": "awaiting_upload", "mode": analysis_mode,
        "fallback_reason": fallback_reason or job.fallback_reason, "ua_files_reanalyzed": analyzed,
    })
    repository.update_native_understanding_refresh(awaiting, expected_status=job.status)
    return {
        "job": awaiting.model_dump(mode="json"), "uploads": transfers,
        "next_action": "PUT each artifact directly to its signed URL, then call complete-native-refresh.",
    }


def complete_native_refresh(repository: Any, job_id: str) -> dict[str, Any]:
    """Validate staged native artifacts and publish only the complete candidate."""

    job = UnderstandingRefreshJob.model_validate(repository.get_understanding_refresh(job_id))
    if job.status == "completed":
        return job.model_dump(mode="json")
    if job.status not in {"awaiting_upload", "validating"}:
        raise ValueError("understanding refresh is not awaiting uploaded artifacts")
    transfers = {
        item["kind"]: item for item in repository.list_refresh_transfers(job_id)
        if item["direction"] == "upload"
    }
    if set(transfers) != {"ua-state", "source-snapshot"} or any(
        item["status"] != "uploaded" for item in transfers.values()
    ):
        raise ValueError("both declared refresh artifacts must finish uploading before completion")
    validating = job.model_copy(update={"status": "validating"})
    if job.status == "awaiting_upload":
        validating = UnderstandingRefreshJob.model_validate(
            repository.update_native_understanding_refresh(validating, expected_status="awaiting_upload")
        )
    started = time.monotonic()
    published = False
    try:
        with tempfile.TemporaryDirectory(prefix="cointent-native-refresh-") as temporary:
            root = Path(temporary)
            source_root = root / "source"
            ua_root = root / "ua"
            # A bookkeeping retry must reconstruct byte-for-byte identical immutable records.
            coordinate_created_at = validating.started_at or validating.created_at
            _safe_extract_tar(
                Path(transfers["source-snapshot"]["asset_path"]), source_root,
                expected_git_revision=validating.repository_revision,
            )
            _safe_extract_tar(Path(transfers["ua-state"]["asset_path"]), ua_root)
            snapshot, files_root = _load_source_snapshot(
                source_root, validating, captured_at=coordinate_created_at,
            )
            state = _locate_ua_state(ua_root)
            knowledge, domain = _load_complete_ua_state(state, validating.repository_revision or "")

            # Validate the complete candidate and projection before any visible coordinate advances.
            candidate = build_ua_snapshot(
                project_id=validating.project_id, code_snapshot=snapshot,
                ua_tool_revision=UA_TOOL_REVISION, knowledge_graph=knowledge, domain_graph=domain,
                created_at=coordinate_created_at,
            )
            candidate_observed = project_observed_model(
                candidate, snapshot, created_at=coordinate_created_at,
            )
            coordinate = repository.observation_coordinate(validating.project_id)
            previous = coordinate.get("observed_revision")
            current_id = None if previous is None else previous["id"]
            already_published = False
            if current_id != validating.base_observed_revision_id:
                if previous is None or previous["code_snapshot_id"] != snapshot.id or previous["ua_snapshot_id"] != candidate.id:
                    raise ValueError("current Observation changed after this refresh froze its baseline")
                already_published = True
            project = repository.get_project(validating.project_id)
            if project["default_branch"] != validating.repository_branch:
                raise ValueError("project default branch changed during refresh")
            previous_snapshot = None
            if previous is not None:
                previous_snapshot = RepositorySnapshot.model_validate(
                    repository.get_snapshot(previous["code_snapshot_id"])["snapshot"]
                )
            changed = snapshot_diff(previous_snapshot, snapshot)
            changed_files = sorted({*changed["added"], *changed["modified"], *changed["removed"]})

            if already_published:
                imported = {
                    "ua_snapshot": repository.get_understand_anything_snapshot(candidate.id),
                    "observed_revision": previous,
                }
                published = True
            else:
                repository.store_uploaded_snapshot_sources(snapshot, files_root)
                imported = repository.publish_native_observation(
                    snapshot, candidate, candidate_observed,
                    expected_base_observed_revision_id=validating.base_observed_revision_id,
                )
                published = True
            checkpoint_diagnostic: list[str] = []
            try:
                repository.promote_ua_checkpoint(
                    validating.project_id, branch=validating.repository_branch or "",
                    base_revision=snapshot.revision, ua_tool_revision=UA_TOOL_REVISION,
                    profile_digest=validating.analysis_profile_digest or "",
                    content_digest=transfers["ua-state"]["expected_digest"],
                    size_bytes=int(transfers["ua-state"]["expected_size"]),
                    source_path=Path(transfers["ua-state"]["asset_path"]),
                )
            except Exception as checkpoint_error:
                # A checkpoint is an optimization. Once the immutable Observation transaction commits, a cache
                # failure must not relabel valid current truth as failed; the next refresh falls back to full.
                checkpoint_diagnostic.append(
                    f"UA checkpoint promotion failed; next refresh may run full: {checkpoint_error}"
                )
            completed = validating.model_copy(update={
                "status": "completed", "changed_files": changed_files,
                "code_snapshot_id": snapshot.id,
                "ua_snapshot_id": imported["ua_snapshot"]["id"],
                "observed_revision_id": imported["observed_revision"]["id"],
                "duration_ms": int((time.monotonic() - started) * 1000),
                "completed_at": _now(),
                "diagnostics": [
                    *validating.diagnostics,
                    "Native UA artifacts passed coordinate, schema, evidence, and projection validation.",
                    *checkpoint_diagnostic,
                ],
            })
        result = repository.update_native_understanding_refresh(completed, expected_status="validating")
        repository.purge_refresh_staging(job_id)
        return result
    except Exception as error:
        if published:
            # Leave the recoverable state at `validating`; replay will detect the exact published coordinate and
            # finish bookkeeping without republishing it.
            raise
        failed = validating.model_copy(update={
            "status": "failed", "error": str(error),
            "duration_ms": int((time.monotonic() - started) * 1000), "completed_at": _now(),
        })
        repository.update_native_understanding_refresh(failed, expected_status="validating")
        repository.purge_refresh_staging(job_id)
        raise


def _load_source_snapshot(
    root: Path, job: UnderstandingRefreshJob, *, captured_at: str,
) -> tuple[RepositorySnapshot, Path]:
    """Build a deterministic manifest from a standard `git archive` extraction."""

    files_root = root
    values = sorted(item for item in files_root.rglob("*") if item.is_file())
    if not values:
        raise ValueError("source Git archive must contain at least one tracked file")
    artifacts: list[Artifact] = []
    seen: set[str] = set()
    for payload_path in values:
        path = _safe_relative_path(payload_path.relative_to(files_root).as_posix())
        if path in seen:
            raise ValueError(f"duplicate source archive path {path!r}")
        seen.add(path)
        digest, size, expected_lines = _hash_source_file(payload_path)
        artifacts.append(Artifact(
            path=path, kind=_kind(path), language=_language(path), component=_component(path),
            sha256=digest, size=size, line_count=expected_lines,
        ))
    artifacts.sort(key=lambda item: item.path)
    identity = hashlib.sha256(json.dumps({
        "project_id": job.project_id,
        "repository": job.repository_identity,
        "revision": job.repository_revision, "scope": "full",
        "branch": job.repository_branch,
        "artifacts": [(item.path, item.sha256) for item in artifacts], "relations": [],
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]
    return RepositorySnapshot(
        id=f"snapshot-{identity}", project_id=job.project_id,
        repository=job.repository_identity or "remote-agent",
        revision=job.repository_revision or "", branch=job.repository_branch or "",
        dirty=False, captured_at=captured_at, scope="full", artifacts=artifacts, relations=[],
        entrypoints={}, language_counts=dict(sorted(Counter(item.language for item in artifacts).items())),
    ), files_root


def _locate_ua_state(root: Path) -> Path:
    candidates = [root / ".ua", root / ".understand-anything", root]
    for candidate in candidates:
        if (candidate / "knowledge-graph.json").is_file():
            return candidate
    raise ValueError("UA archive has no .ua or legacy state directory")


def _load_complete_ua_state(state: Path, revision: str) -> tuple[UAKnowledgeGraph, UAKnowledgeGraph]:
    required = (
        "knowledge-graph.json", "domain-graph.json", "meta.json", "fingerprints.json",
        "config.json", ".understandignore", "intermediate/scan-result.json",
    )
    missing = [name for name in required if not (state / name).is_file()]
    if missing:
        raise ValueError(f"UA incremental state is incomplete: {missing!r}")
    for name in ("meta.json", "fingerprints.json", "config.json", "intermediate/scan-result.json"):
        value = json.loads((state / name).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"UA state {name!r} must contain a JSON object")
        if name == "meta.json" and value.get("gitCommitHash") != revision:
            raise ValueError("UA metadata does not match the frozen Git revision")
    knowledge = UAKnowledgeGraph.model_validate_json((state / "knowledge-graph.json").read_text(encoding="utf-8"))
    domain = UAKnowledgeGraph.model_validate_json((state / "domain-graph.json").read_text(encoding="utf-8"))
    if knowledge.project.git_commit_hash != revision or domain.project.git_commit_hash != revision:
        raise ValueError("UA graphs do not match the frozen Git revision")
    return knowledge, domain


def _safe_extract_tar(
    archive: Path, target: Path, *, expected_git_revision: str | None = None,
) -> None:
    if not archive.is_file():
        raise ValueError("refresh artifact is unavailable")
    target.mkdir(parents=True, exist_ok=True)
    total = 0
    seen: set[str] = set()
    with tarfile.open(archive, mode="r:gz") as bundle:
        if expected_git_revision is not None and bundle.pax_headers.get("comment") != expected_git_revision:
            raise ValueError("source archive Git coordinate does not match the frozen revision")
        for entry_count, member in enumerate(bundle, start=1):
            if entry_count > MAX_ARCHIVE_ENTRIES:
                raise ValueError("refresh archive has too many entries")
            name = _safe_relative_path(member.name.rstrip("/"))
            if name in seen:
                raise ValueError(f"refresh archive contains duplicate path {name!r}")
            seen.add(name)
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError("refresh archive links and device entries are forbidden")
            destination = target / name
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError("refresh archive contains an unsupported entry type")
            total += member.size
            if total > MAX_EXPANDED_BYTES:
                raise ValueError("refresh archive expands beyond the configured limit")
            source = bundle.extractfile(member)
            if source is None:
                raise ValueError("refresh archive member cannot be read")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)


def _hash_source_file(path: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    size = 0
    newline_count = 0
    last_byte = b""
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            newline_count += chunk.count(b"\n")
            last_byte = chunk[-1:]
    line_count = newline_count + (1 if size and last_byte != b"\n" else 0)
    return digest.hexdigest(), size, line_count


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe archive path {value!r}")
    return path.as_posix()


def _language(path: str) -> str:
    return {
        ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
        ".jsx": "JavaScript", ".json": "JSON", ".md": "Markdown", ".go": "Go",
        ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby", ".php": "PHP",
    }.get(Path(path).suffix.lower(), Path(path).suffix.removeprefix(".").upper() or "Other")


def _kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".php"}:
        return "source"
    return "documentation" if suffix in {".md", ".rst"} else "resource"


def _component(path: str) -> str:
    parts = PurePosixPath(path).parts
    return "/".join(parts[:2]) if parts and parts[0] in {"src", "app", "packages"} and len(parts) > 1 else parts[0]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _public_url(path: str) -> str:
    origin = os.environ.get("COINTENT_PUBLIC_ORIGIN", "http://127.0.0.1:8811").rstrip("/")
    return f"{origin}{path}"
