"""CoIntent command-line entry points."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .experiments import idea_factory_model
from .repository import CoIntentRepository
from .scanner import RepositorySnapshot, scan_repository


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cointent")
    root.add_argument("--database", default=os.environ.get("COINTENT_DB_PATH", "runtime/cointent.db"))
    commands = root.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="scan a Git repository without modifying it")
    scan.add_argument("repository")
    scan.add_argument("--project-id", required=True)
    scan.add_argument("--name")
    scan.add_argument("--include-untracked", action="store_true")
    scan.add_argument("--scope", choices=("backend", "full"), default="backend")
    scan.add_argument("--seed-idea-factory", action="store_true")
    scan.add_argument("--export")

    load = commands.add_parser("import-fixture", help="idempotently import a snapshot and model fixture")
    load.add_argument("--snapshot", required=True)
    load.add_argument("--model", required=True)

    ua = commands.add_parser("import-understand-anything", help="operator-only import of completed UA graph JSON")
    ua.add_argument("--project-id", required=True)
    ua.add_argument("--code-snapshot-id", required=True)
    ua.add_argument("--knowledge-graph", required=True)
    ua.add_argument("--domain-graph")
    ua.add_argument("--ua-tool-revision", required=True)

    bind = commands.add_parser("bind-checkout", help="bind a trusted local checkout for on-demand refreshes")
    bind.add_argument("--project-id", required=True)
    bind.add_argument("repository")

    refresh = commands.add_parser("refresh", help="request an on-demand understanding refresh")
    refresh.add_argument("--project-id", required=True)
    refresh.add_argument("--run", action="store_true", help="run this job in the current trusted worker process")

    worker = commands.add_parser("refresh-worker", help="run the trusted on-demand understanding worker")
    selection = worker.add_mutually_exclusive_group(required=True)
    selection.add_argument("--job-id", help="process one queued job")
    selection.add_argument("--forever", action="store_true", help="poll and process queued jobs continuously")
    worker.add_argument("--poll-seconds", type=float, default=2.0)

    export = commands.add_parser("export-model", help="export the current accepted model as JSON")
    export.add_argument("--project-id", required=True)
    export.add_argument("--output", required=True)

    serve = commands.add_parser("serve", help="serve Contexture MCP and REST over HTTP")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8811)

    commands.add_parser("mcp", help="serve the Contexture MCP application over stdio")
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    os.environ["COINTENT_DB_PATH"] = args.database
    if args.command == "scan":
        _scan(args)
    elif args.command == "import-fixture":
        _import_fixture(args)
    elif args.command == "import-understand-anything":
        _import_understand_anything(args)
    elif args.command == "bind-checkout":
        result = CoIntentRepository(args.database).set_project_checkout(args.project_id, args.repository)
        print(json.dumps(result, indent=2))
    elif args.command == "refresh":
        repository = CoIntentRepository(args.database)
        result = repository.request_understanding_refresh(args.project_id, requested_by="operator")
        if args.run and result["job"]["status"] == "queued":
            from .refresh import run_refresh_job
            result = {"duplicate": result["duplicate"], "job": run_refresh_job(repository, result["job"]["id"])}
        print(json.dumps(result, indent=2))
    elif args.command == "refresh-worker":
        from .refresh import run_refresh_job
        repository = CoIntentRepository(args.database)
        if args.job_id:
            print(json.dumps(run_refresh_job(repository, args.job_id), indent=2))
        else:
            delay = max(0.25, min(args.poll_seconds, 60.0))
            try:
                while True:
                    job_id = repository.next_queued_understanding_refresh()
                    if job_id is None:
                        time.sleep(delay)
                        continue
                    try:
                        print(json.dumps(run_refresh_job(repository, job_id)), flush=True)
                    except Exception as error:
                        try:
                            job = repository.get_understanding_refresh(job_id)
                        except KeyError:
                            continue
                        # A concurrent worker claiming the same candidate is normal.
                        if job["status"] == "failed":
                            print(json.dumps({"job_id": job_id, "status": "failed", "error": str(error)}), flush=True)
            except KeyboardInterrupt:
                return
    elif args.command == "serve":
        if args.host not in {"127.0.0.1", "localhost", "::1"} and not os.environ.get("COINTENT_MCP_TOKEN"):
            raise SystemExit("COINTENT_MCP_TOKEN is required for a non-loopback server")
        if args.host not in {"127.0.0.1", "localhost", "::1"} and not (
            os.environ.get("COINTENT_LOGIN_USER") and os.environ.get("COINTENT_LOGIN_PASSWORD")
        ):
            raise SystemExit("COINTENT_LOGIN_USER and COINTENT_LOGIN_PASSWORD are required for a non-loopback server")
        import uvicorn
        uvicorn.run("cointent.app:application", host=args.host, port=args.port, factory=False)
    elif args.command == "export-model":
        repository = CoIntentRepository(args.database)
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(repository.get_model(args.project_id)["model"], indent=2) + "\n", encoding="utf-8")
        print(target)
    elif args.command == "mcp":
        from contexture.server import ContextureOptions, serve
        from .controller import app
        serve(app, ContextureOptions(transport="stdio"))


def _scan(args: argparse.Namespace) -> None:
    snapshot = scan_repository(
        args.repository, args.project_id, include_untracked=args.include_untracked, scope=args.scope,
    )
    repository = CoIntentRepository(args.database)
    repository.ensure_project(args.project_id, args.name or args.project_id.replace("-", " ").title(), snapshot.repository)
    repository.set_project_checkout(args.project_id, args.repository)
    result = repository.ingest_snapshot(args.project_id, snapshot.model_dump())
    current = repository.get_model(args.project_id)
    if args.seed_idea_factory and not current["model"]["responsibilities"]:
        repository.replace_model(
            args.project_id, idea_factory_model(snapshot), actor="agent:initial-scan",
            message="Create the first responsibility model from repository evidence.",
        )
    if args.export:
        Path(args.export).parent.mkdir(parents=True, exist_ok=True)
        Path(args.export).write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    delta = result["diff"]
    print(json.dumps({
        "snapshot": snapshot.id, "revision": snapshot.revision,
        "scope": snapshot.scope,
        "duplicate": result["duplicate"],
        "artifacts": len(snapshot.artifacts), "relations": len(snapshot.relations),
        "delta": {"added": len(delta["added"]), "modified": len(delta["modified"]),
                  "removed": len(delta["removed"]), "relations_added": len(delta["relations_added"]),
                  "relations_removed": len(delta["relations_removed"])},
        "findings_created": len(result["findings_created"]),
        "model_version": repository.get_model(args.project_id)["version"],
    }, indent=2))


def _import_fixture(args: argparse.Namespace) -> None:
    snapshot = RepositorySnapshot.model_validate_json(Path(args.snapshot).read_text(encoding="utf-8"))
    from .models import ProjectModel
    model = ProjectModel.model_validate_json(Path(args.model).read_text(encoding="utf-8"))
    repository = CoIntentRepository(args.database)
    repository.ensure_project(model.project_id, model.name, snapshot.repository)
    repository.ingest_snapshot(model.project_id, snapshot.model_dump())
    current = repository.get_model(model.project_id)
    if (not current["model"]["responsibilities"]
            or repository.stored_schema_version(model.project_id) != model.schema_version):
        repository.replace_model(model.project_id, model, actor="agent:fixture", message="Import experiment baseline")
    repository.record_mapping_revision(model.project_id, snapshot_id=snapshot.id)
    repository.dismiss_non_backend_findings(model.project_id)
    print(json.dumps(repository.overview(model.project_id), indent=2))


def _import_understand_anything(args: argparse.Namespace) -> None:
    knowledge = json.loads(Path(args.knowledge_graph).read_text(encoding="utf-8"))
    domain = None
    if args.domain_graph:
        domain = json.loads(Path(args.domain_graph).read_text(encoding="utf-8"))
    result = CoIntentRepository(args.database).import_understand_anything(
        args.project_id, args.code_snapshot_id, args.ua_tool_revision, knowledge, domain,
    )
    revision = result["observed_revision"]
    print(json.dumps({
        "duplicate": result["duplicate"],
        "ua_snapshot_id": result["ua_snapshot"]["id"],
        "observed_revision_id": revision["id"],
        "observed_responsibilities": len(revision["responsibilities"]),
        "observed_capabilities": len(revision["capabilities"]),
        "diagnostics": len(revision["diagnostics"]),
    }, indent=2))
