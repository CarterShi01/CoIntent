from pathlib import Path

import pytest
from pydantic import ValidationError

from cointent.observation import UAKnowledgeGraph, build_ua_snapshot, project_observed_model
from cointent.repository import CoIntentRepository
from cointent.scanner import Artifact, RepositorySnapshot


REVISION = "a" * 40
FIXTURES = Path(__file__).parent / "fixtures" / "ua"


def code_snapshot(*, scope: str = "full", revision: str = REVISION) -> RepositorySnapshot:
    return RepositorySnapshot(
        id="snapshot-full", project_id="demo", repository="demo", revision=revision,
        branch="main", dirty=False, scope=scope, captured_at="2026-09-09T00:00:00+00:00",
        artifacts=[
            Artifact(path="src/orders.py", kind="source", language="Python",
                     component="src/orders.py", sha256="1" * 64, size=100),
            Artifact(path="web/src/App.tsx", kind="source", language="TypeScript",
                     component="web", sha256="2" * 64, size=100),
        ],
    )


def graph(nodes: list[dict], edges: list[dict], *, commit: str = REVISION) -> dict:
    return {
        "version": "1.2.0", "kind": "codebase",
        "project": {
            "name": "Demo", "languages": ["Python", "TypeScript"], "frameworks": [],
            "description": "Demo", "analyzedAt": "2026-09-09T00:00:00Z", "gitCommitHash": commit,
        },
        "nodes": nodes, "edges": edges, "layers": [], "tour": [],
    }


def native_artifacts() -> tuple[dict, dict]:
    knowledge = graph(
        nodes=[
            {"id": "file:orders", "type": "file", "name": "orders.py",
             "filePath": "src/orders.py", "lineRange": [1, 20]},
            {"id": "fn:create", "type": "function", "name": "create_order",
             "filePath": "src/orders.py", "lineRange": [2, 10]},
        ],
        edges=[{"source": "file:orders", "target": "fn:create", "type": "contains",
                "direction": "forward", "weight": 1}],
    )
    domain = graph(
        nodes=[
            {"id": "domain:orders", "type": "domain", "name": "Orders", "summary": "Own orders"},
            {"id": "flow:create", "type": "flow", "name": "Create order", "summary": "Accept an order"},
            {"id": "step:validate", "type": "step", "name": "Validate", "summary": "Validate input",
             "filePath": "src/orders.py", "lineRange": [2, 4]},
            {"id": "step:save", "type": "step", "name": "Save", "summary": "Persist order",
             "filePath": "src/orders.py", "lineRange": [5, 9]},
            {"id": "flow:unsupported", "type": "flow", "name": "Imagined flow", "summary": "No evidence"},
        ],
        edges=[
            {"source": "domain:orders", "target": "flow:create", "type": "contains_flow",
             "direction": "forward", "weight": 1},
            {"source": "flow:create", "target": "step:validate", "type": "flow_step",
             "direction": "forward", "weight": 0.1},
            {"source": "flow:create", "target": "step:save", "type": "flow_step",
             "direction": "forward", "weight": 0.2},
            {"source": "domain:orders", "target": "flow:unsupported", "type": "contains_flow",
             "direction": "forward", "weight": 1},
        ],
    )
    return knowledge, domain


def test_ua_projection_publishes_only_evidence_backed_semantics() -> None:
    knowledge, domain = native_artifacts()
    code = code_snapshot()
    imported = build_ua_snapshot(
        project_id="demo", code_snapshot=code, ua_tool_revision="ua-pin-123",
        knowledge_graph=UAKnowledgeGraph.model_validate(knowledge),
        domain_graph=UAKnowledgeGraph.model_validate(domain),
        created_at="2026-09-09T01:00:00+00:00",
    )
    observed = project_observed_model(imported, code, created_at="2026-09-09T01:00:00+00:00")

    by_native = {item.source_ids[0]: item for item in observed.responsibilities}
    evidence_by_responsibility = {
        item.subject_id: item.evidence for item in observed.bindings
        if item.subject_kind == "responsibility"
    }
    assert set(by_native) == {"domain:orders", "flow:create", "step:validate", "step:save"}
    assert len(evidence_by_responsibility[by_native["domain:orders"].id]) == 2
    assert evidence_by_responsibility[by_native["step:validate"].id][0].structural_ua_node_ids == ["file:orders", "fn:create"]
    assert [item.name for item in observed.capabilities] == ["Create order"]
    assert any(edge.kind == "next" for edge in by_native["flow:create"].workflow.edges)
    assert any(item.subject_id == "flow:unsupported" for item in observed.diagnostics)
    assert set(evidence_by_responsibility) == {item.id for item in observed.responsibilities}


def test_ua_import_rejects_wrong_scope_commit_and_path() -> None:
    knowledge, domain = native_artifacts()
    with pytest.raises(ValueError, match="full code snapshot"):
        build_ua_snapshot(
            project_id="demo", code_snapshot=code_snapshot(scope="backend"), ua_tool_revision="pin",
            knowledge_graph=UAKnowledgeGraph.model_validate(knowledge),
        )

    with pytest.raises(ValueError, match="gitCommitHash"):
        build_ua_snapshot(
            project_id="demo", code_snapshot=code_snapshot(revision="b" * 40), ua_tool_revision="pin",
            knowledge_graph=UAKnowledgeGraph.model_validate(knowledge),
        )

    domain["nodes"][2]["filePath"] = "src/missing.py"
    with pytest.raises(ValueError, match="absent from code snapshot"):
        build_ua_snapshot(
            project_id="demo", code_snapshot=code_snapshot(), ua_tool_revision="pin",
            knowledge_graph=UAKnowledgeGraph.model_validate(knowledge),
            domain_graph=UAKnowledgeGraph.model_validate(domain),
        )


def test_ua_native_validation_fails_closed() -> None:
    duplicate = graph(
        [{"id": "same", "type": "file", "name": "A"},
         {"id": "same", "type": "file", "name": "B"}], [],
    )
    with pytest.raises(ValidationError, match="duplicate node IDs"):
        UAKnowledgeGraph.model_validate(duplicate)

    dangling = graph(
        [{"id": "known", "type": "file", "name": "A"}],
        [{"source": "known", "target": "missing", "type": "contains",
          "direction": "forward", "weight": 1}],
    )
    with pytest.raises(ValidationError, match="dangling endpoint"):
        UAKnowledgeGraph.model_validate(dangling)

    unsafe = graph(
        [{"id": "unsafe", "type": "file", "name": "A", "filePath": "../secret"}], [],
    )
    with pytest.raises(ValidationError, match="unsafe filePath"):
        UAKnowledgeGraph.model_validate(unsafe)


def test_pinned_ua_json_fixtures_match_the_import_contract() -> None:
    for name in ("knowledge-graph.json", "domain-graph.json"):
        parsed = UAKnowledgeGraph.model_validate_json((FIXTURES / name).read_text(encoding="utf-8"))
        assert parsed.version == "1.0.0"


def test_repository_import_is_idempotent_and_observation_is_read_only(tmp_path: Path) -> None:
    repository = CoIntentRepository(tmp_path / "model.db")
    repository.create_project("demo", "Demo")
    repository.ingest_snapshot("demo", code_snapshot().model_dump())
    knowledge, domain = native_artifacts()

    first = repository.import_understand_anything(
        "demo", "snapshot-full", "ua-pin-123", knowledge, domain,
    )
    second = repository.import_understand_anything(
        "demo", "snapshot-full", "ua-pin-123", knowledge, domain,
    )

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert first["ua_snapshot"]["id"] == second["ua_snapshot"]["id"]
    assert first["observed_revision"]["id"] == second["observed_revision"]["id"]
    assert repository.observation_coordinate("demo")["status"] == "current"
    assert len(repository.list_observed_revisions("demo")) == 1
    assert not hasattr(repository, "replace_observed_revision")
    assert (tmp_path / "projects/demo/understand-anything" / f"{first['ua_snapshot']['id']}.json").is_file()
    assert (tmp_path / "projects/demo/observed" / f"{first['observed_revision']['id']}.json").is_file()

    target = first["observed_revision"]["capabilities"][0]["responsibility_id"]
    expansion = repository.request_observation_expansion(
        "demo", first["observed_revision"]["id"], target, depth=1,
    )
    repeated = repository.request_observation_expansion(
        "demo", first["observed_revision"]["id"], target, depth=1,
    )
    assert expansion["duplicate"] is False
    assert repeated["duplicate"] is True
    assert expansion["request"]["status"] == "queued"
    assert expansion["request"]["evidence_scope"]
    assert "nodes" not in expansion["request"] and "edges" not in expansion["request"]

    with pytest.raises(ValueError, match="not part of"):
        repository.request_observation_expansion(
            "demo", first["observed_revision"]["id"], "obs-node-not-real", depth=1,
        )
    with pytest.raises(ValueError, match="between 1 and 3"):
        repository.request_observation_expansion(
            "demo", first["observed_revision"]["id"], target, depth=4,
        )
