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
  The conftest stubs are sufficient to import server.py in the test environment.
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


if __name__ == "__main__":
    unittest.main()
