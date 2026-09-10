"""Single authoritative source of the dependency-free import stubs.

TRN-144: the unit suite runs in a dependency-free checkout where ``httpx`` /
``mcp`` / ``starlette`` / ``uvicorn`` are not installed. Every test file that
needs them (``test_file_transfer`` directly, plus ``test_recovery`` /
``test_network`` / ``test_server`` / ``test_openapi`` transitively) must resolve
the **same** stub objects so that exception-class identity holds suite-wide:
``transport.lifecycle`` binds ``except (httpx.ConnectError, httpx.ConnectTimeout,
...)`` to the class objects on ``sys.modules["httpx"]`` at import time, and the
recovery tests raise ``httpx.ConnectError(...)`` — those must be one and the same
class.

The install function is idempotent: the exception classes are defined once at
module scope here (never re-created per call), and ``install_import_stubs()``
returns early if ``sys.modules["httpx"]`` already carries the shared-stub marker.
The first test file to import in discovery order installs the shared stub; every
later import — including ``lifecycle``'s top-level ``import httpx`` — resolves the
same object. There is deliberately no ``tearDownModule``/``setUpModule`` teardown:
the sequential runner requires the stubs to persist for the whole run.
"""
from __future__ import annotations

import sys
import types
from typing import Any


# ── Module-level exception classes (defined ONCE — the single identity) ───────

class HTTPStatusError(Exception):
    def __init__(self, message: str = "", request: Any = None, response: Any = None) -> None:
        super().__init__(message)
        self.request = request
        self.response = response


class ConnectError(Exception):
    pass


class ConnectTimeout(Exception):
    pass


def build_httpx_stub() -> types.ModuleType:
    """Build the fake ``httpx`` module with the shared exception classes."""
    httpx = types.ModuleType("httpx")

    class Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class AsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def request(self, *args: Any, **kwargs: Any) -> Any:
            pass

        def stream(self, *args: Any, **kwargs: Any) -> Any:
            pass

    class HTTPTransport:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class Response:
        """Minimal httpx.Response stub — needed by httpx_ws._exceptions at import time."""

        def __init__(self, status_code: int = 200, **kwargs: Any) -> None:
            self.status_code = status_code

    # Module-level function stubs — placeholder targets that tests can patch with
    # patch.object(server.httpx, "put", ...) etc. Without them patch.object
    # raises AttributeError before the test even runs.
    def _httpx_put(*args: Any, **kwargs: Any) -> Response:  # pragma: no cover
        raise NotImplementedError("httpx.put stub — patch in tests")

    def _httpx_delete(*args: Any, **kwargs: Any) -> Response:  # pragma: no cover
        raise NotImplementedError("httpx.delete stub — patch in tests")

    httpx.Client = Client  # type: ignore[attr-defined]
    httpx.AsyncClient = AsyncClient  # type: ignore[attr-defined]
    httpx.HTTPTransport = HTTPTransport  # type: ignore[attr-defined]
    httpx.HTTPStatusError = HTTPStatusError  # type: ignore[attr-defined]
    httpx.ConnectError = ConnectError  # type: ignore[attr-defined]
    httpx.ConnectTimeout = ConnectTimeout  # type: ignore[attr-defined]
    httpx.Response = Response  # type: ignore[attr-defined]
    httpx.put = _httpx_put  # type: ignore[attr-defined]
    httpx.delete = _httpx_delete  # type: ignore[attr-defined]
    return httpx


def _install_mcp_stubs() -> None:
    mcp = types.ModuleType("mcp")
    mcp_server = types.ModuleType("mcp.server")
    mcp_mcpserver = types.ModuleType("mcp.server.mcpserver")
    mcp_server_impl = types.ModuleType("mcp.server.mcpserver.server")

    class MCPServer:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def _decorator(self, *args: Any, **kwargs: Any):
            return lambda function: function

        def tool(self, *args: Any, **kwargs: Any):
            return self._decorator(*args, **kwargs)

        def resource(self, *args: Any, **kwargs: Any):
            return self._decorator(*args, **kwargs)

        def streamable_http_app(self, *args: Any, **kwargs: Any):
            """Stub: return a no-op ASGI app."""
            async def _noop(scope, receive, send):
                pass
            return _noop

    mcp_server_impl.MCPServer = MCPServer  # type: ignore[attr-defined]
    sys.modules.update({
        "mcp": mcp,
        "mcp.server": mcp_server,
        "mcp.server.mcpserver": mcp_mcpserver,
        "mcp.server.mcpserver.server": mcp_server_impl,
    })


def _install_starlette_stubs() -> None:
    starlette = types.ModuleType("starlette")
    starlette_applications = types.ModuleType("starlette.applications")
    starlette_requests = types.ModuleType("starlette.requests")
    starlette_responses = types.ModuleType("starlette.responses")
    starlette_routing = types.ModuleType("starlette.routing")

    class Response:
        def __init__(self, content: Any = b"", status_code: int = 200, **kwargs: Any) -> None:
            if isinstance(content, str):
                self.body = content.encode("utf-8")
            elif isinstance(content, (dict, list)):
                import json as _json
                self.body = _json.dumps(content).encode("utf-8")
            else:
                self.body = content
            self.status_code = status_code
            self.kwargs = kwargs
            # Expose headers as a dict-like object so tests can call
            # resp.headers.get("Set-Cookie", "") the same way as real Starlette.
            self.headers = kwargs.get("headers", {})

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            """Make Response callable as an ASGI app (for proxy handler tests)."""
            await send({
                "type": "http.response.start",
                "status": self.status_code,
                "headers": [],
            })
            await send({
                "type": "http.response.body",
                "body": self.body if isinstance(self.body, bytes) else b"",
            })

    class Request:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if args:
                scope = args[0]
                self.method = scope.get("method", "GET")
                self.scope = scope
                self.headers = {
                    k.decode("latin-1"): v.decode("latin-1")
                    for k, v in scope.get("headers", [])
                }

        async def body(self) -> bytes:
            return b""

    class Starlette:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class Route:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    starlette_applications.Starlette = Starlette  # type: ignore[attr-defined]
    starlette_requests.Request = Request  # type: ignore[attr-defined]
    starlette_responses.Response = Response  # type: ignore[attr-defined]
    starlette_responses.StreamingResponse = Response  # type: ignore[attr-defined]
    starlette_responses.PlainTextResponse = Response  # type: ignore[attr-defined]
    starlette_responses.JSONResponse = Response  # type: ignore[attr-defined]
    starlette_routing.Route = Route  # type: ignore[attr-defined]
    starlette_routing.Mount = Route  # type: ignore[attr-defined]

    starlette_websockets = types.ModuleType("starlette.websockets")

    class WebSocket:
        """Minimal starlette WebSocket stub for TRN-80 WS proxy tests."""

        def __init__(self, scope: Any = None, receive: Any = None, send: Any = None) -> None:
            self.scope = scope or {}
            self._receive = receive
            self._send = send

        async def accept(self) -> None:
            pass

        async def receive(self) -> dict:
            if self._receive:
                return await self._receive()
            return {"type": "websocket.disconnect"}

        async def send_text(self, data: str) -> None:
            pass

        async def send_bytes(self, data: bytes) -> None:
            pass

        async def close(self, code: int = 1000) -> None:
            pass

    class WebSocketDisconnect(Exception):
        def __init__(self, code: int = 1000) -> None:
            self.code = code

    starlette_websockets.WebSocket = WebSocket  # type: ignore[attr-defined]
    starlette_websockets.WebSocketDisconnect = WebSocketDisconnect  # type: ignore[attr-defined]
    starlette.websockets = starlette_websockets  # type: ignore[attr-defined]

    sys.modules.update({
        "starlette": starlette,
        "starlette.applications": starlette_applications,
        "starlette.requests": starlette_requests,
        "starlette.responses": starlette_responses,
        "starlette.routing": starlette_routing,
        "starlette.websockets": starlette_websockets,
    })


def _install_uvicorn_stubs() -> None:
    uvicorn_mod = types.ModuleType("uvicorn")

    class _UvicornConfig:
        def __init__(self, app: Any = None, **kwargs: Any) -> None:
            self.app = app

    class _UvicornServer:
        def __init__(self, config: Any = None) -> None:
            self.should_exit = False

        async def serve(self) -> None:
            pass

    uvicorn_mod.Config = _UvicornConfig  # type: ignore[attr-defined]
    uvicorn_mod.Server = _UvicornServer  # type: ignore[attr-defined]
    sys.modules["uvicorn"] = uvicorn_mod


def install_import_stubs() -> None:
    """Idempotently install the ONE shared stub set into ``sys.modules``.

    Two early-return cases preserve object identity so that every caller — and
    ``transport.lifecycle`` — resolves the SAME ``httpx`` module (and therefore
    the same ``ConnectError`` / ``ConnectTimeout`` / ``HTTPStatusError`` classes):

    * If ``sys.modules["httpx"]`` is already our shared stub (marked with
      ``_kirocrew_shared_stub``), do nothing — a second caller reuses it.
    * If some ``httpx`` is already present that is NOT our stub, it is the REAL
      httpx (installed in the venv ``tests/run.sh`` bootstraps). Never overwrite
      it: doing so would leave ``lifecycle`` bound to real httpx while a later
      ``import httpx`` resolves the stub, splitting exception-class identity.
      When real httpx is importable, identity is trivially consistent (everyone
      uses real httpx), so the stub is simply not needed.

    The stub is therefore installed only in the dependency-free checkout, where
    ``httpx`` is genuinely absent from ``sys.modules`` and not importable.
    """
    existing = sys.modules.get("httpx")
    if existing is not None:
        # Either our shared stub (reuse) or real httpx (leave untouched).
        return

    httpx = build_httpx_stub()
    httpx._kirocrew_shared_stub = True  # type: ignore[attr-defined]
    sys.modules["httpx"] = httpx

    _install_mcp_stubs()
    _install_starlette_stubs()
    _install_uvicorn_stubs()
