"""Persistent state models for on-demand native Understand Anything refreshes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class UnderstandingRefreshJob(BaseModel):
    """Public view of one explicitly requested, Agent-executed understanding refresh."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["cointent.understanding-refresh/0.1"] = "cointent.understanding-refresh/0.1"
    id: str
    project_id: str
    status: Literal[
        "queued", "running", "awaiting_upload", "validating", "completed", "failed",
    ] = "queued"
    mode: Literal["unchanged", "incremental", "full"] | None = None
    requested_by: str
    changed_files: list[str] = Field(default_factory=list)
    ua_files_reanalyzed: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None
    diagnostics: list[str] = Field(default_factory=list)
    repository_revision: str | None = None
    repository_branch: str | None = None
    repository_identity: str | None = None
    base_observed_revision_id: str | None = None
    analysis_profile_digest: str | None = None
    checkpoint_base_revision: str | None = None
    code_snapshot_id: str | None = None
    ua_snapshot_id: str | None = None
    observed_revision_id: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    lease_expires_at: str | None = None


class UaRunResult(BaseModel):
    """Small test/recovery representation of artifacts emitted by native UA."""

    model_config = ConfigDict(extra="forbid")
    knowledge_graph: dict[str, Any]
    domain_graph: dict[str, Any] | None = None
    files_reanalyzed: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
