"""CoIntent 0.3 recursive Responsibility and Workflow model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpecificationItem(ModelRecord):
    """Plain-language, implementation-independent product meaning."""

    id: str
    name: str
    description: str = ""
    parent_id: str | None = None
    status: Literal["draft", "accepted", "questioned", "deferred"] = "accepted"
    source_ids: list[str] = Field(default_factory=list)


class WorkflowNode(ModelRecord):
    """One occurrence of a Responsibility inside a Workflow."""

    id: str
    responsibility_id: str
    note: str = ""


class WorkflowEdge(ModelRecord):
    id: str
    source_node_id: str
    target_node_id: str
    kind: Literal["next", "condition", "parallel", "event", "error"] = "next"
    label: str = ""


class Workflow(ModelRecord):
    entry_node_ids: list[str] = Field(default_factory=list)
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_local_graph(self) -> "Workflow":
        node_ids = _unique(self.nodes, "workflow node")
        _unique(self.edges, "workflow edge")
        unknown_entries = set(self.entry_node_ids) - node_ids
        if unknown_entries:
            raise ValueError(f"workflow has unknown entry nodes {sorted(unknown_entries)!r}")
        for edge in self.edges:
            if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids:
                raise ValueError(f"workflow edge {edge.id!r} has an unknown node endpoint")
        if self.nodes and not self.entry_node_ids:
            raise ValueError("non-empty workflow requires at least one entry node")
        return self


class Responsibility(ModelRecord):
    """A semantic object that owns one coherent program responsibility."""

    id: str
    name: str
    description: str = ""
    data_members: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    workflow: Workflow | None = None
    status: Literal["draft", "accepted", "questioned"] = "accepted"
    source_ids: list[str] = Field(default_factory=list)


class SpecificationResponsibilityLink(ModelRecord):
    id: str
    specification_id: str
    responsibility_id: str
    kind: Literal["realizes", "contributes"] = "realizes"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: str = ""
    source_ids: list[str] = Field(default_factory=list)


class ImplementationLink(ModelRecord):
    id: str
    responsibility_id: str
    artifact_path: str
    symbol: str = ""
    kind: Literal["realizes", "supports", "verifies", "stores"] = "realizes"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    origin: Literal["human", "agent", "scanner", "runtime"] = "agent"
    evidence: str = ""


class ProjectModel(ModelRecord):
    schema_version: Literal["0.3"] = "0.3"
    project_id: str
    name: str
    summary: str = ""
    status: Literal["draft", "baseline"] = "draft"
    specification_items: list[SpecificationItem] = Field(default_factory=list)
    responsibilities: list[Responsibility] = Field(default_factory=list)
    specification_responsibility_links: list[SpecificationResponsibilityLink] = Field(default_factory=list)
    implementation_links: list[ImplementationLink] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_v02(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if data.get("schema_version") == "0.3" and "role_objects" not in data:
            return data

        migrated = dict(data)
        old_functions = [_record_dict(item) for item in migrated.get("product_functions", migrated.get("goals", []))]
        old_roles = [_record_dict(item) for item in migrated.get("role_objects", migrated.get("roles", []))]
        old_responsibilities = [_record_dict(item) for item in migrated.get("responsibilities", [])]
        old_function_links = [_record_dict(item) for item in migrated.get("function_role_links", [])]
        old_trace_links = [_record_dict(item) for item in migrated.get("trace_links", [])]

        if old_functions and "specification_items" not in migrated:
            migrated["specification_items"] = [
                {
                    "id": item["id"],
                    "name": item.get("name", item.get("title", item["id"])),
                    "description": item.get("description", ""),
                    "parent_id": item.get("parent_id"),
                    "status": "questioned" if item.get("status") == "open" else item.get("status", "accepted"),
                    "source_ids": item.get("source_ids", []),
                }
                for item in old_functions
            ]

        if old_roles:
            statements: dict[str, list[str]] = {}
            for item in old_responsibilities:
                statements.setdefault(item.get("role_id", ""), []).append(item.get("statement", ""))
            children: dict[str, list[dict[str, Any]]] = {}
            for role in old_roles:
                if role.get("parent_id"):
                    children.setdefault(role["parent_id"], []).append(role)
            converted: list[dict[str, Any]] = []
            for role in old_roles:
                child_roles = children.get(role["id"], [])
                nodes = [
                    {"id": f"node.{role['id']}.{child['id']}", "responsibility_id": child["id"]}
                    for child in child_roles
                ]
                edges = [
                    {
                        "id": f"edge.{role['id']}.{index}",
                        "source_node_id": nodes[index]["id"],
                        "target_node_id": nodes[index + 1]["id"],
                        "kind": "next",
                    }
                    for index in range(max(0, len(nodes) - 1))
                ]
                detail = " ".join(value for value in statements.get(role["id"], []) if value)
                converted.append({
                    "id": role["id"],
                    "name": role.get("name", role["id"]),
                    "description": detail or role.get("purpose", ""),
                    "data_members": role.get("owns_knowledge", []),
                    "inputs": role.get("inputs", []),
                    "outputs": role.get("outputs", []),
                    "workflow": None if not nodes else {
                        "entry_node_ids": [nodes[0]["id"]], "nodes": nodes, "edges": edges,
                    },
                    "status": role.get("status", "accepted"),
                    "source_ids": role.get("source_ids", []),
                })
            migrated["responsibilities"] = converted

        if old_function_links and "specification_responsibility_links" not in migrated:
            migrated["specification_responsibility_links"] = [
                {
                    "id": item["id"],
                    "specification_id": item.get("function_id"),
                    "responsibility_id": item.get("role_id"),
                    "kind": "contributes" if item.get("kind") == "contributes" else "realizes",
                    "confidence": item.get("confidence", 1.0),
                    "evidence": item.get("evidence", ""),
                    "source_ids": item.get("source_ids", []),
                }
                for item in old_function_links
            ]

        if old_trace_links and "implementation_links" not in migrated:
            migrated["implementation_links"] = [
                {
                    "id": item["id"],
                    "responsibility_id": item.get("role_id"),
                    "artifact_path": item.get("artifact_path", ""),
                    "kind": item.get("kind") if item.get("kind") in {"realizes", "supports", "verifies", "stores"} else "supports",
                    "confidence": item.get("confidence", 1.0),
                    "origin": item.get("origin", "agent"),
                    "evidence": item.get("evidence", ""),
                }
                for item in old_trace_links
            ]

        for key in (
            "product_functions", "goals", "role_objects", "roles", "role_relations", "relations",
            "function_role_links", "trace_links",
        ):
            migrated.pop(key, None)
        migrated["schema_version"] = "0.3"
        migrated.setdefault("specification_items", [])
        migrated.setdefault("responsibilities", [])
        migrated.setdefault("specification_responsibility_links", [])
        migrated.setdefault("implementation_links", [])
        return migrated

    @model_validator(mode="after")
    def validate_model(self) -> "ProjectModel":
        specifications = _unique(self.specification_items, "specification item")
        responsibilities = _unique(self.responsibilities, "responsibility")
        _unique(self.specification_responsibility_links, "specification-responsibility link")
        _unique(self.implementation_links, "implementation link")

        for item in self.specification_items:
            if item.parent_id is not None and item.parent_id not in specifications:
                raise ValueError(f"specification item {item.id!r} has unknown parent {item.parent_id!r}")
        _assert_acyclic(self.specification_items, "specification item")

        for responsibility in self.responsibilities:
            if responsibility.workflow is None:
                continue
            for node in responsibility.workflow.nodes:
                if node.responsibility_id not in responsibilities:
                    raise ValueError(
                        f"workflow node {node.id!r} has unknown responsibility {node.responsibility_id!r}"
                    )

        for item in self.specification_responsibility_links:
            if item.specification_id not in specifications or item.responsibility_id not in responsibilities:
                raise ValueError(f"specification-responsibility link {item.id!r} has an unknown endpoint")

        for item in self.implementation_links:
            if item.responsibility_id not in responsibilities:
                raise ValueError(f"implementation link {item.id!r} has unknown responsibility")
            if not _safe_relative_path(item.artifact_path):
                raise ValueError(f"implementation link {item.id!r} has an unsafe artifact path")
        return self


class ModelPatch(ModelRecord):
    name: str | None = None
    summary: str | None = None
    status: Literal["draft", "baseline"] | None = None
    upsert_specification_items: list[SpecificationItem] = Field(default_factory=list)
    remove_specification_item_ids: list[str] = Field(default_factory=list)
    upsert_responsibilities: list[Responsibility] = Field(default_factory=list)
    remove_responsibility_ids: list[str] = Field(default_factory=list)
    upsert_specification_responsibility_links: list[SpecificationResponsibilityLink] = Field(default_factory=list)
    remove_specification_responsibility_link_ids: list[str] = Field(default_factory=list)
    upsert_implementation_links: list[ImplementationLink] = Field(default_factory=list)
    remove_implementation_link_ids: list[str] = Field(default_factory=list)


def apply_model_patch(model: ProjectModel, patch: ModelPatch) -> ProjectModel:
    data = model.model_dump()
    if patch.name is not None:
        data["name"] = patch.name
    if patch.summary is not None:
        data["summary"] = patch.summary
    if patch.status is not None:
        data["status"] = patch.status
    for field, upserts, removals in (
        ("specification_items", patch.upsert_specification_items, patch.remove_specification_item_ids),
        ("responsibilities", patch.upsert_responsibilities, patch.remove_responsibility_ids),
        (
            "specification_responsibility_links", patch.upsert_specification_responsibility_links,
            patch.remove_specification_responsibility_link_ids,
        ),
        ("implementation_links", patch.upsert_implementation_links, patch.remove_implementation_link_ids),
    ):
        indexed = {item["id"]: item for item in data[field] if item["id"] not in removals}
        for item in upserts:
            indexed[item.id] = item.model_dump()
        data[field] = list(indexed.values())
    return ProjectModel.model_validate(data)


def semantic_diff(before: ProjectModel, after: ProjectModel) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in (
        "specification_items", "responsibilities", "specification_responsibility_links", "implementation_links",
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
