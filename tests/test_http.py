import json
from pathlib import Path

from starlette.testclient import TestClient

from cointent.app import build_http_app
from cointent.repository import CoIntentRepository
from cointent.scanner import Artifact, RepositorySnapshot


def test_rest_surface_uses_contexture_runtime(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "model.db"
    CoIntentRepository(database).create_project("idea-factory", "Idea Factory")
    monkeypatch.setenv("COINTENT_DB_PATH", str(database))

    with TestClient(build_http_app(), base_url="http://127.0.0.1") as client:
        health = client.get("/api/health")
        model = client.get("/api/v1/model?project_id=idea-factory")
        observation = client.get("/api/v1/observation?project_id=idea-factory")

    assert health.status_code == 200
    assert health.json() == {"ok": True, "service": "cointent", "schema_version": "0.3", "projects": 1}
    assert model.status_code == 200
    assert model.json()["model"]["project_id"] == "idea-factory"
    assert model.json()["model"]["schema_version"] == "0.3"
    assert observation.status_code == 200
    assert observation.json() == {
        "project_id": "idea-factory", "status": "not_generated", "observed_revision": None,
    }


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


def test_browser_can_request_and_open_a_generated_observation_refinement(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "model.db"
    repository = CoIntentRepository(database)
    repository.create_project("idea-factory", "Idea Factory")
    snapshot = RepositorySnapshot(
        id="snapshot-browser-full",
        project_id="idea-factory",
        repository="demo",
        revision="f" * 40,
        branch="main",
        dirty=True,
        scope="full",
        captured_at="2026-09-09T00:00:00+00:00",
        artifacts=[
            Artifact(path="src/cointent/repository.py", kind="source", language="Python",
                     component="src/cointent", sha256="1" * 64, size=100, line_count=1200),
            Artifact(path="src/cointent/app.py", kind="source", language="Python",
                     component="src/cointent", sha256="2" * 64, size=100, line_count=200),
        ],
    )
    repository.ingest_snapshot("idea-factory", snapshot.model_dump())
    fixtures = Path(__file__).parent / "fixtures" / "ua"
    imported = repository.import_understand_anything(
        "idea-factory",
        snapshot.id,
        "ua-pin",
        json.loads((fixtures / "knowledge-graph.json").read_text(encoding="utf-8")),
        json.loads((fixtures / "domain-graph.json").read_text(encoding="utf-8")),
    )
    base = imported["observed_revision"]
    target = base["capabilities"][0]["responsibility_id"]
    monkeypatch.setenv("COINTENT_DB_PATH", str(database))

    with TestClient(build_http_app(), base_url="http://127.0.0.1") as client:
        expanded = client.post("/api/v1/observation-expansions", json={
            "project_id": "idea-factory",
            "observed_revision_id": base["id"],
            "node_id": target,
            "depth": 1,
        })
        assert expanded.status_code == 200
        request = expanded.json()["request"]
        assert request["status"] == "completed"
        child = client.get("/api/v1/observation", params={
            "project_id": "idea-factory",
            "observed_revision_id": request["result_observed_revision_id"],
        })
        created_design = client.post("/api/v1/target-design-workspaces", json={
            "project_id": "idea-factory",
            "base_observed_revision_id": base["id"],
            "title": "Next system",
            "rationale": "Begin from the verified current model.",
            "actor": "human",
        })
        assert created_design.status_code == 200
        initial_design = created_design.json()
        changed_responsibility = dict(initial_design["revision"]["responsibilities"][0])
        changed_responsibility["description"] = "Own current understanding and a faster return path."
        changed_design = client.post("/api/v1/target-design-operations", json={
            "workspace_id": initial_design["workspace"]["id"],
            "base_design_revision_id": initial_design["revision"]["id"],
            "operations": [{"kind": "upsert_responsibility", "responsibility": changed_responsibility}],
            "rationale": "Capture the reviewed product expectation.",
            "actor": "human",
        })
        assert changed_design.status_code == 200
        target_view = client.get("/api/v1/target-design-workspace", params={
            "project_id": "idea-factory",
            "workspace_id": initial_design["workspace"]["id"],
        })
        review = client.post("/api/v1/target-design-reviews", json={
            "workspace_id": initial_design["workspace"]["id"],
            "acceptance_criteria": ["The faster return path is covered by an integration test."],
        })
        assert review.status_code == 200
        approval = client.post("/api/v1/target-design-approvals", json={
            "review_id": review.json()["id"],
        })
        assert approval.status_code == 200
        implementation_export = client.post("/api/v1/implementation-exports", json={
            "workspace_id": initial_design["workspace"]["id"],
        })
        assert implementation_export.status_code == 200
        verification = client.post("/api/v1/verifications", json={
            "workspace_id": initial_design["workspace"]["id"],
            "observed_revision_id": base["id"],
        })
        assert verification.status_code == 200
        blocked_convergence = client.post("/api/v1/verification-decisions", json={
            "report_id": verification.json()["id"],
            "decision": "converged",
            "notes": "This must fail because the code coordinate is stale.",
        })
        needs_revision = client.post("/api/v1/verification-decisions", json={
            "report_id": verification.json()["id"],
            "decision": "needs_revision",
            "notes": "Import a post-implementation observation before convergence.",
        })

    assert child.status_code == 200
    assert child.json()["observed_revision"]["parent_revision_id"] == base["id"]
    assert child.json()["observed_revision"]["refinement"]["added_responsibilities"] == 2
    assert target_view.status_code == 200
    assert target_view.json()["revision"]["responsibilities"][0]["description"].endswith("return path.")
    assert implementation_export.json()["approved_by"] == "local-human"
    assert implementation_export.json()["acceptance_criteria"]
    assert verification.json()["summary"]["stale"] > 0
    assert blocked_convergence.status_code == 400
    assert needs_revision.status_code == 200
    assert needs_revision.json()["decision"] == "needs_revision"
    assert repository.get_observed_revision(base["id"])["content_digest"] == base["content_digest"]


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
