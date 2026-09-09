"""Read-only backend repository facts for Responsibility inference."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


IGNORED_PREFIXES = (
    ".git/", ".venv/", "node_modules/", "dist/", "build/", "web-dist/",
    "data/processed/", ".pytest_cache/", ".ruff_cache/", "__pycache__/",
    "web/", "frontend/", "studio/", "ui/", "client/", "public/", "assets/",
)

FRONTEND_SEGMENTS = (
    "/web/", "/frontend/", "/studio/", "/ui/", "/client/", "/components/", "/pages/",
)
FRONTEND_SUFFIXES = {".tsx", ".jsx", ".css", ".scss", ".sass", ".less", ".html", ".vue", ".svelte"}
TECHNICAL_NOISE_SEGMENTS = (
    "/logging/", "/logger/", "/telemetry/", "/metrics/", "/tracing/", "/monitoring/",
)


class ScanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Artifact(ScanRecord):
    path: str
    kind: str
    language: str
    component: str
    sha256: str
    size: int


class CodeRelation(ScanRecord):
    source: str
    target: str
    kind: str = "imports"


class RepositorySnapshot(ScanRecord):
    schema_version: str = "0.1"
    id: str
    project_id: str
    repository: str
    revision: str
    branch: str
    dirty: bool
    captured_at: str
    artifacts: list[Artifact] = Field(default_factory=list)
    relations: list[CodeRelation] = Field(default_factory=list)
    entrypoints: dict[str, str] = Field(default_factory=dict)
    language_counts: dict[str, int] = Field(default_factory=dict)


def scan_repository(root: str | Path, project_id: str, *, include_untracked: bool = False) -> RepositorySnapshot:
    base = Path(root).resolve()
    if not (base / ".git").exists():
        raise ValueError(f"not a Git working tree: {base}")
    paths = _git_paths(base, include_untracked=include_untracked)
    artifacts: list[Artifact] = []
    for relative in paths:
        if _ignored(relative):
            continue
        path = base / relative
        if not path.is_file():
            continue
        payload = path.read_bytes()
        artifacts.append(Artifact(
            path=relative,
            kind=_kind(relative),
            language=_language(relative),
            component=_component(relative),
            sha256=hashlib.sha256(payload).hexdigest(),
            size=len(payload),
        ))
    artifacts.sort(key=lambda item: item.path)
    relations = _relations(base, artifacts)
    entrypoints = _entrypoints(base)
    revision = _git(base, "rev-parse", "HEAD")
    identity = hashlib.sha256(json.dumps({
        "revision": revision,
        "artifacts": [(item.path, item.sha256) for item in artifacts],
        "relations": [(item.source, item.target, item.kind) for item in relations],
    }, separators=(",", ":")).encode()).hexdigest()[:20]
    return RepositorySnapshot(
        id=f"snapshot-{identity}",
        project_id=project_id,
        repository=_git(base, "remote", "get-url", "origin", required=False) or base.name,
        revision=revision,
        branch=_git(base, "branch", "--show-current", required=False) or "detached",
        dirty=bool(_git(base, "status", "--porcelain", "--untracked-files=no", required=False)),
        captured_at=datetime.now(UTC).isoformat(),
        artifacts=artifacts,
        relations=relations,
        entrypoints=entrypoints,
        language_counts=dict(sorted(Counter(item.language for item in artifacts).items())),
    )


def snapshot_diff(before: RepositorySnapshot | None, after: RepositorySnapshot) -> dict[str, Any]:
    if before is None:
        return {
            "from_snapshot": None,
            "to_snapshot": after.id,
            "added": [item.path for item in after.artifacts],
            "modified": [],
            "removed": [],
            "relations_added": [item.model_dump() for item in after.relations],
            "relations_removed": [],
        }
    old = {item.path: item.sha256 for item in before.artifacts}
    new = {item.path: item.sha256 for item in after.artifacts}
    old_rel = {(item.source, item.target, item.kind) for item in before.relations}
    new_rel = {(item.source, item.target, item.kind) for item in after.relations}
    return {
        "from_snapshot": before.id,
        "to_snapshot": after.id,
        "added": sorted(new.keys() - old.keys()),
        "modified": sorted(path for path in old.keys() & new.keys() if old[path] != new[path]),
        "removed": sorted(old.keys() - new.keys()),
        "relations_added": [dict(zip(("source", "target", "kind"), row)) for row in sorted(new_rel - old_rel)],
        "relations_removed": [dict(zip(("source", "target", "kind"), row)) for row in sorted(old_rel - new_rel)],
    }


def _git_paths(base: Path, *, include_untracked: bool) -> list[str]:
    command = ["git", "ls-files", "-z"]
    if include_untracked:
        command.extend(["--cached", "--others", "--exclude-standard"])
    result = subprocess.run(command, cwd=base, check=True, capture_output=True)
    return sorted(path for path in result.stdout.decode().split("\0") if path)


def _git(base: Path, *args: str, required: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=base, capture_output=True, text=True)
    if required and result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip() if result.returncode == 0 else ""


def _ignored(path: str) -> bool:
    normalized = "/" + path.replace("\\", "/").lower()
    relative = normalized.removeprefix("/")
    if any(relative.startswith(prefix) or f"/{prefix}" in normalized for prefix in IGNORED_PREFIXES):
        return True
    if Path(relative).suffix.lower() in FRONTEND_SUFFIXES:
        return True
    if any(segment in normalized for segment in FRONTEND_SEGMENTS):
        return True
    return any(segment in normalized for segment in TECHNICAL_NOISE_SEGMENTS)


def is_backend_logic_candidate(path: str) -> bool:
    """Return whether a changed path can carry product-relevant backend logic."""
    normalized = "/" + path.replace("\\", "/").lower()
    relative = normalized.removeprefix("/")
    if Path(relative).suffix.lower() not in {".py", ".go", ".rs", ".java", ".kt", ".rb", ".php"}:
        return False
    if any(relative.startswith(prefix) for prefix in (
        "web/", "frontend/", "studio/", "ui/", "client/", "public/", "assets/",
    )):
        return False
    if any(segment in normalized for segment in FRONTEND_SEGMENTS):
        return False
    return not any(segment in normalized for segment in TECHNICAL_NOISE_SEGMENTS)


def _language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript",
        ".js": "JavaScript", ".jsx": "JavaScript", ".json": "JSON",
        ".md": "Markdown", ".yml": "YAML", ".yaml": "YAML",
        ".toml": "TOML", ".sh": "Shell", ".css": "CSS", ".html": "HTML",
    }.get(suffix, suffix.removeprefix(".").upper() or "Other")


def _kind(path: str) -> str:
    name = Path(path).name.lower()
    if name in {"pyproject.toml", "package.json", "package-lock.json"}:
        return "manifest"
    if name.startswith("readme") or path.startswith("docs/") or name in {"claude.md", "agents.md"}:
        return "documentation"
    if "/test" in path or path.startswith("tests/"):
        return "test"
    if Path(path).suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        return "source"
    return "resource"


def _component(path: str) -> str:
    parts = Path(path).parts
    if len(parts) >= 2 and parts[0] == "src":
        return f"src/{parts[1]}"
    if len(parts) >= 2 and parts[0] == "studio":
        return f"studio/{parts[1]}"
    return parts[0] if len(parts) > 1 else "root"


def _relations(base: Path, artifacts: list[Artifact]) -> list[CodeRelation]:
    known = {item.path for item in artifacts}
    module_to_path: dict[str, str] = {}
    for path in known:
        if path.startswith("src/") and path.endswith(".py"):
            module = path[4:-3].replace("/", ".")
            if module.endswith(".__init__"):
                module = module[:-9]
            module_to_path[module] = path
    found: set[tuple[str, str, str]] = set()
    for artifact in artifacts:
        if artifact.language == "Python" and artifact.kind == "source":
            try:
                tree = ast.parse((base / artifact.path).read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module)
            for imported in imports:
                target = _resolve_module(imported, module_to_path)
                if target and target != artifact.path:
                    found.add((artifact.path, target, "imports"))
        elif artifact.language in {"TypeScript", "JavaScript"} and artifact.kind == "source":
            try:
                text = (base / artifact.path).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for specifier in re.findall(r"(?:from\s+|import\s*\()\s*['\"]([^'\"]+)['\"]", text):
                target = _resolve_relative(artifact.path, specifier, known)
                if target:
                    found.add((artifact.path, target, "imports"))
    return [CodeRelation(source=a, target=b, kind=k) for a, b, k in sorted(found)]


def _resolve_module(name: str, modules: dict[str, str]) -> str | None:
    candidate = name
    while candidate:
        if candidate in modules:
            return modules[candidate]
        candidate = candidate.rpartition(".")[0]
    return None


def _resolve_relative(source: str, specifier: str, known: set[str]) -> str | None:
    if not specifier.startswith("."):
        return None
    stem = (Path(source).parent / specifier).as_posix()
    for candidate in (stem, f"{stem}.ts", f"{stem}.tsx", f"{stem}.js", f"{stem}.jsx",
                      f"{stem}/index.ts", f"{stem}/index.tsx"):
        normalized = str(Path(candidate))
        if normalized in known:
            return normalized
    return None


def _entrypoints(base: Path) -> dict[str, str]:
    path = base / "pyproject.toml"
    if not path.exists():
        return {}
    try:
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    scripts = data.get("project", {}).get("scripts", {})
    return {str(key): str(value) for key, value in scripts.items()}
