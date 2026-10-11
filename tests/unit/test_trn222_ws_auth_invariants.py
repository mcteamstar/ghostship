"""TRN-222 — WS auth baseline regression tests.

Pins the two code invariants that make KiroCrew 0.9.0's per-app WS event
scoping and WS broadcast content redaction harmless to ghostship's portal:

  1. **No X-App-Token on the WS proxy path** (SA-2 / design D1)
     ``crew_proxy_handler`` injects only ``X-Transport-Token``; it MUST NOT
     inject ``X-App-Token`` (or any per-app token header).  The per-app WS
     scoping in KiroCrew 0.9.0 (PR #714) filters *only* connections that
     present an app token, so the absence of that header keeps the dashboard
     WS on the full-stream path.

  2. **DashboardGate.handle_auth reads only the gs_session cookie** (SA-4)
     No WS payload body, no ``X-App-Token`` header, is ever inspected by the
     forward_auth endpoint.  The portal's WS upgrade authenticates by the
     browser session cookie established on the SPA's initial HTTP load.

If either invariant is broken by a future PR, this file becomes a loud CI
failure rather than a silent regression.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import Mock, patch

from tests.unit._stubs import install_import_stubs

install_import_stubs()

import transport.caddy as _caddy_mod       # noqa: E402
import transport.server as server           # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────────

class _FakeRequest:
    """Minimal request stub for handle_auth tests."""

    def __init__(
        self,
        *,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> None:
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.query_params = query_params or {}


def _build_crew_proxy_handler() -> dict:
    """Return the crew_proxy_handler produced by CaddyPortal.register_crew."""
    portal = _caddy_mod.CaddyPortal(
        port=8080,
        api_key="test-key",
        port_range_start=9000,
        port_range_size=50,
    )

    captured_payload: dict = {}

    def fake_put(url: str, *, json: dict, timeout: float = 5.0) -> Mock:
        captured_payload.update(json)
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        return resp

    with patch.object(_caddy_mod.httpx, "put", side_effect=fake_put):
        portal.register_crew("alpha", 64058)

    # The WS route is routes[0]; extract its handler.
    routes = captured_payload.get("routes", [])
    assert len(routes) == 2, f"Expected 2 routes, got {len(routes)}: {routes}"
    ws_route = routes[0]
    assert ws_route["match"] == [{"header": {"Connection": ["Upgrade"]}}], (
        f"Expected WS-upgrade matcher, got: {ws_route.get('match')}"
    )
    return ws_route["handle"][0]


# ── TRN-222 invariant 1: No X-App-Token on WS proxy path ─────────────────────

class WsProxyNoAppTokenTests(unittest.TestCase):
    """SA-2 / D1 — crew_proxy_handler MUST NOT inject X-App-Token."""

    def setUp(self) -> None:
        self._handler = _build_crew_proxy_handler()

    def test_ws_proxy_handler_sets_x_transport_token(self) -> None:
        """WS proxy handler injects X-Transport-Token (transport auth)."""
        set_headers = self._handler.get("headers", {}).get("request", {}).get("set", {})
        self.assertIn(
            "X-Transport-Token", set_headers,
            "crew_proxy_handler must inject X-Transport-Token on the WS path",
        )

    def test_ws_proxy_handler_has_no_x_app_token(self) -> None:
        """TRN-222 / D1: WS proxy handler MUST NOT inject X-App-Token.

        KiroCrew 0.9.0 per-app WS scoping (PR #714) filters events for
        connections that carry an X-App-Token.  A WS upgrade that carries
        that header would receive only that app's events, breaking the
        ghostship portal which needs all crew events.  The dashboard WS
        path authenticates via gs_session cookie and MUST stay app-token-free.
        """
        set_headers = self._handler.get("headers", {}).get("request", {}).get("set", {})
        self.assertNotIn(
            "X-App-Token", set_headers,
            "crew_proxy_handler must NOT inject X-App-Token on the WS path; "
            "doing so would subject the dashboard WS to per-app KiroCrew 0.9.0 event scoping. "
            "See TRN-222 design D1.",
        )

    def test_ws_proxy_handler_only_transport_token_injected(self) -> None:
        """Only X-Transport-Token is injected — no extra per-app headers."""
        set_headers = self._handler.get("headers", {}).get("request", {}).get("set", {})
        self.assertEqual(
            set(set_headers.keys()),
            {"X-Transport-Token"},
            "crew_proxy_handler should inject exactly X-Transport-Token and nothing else. "
            "Adding any app-token header here risks triggering per-app WS event scoping. "
            "See TRN-222 design D1.",
        )


# ── TRN-222 invariant 2: handle_auth reads only gs_session ───────────────────

class HandleAuthCookieOnlyTests(unittest.TestCase):
    """SA-4 / D1 — DashboardGate.handle_auth MUST authenticate via gs_session only."""

    def setUp(self) -> None:
        self._sessions = server._security.SessionStore(lifetime_secs=3600)
        self._orig_api_key = server._dashboard_gate._api_key
        server._dashboard_gate._api_key = "test-key"

    def tearDown(self) -> None:
        server._dashboard_gate._api_key = self._orig_api_key

    def _run(self, cookies: dict | None = None, headers: dict | None = None) -> int:
        with patch.object(server._dashboard_gate, "_sessions", self._sessions):
            req = _FakeRequest(cookies=cookies or {}, headers=headers or {})
            resp = asyncio.run(server._dashboard_gate.handle_auth(req))
        return resp.status_code

    def test_valid_gs_session_returns_200(self) -> None:
        """A valid gs_session cookie is sufficient for auth."""
        token = self._sessions.issue()
        status = self._run(cookies={"gs_session": token})
        self.assertEqual(status, 200)

    def test_missing_gs_session_returns_401(self) -> None:
        """No gs_session cookie → 401; no other cookie path exists."""
        status = self._run(cookies={})
        self.assertEqual(status, 401)

    def test_x_app_token_header_alone_does_not_grant_access(self) -> None:
        """TRN-222 / D1: X-App-Token header MUST NOT bypass the gs_session check.

        handle_auth validates only the gs_session cookie.  An X-App-Token
        header carries no session credential for this endpoint — presenting
        one without a valid gs_session must still return 401.
        """
        status = self._run(
            cookies={},
            headers={"X-App-Token": "some-app-token"},
        )
        self.assertEqual(
            status, 401,
            "X-App-Token alone must not grant access; "
            "forward_auth is cookie-gated only (gs_session). See TRN-222 SA-4.",
        )

    def test_gs_session_with_x_app_token_returns_200(self) -> None:
        """A valid gs_session is sufficient even when X-App-Token is also present."""
        token = self._sessions.issue()
        status = self._run(
            cookies={"gs_session": token},
            headers={"X-App-Token": "some-app-token"},
        )
        self.assertEqual(
            status, 200,
            "A valid gs_session must grant access regardless of any "
            "X-App-Token header being present.",
        )


if __name__ == "__main__":
    unittest.main()
