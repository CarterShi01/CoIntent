from pathlib import Path

from starlette.testclient import TestClient

from cointent.app import build_http_app
from cointent.repository import CoIntentRepository


def test_rest_surface_uses_contexture_runtime(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "model.db"
    CoIntentRepository(database).create_project("idea-factory", "Idea Factory")
    monkeypatch.setenv("COINTENT_DB_PATH", str(database))

    with TestClient(build_http_app(), base_url="http://127.0.0.1") as client:
        health = client.get("/api/health")
        model = client.get("/api/v1/model?project_id=idea-factory")

    assert health.status_code == 200
    assert health.json() == {"ok": True, "service": "cointent", "projects": 1}
    assert model.status_code == 200
    assert model.json()["model"]["project_id"] == "idea-factory"


def test_streamable_http_mcp_requires_and_accepts_static_token(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "model.db"
    CoIntentRepository(database).create_project("idea-factory", "Idea Factory")
    monkeypatch.setenv("COINTENT_DB_PATH", str(database))
    monkeypatch.setenv("COINTENT_MCP_TOKEN", "test-secret")
    monkeypatch.setenv("COINTENT_PUBLIC_ORIGIN", "http://127.0.0.1:8811")
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1"},
        },
    }
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8811") as client:
        unauthorized = client.post("/mcp", json=initialize, headers=headers)
        authorized = client.post(
            "/mcp", json=initialize,
            headers={**headers, "Authorization": "Bearer test-secret"},
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert '"serverInfo"' in authorized.text
