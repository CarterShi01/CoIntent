"""Versioned intent, responsibility, and implementation model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Goal(ModelRecord):
    id: str
    title: str
    description: str = ""
    parent_id: str | None = None
    status: Literal["open", "accepted", "deferred"] = "accepted"
    source_ids: list[str] = Field(default_factory=list)


class RoleRecord(ModelRecord):
    id: str
    name: str
    purpose: str
    parent_id: str | None = None
    status: Literal["draft", "accepted", "questioned"] = "accepted"
    source_ids: list[str] = Field(default_factory=list)


class Responsibility(ModelRecord):
    id: str
    role_id: str
    statement: str
    goal_ids: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class Relation(ModelRecord):
    id: str
    source_role_id: str
    target_role_id: str
    kind: Literal["collaborates", "depends_on", "delegates_to", "exchanges_with"]
    label: str = ""


class TraceLink(ModelRecord):
    id: str
    role_id: str
    artifact_path: str
    kind: Literal["realizes", "supports", "verifies", "stores", "presents"] = "realizes"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    origin: Literal["human", "agent", "scanner", "runtime"] = "agent"
    evidence: str = ""


class ProjectModel(ModelRecord):
    schema_version: str = "0.1"
    project_id: str
    name: str
    summary: str = ""
    status: Literal["draft", "baseline"] = "draft"
    goals: list[Goal] = Field(default_factory=list)
    roles: list[RoleRecord] = Field(default_factory=list)
    responsibilities: list[Responsibility] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    trace_links: list[TraceLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> "ProjectModel":
        goals = _unique(self.goals, "goal")
        roles = _unique(self.roles, "role")
        _unique(self.responsibilities, "responsibility")
        _unique(self.relations, "relation")
        _unique(self.trace_links, "trace link")

        for goal in self.goals:
            if goal.parent_id is not None and goal.parent_id not in goals:
                raise ValueError(f"goal {goal.id!r} has unknown parent {goal.parent_id!r}")
            if goal.parent_id == goal.id:
                raise ValueError(f"goal {goal.id!r} cannot contain itself")
        for role in self.roles:
            if role.parent_id is not None and role.parent_id not in roles:
                raise ValueError(f"role {role.id!r} has unknown parent {role.parent_id!r}")
            if role.parent_id == role.id:
                raise ValueError(f"role {role.id!r} cannot contain itself")
        for item in self.responsibilities:
            if item.role_id not in roles:
                raise ValueError(f"responsibility {item.id!r} has unknown role {item.role_id!r}")
            unknown = set(item.goal_ids) - goals
            if unknown:
                raise ValueError(f"responsibility {item.id!r} has unknown goals {sorted(unknown)!r}")
        for relation in self.relations:
            if relation.source_role_id not in roles or relation.target_role_id not in roles:
                raise ValueError(f"relation {relation.id!r} has an unknown role endpoint")
        for link in self.trace_links:
            if link.role_id not in roles:
                raise ValueError(f"trace link {link.id!r} has unknown role {link.role_id!r}")
            if not _safe_relative_path(link.artifact_path):
                raise ValueError(f"trace link {link.id!r} has an unsafe artifact path")
        return self


class ModelPatch(ModelRecord):
    summary: str | None = None
    status: Literal["draft", "baseline"] | None = None
    upsert_goals: list[Goal] = Field(default_factory=list)
    remove_goal_ids: list[str] = Field(default_factory=list)
    upsert_roles: list[RoleRecord] = Field(default_factory=list)
    remove_role_ids: list[str] = Field(default_factory=list)
    upsert_responsibilities: list[Responsibility] = Field(default_factory=list)
    remove_responsibility_ids: list[str] = Field(default_factory=list)
    upsert_relations: list[Relation] = Field(default_factory=list)
    remove_relation_ids: list[str] = Field(default_factory=list)
    upsert_trace_links: list[TraceLink] = Field(default_factory=list)
    remove_trace_link_ids: list[str] = Field(default_factory=list)


def apply_model_patch(model: ProjectModel, patch: ModelPatch) -> ProjectModel:
    data = model.model_dump()
    if patch.summary is not None:
        data["summary"] = patch.summary
    if patch.status is not None:
        data["status"] = patch.status
    for field, upserts, removals in (
        ("goals", patch.upsert_goals, patch.remove_goal_ids),
        ("roles", patch.upsert_roles, patch.remove_role_ids),
        ("responsibilities", patch.upsert_responsibilities, patch.remove_responsibility_ids),
        ("relations", patch.upsert_relations, patch.remove_relation_ids),
        ("trace_links", patch.upsert_trace_links, patch.remove_trace_link_ids),
    ):
        indexed = {item["id"]: item for item in data[field] if item["id"] not in removals}
        for item in upserts:
            indexed[item.id] = item.model_dump()
        data[field] = list(indexed.values())
    return ProjectModel.model_validate(data)


def semantic_diff(before: ProjectModel, after: ProjectModel) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in ("goals", "roles", "responsibilities", "relations", "trace_links"):
        left = {item.id: item.model_dump() for item in getattr(before, field)}
        right = {item.id: item.model_dump() for item in getattr(after, field)}
        result[field] = {
            "added": sorted(right.keys() - left.keys()),
            "removed": sorted(left.keys() - right.keys()),
            "changed": sorted(key for key in left.keys() & right.keys() if left[key] != right[key]),
        }
    result["summary_changed"] = before.summary != after.summary
    result["status_changed"] = before.status != after.status
    return result


def _unique(items: list[Any], label: str) -> set[str]:
    identifiers = [item.id for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"duplicate {label} id")
    return set(identifiers)


def _safe_relative_path(value: str) -> bool:
    return bool(value) and not value.startswith(("/", "~")) and ".." not in value.split("/")
