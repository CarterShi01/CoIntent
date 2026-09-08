from contexture.server import compile_application

from cointent.controller import app


def test_contexture_graph_exposes_v02_agent_capabilities(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COINTENT_DB_PATH", str(tmp_path / "model.db"))
    compiled = compile_application(app)
    refs = {ref for ref, node in compiled.index.walk() if node.kind == "tool"}
    skill_refs = {ref for ref, node in compiled.index.walk() if node.kind == "skill"}

    assert {
        "cointent/project-management/list-projects",
        "cointent/project-management/list-design-versions",
        "cointent/product-design/propose-design-patch",
        "cointent/product-design/inspect-product-function",
        "cointent/responsibility-design/inspect-role-object",
        "cointent/implementation-alignment/ingest-code-snapshot",
        "cointent/implementation-alignment/record-mapping-revision",
        "cointent/implementation-alignment/compare-design-to-code",
        "cointent/change-lifecycle/generate-implementation-brief",
        "cointent/history-and-portability/export-design-version",
    } <= refs
    assert {
        "cointent/product-design/refine-product-functions",
        "cointent/product-design/review-design",
        "cointent/responsibility-design/decompose-responsibilities",
        "cointent/implementation-alignment/map-implementation",
        "cointent/change-lifecycle/close-alignment-loop",
    } <= skill_refs

    opened = compiled.server().surface.tree.open("cointent/product-design")
    schemas = {tool["name"]: tool["input_schema"] for tool in opened["tools"]}
    patch_schema = schemas["propose-design-patch"]
    patch_ref = patch_schema["properties"]["patch"]["$ref"]
    model_patch = patch_schema["$defs"][patch_ref.rsplit("/", 1)[-1]]
    assert "upsert_product_functions" in model_patch["properties"]
    assert "upsert_function_role_links" in model_patch["properties"]
    assert model_patch["additionalProperties"] is False

    implementation = compiled.server().surface.tree.open("cointent/implementation-alignment")
    snapshot_schema = {tool["name"]: tool["input_schema"] for tool in implementation["tools"]}["ingest-code-snapshot"]
    snapshot_ref = snapshot_schema["properties"]["snapshot"]["$ref"]
    assert "artifacts" in snapshot_schema["$defs"][snapshot_ref.rsplit("/", 1)[-1]]["properties"]
