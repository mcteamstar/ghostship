"""Unit tests for transport/caddy.py.

Covers:
- CaddyPortal port pool allocation and release (allocate_port / release_port)
- Module-level port wrappers (_allocate_dashboard_port / _release_dashboard_port)
- CaddyPortal.register_crew: reverse proxy config structure and routing contract
- CaddyPortal.register_crew: retry and error paths
- CaddyPortal.deregister_crew: HTTP status code handling and error paths
- Module-level thin wrappers (_caddy_register_crew / _caddy_deregister_crew)
- _caddy_admin_url() constant
- CaddyPortal constructor field storage

All HTTP calls are intercepted with unittest.mock.patch — no live Caddy process
required. The module-level _dashboard_ports_in_use set is cleared in setUp /
tearDown for every test class that mutates it to prevent cross-test leakage.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch

import transport.caddy
from transport.caddy import (
    CaddyPortal,
    _allocate_dashboard_port,
    _caddy_admin_url,
    _caddy_deregister_crew,
    _caddy_register_crew,
    _dashboard_ports_in_use,
    _release_dashboard_port,
)


# ── 2. TestCaddyPortalPortPool ────────────────────────────────────────────────


class TestCaddyPortalPortPool(unittest.TestCase):
    """CaddyPortal.allocate_port and release_port — port pool management."""

    def setUp(self):
        transport.caddy._dashboard_ports_in_use.clear()

    def tearDown(self):
        transport.caddy._dashboard_ports_in_use.clear()

    # 2.2
    def test_allocate_returns_range_start_when_pool_empty(self):
        portal = CaddyPortal(port=0, api_key="", port_range_start=8000, port_range_size=10)
        result = portal.allocate_port()
        self.assertEqual(result, 8000)
        self.assertIn(8000, transport.caddy._dashboard_ports_in_use)

    # 2.3
    def test_allocate_skips_in_use_port(self):
        transport.caddy._dashboard_ports_in_use.add(8000)
        portal = CaddyPortal(port=0, api_key="", port_range_start=8000, port_range_size=10)
        result = portal.allocate_port()
        self.assertEqual(result, 8001)

    # 2.4
    def test_allocate_raises_when_pool_exhausted(self):
        transport.caddy._dashboard_ports_in_use.update(range(8000, 8010))
        portal = CaddyPortal(port=0, api_key="", port_range_start=8000, port_range_size=10)
        with self.assertRaises(RuntimeError):
            portal.allocate_port()

    # 2.5
    def test_release_then_reallocate(self):
        portal = CaddyPortal(port=0, api_key="", port_range_start=8000, port_range_size=10)
        allocated = portal.allocate_port()
        portal.release_port(allocated)
        reallocated = portal.allocate_port()
        self.assertEqual(reallocated, allocated)

    # 2.6
    def test_release_absent_port_is_noop(self):
        portal = CaddyPortal(port=0, api_key="", port_range_start=8000, port_range_size=10)
        portal.release_port(9999)  # must not raise
        self.assertEqual(len(transport.caddy._dashboard_ports_in_use), 0)


# ── 3. TestModuleLevelPortWrappers ────────────────────────────────────────────


class TestModuleLevelPortWrappers(unittest.TestCase):
    """_allocate_dashboard_port and _release_dashboard_port delegate to module portal."""

    def setUp(self):
        transport.caddy._dashboard_ports_in_use.clear()
        self._start_patcher = patch.object(
            transport.caddy, "GA_DASHBOARD_PORT_RANGE_START", 9100
        )
        self._size_patcher = patch.object(
            transport.caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 5
        )
        self._start_patcher.start()
        self._size_patcher.start()

    def tearDown(self):
        self._start_patcher.stop()
        self._size_patcher.stop()
        transport.caddy._dashboard_ports_in_use.clear()

    # 3.2
    def test_allocate_dashboard_port_returns_range_port(self):
        result = _allocate_dashboard_port()
        self.assertIn(result, range(9100, 9105))

    # 3.3
    def test_release_dashboard_port_removes_port(self):
        port = _allocate_dashboard_port()
        _release_dashboard_port(port)
        self.assertNotIn(port, transport.caddy._dashboard_ports_in_use)


# ── 4. TestCaddyPortalRegisterCrew — config and routing structure ─────────────


class TestCaddyPortalRegisterCrew(unittest.TestCase):
    """CaddyPortal.register_crew: correct Caddy server object structure."""

    def _make_portal(self, api_key=""):
        return CaddyPortal(port=5476, api_key=api_key, port_range_start=9000, port_range_size=10)

    def _call_register(self, portal, crew_id="abc", port=8765, status=200):
        mock_resp = MagicMock(status_code=status, text="")
        with patch("transport.caddy.httpx.put", return_value=mock_resp, create=True) as mock_put:
            portal.register_crew(crew_id, port)
        return mock_put

    def _get_put_body(self, mock_put):
        """Extract the json= kwarg from the first httpx.put call."""
        return mock_put.call_args[1]["json"]

    def _get_http_catch_all_route(self, body):
        """Return routes[1] — the HTTP catch-all route."""
        return body["routes"][1]

    def _get_crew_proxy_handler(self, body):
        """Return the reverse proxy handler from routes[1]."""
        http_route = self._get_http_catch_all_route(body)
        handles = http_route["handle"]
        # With api_key set, proxy is second; without, it's first.
        for h in handles:
            if h.get("handler") == "reverse_proxy" and "rewrite" in h and "/ui" in h["rewrite"].get("uri", ""):
                return h
        return handles[-1]

    # 4.2
    def test_put_200_succeeds(self):
        portal = self._make_portal()
        mock_put = self._call_register(portal, status=200)
        mock_put.assert_called_once()

    # 4.3
    def test_put_201_succeeds(self):
        portal = self._make_portal()
        mock_put = self._call_register(portal, status=201)
        mock_put.assert_called_once()

    # 4.4
    def test_put_409_idempotent(self):
        portal = self._make_portal()
        mock_put = self._call_register(portal, status=409)
        mock_put.assert_called_once()

    # 4.5
    def test_listen_port_in_body(self):
        portal = self._make_portal()
        mock_put = self._call_register(portal, crew_id="abc", port=8765)
        body = self._get_put_body(mock_put)
        self.assertEqual(body["listen"], [":8765"])

    # 4.6
    def test_server_id_in_body(self):
        portal = self._make_portal()
        mock_put = self._call_register(portal, crew_id="abc", port=8765)
        body = self._get_put_body(mock_put)
        self.assertEqual(body["@id"], "crew-abc")

    # 4.7
    def test_rewrite_uri_uses_crew_prefix(self):
        portal = self._make_portal()
        mock_put = self._call_register(portal, crew_id="abc", port=8765)
        body = self._get_put_body(mock_put)
        proxy_handler = self._get_crew_proxy_handler(body)
        self.assertTrue(
            proxy_handler["rewrite"]["uri"].startswith("/crews/abc/ui"),
            f"Expected rewrite.uri to start with /crews/abc/ui, got: {proxy_handler['rewrite']['uri']!r}",
        )

    # 4.8
    def test_transport_token_header_injected(self):
        portal = self._make_portal()
        mock_put = self._call_register(portal, crew_id="abc", port=8765)
        body = self._get_put_body(mock_put)
        proxy_handler = self._get_crew_proxy_handler(body)
        token_header = proxy_handler["headers"]["request"]["set"]["X-Transport-Token"]
        self.assertEqual(token_header, ["{file./run/secrets/ga-transport-secret}"])

    # 4.9
    def test_ws_route_before_http_route(self):
        portal = self._make_portal()
        mock_put = self._call_register(portal, crew_id="abc", port=8765)
        body = self._get_put_body(mock_put)
        routes = body["routes"]
        # routes[0] must match on Connection: Upgrade (WebSocket route)
        ws_route = routes[0]
        match_headers = [m.get("header", {}) for m in ws_route.get("match", [])]
        connection_upgrade = any("Connection" in h for h in match_headers)
        self.assertTrue(connection_upgrade, "routes[0] should match on Connection: Upgrade")
        # routes[1] must NOT have such a match
        http_route = routes[1]
        if "match" in http_route:
            http_match_headers = [m.get("header", {}) for m in http_route.get("match", [])]
            has_upgrade = any("Connection" in h for h in http_match_headers)
            self.assertFalse(has_upgrade, "routes[1] should not match on Connection: Upgrade")

    # 4.10
    def test_forward_auth_present_when_api_key_set(self):
        portal = self._make_portal(api_key="secret")
        mock_resp = MagicMock(status_code=200, text="")
        with patch("transport.caddy.httpx.put", return_value=mock_resp, create=True) as mock_put:
            portal.register_crew("abc", 8765)
        body = mock_put.call_args[1]["json"]
        http_route = self._get_http_catch_all_route(body)
        handles = http_route["handle"]
        self.assertGreaterEqual(len(handles), 2)
        first_handler = handles[0]
        self.assertIn("/dashboard/auth", first_handler["rewrite"]["uri"])

    # 4.11
    def test_forward_auth_absent_when_api_key_empty(self):
        portal = self._make_portal(api_key="")
        mock_resp = MagicMock(status_code=200, text="")
        with patch("transport.caddy.httpx.put", return_value=mock_resp, create=True) as mock_put:
            portal.register_crew("abc", 8765)
        body = mock_put.call_args[1]["json"]
        http_route = self._get_http_catch_all_route(body)
        handles = http_route["handle"]
        self.assertEqual(len(handles), 1, "Expected exactly one handler when api_key is empty")

    # 4.12
    def test_put_url_includes_crew_id(self):
        portal = self._make_portal()
        mock_put = self._call_register(portal, crew_id="abc", port=8765)
        url = mock_put.call_args[0][0]
        self.assertEqual(url, "http://ga-portal:2019/config/apps/http/servers/crew-abc")


# ── 5. TestCaddyPortalRegisterCrew — retry and error paths ───────────────────


class TestCaddyPortalRegisterCrewRetry(unittest.TestCase):
    """CaddyPortal.register_crew: retry behaviour on transient failures."""

    def _make_portal(self):
        return CaddyPortal(port=5476, api_key="", port_range_start=9000, port_range_size=10)

    # 5.1
    def test_retry_on_500_then_success(self):
        portal = self._make_portal()
        side_effects = [
            MagicMock(status_code=500, text="err"),
            MagicMock(status_code=200, text="ok"),
        ]
        with patch("transport.caddy.httpx.put", side_effect=side_effects, create=True) as mock_put, \
             patch("transport.caddy.time.sleep"):
            portal.register_crew("abc", 8765)
        self.assertEqual(mock_put.call_count, 2)

    # 5.2
    def test_no_exception_after_all_retries_exhausted(self):
        portal = self._make_portal()
        side_effects = [
            MagicMock(status_code=500, text="err"),
            MagicMock(status_code=500, text="err"),
            MagicMock(status_code=500, text="err"),
        ]
        with patch("transport.caddy.httpx.put", side_effect=side_effects, create=True), \
             patch("transport.caddy.time.sleep"):
            # Must not raise
            portal.register_crew("abc", 8765)

    # 5.3
    def test_retry_on_connection_error_then_success(self):
        portal = self._make_portal()
        side_effects = [
            Exception("timeout"),
            MagicMock(status_code=200, text="ok"),
        ]
        with patch("transport.caddy.httpx.put", side_effect=side_effects, create=True) as mock_put, \
             patch("transport.caddy.time.sleep"):
            portal.register_crew("abc", 8765)
        self.assertEqual(mock_put.call_count, 2)

    # 5.4
    def test_no_exception_all_retries_connection_error(self):
        portal = self._make_portal()
        side_effects = [Exception("conn refused")] * 3
        with patch("transport.caddy.httpx.put", side_effect=side_effects, create=True), \
             patch("transport.caddy.time.sleep"):
            # Must not raise
            portal.register_crew("abc", 8765)


# ── 6. TestCaddyPortalDeregisterCrew ─────────────────────────────────────────


class TestCaddyPortalDeregisterCrew(unittest.TestCase):
    """CaddyPortal.deregister_crew: HTTP status code handling and error paths."""

    def setUp(self):
        self._portal = CaddyPortal(port=5476, api_key="", port_range_start=9000, port_range_size=10)

    def _call_deregister(self, crew_id="abc", status=200):
        mock_resp = MagicMock(status_code=status, text="")
        with patch("transport.caddy.httpx.delete", return_value=mock_resp, create=True) as mock_del:
            self._portal.deregister_crew(crew_id)
        return mock_del

    # 6.2
    def test_delete_url_includes_crew_id(self):
        mock_del = self._call_deregister(crew_id="abc", status=200)
        url = mock_del.call_args[0][0]
        self.assertEqual(url, "http://ga-portal:2019/id/crew-abc")

    # 6.3
    def test_delete_200_succeeds(self):
        self._call_deregister(status=200)  # must not raise

    # 6.4
    def test_delete_204_succeeds(self):
        self._call_deregister(status=204)  # must not raise

    # 6.5
    def test_delete_404_graceful(self):
        self._call_deregister(status=404)  # must not raise

    # 6.6
    def test_delete_500_no_exception(self):
        self._call_deregister(status=500)  # must not raise

    # 6.7
    def test_delete_connection_error_no_exception(self):
        with patch("transport.caddy.httpx.delete", side_effect=Exception("conn refused"), create=True):
            self._portal.deregister_crew("abc")  # must not raise


# ── 7. TestCaddyModuleLevelHelpers ────────────────────────────────────────────


class TestCaddyModuleLevelHelpers(unittest.TestCase):
    """_caddy_admin_url, CaddyPortal constructor, and module-level wrappers."""

    def setUp(self):
        transport.caddy._dashboard_ports_in_use.clear()

    def tearDown(self):
        transport.caddy._dashboard_ports_in_use.clear()

    # 7.2
    def test_caddy_admin_url_constant(self):
        self.assertEqual(_caddy_admin_url(), "http://ga-portal:2019")

    # 7.3
    def test_portal_constructor_stores_fields(self):
        portal = CaddyPortal(port=1234, api_key="k", port_range_start=5000, port_range_size=20)
        self.assertEqual(portal._port, 1234)
        self.assertEqual(portal._api_key, "k")
        self.assertEqual(portal._range_start, 5000)
        self.assertEqual(portal._range_size, 20)

    # 7.4
    def test_caddy_register_crew_module_wrapper_issues_put(self):
        mock_resp = MagicMock(status_code=200, text="")
        with patch("transport.caddy.httpx.put", return_value=mock_resp, create=True) as mock_put, \
             patch.object(transport.caddy, "GA_API_KEY", ""):
            _caddy_register_crew("test", 9000)
        mock_put.assert_called_once()
        url = mock_put.call_args[0][0]
        self.assertIn("crew-test", url)

    # 7.5
    def test_caddy_deregister_crew_module_wrapper_issues_delete(self):
        mock_resp = MagicMock(status_code=200, text="")
        with patch("transport.caddy.httpx.delete", return_value=mock_resp, create=True) as mock_del:
            _caddy_deregister_crew("test")
        mock_del.assert_called_once()
        url = mock_del.call_args[0][0]
        self.assertIn("crew-test", url)


if __name__ == "__main__":
    unittest.main()
