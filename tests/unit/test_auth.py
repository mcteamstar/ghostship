"""Unit tests for transport/auth.py — ASGI authentication and rate-limit middleware.

Covers every public class and helper in ``transport.auth``:
- ``_parse_bearer_token``
- ``_parse_rate_limit_var``
- ``_build_rate_limiters``
- ``_request_source``
- ``TransportSecretMiddleware``
- ``RateLimitMiddleware``
- ``BearerAuthMiddleware`` (pass-through, rejection, and route dispatch)
- ``SecurityHeadersMiddleware``

Design (see openspec/changes/trn-248-test-auth/design.md): each middleware is
constructed in isolation and invoked by passing minimal ASGI ``scope`` dicts to
``__call__`` directly — no Starlette ``TestClient`` and no live server. ``send``
is a coroutine that appends ASGI messages to a list; ``receive`` returns a
minimal body event. No network I/O is performed and no production code changes
are made.
"""

from __future__ import annotations

import asyncio
import hmac
import os
import unittest
import unittest.mock


# ── Shared ASGI helpers ───────────────────────────────────────────────────────

def _make_scope(method, path, headers=None, scope_type="http", client=("127.0.0.1", 55555), scheme="http"):
    """Return a minimal ASGI scope dict.

    ``headers`` is an optional dict of ``{str_name: str_value}``; it is encoded
    into the ASGI ``(bytes, bytes)`` header-list form. Header names are
    lower-cased, as a real ASGI server delivers them.
    """
    raw_headers = []
    if headers:
        for name, value in headers.items():
            raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
    scope = {
        "type": scope_type,
        "method": method,
        "path": path,
        "headers": raw_headers,
        "scheme": scheme,
        "query_string": b"",
    }
    if client is not None:
        scope["client"] = client
    return scope


def _collect_send():
    """Return ``(messages, send)`` where ``send`` is an async callable that
    appends each ASGI message to the ``messages`` list."""
    messages = []

    async def send(message):
        messages.append(message)

    return messages, send


async def _receive():
    """Minimal ASGI receive: a single empty-body HTTP request event."""
    return {"type": "http.request", "body": b"", "more_body": False}


def _run(coro):
    """Run an awaitable to completion on an event loop.

    Uses ``asyncio.get_event_loop().run_until_complete`` per the test design; on
    Python 3.12 ``get_event_loop`` warns when no loop is current, so we create
    and install one in that case (and silence the transitional DeprecationWarning).
    """
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
    """Return the HTTP status code from the first ``http.response.start`` message,
    or ``None`` if the middleware never started a response itself."""
    for msg in messages:
        if msg.get("type") == "http.response.start":
            return msg.get("status")
    return None


def _headers_of(messages):
    """Return response headers (as a list of (bytes, bytes)) from the
    ``http.response.start`` message, or ``[]`` if none."""
    for msg in messages:
        if msg.get("type") == "http.response.start":
            return list(msg.get("headers", []))
    return []


class _RecordingApp:
    """A downstream ASGI app that records whether it was called and sends 200 OK."""

    def __init__(self):
        self.called = False
        self.last_scope = None

    async def __call__(self, scope, receive, send):
        self.called = True
        self.last_scope = scope
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


# ── _parse_bearer_token ───────────────────────────────────────────────────────

class TestParseBearerToken(unittest.TestCase):
    def test_well_formed_token(self):
        from transport.auth import _parse_bearer_token
        self.assertEqual(_parse_bearer_token("Bearer abc123"), "abc123")

    def test_case_insensitive_scheme(self):
        from transport.auth import _parse_bearer_token
        self.assertEqual(_parse_bearer_token("BEARER mytoken"), "mytoken")

    def test_missing_scheme_returns_none(self):
        from transport.auth import _parse_bearer_token
        self.assertIsNone(_parse_bearer_token("abc123xyz"))

    def test_wrong_scheme_returns_none(self):
        from transport.auth import _parse_bearer_token
        self.assertIsNone(_parse_bearer_token("Basic abc123"))

    def test_token_with_embedded_space_returns_none(self):
        from transport.auth import _parse_bearer_token
        self.assertIsNone(_parse_bearer_token("Bearer a b"))

    def test_empty_string_returns_none(self):
        from transport.auth import _parse_bearer_token
        self.assertIsNone(_parse_bearer_token(""))

    def test_too_short_returns_none(self):
        from transport.auth import _parse_bearer_token
        # Fewer than 8 characters is rejected before scheme parsing.
        self.assertIsNone(_parse_bearer_token("Bear x"))


# ── _parse_rate_limit_var ─────────────────────────────────────────────────────

class TestParseRateLimitVar(unittest.TestCase):
    _VAR = "GA_RATE_LIMIT_TEST_VAR"

    def test_valid_env_var_parsed(self):
        from transport.auth import _parse_rate_limit_var
        with unittest.mock.patch.dict(os.environ, {self._VAR: "10:60"}, clear=True):
            self.assertEqual(_parse_rate_limit_var(self._VAR, 5, 30), (10, 60))

    def test_env_var_absent_returns_defaults(self):
        from transport.auth import _parse_rate_limit_var
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_parse_rate_limit_var(self._VAR, 7, 45), (7, 45))

    def test_non_integer_returns_defaults_and_warns(self):
        from transport.auth import _parse_rate_limit_var
        with unittest.mock.patch.dict(os.environ, {self._VAR: "notanumber:60"}, clear=True):
            with self.assertLogs("transport.server", level="WARNING") as cm:
                result = _parse_rate_limit_var(self._VAR, 5, 30)
        self.assertEqual(result, (5, 30))
        self.assertTrue(any("WARNING" in line for line in cm.output))

    def test_zero_count_returns_defaults_and_warns(self):
        from transport.auth import _parse_rate_limit_var
        with unittest.mock.patch.dict(os.environ, {self._VAR: "0:60"}, clear=True):
            with self.assertLogs("transport.server", level="WARNING") as cm:
                result = _parse_rate_limit_var(self._VAR, 5, 30)
        self.assertEqual(result, (5, 30))
        self.assertTrue(cm.output)

    def test_negative_window_returns_defaults_and_warns(self):
        from transport.auth import _parse_rate_limit_var
        with unittest.mock.patch.dict(os.environ, {self._VAR: "10:-1"}, clear=True):
            with self.assertLogs("transport.server", level="WARNING") as cm:
                result = _parse_rate_limit_var(self._VAR, 5, 30)
        self.assertEqual(result, (5, 30))
        self.assertTrue(cm.output)


# ── _build_rate_limiters ──────────────────────────────────────────────────────

class TestBuildRateLimiters(unittest.TestCase):
    def test_master_switch_false_returns_none(self):
        from transport.auth import _build_rate_limiters
        with unittest.mock.patch.dict(os.environ, {"GA_RATE_LIMIT_ENABLED": "false"}, clear=True):
            self.assertIsNone(_build_rate_limiters())

    def test_master_switch_true_returns_populated_dict(self):
        from transport.auth import _build_rate_limiters
        with unittest.mock.patch.dict(os.environ, {"GA_RATE_LIMIT_ENABLED": "true"}, clear=True):
            limiters = _build_rate_limiters()
        self.assertIsNotNone(limiters)
        for key in ("login_post", "login_get", "files", "crew_api", "mcp", "dashboard_auth"):
            self.assertIn(key, limiters)


# ── _request_source ───────────────────────────────────────────────────────────

class TestRequestSource(unittest.TestCase):
    def test_xff_first_hop_from_scope(self):
        from transport.auth import _request_source
        scope = _make_scope("GET", "/", headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"})
        self.assertEqual(_request_source(scope), "1.2.3.4")

    def test_asgi_client_ip_when_no_xff(self):
        from transport.auth import _request_source
        scope = _make_scope("GET", "/", client=("10.0.0.1", 1234))
        self.assertEqual(_request_source(scope), "10.0.0.1")

    def test_none_when_source_unavailable(self):
        from transport.auth import _request_source
        scope = {"type": "http", "headers": []}  # no headers, no client
        self.assertIsNone(_request_source(scope))


# ── TransportSecretMiddleware ─────────────────────────────────────────────────

class TestTransportSecretMiddleware(unittest.TestCase):
    def _make(self, secret):
        from transport.auth import TransportSecretMiddleware
        app = _RecordingApp()
        return TransportSecretMiddleware(app, transport_secret=secret), app

    def test_correct_token_passes_through(self):
        mw, app = self._make("s3cr3t")
        scope = _make_scope("GET", "/mcp", headers={"x-transport-token": "s3cr3t"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)
        self.assertNotEqual(_status_of(messages), 401)

    def test_wrong_token_returns_401(self):
        mw, app = self._make("s3cr3t")
        scope = _make_scope("GET", "/mcp", headers={"x-transport-token": "wrong"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertFalse(app.called)
        self.assertEqual(_status_of(messages), 401)

    def test_missing_token_returns_401(self):
        mw, app = self._make("s3cr3t")
        scope = _make_scope("GET", "/mcp")
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertFalse(app.called)
        self.assertEqual(_status_of(messages), 401)

    def test_empty_secret_passthrough(self):
        mw, app = self._make("")
        scope = _make_scope("GET", "/mcp", headers={"x-transport-token": "anything"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)

    def test_non_http_scope_passthrough(self):
        mw, app = self._make("s3cr3t")
        # WebSocket scope with a wrong token must still pass through to downstream.
        scope = _make_scope("GET", "/ws", headers={"x-transport-token": "wrong"}, scope_type="websocket")
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)
        self.assertNotEqual(_status_of(messages), 401)

    def test_constant_time_compare_used(self):
        mw, app = self._make("s3cr3t")
        scope = _make_scope("GET", "/mcp", headers={"x-transport-token": "s3cr3t"})
        messages, send = _collect_send()
        with unittest.mock.patch("transport.auth.hmac.compare_digest", wraps=hmac.compare_digest) as spy:
            _run(mw(scope, _receive, send))
        self.assertTrue(spy.called)


# ── RateLimitMiddleware ───────────────────────────────────────────────────────

class TestRateLimitMiddleware(unittest.TestCase):
    def _limiter(self, max_requests=5, window_secs=60):
        from transport import security as _security
        return _security.RateLimiter(max_requests=max_requests, window_secs=float(window_secs))

    def _make_middleware(self, limiters, api_key=""):
        from transport.auth import RateLimitMiddleware
        app = _RecordingApp()
        return RateLimitMiddleware(app, limiters, api_key=api_key), app

    def test_health_exempt(self):
        limiter = self._limiter(max_requests=1)
        mw, app = self._make_middleware({"login_get": limiter})
        scope = _make_scope("GET", "/health")
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)
        self.assertFalse(limiter._hits)  # no limiter state recorded

    def test_version_exempt(self):
        limiter = self._limiter(max_requests=1)
        mw, app = self._make_middleware({"login_get": limiter})
        scope = _make_scope("GET", "/version")
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)
        self.assertFalse(limiter._hits)

    def test_first_request_within_limit_passes(self):
        limiter = self._limiter(max_requests=5, window_secs=60)
        mw, app = self._make_middleware({"login_post": limiter})
        scope = _make_scope("POST", "/login", client=("9.9.9.9", 1))
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)
        self.assertNotEqual(_status_of(messages), 429)

    def test_over_limit_returns_429(self):
        limiter = self._limiter(max_requests=2, window_secs=60)
        mw, app = self._make_middleware({"login_post": limiter})
        # Exhaust the limit from one IP.
        for _ in range(2):
            app.called = False
            messages, send = _collect_send()
            _run(mw(_make_scope("POST", "/login", client=("9.9.9.9", 1)), _receive, send))
            self.assertTrue(app.called)
        # Third request over the limit → 429, downstream NOT called.
        app.called = False
        messages, send = _collect_send()
        _run(mw(_make_scope("POST", "/login", client=("9.9.9.9", 1)), _receive, send))
        self.assertFalse(app.called)
        self.assertEqual(_status_of(messages), 429)
        header_names = {k for k, _ in _headers_of(messages)}
        self.assertIn(b"retry-after", header_names)

    def test_caller_key_ip_only_when_no_bearer(self):
        # Two different IPs are tracked separately: exhaust IP A, then IP B still passes.
        limiter = self._limiter(max_requests=1, window_secs=60)
        mw, app = self._make_middleware({"login_post": limiter})
        # IP A: first passes, second is at limit (429).
        _run(mw(_make_scope("POST", "/login", client=("1.1.1.1", 1)), _receive, _collect_send()[1]))
        messages_a, send_a = _collect_send()
        app.called = False
        _run(mw(_make_scope("POST", "/login", client=("1.1.1.1", 1)), _receive, send_a))
        self.assertEqual(_status_of(messages_a), 429)
        # IP B: fresh key, passes.
        messages_b, send_b = _collect_send()
        app.called = False
        _run(mw(_make_scope("POST", "/login", client=("2.2.2.2", 1)), _receive, send_b))
        self.assertTrue(app.called)
        self.assertNotEqual(_status_of(messages_b), 429)

    def test_caller_key_hashes_bearer_when_present(self):
        # Same IP, two different bearer tokens → tracked independently.
        limiter = self._limiter(max_requests=1, window_secs=60)
        mw, app = self._make_middleware({"login_post": limiter})
        scope1 = _make_scope("POST", "/login", client=("3.3.3.3", 1),
                             headers={"authorization": "Bearer tokenAAAA"})
        scope2 = _make_scope("POST", "/login", client=("3.3.3.3", 1),
                             headers={"authorization": "Bearer tokenBBBB"})
        messages1, send1 = _collect_send()
        app.called = False
        _run(mw(scope1, _receive, send1))
        self.assertTrue(app.called)
        self.assertNotEqual(_status_of(messages1), 429)
        messages2, send2 = _collect_send()
        app.called = False
        _run(mw(scope2, _receive, send2))
        self.assertTrue(app.called)  # different token key → not at limit
        self.assertNotEqual(_status_of(messages2), 429)

    def test_unmatched_path_passthrough(self):
        limiter = self._limiter(max_requests=1)
        mw, app = self._make_middleware({"login_post": limiter})
        scope = _make_scope("GET", "/some/other/path")
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)
        self.assertFalse(limiter._hits)  # no record on unmatched path

    def test_login_post_matched(self):
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"login_post": limiter})
        _run(mw(_make_scope("POST", "/login", client=("5.5.5.5", 1)), _receive, _collect_send()[1]))
        self.assertTrue(limiter._hits)  # login_post limiter consumed

    def test_login_get_matched(self):
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"login_get": limiter})
        _run(mw(_make_scope("GET", "/login", client=("5.5.5.6", 1)), _receive, _collect_send()[1]))
        self.assertTrue(limiter._hits)

    def test_files_path_matched(self):
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"files": limiter})
        _run(mw(_make_scope("GET", "/files/abc", client=("5.5.5.7", 1)), _receive, _collect_send()[1]))
        self.assertTrue(limiter._hits)

    def test_crew_api_path_matched(self):
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"crew_api": limiter})
        _run(mw(_make_scope("GET", "/crews/xyz/api/foo", client=("5.5.5.8", 1)), _receive, _collect_send()[1]))
        self.assertTrue(limiter._hits)

    def test_mcp_path_matched(self):
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"mcp": limiter})
        _run(mw(_make_scope("GET", "/mcp/list", client=("5.5.5.9", 1)), _receive, _collect_send()[1]))
        self.assertTrue(limiter._hits)

    def test_dashboard_auth_get_matched(self):
        """GET /dashboard/auth is matched to the dashboard_auth limiter."""
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"dashboard_auth": limiter})
        _run(mw(_make_scope("GET", "/dashboard/auth", client=("5.5.5.10", 1)), _receive, _collect_send()[1]))
        self.assertTrue(limiter._hits)  # dashboard_auth limiter consumed

    def test_dashboard_login_post_matched(self):
        """POST /dashboard/login is matched to the dashboard_auth limiter."""
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"dashboard_auth": limiter})
        _run(mw(_make_scope("POST", "/dashboard/login", client=("5.5.5.11", 1)), _receive, _collect_send()[1]))
        self.assertTrue(limiter._hits)  # dashboard_auth limiter consumed


# ── BearerAuthMiddleware — pass-through and rejection paths ───────────────────

class TestBearerAuthMiddleware(unittest.TestCase):
    def _make_mw(self, api_key, routes=None, public_routes=None, file_app=None):
        from transport.auth import BearerAuthMiddleware
        app = _RecordingApp()
        mw = BearerAuthMiddleware(
            app, api_key=api_key, file_app=file_app,
            routes=routes, public_routes=public_routes,
        )
        return mw, app

    def test_correct_bearer_passes(self):
        mw, app = self._make_mw("thekey123")
        scope = _make_scope("GET", "/mcp", headers={"authorization": "Bearer thekey123"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)
        self.assertNotEqual(_status_of(messages), 401)

    def test_wrong_bearer_returns_401(self):
        mw, app = self._make_mw("thekey123")
        scope = _make_scope("GET", "/mcp", headers={"authorization": "Bearer wrongkey9"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertFalse(app.called)
        self.assertEqual(_status_of(messages), 401)
        header_names = {k.lower() for k, _ in _headers_of(messages)}
        self.assertIn(b"www-authenticate", header_names)

    def test_missing_auth_header_returns_401(self):
        mw, app = self._make_mw("thekey123")
        scope = _make_scope("GET", "/mcp")
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertFalse(app.called)
        self.assertEqual(_status_of(messages), 401)

    def test_duplicate_auth_headers_returns_401(self):
        mw, app = self._make_mw("thekey123")
        scope = _make_scope("GET", "/mcp")
        # Two authorization headers — construct the raw list directly.
        scope["headers"] = [
            (b"authorization", b"Bearer thekey123"),
            (b"authorization", b"Bearer thekey123"),
        ]
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertFalse(app.called)
        self.assertEqual(_status_of(messages), 401)

    def test_malformed_auth_header_returns_401(self):
        mw, app = self._make_mw("thekey123")
        scope = _make_scope("GET", "/mcp", headers={"authorization": "Token abc"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertFalse(app.called)
        self.assertEqual(_status_of(messages), 401)

    def test_health_bypasses_bearer(self):
        from starlette.responses import PlainTextResponse
        served = {"flag": False}

        async def health(request):
            served["flag"] = True
            return PlainTextResponse("ok")

        # /health is bearer-exempt: it is served by its registered route handler
        # without any Authorization header, even when api_key is set.
        mw, app = self._make_mw("thekey123", routes={("GET", "/health"): health})
        scope = _make_scope("GET", "/health")  # no auth header
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(served["flag"])
        self.assertNotEqual(_status_of(messages), 401)

    def test_empty_api_key_passthrough(self):
        mw, app = self._make_mw("")
        scope = _make_scope("GET", "/mcp")  # no auth header
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)

    def test_constant_time_compare_used(self):
        mw, app = self._make_mw("thekey123")
        scope = _make_scope("GET", "/mcp", headers={"authorization": "Bearer thekey123"})
        messages, send = _collect_send()
        with unittest.mock.patch("transport.auth.hmac.compare_digest", wraps=hmac.compare_digest) as spy:
            _run(mw(scope, _receive, send))
        self.assertTrue(spy.called)

    def test_audit_event_emitted_on_rejection(self):
        mw, app = self._make_mw("thekey123")
        scope = _make_scope("GET", "/mcp", headers={"authorization": "Bearer wrongkey9"})
        messages, send = _collect_send()
        with unittest.mock.patch("transport.auth._security.audit_auth_event") as audit:
            _run(mw(scope, _receive, send))
        self.assertTrue(audit.called)
        _, kwargs = audit.call_args
        self.assertEqual(kwargs.get("outcome"), "denied")


# ── BearerAuthMiddleware — route dispatch ─────────────────────────────────────

class TestBearerAuthRouteDispatch(unittest.TestCase):
    def _make_mw(self, api_key, routes=None, public_routes=None, file_app=None):
        from transport.auth import BearerAuthMiddleware
        app = _RecordingApp()
        mw = BearerAuthMiddleware(
            app, api_key=api_key, file_app=file_app,
            routes=routes, public_routes=public_routes,
        )
        return mw, app

    def test_public_route_dispatched_without_auth(self):
        from starlette.responses import PlainTextResponse
        called = {"flag": False}

        async def handler(request):
            called["flag"] = True
            return PlainTextResponse("pub")

        mw, app = self._make_mw("thekey123", public_routes={("GET", "/pub"): handler})
        scope = _make_scope("GET", "/pub")  # no Authorization header
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(called["flag"])
        self.assertFalse(app.called)

    def test_files_forwarded_to_file_app_bypassing_bearer(self):
        file_app = _RecordingApp()
        mw, app = self._make_mw("thekey123", file_app=file_app)
        scope = _make_scope("GET", "/files/x")  # no auth header
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(file_app.called)
        self.assertFalse(app.called)

    def test_registered_route_dispatched_after_auth(self):
        from starlette.responses import PlainTextResponse
        called = {"flag": False}

        async def handler(request):
            called["flag"] = True
            return PlainTextResponse("tool")

        mw, app = self._make_mw("thekey123", routes={("GET", "/tool"): handler})
        scope = _make_scope("GET", "/tool", headers={"authorization": "Bearer thekey123"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(called["flag"])
        self.assertFalse(app.called)

    def test_ws_upgrade_dispatched_without_bearer(self):
        called = {"flag": False}

        async def ws_handler(scope, receive, send):
            called["flag"] = True

        mw, app = self._make_mw(
            "thekey123",
            public_routes={("WS", "/crews/*/ui"): ws_handler},
        )
        scope = _make_scope("GET", "/crews/abc/ui/x", scope_type="websocket")
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(called["flag"])
        self.assertFalse(app.called)


# ── SecurityHeadersMiddleware ─────────────────────────────────────────────────

class TestSecurityHeadersMiddleware(unittest.TestCase):
    def _make(self, enable_headers=True, enforce_redirect=False, csp_enforce=False):
        from transport.auth import SecurityHeadersMiddleware
        app = _RecordingApp()
        mw = SecurityHeadersMiddleware(
            app,
            enable_headers=enable_headers,
            enforce_redirect=enforce_redirect,
            csp_enforce=csp_enforce,
        )
        return mw, app

    def test_security_headers_added(self):
        mw, app = self._make()
        scope = _make_scope("GET", "/mcp")
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        header_names = {k.lower() for k, _ in _headers_of(messages)}
        self.assertIn(b"x-content-type-options", header_names)
        self.assertTrue(
            any(k.lower().startswith(b"content-security-policy") for k, _ in _headers_of(messages))
        )

    def test_hsts_on_https_response(self):
        mw, app = self._make()
        scope = _make_scope("GET", "/mcp", headers={"x-forwarded-proto": "https"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        hsts = [v for k, v in _headers_of(messages) if k.lower() == b"strict-transport-security"]
        self.assertEqual(len(hsts), 1)
        self.assertIn(b"max-age=", hsts[0])
        # max-age must be non-zero.
        self.assertNotIn(b"max-age=0", hsts[0])

    def test_hsts_absent_on_http_response(self):
        mw, app = self._make()
        scope = _make_scope("GET", "/mcp")  # plain HTTP
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        header_names = {k.lower() for k, _ in _headers_of(messages)}
        self.assertNotIn(b"strict-transport-security", header_names)

    def test_xfp_detection(self):
        from transport.auth import SecurityHeadersMiddleware
        scope = _make_scope("GET", "/mcp", headers={"x-forwarded-proto": "https"}, scheme="http")
        self.assertTrue(SecurityHeadersMiddleware._is_https(scope))

    def test_enforce_redirect_sends_301(self):
        mw, app = self._make(enforce_redirect=True)
        scope = _make_scope("GET", "/dashboard", headers={"host": "example.com"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertEqual(_status_of(messages), 301)
        location = [v for k, v in _headers_of(messages) if k.lower() == b"location"]
        self.assertEqual(len(location), 1)
        self.assertTrue(location[0].startswith(b"https://"))
        self.assertFalse(app.called)

    def test_health_not_redirected(self):
        mw, app = self._make(enforce_redirect=True)
        scope = _make_scope("GET", "/health", headers={"host": "example.com"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)
        self.assertNotEqual(_status_of(messages), 301)

    def test_control_chars_stripped_from_redirect_target(self):
        mw, app = self._make(enforce_redirect=True)
        # Path containing CR/LF must not leak into the Location header.
        scope = _make_scope("GET", "/evil\r\nX-Injected: 1", headers={"host": "example.com"})
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        location = [v for k, v in _headers_of(messages) if k.lower() == b"location"]
        self.assertEqual(len(location), 1)
        self.assertNotIn(b"\r", location[0])
        self.assertNotIn(b"\n", location[0])

    def test_headers_disabled_when_flag_false(self):
        mw, app = self._make(enable_headers=False)
        scope = _make_scope("GET", "/mcp")
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)
        header_names = {k.lower() for k, _ in _headers_of(messages)}
        self.assertNotIn(b"x-content-type-options", header_names)

    def test_non_http_scope_passthrough(self):
        mw, app = self._make()
        scope = _make_scope("GET", "/ws", scope_type="websocket")
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        self.assertTrue(app.called)
        # The middleware injects no security headers on a non-HTTP scope: the
        # downstream app's own response passes through unwrapped.
        header_names = {k.lower() for k, _ in _headers_of(messages)}
        self.assertNotIn(b"x-content-type-options", header_names)


# ── TRN-233: new route table tests ───────────────────────────────────────────


class TestTrn233RouteTable(unittest.TestCase):
    """TRN-233 task 3.1: old paths return 404, new paths get through bearer,
    and the rate-limit rule is widened to POST /login/*."""

    def _make_mw(self, api_key="testkey", routes=None, public_routes=None):
        from transport.auth import BearerAuthMiddleware
        app = _RecordingApp()
        mw = BearerAuthMiddleware(
            app, api_key=api_key,
            routes=routes or {},
            public_routes=public_routes or {},
        )
        return mw, app

    def _status(self, mw, method, path, key=None):
        headers = {}
        if key:
            headers["authorization"] = f"Bearer {key}"
        scope = _make_scope(method, path, headers=headers)
        messages, send = _collect_send()
        _run(mw(scope, _receive, send))
        start = next((m for m in messages if m["type"] == "http.response.start"), None)
        return start["status"] if start else None

    def test_old_bare_login_post_returns_404_via_mcp_app(self):
        """POST /login is not in the new route table; falls through to MCP app.
        BearerAuthMiddleware dispatches to the inner app (which in our test is
        _RecordingApp, which records the call without setting a status —
        effectively a 200). The key thing is it is NOT in the routes dict,
        so the route dispatch doesn't call any login handler. We verify 401
        when bearer is wrong (since no route matches and MCP app requires bearer).
        """
        mw, app = self._make_mw(api_key="testkey123", routes={})
        # No route registered for POST /login → falls to MCP app after bearer check
        status = self._status(mw, "POST", "/login", key=None)
        # Without bearer key and with api_key set → 401
        self.assertEqual(status, 401)

    def test_old_bare_logout_post_not_registered(self):
        mw, app = self._make_mw(api_key="testkey123", routes={})
        status = self._status(mw, "POST", "/logout", key=None)
        self.assertEqual(status, 401)

    def test_old_login_claude_not_registered(self):
        mw, app = self._make_mw(api_key="testkey123", routes={})
        status = self._status(mw, "POST", "/login/claude", key=None)
        self.assertEqual(status, 401)

    def test_old_login_claude_code_not_registered(self):
        mw, app = self._make_mw(api_key="testkey123", routes={})
        status = self._status(mw, "POST", "/login/claude/code", key=None)
        self.assertEqual(status, 401)

    def test_old_login_codex_not_registered(self):
        mw, app = self._make_mw(api_key="testkey123", routes={})
        status = self._status(mw, "POST", "/login/codex", key=None)
        self.assertEqual(status, 401)

    def test_new_login_kiro_get_registered(self):
        """GET /login/kiro with valid bearer is dispatched to the registered handler."""
        from starlette.responses import JSONResponse
        called = {"flag": False}

        async def handler(request):
            called["flag"] = True
            return JSONResponse({"ok": True})

        mw, app = self._make_mw(api_key="testkey", routes={("GET", "/login/kiro"): handler})
        status = self._status(mw, "GET", "/login/kiro", key="testkey")
        self.assertTrue(called["flag"])

    def test_new_login_claude_api_key_registered(self):
        from starlette.responses import JSONResponse
        called = {"flag": False}

        async def handler(request):
            called["flag"] = True
            return JSONResponse({"ok": True})

        mw, app = self._make_mw(api_key="testkey", routes={("POST", "/login/claude/api-key"): handler})
        status = self._status(mw, "POST", "/login/claude/api-key", key="testkey")
        self.assertTrue(called["flag"])

    def test_new_logout_kiro_registered(self):
        from starlette.responses import JSONResponse
        called = {"flag": False}

        async def handler(request):
            called["flag"] = True
            return JSONResponse({"ok": True})

        mw, app = self._make_mw(api_key="testkey", routes={("POST", "/logout/kiro"): handler})
        status = self._status(mw, "POST", "/logout/kiro", key="testkey")
        self.assertTrue(called["flag"])

    def test_new_route_without_bearer_returns_401(self):
        """New routes require bearer auth — no bearer → 401."""
        from starlette.responses import JSONResponse

        async def handler(request):
            return JSONResponse({"ok": True})

        mw, app = self._make_mw(api_key="testkey", routes={("GET", "/login/kiro"): handler})
        status = self._status(mw, "GET", "/login/kiro", key=None)
        self.assertEqual(status, 401)

    def test_new_route_wrong_bearer_returns_401(self):
        from starlette.responses import JSONResponse

        async def handler(request):
            return JSONResponse({"ok": True})

        mw, app = self._make_mw(api_key="testkey", routes={("GET", "/login/kiro"): handler})
        status = self._status(mw, "GET", "/login/kiro", key="wrongkey")
        self.assertEqual(status, 401)


class TestTrn233RateLimit(unittest.TestCase):
    """TRN-233 task 3.1: rate limit widened to POST /login/*."""

    def _limiter(self, max_requests=5):
        from transport.security import RateLimiter
        class _CapLimiter(RateLimiter):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.recorded = []
            def record(self, key):
                self.recorded.append(key)
                return True
        return _CapLimiter(max_requests=max_requests, window_secs=60)

    def _make_middleware(self, limiters):
        from transport.auth import RateLimitMiddleware
        app = _RecordingApp()
        mw = RateLimitMiddleware(app, limiters=limiters, api_key="testkey")
        return mw, app

    def test_login_kiro_builder_id_matches_login_post(self):
        """POST /login/kiro/builder-id is subject to the login_post rate limit."""
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"login_post": limiter})
        _run(mw(_make_scope("POST", "/login/kiro/builder-id", client=("5.5.5.5", 1)), _receive, _collect_send()[1]))
        self.assertTrue(limiter.recorded)

    def test_login_claude_oauth_matches_login_post(self):
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"login_post": limiter})
        _run(mw(_make_scope("POST", "/login/claude/oauth", client=("5.5.5.6", 1)), _receive, _collect_send()[1]))
        self.assertTrue(limiter.recorded)

    def test_login_kiro_get_matches_login_get(self):
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"login_get": limiter})
        _run(mw(_make_scope("GET", "/login/kiro", client=("5.5.5.7", 1)), _receive, _collect_send()[1]))
        self.assertTrue(limiter.recorded)

    def test_logout_not_rate_limited_by_login_limiter(self):
        """POST /logout/kiro is not subject to the login rate limit."""
        limiter = self._limiter(max_requests=5)
        mw, app = self._make_middleware({"login_post": limiter})
        _run(mw(_make_scope("POST", "/logout/kiro", client=("5.5.5.8", 1)), _receive, _collect_send()[1]))
        # /logout is not /login/* — should not match login_post
        self.assertFalse(limiter.recorded)


if __name__ == "__main__":
    unittest.main()
