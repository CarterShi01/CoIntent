"""Versioned product-function, responsibility, and implementation model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductFunction(ModelRecord):
    id: str
    name: str
    description: str = ""
    parent_id: str | None = None
    status: Literal["draft", "accepted", "questioned", "deferred"] = "accepted"
    priority: Literal["critical", "high", "medium", "low", "unset"] = "unset"
    acceptance: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class RoleObject(ModelRecord):
    id: str
    name: str
    purpose: str
    parent_id: str | None = None
    status: Literal["draft", "accepted", "questioned"] = "accepted"
    owns_knowledge: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class Responsibility(ModelRecord):
    id: str
    role_id: str
    statement: str
    function_ids: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_goal_ids(cls, data: Any) -> Any:
        if isinstance(data, dict) and "goal_ids" in data and "function_ids" not in data:
            data = dict(data)
            data["function_ids"] = data.pop("goal_ids")
        return data


class RoleRelation(ModelRecord):
    id: str
    source_role_id: str
    target_role_id: str
    kind: Literal["collaborates", "depends_on", "delegates_to", "exchanges_with", "governs"]
    label: str = ""


class FunctionRoleLink(ModelRecord):
    id: str
    function_id: str
    role_id: str
    kind: Literal["owns", "contributes", "governs"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: str = ""
    source_ids: list[str] = Field(default_factory=list)


class TraceLink(ModelRecord):
    id: str
    role_id: str
    artifact_path: str
    kind: Literal["realizes", "supports", "verifies", "stores", "presents"] = "realizes"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    origin: Literal["human", "agent", "scanner", "runtime"] = "agent"
    evidence: str = ""


class Goal(ModelRecord):
    """Legacy 0.1 input type retained for Python import compatibility."""

    id: str
    title: str
    description: str = ""
    parent_id: str | None = None
    status: Literal["open", "accepted", "deferred"] = "accepted"
    source_ids: list[str] = Field(default_factory=list)


class RoleRecord(ModelRecord):
    """Legacy 0.1 input type retained for Python import compatibility."""

    id: str
    name: str
    purpose: str
    parent_id: str | None = None
    status: Literal["draft", "accepted", "questioned"] = "accepted"
    source_ids: list[str] = Field(default_factory=list)


class Relation(ModelRecord):
    """Legacy 0.1 input type retained for Python import compatibility."""

    id: str
    source_role_id: str
    target_role_id: str
    kind: Literal["collaborates", "depends_on", "delegates_to", "exchanges_with"]
    label: str = ""


class ProjectModel(ModelRecord):
    schema_version: Literal["0.2"] = "0.2"
    project_id: str
    name: str
    summary: str = ""
    status: Literal["draft", "baseline"] = "draft"
    product_functions: list[ProductFunction] = Field(default_factory=list)
    role_objects: list[RoleObject] = Field(default_factory=list)
    responsibilities: list[Responsibility] = Field(default_factory=list)
    role_relations: list[RoleRelation] = Field(default_factory=list)
    function_role_links: list[FunctionRoleLink] = Field(default_factory=list)
    trace_links: list[TraceLink] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_model(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        legacy = any(key in migrated for key in ("goals", "roles", "relations"))
        if "product_functions" not in migrated and "goals" in migrated:
            migrated["product_functions"] = [
                {
                    "id": record["id"], "name": record.get("title", record["id"]),
                    "description": record.get("description", ""), "parent_id": record.get("parent_id"),
                    "status": "questioned" if record.get("status") == "open" else record.get("status", "accepted"),
                    "source_ids": record.get("source_ids", []),
                }
                for item in migrated.pop("goals")
                for record in [_record_dict(item)]
            ]
        if "role_objects" not in migrated and "roles" in migrated:
            migrated["role_objects"] = [_record_dict(item) for item in migrated.pop("roles")]
        if "role_relations" not in migrated and "relations" in migrated:
            migrated["role_relations"] = [_record_dict(item) for item in migrated.pop("relations")]
        if legacy:
            migrated["schema_version"] = "0.2"
        return migrated

    @model_validator(mode="after")
    def validate_graph(self) -> "ProjectModel":
        functions = _unique(self.product_functions, "product function")
        roles = _unique(self.role_objects, "role object")
        _unique(self.responsibilities, "responsibility")
        _unique(self.role_relations, "role relation")
        _unique(self.function_role_links, "function-role link")
        _unique(self.trace_links, "trace link")
        for item in self.product_functions:
            if item.parent_id is not None and item.parent_id not in functions:
                raise ValueError(f"product function {item.id!r} has unknown parent {item.parent_id!r}")
        _assert_acyclic(self.product_functions, "product function")
        for item in self.role_objects:
            if item.parent_id is not None and item.parent_id not in roles:
                raise ValueError(f"role object {item.id!r} has unknown parent {item.parent_id!r}")
        _assert_acyclic(self.role_objects, "role object")
        for item in self.responsibilities:
            if item.role_id not in roles:
                raise ValueError(f"responsibility {item.id!r} has unknown role {item.role_id!r}")
            unknown = set(item.function_ids) - functions
            if unknown:
                raise ValueError(f"responsibility {item.id!r} has unknown product functions {sorted(unknown)!r}")
        for item in self.role_relations:
            if item.source_role_id not in roles or item.target_role_id not in roles:
                raise ValueError(f"role relation {item.id!r} has an unknown role endpoint")
        for item in self.function_role_links:
            if item.function_id not in functions or item.role_id not in roles:
                raise ValueError(f"function-role link {item.id!r} has an unknown endpoint")
        for item in self.trace_links:
            if item.role_id not in roles:
                raise ValueError(f"trace link {item.id!r} has unknown role {item.role_id!r}")
            if not _safe_relative_path(item.artifact_path):
                raise ValueError(f"trace link {item.id!r} has an unsafe artifact path")
        return self

    @property
    def goals(self) -> list[ProductFunction]:
        return self.product_functions

    @property
    def roles(self) -> list[RoleObject]:
        return self.role_objects

    @property
    def relations(self) -> list[RoleRelation]:
        return self.role_relations


class ModelPatch(ModelRecord):
    name: str | None = None
    summary: str | None = None
    status: Literal["draft", "baseline"] | None = None
    upsert_product_functions: list[ProductFunction] = Field(default_factory=list)
    remove_product_function_ids: list[str] = Field(default_factory=list)
    upsert_role_objects: list[RoleObject] = Field(default_factory=list)
    remove_role_object_ids: list[str] = Field(default_factory=list)
    upsert_responsibilities: list[Responsibility] = Field(default_factory=list)
    remove_responsibility_ids: list[str] = Field(default_factory=list)
    upsert_role_relations: list[RoleRelation] = Field(default_factory=list)
    remove_role_relation_ids: list[str] = Field(default_factory=list)
    upsert_function_role_links: list[FunctionRoleLink] = Field(default_factory=list)
    remove_function_role_link_ids: list[str] = Field(default_factory=list)
    upsert_trace_links: list[TraceLink] = Field(default_factory=list)
    remove_trace_link_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_patch(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        aliases = {
            "upsert_goals": "upsert_product_functions", "remove_goal_ids": "remove_product_function_ids",
            "upsert_roles": "upsert_role_objects", "remove_role_ids": "remove_role_object_ids",
            "upsert_relations": "upsert_role_relations", "remove_relation_ids": "remove_role_relation_ids",
        }
        for old, new in aliases.items():
            if old in migrated and new not in migrated:
                value = migrated.pop(old)
                if old == "upsert_goals":
                    value = [
                        {
                            "id": record["id"], "name": record.get("title", record["id"]),
                            "description": record.get("description", ""), "parent_id": record.get("parent_id"),
                            "status": "questioned" if record.get("status") == "open" else record.get("status", "accepted"),
                            "source_ids": record.get("source_ids", []),
                        }
                        for item in value
                        for record in [_record_dict(item)]
                    ]
                elif old in {"upsert_roles", "upsert_relations"}:
                    value = [_record_dict(item) for item in value]
                migrated[new] = value
        return migrated


def apply_model_patch(model: ProjectModel, patch: ModelPatch) -> ProjectModel:
    data = model.model_dump()
    if patch.name is not None:
        data["name"] = patch.name
    if patch.summary is not None:
        data["summary"] = patch.summary
    if patch.status is not None:
        data["status"] = patch.status
    for field, upserts, removals in (
        ("product_functions", patch.upsert_product_functions, patch.remove_product_function_ids),
        ("role_objects", patch.upsert_role_objects, patch.remove_role_object_ids),
        ("responsibilities", patch.upsert_responsibilities, patch.remove_responsibility_ids),
        ("role_relations", patch.upsert_role_relations, patch.remove_role_relation_ids),
        ("function_role_links", patch.upsert_function_role_links, patch.remove_function_role_link_ids),
        ("trace_links", patch.upsert_trace_links, patch.remove_trace_link_ids),
    ):
        indexed = {item["id"]: item for item in data[field] if item["id"] not in removals}
        for item in upserts:
            indexed[item.id] = item.model_dump()
        data[field] = list(indexed.values())
    return ProjectModel.model_validate(data)


def semantic_diff(before: ProjectModel, after: ProjectModel) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in (
        "product_functions", "role_objects", "responsibilities", "role_relations",
        "function_role_links", "trace_links",
    ):
        left = {item.id: item.model_dump() for item in getattr(before, field)}
        right = {item.id: item.model_dump() for item in getattr(after, field)}
        result[field] = {
            "added": sorted(right.keys() - left.keys()),
            "removed": sorted(left.keys() - right.keys()),
            "changed": sorted(key for key in left.keys() & right.keys() if left[key] != right[key]),
        }
    result["name_changed"] = before.name != after.name
    result["summary_changed"] = before.summary != after.summary
    result["status_changed"] = before.status != after.status
    return result


def _unique(items: list[Any], label: str) -> set[str]:
    identifiers = [item.id for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"duplicate {label} id")
    return set(identifiers)


def _assert_acyclic(items: list[Any], label: str) -> None:
    parents = {item.id: item.parent_id for item in items}
    for identifier in parents:
        seen: set[str] = set()
        cursor: str | None = identifier
        while cursor is not None:
            if cursor in seen:
                raise ValueError(f"{label} hierarchy contains a cycle at {cursor!r}")
            seen.add(cursor)
            cursor = parents.get(cursor)


def _safe_relative_path(value: str) -> bool:
    return bool(value) and not value.startswith(("/", "~")) and ".." not in value.split("/")


def _record_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    raise TypeError(f"expected a model record, got {type(value).__name__}")
