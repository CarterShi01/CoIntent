from contexture.server import compile_application

from cointent.controller import app


def test_contexture_graph_exposes_required_mcp_capabilities(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COINTENT_DB_PATH", str(tmp_path / "model.db"))
    compiled = compile_application(app)
    refs = {ref for ref, node in compiled.index.walk() if node.kind == "tool"}

    assert "project-alignment/design-convergence/propose-model-patch" in refs
    assert "project-alignment/implementation-mapping/ingest-snapshot" in refs
    assert "project-alignment/alignment-review/list-findings" in refs
    assert "project-alignment/history/compare-versions" in refs
