"""Caddy admin API and dashboard-port tests split from test_server.py
(trn-119). Absorbs the former test_trn92_caddy.py.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import importlib as _importlib
import inspect
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from unittest.mock import ANY, Mock, MagicMock, patch

import httpx
import transport.registry as _registry_mod  # noqa: F401

from tests.unit.helpers import Request, server, lifecycle, monitors, academy  # noqa: F401


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
        """PUT body contains @id, listen port, crew reverse_proxy with Cookie injection. No forward_auth when GA_API_KEY unset."""
        mock_resp = self._make_response(200)
        mock_put = Mock(return_value=mock_resp)

        with patch.object(server.httpx, "put", mock_put):
            server._caddy_register_crew("alpha", 64058, crew_cookie="test-token-abc123")

        mock_put.assert_called_once()
        url: str = mock_put.call_args.args[0]
        self.assertIn("crew-alpha", url)

        payload: dict = mock_put.call_args.kwargs["json"]
        self.assertEqual(payload["@id"], "crew-alpha")
        self.assertIn(":64058", payload["listen"])

        # No GA_API_KEY in tests → only the crew reverse_proxy handler (no forward_auth).
        handles = payload["routes"][0]["handle"]
        self.assertEqual(len(handles), 1)
        crew_proxy = handles[0]
        self.assertEqual(crew_proxy["handler"], "reverse_proxy")
        # TRN-102: upstream is the transport, not the crew gateway; the path is
        # rewritten to /crews/{id}/ui/... and NO Cookie is injected in Caddy.
        self.assertEqual(crew_proxy["upstreams"][0]["dial"], f"ga-transport:{server.PORT}")
        self.assertIn("/crews/alpha/ui", crew_proxy["rewrite"]["uri"])
        # TRN-107: every route to ga-transport carries the portal secret header,
        # regardless of whether GA_API_KEY is set.
        self.assertEqual(
            crew_proxy["headers"]["request"]["set"]["X-Transport-Token"],
            ["{file./run/secrets/ga-transport-secret}"],
        )

    def test_register_with_api_key_includes_forward_auth(self) -> None:
        """When GA_API_KEY is set, forward_auth handler precedes the crew proxy."""
        mock_resp = self._make_response(200)
        mock_put = Mock(return_value=mock_resp)

        # TRN-116: _caddy_register_crew moved to transport/caddy.py and reads
        # GA_API_KEY from that module's globals, so patch it there.
        with patch.object(server._caddy, "GA_API_KEY", "some-key"), \
             patch.object(server.httpx, "put", mock_put):
            server._caddy_register_crew("alpha", 64058, crew_cookie="test-token")

        payload: dict = mock_put.call_args.kwargs["json"]
        handles = payload["routes"][0]["handle"]
        self.assertEqual(len(handles), 2)
        fwd_auth = handles[0]
        self.assertEqual(fwd_auth["handler"], "reverse_proxy")
        self.assertIn("dashboard/auth", fwd_auth["rewrite"]["uri"])
        self.assertIn("handle_response", fwd_auth)
        # TRN-107: forward_auth also carries the portal secret header.
        self.assertEqual(
            fwd_auth["headers"]["request"]["set"]["X-Transport-Token"],
            ["{file./run/secrets/ga-transport-secret}"],
        )
        crew_proxy = handles[1]
        self.assertEqual(crew_proxy["handler"], "reverse_proxy")
        # TRN-102: crew proxy upstreams the transport, not the crew gateway.
        self.assertEqual(crew_proxy["upstreams"][0]["dial"], f"ga-transport:{server.PORT}")

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
    """8.2 — _handle_dashboard_login_post: key validation + cookie issuance.

    Migrated from _gs_session_store/_gs_session_store_lock (TRN-92 API,
    removed in TRN-121) to security.SessionStore + security.Throttle.
    Each test injects fresh instances via patch.object so state never leaks.
    """

    _KNOWN_CSRF = "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"

    def setUp(self) -> None:
        # Fresh security instances per test — isolates without relying on
        # removed module-level symbols.
        self._sessions = server._security.SessionStore(lifetime_secs=3600)
        self._throttle = server._security.Throttle(max_failures=5, window_secs=900)
        self._orig_api_key = server._dashboard_gate._api_key
        # Pin CSRF token so tests can include correct value in form data.
        self._orig_csrf = server._dashboard_gate._csrf_token
        server._dashboard_gate._csrf_token = self._KNOWN_CSRF

    def tearDown(self) -> None:
        server._dashboard_gate._api_key = self._orig_api_key
        server._dashboard_gate._csrf_token = self._orig_csrf

    def _run(self, form_data: dict[str, str] | None = None) -> "server.Response":
        data = {"csrf_token": self._KNOWN_CSRF, **(form_data or {})}
        with (
            patch.object(server._dashboard_gate, "_sessions", self._sessions),
            patch.object(server._dashboard_gate, "_throttle", self._throttle),
            patch.object(server._dashboard_gate, "_tls_mode", "auto"),
        ):
            req = _FakeRequest(form_data=data)
            return asyncio.run(server._dashboard_gate.handle_login_post(req))

    def test_valid_key_returns_200_with_set_cookie(self) -> None:
        server._dashboard_gate._api_key = "secret-key"
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
        """A successful login issues a token into the SessionStore."""
        server._dashboard_gate._api_key = "secret-key"
        self._run({"ga_api_key": "secret-key"})
        # The SessionStore's internal _issued dict should have one entry.
        self.assertGreater(len(self._sessions._issued), 0)

    def test_invalid_key_returns_401(self) -> None:
        server._dashboard_gate._api_key = "secret-key"
        resp = self._run({"ga_api_key": "wrong-key"})
        self.assertEqual(resp.status_code, 401)

    def test_invalid_key_does_not_issue_cookie(self) -> None:
        """A failed login must not populate the SessionStore."""
        server._dashboard_gate._api_key = "secret-key"
        self._run({"ga_api_key": "wrong-key"})
        self.assertEqual(len(self._sessions._issued), 0)

    def test_no_api_key_configured_returns_401(self) -> None:
        server._dashboard_gate._api_key = ""
        resp = self._run({"ga_api_key": "anything"})
        self.assertEqual(resp.status_code, 401)

    def test_empty_form_returns_401(self) -> None:
        server._dashboard_gate._api_key = "secret-key"
        resp = self._run({})
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# 8.3 — _handle_dashboard_auth
# ---------------------------------------------------------------------------

class DashboardAuthTests(unittest.TestCase):
    """8.3 — _handle_dashboard_auth: session validation + crew cookie injection.

    Migrated from _gs_session_store/_gs_session_store_lock/_gs_session_issue
    (TRN-92 API, removed in TRN-121) to security.SessionStore.
    """

    def setUp(self) -> None:
        # Fresh SessionStore per test — no leakage, no lock references.
        self._sessions = server._security.SessionStore(lifetime_secs=3600)
        # Pre-populate port→crew mapping
        self._orig_port_crew = dict(server._dashboard_gate._port_crew)
        server._dashboard_gate._port_crew.clear()
        # Set a non-empty API key so session validation is active by default.
        self._orig_api_key = server._dashboard_gate._api_key
        server._dashboard_gate._api_key = "test-key"

    def tearDown(self) -> None:
        server._dashboard_gate._port_crew.clear()
        server._dashboard_gate._port_crew.update(self._orig_port_crew)
        server._dashboard_gate._api_key = self._orig_api_key

    def _issue_token(self) -> str:
        return self._sessions.issue()

    def _run(
        self,
        cookies: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> "server.Response":
        with patch.object(server._dashboard_gate, "_sessions", self._sessions):
            req = _FakeRequest(cookies=cookies or {}, query_params=query_params or {})
            return asyncio.run(server._dashboard_gate.handle_auth(req))

    def test_valid_session_returns_200(self) -> None:
        token = self._issue_token()
        resp = self._run({"gs_session": token})
        self.assertEqual(resp.status_code, 200)

    def test_expired_session_returns_401(self) -> None:
        # Issue a token into a store with zero lifetime so it is already expired.
        expired_store = server._security.SessionStore(lifetime_secs=0)
        token = expired_store.issue(now=time.time() - 1)
        with patch.object(server._dashboard_gate, "_sessions", expired_store):
            req = _FakeRequest(cookies={"gs_session": token})
            resp = asyncio.run(server._dashboard_gate.handle_auth(req))
        self.assertEqual(resp.status_code, 401)

    def test_missing_session_cookie_returns_401(self) -> None:
        resp = self._run({})
        self.assertEqual(resp.status_code, 401)

    def test_invalid_token_returns_401(self) -> None:
        resp = self._run({"gs_session": "nonexistent-token"})
        self.assertEqual(resp.status_code, 401)

    def test_no_api_key_open_access_returns_200(self) -> None:
        """When GA_API_KEY is unset, all dashboard-auth requests return 200 (open access)."""
        server._dashboard_gate._api_key = ""
        resp = self._run({})
        self.assertEqual(resp.status_code, 200)

    def test_valid_session_with_known_port_returns_200(self) -> None:
        """Valid gs_session returns 200. Cookie injection is handled by Caddy config, not dashboard-auth."""
        token = self._issue_token()
        server._dashboard_gate._port_crew[64058] = "alpha"
        resp = self._run(
            {"gs_session": token},
            {"port": "64058"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_valid_session_unknown_port_still_returns_200(self) -> None:
        """A valid session with an unrecognised port returns 200."""
        token = self._issue_token()
        resp = self._run({"gs_session": token}, {"port": "99999"})
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# 8.4 — Per-port uvicorn listener suppression
# ---------------------------------------------------------------------------

class CaddyLaunchNukeTests(unittest.TestCase):
    """8.5 — launch() registers Caddy server; nuke() deregisters it. (TRN-101 updated)"""

    def setUp(self) -> None:
        server._dashboard_ports_in_use.clear()
        server._dashboard_gate._port_crew.clear()

    def tearDown(self) -> None:
        server._dashboard_ports_in_use.clear()
        server._dashboard_gate._port_crew.clear()

    def _run_launch(self) -> dict:
        registry_state = {"crews": {}}
        podman = Mock()
        podman.network_create = Mock()
        podman.volume_create = Mock()
        podman.container_create = Mock(return_value={})
        podman.container_start = Mock()
        podman.container_stop = Mock()
        podman.container_remove = Mock()
        podman.volume_remove = Mock()

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
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
            patch.object(server, "_caddy_register_crew") as mock_register,
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ""
            mock_cfg.ga_portal_tls_mode = "internal"
            mock_cfg.ga_dashboard_port_range_start = 9000
            mock_cfg.ga_dashboard_port_range_size = 50
            result = server.launch("demo", dashboard=True)

        return result, mock_register

    def test_launch_caddy_enabled_registers_with_caddy(self) -> None:
        result, mock_register = self._run_launch()
        mock_register.assert_called_once()
        crew_id, port = mock_register.call_args.args
        self.assertEqual(crew_id, "demo")
        self.assertIsInstance(port, int)

    def test_launch_caddy_enabled_returns_https_url(self) -> None:
        result, _ = self._run_launch()
        self.assertIn("dashboard_url", result)
        self.assertTrue(
            result["dashboard_url"].startswith("https://"),
            f"Expected https:// URL, got: {result['dashboard_url']}",
        )

    def test_nuke_deregisters_with_caddy(self) -> None:
        """nuke() calls _caddy_deregister_crew (always — Portal is the only proxy)."""
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
            patch.object(server, "_caddy_deregister_crew") as mock_deregister,
            patch.object(server, "_delete_crew_secret"),
        ):
            result = server.nuke("alpha", confirm=True)

        mock_deregister.assert_called_once_with("alpha")
        self.assertEqual(result["status"], "nuked")


# ---------------------------------------------------------------------------
# Session store helpers
# ---------------------------------------------------------------------------

class GsSessionStoreTests(unittest.TestCase):
    """Verify the gs_session store semantics via security.SessionStore.

    Migrated from direct _gs_session_store dict manipulation
    (TRN-92 API, removed in TRN-121) to the SessionStore public API.
    Equivalent coverage now also exists in TestDashboardSessionStore in
    test_server.py; this class remains to cover the same scenarios through
    the test_caddy fixture pattern.
    """

    def setUp(self) -> None:
        # Fresh store per test, patched onto the module symbol.
        self._store = server._security.SessionStore(lifetime_secs=3600)
        self._patcher = patch.object(server._dashboard_gate, "_sessions", self._store)
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()

    def test_issued_token_is_valid(self) -> None:
        token = self._store.issue()
        self.assertTrue(self._store.validate(token))

    def test_unknown_token_is_invalid(self) -> None:
        self.assertFalse(self._store.validate("no-such-token"))

    def test_expired_token_is_invalid_and_purged(self) -> None:
        # Issue into a zero-lifetime store so it expires immediately.
        expired_store = server._security.SessionStore(lifetime_secs=0)
        token = expired_store.issue(now=time.time() - 1)
        self.assertFalse(expired_store.validate(token))
        # After validate, the expired token should be evicted from _issued.
        self.assertNotIn(token, expired_store._issued)


if __name__ == "__main__":
    unittest.main()
class _FakeDownstream:
    """Minimal ASGI app that records whether it was called."""

    def __init__(self) -> None:
        self.called = False
        self.scope = None

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        self.scope = scope
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"OK"})
def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": headers or [],
    }
def _run_asgi(app, scope, body: bytes = b"") -> tuple[int, list, bytes]:
    """Run an ASGI app synchronously and return (status, headers, body)."""
    status = None
    resp_headers = []
    resp_body = b""

    async def receive():
        return {"type": "http.request", "body": body}

    async def send(msg):
        nonlocal status, resp_headers, resp_body
        if msg["type"] == "http.response.start":
            status = msg["status"]
            resp_headers = msg.get("headers", [])
        elif msg["type"] == "http.response.body":
            resp_body += msg.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return status, resp_headers, resp_body
class _FakeStreamRequest:
    """Minimal async-compatible request stub for proxy handler tests."""

    def __init__(
        self,
        method: str = "GET",
        path: str = "/crews/demo/ui",
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        query_string: bytes = b"",
    ) -> None:
        self.method = method
        self.scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query_string,
        }
        self.headers = headers or {}
        self._body = body

    async def body(self) -> bytes:
        return self._body
class _FakeUpstreamResponse:
    """httpx.Response-like stub returned by _async_http.stream() context manager."""

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = dict(headers or {})

    async def aread(self) -> bytes:
        return self.content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass
class UiPortAllocationTests(unittest.TestCase):
    """Tests for _allocate_dashboard_port / _release_dashboard_port (TRN-80 task 3)."""

    def setUp(self) -> None:
        # Isolate module-level port state for each test
        server._dashboard_ports_in_use.clear()

    def tearDown(self) -> None:
        server._dashboard_ports_in_use.clear()

    def test_allocate_returns_range_start_when_empty(self) -> None:
        with (
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
        ):
            port = server._allocate_dashboard_port()
        self.assertEqual(port, 9000)
        self.assertIn(9000, server._dashboard_ports_in_use)

    def test_allocate_returns_next_free_port(self) -> None:
        server._dashboard_ports_in_use.add(9000)
        server._dashboard_ports_in_use.add(9001)
        with (
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
        ):
            port = server._allocate_dashboard_port()
        self.assertEqual(port, 9002)
        self.assertIn(9002, server._dashboard_ports_in_use)

    def test_allocate_raises_when_exhausted(self) -> None:
        with (
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 3),
        ):
            server._dashboard_ports_in_use.update({9000, 9001, 9002})
            with self.assertRaises(RuntimeError) as ctx:
                server._allocate_dashboard_port()
        self.assertIn("exhausted", str(ctx.exception).lower())

    def test_release_frees_port(self) -> None:
        server._dashboard_ports_in_use.add(9005)
        server._release_dashboard_port(9005)
        self.assertNotIn(9005, server._dashboard_ports_in_use)

    def test_release_is_noop_for_unallocated_port(self) -> None:
        # Must not raise
        server._release_dashboard_port(9999)
class UiPortLaunchTests(unittest.TestCase):
    """Tests for launch() UI port wiring (TRN-80 task 4.1)."""

    def setUp(self) -> None:
        server._dashboard_ports_in_use.clear()

    def tearDown(self) -> None:
        server._dashboard_ports_in_use.clear()

    def _run_launch(self, ga_host_url: str = "") -> dict:
        """Run server.launch() with a minimal set of mocks and return the result."""
        registry = {"crews": {}}
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

        def save_registry(reg: dict) -> None:
            # Simulate what _finish_crew_setup writes
            if "demo" in reg["crews"] and reg["crews"]["demo"].get("status") != "launching":
                pass

        with (
            patch.object(server, "_read_auth_file", return_value="auth-b64"),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry", side_effect=lambda r: None),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_finish_crew_setup", return_value=finish_result),
            patch.object(server, "_resolve_composition", return_value={"name": "spec-ops", "description": ""}),
            patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(server, "_caddy_register_crew"),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ga_host_url
            mock_cfg.ga_portal_tls_mode = "internal"
            mock_cfg.ga_dashboard_port_range_start = 9000
            mock_cfg.ga_dashboard_port_range_size = 50
            result = server.launch("demo", dashboard=True)
        return result

    def test_launch_includes_dashboard_url_when_portal_enabled(self) -> None:
        """TRN-103: launch(dashboard=True) returns dashboard_url (Portal is always on)."""
        result = self._run_launch(ga_host_url="")
        self.assertIn("dashboard_url", result)
        self.assertIsNotNone(result["dashboard_url"])
        # Portal internal TLS → https://
        self.assertTrue(result["dashboard_url"].startswith("https://"))
        self.assertIn("9000", result["dashboard_url"])

    def test_launch_dashboard_url_uses_ga_host_url_host(self) -> None:
        result = self._run_launch(ga_host_url="http://vm23.example.com:64057")
        self.assertIn("dashboard_url", result)
        self.assertIn("vm23.example.com", result["dashboard_url"])
        self.assertIn("9000", result["dashboard_url"])

    def test_launch_dashboard_url_is_none_when_dashboard_false(self) -> None:
        """TRN-103: dashboard=False always gives dashboard_url=None."""
        registry = {"crews": {}}
        podman = Mock()
        podman.network_create = Mock()
        podman.volume_create = Mock()
        podman.container_create = Mock(return_value={})
        podman.container_start = Mock()
        finish_result = {"crew_id": "demo", "container": "gs-demo", "status": "ready"}
        with (
            patch.object(server, "_read_auth_file", return_value="auth-b64"),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_finish_crew_setup", return_value=finish_result),
            patch.object(server, "_resolve_composition", return_value={"name": "spec-ops", "description": ""}),
            patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ""
            mock_cfg.ga_portal_tls_mode = "internal"
            mock_cfg.ga_dashboard_port_range_start = 9000
            mock_cfg.ga_dashboard_port_range_size = 50
            result = server.launch("demo", dashboard=False)
        self.assertIn("dashboard_url", result)
        self.assertIsNone(result["dashboard_url"])

    def test_launch_passes_ports_to_container_create(self) -> None:
        registry = {"crews": {}}
        podman = Mock()
        podman.network_create = Mock()
        podman.volume_create = Mock()
        podman.container_create = Mock(return_value={})
        podman.container_start = Mock()
        finish_result = {"crew_id": "demo", "container": "gs-demo", "gateway_url": "http://gs-demo:5476", "status": "ready"}

        with (
            patch.object(server, "_read_auth_file", return_value="auth-b64"),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_finish_crew_setup", return_value=finish_result),
            patch.object(server, "_resolve_composition", return_value={"name": "spec-ops", "description": ""}),
            patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(server, "_caddy_register_crew"),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ""
            mock_cfg.ga_portal_tls_mode = "internal"
            mock_cfg.ga_dashboard_port_range_start = 9000
            mock_cfg.ga_dashboard_port_range_size = 50
            server.launch("demo", dashboard=True)

        call_kwargs = podman.container_create.call_args.kwargs
        self.assertNotIn("ports", call_kwargs, "crew containers must not bind host ports")

    def test_launch_no_ports_passed_when_dashboard_false(self) -> None:
        """TRN-101: dashboard=False → no port allocation, container_create has no ports kwarg."""
        registry = {"crews": {}}
        podman = Mock()
        podman.network_create = Mock()
        podman.volume_create = Mock()
        podman.container_create = Mock(return_value={})
        podman.container_start = Mock()
        finish_result = {"crew_id": "demo", "container": "gs-demo", "gateway_url": "http://gs-demo:5476", "status": "ready"}

        with (
            patch.object(server, "_read_auth_file", return_value="auth-b64"),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_finish_crew_setup", return_value=finish_result),
            patch.object(server, "_resolve_composition", return_value={"name": "spec-ops", "description": ""}),
            patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ""
            mock_cfg.ga_portal_tls_mode = "internal"
            mock_cfg.ga_dashboard_port_range_start = 9000
            mock_cfg.ga_dashboard_port_range_size = 50
            server.launch("demo")  # dashboard=False by default

        call_kwargs = podman.container_create.call_args.kwargs
        self.assertIsNone(call_kwargs.get("ports"))
class UiPortNukeTests(unittest.TestCase):
    """Tests for nuke() UI port release (TRN-80 task 4.2)."""

    def setUp(self) -> None:
        server._dashboard_ports_in_use.clear()

    def tearDown(self) -> None:
        server._dashboard_ports_in_use.clear()

    def test_nuke_releases_dashboard_port(self) -> None:
        server._dashboard_ports_in_use.add(9000)
        crew = {
            "container": "gs-demo",
            "volume": "gs-vol-demo",
            "home_volume": "gs-home-demo",
            "dashboard_port": 9000,
        }
        registry = {"crews": {"demo": dict(crew)}}
        podman = Mock()
        podman.container_stop = Mock()
        podman.container_remove = Mock()
        podman.volume_remove = Mock()

        with (
            patch.object(server, "_get_crew", return_value=crew),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_crew_api", return_value={"agents": []}),
            patch.object(server, "_get_crew_schedules", return_value=[]),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
            patch.object(server, "_cleanup_crew"),
            patch.object(server, "_captain_order_locks_lock", threading.Lock()),
            patch.object(server, "_captain_order_locks", {}),
        ):
            result = server.nuke("demo", confirm=True)

        self.assertEqual(result["status"], "nuked")
        self.assertNotIn(9000, server._dashboard_ports_in_use)
class CrewsListUiUrlTests(unittest.TestCase):
    """Tests for dashboard_url in crews() list (TRN-80 task 5)."""

    def _run_crews(
        self,
        crews_data: dict,
        ga_host_url: str = "",
        portal_tls_mode: str = "internal",
    ) -> list:
        registry = {"crews": crews_data}
        with (
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(server, "_crew_api", return_value=[]),
            patch.object(server, "_get_podman", return_value=Mock(
                system_info=lambda: {"host": {"memAvailable": 4 * 1024**3}}
            )),
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ga_host_url
            mock_cfg.ga_portal_tls_mode = portal_tls_mode
            result = server.crews()
        return result["crews"]

    def test_crews_includes_dashboard_url_when_port_assigned(self) -> None:
        crews_data = {
            "demo": {
                "container": "gs-demo",
                "status": "running",
                "composition": "spec-ops",
                "created_at": None,
                "dashboard_port": 9005,
                "cookie": "c",
            }
        }
        entries = self._run_crews(crews_data, ga_host_url="")
        self.assertEqual(len(entries), 1)
        # TRN-103: Portal is always on; internal TLS mode → https://
        self.assertEqual(entries[0]["dashboard_url"], "https://localhost:9005/")

    def test_crews_dashboard_url_uses_ga_host_url_host(self) -> None:
        crews_data = {
            "demo": {
                "container": "gs-demo",
                "status": "running",
                "composition": "spec-ops",
                "created_at": None,
                "dashboard_port": 9010,
                "cookie": "c",
            }
        }
        entries = self._run_crews(crews_data, ga_host_url="http://vm23.example.com:64057")
        self.assertIn("vm23.example.com:9010", entries[0]["dashboard_url"])

    def test_crews_dashboard_url_is_none_when_no_port(self) -> None:
        crews_data = {
            "demo": {
                "container": "gs-demo",
                "status": "running",
                "composition": "spec-ops",
                "created_at": None,
                "cookie": "c",
            }
        }
        entries = self._run_crews(crews_data)
        self.assertIsNone(entries[0]["dashboard_url"])

    # ── 9.2 (TRN-116): dashboard URL when Caddy portal TLS is off ────────────

    def test_crews_dashboard_url_uses_http_when_tls_off(self) -> None:
        """9.2a: with ga_portal_tls_mode='off' the dashboard URL uses http://
        and the direct port, not the Caddy-proxied https:// URL."""
        crews_data = {
            "demo": {
                "container": "gs-demo",
                "status": "running",
                "composition": "spec-ops",
                "created_at": None,
                "dashboard_port": 9005,
                "cookie": "c",
            }
        }
        entries = self._run_crews(crews_data, ga_host_url="", portal_tls_mode="off")
        self.assertEqual(entries[0]["dashboard_url"], "http://localhost:9005/")
        self.assertTrue(entries[0]["dashboard_url"].startswith("http://"))

    def test_crews_dashboard_url_http_with_ga_host_when_tls_off(self) -> None:
        """9.2b: tls-off honours the ga_host_url host but keeps the http:// scheme
        and the crew's own dashboard port (not the ga_host_url port)."""
        crews_data = {
            "demo": {
                "container": "gs-demo",
                "status": "running",
                "composition": "spec-ops",
                "created_at": None,
                "dashboard_port": 9010,
                "cookie": "c",
            }
        }
        entries = self._run_crews(
            crews_data,
            ga_host_url="http://vm23.example.com:64057",
            portal_tls_mode="off",
        )
        url = entries[0]["dashboard_url"]
        self.assertTrue(url.startswith("http://"))
        self.assertIn("vm23.example.com:9010", url)
class TRN101LaunchPortalTests(unittest.TestCase):
    """TRN-103: Portal is always present; launch(dashboard=True) allocates a dashboard."""

    def setUp(self) -> None:
        server._dashboard_ports_in_use.clear()

    def tearDown(self) -> None:
        server._dashboard_ports_in_use.clear()

    def _run_launch_portal(self, dashboard: bool = True) -> dict:
        """Run launch() and return result (Portal is always enabled)."""
        registry = {"crews": {}}
        podman = Mock()
        podman.network_create = Mock()
        podman.volume_create = Mock()
        podman.container_create = Mock(return_value={})
        podman.container_start = Mock()
        podman.container_stop = Mock()
        podman.container_remove = Mock()
        podman.volume_remove = Mock()
        finish_result = {
            "crew_id": "demo",
            "container": "gs-demo",
            "gateway_url": "http://gs-demo:5476",
            "status": "ready",
        }

        with (
            patch.object(server, "_read_auth_file", return_value="auth-b64"),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry", side_effect=lambda r: None),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_finish_crew_setup", return_value=finish_result),
            patch.object(server, "_resolve_composition", return_value={"name": "spec-ops", "description": ""}),
            patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(server, "_caddy_register_crew"),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ""
            mock_cfg.ga_portal_tls_mode = "internal"
            mock_cfg.ga_dashboard_port_range_start = 9000
            mock_cfg.ga_dashboard_port_range_size = 50
            result = server.launch("demo", dashboard=dashboard)
        return result

    def test_launch_dashboard_false_succeeds(self) -> None:
        """dashboard=False launches a headless crew — no error, no port allocated."""
        result = self._run_launch_portal(dashboard=False)
        self.assertNotIn("error", result)
        self.assertEqual(len(server._dashboard_ports_in_use), 0,
                         "No port should be allocated for a headless crew")

    def test_launch_dashboard_true_succeeds(self) -> None:
        """TRN-103: dashboard=True returns a dashboard_url (Portal is always on)."""
        result = self._run_launch_portal(dashboard=True)
        self.assertNotIn("error", result)
        self.assertIsNotNone(result.get("dashboard_url"))
class LaunchDashboardParamTests(unittest.TestCase):
    """TRN-80 task 5.3 / 9.1 / TRN-101 — launch(dashboard=True/False) port allocation gate."""

    def setUp(self) -> None:
        server._dashboard_ports_in_use.clear()

    def tearDown(self) -> None:
        server._dashboard_ports_in_use.clear()

    def _run_launch(self, dashboard: bool) -> dict:
        """Run server.launch() and return the result. Portal is always present."""
        registry = {"crews": {}}
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
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry", side_effect=lambda r: None),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_finish_crew_setup", return_value=finish_result),
            patch.object(server, "_resolve_composition", return_value={"name": "spec-ops", "description": ""}),
            patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(server, "_caddy_register_crew"),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ""
            mock_cfg.ga_portal_tls_mode = "internal"
            mock_cfg.ga_dashboard_port_range_start = 9000
            mock_cfg.ga_dashboard_port_range_size = 50
            result = server.launch("demo", dashboard=dashboard)
        return result

    def test_launch_dashboard_true_allocates_port_and_returns_dashboard_url(self) -> None:
        """9.1a — launch(dashboard=True) allocates port and returns dashboard_url."""
        result = self._run_launch(dashboard=True)
        self.assertIn("dashboard_url", result)
        self.assertIsNotNone(result["dashboard_url"])
        # TRN-103: Portal internal mode → https://
        self.assertTrue(result["dashboard_url"].startswith("https://"))
        self.assertIn("9000", result["dashboard_url"])
        # Port should be marked as in-use
        self.assertIn(9000, server._dashboard_ports_in_use)

    def test_launch_dashboard_false_does_not_allocate_port(self) -> None:
        """9.1b — launch(dashboard=False) does NOT allocate port, dashboard_url is null."""
        result = self._run_launch(dashboard=False)
        self.assertIn("dashboard_url", result)
        self.assertIsNone(result["dashboard_url"])
        # No port should have been allocated
        self.assertEqual(len(server._dashboard_ports_in_use), 0)

    def test_launch_dashboard_default_is_false(self) -> None:
        """9.1c — launch() default is dashboard=False (no port allocated)."""
        registry = {"crews": {}}
        podman = Mock()
        podman.network_create = Mock()
        podman.volume_create = Mock()
        podman.container_create = Mock(return_value={})
        podman.container_start = Mock()
        finish_result = {"crew_id": "demo", "container": "gs-demo", "status": "ready"}

        with (
            patch.object(server, "_read_auth_file", return_value="auth-b64"),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_finish_crew_setup", return_value=finish_result),
            patch.object(server, "_resolve_composition", return_value={"name": "spec-ops", "description": ""}),
            patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
            patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ""
            mock_cfg.ga_portal_tls_mode = "internal"
            mock_cfg.ga_dashboard_port_range_start = 9000
            mock_cfg.ga_dashboard_port_range_size = 50
            result = server.launch("demo")  # no dashboard=... passed

        self.assertIsNone(result.get("dashboard_url"))
        self.assertEqual(len(server._dashboard_ports_in_use), 0)
class DashboardRestEndpointTests(unittest.TestCase):
    """TRN-80 task 7.1-7.4 — POST/DELETE /crews/{id}/dashboard REST endpoints."""

    def setUp(self) -> None:
        server._dashboard_ports_in_use.clear()

    def tearDown(self) -> None:
        server._dashboard_ports_in_use.clear()

    # ── POST /crews/{id}/dashboard ────────────────────────────────────────────

    def test_post_dashboard_allocates_port_and_returns_dashboard_url(self) -> None:
        """7.1a — POST on crew without dashboard allocates port and returns dashboard_url."""
        crew = {"container": "gs-demo", "cookie": "c"}
        registry = {"crews": {"demo": dict(crew)}}

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
                patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(server, "_save_registry"),
                patch.object(server, "_caddy_register_crew") as mock_caddy,
                patch.object(server, "cfg") as mock_cfg,
            ):
                mock_cfg.ga_host_url = ""
                mock_cfg.ga_portal_tls_mode = "internal"
                request = _FakeStreamRequest(method="POST", path="/crews/demo/dashboard")
                resp = await server._handle_crew_dashboard_post(request)
                return resp, mock_caddy

        response, mock_caddy = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertIn("dashboard_url", body)
        self.assertIsNotNone(body["dashboard_url"])
        self.assertIn("9000", body["dashboard_url"])
        mock_caddy.assert_called_once_with("demo", 9000, crew_cookie="c")

    def test_post_dashboard_noop_when_already_active(self) -> None:
        """7.1b — POST on crew that already has a dashboard returns existing dashboard_url (no-op)."""
        crew = {"container": "gs-demo", "cookie": "c", "dashboard_port": 9003}
        registry = {"crews": {"demo": dict(crew)}}

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(server, "_caddy_register_crew") as mock_caddy,
                patch.object(server, "cfg") as mock_cfg,
            ):
                mock_cfg.ga_host_url = ""
                mock_cfg.ga_portal_tls_mode = "internal"
                request = _FakeStreamRequest(method="POST", path="/crews/demo/dashboard")
                resp = await server._handle_crew_dashboard_post(request)
                return resp, mock_caddy

        response, mock_caddy = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        # TRN-103: Portal internal mode → https://
        self.assertIn("9003", body["dashboard_url"])
        # No new port should have been allocated
        self.assertNotIn(9003, server._dashboard_ports_in_use)
        # Caddy should NOT be called on no-op
        mock_caddy.assert_not_called()

    def test_post_dashboard_404_for_unknown_crew(self) -> None:
        """7.1c — POST returns 404 for unknown crew."""
        async def run():
            with (
                patch.object(server, "_require_crew", side_effect=KeyError("no such crew")),
            ):
                request = _FakeStreamRequest(method="POST", path="/crews/unknown/dashboard")
                return await server._handle_crew_dashboard_post(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 404)

    def test_post_dashboard_409_when_port_pool_exhausted(self) -> None:
        """7.1d — POST returns 409 when port pool is exhausted."""
        crew = {"container": "gs-demo", "cookie": "c"}
        registry = {"crews": {"demo": dict(crew)}}

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
                patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 2),
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(server, "_caddy_register_crew"),
                patch.object(server, "cfg") as mock_cfg,
            ):
                mock_cfg.ga_host_url = ""
                mock_cfg.ga_portal_tls_mode = "internal"
                # Fill the pool
                server._dashboard_ports_in_use.update({9000, 9001})
                request = _FakeStreamRequest(method="POST", path="/crews/demo/dashboard")
                return await server._handle_crew_dashboard_post(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 409)
        body = json.loads(response.body)
        self.assertIn("error", body)

    def test_post_dashboard_uses_ga_host_url_for_dashboard_url(self) -> None:
        """7.1e — POST uses GA_HOST_URL hostname in dashboard_url when set."""
        crew = {"container": "gs-demo", "cookie": "c"}
        registry = {"crews": {"demo": dict(crew)}}

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_START", 9000),
                patch.object(server._caddy, "GA_DASHBOARD_PORT_RANGE_SIZE", 50),
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(server, "_save_registry"),
                patch.object(server, "_caddy_register_crew") as mock_caddy,
                patch.object(server, "cfg") as mock_cfg,
            ):
                mock_cfg.ga_host_url = "http://vm23.example.com:64057"
                mock_cfg.ga_portal_tls_mode = "internal"
                request = _FakeStreamRequest(method="POST", path="/crews/demo/dashboard")
                resp = await server._handle_crew_dashboard_post(request)
                return resp, mock_caddy

        response, mock_caddy = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertIn("vm23.example.com", body["dashboard_url"])
        self.assertIn("9000", body["dashboard_url"])
        mock_caddy.assert_called_once_with("demo", 9000, crew_cookie="c")

    # ── DELETE /crews/{id}/dashboard ──────────────────────────────────────────

    def test_delete_dashboard_deregisters_and_releases_port(self) -> None:
        """TRN-101 2.5 — DELETE deregisters from Caddy, releases port, returns dashboard_url: null."""
        server._dashboard_ports_in_use.add(9004)
        crew = {"container": "gs-demo", "cookie": "c", "dashboard_port": 9004}
        registry = {"crews": {"demo": {**crew}}}

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server, "_caddy_deregister_crew") as mock_deregister,
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(server, "_save_registry"),
            ):
                request = _FakeStreamRequest(method="DELETE", path="/crews/demo/dashboard")
                resp = await server._handle_crew_dashboard_delete(request)
                return resp, mock_deregister

        response, mock_deregister = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertIsNone(body["dashboard_url"])
        mock_deregister.assert_called_once_with("demo")
        # Port should be released
        self.assertNotIn(9004, server._dashboard_ports_in_use)

    def test_delete_dashboard_noop_when_no_dashboard_active(self) -> None:
        """7.2b — DELETE on crew with no dashboard returns dashboard_url: null (no-op)."""
        crew = {"container": "gs-demo", "cookie": "c"}  # no dashboard_port

        async def run():
            with patch.object(server, "_require_crew", return_value=crew):
                request = _FakeStreamRequest(method="DELETE", path="/crews/demo/dashboard")
                return await server._handle_crew_dashboard_delete(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertIsNone(body["dashboard_url"])

    def test_delete_dashboard_404_for_unknown_crew(self) -> None:
        """7.2c — DELETE returns 404 for unknown crew."""
        async def run():
            with patch.object(server, "_require_crew", side_effect=KeyError("no such crew")):
                request = _FakeStreamRequest(method="DELETE", path="/crews/unknown/dashboard")
                return await server._handle_crew_dashboard_delete(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 404)

    def test_delete_dashboard_removes_dashboard_port_from_registry(self) -> None:
        """7.2d — DELETE clears dashboard_port field from registry."""
        server._dashboard_ports_in_use.add(9007)
        crew = {"container": "gs-demo", "cookie": "c", "dashboard_port": 9007}
        registry = {"crews": {"demo": {**crew}}}
        save_calls = []

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server, "_caddy_deregister_crew"),
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(server, "_save_registry", side_effect=lambda r: save_calls.append(
                    json.loads(json.dumps(r))
                )),
            ):
                request = _FakeStreamRequest(method="DELETE", path="/crews/demo/dashboard")
                return await server._handle_crew_dashboard_delete(request)

        asyncio.run(run())
        self.assertTrue(save_calls, "Expected _save_registry to be called")
        saved_crew = save_calls[-1]["crews"]["demo"]
        self.assertNotIn("dashboard_port", saved_crew)

    # ── BearerAuthMiddleware routing for /dashboard ───────────────────────────

    def test_middleware_dispatches_post_dashboard_when_auth_passes(self) -> None:
        """7.4a — POST /crews/demo/dashboard reaches handler after auth passes."""
        handled = []

        async def fake_post_handler(req):
            handled.append("post-dashboard")
            return server.JSONResponse({"dashboard_url": "http://localhost:9000/"})

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/crews/demo/dashboard",
            "headers": [(b"authorization", b"Bearer testkey")],
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="testkey",
            routes={("POST", "/crews/*/dashboard"): fake_post_handler})

        status, _, _ = _run_asgi(mw, scope)

        self.assertEqual(status, 200)
        self.assertIn("post-dashboard", handled)

    def test_middleware_dispatches_delete_dashboard_when_auth_passes(self) -> None:
        """7.4b — DELETE /crews/demo/dashboard reaches handler after auth passes."""
        handled = []

        async def fake_delete_handler(req):
            handled.append("delete-dashboard")
            return server.JSONResponse({"dashboard_url": None})

        scope = {
            "type": "http",
            "method": "DELETE",
            "path": "/crews/demo/dashboard",
            "headers": [(b"authorization", b"Bearer testkey")],
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="testkey",
            routes={("DELETE", "/crews/*/dashboard"): fake_delete_handler})

        status, _, _ = _run_asgi(mw, scope)

        self.assertEqual(status, 200)
        self.assertIn("delete-dashboard", handled)

    def test_middleware_returns_401_for_dashboard_when_key_wrong(self) -> None:
        """7.4c — /crews/demo/dashboard returns 401 when bearer token is wrong."""
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/crews/demo/dashboard",
            "headers": [(b"authorization", b"Bearer wrongkey")],
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="correctkey")
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)

    def test_middleware_dispatches_dashboard_without_auth_when_no_key(self) -> None:
        """7.4d — /crews/demo/dashboard is dispatched without auth when GA_API_KEY unset."""
        handled = []

        async def fake_post_handler(req):
            handled.append("post-dashboard-no-auth")
            return server.JSONResponse({"dashboard_url": "http://localhost:9000/"})

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/crews/demo/dashboard",
            "headers": [],  # No auth header
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="",
            routes={("POST", "/crews/*/dashboard"): fake_post_handler})

        status, _, body = _run_asgi(mw, scope)

        self.assertEqual(status, 200)
        self.assertIn("post-dashboard-no-auth", handled)
class CorsOriginInjectionTests(unittest.TestCase):
    """Tests for CORS origin injection at container_create time (TRN-80 task 6)."""

    def setUp(self) -> None:
        server._dashboard_ports_in_use.clear()

    def tearDown(self) -> None:
        server._dashboard_ports_in_use.clear()

    def _run_launch_capture_env(self, ga_host_url: str = "") -> dict:
        """Run server.launch() and return the env dict passed to container_create."""
        registry = {"crews": {}}
        podman = Mock()
        podman.network_create = Mock()
        podman.volume_create = Mock()
        podman.container_create = Mock(return_value={})
        podman.container_start = Mock()
        finish_result = {"crew_id": "demo", "container": "gs-demo", "gateway_url": "http://gs-demo:5476", "status": "ready"}

        with (
            patch.object(server, "_read_auth_file", return_value="auth-b64"),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_finish_crew_setup", return_value=finish_result),
            patch.object(server, "_resolve_composition", return_value={"name": "spec-ops", "description": ""}),
            patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(server, "cfg") as mock_cfg,
        ):
            mock_cfg.ga_host_url = ga_host_url
            mock_cfg.ga_dashboard_port_range_start = 9000
            mock_cfg.ga_dashboard_port_range_size = 50
            server.launch("demo")

        call_kwargs = podman.container_create.call_args.kwargs
        return call_kwargs["env"]

    def test_cors_includes_transport_origin_when_ga_host_url_set(self) -> None:
        env = self._run_launch_capture_env(ga_host_url="http://vm23.example.com:64057")
        origins = env.get("KIROCREW_CORS_ORIGINS", "")
        self.assertIn("http://vm23.example.com:64057", origins)

    def test_cors_falls_back_to_localhost_when_ga_host_url_unset(self) -> None:
        env = self._run_launch_capture_env(ga_host_url="")
        origins = env.get("KIROCREW_CORS_ORIGINS", "")
        self.assertIn("http://localhost:", origins)

    def test_cors_preserves_crew_internal_origin(self) -> None:
        env = self._run_launch_capture_env(ga_host_url="http://vm23.example.com:64057")
        origins = env.get("KIROCREW_CORS_ORIGINS", "")
        # Internal origin (container:5476) must still be present
        self.assertIn("gs-demo", origins)
        self.assertIn(str(server.CREW_GATEWAY_PORT), origins)

    def test_cors_includes_both_origins_when_existing_value_present(self) -> None:
        """Both crew-internal and transport origins appear in the comma-separated list."""
        env = self._run_launch_capture_env(ga_host_url="http://host.example.com:64057")
        origins = env.get("KIROCREW_CORS_ORIGINS", "")
        parts = [p.strip() for p in origins.split(",")]
        self.assertGreaterEqual(len(parts), 2)
