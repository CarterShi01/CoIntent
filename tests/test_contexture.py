from contexture.server import compile_application

from cointent.controller import app


def test_contexture_graph_exposes_v03_agent_capabilities(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COINTENT_DB_PATH", str(tmp_path / "model.db"))
    compiled = compile_application(app)
    refs = {ref for ref, node in compiled.index.walk() if node.kind == "tool"}
    skill_refs = {ref for ref, node in compiled.index.walk() if node.kind == "skill"}

    assert {
        "cointent/project-management/list-projects",
        "cointent/project-management/list-design-versions",
        "cointent/current-understanding/inspect-observation-coordinate",
        "cointent/current-understanding/list-observed-revisions",
        "cointent/current-understanding/inspect-observed-revision",
        "cointent/current-understanding/request-observation-expansion",
        "cointent/target-design/list-target-design-workspaces",
        "cointent/target-design/inspect-target-design-workspace",
        "cointent/target-design/create-target-design-workspace",
        "cointent/target-design/apply-target-design-operations",
        "cointent/target-design/list-target-design-operations",
        "cointent/target-design/compare-implementation-to-target",
        "cointent/target-design/inspect-verification-report",
        "cointent/specification/inspect-specification-tree",
        "cointent/responsibility-model/propose-design-patch",
        "cointent/responsibility-model/inspect-responsibility",
        "cointent/responsibility-model/trace-responsibility-workflow",
        "cointent/implementation-alignment/ingest-code-snapshot",
        "cointent/implementation-alignment/record-mapping-revision",
        "cointent/implementation-alignment/compare-design-to-code",
        "cointent/change-lifecycle/generate-implementation-brief",
        "cointent/history-and-portability/export-design-version",
    } <= refs
    assert not any("import-understand-anything" in ref or "replace-observed" in ref for ref in refs)
    assert not any(
        value in refs for value in {
            "cointent/target-design/approve-target-design",
            "cointent/target-design/export-implementation-bundle",
            "cointent/target-design/decide-verification",
        }
    )
    understanding = compiled.server().surface.tree.open("cointent/current-understanding")
    expansion_schema = {
        tool["name"]: tool["input_schema"] for tool in understanding["tools"]
    }["request-observation-expansion"]
    assert set(expansion_schema["properties"]) == {
        "project_id", "observed_revision_id", "node_id", "depth",
    }
    assert {
        "cointent/responsibility-model/model-responsibilities",
        "cointent/responsibility-model/review-responsibility-model",
        "cointent/implementation-alignment/map-backend-implementation",
        "cointent/change-lifecycle/close-alignment-loop",
    } <= skill_refs

    opened = compiled.server().surface.tree.open("cointent/responsibility-model")
    schemas = {tool["name"]: tool["input_schema"] for tool in opened["tools"]}
    patch_schema = schemas["propose-design-patch"]
    patch_ref = patch_schema["properties"]["patch"]["$ref"]
    model_patch = patch_schema["$defs"][patch_ref.rsplit("/", 1)[-1]]
    assert "upsert_responsibilities" in model_patch["properties"]
    assert "upsert_implementation_links" in model_patch["properties"]
    assert "upsert_specification_items" in model_patch["properties"]
    assert model_patch["additionalProperties"] is False

    implementation = compiled.server().surface.tree.open("cointent/implementation-alignment")
    snapshot_schema = {tool["name"]: tool["input_schema"] for tool in implementation["tools"]}["ingest-code-snapshot"]
    snapshot_ref = snapshot_schema["properties"]["snapshot"]["$ref"]
    assert "artifacts" in snapshot_schema["$defs"][snapshot_ref.rsplit("/", 1)[-1]]["properties"]
