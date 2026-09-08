"""CoIntent command-line entry points."""

from __future__ import annotations

import argparse
import json
import os
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
    scan.add_argument("--seed-idea-factory", action="store_true")
    scan.add_argument("--export")

    load = commands.add_parser("import-fixture", help="idempotently import a snapshot and model fixture")
    load.add_argument("--snapshot", required=True)
    load.add_argument("--model", required=True)

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
    snapshot = scan_repository(args.repository, args.project_id, include_untracked=args.include_untracked)
    repository = CoIntentRepository(args.database)
    repository.ensure_project(args.project_id, args.name or args.project_id.replace("-", " ").title(), snapshot.repository)
    result = repository.ingest_snapshot(args.project_id, snapshot.model_dump())
    current = repository.get_model(args.project_id)
    if args.seed_idea_factory and not current["model"]["roles"]:
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
    if not current["model"]["roles"]:
        repository.replace_model(model.project_id, model, actor="agent:fixture", message="Import experiment baseline")
    print(json.dumps(repository.overview(model.project_id), indent=2))
