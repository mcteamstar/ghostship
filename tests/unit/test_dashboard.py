"""Unit tests for transport/dashboard.py — DashboardGate unit tests.

Covers the DashboardGate class and its pure helper _validate_next_url:
- ``TestValidateNextUrl``           — open-redirect guard, NFKC normalisation,
                                      backslash rejection, empty-string fallback
- ``TestDashboardGateCsrfUniqueness`` — per-request CSRF tokens are distinct
- ``TestDashboardGateCsrfRejection``  — mismatched/absent CSRF → 401/403; correct → 200
- ``TestDashboardGateCookieFlags``    — SameSite=Lax always; Secure iff https

Design (see openspec/changes/trn-275-server-dashboard-unit-tests/design.md):
- ``DashboardGate`` is constructed with explicit ``session_ttl_secs``,
  ``api_key``, and ``external_url`` arguments — no module-level patching.
- Tests call handler methods directly (not via ASGI middleware), passing
  minimal ``FakeRequest`` objects with controlled ``cookies``, ``form()``
  return values, and ``client``.
- ASGI responses are collected by awaiting the response object directly.
- ``_validate_next_url`` is a pure function — no ASGI scaffolding.

Dual-import shim (container flat layout vs. local dev package):
    try:
        import dashboard as _dashboard        # /app/dashboard.py (container)
    except ModuleNotFoundError:
        from transport import dashboard as _dashboard   # local dev
"""

from __future__ import annotations

import asyncio
import re
import unittest


# ── Shared ASGI helpers ───────────────────────────────────────────────────────

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


def _headers_of(messages):
    for msg in messages:
        if msg.get("type") == "http.response.start":
            return list(msg.get("headers", []))
    return []


def _set_cookie_of(messages):
    """Return the Set-Cookie header value from the first http.response.start, or ''."""
    for k, v in _headers_of(messages):
        if k.lower() == b"set-cookie":
            return v.decode("latin-1")
    return ""


_HTTP_SCOPE = {
    "type": "http",
    "method": "GET",
    "path": "/dashboard/login",
    "headers": [],
    "scheme": "http",
    "query_string": b"",
}

_POST_SCOPE = {
    "type": "http",
    "method": "POST",
    "path": "/dashboard/login",
    "headers": [],
    "scheme": "http",
    "query_string": b"",
}


class FakeRequest:
    """Minimal Starlette Request substitute for DashboardGate handler tests.

    Provides ``cookies``, ``form()``, ``headers``, ``client``, and
    ``query_params``.  All fields are set at construction time.
    """

    def __init__(
        self,
        scope=None,
        form_data: dict | None = None,
        cookies: dict | None = None,
        query_params: dict | None = None,
    ) -> None:
        self.scope = scope or _HTTP_SCOPE
        self._form = form_data or {}
        self.cookies = cookies or {}
        self.client = None  # throttle source falls back to None gracefully
        self.headers = type(
            "_Headers",
            (),
            {
                "get": lambda s, k, d="": "",
                "items": lambda s: [],
            },
        )()
        qp = query_params or {}
        self.query_params = type(
            "_QP",
            (),
            {"get": lambda s, k, d="": qp.get(k, d)},
        )()

    async def form(self) -> dict:
        return self._form


async def _collect_response(resp, scope=None) -> list:
    """Await a DashboardGate Response as an ASGI callable and collect messages."""
    messages = []

    async def send(msg):
        messages.append(msg)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await resp(scope or _HTTP_SCOPE, receive, send)
    return messages


# ── TestValidateNextUrl ───────────────────────────────────────────────────────


class TestValidateNextUrl(unittest.TestCase):
    """_validate_next_url is a pure function that guards open redirects."""

    def _fn(self):
        try:
            import dashboard as _d
        except ModuleNotFoundError:
            from transport import dashboard as _d
        return _d._validate_next_url

    def test_relative_path_passes_through(self):
        fn = self._fn()
        self.assertEqual(fn("/dashboard"), "/dashboard")

    def test_relative_path_with_query(self):
        fn = self._fn()
        self.assertEqual(fn("/crews?tab=1"), "/crews?tab=1")

    def test_protocol_relative_rejected(self):
        fn = self._fn()
        self.assertEqual(fn("//evil.com"), "/")

    def test_absolute_http_url_rejected(self):
        fn = self._fn()
        self.assertEqual(fn("http://evil.com/steal"), "/")

    def test_absolute_https_url_rejected(self):
        fn = self._fn()
        self.assertEqual(fn("https://evil.com"), "/")

    def test_javascript_scheme_rejected(self):
        fn = self._fn()
        self.assertEqual(fn("javascript:alert(1)"), "/")

    def test_nfkc_lookalike_rejected(self):
        fn = self._fn()
        # Fullwidth ASCII chars that NFKC-normalise to letters — would bypass
        # a naive startswith check if normalisation were absent.
        # "ＡＢＣ" NFKC-normalises to "ABC", which does not start with "/".
        self.assertEqual(fn("\uff21\uff22\uff23"), "/")

    def test_backslash_rejected(self):
        fn = self._fn()
        # Browsers treat "\" as "/" — "/\evil.com" would become "//evil.com".
        self.assertEqual(fn("/\\evil.com"), "/")

    def test_empty_string_returns_root(self):
        fn = self._fn()
        self.assertEqual(fn(""), "/")

    def test_control_char_rejected(self):
        fn = self._fn()
        # Path with embedded LF should be rejected.
        self.assertEqual(fn("/foo\nX-Injected: 1"), "/")

    def test_plain_root_passes_through(self):
        fn = self._fn()
        self.assertEqual(fn("/"), "/")


# ── TestDashboardGateCsrfUniqueness ──────────────────────────────────────────


class TestDashboardGateCsrfUniqueness(unittest.TestCase):
    """Each call to handle_login_get issues a distinct gs_csrf CSRF nonce."""

    def _gate(self, **kwargs):
        try:
            import dashboard as _d
        except ModuleNotFoundError:
            from transport import dashboard as _d
        return _d.DashboardGate(
            session_ttl_secs=kwargs.get("session_ttl_secs", 3600),
            api_key=kwargs.get("api_key", "testkey"),
            external_url=kwargs.get("external_url", "http://localhost"),
        )

    def _csrf_from_messages(self, messages):
        cookie = _set_cookie_of(messages)
        m = re.search(r"gs_csrf=([^;]+)", cookie)
        return m.group(1) if m else None

    def test_two_gate_instances_issue_distinct_csrf(self):
        gate1 = self._gate()
        gate2 = self._gate()

        req1 = FakeRequest(scope=_HTTP_SCOPE)
        req2 = FakeRequest(scope=_HTTP_SCOPE)

        async def run():
            r1 = await gate1.handle_login_get(req1)
            r2 = await gate2.handle_login_get(req2)
            msgs1 = await _collect_response(r1, _HTTP_SCOPE)
            msgs2 = await _collect_response(r2, _HTTP_SCOPE)
            return msgs1, msgs2

        msgs1, msgs2 = _run(run())
        csrf1 = self._csrf_from_messages(msgs1)
        csrf2 = self._csrf_from_messages(msgs2)
        self.assertIsNotNone(csrf1, "first gate should issue a gs_csrf cookie")
        self.assertIsNotNone(csrf2, "second gate should issue a gs_csrf cookie")
        self.assertNotEqual(csrf1, csrf2, "CSRF tokens from two gates must be distinct")

    def test_same_gate_two_calls_issue_distinct_csrf(self):
        gate = self._gate()

        req1 = FakeRequest(scope=_HTTP_SCOPE)
        req2 = FakeRequest(scope=_HTTP_SCOPE)

        async def run():
            r1 = await gate.handle_login_get(req1)
            r2 = await gate.handle_login_get(req2)
            msgs1 = await _collect_response(r1, _HTTP_SCOPE)
            msgs2 = await _collect_response(r2, _HTTP_SCOPE)
            return msgs1, msgs2

        msgs1, msgs2 = _run(run())
        csrf1 = self._csrf_from_messages(msgs1)
        csrf2 = self._csrf_from_messages(msgs2)
        self.assertIsNotNone(csrf1)
        self.assertIsNotNone(csrf2)
        self.assertNotEqual(csrf1, csrf2)

    def test_csrf_cookie_is_samesite_strict(self):
        gate = self._gate()
        req = FakeRequest(scope=_HTTP_SCOPE)

        async def run():
            r = await gate.handle_login_get(req)
            return await _collect_response(r, _HTTP_SCOPE)

        msgs = _run(run())
        cookie = _set_cookie_of(msgs)
        self.assertIn("SameSite=Strict", cookie)

    def test_csrf_cookie_httponly_false(self):
        """gs_csrf must NOT be HttpOnly — JS reads it for the cookie-echo pattern."""
        gate = self._gate()
        req = FakeRequest(scope=_HTTP_SCOPE)

        async def run():
            r = await gate.handle_login_get(req)
            return await _collect_response(r, _HTTP_SCOPE)

        msgs = _run(run())
        cookie = _set_cookie_of(msgs)
        self.assertNotIn("HttpOnly", cookie.replace("gs_session", ""))


# ── TestDashboardGateCsrfRejection ────────────────────────────────────────────


class TestDashboardGateCsrfRejection(unittest.TestCase):
    """handle_login_post rejects forged or absent CSRF tokens."""

    _CSRF_TOKEN = "a" * 64  # 64-char hex-like test token

    def _gate(self, **kwargs):
        try:
            import dashboard as _d
        except ModuleNotFoundError:
            from transport import dashboard as _d
        return _d.DashboardGate(
            session_ttl_secs=3600,
            api_key=kwargs.get("api_key", "testkey"),
            external_url="http://localhost",
        )

    def _post(self, gate, form_data, cookies):
        req = FakeRequest(scope=_POST_SCOPE, form_data=form_data, cookies=cookies)

        async def run():
            r = await gate.handle_login_post(req)
            return await _collect_response(r, _POST_SCOPE)

        return _run(run())

    def test_mismatched_csrf_returns_403(self):
        gate = self._gate()
        msgs = self._post(
            gate,
            form_data={"csrf_token": "wrong_token", "ga_api_key": "testkey"},
            cookies={"gs_csrf": self._CSRF_TOKEN},
        )
        self.assertEqual(_status_of(msgs), 403)

    def test_absent_csrf_token_field_returns_403(self):
        gate = self._gate()
        msgs = self._post(
            gate,
            form_data={"ga_api_key": "testkey"},  # no csrf_token key
            cookies={"gs_csrf": self._CSRF_TOKEN},
        )
        self.assertEqual(_status_of(msgs), 403)

    def test_absent_csrf_cookie_returns_403(self):
        gate = self._gate()
        msgs = self._post(
            gate,
            form_data={"csrf_token": self._CSRF_TOKEN, "ga_api_key": "testkey"},
            cookies={},  # no gs_csrf cookie
        )
        self.assertEqual(_status_of(msgs), 403)

    def test_matching_csrf_with_correct_api_key_returns_200(self):
        gate = self._gate()
        msgs = self._post(
            gate,
            form_data={
                "csrf_token": self._CSRF_TOKEN,
                "ga_api_key": "testkey",
                "next": "/",
            },
            cookies={"gs_csrf": self._CSRF_TOKEN},
        )
        self.assertEqual(_status_of(msgs), 200)

    def test_matching_csrf_wrong_api_key_returns_401(self):
        gate = self._gate()
        msgs = self._post(
            gate,
            form_data={
                "csrf_token": self._CSRF_TOKEN,
                "ga_api_key": "wrongkey",
                "next": "/",
            },
            cookies={"gs_csrf": self._CSRF_TOKEN},
        )
        self.assertEqual(_status_of(msgs), 401)


# ── TestDashboardGateCookieFlags ──────────────────────────────────────────────


class TestDashboardGateCookieFlags(unittest.TestCase):
    """After a successful login, gs_session cookie must carry correct flags.

    - ``SameSite=Lax`` is always present.
    - ``Secure`` is present when ``external_url`` is ``https://...``
    - ``Secure`` is absent when ``external_url`` is ``http://...``
    """

    _CSRF_TOKEN = "b" * 64

    def _gate(self, external_url: str):
        try:
            import dashboard as _d
        except ModuleNotFoundError:
            from transport import dashboard as _d
        return _d.DashboardGate(
            session_ttl_secs=3600,
            api_key="testkey",
            external_url=external_url,
        )

    def _login(self, gate):
        req = FakeRequest(
            scope=_POST_SCOPE,
            form_data={
                "csrf_token": self._CSRF_TOKEN,
                "ga_api_key": "testkey",
                "next": "/",
            },
            cookies={"gs_csrf": self._CSRF_TOKEN},
        )

        async def run():
            r = await gate.handle_login_post(req)
            return await _collect_response(r, _POST_SCOPE)

        return _run(run())

    def test_samesite_lax_always_present(self):
        gate = self._gate("http://localhost")
        msgs = self._login(gate)
        self.assertEqual(_status_of(msgs), 200)
        cookie = _set_cookie_of(msgs)
        self.assertIn("SameSite=Lax", cookie)

    def test_secure_absent_for_http_external_url(self):
        gate = self._gate("http://localhost")
        msgs = self._login(gate)
        cookie = _set_cookie_of(msgs)
        # "Secure" must not appear in the gs_session cookie when TLS is off.
        self.assertNotIn("Secure", cookie)

    def test_secure_present_for_https_external_url(self):
        gate = self._gate("https://example.com")
        msgs = self._login(gate)
        self.assertEqual(_status_of(msgs), 200)
        cookie = _set_cookie_of(msgs)
        self.assertIn("Secure", cookie)

    def test_httponly_present(self):
        gate = self._gate("http://localhost")
        msgs = self._login(gate)
        cookie = _set_cookie_of(msgs)
        self.assertIn("HttpOnly", cookie)

    def test_gs_session_cookie_name_present(self):
        gate = self._gate("http://localhost")
        msgs = self._login(gate)
        cookie = _set_cookie_of(msgs)
        self.assertTrue(cookie.startswith("gs_session="))


if __name__ == "__main__":
    unittest.main()
