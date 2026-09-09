"""Read-only Understand Anything viewer sessions and source helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict


VIEWER_PROTOCOL_VERSION = 1
VIEWER_TTL_SECONDS = 15 * 60
MAX_SOURCE_BYTES = 1024 * 1024


class UaViewerSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    project_id: str
    observed_revision_id: str
    ua_snapshot_id: str
    code_snapshot_id: str
    principal: str
    expires_at: str
    created_at: str


class UaViewerSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    viewer_url: str
    project_id: str
    observed_revision_id: str
    ua_snapshot_id: str
    code_snapshot_id: str
    expires_at: str


class SourceContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    language: str
    content: str
    size_bytes: int
    line_count: int
    source_digest: str


def issue_viewer_token() -> tuple[str, str, str]:
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest(), f"ua-viewer-{secrets.token_hex(12)}"


def expiry() -> str:
    return (datetime.now(UTC) + timedelta(seconds=VIEWER_TTL_SECONDS)).isoformat()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_expired(value: str) -> bool:
    return datetime.fromisoformat(value) <= datetime.now(UTC)


def safe_source_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("source path must be a normalized repository-relative path")
    normalized = str(path)
    if "\x00" in normalized or "\\" in normalized:
        raise ValueError("source path must be a normalized repository-relative path")
    return normalized


def source_language(path: str) -> str:
    extension = PurePosixPath(path).suffix.lower()
    return {
        ".bash": "bash", ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".cs": "csharp",
        ".css": "css", ".go": "go", ".h": "c", ".hpp": "cpp", ".html": "markup",
        ".java": "java", ".js": "javascript", ".jsx": "jsx", ".json": "json",
        ".md": "markdown", ".mjs": "javascript", ".py": "python", ".rb": "ruby",
        ".rs": "rust", ".sh": "bash", ".ts": "typescript", ".tsx": "tsx",
        ".txt": "text", ".yaml": "yaml", ".yml": "yaml",
    }.get(extension, "text")
