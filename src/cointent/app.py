"""Combined Contexture MCP and explicit REST host for CoIntent."""

from __future__ import annotations

import hmac
import json
import os

from contexture import Principal
from contexture.server import Auth, compile_application
from contexture.web import RestSurface, Route
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from .controller import app as declaration
from .session import LoginThrottle, SESSION_COOKIE, SessionAuth


class StaticTokenVerifier:
    def __init__(self, expected: str) -> None:
        self.expected = expected

    async def verify(self, token: str) -> Principal | None:
        if not hmac.compare_digest(token, self.expected):
            return None
        return Principal(
            subject="cointent-agent", client_id="mcp", issuer="cointent-static",
            scopes=frozenset({"cointent"}), claims={"auth": "static-token"},
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
    runtime = compiled.runtime()
    rest = RestSurface(runtime, routes=REST_ROUTES)
    browser_auth = SessionAuth.from_env()
    login_throttle = LoginThrottle()
    token = os.environ.get("COINTENT_MCP_TOKEN", "")
    public_origin = os.environ.get("COINTENT_PUBLIC_ORIGIN", "http://127.0.0.1:8811").rstrip("/")
    auth = Auth(verifier=StaticTokenVerifier(token), issuer=public_origin,
                resource=f"{public_origin}/mcp", required_scopes=("cointent",)) if token else None
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

        if path.startswith("/api/") and browser_auth.enabled and session_user is None:
            response = JSONResponse(
                {"error": "unauthorized", "detail": "not logged in or session expired", "login_required": True},
                status_code=401,
            )
            await response(scope, receive, send)
            return
        await rest(scope, receive, send)

    parent = Starlette(lifespan=mcp.router.lifespan_context)
    parent.mount("/", dispatch)
    return parent


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
