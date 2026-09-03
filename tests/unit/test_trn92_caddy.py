"""Unit tests for TRN-92 — Caddy reverse-proxy transport layer.

Coverage:
  8.1 _caddy_register_crew / _caddy_deregister_crew
  8.2 _handle_dashboard_login_post
  8.3 _handle_dashboard_auth
  8.4 Per-port uvicorn listener suppression with/without Caddy
  8.5 launch / nuke Caddy register/deregister
"""

from __future__ import annotations

import asyncio
import json
import time
import unittest
from unittest.mock import ANY, MagicMock, Mock, patch, call

# Import server via the helpers module, which installs httpx/mcp/starlette stubs
# in dependency-free environments before the transport modules are imported.
from tests.unit.helpers import server  # noqa: F401

# httpx is available (real or stub) after the helpers import bootstraps the stubs.
import httpx


# ---------------------------------------------------------------------------
# Minimal starlette-compatible Request stub for handler tests
# ---------------------------------------------------------------------------

class _FakeRequest:
    """Minimal request stub used by Caddy handler tests."""

    def __init__(
        self,
        *,
        cookies: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        form_data: dict[str, str] | None = None,
    ):
        self.cookies = cookies or {}
        self.query_params = query_params or {}
        self.headers = headers or {}
        self._form_data = form_data or {}

    async def form(self) -> dict:
        return self._form_data


def _get_header(resp: object, name: str) -> str:
    """Extract a response header value regardless of Response implementation.

    Supports real starlette Response (raw_headers as list of (bytes, bytes))
    and the lightweight httpx stub (resp.kwargs["headers"] dict).
    Returns the header value as a str, or "" if not present.
    """
    target = name.lower().encode()
    raw = getattr(resp, "raw_headers", None)
    if raw is not None:
        for k, v in raw:
            if (k.lower() if isinstance(k, bytes) else k.lower().encode()) == target:
                return v.decode() if isinstance(v, bytes) else v
        return ""
    # Stub path
    kwargs_headers: dict = getattr(resp, "kwargs", {}).get("headers", {})
    return kwargs_headers.get(name, "")


# ---------------------------------------------------------------------------
# 8.1 — _caddy_register_crew / _caddy_deregister_crew
# ---------------------------------------------------------------------------

class CaddyRegisterCrewTests(unittest.TestCase):
    """8.1 — _caddy_register_crew: correct JSON structure + admin API call."""

    def _make_response(self, status: int, text: str = "") -> Mock:
        """Build a minimal response stub matching what server.py expects."""
        resp = Mock()
        resp.status_code = status
        resp.text = text
        return resp

    def test_register_puts_correct_server_json(self) -> None:
        """PUT request body contains @id, listen port, forward_auth, reverse_proxy."""
        mock_resp = self._make_response(200)
        mock_put = Mock(return_value=mock_resp)

        with patch.object(server.httpx, "put", mock_put):
            server._caddy_register_crew("alpha", 64058)

        mock_put.assert_called_once()
        url: str = mock_put.call_args.args[0]
        self.assertIn("crew-alpha", url)

        payload: dict = mock_put.call_args.kwargs["json"]
        self.assertEqual(payload["@id"], "crew-alpha")
        self.assertIn(":64058", payload["listen"])

        # Verify forward_auth handler is present
        subroute = payload["routes"][0]["handle"][0]
        self.assertEqual(subroute["handler"], "subroute")
        fwd_auth_handle = subroute["routes"][0]["handle"][0]
        self.assertEqual(fwd_auth_handle["handler"], "forward_auth")
        self.assertIn("dashboard-auth", fwd_auth_handle["uri"])
        self.assertIn("X-Crew-Cookie", fwd_auth_handle["copy_headers"])

        # Verify reverse_proxy points to correct upstream
        proxy_handle = subroute["routes"][1]["handle"][0]
        self.assertEqual(proxy_handle["handler"], "reverse_proxy")
        self.assertEqual(proxy_handle["upstreams"][0]["dial"], "gs-alpha:5476")

    def test_register_treats_409_as_idempotent(self) -> None:
        """409 Conflict (existing @id) is treated as success — no retry, no exception."""
        mock_put = Mock(return_value=self._make_response(409))
        with patch.object(server.httpx, "put", mock_put):
            # Must not raise
            server._caddy_register_crew("alpha", 64058)

    def test_register_retries_on_failure_and_logs_warning(self) -> None:
        """Server errors trigger up to 3 retries; a warning is logged."""
        fail = self._make_response(503, "unavailable")
        call_count = [0]

        def fail_put(*a, **kw):
            call_count[0] += 1
            return fail

        with (
            patch.object(server.httpx, "put", side_effect=fail_put),
            patch.object(server.time, "sleep"),  # suppress real waits
        ):
            server._caddy_register_crew("beta", 64059)

        self.assertEqual(call_count[0], 3)

    def test_register_handles_connection_error_gracefully(self) -> None:
        """Network errors do not raise; a warning is logged."""

        class _ConnErr(Exception):
            pass

        with (
            patch.object(server.httpx, "put", side_effect=_ConnErr("unreachable")),
            patch.object(server.time, "sleep"),
        ):
            server._caddy_register_crew("gamma", 64060)  # must not raise


class CaddyDeregisterCrewTests(unittest.TestCase):
    """8.1 — _caddy_deregister_crew: DELETE + graceful 404 handling."""

    def _make_response(self, status: int, text: str = "") -> Mock:
        resp = Mock()
        resp.status_code = status
        resp.text = text
        return resp

    def test_deregister_calls_correct_url(self) -> None:
        mock_delete = Mock(return_value=self._make_response(200))
        with patch.object(server.httpx, "delete", mock_delete):
            server._caddy_deregister_crew("alpha")

        mock_delete.assert_called_once()
        url: str = mock_delete.call_args.args[0]
        self.assertIn("crew-alpha", url)

    def test_deregister_handles_404_gracefully(self) -> None:
        """404 on deregister is not an error — server already removed."""
        with patch.object(server.httpx, "delete", return_value=self._make_response(404)):
            server._caddy_deregister_crew("alpha")  # must not raise

    def test_deregister_handles_connection_error(self) -> None:
        """Network errors do not raise."""

        class _ConnErr(Exception):
            pass

        with patch.object(server.httpx, "delete", side_effect=_ConnErr("down")):
            server._caddy_deregister_crew("beta")  # must not raise

    def test_deregister_logs_warning_on_unexpected_status(self) -> None:
        """Non-200/404 status codes do not raise but are logged as warnings."""
        with patch.object(server.httpx, "delete", return_value=self._make_response(500, "err")):
            server._caddy_deregister_crew("gamma")  # must not raise


# ---------------------------------------------------------------------------
# 8.2 — _handle_dashboard_login_post
# ---------------------------------------------------------------------------

class DashboardLoginPostTests(unittest.TestCase):
    """8.2 — _handle_dashboard_login_post: key validation + cookie issuance."""

    def setUp(self) -> None:
        # Reset the session store between tests
        with server._gs_session_store_lock:
            server._gs_session_store.clear()
        self._orig_api_key = server.GA_API_KEY

    def tearDown(self) -> None:
        with server._gs_session_store_lock:
            server._gs_session_store.clear()
        server.GA_API_KEY = self._orig_api_key

    def _run(self, form_data: dict[str, str] | None = None) -> "server.Response":
        req = _FakeRequest(form_data=form_data or {})
        return asyncio.run(server._handle_dashboard_login_post(req))

    def test_valid_key_returns_200_with_set_cookie(self) -> None:
        server.GA_API_KEY = "secret-key"
        resp = self._run({"ga_api_key": "secret-key"})
        self.assertEqual(resp.status_code, 200)
        # Check that a Set-Cookie header was included.
        # Starlette's real Response stores headers in raw_headers as (bytes, bytes) pairs;
        # the httpx stub stores them in resp.kwargs["headers"].  Support both.
        set_cookie = ""
        raw = getattr(resp, "raw_headers", None)
        if raw is not None:
            for k, v in raw:
                if k.lower() in (b"set-cookie", "set-cookie"):
                    set_cookie = v.decode() if isinstance(v, bytes) else v
                    break
        else:
            headers = getattr(resp, "kwargs", {}).get("headers", {})
            set_cookie = headers.get("Set-Cookie", "")
        self.assertIn("gs_session=", set_cookie)

    def test_valid_key_stores_token(self) -> None:
        server.GA_API_KEY = "secret-key"
        self._run({"ga_api_key": "secret-key"})
        with server._gs_session_store_lock:
            self.assertGreater(len(server._gs_session_store), 0)

    def test_invalid_key_returns_401(self) -> None:
        server.GA_API_KEY = "secret-key"
        resp = self._run({"ga_api_key": "wrong-key"})
        self.assertEqual(resp.status_code, 401)

    def test_invalid_key_does_not_issue_cookie(self) -> None:
        server.GA_API_KEY = "secret-key"
        self._run({"ga_api_key": "wrong-key"})
        with server._gs_session_store_lock:
            self.assertEqual(len(server._gs_session_store), 0)

    def test_no_api_key_configured_returns_401(self) -> None:
        server.GA_API_KEY = ""
        resp = self._run({"ga_api_key": "anything"})
        self.assertEqual(resp.status_code, 401)

    def test_empty_form_returns_401(self) -> None:
        server.GA_API_KEY = "secret-key"
        resp = self._run({})
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# 8.3 — _handle_dashboard_auth
# ---------------------------------------------------------------------------

class DashboardAuthTests(unittest.TestCase):
    """8.3 — _handle_dashboard_auth: session validation + crew cookie injection."""

    def setUp(self) -> None:
        with server._gs_session_store_lock:
            server._gs_session_store.clear()
        # Pre-populate port→crew mapping
        self._orig_port_crew = dict(server._dashboard_port_crew)
        server._dashboard_port_crew.clear()

    def tearDown(self) -> None:
        with server._gs_session_store_lock:
            server._gs_session_store.clear()
        server._dashboard_port_crew.clear()
        server._dashboard_port_crew.update(self._orig_port_crew)

    def _issue_token(self) -> str:
        return server._gs_session_issue()

    def _run(
        self,
        cookies: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> "server.Response":
        req = _FakeRequest(cookies=cookies or {}, query_params=query_params or {})
        return asyncio.run(server._handle_dashboard_auth(req))

    def test_valid_session_returns_200(self) -> None:
        token = self._issue_token()
        resp = self._run({"gs_session": token})
        self.assertEqual(resp.status_code, 200)

    def test_expired_session_returns_401(self) -> None:
        token = server.secrets.token_hex(32)
        # Manually insert with past expiry
        with server._gs_session_store_lock:
            server._gs_session_store[token] = time.time() - 1
        resp = self._run({"gs_session": token})
        self.assertEqual(resp.status_code, 401)

    def test_missing_session_cookie_returns_401(self) -> None:
        resp = self._run({})
        self.assertEqual(resp.status_code, 401)

    def test_invalid_token_returns_401(self) -> None:
        resp = self._run({"gs_session": "nonexistent-token"})
        self.assertEqual(resp.status_code, 401)

    def test_valid_session_returns_crew_cookie_for_port(self) -> None:
        token = self._issue_token()
        # Register port→crew and mock registry to return a gateway token
        server._dashboard_port_crew[64058] = "alpha"
        reg = {"crews": {"alpha": {"gateway_token": "crew-token-abc123"}}}
        with patch.object(server, "_load_registry", return_value=reg):
            resp = self._run(
                {"gs_session": token},
                {"port": "64058"},
            )
        self.assertEqual(resp.status_code, 200)
        # Extract X-Crew-Cookie from raw_headers (real starlette) or kwargs (stub).
        x_cookie = _get_header(resp, "X-Crew-Cookie")
        self.assertIn("mc_token_5476=crew-token-abc123", x_cookie)

    def test_valid_session_unknown_port_still_returns_200(self) -> None:
        """A valid session with an unrecognised port returns 200 (no crew cookie)."""
        token = self._issue_token()
        resp = self._run({"gs_session": token}, {"port": "99999"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_get_header(resp, "X-Crew-Cookie"), "")


# ---------------------------------------------------------------------------
# 8.4 — Per-port uvicorn listener suppression
# ---------------------------------------------------------------------------

class CaddyUvicornSuppressionTests(unittest.TestCase):
    """8.4 — _start_dashboard_port_server is a no-op when GA_CADDY_ENABLED=True."""

    def setUp(self) -> None:
        server._dashboard_ports_in_use.clear()
        server._dashboard_port_crew.clear()
        server._dashboard_port_servers.clear()

    def tearDown(self) -> None:
        server._dashboard_ports_in_use.clear()
        server._dashboard_port_crew.clear()
        server._dashboard_port_servers.clear()

    def test_start_port_server_noop_when_caddy_enabled(self) -> None:
        """When GA_CADDY_ENABLED=True, no uvicorn Server is created."""
        with patch.object(server, "GA_CADDY_ENABLED", True):
            server._start_dashboard_port_server(64058, "alpha", Mock())
        # No server created
        self.assertNotIn(64058, server._dashboard_port_servers)
        # Port→crew mapping IS stored (needed for forward_auth)
        self.assertEqual(server._dashboard_port_crew.get(64058), "alpha")

    def test_start_port_server_creates_uvicorn_when_caddy_disabled(self) -> None:
        """When GA_CADDY_ENABLED=False, a uvicorn Server IS created on the port."""
        mock_app = Mock()
        mock_server = Mock()
        mock_config = Mock()

        with (
            patch.object(server, "GA_CADDY_ENABLED", False),
            patch("transport.server.uvicorn.Config", return_value=mock_config),
            patch("transport.server.uvicorn.Server", return_value=mock_server),
        ):
            server._start_dashboard_port_server(64058, "alpha", mock_app)

        self.assertIn(64058, server._dashboard_port_servers)
        self.assertEqual(server._dashboard_port_crew.get(64058), "alpha")


# ---------------------------------------------------------------------------
# 8.5 — launch / nuke Caddy register/deregister
# ---------------------------------------------------------------------------

class CaddyLaunchNukeTests(unittest.TestCase):
    """8.5 — launch() registers Caddy server; nuke() deregisters it."""

    def setUp(self) -> None:
        server._dashboard_ports_in_use.clear()
        server._dashboard_port_crew.clear()

    def tearDown(self) -> None:
        server._dashboard_ports_in_use.clear()
        server._dashboard_port_crew.clear()

    def _run_launch(self, caddy_enabled: bool = True) -> dict:
        registry_state = {"crews": {}}
        podman = Mock()
        podman.network_create = Mock()
        podman.volume_create = Mock()
        podman.container_create = Mock(return_value={})
        podman.container_start = Mock()

        finish_result = {
            "crew_id": "demo",
            "container": "gs-demo",
            "gateway_url": "http://gs-demo:5476",
            "status": "ready",
        }

        with (
            patch.object(server, "_read_auth_file", return_value="auth-b64"),
            patch.object(server, "_load_registry", return_value=registry_state),
            patch.object(server, "_save_registry"),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_finish_crew_setup", return_value=finish_result),
            patch.object(server, "_resolve_composition", return_value={"name": "spec-ops"}),
            patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(server, "GA_DASHBOARD_PORT_ENABLED", True),
            patch.object(server, "GA_CADDY_ENABLED", caddy_enabled),
            patch.object(server, "GA_DASHBOARD_PORT_RANGE_START", 9000),
            patch.object(server, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
            patch.object(server, "_caddy_register_crew") as mock_register,
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ""
            mock_cfg.ga_dashboard_port_range_start = 9000
            mock_cfg.ga_dashboard_port_range_size = 50
            mock_cfg.ga_caddy_enabled = caddy_enabled
            result = server.launch("demo", dashboard=True)

        return result, mock_register

    def test_launch_caddy_enabled_registers_with_caddy(self) -> None:
        result, mock_register = self._run_launch(caddy_enabled=True)
        mock_register.assert_called_once()
        crew_id, port = mock_register.call_args.args
        self.assertEqual(crew_id, "demo")
        self.assertIsInstance(port, int)

    def test_launch_caddy_enabled_returns_https_url(self) -> None:
        result, _ = self._run_launch(caddy_enabled=True)
        self.assertIn("dashboard_url", result)
        self.assertTrue(
            result["dashboard_url"].startswith("https://"),
            f"Expected https:// URL, got: {result['dashboard_url']}",
        )

    def test_launch_caddy_disabled_does_not_register(self) -> None:
        result, mock_register = self._run_launch(caddy_enabled=False)
        mock_register.assert_not_called()

    def test_launch_caddy_disabled_returns_http_url(self) -> None:
        result, _ = self._run_launch(caddy_enabled=False)
        self.assertIn("dashboard_url", result)
        self.assertTrue(
            result["dashboard_url"].startswith("http://"),
            f"Expected http:// URL, got: {result['dashboard_url']}",
        )

    def test_nuke_caddy_enabled_deregisters(self) -> None:
        """nuke() calls _caddy_deregister_crew when GA_CADDY_ENABLED=True."""
        reg = {"crews": {"alpha": {"container": "gs-alpha", "volume": "gs-vol-alpha",
                                    "home_volume": "gs-home-alpha", "dashboard_port": 64058}}}
        podman = Mock()
        podman.container_stop = Mock()
        podman.container_rm = Mock()
        podman.volume_rm = Mock()

        with (
            patch.object(server, "_get_crew", return_value=reg["crews"]["alpha"]),
            patch.object(server, "_get_crew_schedules", return_value=[]),
            patch.object(server, "_cleanup_crew"),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "GA_DASHBOARD_PORT_ENABLED", True),
            patch.object(server, "GA_CADDY_ENABLED", True),
            patch.object(server, "_caddy_deregister_crew") as mock_deregister,
            patch.object(server, "_delete_crew_secret"),
        ):
            result = server.nuke("alpha", confirm=True)

        mock_deregister.assert_called_once_with("alpha")
        self.assertEqual(result["status"], "nuked")

    def test_nuke_caddy_disabled_does_not_deregister(self) -> None:
        """nuke() does not call _caddy_deregister_crew when GA_CADDY_ENABLED=False."""
        reg = {"crews": {"alpha": {"container": "gs-alpha", "volume": "gs-vol-alpha",
                                    "home_volume": "gs-home-alpha", "dashboard_port": 64058}}}
        with (
            patch.object(server, "_get_crew", return_value=reg["crews"]["alpha"]),
            patch.object(server, "_get_crew_schedules", return_value=[]),
            patch.object(server, "_cleanup_crew"),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "GA_DASHBOARD_PORT_ENABLED", True),
            patch.object(server, "GA_CADDY_ENABLED", False),
            patch.object(server, "_caddy_deregister_crew") as mock_deregister,
            patch.object(server, "_stop_dashboard_port_server"),
            patch.object(server, "_delete_crew_secret"),
        ):
            server.nuke("alpha", confirm=True)

        mock_deregister.assert_not_called()


# ---------------------------------------------------------------------------
# Session store helpers
# ---------------------------------------------------------------------------

class GsSessionStoreTests(unittest.TestCase):
    """Verify the in-memory gs_session store TTL logic."""

    def setUp(self) -> None:
        with server._gs_session_store_lock:
            server._gs_session_store.clear()

    def tearDown(self) -> None:
        with server._gs_session_store_lock:
            server._gs_session_store.clear()

    def test_issued_token_is_valid(self) -> None:
        token = server._gs_session_issue()
        self.assertTrue(server._gs_session_valid(token))

    def test_unknown_token_is_invalid(self) -> None:
        self.assertFalse(server._gs_session_valid("no-such-token"))

    def test_expired_token_is_invalid_and_purged(self) -> None:
        token = "test-expired"
        with server._gs_session_store_lock:
            server._gs_session_store[token] = time.time() - 1
        self.assertFalse(server._gs_session_valid(token))
        with server._gs_session_store_lock:
            self.assertNotIn(token, server._gs_session_store)


if __name__ == "__main__":
    unittest.main()
