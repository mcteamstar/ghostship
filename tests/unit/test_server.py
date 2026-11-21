"""Unit tests for transport/server.py utility functions and health handler.

Covers the pure utility functions in server.py and the minimal health endpoint:
- ``TestExtractCrewProxyParts``  — ``_extract_crew_proxy_parts`` path parsing
- ``TestSanitiseQueryString``    — ``_sanitise_query_string`` control-char stripping
- ``TestParseTtlSeconds``        — ``_parse_ttl_seconds`` duration parsing
- ``TestJwtExp``                 — ``_jwt_exp`` session_exp claim extraction
- ``TestCookieNearExpiry``       — ``_cookie_near_expiry`` expiry threshold logic
- ``TestHandleHealth``           — ``_handle_health`` ASGI handler smoke test

Design (see openspec/changes/trn-275-server-dashboard-unit-tests/design.md):
- Import only the specific utility functions needed — ``from transport.server
  import _jwt_exp, ...`` — to avoid pulling in the full server startup path.
  Tests use the installed Starlette, MCP, and Uvicorn dependencies.
- Tests are pure-function or minimal ASGI invocations with no live server.
- JWT payloads are constructed inline with base64 encoding — no real signing.

Dual-import shim (container flat layout vs. local dev package):
    try:
        import server as _server          # /app/server.py (container)
    except ModuleNotFoundError:
        from transport import server as _server   # local dev
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
import unittest
from dataclasses import replace
from unittest.mock import patch


# ── Shared ASGI helpers ───────────────────────────────────────────────────────

def _make_scope(method="GET", path="/", headers=None):
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "scheme": "http",
        "query_string": b"",
    }


def _collect_send():
    messages = []

    async def send(message):
        messages.append(message)

    return messages, send


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _run(coro):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _status_of(messages):
    for msg in messages:
        if msg.get("type") == "http.response.start":
            return msg.get("status")
    return None


def _body_of(messages):
    for msg in messages:
        if msg.get("type") == "http.response.body":
            return msg.get("body", b"")
    return b""


def _make_jwt(payload: dict, parts: int = 2) -> str:
    """Construct a minimal base64-encoded JWT token (no real signing needed).

    KiroCrew tokens are 2-part (payload.signature); standard JWTs are 3-part
    (header.payload.signature). Both formats are supported by _jwt_exp.
    """
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    )
    if parts == 3:
        header_b64 = (
            base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}')
            .rstrip(b"=")
            .decode()
        )
        return f"{header_b64}.{payload_b64}.fakesignature"
    # 2-part KiroCrew format: payload.signature
    return f"{payload_b64}.fakesignature"


class _MissingSecretFile:
    def is_file(self):
        return False


class _PresentSecretFile:
    def is_file(self):
        return True

    def read_text(self, **_kwargs):
        return "transport-secret"


class TestLoadTransportSecret(unittest.TestCase):
    """The internal-secret guard uses GA_TRANSPORT_BIND and supports both modes."""

    @staticmethod
    def _server_module():
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s

    def _patch_startup_config(
        self, server, required: bool, bind="192.168.1.10", **overrides,
    ):
        return patch.object(
            server,
            "cfg",
            replace(
                server.cfg,
                ga_transport_bind=bind,
                ga_require_secret_on_external_bind=required,
                **overrides,
            ),
        )

    def test_enabled_guard_refuses_start_without_secret(self):
        server = self._server_module()

        with self._patch_startup_config(server, required=True), patch.object(
            server, "Path", return_value=_MissingSecretFile()
        ), self.assertLogs(server.__name__, level="CRITICAL") as captured:
            with self.assertRaises(SystemExit) as exc_info:
                server._load_transport_secret()

        self.assertEqual(exc_info.exception.code, 1)
        self.assertIn("GA_TRANSPORT_SECRET is not set", "\n".join(captured.output))
        self.assertIn("192.168.1.10", "\n".join(captured.output))

    def test_disabled_guard_warns_and_continues_without_secret(self):
        server = self._server_module()

        with self._patch_startup_config(server, required=False), patch.object(
            server, "Path", return_value=_MissingSecretFile()
        ), self.assertLogs(server.__name__, level="CRITICAL") as captured:
            secret = server._load_transport_secret()

        self.assertEqual(secret, "")
        self.assertIn("pass-through mode", "\n".join(captured.output))
        self.assertIn("192.168.1.10", "\n".join(captured.output))

    def test_present_secret_allows_specific_external_bind(self):
        server = self._server_module()

        for required in (True, False):
            with self.subTest(required=required):
                with self._patch_startup_config(
                    server, required=required
                ), patch.object(
                    server, "Path", return_value=_PresentSecretFile()
                ), patch.object(server._security, "register_secret") as register:
                    secret = server._load_transport_secret()

                self.assertEqual(secret, "transport-secret")
                register.assert_called_once_with("transport-secret")

    def test_loopback_and_wildcard_binds_do_not_trigger_guard(self):
        server = self._server_module()

        for bind in ("127.0.0.1", "0.0.0.0"):
            for required in (True, False):
                with self.subTest(bind=bind, required=required):
                    with self._patch_startup_config(
                        server, required=required, bind=bind
                    ), patch.object(server, "Path", return_value=_MissingSecretFile()):
                        self.assertEqual(server._load_transport_secret(), "")

    def test_portal_host_and_api_key_do_not_satisfy_transport_guard(self):
        server = self._server_module()

        with self._patch_startup_config(
            server,
            required=True,
            ga_portal_host="127.0.0.1",
        ), patch.object(
            server, "GA_API_KEY", "portal-api-key"
        ), patch.object(server, "Path", return_value=_MissingSecretFile()):
            with self.assertRaises(SystemExit) as exc_info:
                server._load_transport_secret()

        self.assertEqual(exc_info.exception.code, 1)


# ── TestExtractCrewProxyParts ─────────────────────────────────────────────────


class TestExtractCrewProxyParts(unittest.TestCase):
    """_extract_crew_proxy_parts parses /crews/{crew_id}/{segment}/{sub_path}."""

    def _fn(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s._extract_crew_proxy_parts

    def test_valid_ui_path(self):
        fn = self._fn()
        self.assertEqual(fn("/crews/demo/ui"), ("demo", "ui", ""))

    def test_valid_ui_path_trailing_slash(self):
        fn = self._fn()
        self.assertEqual(fn("/crews/demo/ui/"), ("demo", "ui", ""))

    def test_valid_ui_path_with_sub_path(self):
        fn = self._fn()
        self.assertEqual(fn("/crews/demo/ui/app/page"), ("demo", "ui", "app/page"))

    def test_valid_api_path(self):
        fn = self._fn()
        self.assertEqual(fn("/crews/demo/api/spawn"), ("demo", "api", "spawn"))

    def test_short_path_returns_none(self):
        fn = self._fn()
        # Only /crews/<id> — no segment
        self.assertIsNone(fn("/crews/demo"))

    def test_wrong_prefix_returns_none(self):
        fn = self._fn()
        self.assertIsNone(fn("/notcrews/demo/ui"))

    def test_root_path_returns_none(self):
        fn = self._fn()
        self.assertIsNone(fn("/"))

    def test_empty_path_returns_none(self):
        fn = self._fn()
        self.assertIsNone(fn(""))


# ── TestSanitiseQueryString ───────────────────────────────────────────────────


class TestSanitiseQueryString(unittest.TestCase):
    """_sanitise_query_string strips control characters from raw query bytes."""

    def _fn(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s._sanitise_query_string

    def test_safe_passthrough(self):
        fn = self._fn()
        self.assertEqual(fn(b"foo=bar&baz=1"), "foo=bar&baz=1")

    def test_empty_bytes_returns_empty_string(self):
        fn = self._fn()
        self.assertEqual(fn(b""), "")

    def test_strips_null_byte(self):
        fn = self._fn()
        result = fn(b"q=hello\x00world")
        self.assertNotIn("\x00", result)
        self.assertIn("q=hello", result)
        self.assertIn("world", result)

    def test_strips_cr_lf(self):
        fn = self._fn()
        result = fn(b"q=hello\r\nX-Injected: 1")
        self.assertNotIn("\r", result)
        self.assertNotIn("\n", result)

    def test_strips_all_control_chars(self):
        fn = self._fn()
        # Control chars 0x00-0x1F and 0x7F should all be stripped.
        raw = b"safe" + bytes(range(0x00, 0x20)) + b"also_safe" + bytes([0x7F])
        result = fn(raw)
        self.assertEqual(result, "safealso_safe")

    def test_non_ascii_preserved(self):
        fn = self._fn()
        # Percent-encoded non-ASCII is preserved (latin-1 passthrough).
        self.assertEqual(fn(b"q=%C3%A9"), "q=%C3%A9")


# ── TestParseTtlSeconds ───────────────────────────────────────────────────────


class TestParseTtlSeconds(unittest.TestCase):
    """_parse_ttl_seconds converts duration strings to seconds."""

    def _fn(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s._parse_ttl_seconds

    def test_bare_integer_as_seconds(self):
        fn = self._fn()
        self.assertEqual(fn("3600"), 3600)

    def test_seconds_suffix(self):
        fn = self._fn()
        self.assertEqual(fn("90s"), 90)

    def test_minutes_suffix(self):
        fn = self._fn()
        self.assertEqual(fn("30m"), 1800)

    def test_hours_suffix(self):
        fn = self._fn()
        self.assertEqual(fn("24h"), 86400)

    def test_days_suffix(self):
        fn = self._fn()
        self.assertEqual(fn("2d"), 172800)

    def test_empty_string_returns_default(self):
        fn = self._fn()
        self.assertEqual(fn(""), 86400)

    def test_invalid_string_returns_default(self):
        fn = self._fn()
        self.assertEqual(fn("not_a_number"), 86400)

    def test_whitespace_around_value(self):
        fn = self._fn()
        self.assertEqual(fn("  12h  "), 43200)


# ── TestJwtExp ────────────────────────────────────────────────────────────────


class TestJwtExp(unittest.TestCase):
    """_jwt_exp extracts session_exp from a KiroCrew JWT without signature verification."""

    def _fn(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s._jwt_exp

    def test_2part_token_extracts_session_exp(self):
        fn = self._fn()
        exp = int(time.time()) + 86400
        token = _make_jwt({"session_exp": exp, "sub": "test"}, parts=2)
        self.assertEqual(fn(token), exp)

    def test_3part_token_extracts_session_exp(self):
        fn = self._fn()
        exp = int(time.time()) + 86400
        token = _make_jwt({"session_exp": exp, "sub": "test"}, parts=3)
        self.assertEqual(fn(token), exp)

    def test_fallback_to_exp_claim(self):
        fn = self._fn()
        exp = int(time.time()) + 3600
        token = _make_jwt({"exp": exp}, parts=2)
        self.assertEqual(fn(token), exp)

    def test_no_exp_claims_returns_none(self):
        fn = self._fn()
        token = _make_jwt({"sub": "test"}, parts=2)
        self.assertIsNone(fn(token))

    def test_not_a_jwt_returns_none(self):
        fn = self._fn()
        self.assertIsNone(fn("not-a-jwt"))

    def test_single_part_returns_none(self):
        fn = self._fn()
        self.assertIsNone(fn("onlyone"))

    def test_malformed_base64_returns_none(self):
        fn = self._fn()
        # Invalid base64 payload → json.loads fails → None
        self.assertIsNone(fn("!!notbase64!!.sig"))

    def test_empty_string_returns_none(self):
        fn = self._fn()
        self.assertIsNone(fn(""))


# ── TestCookieNearExpiry ──────────────────────────────────────────────────────


class TestCookieNearExpiry(unittest.TestCase):
    """_cookie_near_expiry returns True when > 80% of TTL has elapsed."""

    def _fn(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s._cookie_near_expiry

    def test_fresh_jwt_is_not_near_expiry(self):
        fn = self._fn()
        # > 20% TTL remaining (86400 * 0.20 = 17280 s threshold)
        exp = int(time.time()) + 30000  # well above the 17280-s threshold
        token = _make_jwt({"session_exp": exp}, parts=2)
        self.assertFalse(fn(token))

    def test_nearly_expired_jwt_is_near_expiry(self):
        fn = self._fn()
        # Less than 20% of 86400 remaining (< 17280 s)
        exp = int(time.time()) + 1000
        token = _make_jwt({"session_exp": exp}, parts=2)
        self.assertTrue(fn(token))

    def test_already_expired_is_near_expiry(self):
        fn = self._fn()
        exp = int(time.time()) - 100  # already in the past
        token = _make_jwt({"session_exp": exp}, parts=2)
        self.assertTrue(fn(token))

    def test_non_jwt_string_treated_as_near_expiry(self):
        fn = self._fn()
        # A cookie that is not a JWT has no exp → treated as near-expiry.
        self.assertTrue(fn("not-a-jwt-at-all"))

    def test_jwt_without_exp_treated_as_near_expiry(self):
        fn = self._fn()
        # No exp claims → _jwt_exp returns None → treat as near-expiry.
        token = _make_jwt({"sub": "test"}, parts=2)
        self.assertTrue(fn(token))


# ── TestHandleHealth ─────────────────────────────────────────────────────────


class TestHandleHealth(unittest.TestCase):
    """_handle_health ASGI handler returns HTTP 200 with {"status": "ok"} body."""

    def _handler(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s._handle_health

    def _run_health(self):
        """Invoke _handle_health via a minimal ASGI scope and collect messages."""
        handler = self._handler()
        from starlette.requests import Request

        scope = _make_scope("GET", "/health")
        messages, send = _collect_send()

        async def _invoke():
            req = Request(scope, _receive)
            resp = await handler(req)
            await resp(scope, _receive, send)

        _run(_invoke())
        return messages

    def test_returns_200(self):
        messages = self._run_health()
        self.assertEqual(_status_of(messages), 200)

    def test_body_is_ok(self):
        messages = self._run_health()
        body = _body_of(messages)
        self.assertEqual(body, b"ok")

    def test_response_body_event_emitted(self):
        messages = self._run_health()
        types_ = [m.get("type") for m in messages]
        self.assertIn("http.response.start", types_)
        self.assertIn("http.response.body", types_)


# ── TestCrewApiProxy404OnUnknownCrew (TRN-284 task 5.1) ──────────────────────

class TestCrewUiProxyStripsAcceptEncoding(unittest.TestCase):
    """_handle_crew_ui_proxy strips Accept-Encoding from forwarded requests.

    TRN-289: The transport streams raw bytes without decompressing. If
    Accept-Encoding is forwarded, the crew gateway may return gzip-compressed
    content. The transport strips Content-Encoding from responses (hop-by-hop)
    without decompressing the body, so the browser receives binary garbage.
    Stripping Accept-Encoding at source prevents this.
    """

    def _server(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s

    def test_accept_encoding_in_stripped_set(self):
        """accept-encoding is present in _STRIPPED_CREW_PROXY_HEADERS (TRN-289)."""
        _s = self._server()
        self.assertIn(
            "accept-encoding",
            _s._STRIPPED_CREW_PROXY_HEADERS,
            "accept-encoding must be in _STRIPPED_CREW_PROXY_HEADERS so crew "
            "gateways never return compressed responses the transport cannot "
            "transparently pass through (TRN-289 fix)",
        )

    def test_stripped_headers_excludes_accept_encoding_from_forward(self):
        """forward_headers dict built from a request does not contain accept-encoding."""
        _s = self._server()

        # Simulate the header-filtering logic used in _handle_crew_ui_proxy:
        #   forward_headers = {k: v for k, v in request.headers.items()
        #                       if k.lower() not in _STRIPPED_CREW_PROXY_HEADERS}
        incoming = {
            "accept-encoding": "gzip, br",
            "accept": "application/javascript",
            "user-agent": "Mozilla/5.0",
            "host": "localhost:64058",
        }
        forward_headers = {
            k: v
            for k, v in incoming.items()
            if k.lower() not in _s._STRIPPED_CREW_PROXY_HEADERS
        }

        self.assertNotIn(
            "accept-encoding",
            forward_headers,
            "accept-encoding must be filtered out by _STRIPPED_CREW_PROXY_HEADERS",
        )
        # Unrelated headers are preserved
        self.assertIn("accept", forward_headers)
        self.assertIn("user-agent", forward_headers)


class TestCrewApiProxyUnknownCrew(unittest.TestCase):
    """_handle_crew_api_proxy returns 404 when the crew_id is unknown.

    TRN-284 task 5.1: verify the crew API proxy handler returns 404 for a
    crew_id that is not present in the registry.
    """

    def _handler(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s._handle_crew_api_proxy

    def test_unknown_crew_returns_404(self):
        """GET /crews/unknown-xyz/api/spawn should return 404."""
        from unittest.mock import patch, MagicMock
        import transport.registry as _reg_mod

        handler = self._handler()

        scope = _make_scope("GET", "/crews/unknown-xyz/api/spawn")
        messages, send = _collect_send()

        async def _invoke():
            from starlette.requests import Request
            req = Request(scope, _receive)
            resp = await handler(req)
            await resp(scope, _receive, send)

        # Patch _require_crew to raise KeyError (crew not found)
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s

        with patch.object(_s, "_require_crew", side_effect=KeyError("unknown-xyz")):
            _run(_invoke())

        status = _status_of(messages)
        self.assertEqual(status, 404)


class TestDashboardWebSocketSessionGate(unittest.TestCase):
    def test_missing_session_is_denied_before_crew_resolution(self):
        from unittest.mock import AsyncMock, patch
        from transport.dashboard import DashboardGate
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s

        gate = DashboardGate(
            session_ttl_secs=3600,
            api_key="keyed-installation",
            external_url="http://localhost",
        )
        scope = {
            "type": "websocket",
            "path": "/crews/not-started/ui/ws",
            "headers": [],
            "extensions": {"websocket.http.response": {}},
        }
        messages, send = _collect_send()
        with patch.object(_s, "_dashboard_gate", gate), patch.object(
            _s, "_resolve_crew_for_proxy", new_callable=AsyncMock
        ) as resolve:
            _run(_s._handle_crew_ui_ws_proxy(scope, _receive, send))

        self.assertEqual(
            [message.get("status") for message in messages if message.get("type") == "websocket.http.response.start"],
            [401],
        )
        resolve.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()


class TestRewriteDashboardOrigin(unittest.TestCase):
    """_rewrite_dashboard_origin maps a same-origin dashboard Origin to the
    crew gateway's loopback origin so KiroCrew's CSRF check accepts
    state-changing dashboard requests, and leaves cross-site Origins alone."""

    def _server(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s

    def _run(self, headers, matches):
        from unittest.mock import patch
        _s = self._server()
        with patch.object(_s._dashboard_gate, "is_dashboard_origin", return_value=matches):
            _s._rewrite_dashboard_origin(headers, {"type": "http", "headers": []})
        return _s

    def test_same_origin_rewritten_to_crew_origin(self):
        headers = {"origin": "http://localhost:64058", "accept": "*/*"}
        _s = self._server()
        from unittest.mock import patch
        with patch.object(_s._dashboard_gate, "is_dashboard_origin", return_value=True):
            foreign = _s._rewrite_dashboard_origin(headers, {"type": "http", "headers": []})
        self.assertFalse(foreign)
        self.assertNotIn("origin", headers)
        self.assertEqual(headers["Origin"], f"http://localhost:{_s.CREW_GATEWAY_PORT}")
        self.assertEqual(headers["accept"], "*/*")

    def test_cross_site_origin_forwarded_unchanged(self):
        headers = {"origin": "https://attacker.example"}
        from unittest.mock import patch
        _s = self._server()
        with patch.object(_s._dashboard_gate, "is_dashboard_origin", return_value=False):
            foreign = _s._rewrite_dashboard_origin(headers, {"type": "http", "headers": []})
        self.assertTrue(foreign)
        self.assertEqual(headers, {"origin": "https://attacker.example"})

    def test_no_origin_left_untouched(self):
        headers = {"accept": "*/*"}
        self._run(headers, matches=True)
        self.assertEqual(headers, {"accept": "*/*"})



class _FakeStreamResp:
    def __init__(self, status):
        self.status_code = status
        self.headers = {"content-type": "text/plain"}

    async def aread(self):
        return b"CSRF check failed: request origin not allowed."


class _FakeStreamCtx:
    def __init__(self, status):
        self._resp = _FakeStreamResp(status)

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class TestCrewUiProxyForeignOriginNoCookieRefresh(unittest.TestCase):
    """A 403 on a foreign-Origin request is KiroCrew's CSRF check, so the UI
    proxy must pass it through without re-minting the crew cookie."""

    def _server(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s

    def _invoke(self, origin_matches):
        from unittest.mock import patch, MagicMock
        _s = self._server()
        scope = _make_scope("POST", "/crews/c1/ui/api/ui-prefs",
                            headers={"origin": "https://attacker.example"})
        messages, send = _collect_send()
        refresh = MagicMock(return_value=False)

        async def _resolved(*a, **k):
            return ("c1", "api/ui-prefs", {"cookie": "x"})

        async def _go():
            from starlette.requests import Request
            resp = await _s._handle_crew_ui_proxy(Request(scope, _receive))
            await resp(scope, _receive, send)

        with patch.object(_s, "_resolve_crew_for_proxy", side_effect=_resolved), \
             patch.object(_s, "_cookie_near_expiry", return_value=False, create=True), \
             patch.object(_s, "_crew_cookie", return_value="mc_token_5476=x"), \
             patch.object(_s, "_refresh_cookie", refresh), \
             patch.object(_s._dashboard_gate, "is_dashboard_origin", return_value=origin_matches), \
             patch.object(_s._async_http, "stream", side_effect=lambda *a, **k: _FakeStreamCtx(403), create=True):
            _run(_go())
        return _status_of(messages), refresh

    def test_foreign_origin_403_does_not_refresh_cookie(self):
        status, refresh = self._invoke(origin_matches=False)
        self.assertEqual(status, 403)
        refresh.assert_not_called()

    def test_dashboard_origin_403_still_refreshes_cookie(self):
        status, refresh = self._invoke(origin_matches=True)
        self.assertEqual(status, 403)
        refresh.assert_called_once()


class TestCrewUiProxySessionGate(unittest.TestCase):
    """Direct internal UI-proxy calls still require a dashboard session."""

    def _server(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s

    def _invoke(self, *, api_key, with_session):
        from unittest.mock import AsyncMock, MagicMock, patch
        from transport.dashboard import DashboardGate

        _s = self._server()
        gate = DashboardGate(
            session_ttl_secs=3600,
            api_key=api_key,
            external_url="http://localhost:64057",
        )
        headers = {"x-transport-token": "radar-transport-secret"}
        if with_session:
            token = gate._sessions.issue()
            headers["cookie"] = f"gs_session={token}"
        scope = _make_scope("GET", "/crews/c1/ui", headers=headers)

        class _ProxyRequest:
            def __init__(self, request_scope):
                self.scope = request_scope
                self.method = request_scope["method"]
                self.headers = {
                    key.decode("latin-1"): value.decode("latin-1")
                    for key, value in request_scope["headers"]
                }

            async def body(self):
                return b""

        resolver = AsyncMock(return_value=("c1", "", {"cookie": "crew-cookie"}))
        stream = MagicMock(return_value=_FakeStreamCtx(200))

        async def _go():
            return await _s._handle_crew_ui_proxy(_ProxyRequest(scope))

        with patch.object(_s, "_dashboard_gate", gate), \
             patch.object(_s, "_resolve_crew_for_proxy", resolver), \
             patch.object(_s, "_cookie_near_expiry", return_value=False), \
             patch.object(_s, "_crew_cookie", return_value="mc_token_5476=crew"), \
             patch.object(_s._async_http, "stream", stream, create=True):
            response = _run(_go())
        return response, resolver, stream

    def test_transport_secret_without_session_is_rejected_before_proxy(self):
        response, resolver, stream = self._invoke(api_key="keyed-install", with_session=False)

        self.assertEqual(response.status_code, 401)
        resolver.assert_not_awaited()
        stream.assert_not_called()

    def test_valid_session_can_proxy_on_keyed_install(self):
        response, resolver, stream = self._invoke(api_key="keyed-install", with_session=True)

        self.assertEqual(response.status_code, 200)
        resolver.assert_awaited_once()
        stream.assert_called_once()

    def test_open_install_can_proxy_without_session(self):
        response, resolver, stream = self._invoke(api_key="", with_session=False)

        self.assertEqual(response.status_code, 200)
        resolver.assert_awaited_once()
        stream.assert_called_once()


class TestRestoreCaddyDashboardRoutes(unittest.TestCase):
    """Startup route restoration uses the same Caddy socket client."""

    def test_restored_dashboard_routes_are_registered_through_caddy_portal(self):
        from unittest.mock import MagicMock, patch
        import transport.caddy as _caddy
        from transport.caddy import CaddyPortal
        from transport.dashboard import DashboardGate

        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s

        portal = CaddyPortal(
            port=64057,
            api_key="",
            port_range_start=64058,
            port_range_size=4,
        )
        gate = DashboardGate(
            session_ttl_secs=3600,
            api_key="",
            external_url="http://localhost:64057",
        )
        response = MagicMock(status_code=200, text="")
        with patch.object(_s, "_caddy_portal", portal), \
             patch.object(_s, "_dashboard_gate", gate), \
             patch.object(
                 _caddy._caddy_admin_client,
                 "put",
                 return_value=response,
                 create=True,
             ) as put:
            _s._restore_caddy_dashboard_routes({
                "alpha": {"dashboard_port": 64058, "cookie": "old-cookie"},
                "headless": {},
            })

        self.assertEqual(gate._port_crew[64058], "alpha")
        put.assert_called_once()
        self.assertEqual(
            put.call_args.args[0],
            "http://localhost:2019/config/apps/http/servers/crew-alpha",
        )


class TestCrewDashboardEndpointRejectsBrowserOrigin(unittest.TestCase):
    """POST/DELETE /crews/{id}/dashboard refuse any request carrying Origin
    (cross-site "simple request" guard); non-browser clients are unaffected."""

    def _server(self):
        try:
            import server as _s
        except ModuleNotFoundError:
            from transport import server as _s
        return _s

    def _call(self, handler, method, headers):
        from unittest.mock import patch
        _s = self._server()
        scope = _make_scope(method, "/crews/unknown-xyz/dashboard", headers=headers)
        messages, send = _collect_send()

        async def _go():
            from starlette.requests import Request
            resp = await handler(Request(scope, _receive))
            await resp(scope, _receive, send)

        with patch.object(_s, "_require_crew", side_effect=KeyError("unknown-xyz")):
            _run(_go())
        return _status_of(messages)

    def test_origin_rejected_on_post_and_delete(self):
        _s = self._server()
        for handler, method in ((_s._handle_crew_dashboard_post, "POST"),
                                (_s._handle_crew_dashboard_delete, "DELETE")):
            for origin in ("https://evil.example", "http://localhost:64058"):
                with self.subTest(method=method, origin=origin):
                    self.assertEqual(self._call(handler, method, {"origin": origin}), 403)

    def test_no_origin_reaches_handler(self):
        _s = self._server()
        # Unknown crew → 404 proves the request got past the Origin guard.
        self.assertEqual(self._call(_s._handle_crew_dashboard_post, "POST", {}), 404)
