from contexture.server import compile_application

from cointent.controller import app, legacy_app


def test_contexture_graph_exposes_compact_on_demand_product_surface(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COINTENT_DB_PATH", str(tmp_path / "model.db"))
    compiled = compile_application(app)
    refs = {ref for ref, node in compiled.index.walk() if node.kind == "tool"}
    skill_refs = {ref for ref, node in compiled.index.walk() if node.kind == "skill"}

    assert refs == {
        "cointent/project-context/list-projects",
        "cointent/project-context/inspect-project-state",
        "cointent/understand-current/refresh-current-understanding",
        "cointent/understand-current/inspect-understanding-refresh",
        "cointent/understand-current/read-current-level",
        "cointent/design-future/start-structure-design",
        "cointent/design-future/read-design-level",
        "cointent/design-future/revise-structure-design",
        "cointent/design-future/diff-structure-design",
        "cointent/design-future/create-implementation-context",
        "cointent/design-future/list-structure-design-versions",
        "cointent/design-future/compare-design-to-current",
    }
    assert skill_refs == {
        "cointent/understand-current/learn-current-system",
        "cointent/design-future/design-structure-first",
    }
    assert not any(
        value in ref for ref in refs
        for value in ("understand-anything", "ua-dashboard", "ingest", "publish", "replace-observed")
    )

    understanding = compiled.server().surface.tree.open("cointent/understand-current")
    schemas = {tool["name"]: tool["input_schema"] for tool in understanding["tools"]}
    assert set(schemas["read-current-level"]["properties"]) == {
        "project_id", "focus_id", "observed_revision_id",
    }
    assert set(schemas["refresh-current-understanding"]["properties"]) == {"project_id"}

    design = compiled.server().surface.tree.open("cointent/design-future")
    revise_schema = {tool["name"]: tool["input_schema"] for tool in design["tools"]}["revise-structure-design"]
    operation_ref = revise_schema["properties"]["operations"]["items"]["$ref"]
    operation = revise_schema["$defs"][operation_ref.rsplit("/", 1)[-1]]
    assert "set_acceptance_criteria" in operation["properties"]["kind"]["enum"]
    assert operation["additionalProperties"] is False


def test_legacy_declaration_remains_available_only_for_http_compatibility(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COINTENT_DB_PATH", str(tmp_path / "model.db"))
    compiled = compile_application(legacy_app)
    refs = {ref for ref, node in compiled.index.walk() if node.kind == "tool"}
    assert "cointent/current-understanding/request-observation-expansion" in refs
    assert "cointent/target-design/create-target-design-workspace" in refs
    assert not any("import-understand-anything" in ref or "replace-observed" in ref for ref in refs)
