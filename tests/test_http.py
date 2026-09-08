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
    assert health.json() == {"ok": True, "service": "cointent", "schema_version": "0.2", "projects": 1}
    assert model.status_code == 200
    assert model.json()["model"]["project_id"] == "idea-factory"
    assert model.json()["model"]["schema_version"] == "0.2"


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


def test_browser_api_uses_oc_style_signed_session(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "model.db"
    CoIntentRepository(database).create_project("idea-factory", "Idea Factory")
    monkeypatch.setenv("COINTENT_DB_PATH", str(database))
    monkeypatch.setenv("COINTENT_LOGIN_USER", "carter")
    monkeypatch.setenv("COINTENT_LOGIN_PASSWORD", "correct-horse-battery-staple")
    monkeypatch.setenv("COINTENT_SESSION_SECRET", "independent-test-secret")
    monkeypatch.setenv("COINTENT_PUBLIC_ORIGIN", "https://127.0.0.1:8811")

    with TestClient(build_http_app(), base_url="https://127.0.0.1:8811") as client:
        me = client.get("/api/me")
        protected = client.get("/api/v1/model?project_id=idea-factory")
        rejected = client.post("/api/login", json={"user": "carter", "password": "wrong"})
        accepted = client.post(
            "/api/login", json={"user": "carter", "password": "correct-horse-battery-staple"},
        )
        opened = client.get("/api/v1/model?project_id=idea-factory")
        logout = client.post("/api/logout")
        closed = client.get("/api/v1/model?project_id=idea-factory")

    assert me.json() == {"login_required": True, "authed": False, "user": None, "bypass": False}
    assert protected.status_code == 401
    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert "HttpOnly" in accepted.headers["set-cookie"]
    assert "SameSite=strict" in accepted.headers["set-cookie"]
    assert "Secure" in accepted.headers["set-cookie"]
    assert opened.status_code == 200
    assert logout.status_code == 200
    assert closed.status_code == 401
