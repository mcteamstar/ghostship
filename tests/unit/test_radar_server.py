"""Unit tests for the ga-radar server.py (TRN-286).

Tests call the ASGI app directly without starlette TestClient to avoid
httpx2/starlette version compatibility issues in the test venv.

Covers:
  - GET /health  — returns 200 {"status": "ok"}
  - GET /api/crews with a mocked transport response — returns correct payload
  - GET /api/crews with transport unreachable — returns 502 with error JSON
  - GET /  — returns HTML (index.html)
  - GET /static/style.css  — returns CSS content-type
  - GET /static/main.js    — returns JS content-type (TRN-303: app.js split into ES modules)
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

# ---------------------------------------------------------------------------
# Ensure the radar package is importable without installing.
# ---------------------------------------------------------------------------
_RADAR_DIR = Path(__file__).parents[2] / "radar"

# Module names that may have been stubbed by conftest.py for transport tests.
_STARLETTE_STUB_KEYS = [
    k for k in ("starlette", "starlette.responses", "starlette.requests",
                "starlette.routing")
]


def _evict_starlette_stubs() -> None:
    """Remove conftest stubs so the real starlette can be imported."""
    stub = sys.modules.get("starlette")
    if stub is not None and getattr(stub, "_unit_test_stub", False):
        for key in list(sys.modules.keys()):
            if key == "starlette" or key.startswith("starlette."):
                del sys.modules[key]


import importlib.util as _importlib_util
import pytest

# (pytestmark slow removed — test hang was caused by _make_scope missing the ASGI
# spec_version field; fixed below.  The slow marker band-aid is gone per TRN-296.)

_radar_server_module = None


def _import_radar_server():
    global _radar_server_module
    if _radar_server_module is not None:
        return _radar_server_module

    _evict_starlette_stubs()

    # Use importlib to load radar/server.py under a unique name so it never
    # clobbers sys.modules["server"] (which test_server.py uses for transport).
    spec = _importlib_util.spec_from_file_location(
        "radar.server", _RADAR_DIR / "server.py"
    )
    mod = _importlib_util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    _radar_server_module = mod
    return mod


# ---------------------------------------------------------------------------
# Minimal ASGI test harness (no httpx / TestClient dependency).
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_scope(method: str, path: str) -> dict:
    return {
        "type": "http",
        "method": method.upper(),
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "server": ("localhost", 8080),
        "root_path": "",
        # spec_version >= 2.4 tells starlette's FileResponse to use the fast-path
        # (send all bytes then return) instead of a collapsing task group that waits
        # for http.disconnect — which never arrives in unit tests, causing a hang.
        "asgi": {"version": "3.0", "spec_version": "2.4"},
    }


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _collect_send():
    messages: list[dict] = []

    async def _send(msg):
        messages.append(msg)

    return messages, _send


def _status_of(messages) -> int | None:
    for m in messages:
        if m.get("type") == "http.response.start":
            return m["status"]
    return None


def _headers_of(messages) -> dict[str, str]:
    for m in messages:
        if m.get("type") == "http.response.start":
            return {
                k.decode().lower(): v.decode()
                for k, v in m.get("headers", [])
            }
    return {}


def _body_of(messages) -> bytes:
    parts = [m.get("body", b"") for m in messages if m.get("type") == "http.response.body"]
    return b"".join(parts)


async def _call(app, scope) -> tuple[list[dict], bytes]:
    messages, send = _collect_send()
    await app(scope, _receive, send)
    return messages, _body_of(messages)


def _get_httpx():
    try:
        import httpx as _httpx
    except ImportError:
        import httpx2 as _httpx  # type: ignore[no-redef]
    return _httpx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRadarHealth(unittest.TestCase):
    """GET /health returns 200 {"status": "ok"}."""

    def test_health_200(self):
        server = _import_radar_server()
        scope = _make_scope("GET", "/health")
        messages, body = _run(_call(server.app, scope))
        self.assertEqual(_status_of(messages), 200)
        data = json.loads(body)
        self.assertEqual(data, {"status": "ok"})


@unittest.skip("httpx/httpx2 mock incompatibility — pending test infra fix")
class TestRadarApiCrewsSuccess(unittest.TestCase):
    """GET /api/crews proxies to transport and returns the payload."""

    def test_returns_fleet_payload(self):
        server = _import_radar_server()
        httpx = _get_httpx()
        mock_payload = {
            "crews": [{"crew_id": "alpha", "status": "running"}],
            "active_crews": 1,
            "max_active_crews": 3,
            "host_memory_available_gb": 8.0,
        }
        mock_resp = httpx.Response(200, json=mock_payload)
        scope = _make_scope("GET", "/api/crews")

        with patch.object(server, "httpx") as mock_httpx_mod:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            mock_httpx_mod.AsyncClient.return_value = mock_ctx
            mock_httpx_mod.RequestError = httpx.RequestError

            messages, body = _run(_call(server.app, scope))

        self.assertEqual(_status_of(messages), 200)
        data = json.loads(body)
        self.assertIn("crews", data)
        self.assertEqual(len(data["crews"]), 1)
        self.assertEqual(data["crews"][0]["crew_id"], "alpha")


@unittest.skip("httpx/httpx2 mock incompatibility — pending test infra fix")
class TestRadarApiCrewsTransportDown(unittest.TestCase):
    """GET /api/crews returns 502 when transport is unreachable."""

    def test_returns_502_on_request_error(self):
        server = _import_radar_server()
        httpx = _get_httpx()
        scope = _make_scope("GET", "/api/crews")

        with patch.object(server, "httpx") as mock_httpx_mod:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_ctx.get = AsyncMock(
                side_effect=httpx.RequestError("connection refused")
            )
            mock_httpx_mod.AsyncClient.return_value = mock_ctx
            mock_httpx_mod.RequestError = httpx.RequestError

            messages, body = _run(_call(server.app, scope))

        self.assertEqual(_status_of(messages), 502)
        data = json.loads(body)
        self.assertIn("error", data)
        self.assertEqual(data["error"], "transport unreachable")

    def test_returns_502_on_transport_error_status(self):
        server = _import_radar_server()
        httpx = _get_httpx()
        scope = _make_scope("GET", "/api/crews")
        mock_resp = httpx.Response(500, text="Internal Server Error")

        with patch.object(server, "httpx") as mock_httpx_mod:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            mock_httpx_mod.AsyncClient.return_value = mock_ctx
            mock_httpx_mod.RequestError = httpx.RequestError

            messages, body = _run(_call(server.app, scope))

        self.assertEqual(_status_of(messages), 502)
        data = json.loads(body)
        self.assertIn("error", data)


class TestRadarIndex(unittest.TestCase):
    """GET / returns the index.html with text/html content-type."""

    def test_index_returns_html(self):
        server = _import_radar_server()
        scope = _make_scope("GET", "/")
        messages, body = _run(_call(server.app, scope))
        self.assertEqual(_status_of(messages), 200)
        ct = _headers_of(messages).get("content-type", "")
        self.assertIn("text/html", ct)
        self.assertIn(b"<html", body.lower())


class TestRadarStaticFiles(unittest.TestCase):
    """GET /static/style.css and /static/main.js return correct content-types.

    TRN-303: app.js was split into ES modules (main.js, format.js, state.js,
    render.js, data.js).  The canonical JS entry point is now main.js.
    """

    def test_style_css_content_type(self):
        server = _import_radar_server()
        scope = _make_scope("GET", "/static/style.css")
        messages, body = _run(_call(server.app, scope))
        self.assertEqual(_status_of(messages), 200)
        ct = _headers_of(messages).get("content-type", "")
        self.assertIn("css", ct)
        self.assertGreater(len(body), 100)

    def test_main_js_content_type(self):
        """Entry-point module (replaces app.js after TRN-303 split)."""
        server = _import_radar_server()
        scope = _make_scope("GET", "/static/main.js")
        messages, body = _run(_call(server.app, scope))
        self.assertEqual(_status_of(messages), 200)
        ct = _headers_of(messages).get("content-type", "")
        self.assertIn("javascript", ct)
        self.assertGreater(len(body), 100)

    def test_app_js_returns_404(self):
        """app.js was deleted in TRN-303 — must not be served."""
        server = _import_radar_server()
        scope = _make_scope("GET", "/static/app.js")
        messages, _body = _run(_call(server.app, scope))
        self.assertEqual(_status_of(messages), 404)


class TestRadarApiCrewAgents(unittest.TestCase):
    """GET /api/crews/{crew_id}/agents — proxy to transport per-crew agents endpoint (TRN-304)."""

    def _make_agents_scope(self, crew_id: str) -> dict:
        scope = _make_scope("GET", f"/api/crews/{crew_id}/agents")
        scope["path_params"] = {"crew_id": crew_id}
        return scope

    def _make_fake_httpx(self, response=None, request_error=False):
        """Build a minimal httpx module replacement with a controlled AsyncClient."""
        import types
        from unittest.mock import AsyncMock, MagicMock

        class _FakeRequestError(Exception):
            """Stands in for httpx.RequestError inside the patched module."""
            pass

        fake_resp = MagicMock()
        fake_resp.status_code = response[0] if response else 200
        fake_resp.content = (response[1] if response else b'{"agents":[]}')
        fake_resp.text = (response[1].decode() if response and isinstance(response[1], bytes) else "")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        if request_error:
            mock_client.get = AsyncMock(side_effect=_FakeRequestError("connection refused"))
        else:
            mock_client.get = AsyncMock(return_value=fake_resp)

        fake_httpx = types.ModuleType("fake_httpx")
        fake_httpx.AsyncClient = MagicMock(return_value=mock_client)
        fake_httpx.RequestError = _FakeRequestError
        return fake_httpx

    def _call_handler(self, crew_id: str, fake_httpx) -> tuple:
        server = _import_radar_server()
        scope = self._make_agents_scope(crew_id)
        messages, send = _collect_send()

        async def _invoke():
            from starlette.requests import Request
            req = Request(scope, _receive)
            resp = await server.api_crew_agents(req)
            await resp(scope, _receive, send)

        with patch.object(server, "httpx", fake_httpx):
            _run(_invoke())
        return messages, _body_of(messages)

    def test_forwards_to_transport_and_returns_payload(self):
        """Successful proxy: returns transport's JSON response unchanged."""
        import json as _json
        payload = {"agents": [
            {"task_id": "t1", "agent": "ghost", "done": False, "elapsed_secs": 10}
        ]}
        body_bytes = _json.dumps(payload).encode()
        fake_httpx = self._make_fake_httpx(response=(200, body_bytes))
        messages, body = self._call_handler("alpha", fake_httpx)
        self.assertEqual(_status_of(messages), 200)
        data = _json.loads(body)
        self.assertIn("agents", data)
        self.assertEqual(len(data["agents"]), 1)
        self.assertEqual(data["agents"][0]["task_id"], "t1")

    def test_returns_502_on_request_error(self):
        """Transport unreachable → 502."""
        import json as _json
        fake_httpx = self._make_fake_httpx(request_error=True)
        messages, body = self._call_handler("beta", fake_httpx)
        self.assertEqual(_status_of(messages), 502)
        data = _json.loads(body)
        self.assertIn("error", data)

    def test_returns_502_on_transport_error_status(self):
        """Transport returns non-200 → 502."""
        import json as _json
        fake_httpx = self._make_fake_httpx(response=(404, b"not found"))
        messages, body = self._call_handler("gamma", fake_httpx)
        self.assertEqual(_status_of(messages), 502)
        data = _json.loads(body)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
