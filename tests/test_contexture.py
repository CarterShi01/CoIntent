from contexture.server import compile_application

from cointent.controller import app


def test_contexture_graph_exposes_required_mcp_capabilities(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COINTENT_DB_PATH", str(tmp_path / "model.db"))
    compiled = compile_application(app)
    refs = {ref for ref, node in compiled.index.walk() if node.kind == "tool"}
    skill_refs = {ref for ref, node in compiled.index.walk() if node.kind == "skill"}

    assert "project-alignment/design-convergence/propose-model-patch" in refs
    assert "project-alignment/design-convergence/assess-model-quality" in refs
    assert "project-alignment/implementation-mapping/ingest-snapshot" in refs
    assert "project-alignment/alignment-review/list-findings" in refs
    assert "project-alignment/history/compare-versions" in refs
    assert "project-alignment/design-convergence/review-role-model" in skill_refs

    opened = compiled.server().surface.tree.open("project-alignment/design-convergence")
    schemas = {tool["name"]: tool["input_schema"] for tool in opened["tools"]}
    patch_schema = schemas["propose-model-patch"]
    patch_ref = patch_schema["properties"]["patch"]["$ref"]
    model_patch = patch_schema["$defs"][patch_ref.rsplit("/", 1)[-1]]
    assert "upsert_responsibilities" in model_patch["properties"]
    assert model_patch["additionalProperties"] is False
