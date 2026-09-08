"""SQLite persistence for immutable model versions and observed snapshots."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .models import ModelPatch, ProjectModel, apply_model_patch, semantic_diff
from .scanner import RepositorySnapshot, snapshot_diff


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class CoIntentRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connection() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    repository TEXT NOT NULL DEFAULT '',
                    current_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_versions (
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    version INTEGER NOT NULL,
                    parent_version INTEGER,
                    model_json TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, version)
                );
                CREATE TABLE IF NOT EXISTS intent_sources (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    speaker TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    base_version INTEGER NOT NULL,
                    patch_json TEXT NOT NULL,
                    proposed_model_json TEXT NOT NULL,
                    diff_json TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolution TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    snapshot_json TEXT NOT NULL,
                    diff_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alignment_findings (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
                    kind TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    role_ids_json TEXT NOT NULL,
                    artifact_paths_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolution TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_versions_project ON model_versions(project_id, version DESC);
                CREATE INDEX IF NOT EXISTS idx_snapshots_project ON snapshots(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_findings_project ON alignment_findings(project_id, status, created_at DESC);
            """)

    def create_project(self, project_id: str, name: str, repository: str = "") -> dict[str, Any]:
        initial = ProjectModel(project_id=project_id, name=name)
        created = _now()
        with self.connection() as db:
            db.execute(
                "INSERT INTO projects(id,name,repository,current_version,created_at) VALUES(?,?,?,?,?)",
                (project_id, name, repository, 1, created),
            )
            db.execute(
                "INSERT INTO model_versions VALUES(?,?,?,?,?,?,?)",
                (project_id, 1, None, initial.model_dump_json(), "system", "Project created", created),
            )
        return self.get_model(project_id)

    def ensure_project(self, project_id: str, name: str, repository: str = "") -> dict[str, Any]:
        try:
            return self.get_model(project_id)
        except KeyError:
            return self.create_project(project_id, name, repository)

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT id,name,repository,current_version,created_at FROM projects ORDER BY name"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_model(self, project_id: str, version: int | None = None) -> dict[str, Any]:
        with self.connection() as db:
            project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if project is None:
                raise KeyError(f"unknown project {project_id!r}")
            selected = version if version is not None else int(project["current_version"])
            row = db.execute(
                "SELECT * FROM model_versions WHERE project_id=? AND version=?",
                (project_id, selected),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown model version {project_id!r}@{selected}")
        return {
            "project": dict(project),
            "version": selected,
            "parent_version": row["parent_version"],
            "actor": row["actor"],
            "message": row["message"],
            "created_at": row["created_at"],
            "model": json.loads(row["model_json"]),
        }

    def replace_model(self, project_id: str, model: ProjectModel, *, actor: str, message: str) -> dict[str, Any]:
        current = self.get_model(project_id)
        if model.project_id != project_id:
            raise ValueError("model project_id does not match target project")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            actual = db.execute("SELECT current_version FROM projects WHERE id=?", (project_id,)).fetchone()
            if actual is None or int(actual[0]) != current["version"]:
                raise RuntimeError("model changed while replacement was being prepared")
            version = current["version"] + 1
            db.execute(
                "INSERT INTO model_versions VALUES(?,?,?,?,?,?,?)",
                (project_id, version, current["version"], model.model_dump_json(), actor, message, _now()),
            )
            db.execute("UPDATE projects SET current_version=? WHERE id=?", (version, project_id))
        return self.get_model(project_id)

    def record_intent(self, project_id: str, speaker: str, content: str, source_ref: str = "") -> dict[str, Any]:
        self.get_model(project_id)
        record = {
            "id": _id("intent"), "project_id": project_id, "speaker": speaker,
            "content": content, "source_ref": source_ref, "created_at": _now(),
        }
        with self.connection() as db:
            db.execute(
                "INSERT INTO intent_sources(id,project_id,speaker,content,source_ref,created_at) VALUES(:id,:project_id,:speaker,:content,:source_ref,:created_at)",
                record,
            )
        return record

    def list_intent_sources(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM intent_sources WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, max(1, min(limit, 500))),
            ).fetchall()
        return [dict(row) for row in rows]

    def propose_patch(
        self, project_id: str, base_version: int, patch_data: dict[str, Any],
        *, rationale: str, evidence_ids: list[str], actor: str,
    ) -> dict[str, Any]:
        current = self.get_model(project_id)
        if current["version"] != base_version:
            raise ValueError(f"stale base version {base_version}; current version is {current['version']}")
        before = ProjectModel.model_validate(current["model"])
        patch = ModelPatch.model_validate(patch_data)
        after = apply_model_patch(before, patch)
        proposal = {
            "id": _id("proposal"), "project_id": project_id, "base_version": base_version,
            "patch_json": patch.model_dump_json(), "proposed_model_json": after.model_dump_json(),
            "diff_json": json.dumps(semantic_diff(before, after), separators=(",", ":")),
            "rationale": rationale, "evidence_json": json.dumps(evidence_ids), "actor": actor,
            "status": "pending", "created_at": _now(),
        }
        with self.connection() as db:
            db.execute("""
                INSERT INTO proposals(id,project_id,base_version,patch_json,proposed_model_json,diff_json,
                    rationale,evidence_json,actor,status,created_at)
                VALUES(:id,:project_id,:base_version,:patch_json,:proposed_model_json,:diff_json,
                    :rationale,:evidence_json,:actor,:status,:created_at)
            """, proposal)
        return self.get_proposal(proposal["id"])

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown proposal {proposal_id!r}")
        return _proposal(row)

    def list_proposals(self, project_id: str, status: str = "pending") -> list[dict[str, Any]]:
        with self.connection() as db:
            if status == "all":
                rows = db.execute(
                    "SELECT * FROM proposals WHERE project_id=? ORDER BY created_at DESC", (project_id,)
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM proposals WHERE project_id=? AND status=? ORDER BY created_at DESC",
                    (project_id, status),
                ).fetchall()
        return [_proposal(row) for row in rows]

    def resolve_proposal(self, proposal_id: str, *, accept: bool, actor: str, resolution: str = "") -> dict[str, Any]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            proposal = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if proposal is None:
                raise KeyError(f"unknown proposal {proposal_id!r}")
            if proposal["status"] != "pending":
                raise ValueError(f"proposal is already {proposal['status']}")
            status = "accepted" if accept else "rejected"
            if accept:
                project = db.execute(
                    "SELECT current_version FROM projects WHERE id=?", (proposal["project_id"],)
                ).fetchone()
                if project is None or int(project[0]) != int(proposal["base_version"]):
                    raise ValueError("proposal is stale and must be rebased before acceptance")
                next_version = int(proposal["base_version"]) + 1
                db.execute(
                    "INSERT INTO model_versions VALUES(?,?,?,?,?,?,?)",
                    (proposal["project_id"], next_version, proposal["base_version"],
                     proposal["proposed_model_json"], actor, proposal["rationale"], _now()),
                )
                db.execute(
                    "UPDATE projects SET current_version=? WHERE id=?",
                    (next_version, proposal["project_id"]),
                )
            db.execute(
                "UPDATE proposals SET status=?,resolution=?,resolved_at=? WHERE id=?",
                (status, resolution, _now(), proposal_id),
            )
        return self.get_proposal(proposal_id)

    def ingest_snapshot(self, project_id: str, data: dict[str, Any]) -> dict[str, Any]:
        snapshot = RepositorySnapshot.model_validate(data)
        if snapshot.project_id != project_id:
            raise ValueError("snapshot project_id does not match target project")
        self.get_model(project_id)
        with self.connection() as db:
            existing = db.execute("SELECT * FROM snapshots WHERE id=?", (snapshot.id,)).fetchone()
            if existing is not None:
                return {**self.get_snapshot(snapshot.id), "findings_created": [], "duplicate": True}
            previous_row = db.execute(
                "SELECT snapshot_json FROM snapshots WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            previous = RepositorySnapshot.model_validate_json(previous_row[0]) if previous_row else None
            delta = snapshot_diff(previous, snapshot)
            db.execute(
                "INSERT INTO snapshots(id,project_id,snapshot_json,diff_json,created_at) VALUES(?,?,?,?,?)",
                (snapshot.id, project_id, snapshot.model_dump_json(), json.dumps(delta), _now()),
            )
        findings = self._derive_findings(project_id, snapshot, delta, initial=previous is None)
        return {**self.get_snapshot(snapshot.id), "findings_created": findings, "duplicate": False}

    def _derive_findings(
        self, project_id: str, snapshot: RepositorySnapshot, delta: dict[str, Any], *, initial: bool,
    ) -> list[dict[str, Any]]:
        if initial:
            return []
        model = ProjectModel.model_validate(self.get_model(project_id)["model"])
        changed = [(path, "modified") for path in delta["modified"]]
        changed += [(path, "added") for path in delta["added"]]
        changed += [(path, "removed") for path in delta["removed"]]
        created: list[dict[str, Any]] = []
        for path, change in changed:
            roles = sorted({link.role_id for link in model.trace_links if _path_matches(link.artifact_path, path)})
            if not roles and change == "added" and not _architectural_source(path):
                continue
            if change == "removed" and roles:
                kind, severity = "Absent", "high"
                summary = f"Mapped implementation artifact was removed: {path}"
            elif roles:
                kind, severity = "BoundaryChange", "medium"
                summary = f"Implementation changed inside mapped role boundary: {path}"
            else:
                kind, severity = "Unmapped", "low"
                summary = f"New implementation artifact has no role mapping: {path}"
            created.append(self._insert_finding(
                project_id, snapshot.id, kind, severity, summary, roles, [path],
                {"change": change, "snapshot": snapshot.id},
            ))
        for relation in delta["relations_added"]:
            source_roles = {link.role_id for link in model.trace_links if _path_matches(link.artifact_path, relation["source"])}
            target_roles = {link.role_id for link in model.trace_links if _path_matches(link.artifact_path, relation["target"])}
            pairs = {(a, b) for a in source_roles for b in target_roles if a != b}
            declared = {(item.source_role_id, item.target_role_id) for item in model.relations}
            undeclared = sorted(pairs - declared)
            if undeclared:
                created.append(self._insert_finding(
                    project_id, snapshot.id, "Divergent", "medium",
                    "A new code dependency crosses role boundaries without a declared relationship.",
                    sorted({role for pair in undeclared for role in pair}),
                    [relation["source"], relation["target"]], relation,
                ))
        return created

    def _insert_finding(
        self, project_id: str, snapshot_id: str, kind: str, severity: str, summary: str,
        role_ids: list[str], paths: list[str], evidence: dict[str, Any],
    ) -> dict[str, Any]:
        item = {
            "id": _id("finding"), "project_id": project_id, "snapshot_id": snapshot_id,
            "kind": kind, "severity": severity, "summary": summary,
            "role_ids_json": json.dumps(role_ids), "artifact_paths_json": json.dumps(paths),
            "evidence_json": json.dumps(evidence), "status": "open", "created_at": _now(),
        }
        with self.connection() as db:
            db.execute("""
                INSERT INTO alignment_findings(id,project_id,snapshot_id,kind,severity,summary,
                    role_ids_json,artifact_paths_json,evidence_json,status,created_at)
                VALUES(:id,:project_id,:snapshot_id,:kind,:severity,:summary,
                    :role_ids_json,:artifact_paths_json,:evidence_json,:status,:created_at)
            """, item)
        return self.get_finding(item["id"])

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown snapshot {snapshot_id!r}")
        return {"id": row["id"], "project_id": row["project_id"], "created_at": row["created_at"],
                "snapshot": json.loads(row["snapshot_json"]), "diff": json.loads(row["diff_json"])}

    def list_snapshots(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT id,snapshot_json,diff_json,created_at FROM snapshots WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, max(1, min(limit, 100))),
            ).fetchall()
        return [{"id": row["id"], "created_at": row["created_at"],
                 "snapshot": json.loads(row["snapshot_json"]), "diff": json.loads(row["diff_json"])} for row in rows]

    def get_finding(self, finding_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM alignment_findings WHERE id=?", (finding_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown finding {finding_id!r}")
        return _finding(row)

    def list_findings(self, project_id: str, status: str = "open") -> list[dict[str, Any]]:
        with self.connection() as db:
            if status == "all":
                rows = db.execute(
                    "SELECT * FROM alignment_findings WHERE project_id=? ORDER BY created_at DESC", (project_id,)
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM alignment_findings WHERE project_id=? AND status=? ORDER BY created_at DESC",
                    (project_id, status),
                ).fetchall()
        return [_finding(row) for row in rows]

    def resolve_finding(self, finding_id: str, status: str, resolution: str) -> dict[str, Any]:
        if status not in {"resolved", "accepted_exception", "dismissed"}:
            raise ValueError("status must be resolved, accepted_exception, or dismissed")
        with self.connection() as db:
            changed = db.execute(
                "UPDATE alignment_findings SET status=?,resolution=?,resolved_at=? WHERE id=?",
                (status, resolution, _now(), finding_id),
            ).rowcount
        if not changed:
            raise KeyError(f"unknown finding {finding_id!r}")
        return self.get_finding(finding_id)

    def compare_versions(self, project_id: str, from_version: int, to_version: int) -> dict[str, Any]:
        before = ProjectModel.model_validate(self.get_model(project_id, from_version)["model"])
        after = ProjectModel.model_validate(self.get_model(project_id, to_version)["model"])
        return {"project_id": project_id, "from_version": from_version, "to_version": to_version,
                "diff": semantic_diff(before, after)}

    def overview(self, project_id: str) -> dict[str, Any]:
        current = self.get_model(project_id)
        model = current["model"]
        with self.connection() as db:
            snapshot = db.execute(
                "SELECT snapshot_json,created_at FROM snapshots WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            open_findings = db.execute(
                "SELECT COUNT(*) FROM alignment_findings WHERE project_id=? AND status='open'", (project_id,)
            ).fetchone()[0]
            proposals = db.execute(
                "SELECT COUNT(*) FROM proposals WHERE project_id=? AND status='pending'", (project_id,)
            ).fetchone()[0]
        snapshot_summary = None
        if snapshot:
            observed = json.loads(snapshot["snapshot_json"])
            snapshot_summary = {
                key: observed[key]
                for key in ("id", "repository", "revision", "branch", "dirty", "captured_at")
            }
            snapshot_summary["artifact_count"] = len(observed["artifacts"])
            snapshot_summary["relation_count"] = len(observed["relations"])
        return {
            "project": current["project"], "version": current["version"], "status": model["status"],
            "counts": {"goals": len(model["goals"]), "roles": len(model["roles"]),
                       "responsibilities": len(model["responsibilities"]),
                       "trace_links": len(model["trace_links"]), "open_findings": open_findings,
                       "pending_proposals": proposals},
            "latest_snapshot": snapshot_summary,
            "snapshot_recorded_at": snapshot["created_at"] if snapshot else None,
        }


def _proposal(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for source, target in (("patch_json", "patch"), ("proposed_model_json", "proposed_model"),
                           ("diff_json", "diff"), ("evidence_json", "evidence_ids")):
        item[target] = json.loads(item.pop(source))
    return item


def _finding(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for source, target in (("role_ids_json", "role_ids"), ("artifact_paths_json", "artifact_paths"),
                           ("evidence_json", "evidence")):
        item[target] = json.loads(item.pop(source))
    return item


def _path_matches(mapping: str, path: str) -> bool:
    prefix = mapping.rstrip("/")
    return path == prefix or path.startswith(f"{prefix}/")


def _architectural_source(path: str) -> bool:
    return Path(path).suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"}
