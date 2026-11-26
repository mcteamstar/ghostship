"""Unit tests for the ga-radar server.py (TRN-286).

Tests call the ASGI app directly with the installed Starlette and HTTP
libraries. External HTTP is intercepted by an in-process MockTransport.

Covers:
  - GET /health  — returns 200 {"status": "ok"}
  - GET /api/crews with a mocked transport response — returns correct payload
  - GET /api/crews with transport unreachable — returns 502 with error JSON
  - GET /  — returns HTML (index.html)
  - GET /static/assets/*   — hashed bundle files, immutable cache (TRN-371)
  - GET /static/*.js|css  — removed source modules answer 404 (TRN-371)
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Ensure the radar package is importable without installing.
# ---------------------------------------------------------------------------
_RADAR_DIR = Path(__file__).parents[2] / "radar"

import importlib.util as _importlib_util
import pytest

# (pytestmark slow removed — test hang was caused by _make_scope missing the ASGI
# spec_version field; fixed below.  The slow marker band-aid is gone per TRN-296.)

_radar_server_module = None


def _import_radar_server():
    global _radar_server_module
    if _radar_server_module is not None:
        return _radar_server_module

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
# Minimal ASGI test harness that invokes the installed Starlette app in-process.
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


def _mock_transport(server, *, response=None, request_error=False):
    """Patch the client's transport to return real HTTP responses offline."""
    client_library = server.httpx
    if response is None:
        response = (200, b"{}")

    def handle(request):
        if request_error:
            raise client_library.ConnectError("connection refused", request=request)
        status, content = response
        return client_library.Response(status, content=content, request=request)

    real_async_client = client_library.AsyncClient
    transport = client_library.MockTransport(handle)

    def async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    return patch.object(server.httpx, "AsyncClient", side_effect=async_client)


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


class TestRadarApiCrewsSuccess(unittest.TestCase):
    """GET /api/crews proxies to transport and returns the payload."""


    def test_returns_fleet_payload(self):
        server = _import_radar_server()
        mock_payload = {
            "crews": [{"crew_id": "alpha", "status": "running"}],
            "active_crews": 1,
            "max_active_crews": 3,
            "host_memory_available_gb": 8.0,
        }
        mock_transport = _mock_transport(server, response=(200, json.dumps(mock_payload).encode()))
        scope = _make_scope("GET", "/api/crews")

        with mock_transport:
            messages, body = _run(_call(server.app, scope))

        self.assertEqual(_status_of(messages), 200)
        data = json.loads(body)
        self.assertIn("crews", data)
        self.assertEqual(len(data["crews"]), 1)
        self.assertEqual(data["crews"][0]["crew_id"], "alpha")


class TestRadarApiCrewsTransportDown(unittest.TestCase):
    """GET /api/crews returns 502 when transport is unreachable."""


    def test_returns_502_on_request_error(self):
        server = _import_radar_server()
        mock_transport = _mock_transport(server, request_error=True)
        scope = _make_scope("GET", "/api/crews")

        with mock_transport:
            messages, body = _run(_call(server.app, scope))

        self.assertEqual(_status_of(messages), 502)
        data = json.loads(body)
        self.assertIn("error", data)
        self.assertEqual(data["error"], "transport unreachable")

    def test_returns_502_on_transport_error_status(self):
        server = _import_radar_server()
        mock_transport = _mock_transport(server, response=(500, b"Internal Server Error"))
        scope = _make_scope("GET", "/api/crews")

        with mock_transport:
            messages, body = _run(_call(server.app, scope))

        self.assertEqual(_status_of(messages), 502)
        data = json.loads(body)
        self.assertIn("error", data)


BUNDLE_INDEX = (
    b"<!DOCTYPE html><html><head><title>Ghostship Fleet Radar</title></head><body>"
    b"<div id=\"root\"></div>"
    b"<script type=\"module\" crossorigin src=\"/static/assets/app-1a2b3c.js\"></script>"
    b"</body></html>"
)
BUNDLE_JS = b"export const radar = 'bundle';\n" + b"// padding\n" * 20
BUNDLE_CSS = b"body { color: #0f172a; }\n" + b"/* padding */\n" * 20


def _write_bundle(root: Path) -> Path:
    """Write a fixture shaped like the Vite output: index.html plus hashed assets/."""
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_bytes(BUNDLE_INDEX)
    (root / "assets" / "app-1a2b3c.js").write_bytes(BUNDLE_JS)
    (root / "assets" / "style-4d5e6f.css").write_bytes(BUNDLE_CSS)
    return root


class TestRadarBundleServing(unittest.TestCase):
    """GET / and /static/* serve the built bundle with the TRN-371 cache policy.

    Uses a fixture bundle rather than radar/static, so these checks do not depend on
    the committed source tree (which holds no built output).
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.bundle = _write_bundle(Path(tmp.name) / "static")
        self.server = _import_radar_server()
        self.app = self.server.build_app(self.bundle)

    def _get(self, path: str):
        return _run(_call(self.app, _make_scope("GET", path)))

    def test_index_is_the_built_page(self):
        messages, body = self._get("/")
        self.assertEqual(_status_of(messages), 200)
        self.assertIn("text/html", _headers_of(messages).get("content-type", ""))
        self.assertEqual(body, BUNDLE_INDEX)

    def test_index_is_revalidated(self):
        messages, _body = self._get("/")
        self.assertEqual(_headers_of(messages).get("cache-control"), "no-cache")

    def test_hashed_script_is_served_with_javascript_type_and_immutable_cache(self):
        messages, body = self._get("/static/assets/app-1a2b3c.js")
        self.assertEqual(_status_of(messages), 200)
        self.assertIn("javascript", _headers_of(messages).get("content-type", ""))
        self.assertEqual(body, BUNDLE_JS)
        self.assertEqual(_headers_of(messages).get("cache-control"), self.server._IMMUTABLE)
        self.assertIn("immutable", _headers_of(messages).get("cache-control", ""))
        self.assertIn("max-age=31536000", _headers_of(messages).get("cache-control", ""))

    def test_hashed_stylesheet_is_served_as_css_and_immutable(self):
        messages, body = self._get("/static/assets/style-4d5e6f.css")
        self.assertEqual(_status_of(messages), 200)
        self.assertIn("css", _headers_of(messages).get("content-type", ""))
        self.assertEqual(body, BUNDLE_CSS)
        self.assertIn("immutable", _headers_of(messages).get("cache-control", ""))

    def test_hashed_asset_revalidated_with_a_304_keeps_the_immutable_cache(self):
        # A browser that revalidates a cached hashed asset gets a 304. That answer must
        # not overwrite the long-lived policy with "no-cache".
        messages, _body = self._get("/static/assets/app-1a2b3c.js")
        etag = _headers_of(messages).get("etag")
        self.assertIsNotNone(etag)
        scope = _make_scope("GET", "/static/assets/app-1a2b3c.js")
        scope["headers"] = [(b"if-none-match", etag.encode())]
        messages, _body = _run(_call(self.app, scope))
        self.assertEqual(_status_of(messages), 304)
        self.assertEqual(_headers_of(messages).get("cache-control"), self.server._IMMUTABLE)

    def test_non_hashed_file_under_static_is_revalidated(self):
        messages, body = self._get("/static/index.html")
        self.assertEqual(_status_of(messages), 200)
        self.assertEqual(body, BUNDLE_INDEX)
        self.assertEqual(_headers_of(messages).get("cache-control"), "no-cache")

    def test_removed_source_modules_are_not_served(self):
        for path in (
            "/static/main.js", "/static/render.js", "/static/app.js", "/static/state.js",
            "/static/data.js", "/static/format.js", "/static/style.css",
        ):
            with self.subTest(path=path):
                messages, body = self._get(path)
                self.assertEqual(_status_of(messages), 404)
                self.assertNotIn(b"<html", body.lower())

    def test_missing_asset_is_404_and_never_the_page(self):
        messages, body = self._get("/static/assets/missing.js")
        self.assertEqual(_status_of(messages), 404)
        self.assertNotEqual(body, BUNDLE_INDEX)
        self.assertNotIn(b"<html", body.lower())

    def test_missing_hashed_looking_asset_is_not_cached_as_immutable(self):
        messages, _body = self._get("/static/assets/app-ffffff.js")
        self.assertEqual(_status_of(messages), 404)
        self.assertNotIn("immutable", _headers_of(messages).get("cache-control", ""))

    def test_unknown_api_path_is_404_and_not_html(self):
        for path in ("/api/unknown", "/api/crews/alpha/unknown", "/api/"):
            with self.subTest(path=path):
                messages, body = self._get(path)
                self.assertEqual(_status_of(messages), 404)
                self.assertNotIn("text/html", _headers_of(messages).get("content-type", ""))
                self.assertNotEqual(body, BUNDLE_INDEX)

    def test_static_directory_listing_and_traversal_are_404(self):
        for path in ("/static/assets", "/static/assets/../../index.html"):
            with self.subTest(path=path):
                messages, body = self._get(path)
                self.assertEqual(_status_of(messages), 404)
                self.assertNotEqual(body, BUNDLE_INDEX)

    def test_missing_bundle_answers_404_not_a_server_error(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app = self.server.build_app(Path(tmp.name))
        messages, body = _run(_call(app, _make_scope("GET", "/")))
        self.assertEqual(_status_of(messages), 404)
        self.assertIn(b"not built", body)
        messages, _body = _run(_call(app, _make_scope("GET", "/static/assets/app-1a2b3c.js")))
        self.assertEqual(_status_of(messages), 404)


class TestRadarBundleBuildLayout(unittest.TestCase):
    """The module-level app serves the directory the image copies the bundle into."""

    def test_default_static_directory_is_next_to_server_py(self):
        server = _import_radar_server()
        self.assertEqual(server._STATIC_DIR, _RADAR_DIR / "static")

    def test_module_app_uses_the_same_routes_as_build_app(self):
        server = _import_radar_server()
        paths = {getattr(r, "path", None) for r in server.app.routes}
        self.assertTrue({"/", "/health", "/api/crews", "/static"} <= paths)


class TestRadarApiCrewAgents(unittest.TestCase):
    """GET /api/crews/{crew_id}/agents — proxy to transport per-crew agents endpoint (TRN-304)."""

    def _make_agents_scope(self, crew_id: str) -> dict:
        scope = _make_scope("GET", f"/api/crews/{crew_id}/agents")
        scope["path_params"] = {"crew_id": crew_id}
        return scope


    def _call_handler(self, crew_id: str, *, response=None, request_error=False) -> tuple:
        server = _import_radar_server()
        mock_transport = _mock_transport(server, response=response, request_error=request_error)
        scope = self._make_agents_scope(crew_id)
        messages, send = _collect_send()

        async def _invoke():
            from starlette.requests import Request
            req = Request(scope, _receive)
            resp = await server.api_crew_agents(req)
            await resp(scope, _receive, send)

        with mock_transport:
            _run(_invoke())
        return messages, _body_of(messages)

    def test_forwards_to_transport_and_returns_payload(self):
        """Successful proxy: returns transport's JSON response unchanged."""
        import json as _json
        payload = {"agents": [
            {"task_id": "t1", "agent": "ghost", "done": False, "elapsed_secs": 10}
        ]}
        body_bytes = _json.dumps(payload).encode()
        messages, body = self._call_handler("alpha", response=(200, body_bytes))
        self.assertEqual(_status_of(messages), 200)
        data = _json.loads(body)
        self.assertIn("agents", data)
        self.assertEqual(len(data["agents"]), 1)
        self.assertEqual(data["agents"][0]["task_id"], "t1")

    def test_returns_502_on_request_error(self):
        """Transport unreachable → 502."""
        import json as _json
        messages, body = self._call_handler("beta", request_error=True)
        self.assertEqual(_status_of(messages), 502)
        data = _json.loads(body)
        self.assertIn("error", data)

    def test_returns_502_on_transport_error_status(self):
        """Transport returns non-200 → 502."""
        import json as _json
        messages, body = self._call_handler("gamma", response=(404, b"not found"))
        self.assertEqual(_status_of(messages), 502)
        data = _json.loads(body)
        self.assertIn("error", data)


class TestRadarApiCrewMailSubjects(unittest.TestCase):
    """GET /api/crews/{crew_id}/mail-subjects — proxy to transport (TRN-370)."""

    def _call(self, crew_id, *, status=200, content=b"{}", request_error=False):
        server = _import_radar_server()
        seen: dict = {}
        client_library = server.httpx

        def handle(request):
            seen["url"] = str(request.url)
            seen["token"] = request.headers.get("x-transport-token")
            if request_error:
                raise client_library.ConnectError("connection refused", request=request)
            return client_library.Response(status, content=content, request=request)

        transport = client_library.MockTransport(handle)
        real_async_client = client_library.AsyncClient

        def async_client(*args, **kwargs):
            kwargs["transport"] = transport
            return real_async_client(*args, **kwargs)

        scope = _make_scope("GET", f"/api/crews/{crew_id}/mail-subjects")
        scope["path_params"] = {"crew_id": crew_id}
        messages, send = _collect_send()

        async def _invoke():
            from starlette.requests import Request
            req = Request(scope, _receive)
            resp = await server.api_crew_mail_subjects(req)
            await resp(scope, _receive, send)

        with patch.object(server, "_TRANSPORT_SECRET", "test-transport-secret"), \
             patch.object(server.httpx, "AsyncClient", side_effect=async_client):
            _run(_invoke())
        return messages, _body_of(messages), seen

    def test_forwards_transport_token_to_internal_route(self):
        messages, _body, seen = self._call("alpha", content=b'{"mailboxes": {}}')
        self.assertTrue(seen["url"].endswith("/internal/crews/alpha/mail-subjects"))
        self.assertEqual(seen["token"], "test-transport-secret")

    def test_passes_subject_only_payload_through(self):
        payload = {"mailboxes": {"ghost": ["hello"], "admiral": []}}
        messages, body, _seen = self._call("alpha", content=json.dumps(payload).encode())
        self.assertEqual(_status_of(messages), 200)
        self.assertEqual(json.loads(body), payload)

    def test_transport_mailbox_unavailable_becomes_502(self):
        messages, body, _seen = self._call("alpha", status=503, content=b'{"error": "x"}')
        self.assertEqual(_status_of(messages), 502)
        self.assertEqual(json.loads(body)["error"], "transport error")

    def test_transport_unreachable_becomes_502(self):
        messages, body, _seen = self._call("beta", request_error=True)
        self.assertEqual(_status_of(messages), 502)
        self.assertEqual(json.loads(body), {"error": "transport unreachable"})


class TestRadarApiCrewAuthRefresh(unittest.TestCase):
    """POST /api/crews/{crew_id}/auth/refresh — same-origin proxy to transport (TRN-367).

    Drives the whole ASGI app so routing, method filtering and path parameters
    are exercised, with a mock transport that records what Radar sends upstream.
    """

    SECRET = "test-transport-secret"
    HOST = "radar.example:64057"
    ORIGIN = "https://radar.example:64057"
    OUTCOMES = (
        "refreshed", "pending_on_wake", "current",
        "recreate_required", "credential_missing", "refresh_failed",
    )

    def _post(
        self,
        crew_id="alpha",
        *,
        headers=None,
        method="POST",
        status=200,
        content=b"{}",
        request_error=None,
    ):
        """Return (messages, body, upstream) for one request through the app."""
        server = _import_radar_server()
        client_library = server.httpx
        upstream: dict = {"requests": []}

        def handle(request):
            upstream["requests"].append(request)
            if request_error is not None:
                raise request_error(request)
            return client_library.Response(status, content=content, request=request)

        transport = client_library.MockTransport(handle)
        real_async_client = client_library.AsyncClient

        def async_client(*args, **kwargs):
            upstream["timeout"] = kwargs.get("timeout")
            kwargs["transport"] = transport
            return real_async_client(*args, **kwargs)

        if headers is None:
            headers = {"host": self.HOST, "origin": self.ORIGIN}
        scope = _make_scope(method, f"/api/crews/{crew_id}/auth/refresh")
        scope["headers"] = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        with patch.object(server, "_TRANSPORT_SECRET", self.SECRET), \
             patch.object(server.httpx, "AsyncClient", side_effect=async_client):
            messages, body = _run(_call(server.app, scope))
        return messages, body, upstream

    # ── proxying ──────────────────────────────────────────────────────────────

    def test_forwards_post_to_the_internal_route_with_the_transport_token(self):
        messages, _body, upstream = self._post("alpha")
        self.assertEqual(_status_of(messages), 200)
        (request,) = upstream["requests"]
        self.assertEqual(request.method, "POST")
        self.assertTrue(str(request.url).endswith("/internal/crews/alpha/auth/refresh"))
        self.assertEqual(request.headers.get("x-transport-token"), self.SECRET)

    def test_forwards_no_browser_data_and_no_credential(self):
        headers = {
            "host": self.HOST,
            "origin": self.ORIGIN,
            "cookie": "gs_session=browser-session-cookie",
            "authorization": "Bearer browser-supplied-key",
            "content-type": "application/json",
        }
        _messages, _body, upstream = self._post("alpha", headers=headers)
        (request,) = upstream["requests"]
        sent = {name.lower() for name in request.headers.keys()}
        for browser_header in ("cookie", "authorization", "origin"):
            self.assertNotIn(browser_header, sent)
        self.assertEqual(request.content, b"")
        self.assertEqual(request.url.query, b"")

    def test_passes_every_transport_outcome_through_unmodified(self):
        for status in self.OUTCOMES:
            with self.subTest(status=status):
                payload = json.dumps(
                    {"status": status, "crew_id": "alpha", "backend": "kiro",
                     "profile": "default", "message": f"message for {status}"},
                ).encode()
                messages, body, _upstream = self._post("alpha", content=payload)
                self.assertEqual(_status_of(messages), 200)
                self.assertEqual(body, payload)
                self.assertIn("application/json", _headers_of(messages)["content-type"])

    def test_crew_id_is_taken_from_the_path(self):
        _messages, _body, upstream = self._post("crew-2")
        self.assertTrue(str(upstream["requests"][0].url).endswith("/internal/crews/crew-2/auth/refresh"))

    def test_refresh_is_given_longer_than_a_fleet_read(self):
        server = _import_radar_server()
        _messages, _body, upstream = self._post("alpha")
        self.assertEqual(upstream["timeout"], server._AUTH_REFRESH_TIMEOUT_SECS)
        self.assertGreater(server._AUTH_REFRESH_TIMEOUT_SECS, 10.0)

    def test_refresh_bound_is_60_seconds_and_a_slow_refresh_is_not_cut_short(self):
        # The browser bound (75 s) must stay above this one, and this one above a
        # transport step that legitimately takes most of a minute.
        server = _import_radar_server()
        self.assertEqual(server._AUTH_REFRESH_TIMEOUT_SECS, 60.0)
        _messages, _body, upstream = self._post("alpha")
        self.assertEqual(upstream["timeout"], 60.0)

    # ── safe failures ─────────────────────────────────────────────────────────

    def test_transport_unreachable_is_a_safe_502(self):
        def refused(request):
            return _import_radar_server().httpx.ConnectError(
                f"connection refused to {self.SECRET} at ga-transport", request=request,
            )

        with self.assertLogs("radar", level="ERROR") as captured:
            messages, body, _upstream = self._post("alpha", request_error=refused)
        self.assertEqual(_status_of(messages), 502)
        self.assertEqual(json.loads(body), {"error": "transport unreachable"})
        self.assertNotIn(self.SECRET.encode(), body)
        self.assertNotIn(self.SECRET, "\n".join(captured.output))

    def test_transport_timeout_is_a_safe_502(self):
        def timed_out(request):
            return _import_radar_server().httpx.ReadTimeout("read timed out", request=request)

        with self.assertLogs("radar", level="ERROR"):
            messages, body, _upstream = self._post("alpha", request_error=timed_out)
        self.assertEqual(_status_of(messages), 502)
        self.assertEqual(json.loads(body), {"error": "transport unreachable"})

    def test_non_200_from_transport_is_a_502_naming_only_the_status(self):
        for status in (401, 404, 500, 503):
            with self.subTest(status=status):
                with self.assertLogs("radar", level="ERROR") as captured:
                    messages, body, _upstream = self._post(
                        "alpha", status=status, content=b'{"error": "upstream detail secret-body"}',
                    )
                self.assertEqual(_status_of(messages), 502)
                self.assertEqual(json.loads(body), {"error": "transport error", "status_code": status})
                self.assertNotIn(b"secret-body", body)
                self.assertNotIn("secret-body", "\n".join(captured.output))

    # ── same-origin guard ─────────────────────────────────────────────────────

    def _assert_rejected(self, headers, label):
        with self.subTest(case=label):
            messages, body, upstream = self._post("alpha", headers=headers)
            self.assertEqual(_status_of(messages), 403)
            self.assertEqual(json.loads(body), {"error": "cross-origin request rejected"})
            self.assertEqual(upstream["requests"], [], "transport must not be called")

    def test_missing_origin_is_rejected_without_calling_transport(self):
        self._assert_rejected({"host": self.HOST}, "no origin header")

    def test_cross_origin_is_rejected_without_calling_transport(self):
        for label, origin in (
            ("other host", "https://evil.example"),
            ("other host same port", "https://evil.example:64057"),
            ("same host other port", "https://radar.example:64058"),
            ("same host no port", "https://radar.example"),
            ("subdomain", "https://sub.radar.example:64057"),
            ("suffix attack", "https://radar.example:64057.evil.example"),
            ("userinfo", "https://radar.example:64057@evil.example"),
            ("opaque origin", "null"),
            ("empty", ""),
            ("not a url", "radar.example:64057"),
            ("file scheme", "file://radar.example:64057"),
            ("javascript scheme", "javascript://radar.example:64057"),
            ("with path", "https://radar.example:64057/"),
            ("with path segment", "https://radar.example:64057/x"),
            ("with query", "https://radar.example:64057?x=1"),
            ("with fragment", "https://radar.example:64057#x"),
        ):
            self._assert_rejected({"host": self.HOST, "origin": origin}, label)

    def test_malformed_origin_is_rejected(self):
        self._assert_rejected({"host": self.HOST, "origin": "http://[::1"}, "unbalanced IPv6 bracket")

    def test_missing_host_is_rejected(self):
        self._assert_rejected({"origin": self.ORIGIN}, "no host header")

    def test_duplicate_origin_headers_are_rejected(self):
        server = _import_radar_server()
        scope = _make_scope("POST", "/api/crews/alpha/auth/refresh")
        scope["headers"] = [
            (b"host", self.HOST.encode()),
            (b"origin", self.ORIGIN.encode()),
            (b"origin", self.ORIGIN.encode()),
        ]
        called = []
        with patch.object(server.httpx, "AsyncClient", side_effect=lambda *a, **k: called.append(1)):
            messages, _body = _run(_call(server.app, scope))
        self.assertEqual(_status_of(messages), 403)
        self.assertEqual(called, [])

    def test_origin_check_runs_before_crew_validation_and_transport(self):
        messages, body, upstream = self._post("NOT A CREW", headers={"host": self.HOST})
        self.assertEqual(_status_of(messages), 403)
        self.assertEqual(upstream["requests"], [])

    def test_same_origin_is_accepted(self):
        for label, host, origin in (
            ("https with port", "radar.example:64057", "https://radar.example:64057"),
            ("http with port", "radar.example:64057", "http://radar.example:64057"),
            ("https default port", "radar.example", "https://radar.example"),
            ("localhost dev", "localhost:64057", "http://localhost:64057"),
            ("ipv4", "127.0.0.1:64057", "http://127.0.0.1:64057"),
            ("ipv6", "[::1]:64057", "http://[::1]:64057"),
            ("case differs", "Radar.Example:64057", "https://radar.example:64057"),
        ):
            with self.subTest(case=label):
                messages, _body, upstream = self._post("alpha", headers={"host": host, "origin": origin})
                self.assertEqual(_status_of(messages), 200)
                self.assertEqual(len(upstream["requests"]), 1)

    def test_origin_guard_helper_returns_booleans_for_a_direct_call(self):
        from starlette.requests import Request
        server = _import_radar_server()

        def request(headers):
            scope = _make_scope("POST", "/x")
            scope["headers"] = [(k.encode(), v.encode()) for k, v in headers]
            return Request(scope)

        self.assertTrue(server._is_same_origin(request([("host", "a:1"), ("origin", "http://a:1")])))
        self.assertFalse(server._is_same_origin(request([("host", "a:1")])))
        self.assertFalse(server._is_same_origin(request([("origin", "http://a:1")])))
        self.assertFalse(server._is_same_origin(request([("host", "a:1"), ("origin", "http://b:1")])))

    # ── routing ───────────────────────────────────────────────────────────────

    def test_only_post_is_routed(self):
        for method in ("GET", "PUT", "DELETE", "PATCH"):
            with self.subTest(method=method):
                messages, _body, upstream = self._post("alpha", method=method)
                self.assertEqual(_status_of(messages), 405)
                self.assertEqual(upstream["requests"], [])

    def test_invalid_crew_ids_are_not_proxied(self):
        for crew_id in ("..", ".", "Alpha", "a" * 51, "-alpha", "alpha-", "a_b", "a%3Fb", "a%2Fb", "a b"):
            with self.subTest(crew_id=crew_id):
                messages, body, upstream = self._post(crew_id)
                self.assertIn(_status_of(messages), (404,))
                self.assertEqual(upstream["requests"], [])

    def test_valid_crew_id_shapes_are_proxied(self):
        for crew_id in ("a", "ab", "a-b", "alpha-2", "a" * 50, "0"):
            with self.subTest(crew_id=crew_id):
                messages, _body, upstream = self._post(crew_id)
                self.assertEqual(_status_of(messages), 200)
                self.assertEqual(len(upstream["requests"]), 1)

    def test_existing_read_routes_are_unchanged(self):
        server = _import_radar_server()
        routes = {getattr(r, "path", None): getattr(r, "methods", None) for r in server.app.routes}
        self.assertEqual(routes["/api/crews/{crew_id}/auth/refresh"], {"POST"})
        for path in ("/api/crews", "/api/crews/{crew_id}/agents", "/api/crews/{crew_id}/mail-subjects"):
            self.assertIn("GET", routes[path])
            self.assertNotIn("POST", routes[path])


if __name__ == "__main__":
    unittest.main()
