"""SQLite persistence for immutable models, backend snapshots, and alignment review."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .design import (
    DesignOperation,
    DesignOperationRecord,
    DesignRevision,
    DesignWorkspace,
    apply_design_operations,
    seed_design_from_observation,
)
from .delivery import (
    DesignApproval,
    DesignReview,
    ImplementationChangeBundle,
    VerificationDecision,
    VerificationReport,
    build_approval,
    build_design_review,
    build_implementation_bundle,
    build_verification_decision,
    build_verification_report,
)
from .models import ImplementationLink, ModelPatch, ProjectModel, apply_model_patch, semantic_diff
from .observation import (
    ObservationExpansionRequest,
    ObservedModelRevision,
    UAKnowledgeGraph,
    UnderstandAnythingSnapshot,
    build_ua_snapshot,
    build_expansion_request,
    project_observed_expansion,
    project_observed_model,
)
from .scanner import RepositorySnapshot, is_backend_logic_candidate, snapshot_diff


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class CoIntentRepository:
    def __init__(self, database: str | Path, asset_root: str | Path | None = None) -> None:
        self.database = str(database)
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self.asset_root = Path(asset_root) if asset_root is not None else Path(self.database).parent / "projects"
        self.asset_root.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._backfill_assets()

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
        """Keep the 0.2 physical columns so existing public data upgrades without a risky rewrite."""
        with self.connection() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, repository TEXT NOT NULL DEFAULT '',
                    current_version INTEGER NOT NULL, created_at TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '', default_branch TEXT NOT NULL DEFAULT 'master',
                    language TEXT NOT NULL DEFAULT 'en', status TEXT NOT NULL DEFAULT 'active'
                );
                CREATE TABLE IF NOT EXISTS model_versions (
                    project_id TEXT NOT NULL REFERENCES projects(id), version INTEGER NOT NULL,
                    parent_version INTEGER, model_json TEXT NOT NULL, actor TEXT NOT NULL,
                    message TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (project_id, version)
                );
                CREATE TABLE IF NOT EXISTS intent_sources (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), speaker TEXT NOT NULL,
                    content TEXT NOT NULL, source_ref TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), base_version INTEGER NOT NULL,
                    patch_json TEXT NOT NULL, proposed_model_json TEXT NOT NULL, diff_json TEXT NOT NULL,
                    rationale TEXT NOT NULL, evidence_json TEXT NOT NULL, actor TEXT NOT NULL, status TEXT NOT NULL,
                    resolution TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, resolved_at TEXT
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), snapshot_json TEXT NOT NULL,
                    diff_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS understand_anything_snapshots (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    code_snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
                    snapshot_json TEXT NOT NULL, content_digest TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(project_id, code_snapshot_id, content_digest)
                );
                CREATE TABLE IF NOT EXISTS observed_model_revisions (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    code_snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
                    ua_snapshot_id TEXT NOT NULL REFERENCES understand_anything_snapshots(id),
                    parent_revision_id TEXT REFERENCES observed_model_revisions(id),
                    refinement_of_node_id TEXT, revision_json TEXT NOT NULL,
                    content_digest TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(project_id, ua_snapshot_id, content_digest)
                );
                CREATE TABLE IF NOT EXISTS observation_expansion_requests (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    base_observed_revision_id TEXT NOT NULL REFERENCES observed_model_revisions(id),
                    ua_snapshot_id TEXT NOT NULL REFERENCES understand_anything_snapshots(id),
                    target_observed_node_id TEXT NOT NULL, depth INTEGER NOT NULL,
                    status TEXT NOT NULL, result_observed_revision_id TEXT REFERENCES observed_model_revisions(id),
                    request_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS design_workspaces_v04 (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    base_observed_revision_id TEXT NOT NULL REFERENCES observed_model_revisions(id),
                    current_design_revision_id TEXT NOT NULL,
                    workspace_json TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS design_revisions_v04 (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES design_workspaces_v04(id),
                    parent_revision_id TEXT REFERENCES design_revisions_v04(id),
                    revision_json TEXT NOT NULL, content_digest TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(workspace_id, content_digest)
                );
                CREATE TABLE IF NOT EXISTS design_operations_v04 (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES design_workspaces_v04(id),
                    base_design_revision_id TEXT NOT NULL REFERENCES design_revisions_v04(id),
                    result_design_revision_id TEXT NOT NULL REFERENCES design_revisions_v04(id),
                    operation_index INTEGER NOT NULL, operation_json TEXT NOT NULL,
                    actor TEXT NOT NULL, rationale TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS design_reviews_v04 (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES design_workspaces_v04(id),
                    design_revision_id TEXT NOT NULL REFERENCES design_revisions_v04(id),
                    review_json TEXT NOT NULL, status TEXT NOT NULL, content_digest TEXT NOT NULL,
                    submitted_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS design_approvals_v04 (
                    id TEXT PRIMARY KEY, review_id TEXT NOT NULL UNIQUE REFERENCES design_reviews_v04(id),
                    workspace_id TEXT NOT NULL REFERENCES design_workspaces_v04(id),
                    approval_json TEXT NOT NULL, content_digest TEXT NOT NULL, approved_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS implementation_exports_v04 (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES design_workspaces_v04(id),
                    design_revision_id TEXT NOT NULL REFERENCES design_revisions_v04(id),
                    bundle_json TEXT NOT NULL, content_digest TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(workspace_id, design_revision_id, content_digest)
                );
                CREATE TABLE IF NOT EXISTS verification_reports_v04 (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES design_workspaces_v04(id),
                    implementation_bundle_id TEXT NOT NULL REFERENCES implementation_exports_v04(id),
                    observed_revision_id TEXT NOT NULL REFERENCES observed_model_revisions(id),
                    report_json TEXT NOT NULL, content_digest TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(workspace_id, implementation_bundle_id, observed_revision_id)
                );
                CREATE TABLE IF NOT EXISTS verification_decisions_v04 (
                    id TEXT PRIMARY KEY, report_id TEXT NOT NULL UNIQUE REFERENCES verification_reports_v04(id),
                    workspace_id TEXT NOT NULL REFERENCES design_workspaces_v04(id),
                    decision_json TEXT NOT NULL, content_digest TEXT NOT NULL, decided_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alignment_findings (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(id), kind TEXT NOT NULL, severity TEXT NOT NULL,
                    summary TEXT NOT NULL, role_ids_json TEXT NOT NULL, artifact_paths_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL, status TEXT NOT NULL, resolution TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, resolved_at TEXT
                );
                CREATE TABLE IF NOT EXISTS mapping_revisions (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), design_version INTEGER NOT NULL,
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(id), trace_links_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS change_sets (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), title TEXT NOT NULL,
                    description TEXT NOT NULL, base_design_version INTEGER NOT NULL, target_design_version INTEGER,
                    proposal_id TEXT, snapshot_id TEXT, function_ids_json TEXT NOT NULL, role_ids_json TEXT NOT NULL,
                    status TEXT NOT NULL, resolution TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_versions_project ON model_versions(project_id, version DESC);
                CREATE INDEX IF NOT EXISTS idx_snapshots_project ON snapshots(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_ua_snapshots_project
                    ON understand_anything_snapshots(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_observed_revisions_project
                    ON observed_model_revisions(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_observation_expansions_project
                    ON observation_expansion_requests(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_design_workspaces_v04_project
                    ON design_workspaces_v04(project_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_design_revisions_v04_workspace
                    ON design_revisions_v04(workspace_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_design_operations_v04_workspace
                    ON design_operations_v04(workspace_id, created_at DESC, operation_index);
                CREATE INDEX IF NOT EXISTS idx_design_reviews_v04_workspace
                    ON design_reviews_v04(workspace_id, submitted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_implementation_exports_v04_workspace
                    ON implementation_exports_v04(workspace_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_verification_reports_v04_workspace
                    ON verification_reports_v04(workspace_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_findings_project ON alignment_findings(project_id, status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_mappings_project ON mapping_revisions(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_changes_project ON change_sets(project_id, status, updated_at DESC);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(projects)").fetchall()}
            for name, declaration in (
                ("description", "TEXT NOT NULL DEFAULT ''"),
                ("default_branch", "TEXT NOT NULL DEFAULT 'master'"),
                ("language", "TEXT NOT NULL DEFAULT 'en'"),
                ("status", "TEXT NOT NULL DEFAULT 'active'"),
            ):
                if name not in columns:
                    db.execute(f"ALTER TABLE projects ADD COLUMN {name} {declaration}")

    # Projects and immutable model versions

    def create_project(
        self, project_id: str, name: str, repository: str = "", description: str = "",
        default_branch: str = "master", language: str = "en",
    ) -> dict[str, Any]:
        self._project_dir(project_id)
        model = ProjectModel(project_id=project_id, name=name)
        created = _now()
        with self.connection() as db:
            db.execute(
                """INSERT INTO projects(id,name,repository,current_version,created_at,description,
                   default_branch,language,status) VALUES(?,?,?,?,?,?,?,?,?)""",
                (project_id, name, repository, 1, created, description, default_branch, language, "active"),
            )
            db.execute(
                "INSERT INTO model_versions VALUES(?,?,?,?,?,?,?)",
                (project_id, 1, None, model.model_dump_json(), "system", "Project created", created),
            )
        self._write_project_asset(self.get_project(project_id))
        self._write_design_asset(project_id, 1, model)
        return self.get_model(project_id)

    def ensure_project(self, project_id: str, name: str, repository: str = "") -> dict[str, Any]:
        try:
            return self.get_model(project_id)
        except KeyError:
            return self.create_project(project_id, name, repository)

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """SELECT id,name,repository,current_version,created_at,description,default_branch,
                   language,status FROM projects ORDER BY name"""
            ).fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown project {project_id!r}")
        return dict(row)

    def update_project(
        self, project_id: str, *, name: str | None = None, description: str | None = None,
        repository: str | None = None, default_branch: str | None = None,
        language: str | None = None, status: str | None = None,
    ) -> dict[str, Any]:
        if status is not None and status not in {"active", "archived"}:
            raise ValueError("status must be active or archived")
        updates = {key: value for key, value in {
            "name": name, "description": description, "repository": repository,
            "default_branch": default_branch, "language": language, "status": status,
        }.items() if value is not None}
        if updates:
            assignments = ",".join(f"{key}=?" for key in updates)
            with self.connection() as db:
                changed = db.execute(
                    f"UPDATE projects SET {assignments} WHERE id=?", (*updates.values(), project_id)
                ).rowcount
            if not changed:
                raise KeyError(f"unknown project {project_id!r}")
        project = self.get_project(project_id)
        self._write_project_asset(project)
        return project

    def get_model(self, project_id: str, version: int | None = None) -> dict[str, Any]:
        with self.connection() as db:
            project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if project is None:
                raise KeyError(f"unknown project {project_id!r}")
            selected = version if version is not None else int(project["current_version"])
            row = db.execute(
                "SELECT * FROM model_versions WHERE project_id=? AND version=?", (project_id, selected)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown model version {project_id!r}@{selected}")
        return {
            "project": dict(project), "version": selected, "parent_version": row["parent_version"],
            "actor": row["actor"], "message": row["message"], "created_at": row["created_at"],
            "model": ProjectModel.model_validate_json(row["model_json"]).model_dump(),
        }

    def stored_schema_version(self, project_id: str, version: int | None = None) -> str:
        """Return the on-disk schema marker before read migration is applied."""
        with self.connection() as db:
            project = db.execute("SELECT current_version FROM projects WHERE id=?", (project_id,)).fetchone()
            if project is None:
                raise KeyError(f"unknown project {project_id!r}")
            selected = version if version is not None else int(project[0])
            row = db.execute(
                "SELECT model_json FROM model_versions WHERE project_id=? AND version=?",
                (project_id, selected),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown model version {project_id!r}@{selected}")
        return str(json.loads(row[0]).get("schema_version", "0.1"))

    def list_versions(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with self.connection() as db:
            rows = db.execute(
                """SELECT version,parent_version,actor,message,created_at FROM model_versions
                   WHERE project_id=? ORDER BY version DESC""", (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

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
        self._write_design_asset(project_id, version, model)
        return self.get_model(project_id)

    # Original intent and proposal lifecycle

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
        self, project_id: str, base_version: int, patch_data: dict[str, Any], *,
        rationale: str, evidence_ids: list[str], actor: str,
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
        accepted_asset: tuple[str, int, ProjectModel] | None = None
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
                model = ProjectModel.model_validate_json(proposal["proposed_model_json"])
                next_version = int(proposal["base_version"]) + 1
                db.execute(
                    "INSERT INTO model_versions VALUES(?,?,?,?,?,?,?)",
                    (proposal["project_id"], next_version, proposal["base_version"], model.model_dump_json(),
                     actor, proposal["rationale"], _now()),
                )
                db.execute(
                    "UPDATE projects SET current_version=? WHERE id=?", (next_version, proposal["project_id"])
                )
                accepted_asset = proposal["project_id"], next_version, model
            db.execute(
                "UPDATE proposals SET status=?,resolution=?,resolved_at=? WHERE id=?",
                (status, resolution, _now(), proposal_id),
            )
        if accepted_asset is not None:
            self._write_design_asset(*accepted_asset)
        return self.get_proposal(proposal_id)

    # Responsibility model queries

    def inspect_specification_tree(
        self, project_id: str, version: int | None = None,
        root_id: str | None = None, depth: int = 20,
    ) -> dict[str, Any]:
        response = self.get_model(project_id, version)
        model = ProjectModel.model_validate(response["model"])
        selected = _select_hierarchy(model.specification_items, root_id, depth)
        ids = {item.id for item in selected}
        return {
            "project_id": project_id, "version": response["version"],
            "specification_items": [item.model_dump() for item in selected],
            "links": [item.model_dump() for item in model.specification_responsibility_links
                      if item.specification_id in ids],
        }

    def inspect_specification_item(
        self, project_id: str, specification_id: str, version: int | None = None,
    ) -> dict[str, Any]:
        response = self.get_model(project_id, version)
        model = ProjectModel.model_validate(response["model"])
        item = next((value for value in model.specification_items if value.id == specification_id), None)
        if item is None:
            raise KeyError(f"unknown specification item {specification_id!r}")
        links = [value for value in model.specification_responsibility_links
                 if value.specification_id == specification_id]
        by_id = {value.id: value for value in model.responsibilities}
        return {
            "project_id": project_id, "version": response["version"],
            "specification_item": item.model_dump(),
            "responsibilities": [
                {"link": link.model_dump(), "responsibility": by_id[link.responsibility_id].model_dump()}
                for link in links
            ],
        }

    def inspect_responsibility(
        self, project_id: str, responsibility_id: str, version: int | None = None,
    ) -> dict[str, Any]:
        response = self.get_model(project_id, version)
        model = ProjectModel.model_validate(response["model"])
        by_id = {item.id: item for item in model.responsibilities}
        item = by_id.get(responsibility_id)
        if item is None:
            raise KeyError(f"unknown responsibility {responsibility_id!r}")
        child_ids = [] if item.workflow is None else [node.responsibility_id for node in item.workflow.nodes]
        parent_occurrences = [
            {"parent_id": parent.id, "parent_name": parent.name, "node_id": node.id}
            for parent in model.responsibilities if parent.workflow is not None
            for node in parent.workflow.nodes if node.responsibility_id == responsibility_id
        ]
        spec_links = [link for link in model.specification_responsibility_links
                      if link.responsibility_id == responsibility_id]
        spec_by_id = {value.id: value for value in model.specification_items}
        return {
            "project_id": project_id, "version": response["version"],
            "responsibility": item.model_dump(),
            "child_responsibilities": [by_id[value].model_dump() for value in dict.fromkeys(child_ids)],
            "parent_occurrences": parent_occurrences,
            "specification_items": [
                {"link": link.model_dump(), "specification_item": spec_by_id[link.specification_id].model_dump()}
                for link in spec_links
            ],
            "implementation_links": [item.model_dump() for item in model.implementation_links
                                     if item.responsibility_id == responsibility_id],
        }

    def list_root_responsibilities(self, project_id: str, version: int | None = None) -> dict[str, Any]:
        response = self.get_model(project_id, version)
        model = ProjectModel.model_validate(response["model"])
        referenced = {
            node.responsibility_id for parent in model.responsibilities if parent.workflow is not None
            for node in parent.workflow.nodes
        }
        roots = [item.model_dump() for item in model.responsibilities if item.id not in referenced]
        return {"project_id": project_id, "version": response["version"], "responsibilities": roots}

    def trace_workflow(
        self, project_id: str, responsibility_id: str, version: int | None = None,
        max_steps: int = 32, max_paths: int = 64,
    ) -> dict[str, Any]:
        inspected = self.inspect_responsibility(project_id, responsibility_id, version)
        responsibility = inspected["responsibility"]
        workflow = responsibility.get("workflow")
        if not workflow or not workflow["nodes"]:
            return {"project_id": project_id, "version": inspected["version"],
                    "responsibility_id": responsibility_id, "paths": [], "leaf": True}
        nodes = {item["id"]: item for item in workflow["nodes"]}
        outgoing: dict[str, list[dict[str, Any]]] = {}
        for edge in workflow["edges"]:
            outgoing.setdefault(edge["source_node_id"], []).append(edge)
        paths: list[dict[str, Any]] = []

        def walk(node_id: str, visits: list[str], traversed: list[dict[str, Any]]) -> None:
            if len(paths) >= max(1, min(max_paths, 256)):
                return
            repeated = node_id in visits
            next_visits = [*visits, node_id]
            if repeated or len(next_visits) >= max(1, min(max_steps, 256)) or not outgoing.get(node_id):
                paths.append({
                    "node_ids": next_visits,
                    "responsibility_ids": [nodes[value]["responsibility_id"] for value in next_visits],
                    "edges": traversed,
                    "loop": repeated,
                    "truncated": len(next_visits) >= max_steps,
                })
                return
            for edge in outgoing[node_id]:
                walk(edge["target_node_id"], next_visits, [*traversed, edge])

        for entry in workflow["entry_node_ids"]:
            walk(entry, [], [])
        return {"project_id": project_id, "version": inspected["version"],
                "responsibility_id": responsibility_id, "paths": paths, "leaf": False}

    def specification_coverage(self, project_id: str, version: int | None = None) -> dict[str, Any]:
        response = self.get_model(project_id, version)
        model = ProjectModel.model_validate(response["model"])
        parent_ids = {item.parent_id for item in model.specification_items if item.parent_id}
        leaves = {item.id for item in model.specification_items if item.id not in parent_ids}
        covered = {item.specification_id for item in model.specification_responsibility_links}
        return {
            "project_id": project_id, "version": response["version"],
            "leaf_specifications": len(leaves), "covered_leaf_specifications": len(leaves & covered),
            "uncovered_specification_ids": sorted(leaves - covered),
        }

    def responsibility_quality(self, project_id: str, version: int | None = None) -> dict[str, Any]:
        response = self.get_model(project_id, version)
        model = ProjectModel.model_validate(response["model"])
        mapped = {item.responsibility_id for item in model.implementation_links}
        signals: list[dict[str, str]] = []
        for item in model.responsibilities:
            if not item.description:
                signals.append({"kind": "missing_description", "element_id": item.id,
                                "message": "Responsibility has no plain-language description."})
            if item.workflow is None and item.id not in mapped:
                signals.append({"kind": "unmapped_leaf", "element_id": item.id,
                                "message": "Leaf Responsibility has no backend implementation evidence."})
            if item.workflow is not None:
                reachable = _reachable(item.workflow.entry_node_ids, item.workflow.edges)
                for node in item.workflow.nodes:
                    if node.id not in reachable:
                        signals.append({"kind": "unreachable_node", "element_id": item.id,
                                        "message": f"Workflow node {node.id} is unreachable from an entry."})
        return {"project_id": project_id, "design_version": response["version"],
                "verdict": "judgment_required", "signals": signals}

    # Backend snapshots and implementation alignment

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
            current = self.get_model(project_id)
            links = current["model"]["implementation_links"]
            db.execute(
                """INSERT INTO mapping_revisions(id,project_id,design_version,snapshot_id,trace_links_json,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (_id("mapping"), project_id, current["version"], snapshot.id,
                 json.dumps(links, separators=(",", ":"), sort_keys=True), _now()),
            )
        self._write_snapshot_asset(snapshot)
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
            responsibility_ids = sorted({
                link.responsibility_id for link in model.implementation_links
                if _path_matches(link.artifact_path, path)
            })
            if not is_backend_logic_candidate(path):
                continue
            if not responsibility_ids and change == "removed":
                continue
            if change == "removed" and responsibility_ids:
                kind, severity = "Absent", "high"
                summary = f"Mapped backend artifact was removed: {path}"
            elif responsibility_ids:
                kind, severity = "BoundaryChange", "medium"
                summary = f"Backend implementation changed inside a mapped Responsibility: {path}"
            else:
                kind, severity = "Unmapped", "low"
                summary = f"New backend program logic has no Responsibility mapping: {path}"
            created.append(self._insert_finding(
                project_id, snapshot.id, kind, severity, summary, responsibility_ids, [path],
                {"change": change, "snapshot": snapshot.id},
            ))
        return created

    def dismiss_non_backend_findings(self, project_id: str) -> int:
        """Dismiss legacy findings that fall outside the backend-only observation boundary."""
        with self.connection() as db:
            rows = db.execute(
                "SELECT id,artifact_paths_json FROM alignment_findings WHERE project_id=? AND status='open'",
                (project_id,),
            ).fetchall()
            identifiers = [
                row["id"] for row in rows
                if (paths := json.loads(row["artifact_paths_json"]))
                and all(not is_backend_logic_candidate(path) for path in paths)
            ]
            if identifiers:
                placeholders = ",".join("?" for _ in identifiers)
                db.execute(
                    f"""UPDATE alignment_findings SET status='dismissed',
                        resolution='Outside the CoIntent 0.3 backend-logic observation boundary',resolved_at=?
                        WHERE id IN ({placeholders})""",
                    (_now(), *identifiers),
                )
        return len(identifiers)

    def _insert_finding(
        self, project_id: str, snapshot_id: str, kind: str, severity: str, summary: str,
        responsibility_ids: list[str], paths: list[str], evidence: dict[str, Any],
    ) -> dict[str, Any]:
        item = {
            "id": _id("finding"), "project_id": project_id, "snapshot_id": snapshot_id,
            "kind": kind, "severity": severity, "summary": summary,
            "role_ids_json": json.dumps(responsibility_ids), "artifact_paths_json": json.dumps(paths),
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

    def compare_snapshots(self, project_id: str, from_snapshot_id: str, to_snapshot_id: str) -> dict[str, Any]:
        before = RepositorySnapshot.model_validate(self.get_snapshot(from_snapshot_id)["snapshot"])
        after = RepositorySnapshot.model_validate(self.get_snapshot(to_snapshot_id)["snapshot"])
        if before.project_id != project_id or after.project_id != project_id:
            raise ValueError("snapshot does not belong to project")
        return snapshot_diff(before, after)

    # Understand Anything imports and read-only current-system observation

    def import_understand_anything(
        self, project_id: str, code_snapshot_id: str, ua_tool_revision: str,
        knowledge_graph: dict[str, Any], domain_graph: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Operator-only import of completed UA artifacts and atomic observation publication."""
        self.get_project(project_id)
        stored_code = self.get_snapshot(code_snapshot_id)
        if stored_code["project_id"] != project_id:
            raise ValueError("code snapshot does not belong to project")
        code_snapshot = RepositorySnapshot.model_validate(stored_code["snapshot"])
        knowledge = UAKnowledgeGraph.model_validate(knowledge_graph)
        domain = None if domain_graph is None else UAKnowledgeGraph.model_validate(domain_graph)
        created = _now()
        ua_snapshot = build_ua_snapshot(
            project_id=project_id, code_snapshot=code_snapshot, ua_tool_revision=ua_tool_revision,
            knowledge_graph=knowledge, domain_graph=domain, created_at=created,
        )
        observed = project_observed_model(ua_snapshot, code_snapshot, created_at=created)
        with self.connection() as db:
            existing = db.execute(
                "SELECT id FROM understand_anything_snapshots WHERE id=?", (ua_snapshot.id,),
            ).fetchone()
            if existing is None:
                db.execute(
                    """INSERT INTO understand_anything_snapshots(
                       id,project_id,code_snapshot_id,snapshot_json,content_digest,created_at
                       ) VALUES(?,?,?,?,?,?)""",
                    (ua_snapshot.id, project_id, code_snapshot_id, ua_snapshot.model_dump_json(),
                     ua_snapshot.content_digest, created),
                )
            existing_observed = db.execute(
                "SELECT id FROM observed_model_revisions WHERE id=?", (observed.id,),
            ).fetchone()
            if existing_observed is None:
                db.execute(
                    """INSERT INTO observed_model_revisions(
                       id,project_id,code_snapshot_id,ua_snapshot_id,parent_revision_id,
                       refinement_of_node_id,revision_json,content_digest,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (observed.id, project_id, code_snapshot_id, ua_snapshot.id,
                     observed.parent_revision_id, observed.refinement_of_node_id,
                     observed.model_dump_json(), observed.content_digest, created),
                )
        if existing is None:
            self._write_ua_snapshot_asset(ua_snapshot)
        if existing_observed is None:
            self._write_observed_revision_asset(observed)
        return {
            "duplicate": existing is not None and existing_observed is not None,
            "ua_snapshot": self.get_understand_anything_snapshot(ua_snapshot.id),
            "observed_revision": self.get_observed_revision(observed.id),
        }

    def get_understand_anything_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM understand_anything_snapshots WHERE id=?", (snapshot_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown Understand Anything snapshot {snapshot_id!r}")
        return json.loads(row["snapshot_json"])

    def list_understand_anything_snapshots(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with self.connection() as db:
            rows = db.execute(
                """SELECT snapshot_json FROM understand_anything_snapshots
                   WHERE project_id=? ORDER BY created_at DESC LIMIT ?""",
                (project_id, max(1, min(limit, 100))),
            ).fetchall()
        return [json.loads(row["snapshot_json"]) for row in rows]

    def get_observed_revision(self, revision_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                "SELECT revision_json FROM observed_model_revisions WHERE id=?", (revision_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown observed revision {revision_id!r}")
        return json.loads(row["revision_json"])

    def list_observed_revisions(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with self.connection() as db:
            rows = db.execute(
                """SELECT revision_json FROM observed_model_revisions
                   WHERE project_id=? ORDER BY created_at DESC LIMIT ?""",
                (project_id, max(1, min(limit, 100))),
            ).fetchall()
        return [json.loads(row["revision_json"]) for row in rows]

    def observation_coordinate(
        self, project_id: str, observed_revision_id: str | None = None,
    ) -> dict[str, Any]:
        self.get_project(project_id)
        if observed_revision_id is None:
            with self.connection() as db:
                row = db.execute(
                    """SELECT revision_json FROM observed_model_revisions
                       WHERE project_id=? AND parent_revision_id IS NULL
                       ORDER BY created_at DESC LIMIT 1""",
                    (project_id,),
                ).fetchone()
            if row is None:
                return {"project_id": project_id, "status": "not_generated", "observed_revision": None}
            revision = json.loads(row["revision_json"])
        else:
            revision = self.get_observed_revision(observed_revision_id)
            if revision["project_id"] != project_id:
                raise ValueError("observed revision does not belong to project")
        ua_snapshot = self.get_understand_anything_snapshot(revision["ua_snapshot_id"])
        code_snapshot = self.get_snapshot(revision["code_snapshot_id"])["snapshot"]
        latest_full_id = next(
            (item["snapshot"]["id"] for item in self.list_snapshots(project_id, 100)
             if item["snapshot"].get("scope", "backend") == "full"),
            None,
        )
        return {
            "project_id": project_id,
            "status": "current" if revision["code_snapshot_id"] == latest_full_id else "stale",
            "code_snapshot": {
                "id": code_snapshot["id"], "revision": code_snapshot["revision"],
                "branch": code_snapshot["branch"], "dirty": code_snapshot["dirty"],
                "scope": code_snapshot.get("scope", "backend"),
            },
            "ua_snapshot": {
                "id": ua_snapshot["id"], "ua_graph_version": ua_snapshot["ua_graph_version"],
                "ua_tool_revision": ua_snapshot["ua_tool_revision"],
                "coverage": ua_snapshot["coverage"],
            },
            "observed_revision": revision,
        }

    def request_observation_expansion(
        self, project_id: str, observed_revision_id: str, node_id: str, depth: int = 1,
    ) -> dict[str, Any]:
        revision = ObservedModelRevision.model_validate(self.get_observed_revision(observed_revision_id))
        if revision.project_id != project_id:
            raise ValueError("observed revision does not belong to project")
        request = build_expansion_request(revision, node_id=node_id, depth=depth, created_at=_now())
        stored: dict[str, Any] | None = None
        with self.connection() as db:
            existing = db.execute(
                "SELECT request_json FROM observation_expansion_requests WHERE id=?", (request.id,),
            ).fetchone()
            if existing is not None:
                stored = json.loads(existing["request_json"])
            else:
                db.execute(
                    """INSERT INTO observation_expansion_requests(
                       id,project_id,base_observed_revision_id,ua_snapshot_id,target_observed_node_id,
                       depth,status,result_observed_revision_id,request_json,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (request.id, request.project_id, request.base_observed_revision_id,
                     request.ua_snapshot_id, request.target_observed_node_id, request.depth,
                     request.status, request.result_observed_revision_id, request.model_dump_json(),
                     request.created_at, request.updated_at),
                )
        if stored is not None:
            if stored["status"] == "queued":
                stored = self.process_observation_expansion(request.id)
            return {"duplicate": True, "request": stored}
        return {"duplicate": False, "request": self.process_observation_expansion(request.id)}

    def process_observation_expansion(self, request_id: str) -> dict[str, Any]:
        """Run the trusted projector for one queued request and publish its immutable child revision."""
        request = ObservationExpansionRequest.model_validate(self.get_observation_expansion(request_id))
        if request.status != "queued":
            return request.model_dump(mode="json")
        base = ObservedModelRevision.model_validate(
            self.get_observed_revision(request.base_observed_revision_id)
        )
        ua_snapshot = UnderstandAnythingSnapshot.model_validate(
            self.get_understand_anything_snapshot(request.ua_snapshot_id)
        )
        code_snapshot = RepositorySnapshot.model_validate(
            self.get_snapshot(base.code_snapshot_id)["snapshot"]
        )
        created = _now()
        result = project_observed_expansion(
            base,
            ua_snapshot,
            code_snapshot,
            node_id=request.target_observed_node_id,
            depth=request.depth,
            created_at=created,
        )
        completed = request.model_copy(update={
            "status": "atomic_at_current_evidence" if result is None else "completed",
            "result_observed_revision_id": None if result is None else result.id,
            "message": (
                "No deeper located UA structure is available for this node."
                if result is None
                else f"Published {result.refinement.added_responsibilities} evidence-backed structural nodes."
            ),
            "updated_at": created,
        })
        created_result = False
        with self.connection() as db:
            if result is not None:
                existing = db.execute(
                    "SELECT id FROM observed_model_revisions WHERE id=?", (result.id,),
                ).fetchone()
                if existing is None:
                    db.execute(
                        """INSERT INTO observed_model_revisions(
                           id,project_id,code_snapshot_id,ua_snapshot_id,parent_revision_id,
                           refinement_of_node_id,revision_json,content_digest,created_at
                           ) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (result.id, result.project_id, result.code_snapshot_id, result.ua_snapshot_id,
                         result.parent_revision_id, result.refinement_of_node_id,
                         result.model_dump_json(), result.content_digest, result.created_at),
                    )
                    created_result = True
            db.execute(
                """UPDATE observation_expansion_requests
                   SET status=?,result_observed_revision_id=?,request_json=?,updated_at=? WHERE id=?""",
                (completed.status, completed.result_observed_revision_id,
                 completed.model_dump_json(), completed.updated_at, completed.id),
            )
        if result is not None and created_result:
            self._write_observed_revision_asset(result)
        return completed.model_dump(mode="json")

    def get_observation_expansion(self, request_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                "SELECT request_json FROM observation_expansion_requests WHERE id=?", (request_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown observation expansion request {request_id!r}")
        return json.loads(row["request_json"])

    def list_observation_expansions(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with self.connection() as db:
            rows = db.execute(
                """SELECT request_json FROM observation_expansion_requests
                   WHERE project_id=? ORDER BY created_at DESC LIMIT ?""",
                (project_id, max(1, min(limit, 100))),
            ).fetchall()
        return [json.loads(row["request_json"]) for row in rows]

    # Independent 0.4 target-design workspaces and immutable operations

    def create_design_workspace(
        self,
        project_id: str,
        base_observed_revision_id: str,
        title: str,
        *,
        actor: str = "human",
        rationale: str = "Create a target design from the current observed baseline.",
    ) -> dict[str, Any]:
        self.get_project(project_id)
        if actor not in {"human", "agent"}:
            raise ValueError("design actor must be human or agent")
        if not title.strip():
            raise ValueError("design workspace title is required")
        if not rationale.strip():
            raise ValueError("design workspace rationale is required")
        observed = ObservedModelRevision.model_validate(
            self.get_observed_revision(base_observed_revision_id)
        )
        if observed.project_id != project_id:
            raise ValueError("observed baseline does not belong to project")
        workspace_id = _id("design-workspace")
        created = _now()
        revision = seed_design_from_observation(
            observed,
            workspace_id=workspace_id,
            title=title.strip(),
            actor=actor,
            rationale=rationale.strip(),
            created_at=created,
        )
        workspace = DesignWorkspace(
            id=workspace_id,
            project_id=project_id,
            title=title.strip(),
            base_observed_revision_id=observed.id,
            base_code_snapshot_id=observed.code_snapshot_id,
            current_design_revision_id=revision.id,
            created_by=actor,
            created_at=created,
            updated_at=created,
        )
        with self.connection() as db:
            db.execute(
                """INSERT INTO design_workspaces_v04(
                   id,project_id,base_observed_revision_id,current_design_revision_id,
                   workspace_json,status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (workspace.id, workspace.project_id, workspace.base_observed_revision_id,
                 workspace.current_design_revision_id, workspace.model_dump_json(), workspace.status,
                 workspace.created_at, workspace.updated_at),
            )
            db.execute(
                """INSERT INTO design_revisions_v04(
                   id,workspace_id,parent_revision_id,revision_json,content_digest,created_at
                   ) VALUES(?,?,?,?,?,?)""",
                (revision.id, workspace.id, revision.parent_revision_id, revision.model_dump_json(),
                 revision.content_digest, revision.created_at),
            )
        self._write_target_workspace_asset(workspace)
        self._write_target_revision_asset(project_id, revision)
        return {"workspace": workspace.model_dump(mode="json"), "revision": revision.model_dump(mode="json")}

    def get_design_workspace(self, workspace_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                "SELECT workspace_json FROM design_workspaces_v04 WHERE id=?", (workspace_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown design workspace {workspace_id!r}")
        return json.loads(row["workspace_json"])

    def list_design_workspaces_v04(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with self.connection() as db:
            rows = db.execute(
                """SELECT workspace_json FROM design_workspaces_v04
                   WHERE project_id=? ORDER BY updated_at DESC""",
                (project_id,),
            ).fetchall()
        return [json.loads(row["workspace_json"]) for row in rows]

    def get_design_revision_v04(self, revision_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                "SELECT revision_json FROM design_revisions_v04 WHERE id=?", (revision_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown design revision {revision_id!r}")
        return json.loads(row["revision_json"])

    def get_design_workspace_view(
        self, project_id: str, workspace_id: str | None = None, revision_id: str | None = None,
    ) -> dict[str, Any] | None:
        workspaces = self.list_design_workspaces_v04(project_id)
        if not workspaces:
            return None
        workspace = self.get_design_workspace(workspace_id) if workspace_id else workspaces[0]
        if workspace["project_id"] != project_id:
            raise ValueError("design workspace does not belong to project")
        selected_id = revision_id or workspace["current_design_revision_id"]
        revision = self.get_design_revision_v04(selected_id)
        if revision["workspace_id"] != workspace["id"]:
            raise ValueError("design revision does not belong to workspace")
        with self.connection() as db:
            rows = db.execute(
                """SELECT revision_json FROM design_revisions_v04
                   WHERE workspace_id=? ORDER BY created_at DESC""",
                (workspace["id"],),
            ).fetchall()
        verification_report = self.latest_verification_report_v04(workspace["id"])
        return {
            "workspace": workspace,
            "revision": revision,
            "revisions": [json.loads(row["revision_json"]) for row in rows],
            "review": self.latest_design_review_v04(workspace["id"]),
            "implementation_export": self.latest_implementation_export_v04(workspace["id"]),
            "verification_report": verification_report,
            "verification_decision": self.latest_verification_decision_v04(
                workspace["id"],
                verification_report["id"] if verification_report is not None else None,
            ),
        }

    def apply_design_operations_v04(
        self,
        workspace_id: str,
        base_design_revision_id: str,
        operations: list[dict[str, Any]],
        *,
        actor: str,
        rationale: str,
    ) -> dict[str, Any]:
        workspace = DesignWorkspace.model_validate(self.get_design_workspace(workspace_id))
        if workspace.status != "draft":
            raise ValueError("only draft design workspaces can be changed")
        if workspace.current_design_revision_id != base_design_revision_id:
            raise ValueError("design revision is stale; reload the workspace before applying operations")
        if actor not in {"human", "agent"}:
            raise ValueError("design actor must be human or agent")
        parsed = [DesignOperation.model_validate(item) for item in operations]
        base = DesignRevision.model_validate(self.get_design_revision_v04(base_design_revision_id))
        created = _now()
        revision = apply_design_operations(
            base, parsed, actor=actor, rationale=rationale, created_at=created,
        )
        updated_workspace = workspace.model_copy(update={
            "current_design_revision_id": revision.id,
            "updated_at": created,
        })
        records = [DesignOperationRecord(
            id=_id("design-operation"),
            workspace_id=workspace.id,
            base_design_revision_id=base.id,
            result_design_revision_id=revision.id,
            operation_index=index,
            operation=operation,
            actor=actor,
            rationale=rationale.strip(),
            created_at=created,
        ) for index, operation in enumerate(parsed)]
        with self.connection() as db:
            db.execute(
                """INSERT INTO design_revisions_v04(
                   id,workspace_id,parent_revision_id,revision_json,content_digest,created_at
                   ) VALUES(?,?,?,?,?,?)""",
                (revision.id, revision.workspace_id, revision.parent_revision_id,
                 revision.model_dump_json(), revision.content_digest, revision.created_at),
            )
            for record in records:
                db.execute(
                    """INSERT INTO design_operations_v04(
                       id,workspace_id,base_design_revision_id,result_design_revision_id,
                       operation_index,operation_json,actor,rationale,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (record.id, record.workspace_id, record.base_design_revision_id,
                     record.result_design_revision_id, record.operation_index,
                     record.operation.model_dump_json(), record.actor, record.rationale,
                     record.created_at),
                )
            db.execute(
                """UPDATE design_workspaces_v04
                   SET current_design_revision_id=?,workspace_json=?,updated_at=? WHERE id=?""",
                (updated_workspace.current_design_revision_id, updated_workspace.model_dump_json(),
                 updated_workspace.updated_at, updated_workspace.id),
            )
        self._write_target_workspace_asset(updated_workspace)
        self._write_target_revision_asset(workspace.project_id, revision)
        for record in records:
            self._write_design_operation_asset(workspace.project_id, record)
        return {
            "workspace": updated_workspace.model_dump(mode="json"),
            "revision": revision.model_dump(mode="json"),
            "operations": [item.model_dump(mode="json") for item in records],
        }

    def list_design_operations_v04(self, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
        self.get_design_workspace(workspace_id)
        with self.connection() as db:
            rows = db.execute(
                """SELECT * FROM design_operations_v04 WHERE workspace_id=?
                   ORDER BY created_at DESC,operation_index ASC LIMIT ?""",
                (workspace_id, max(1, min(limit, 500))),
            ).fetchall()
        return [{
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "base_design_revision_id": row["base_design_revision_id"],
            "result_design_revision_id": row["result_design_revision_id"],
            "operation_index": row["operation_index"],
            "operation": json.loads(row["operation_json"]),
            "actor": row["actor"],
            "rationale": row["rationale"],
            "created_at": row["created_at"],
        } for row in rows]

    def submit_design_review_v04(
        self, workspace_id: str, acceptance_criteria: list[str], *, actor: str,
    ) -> dict[str, Any]:
        workspace = DesignWorkspace.model_validate(self.get_design_workspace(workspace_id))
        if workspace.status != "draft":
            raise ValueError("only a draft workspace can be submitted for review")
        design = DesignRevision.model_validate(
            self.get_design_revision_v04(workspace.current_design_revision_id)
        )
        observed = ObservedModelRevision.model_validate(
            self.get_observed_revision(workspace.base_observed_revision_id)
        )
        submitted = _now()
        review = build_design_review(
            project_id=workspace.project_id,
            workspace_id=workspace.id,
            design=design,
            observed=observed,
            acceptance_statements=acceptance_criteria,
            submitted_by=actor,
            submitted_at=submitted,
        )
        updated_workspace = workspace.model_copy(update={"status": "in_review", "updated_at": submitted})
        with self.connection() as db:
            db.execute(
                """INSERT INTO design_reviews_v04(
                   id,workspace_id,design_revision_id,review_json,status,content_digest,submitted_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                (review.id, review.workspace_id, review.design_revision_id, review.model_dump_json(),
                 review.status, review.content_digest, review.submitted_at),
            )
            db.execute(
                """UPDATE design_workspaces_v04 SET status=?,workspace_json=?,updated_at=? WHERE id=?""",
                (updated_workspace.status, updated_workspace.model_dump_json(),
                 updated_workspace.updated_at, updated_workspace.id),
            )
        self._write_target_workspace_asset(updated_workspace)
        self._write_design_review_asset(workspace.project_id, review)
        return review.model_dump(mode="json")

    def get_design_review_v04(self, review_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                "SELECT review_json FROM design_reviews_v04 WHERE id=?", (review_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown design review {review_id!r}")
        return json.loads(row["review_json"])

    def latest_design_review_v04(self, workspace_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                """SELECT review_json FROM design_reviews_v04
                   WHERE workspace_id=? ORDER BY submitted_at DESC LIMIT 1""",
                (workspace_id,),
            ).fetchone()
        return None if row is None else json.loads(row["review_json"])

    def approve_design_review_v04(self, review_id: str, *, actor: str) -> dict[str, Any]:
        if not actor.strip() or actor in {"agent", "local-agent", "cointent-agent"}:
            raise ValueError("approval requires an authenticated human actor")
        review = DesignReview.model_validate(self.get_design_review_v04(review_id))
        if review.status != "in_review":
            raise ValueError("design review is not awaiting approval")
        workspace = DesignWorkspace.model_validate(self.get_design_workspace(review.workspace_id))
        if workspace.status != "in_review" or workspace.current_design_revision_id != review.design_revision_id:
            raise ValueError("workspace no longer matches the submitted design review")
        approved_at = _now()
        approval = build_approval(review, actor=actor, approved_at=approved_at)
        approved_review = review.model_copy(update={"status": "approved"})
        updated_workspace = workspace.model_copy(update={"status": "approved", "updated_at": approved_at})
        with self.connection() as db:
            db.execute(
                """INSERT INTO design_approvals_v04(
                   id,review_id,workspace_id,approval_json,content_digest,approved_at
                   ) VALUES(?,?,?,?,?,?)""",
                (approval.id, approval.review_id, approval.workspace_id, approval.model_dump_json(),
                 approval.content_digest, approval.approved_at),
            )
            db.execute(
                "UPDATE design_reviews_v04 SET review_json=?,status=? WHERE id=?",
                (approved_review.model_dump_json(), approved_review.status, approved_review.id),
            )
            db.execute(
                """UPDATE design_workspaces_v04 SET status=?,workspace_json=?,updated_at=? WHERE id=?""",
                (updated_workspace.status, updated_workspace.model_dump_json(),
                 updated_workspace.updated_at, updated_workspace.id),
            )
        self._write_target_workspace_asset(updated_workspace)
        self._write_design_review_asset(workspace.project_id, approved_review)
        self._write_design_approval_asset(workspace.project_id, approval)
        return approval.model_dump(mode="json")

    def create_implementation_export_v04(self, workspace_id: str) -> dict[str, Any]:
        workspace = DesignWorkspace.model_validate(self.get_design_workspace(workspace_id))
        if workspace.status not in {"approved", "exported"}:
            raise ValueError("only a human-approved target design can be exported")
        coordinate = self.observation_coordinate(workspace.project_id)
        current_code_id = (coordinate.get("code_snapshot") or {}).get("id")
        if current_code_id != workspace.base_code_snapshot_id:
            raise ValueError("the design baseline is stale; review it against the latest code before export")
        review_data = self.latest_design_review_v04(workspace.id)
        if review_data is None:
            raise ValueError("design workspace has no review")
        review = DesignReview.model_validate(review_data)
        if review.status != "approved" or review.design_revision_id != workspace.current_design_revision_id:
            raise ValueError("the current design revision is not approved")
        with self.connection() as db:
            approval_row = db.execute(
                "SELECT approval_json FROM design_approvals_v04 WHERE review_id=?", (review.id,),
            ).fetchone()
        if approval_row is None:
            raise ValueError("design review has no human approval record")
        approval = DesignApproval.model_validate_json(approval_row["approval_json"])
        observed = ObservedModelRevision.model_validate(
            self.get_observed_revision(review.base_observed_revision_id)
        )
        affected = {item.baseline_observed_id for item in review.changes if item.baseline_observed_id}
        evidence = [
            item.model_dump(mode="json") for item in observed.bindings
            if item.subject_id in affected
        ]
        if not evidence:
            evidence = [
                item.model_dump(mode="json") for item in observed.bindings
                if item.subject_kind == "capability"
            ][:20]
        operations = self.list_design_operations_v04(workspace.id, 500)
        bundle = build_implementation_bundle(
            review=review,
            approval=approval,
            base_code_snapshot_id=workspace.base_code_snapshot_id,
            evidence_context=evidence,
            operation_ids=[item["id"] for item in reversed(operations)],
            created_at=_now(),
        )
        with self.connection() as db:
            existing = db.execute(
                "SELECT bundle_json FROM implementation_exports_v04 WHERE id=?", (bundle.id,),
            ).fetchone()
            if existing is None:
                db.execute(
                    """INSERT INTO implementation_exports_v04(
                       id,workspace_id,design_revision_id,bundle_json,content_digest,created_at
                       ) VALUES(?,?,?,?,?,?)""",
                    (bundle.id, bundle.workspace_id, bundle.design_revision_id,
                     bundle.model_dump_json(), bundle.content_digest, bundle.created_at),
                )
                updated_workspace = workspace.model_copy(update={
                    "status": "exported", "updated_at": bundle.created_at,
                })
                db.execute(
                    """UPDATE design_workspaces_v04 SET status=?,workspace_json=?,updated_at=? WHERE id=?""",
                    (updated_workspace.status, updated_workspace.model_dump_json(),
                     updated_workspace.updated_at, updated_workspace.id),
                )
            else:
                bundle = ImplementationChangeBundle.model_validate_json(existing["bundle_json"])
                updated_workspace = workspace
        if existing is None:
            self._write_target_workspace_asset(updated_workspace)
            self._write_implementation_bundle_asset(workspace.project_id, bundle)
        return bundle.model_dump(mode="json")

    def latest_implementation_export_v04(self, workspace_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                """SELECT bundle_json FROM implementation_exports_v04
                   WHERE workspace_id=? ORDER BY created_at DESC LIMIT 1""",
                (workspace_id,),
            ).fetchone()
        return None if row is None else json.loads(row["bundle_json"])

    def create_verification_report_v04(
        self, workspace_id: str, observed_revision_id: str,
    ) -> dict[str, Any]:
        workspace = DesignWorkspace.model_validate(self.get_design_workspace(workspace_id))
        if workspace.status not in {"exported", "implementing", "verifying", "needs_revision"}:
            raise ValueError("verification requires an exported implementation bundle")
        bundle_data = self.latest_implementation_export_v04(workspace.id)
        if bundle_data is None:
            raise ValueError("verification requires an implementation bundle")
        bundle = ImplementationChangeBundle.model_validate(bundle_data)
        design = DesignRevision.model_validate(
            self.get_design_revision_v04(bundle.design_revision_id)
        )
        baseline = ObservedModelRevision.model_validate(
            self.get_observed_revision(bundle.base_observed_revision_id)
        )
        observed = ObservedModelRevision.model_validate(
            self.get_observed_revision(observed_revision_id)
        )
        if observed.project_id != workspace.project_id:
            raise ValueError("verification observation does not belong to the workspace project")
        if observed.parent_revision_id is not None:
            raise ValueError("verification requires a full root observation, not a focused refinement")
        created = _now()
        report = build_verification_report(
            bundle=bundle,
            design=design,
            baseline=baseline,
            observed=observed,
            created_at=created,
        )
        updated_workspace = workspace.model_copy(update={"status": "verifying", "updated_at": created})
        with self.connection() as db:
            existing = db.execute(
                "SELECT report_json FROM verification_reports_v04 WHERE id=?", (report.id,),
            ).fetchone()
            if existing is None:
                db.execute(
                    """INSERT INTO verification_reports_v04(
                       id,workspace_id,implementation_bundle_id,observed_revision_id,
                       report_json,content_digest,created_at
                       ) VALUES(?,?,?,?,?,?,?)""",
                    (report.id, report.workspace_id, report.implementation_bundle_id,
                     report.observed_revision_id, report.model_dump_json(),
                     report.content_digest, report.created_at),
                )
                db.execute(
                    """UPDATE design_workspaces_v04 SET status=?,workspace_json=?,updated_at=? WHERE id=?""",
                    (updated_workspace.status, updated_workspace.model_dump_json(),
                     updated_workspace.updated_at, updated_workspace.id),
                )
            else:
                if workspace.status == "needs_revision":
                    raise ValueError("this observed revision has already been reviewed; import a later observation")
                report = VerificationReport.model_validate_json(existing["report_json"])
        if existing is None:
            self._write_target_workspace_asset(updated_workspace)
            self._write_verification_report_asset(workspace.project_id, report)
        return report.model_dump(mode="json")

    def get_verification_report_v04(self, report_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                "SELECT report_json FROM verification_reports_v04 WHERE id=?", (report_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown verification report {report_id!r}")
        return json.loads(row["report_json"])

    def latest_verification_report_v04(self, workspace_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                """SELECT report_json FROM verification_reports_v04
                   WHERE workspace_id=? ORDER BY created_at DESC LIMIT 1""",
                (workspace_id,),
            ).fetchone()
        return None if row is None else json.loads(row["report_json"])

    def decide_verification_v04(
        self, report_id: str, *, decision: str, notes: str, actor: str,
    ) -> dict[str, Any]:
        if decision not in {"converged", "needs_revision"}:
            raise ValueError("verification decision must be converged or needs_revision")
        report = VerificationReport.model_validate(self.get_verification_report_v04(report_id))
        workspace = DesignWorkspace.model_validate(self.get_design_workspace(report.workspace_id))
        if workspace.status != "verifying":
            raise ValueError("workspace is not awaiting verification review")
        decided = _now()
        record = build_verification_decision(
            report,
            decision=decision,
            notes=notes,
            actor=actor,
            decided_at=decided,
        )
        updated_workspace = workspace.model_copy(update={
            "status": decision,
            "updated_at": decided,
        })
        with self.connection() as db:
            db.execute(
                """INSERT INTO verification_decisions_v04(
                   id,report_id,workspace_id,decision_json,content_digest,decided_at
                   ) VALUES(?,?,?,?,?,?)""",
                (record.id, record.report_id, record.workspace_id, record.model_dump_json(),
                 record.content_digest, record.decided_at),
            )
            db.execute(
                """UPDATE design_workspaces_v04 SET status=?,workspace_json=?,updated_at=? WHERE id=?""",
                (updated_workspace.status, updated_workspace.model_dump_json(),
                 updated_workspace.updated_at, updated_workspace.id),
            )
        self._write_target_workspace_asset(updated_workspace)
        self._write_verification_decision_asset(workspace.project_id, record)
        return record.model_dump(mode="json")

    def latest_verification_decision_v04(
        self, workspace_id: str, report_id: str | None = None,
    ) -> dict[str, Any] | None:
        with self.connection() as db:
            if report_id is None:
                row = db.execute(
                    """SELECT decision_json FROM verification_decisions_v04
                       WHERE workspace_id=? ORDER BY decided_at DESC LIMIT 1""",
                    (workspace_id,),
                ).fetchone()
            else:
                row = db.execute(
                    """SELECT decision_json FROM verification_decisions_v04
                       WHERE workspace_id=? AND report_id=? ORDER BY decided_at DESC LIMIT 1""",
                    (workspace_id, report_id),
                ).fetchone()
        return None if row is None else json.loads(row["decision_json"])

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

    def find_artifact_responsibilities(
        self, project_id: str, artifact_path: str, version: int | None = None,
    ) -> dict[str, Any]:
        response = self.get_model(project_id, version)
        model = ProjectModel.model_validate(response["model"])
        links = [item for item in model.implementation_links if
                 artifact_path == item.artifact_path or artifact_path.startswith(f"{item.artifact_path.rstrip('/')}/")]
        ids = {item.responsibility_id for item in links}
        return {
            "project_id": project_id, "design_version": response["version"], "artifact_path": artifact_path,
            "implementation_links": [item.model_dump() for item in links],
            "responsibilities": [item.model_dump() for item in model.responsibilities if item.id in ids],
        }

    def alignment_baseline(self, project_id: str) -> dict[str, Any]:
        current = self.get_model(project_id)
        snapshots = self.list_snapshots(project_id, 1)
        with self.connection() as db:
            mapping = db.execute(
                "SELECT * FROM mapping_revisions WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,)
            ).fetchone()
        mapping_item = None if mapping is None else _mapping_revision(mapping)
        latest_snapshot_id = snapshots[0]["id"] if snapshots else None
        return {
            "project_id": project_id, "design_version": current["version"],
            "code_snapshot": snapshots[0] if snapshots else None, "mapping_revision": mapping_item,
            "is_current": bool(mapping_item and mapping_item["design_version"] == current["version"]
                               and mapping_item["snapshot_id"] == latest_snapshot_id),
        }

    def record_mapping_revision(
        self, project_id: str, design_version: int | None = None, snapshot_id: str | None = None,
        implementation_links: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        design = self.get_model(project_id, design_version)
        snapshots = self.list_snapshots(project_id, 1)
        selected_snapshot = snapshot_id or (snapshots[0]["id"] if snapshots else None)
        if selected_snapshot is None:
            raise ValueError("a code snapshot is required before recording a mapping revision")
        if self.get_snapshot(selected_snapshot)["project_id"] != project_id:
            raise ValueError("snapshot does not belong to project")
        model = ProjectModel.model_validate(design["model"])
        selected = implementation_links if implementation_links is not None else design["model"]["implementation_links"]
        validated = [ImplementationLink.model_validate(item) for item in selected]
        ProjectModel.model_validate(model.model_copy(update={"implementation_links": validated}).model_dump())
        encoded = json.dumps([item.model_dump() for item in validated], separators=(",", ":"), sort_keys=True)
        with self.connection() as db:
            existing = db.execute(
                """SELECT * FROM mapping_revisions WHERE project_id=? AND design_version=?
                   AND snapshot_id=? AND trace_links_json=? ORDER BY created_at DESC LIMIT 1""",
                (project_id, design["version"], selected_snapshot, encoded),
            ).fetchone()
            if existing is not None:
                return {**_mapping_revision(existing), "duplicate": True}
            item = {
                "id": _id("mapping"), "project_id": project_id, "design_version": design["version"],
                "snapshot_id": selected_snapshot, "trace_links_json": encoded, "created_at": _now(),
            }
            db.execute("""
                INSERT INTO mapping_revisions(id,project_id,design_version,snapshot_id,trace_links_json,created_at)
                VALUES(:id,:project_id,:design_version,:snapshot_id,:trace_links_json,:created_at)
            """, item)
        return {**self.get_mapping_revision(item["id"]), "duplicate": False}

    def get_mapping_revision(self, mapping_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM mapping_revisions WHERE id=?", (mapping_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown mapping revision {mapping_id!r}")
        return _mapping_revision(row)

    def list_mapping_revisions(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM mapping_revisions WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, max(1, min(limit, 100))),
            ).fetchall()
        return [_mapping_revision(row) for row in rows]

    def compare_design_to_code(self, project_id: str) -> dict[str, Any]:
        return {
            "baseline": self.alignment_baseline(project_id),
            "coverage": self.specification_coverage(project_id),
            "quality": self.responsibility_quality(project_id),
            "findings": self.list_findings(project_id),
        }

    # Change lifecycle, history, and summaries

    def start_change_set(
        self, project_id: str, title: str, description: str = "",
        specification_ids: list[str] | None = None, responsibility_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        current = self.get_model(project_id)
        item = {
            "id": _id("change"), "project_id": project_id, "title": title, "description": description,
            "base_design_version": current["version"], "target_design_version": None,
            "proposal_id": None, "snapshot_id": None,
            "function_ids_json": json.dumps(specification_ids or []),
            "role_ids_json": json.dumps(responsibility_ids or []),
            "status": "designing", "resolution": "", "created_at": _now(), "updated_at": _now(),
        }
        with self.connection() as db:
            db.execute("""INSERT INTO change_sets VALUES(:id,:project_id,:title,:description,:base_design_version,
                       :target_design_version,:proposal_id,:snapshot_id,:function_ids_json,:role_ids_json,:status,
                       :resolution,:created_at,:updated_at)""", item)
        return self.get_change_set(item["id"])

    def get_change_set(self, change_set_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM change_sets WHERE id=?", (change_set_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown change set {change_set_id!r}")
        return _change_set(row)

    def list_change_sets(self, project_id: str, status: str = "all") -> list[dict[str, Any]]:
        with self.connection() as db:
            if status == "all":
                rows = db.execute(
                    "SELECT * FROM change_sets WHERE project_id=? ORDER BY updated_at DESC", (project_id,)
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM change_sets WHERE project_id=? AND status=? ORDER BY updated_at DESC",
                    (project_id, status),
                ).fetchall()
        return [_change_set(row) for row in rows]

    def update_change_set(
        self, change_set_id: str, *, proposal_id: str | None = None, snapshot_id: str | None = None,
        target_design_version: int | None = None, status: str | None = None, resolution: str | None = None,
    ) -> dict[str, Any]:
        allowed = {"designing", "approved", "implementing", "reviewing", "closed", "cancelled"}
        if status is not None and status not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        updates = {key: value for key, value in {
            "proposal_id": proposal_id, "snapshot_id": snapshot_id,
            "target_design_version": target_design_version, "status": status, "resolution": resolution,
        }.items() if value is not None}
        updates["updated_at"] = _now()
        assignments = ",".join(f"{key}=?" for key in updates)
        with self.connection() as db:
            changed = db.execute(
                f"UPDATE change_sets SET {assignments} WHERE id=?", (*updates.values(), change_set_id)
            ).rowcount
        if not changed:
            raise KeyError(f"unknown change set {change_set_id!r}")
        return self.get_change_set(change_set_id)

    def implementation_brief(self, change_set_id: str) -> dict[str, Any]:
        change = self.get_change_set(change_set_id)
        response = self.get_model(change["project_id"], change["target_design_version"] or None)
        model = ProjectModel.model_validate(response["model"])
        specifications = [item.model_dump() for item in model.specification_items
                          if item.id in change["specification_ids"]]
        responsibilities = [self.inspect_responsibility(change["project_id"], value, response["version"])
                            for value in change["responsibility_ids"]]
        return {
            "change_set": change, "design_version": response["version"],
            "specification_items": specifications, "affected_responsibilities": responsibilities,
            "agent_prompt": (
                f"Implement change set {change['id']} against accepted design v{response['version']}. "
                "Preserve Responsibility contracts and Workflow semantics, add backend evidence, then ingest a snapshot."
            ),
        }

    def export_design(self, project_id: str, version: int | None = None) -> dict[str, Any]:
        return {"export_schema": "cointent.design-bundle/0.3", **self.get_model(project_id, version)}

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
            pending_proposals = db.execute(
                "SELECT COUNT(*) FROM proposals WHERE project_id=? AND status='pending'", (project_id,)
            ).fetchone()[0]
        summary = None
        if snapshot:
            observed = json.loads(snapshot["snapshot_json"])
            summary = {key: observed[key] for key in
                       ("id", "repository", "revision", "branch", "dirty", "captured_at")}
            summary["artifact_count"] = len(observed["artifacts"])
            summary["relation_count"] = len(observed["relations"])
        workflows = sum(1 for item in model["responsibilities"] if item.get("workflow"))
        leaves = len(model["responsibilities"]) - workflows
        return {
            "project": current["project"], "version": current["version"], "status": model["status"],
            "counts": {
                "specification_items": len(model["specification_items"]),
                "responsibilities": len(model["responsibilities"]), "workflows": workflows,
                "leaf_responsibilities": leaves,
                "specification_links": len(model["specification_responsibility_links"]),
                "implementation_links": len(model["implementation_links"]),
                "open_findings": open_findings, "pending_proposals": pending_proposals,
            },
            "latest_snapshot": summary, "snapshot_recorded_at": snapshot["created_at"] if snapshot else None,
        }

    # Portable JSON assets

    def _backfill_assets(self) -> None:
        with self.connection() as db:
            projects = db.execute("SELECT * FROM projects").fetchall()
            versions = db.execute("SELECT project_id,version,model_json FROM model_versions").fetchall()
            snapshots = db.execute("SELECT snapshot_json FROM snapshots").fetchall()
        for row in projects:
            target = self._project_dir(row["id"]) / "project.json"
            if not target.exists():
                _atomic_json(target, dict(row))
        for row in versions:
            target = self._project_dir(row["project_id"]) / "design" / f"v{int(row['version']):06d}.json"
            if not target.exists():
                _atomic_json(target, ProjectModel.model_validate_json(row["model_json"]).model_dump())
        for row in snapshots:
            snapshot = RepositorySnapshot.model_validate_json(row["snapshot_json"])
            target = self._project_dir(snapshot.project_id) / "snapshots" / f"{snapshot.id}.json"
            if not target.exists():
                _atomic_json(target, snapshot.model_dump())

    def _project_dir(self, project_id: str) -> Path:
        candidate = Path(project_id)
        if (not project_id or candidate.is_absolute() or "/" in project_id or "\\" in project_id
                or any(part in {"", ".", ".."} for part in candidate.parts)):
            raise ValueError("unsafe project id")
        return self.asset_root / project_id

    def _write_project_asset(self, project: dict[str, Any]) -> None:
        _atomic_json(self._project_dir(project["id"]) / "project.json", project)

    def _write_design_asset(self, project_id: str, version: int, model: ProjectModel) -> None:
        _atomic_json(self._project_dir(project_id) / "design" / f"v{version:06d}.json", model.model_dump())

    def _write_snapshot_asset(self, snapshot: RepositorySnapshot) -> None:
        _atomic_json(self._project_dir(snapshot.project_id) / "snapshots" / f"{snapshot.id}.json", snapshot.model_dump())

    def _write_ua_snapshot_asset(self, snapshot: UnderstandAnythingSnapshot) -> None:
        _atomic_json(
            self._project_dir(snapshot.project_id) / "understand-anything" / f"{snapshot.id}.json",
            snapshot.model_dump(mode="json", by_alias=True),
        )

    def _write_observed_revision_asset(self, revision: ObservedModelRevision) -> None:
        _atomic_json(
            self._project_dir(revision.project_id) / "observed" / f"{revision.id}.json",
            revision.model_dump(mode="json"),
        )

    def _write_target_workspace_asset(self, workspace: DesignWorkspace) -> None:
        _atomic_json(
            self._project_dir(workspace.project_id) / "target-design" / workspace.id / "workspace.json",
            workspace.model_dump(mode="json"),
        )

    def _write_target_revision_asset(self, project_id: str, revision: DesignRevision) -> None:
        _atomic_json(
            self._project_dir(project_id) / "target-design" / revision.workspace_id
            / "revisions" / f"{revision.id}.json",
            revision.model_dump(mode="json"),
        )

    def _write_design_operation_asset(self, project_id: str, record: DesignOperationRecord) -> None:
        _atomic_json(
            self._project_dir(project_id) / "target-design" / record.workspace_id
            / "operations" / f"{record.id}.json",
            record.model_dump(mode="json"),
        )

    def _write_design_review_asset(self, project_id: str, review: DesignReview) -> None:
        _atomic_json(
            self._project_dir(project_id) / "target-design" / review.workspace_id
            / "reviews" / f"{review.id}.json",
            review.model_dump(mode="json"),
        )

    def _write_design_approval_asset(self, project_id: str, approval: DesignApproval) -> None:
        _atomic_json(
            self._project_dir(project_id) / "target-design" / approval.workspace_id
            / "approvals" / f"{approval.id}.json",
            approval.model_dump(mode="json"),
        )

    def _write_implementation_bundle_asset(
        self, project_id: str, bundle: ImplementationChangeBundle,
    ) -> None:
        _atomic_json(
            self._project_dir(project_id) / "target-design" / bundle.workspace_id
            / "exports" / f"{bundle.id}.json",
            bundle.model_dump(mode="json"),
        )

    def _write_verification_report_asset(self, project_id: str, report: VerificationReport) -> None:
        _atomic_json(
            self._project_dir(project_id) / "target-design" / report.workspace_id
            / "verifications" / f"{report.id}.json",
            report.model_dump(mode="json"),
        )

    def _write_verification_decision_asset(
        self, project_id: str, decision: VerificationDecision,
    ) -> None:
        _atomic_json(
            self._project_dir(project_id) / "target-design" / decision.workspace_id
            / "verification-decisions" / f"{decision.id}.json",
            decision.model_dump(mode="json"),
        )


def _proposal(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for source, target in (("patch_json", "patch"), ("proposed_model_json", "proposed_model"),
                           ("diff_json", "diff"), ("evidence_json", "evidence_ids")):
        item[target] = json.loads(item.pop(source))
    return item


def _change_set(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["specification_ids"] = json.loads(item.pop("function_ids_json"))
    item["responsibility_ids"] = json.loads(item.pop("role_ids_json"))
    return item


def _normalize_implementation_link(item: dict[str, Any]) -> dict[str, Any]:
    if "responsibility_id" not in item and "role_id" in item:
        item = dict(item)
        item["responsibility_id"] = item.pop("role_id")
        if item.get("kind") == "presents":
            item["kind"] = "supports"
        item.setdefault("symbol", "")
    return item


def _mapping_revision(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    links = [_normalize_implementation_link(value) for value in json.loads(item.pop("trace_links_json"))]
    item["implementation_links"] = links
    return item


def _finding(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["responsibility_ids"] = json.loads(item.pop("role_ids_json"))
    item["artifact_paths"] = json.loads(item.pop("artifact_paths_json"))
    item["evidence"] = json.loads(item.pop("evidence_json"))
    return item


def _select_hierarchy(items: list[Any], root_id: str | None, depth: int) -> list[Any]:
    if root_id is None:
        return items
    by_id = {item.id: item for item in items}
    if root_id not in by_id:
        raise KeyError(f"unknown hierarchy root {root_id!r}")
    selected = {root_id}
    frontier = {root_id}
    for _ in range(max(0, min(depth, 50))):
        frontier = {item.id for item in items if item.parent_id in frontier}
        if not frontier:
            break
        selected.update(frontier)
    return [item for item in items if item.id in selected]


def _reachable(entries: list[str], edges: list[Any]) -> set[str]:
    outgoing: dict[str, set[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge.source_node_id, set()).add(edge.target_node_id)
    seen = set(entries)
    frontier = set(entries)
    while frontier:
        frontier = {target for source in frontier for target in outgoing.get(source, set()) if target not in seen}
        seen.update(frontier)
    return seen


def _atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp-{uuid.uuid4().hex[:8]}")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _path_matches(mapping: str, path: str) -> bool:
    prefix = mapping.rstrip("/")
    return path == prefix or path.startswith(f"{prefix}/")
