"""Unit tests for trn-237-csp-inline-scripts: nonce generation, middleware
threading, login-page stamping, and end-to-end CSP consistency.

Tests cover:
  Section 2: SecurityHeadersMiddleware threads a per-request nonce
    2.1  Response CSP contains 'nonce-...' and scope["csp_nonce"] matches
    2.2  Two requests through the middleware produce different nonces

  Section 3: DashboardGate.handle_login_get stamps the nonce on inline tags
    3.1  <style> and <script> tags gain nonce="..." when scope has csp_nonce
    3.2  Tags are emitted WITHOUT nonce when scope has no csp_nonce; page is 200 text/html

  Section 4: End-to-end CSP consistency
    4.1  Enforced middleware wrapping the login route: nonce in header matches
         nonce in HTML inline tags
    4.2  No regressions: no 'unsafe-inline' or 'unsafe-eval' in any path
"""

from __future__ import annotations

import asyncio
import re
import unittest

# Bootstrap stubs (installs httpx/mcp/starlette stubs if absent).
from tests.unit.test_file_transfer import server  # noqa: F401

import transport.auth as _auth_mod
import transport.security as _security
import transport.dashboard as _dashboard_mod

# ── helpers ────────────────────────────────────────────────────────────────────


def _run_middleware(mw, scope, body=b""):
    """Drive an ASGI middleware synchronously; return (status, headers_dict, body)."""
    status = None
    resp_headers = {}
    resp_body = b""

    async def receive():
        return {"type": "http.request", "body": body}

    async def send(msg):
        nonlocal status, resp_headers, resp_body
        if msg["type"] == "http.response.start":
            status = msg["status"]
            resp_headers = {k.lower(): v for k, v in msg.get("headers", [])}
        elif msg["type"] == "http.response.body":
            resp_body += msg.get("body", b"")

    asyncio.run(mw(scope, receive, send))
    return status, resp_headers, resp_body


def _http_scope(path="/login", method="GET", https=False):
    scheme = "https" if https else "http"
    return {
        "type": "http",
        "method": method,
        "path": path,
        "scheme": scheme,
        "headers": [],
        "query_string": b"",
    }


class _Downstream:
    """Minimal ASGI app that records the scope it received."""

    def __init__(self):
        self.called = False
        self.scope = None

    async def __call__(self, scope, receive, send):
        self.called = True
        self.scope = scope
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


# ── Section 2: Middleware nonce threading ──────────────────────────────────────


class TestMiddlewareNonceThreading(unittest.TestCase):
    """SecurityHeadersMiddleware.2.1 / 2.2 — per-request nonce in scope + header."""

    def _make_mw(self, csp_enforce=True):
        downstream = _Downstream()
        mw = _auth_mod.SecurityHeadersMiddleware(
            downstream,
            enable_headers=True,
            enforce_redirect=False,
            csp_enforce=csp_enforce,
        )
        return mw, downstream

    def test_2_1_nonce_in_csp_header(self):
        """Response CSP header contains a 'nonce-...' value."""
        mw, downstream = self._make_mw(csp_enforce=True)
        scope = _http_scope()
        status, headers, _ = _run_middleware(mw, scope)
        self.assertEqual(status, 200)
        csp = headers.get(b"content-security-policy", b"").decode("latin-1")
        self.assertRegex(csp, r"'nonce-[A-Za-z0-9_-]+'")

    def test_2_1_nonce_in_scope(self):
        """scope['csp_nonce'] is populated before the downstream app runs."""
        mw, downstream = self._make_mw(csp_enforce=True)
        scope = _http_scope()
        _run_middleware(mw, scope)
        self.assertTrue(downstream.called)
        self.assertIn("csp_nonce", downstream.scope)
        nonce = downstream.scope["csp_nonce"]
        self.assertTrue(nonce, "scope['csp_nonce'] must be non-empty")

    def test_2_1_scope_nonce_matches_csp_header(self):
        """The nonce in scope['csp_nonce'] equals the nonce in the CSP header."""
        mw, downstream = self._make_mw(csp_enforce=True)
        scope = _http_scope()
        _, headers, _ = _run_middleware(mw, scope)
        csp = headers.get(b"content-security-policy", b"").decode("latin-1")
        scope_nonce = downstream.scope["csp_nonce"]
        self.assertIn(f"'nonce-{scope_nonce}'", csp)

    def test_2_2_nonces_differ_across_requests(self):
        """Two separate requests through the middleware get different nonces."""
        mw, _ = self._make_mw(csp_enforce=True)
        scope1 = _http_scope()
        scope2 = _http_scope()

        _, h1, _ = _run_middleware(mw, scope1)
        _, h2, _ = _run_middleware(mw, scope2)

        nonce1 = scope1.get("csp_nonce")
        nonce2 = scope2.get("csp_nonce")
        self.assertIsNotNone(nonce1)
        self.assertIsNotNone(nonce2)
        self.assertNotEqual(nonce1, nonce2, "Per-request nonces must be unique")

    def test_2_1_report_only_mode_also_threads_nonce(self):
        """Report-only mode (csp_enforce=False) also injects nonce into scope."""
        mw, downstream = self._make_mw(csp_enforce=False)
        scope = _http_scope()
        _, headers, _ = _run_middleware(mw, scope)
        csp = headers.get(b"content-security-policy-report-only", b"").decode("latin-1")
        self.assertIn("csp_nonce", downstream.scope)
        nonce = downstream.scope["csp_nonce"]
        self.assertIn(f"'nonce-{nonce}'", csp)


# ── Section 3: Login-page nonce stamping ──────────────────────────────────────


class _MinimalRequest:
    """Minimal request stub for DashboardGate handler tests."""

    def __init__(self, scope=None, query_params=None, cookies=None):
        self.scope = scope if scope is not None else {"type": "http"}
        self.query_params = query_params or {}
        self.cookies = cookies or {}


class TestLoginPageNonceStamping(unittest.TestCase):
    """DashboardGate.handle_login_get.3.1 / 3.2 — nonce attribute on inline tags."""

    def _make_gate(self):
        return _dashboard_mod.DashboardGate(
            session_ttl_secs=3600,
            api_key="test-key",
            tls_mode="off",
        )

    def _get_login_html(self, nonce=None):
        gate = self._make_gate()
        scope = {"type": "http"}
        if nonce is not None:
            scope["csp_nonce"] = nonce
        req = _MinimalRequest(scope=scope)
        resp = asyncio.run(gate.handle_login_get(req))
        return resp

    def test_3_1_style_tag_gets_nonce_attribute(self):
        """<style> tag gains nonce="..." when scope has csp_nonce."""
        nonce = "TestNonce111"
        resp = self._get_login_html(nonce=nonce)
        self.assertEqual(resp.status_code, 200)
        html = resp.body.decode("utf-8")
        self.assertIn(f'<style nonce="{nonce}">', html)

    def test_3_1_script_tag_gets_nonce_attribute(self):
        """<script> tag gains nonce="..." when scope has csp_nonce."""
        nonce = "TestNonce222"
        resp = self._get_login_html(nonce=nonce)
        html = resp.body.decode("utf-8")
        self.assertIn(f'<script nonce="{nonce}">', html)

    def test_3_2_no_nonce_in_scope_omits_attribute(self):
        """Tags are emitted WITHOUT nonce attribute when scope has no csp_nonce."""
        resp = self._get_login_html(nonce=None)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        html = resp.body.decode("utf-8")
        # No nonce attribute on style or script
        self.assertNotRegex(html, r"<style\s+nonce=")
        self.assertNotRegex(html, r"<script\s+nonce=")
        # But the tags themselves are still present
        self.assertIn("<style>", html)
        self.assertIn("<script>", html)

    def test_3_2_no_nonce_page_returns_200_text_html(self):
        """Login page without nonce returns 200 text/html."""
        resp = self._get_login_html(nonce=None)
        self.assertEqual(resp.status_code, 200)
        content_type = resp.headers.get("content-type", "")
        self.assertIn("text/html", content_type)


# ── Section 4: End-to-end CSP consistency ─────────────────────────────────────


class TestEndToEndCspConsistency(unittest.TestCase):
    """4.1 / 4.2 — enforced middleware + login route: nonce in header matches HTML."""

    def _run_login_through_middleware(self, csp_enforce=True):
        """Run the login GET through SecurityHeadersMiddleware wrapping a real
        DashboardGate.handle_login_get. Returns (csp_header_str, html_body)."""
        gate = _dashboard_mod.DashboardGate(
            session_ttl_secs=3600,
            api_key="test-key",
            tls_mode="off",
        )

        async def login_asgi(scope, receive, send):
            """Minimal ASGI adapter for handle_login_get using stub-compatible request."""
            req = _MinimalRequest(scope=scope, query_params={})
            resp = await gate.handle_login_get(req)
            # Emit the response through ASGI — starlette stub may not support
            # resp(scope, receive, send) directly, so emit manually.
            body = resp.body if hasattr(resp, "body") else b""
            raw_hdrs = list(resp.raw_headers) if hasattr(resp, "raw_headers") else []
            await send({
                "type": "http.response.start",
                "status": resp.status_code,
                "headers": raw_hdrs,
            })
            await send({"type": "http.response.body", "body": body})

        mw = _auth_mod.SecurityHeadersMiddleware(
            login_asgi,
            enable_headers=True,
            enforce_redirect=False,
            csp_enforce=csp_enforce,
        )

        scope = _http_scope(path="/dashboard/login", method="GET", https=False)
        status, headers, body = _run_middleware(mw, scope)

        if csp_enforce:
            csp = headers.get(b"content-security-policy", b"").decode("latin-1")
        else:
            csp = headers.get(b"content-security-policy-report-only", b"").decode("latin-1")

        return status, csp, body.decode("utf-8")

    def test_4_1_nonce_in_csp_matches_nonce_in_html_style_tag(self):
        """CSP nonce matches the nonce attribute on <style> in the login HTML."""
        status, csp, html = self._run_login_through_middleware(csp_enforce=True)
        self.assertEqual(status, 200)

        # Extract nonce from CSP: 'nonce-<value>'
        m = re.search(r"'nonce-([A-Za-z0-9_-]+)'", csp)
        self.assertIsNotNone(m, f"No nonce found in CSP: {csp!r}")
        csp_nonce = m.group(1)

        self.assertIn(f'<style nonce="{csp_nonce}">', html,
                      "CSP nonce must appear in <style> nonce attribute")

    def test_4_1_nonce_in_csp_matches_nonce_in_html_script_tag(self):
        """CSP nonce matches the nonce attribute on <script> in the login HTML."""
        status, csp, html = self._run_login_through_middleware(csp_enforce=True)
        self.assertEqual(status, 200)

        m = re.search(r"'nonce-([A-Za-z0-9_-]+)'", csp)
        self.assertIsNotNone(m)
        csp_nonce = m.group(1)

        self.assertIn(f'<script nonce="{csp_nonce}">', html,
                      "CSP nonce must appear in <script> nonce attribute")

    def test_4_1_enforced_csp_header_present_not_report_only(self):
        """Enforce mode emits content-security-policy, not content-security-policy-report-only."""
        status, csp, _ = self._run_login_through_middleware(csp_enforce=True)
        self.assertEqual(status, 200)
        self.assertTrue(csp, "content-security-policy header must be present in enforce mode")

    def test_4_2_no_unsafe_inline_in_enforced_csp(self):
        """Enforced CSP does not contain 'unsafe-inline'."""
        _, csp, _ = self._run_login_through_middleware(csp_enforce=True)
        self.assertNotIn("'unsafe-inline'", csp)

    def test_4_2_no_unsafe_eval_in_enforced_csp(self):
        """Enforced CSP does not contain 'unsafe-eval'."""
        _, csp, _ = self._run_login_through_middleware(csp_enforce=True)
        self.assertNotIn("'unsafe-eval'", csp)

    def test_4_2_no_unsafe_inline_in_report_only_csp(self):
        """Report-only CSP also does not contain 'unsafe-inline'."""
        _, csp, _ = self._run_login_through_middleware(csp_enforce=False)
        self.assertNotIn("'unsafe-inline'", csp)


if __name__ == "__main__":
    unittest.main()
