"""Combined Contexture MCP and explicit REST host for CoIntent."""

from __future__ import annotations

import hmac
import os

from contexture import Principal
from contexture.server import Auth, compile_application
from contexture.web import RestSurface, Route
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from .controller import app as declaration


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
    Route("GET", "/api/health", "project-alignment/design-convergence/health"),
    Route("GET", "/api/v1/projects", "project-alignment/design-convergence/list-projects"),
    Route("GET", "/api/v1/overview", "project-alignment/design-convergence/get-overview"),
    Route("GET", "/api/v1/model", "project-alignment/design-convergence/inspect-model"),
    Route("GET", "/api/v1/intent-sources", "project-alignment/design-convergence/list-intent-sources"),
    Route("GET", "/api/v1/proposals", "project-alignment/design-convergence/list-proposals"),
    Route("GET", "/api/v1/snapshots", "project-alignment/implementation-mapping/list-snapshots"),
    Route("GET", "/api/v1/findings", "project-alignment/alignment-review/list-findings"),
)


def build_http_app() -> Starlette:
    """Build a parent ASGI app with MCP routes followed by the REST fallback."""
    compiled = compile_application(declaration)
    runtime = compiled.runtime()
    rest = RestSurface(runtime, routes=REST_ROUTES)
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
        else:
            await rest(scope, receive, send)

    parent = Starlette(lifespan=mcp.router.lifespan_context)
    parent.mount("/", dispatch)
    return parent


application = build_http_app()
