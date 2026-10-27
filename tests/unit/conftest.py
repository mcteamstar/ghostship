"""Pytest configuration for the transport unit test suite (TRN-244 rewrite).

Design principles
-----------------
1. **Dependency injection over module patching** — fixtures expose the test
   doubles directly; tests call functions under test with the fake injected,
   rather than patching import paths with unittest.mock.patch.
2. **No I/O in unit tests** — the autouse ``_block_registry_io`` fixture
   prevents any ``_load_registry`` / ``_save_registry`` call from touching
   the filesystem (they are blocked at the module level for every test not
   explicitly in ``test_registry_lock.py``).
3. **Single stub installation** — ``_install_transport_stubs()`` is called
   once at session scope to install the httpx / mcp / starlette / uvicorn
   shims needed for importing transport modules in the dependency-free
   checkout (no httpx2 or httpx installed in test environment).
"""

from __future__ import annotations

import io
import sys
import tarfile
import types
from typing import Any
from unittest.mock import patch

import pytest

from tests.fakes import FakePodmanClient


# ── Stub installation (session-scoped, idempotent) ────────────────────────────

def _install_transport_stubs() -> None:
    """Install minimal module stubs for packages not present in unit test env.

    Installs httpx2/httpx, mcp, starlette, and uvicorn stubs so that transport
    modules can be imported without the real packages. Idempotent — safe to call
    multiple times; the first call wins.
    """
    # ── httpx2 (the name used by podman.py) ───────────────────────────────────
    if "httpx2" not in sys.modules:
        httpx2 = types.ModuleType("httpx2")

        class HTTPStatusError(Exception):
            def __init__(self, msg: str = "", request: Any = None, response: Any = None):
                super().__init__(msg)
                self.request = request
                self.response = response

        class ConnectError(Exception):
            pass

        class ConnectTimeout(Exception):
            pass

        class Response:
            def __init__(self, status_code: int = 200, **kw: Any):
                self.status_code = status_code

        class Client:
            def __init__(self, *a: Any, **kw: Any):
                pass

            def close(self) -> None:
                pass

            def get(self, url: str, **kw: Any) -> "Response":
                return Response()

            def post(self, url: str, **kw: Any) -> "Response":
                return Response()

            def request(self, method: str, url: str, **kw: Any) -> "Response":
                return Response()

            def build_request(self, method: str, url: str, **kw: Any) -> Any:
                return None

            def send(self, request: Any, **kw: Any) -> "Response":
                return Response()

            def delete(self, url: str, **kw: Any) -> "Response":
                return Response()

        class AsyncClient:
            def __init__(self, *a: Any, **kw: Any):
                pass

            async def aclose(self) -> None:
                pass

            async def request(self, method: str, url: str, **kw: Any) -> "Response":
                return Response()

        class HTTPTransport:
            def __init__(self, *a: Any, **kw: Any):
                pass

        httpx2.HTTPStatusError = HTTPStatusError  # type: ignore[attr-defined]
        httpx2.ConnectError = ConnectError  # type: ignore[attr-defined]
        httpx2.ConnectTimeout = ConnectTimeout  # type: ignore[attr-defined]
        httpx2.Response = Response  # type: ignore[attr-defined]
        httpx2.Client = Client  # type: ignore[attr-defined]
        httpx2.AsyncClient = AsyncClient  # type: ignore[attr-defined]
        httpx2.HTTPTransport = HTTPTransport  # type: ignore[attr-defined]
        httpx2._unit_test_stub = True  # type: ignore[attr-defined]
        sys.modules["httpx2"] = httpx2

    # ── httpx alias (imported by some transport modules as `import httpx`) ────
    if "httpx" not in sys.modules:
        httpx = sys.modules.get("httpx2") or sys.modules["httpx2"]
        # Re-export as httpx so `import httpx` also resolves our stub
        sys.modules["httpx"] = httpx

    # ── starlette (used by transport/auth.py for ASGI response helpers) ──────
    if "starlette" not in sys.modules:
        starlette_mod = types.ModuleType("starlette")
        starlette_responses = types.ModuleType("starlette.responses")
        starlette_requests = types.ModuleType("starlette.requests")

        class Response:
            """Minimal ASGI-callable response stub matching starlette.responses.Response."""

            def __init__(self, content: str = "", status_code: int = 200,
                         headers: dict | None = None, media_type: str = "text/plain") -> None:
                self.status_code = status_code
                self.body = content.encode("utf-8") if isinstance(content, str) else content
                raw_headers: list[tuple[bytes, bytes]] = []
                for k, v in (headers or {}).items():
                    raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
                self._raw_headers = raw_headers

            async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
                await send({
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self._raw_headers,
                })
                await send({
                    "type": "http.response.body",
                    "body": self.body,
                })

        class PlainTextResponse(Response):
            """Minimal stub for starlette.responses.PlainTextResponse."""

            def __init__(self, content: str = "", status_code: int = 200,
                         headers: dict | None = None) -> None:
                super().__init__(content=content, status_code=status_code,
                                 headers=headers, media_type="text/plain")

        class JSONResponse(Response):
            """Minimal stub for starlette.responses.JSONResponse.

            login.py's HTTP handlers (TRN-242) return JSONResponse; the unit
            tests that import login only need the class to exist and carry the
            serialised payload/status. json.dumps matches starlette's behaviour
            closely enough for the assertions made in test_login.py.
            """

            def __init__(self, content: Any = None, status_code: int = 200,
                         headers: dict | None = None) -> None:
                import json as _json
                self.data = content
                body = _json.dumps(content)
                super().__init__(content=body, status_code=status_code,
                                 headers=headers, media_type="application/json")

        class Request:
            """Minimal stub for starlette.requests.Request.

            auth.py constructs ``Request(scope, receive)`` then passes the
            instance to route handlers. The stub does not need to implement
            body parsing — handlers in test_auth.py only check whether they
            were called, not the request content.
            """

            def __init__(self, scope: Any, receive: Any) -> None:
                self.scope = scope
                self._receive = receive
                self.method: str = scope.get("method", "GET")
                self.url = type("URL", (), {"path": scope.get("path", "/")})()

        starlette_responses.Response = Response  # type: ignore[attr-defined]
        starlette_responses.PlainTextResponse = PlainTextResponse  # type: ignore[attr-defined]
        starlette_responses.JSONResponse = JSONResponse  # type: ignore[attr-defined]
        starlette_requests.Request = Request  # type: ignore[attr-defined]

        class StreamingResponse(Response):
            """Minimal stub for starlette.responses.StreamingResponse."""
            def __init__(self, content: Any = None, status_code: int = 200,
                         headers: dict | None = None, media_type: str = "application/octet-stream") -> None:
                super().__init__(content="", status_code=status_code,
                                 headers=headers, media_type=media_type)
                self.body_iterator = content

        starlette_responses.StreamingResponse = StreamingResponse  # type: ignore[attr-defined]

        starlette_routing = types.ModuleType("starlette.routing")

        class Route:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

        starlette_routing.Route = Route  # type: ignore[attr-defined]
        starlette_mod.routing = starlette_routing  # type: ignore[attr-defined]

        starlette_mod.responses = starlette_responses  # type: ignore[attr-defined]
        starlette_mod.requests = starlette_requests  # type: ignore[attr-defined]
        starlette_mod._unit_test_stub = True  # type: ignore[attr-defined]
        sys.modules.update({
            "starlette": starlette_mod,
            "starlette.responses": starlette_responses,
            "starlette.requests": starlette_requests,
            "starlette.routing": starlette_routing,
        })

    # ── cryptography (used by captain._format_captain_mail with signing) ─────
    if "cryptography" not in sys.modules:
        crypto = types.ModuleType("cryptography")
        hazmat = types.ModuleType("cryptography.hazmat")
        primitives = types.ModuleType("cryptography.hazmat.primitives")
        asym = types.ModuleType("cryptography.hazmat.primitives.asymmetric")
        ed25519_mod = types.ModuleType("cryptography.hazmat.primitives.asymmetric.ed25519")

        class Ed25519PrivateKey:
            @classmethod
            def from_private_bytes(cls, data: bytes) -> "Ed25519PrivateKey":
                inst = cls()
                inst._data = data
                return inst

            def sign(self, payload: bytes) -> bytes:
                # Deterministic stub: return first 64 bytes of sha256 repeated
                import hashlib
                h = hashlib.sha256(payload).digest()
                return (h * 3)[:64]

        ed25519_mod.Ed25519PrivateKey = Ed25519PrivateKey  # type: ignore[attr-defined]
        asym.ed25519 = ed25519_mod  # type: ignore[attr-defined]
        primitives.asymmetric = asym  # type: ignore[attr-defined]
        hazmat.primitives = primitives  # type: ignore[attr-defined]
        crypto.hazmat = hazmat  # type: ignore[attr-defined]
        sys.modules.update({
            "cryptography": crypto,
            "cryptography.hazmat": hazmat,
            "cryptography.hazmat.primitives": primitives,
            "cryptography.hazmat.primitives.asymmetric": asym,
            "cryptography.hazmat.primitives.asymmetric.ed25519": ed25519_mod,
        })

    # ── mcp (used by server.py for MCPServer) ─────────────────────────────────
    if "mcp" not in sys.modules:
        mcp_mod = types.ModuleType("mcp")
        mcp_server_mod = types.ModuleType("mcp.server")
        mcp_mcpserver_mod = types.ModuleType("mcp.server.mcpserver")
        mcp_server_server_mod = types.ModuleType("mcp.server.mcpserver.server")

        class MCPServer:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def tool(self, *args: Any, **kwargs: Any) -> Any:
                def decorator(fn: Any) -> Any:
                    return fn
                return decorator

            def resource(self, *args: Any, **kwargs: Any) -> Any:
                def decorator(fn: Any) -> Any:
                    return fn
                return decorator

            def streamable_http_app(self, *args: Any, **kwargs: Any) -> Any:
                return None

        mcp_server_server_mod.MCPServer = MCPServer  # type: ignore[attr-defined]
        mcp_mcpserver_mod.server = mcp_server_server_mod  # type: ignore[attr-defined]
        mcp_server_mod.mcpserver = mcp_mcpserver_mod  # type: ignore[attr-defined]
        mcp_mod.server = mcp_server_mod  # type: ignore[attr-defined]
        sys.modules.update({
            "mcp": mcp_mod,
            "mcp.server": mcp_server_mod,
            "mcp.server.mcpserver": mcp_mcpserver_mod,
            "mcp.server.mcpserver.server": mcp_server_server_mod,
        })

    # ── uvicorn (used by server.py for Config/Server classes) ─────────────────
    if "uvicorn" not in sys.modules:
        uvicorn_mod = types.ModuleType("uvicorn")

        class UvicornConfig:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

        class UvicornServer:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def serve(self) -> None:
                pass

        uvicorn_mod.Config = UvicornConfig  # type: ignore[attr-defined]
        uvicorn_mod.Server = UvicornServer  # type: ignore[attr-defined]
        uvicorn_mod._unit_test_stub = True  # type: ignore[attr-defined]
        sys.modules["uvicorn"] = uvicorn_mod

    # ── starlette.applications, starlette.websockets, starlette.routing.Mount ─
    # starlette core (responses/requests/routing) is already stubbed above.
    # server.py additionally imports starlette.applications.Starlette and
    # starlette.routing.Mount — add those if starlette is already installed.
    if "starlette" in sys.modules:
        starlette_mod2 = sys.modules["starlette"]
        starlette_responses2 = sys.modules.get("starlette.responses")
        starlette_routing2 = sys.modules.get("starlette.routing")

        # starlette.applications
        if "starlette.applications" not in sys.modules:
            st_app = types.ModuleType("starlette.applications")

            class Starlette:
                def __init__(self, *args: Any, **kwargs: Any) -> None:
                    pass

            st_app.Starlette = Starlette  # type: ignore[attr-defined]
            starlette_mod2.applications = st_app  # type: ignore[attr-defined]
            sys.modules["starlette.applications"] = st_app

        # starlette.websockets (imported in a try/except in server.py)
        if "starlette.websockets" not in sys.modules:
            st_ws = types.ModuleType("starlette.websockets")

            class WebSocket:
                def __init__(self, scope: Any, receive: Any, send: Any) -> None:
                    self.scope = scope
                    self._receive = receive
                    self._send = send

                async def accept(self, *args: Any, **kwargs: Any) -> None:
                    pass

                async def close(self, *args: Any, **kwargs: Any) -> None:
                    pass

                async def receive(self) -> dict:
                    return {"type": "websocket.disconnect"}

                async def send_text(self, data: str) -> None:
                    pass

                async def send_bytes(self, data: bytes) -> None:
                    pass

            class WebSocketDisconnect(Exception):
                pass

            st_ws.WebSocket = WebSocket  # type: ignore[attr-defined]
            st_ws.WebSocketDisconnect = WebSocketDisconnect  # type: ignore[attr-defined]
            starlette_mod2.websockets = st_ws  # type: ignore[attr-defined]
            sys.modules["starlette.websockets"] = st_ws

        # starlette.routing.Mount (may not exist in existing stub)
        if starlette_routing2 is not None and not hasattr(starlette_routing2, "Mount"):
            class Mount:
                def __init__(self, *args: Any, **kwargs: Any) -> None:
                    pass

            starlette_routing2.Mount = Mount  # type: ignore[attr-defined]

    # ── websockets (optional; server.py uses try/except) ──────────────────────
    if "websockets" not in sys.modules:
        ws_mod = types.ModuleType("websockets")
        ws_exc = types.ModuleType("websockets.exceptions")

        class ConnectionClosedError(Exception):
            pass

        ws_exc.ConnectionClosedError = ConnectionClosedError  # type: ignore[attr-defined]
        ws_mod.exceptions = ws_exc  # type: ignore[attr-defined]
        ws_mod._unit_test_stub = True  # type: ignore[attr-defined]
        sys.modules.update({
            "websockets": ws_mod,
            "websockets.exceptions": ws_exc,
        })


# Install stubs at module import time (before any transport module is loaded)
_install_transport_stubs()


# ── Autouse fixture: block registry I/O ──────────────────────────────────────

@pytest.fixture(autouse=True)
def _block_registry_io(request):
    """Prevent unit tests from writing to /data.

    CrewRegistry.__enter__ calls _load_registry(); __exit__ calls _save_registry().
    Without these patches, any test that touches a ``with registry:`` block
    would attempt to access /data, which does not exist in test environments.

    Excluded: test_registry_lock.py exercises real file I/O under a tmpdir.
    """
    if "test_registry_lock" in request.fspath.basename:
        yield
        return

    import transport.registry as _reg_mod
    with (
        patch.object(_reg_mod, "_load_registry", return_value={"crews": {}}),
        patch.object(_reg_mod, "_save_registry"),
    ):
        yield


# ── Pytest marks ─────────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks integration tests")


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def fake_podman() -> FakePodmanClient:
    """Return a fresh FakePodmanClient with no scripted state."""
    return FakePodmanClient()


@pytest.fixture
def fake_podman_with_sentinel(tmp_path):
    """Return a FakePodmanClient pre-scripted with a sentinel file.

    The sentinel content is ``captain_id=test-crew\\ncompleted_at=2026-01-01T00:00:00Z\\n``
    and the container is named ``gs-test-crew``.
    """
    podman = FakePodmanClient()
    sentinel_content = b"captain_id=test-crew\ncompleted_at=2026-01-01T00:00:00Z\nreason=standing orders met\n"
    podman.set_archive_file(
        container="gs-test-crew",
        path="/home/kirocrew/workplace/kirocrew-workspace/.captain_done",
        content=sentinel_content,
        filename=".captain_done",
    )
    return podman
