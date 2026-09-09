"""Combined Contexture MCP and explicit REST host for CoIntent."""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

from contexture import Principal
from contexture.server import Auth, compile_application
from contexture.web import RestSurface, Route
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from .controller import app as declaration, legacy_app
from .repository import CoIntentRepository
from .session import LoginThrottle, SESSION_COOKIE, SessionAuth


class StaticTokenVerifier:
    def __init__(self, expected: str) -> None:
        self.expected = expected

    async def verify(self, token: str) -> Principal | None:
        if not hmac.compare_digest(token, self.expected):
            return None
        return Principal(
            subject="cointent-agent", client_id="mcp", issuer="cointent-static",
            scopes=frozenset({
                "cointent.read", "cointent.refresh.request",
                "cointent.design.write", "cointent.design.finalize",
            }), claims={"auth": "static-token"},
        )


REST_ROUTES = (
    Route("GET", "/api/health", "cointent/project-management/health"),
    Route("GET", "/api/v1/projects", "cointent/project-management/list-projects"),
    Route("GET", "/api/v1/project", "cointent/project-management/inspect-project"),
    Route("GET", "/api/v1/overview", "cointent/project-management/get-overview"),
    Route("GET", "/api/v1/design-versions", "cointent/project-management/list-design-versions"),
    Route("GET", "/api/v1/alignment-baseline", "cointent/project-management/inspect-alignment-baseline"),
    Route("GET", "/api/v1/observation", "cointent/current-understanding/inspect-observation-coordinate"),
    Route("GET", "/api/v1/observed-revisions", "cointent/current-understanding/list-observed-revisions"),
    Route("GET", "/api/v1/observed-revision", "cointent/current-understanding/inspect-observed-revision"),
    Route("GET", "/api/v1/observation-expansions", "cointent/current-understanding/list-observation-expansions"),
    Route("POST", "/api/v1/observation-expansions", "cointent/current-understanding/request-observation-expansion"),
    Route("GET", "/api/v1/target-design-workspaces", "cointent/target-design/list-target-design-workspaces"),
    Route("POST", "/api/v1/target-design-workspaces", "cointent/target-design/create-target-design-workspace"),
    Route("GET", "/api/v1/target-design-workspace", "cointent/target-design/inspect-target-design-workspace"),
    Route("POST", "/api/v1/target-design-operations", "cointent/target-design/apply-target-design-operations"),
    Route("GET", "/api/v1/target-design-operations", "cointent/target-design/list-target-design-operations"),
    Route("POST", "/api/v1/verifications", "cointent/target-design/compare-implementation-to-target"),
    Route("GET", "/api/v1/verification", "cointent/target-design/inspect-verification-report"),
    Route("GET", "/api/v1/model", "cointent/responsibility-model/inspect-design"),
    Route("GET", "/api/v1/specification", "cointent/specification/inspect-specification-tree"),
    Route("GET", "/api/v1/intent-sources", "cointent/specification/list-intent-sources"),
    Route("GET", "/api/v1/proposals", "cointent/responsibility-model/list-design-proposals"),
    Route("GET", "/api/v1/responsibilities", "cointent/responsibility-model/list-root-responsibilities"),
    Route("GET", "/api/v1/snapshots", "cointent/implementation-alignment/list-code-snapshots"),
    Route("GET", "/api/v1/findings", "cointent/implementation-alignment/list-alignment-findings"),
    Route("GET", "/api/v1/change-sets", "cointent/change-lifecycle/list-change-sets"),
)


def build_http_app() -> Starlette:
    """Build a parent ASGI app with MCP routes followed by the REST fallback."""
    compiled = compile_application(declaration)
    runtime = compile_application(legacy_app).runtime()
    rest = RestSurface(runtime, routes=REST_ROUTES)
    browser_auth = SessionAuth.from_env()
    login_throttle = LoginThrottle()
    token = os.environ.get("COINTENT_MCP_TOKEN", "")
    public_origin = os.environ.get("COINTENT_PUBLIC_ORIGIN", "http://127.0.0.1:8811").rstrip("/")
    auth = Auth(verifier=StaticTokenVerifier(token), issuer=public_origin,
                resource=f"{public_origin}/mcp", required_scopes=("cointent.read",)) if token else None
    wire = compiled.server().build(auth=auth)
    public_host = public_origin.split("://", 1)[-1].split("/", 1)[0]
    security = TransportSecuritySettings(
        allowed_hosts=[public_host, f"{public_host}:*", "127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*"],
        allowed_origins=[public_origin],
    )
    mcp = wire.streamable_http_app(streamable_http_path="/mcp", stateless_http=True,
                                   transport_security=security, host="127.0.0.1")

    async def dispatch(scope, receive, send):
        path = str(scope.get("path", ""))
        if path.startswith("/mcp") or path.startswith("/.well-known/"):
            await mcp(scope, receive, send)
            return
        if path == "/api/health":
            await rest(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        cookie_token = browser_auth.cookie_token(request.headers.get("cookie", ""))
        session_user = browser_auth.verify(cookie_token)

        if request.method == "GET" and path == "/api/me":
            response = JSONResponse({
                "login_required": browser_auth.enabled,
                "authed": not browser_auth.enabled or session_user is not None,
                "user": session_user,
                "bypass": False,
            })
            await response(scope, receive, send)
            return

        if request.method == "POST" and path == "/api/login":
            response = await _login(request, browser_auth, login_throttle)
            await response(scope, receive, send)
            return

        if request.method == "POST" and path == "/api/logout":
            response = JSONResponse({"ok": True})
            response.set_cookie(
                SESSION_COOKIE, "", max_age=0, expires=0, path="/", httponly=True,
                secure=browser_auth.cookie_secure, samesite="strict",
            )
            await response(scope, receive, send)
            return

        protected_browser_path = path.startswith("/api/") or path.startswith("/internal/") or path.startswith("/ua-viewer")
        if protected_browser_path and browser_auth.enabled and session_user is None:
            response = JSONResponse(
                {"error": "unauthorized", "detail": "not logged in or session expired", "login_required": True},
                status_code=401,
            )
            await response(scope, receive, send)
            return
        if path.startswith("/ua-viewer"):
            response = _serve_ua_viewer_asset(path)
            await response(scope, receive, send)
            return
        if path.startswith("/internal/ua-viewer-data/"):
            response = await _ua_viewer_data(request, session_user)
            await response(scope, receive, send)
            return
        if path == "/api/v1/project-state" and request.method == "GET":
            response = _direct_read(request, "project-state")
            await response(scope, receive, send)
            return
        if path == "/api/v1/understanding-refreshes" and request.method == "POST":
            response = await _direct_write(request, session_user, "request-refresh")
            await response(scope, receive, send)
            return
        if path == "/api/v1/understanding-refresh" and request.method == "GET":
            response = _direct_read(request, "inspect-refresh")
            await response(scope, receive, send)
            return
        if path == "/api/v1/current-level" and request.method == "GET":
            response = _direct_read(request, "current-level")
            await response(scope, receive, send)
            return
        if path == "/api/v1/implementation-refs" and request.method == "GET":
            response = _direct_read(request, "implementation-refs")
            await response(scope, receive, send)
            return
        if path == "/api/v1/ua-node-subjects" and request.method == "GET":
            response = _direct_read(request, "ua-node-subjects")
            await response(scope, receive, send)
            return
        if path == "/api/v1/structure-design-diff" and request.method == "GET":
            response = _direct_read(request, "structure-design-diff")
            await response(scope, receive, send)
            return
        if path.startswith("/api/projects/") and path.endswith("/ua-viewer-sessions") and request.method == "POST":
            response = await _direct_write(request, session_user, "viewer-session")
            await response(scope, receive, send)
            return
        if path == "/api/v1/implementation-contexts" and request.method == "POST":
            response = await _direct_write(request, session_user, "implementation-context")
            await response(scope, receive, send)
            return
        if request.method == "POST" and path == "/api/v1/target-design-workspaces":
            response = await _browser_write(request, session_user, "start-design")
            await response(scope, receive, send)
            return
        if request.method == "POST" and path == "/api/v1/target-design-operations":
            response = await _browser_write(request, session_user, "revise-design")
            await response(scope, receive, send)
            return
        if request.method == "POST" and path == "/api/v1/target-design-reviews":
            response = await _browser_write(request, session_user, "review")
            await response(scope, receive, send)
            return
        if request.method == "POST" and path == "/api/v1/target-design-approvals":
            response = await _browser_write(request, session_user, "approve")
            await response(scope, receive, send)
            return
        if request.method == "POST" and path == "/api/v1/implementation-exports":
            response = await _browser_write(request, session_user, "export")
            await response(scope, receive, send)
            return
        if request.method == "POST" and path == "/api/v1/verification-decisions":
            response = await _browser_write(request, session_user, "verification-decision")
            await response(scope, receive, send)
            return
        await rest(scope, receive, send)

    parent = Starlette(lifespan=mcp.router.lifespan_context)
    parent.mount("/", dispatch)
    return parent


async def _browser_write(request: Request, session_user: str | None, operation: str) -> JSONResponse:
    """Keep human approval/export outside the Agent-visible Contexture tool graph."""
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        database = Path(os.environ.get("COINTENT_DB_PATH", "runtime/cointent.db"))
        asset_root = Path(os.environ.get("COINTENT_DATA_ROOT", str(database.parent / "projects")))
        repository = CoIntentRepository(database, asset_root)
        actor = session_user or "local-human"
        if operation == "start-design":
            requested_baseline = str(payload.get("base_observed_revision_id", ""))
            state = repository.project_state(str(payload.get("project_id", "")))
            observed = state["observation"].get("observed_revision")
            if observed is None or observed["id"] != requested_baseline:
                raise ValueError("requested baseline is not the latest explicitly refreshed Observation")
            result = repository.start_structure_design(
                str(payload.get("project_id", "")),
                str(payload.get("title", "")),
                actor=actor,
            )
        elif operation == "revise-design":
            result = repository.apply_design_operations_v04(
                str(payload.get("workspace_id", "")),
                str(payload.get("base_design_revision_id", "")),
                payload.get("operations", []),
                actor=actor,
                rationale=str(payload.get("rationale", "")),
            )
        elif operation == "review":
            result = repository.submit_design_review_v04(
                str(payload.get("workspace_id", "")),
                [str(item) for item in payload.get("acceptance_criteria", [])],
                actor=actor,
            )
        elif operation == "approve":
            result = repository.approve_design_review_v04(
                str(payload.get("review_id", "")), actor=actor,
            )
        elif operation == "export":
            result = repository.create_implementation_export_v04(
                str(payload.get("workspace_id", "")),
            )
        else:
            result = repository.decide_verification_v04(
                str(payload.get("report_id", "")),
                decision=str(payload.get("decision", "")),
                notes=str(payload.get("notes", "")),
                actor=actor,
            )
        return JSONResponse(result)
    except KeyError as error:
        return JSONResponse({"error": "not_found", "detail": str(error)}, status_code=404)
    except ValueError as error:
        return JSONResponse({"error": "invalid_request", "detail": str(error)}, status_code=400)


def _runtime_repository() -> CoIntentRepository:
    database = Path(os.environ.get("COINTENT_DB_PATH", "runtime/cointent.db"))
    asset_root = Path(os.environ.get("COINTENT_DATA_ROOT", str(database.parent / "projects")))
    return CoIntentRepository(database, asset_root)


def _direct_read(request: Request, operation: str) -> JSONResponse:
    try:
        repository = _runtime_repository()
        query = request.query_params
        if operation == "project-state":
            result = repository.project_state(str(query.get("project_id", "idea-factory")))
        elif operation == "inspect-refresh":
            result = repository.get_understanding_refresh(str(query.get("job_id", "")))
        elif operation == "current-level":
            result = repository.read_current_level(
                str(query.get("project_id", "idea-factory")),
                focus_id=query.get("focus_id"), observed_revision_id=query.get("observed_revision_id"),
            )
        elif operation == "implementation-refs":
            result = {"implementation_refs": repository.implementation_refs_for_subject(
                str(query.get("observed_revision_id", "")), str(query.get("subject_id", "")),
            )}
        elif operation == "structure-design-diff":
            result = repository.diff_structure_design(
                str(query.get("workspace_id", "")),
                from_revision_id=query.get("from_revision_id"),
                to_revision_id=query.get("to_revision_id"),
            )
        else:
            result = repository.semantic_subjects_for_ua_node(
                str(query.get("ua_snapshot_id", "")), str(query.get("node_id", "")),
            )
        return JSONResponse(result)
    except KeyError as error:
        return JSONResponse({"error": "not_found", "detail": str(error)}, status_code=404)
    except ValueError as error:
        return JSONResponse({"error": "invalid_request", "detail": str(error)}, status_code=400)


async def _direct_write(request: Request, session_user: str | None, operation: str) -> JSONResponse:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        repository = _runtime_repository()
        actor = session_user or "local-human"
        if operation == "request-refresh":
            result = repository.request_understanding_refresh(
                str(payload.get("project_id", "")), requested_by=actor,
            )
        elif operation == "implementation-context":
            result = repository.create_implementation_context(
                str(payload.get("workspace_id", "")),
                str(payload.get("design_revision_id", "")),
                str(payload.get("expected_diff_digest", "")),
                actor=actor,
            )
        else:
            parts = [item for item in request.url.path.split("/") if item]
            project_id = parts[2] if len(parts) >= 4 else ""
            result = repository.create_ua_viewer_session(
                project_id,
                str(payload.get("observed_revision_id", "")),
                str(payload.get("ua_snapshot_id", "")),
                principal=actor,
            )
        return JSONResponse(result)
    except KeyError as error:
        return JSONResponse({"error": "not_found", "detail": str(error)}, status_code=404)
    except (json.JSONDecodeError, ValueError) as error:
        return JSONResponse({"error": "invalid_request", "detail": str(error)}, status_code=400)


async def _ua_viewer_data(request: Request, session_user: str | None) -> JSONResponse:
    try:
        prefix = "/internal/ua-viewer-data/"
        relative = request.url.path[len(prefix):]
        token, separator, artifact = relative.partition("/")
        if not separator or not token or not artifact:
            raise ValueError("invalid UA viewer data path")
        repository = _runtime_repository()
        session = repository.resolve_ua_viewer_session(
            token, principal=session_user or "local-human",
        )
        if artifact == "file-content.json":
            result = repository.read_snapshot_source(session, str(request.query_params.get("path", "")))
        else:
            result = repository.ua_viewer_graph(session, artifact)
            if result is None:
                return JSONResponse(
                    {"error": "optional artifact unavailable"}, status_code=404,
                    headers={"Cache-Control": "no-store"},
                )
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except KeyError as error:
        return JSONResponse({"error": "not_found", "detail": str(error)}, status_code=404)
    except ValueError as error:
        return JSONResponse({"error": "invalid_request", "detail": str(error)}, status_code=400)


def _serve_ua_viewer_asset(request_path: str) -> FileResponse | JSONResponse:
    root = Path(os.environ.get("COINTENT_UA_VIEWER_ROOT", "web/ua-viewer-dist")).resolve()
    relative = (
        "index.html" if request_path in {"/ua-viewer", "/ua-viewer/"}
        else request_path.removeprefix("/ua-viewer/")
    )
    target = (root / relative).resolve()
    if root not in target.parents and target != root:
        return JSONResponse({"error": "invalid_viewer_path"}, status_code=400)
    if not target.is_file():
        if "." not in Path(relative).name and (root / "index.html").is_file():
            target = root / "index.html"
        else:
            return JSONResponse({
                "error": "ua_viewer_not_built",
                "detail": "Build the pinned UA Dashboard with scripts/build-ua-viewer.sh",
            }, status_code=503)
    return FileResponse(target, headers={
        "Content-Security-Policy": "frame-ancestors 'self'",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=31536000, immutable" if target.name != "index.html" else "no-cache",
    })


async def _login(request: Request, auth: SessionAuth, throttle: LoginThrottle) -> JSONResponse:
    if not auth.enabled:
        return JSONResponse({"ok": True, "user": None, "login_required": False})
    source = request.client.host if request.client is not None else "unknown"
    wait = throttle.blocked_for(source)
    if wait:
        return JSONResponse(
            {"error": "too_many_attempts", "detail": f"try again in {wait} seconds", "retry_after_seconds": wait},
            status_code=429, headers={"Retry-After": str(wait)},
        )
    try:
        raw = await request.body()
        if len(raw) > 4096:
            return JSONResponse({"error": "request_too_large"}, status_code=413)
        body = json.loads(raw)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    user = str(body.get("user", "")) if isinstance(body, dict) else ""
    password = str(body.get("password", "")) if isinstance(body, dict) else ""
    if not auth.credentials_valid(user, password):
        throttle.fail(source)
        return JSONResponse({"error": "bad_credentials", "detail": "incorrect username or password"}, status_code=401)
    throttle.reset(source)
    response = JSONResponse({"ok": True, "user": auth.user, "login_required": True})
    response.set_cookie(
        SESSION_COOKIE, auth.issue(), max_age=auth.ttl_seconds, path="/", httponly=True,
        secure=auth.cookie_secure, samesite="strict",
    )
    return response


application = build_http_app()
