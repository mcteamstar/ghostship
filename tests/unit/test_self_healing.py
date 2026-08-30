"""Tests for transport self-healing: liveness probe, cookie refresh, retry wrapper,
error messages, call-site migration, crews() gateway_healthy, and integration scenarios.

Covers tasks.md sections 1.3, 2.2, 3.4, 4.3, 5.3, 6.3, 7.1–7.3.
"""
from __future__ import annotations

import json
import sys
import threading
import types
import unittest
from typing import Any
from unittest.mock import Mock, patch, MagicMock

def _ensure_httpx_exceptions() -> None:
    """Add exception classes to the httpx stub module if missing."""
    _httpx = sys.modules.get("httpx")
    if _httpx is None:
        return
    if not hasattr(_httpx, "HTTPStatusError"):

        class HTTPStatusError(Exception):
            def __init__(self, message="", request=None, response=None):
                super().__init__(message)
                self.request = request
                self.response = response

        _httpx.HTTPStatusError = HTTPStatusError  # type: ignore[attr-defined]

    if not hasattr(_httpx, "ConnectError"):

        class ConnectError(Exception):
            pass

        _httpx.ConnectError = ConnectError  # type: ignore[attr-defined]

    if not hasattr(_httpx, "ConnectTimeout"):

        class ConnectTimeout(Exception):
            pass

        _httpx.ConnectTimeout = ConnectTimeout  # type: ignore[attr-defined]


from tests.unit.test_file_transfer import server

_ensure_httpx_exceptions()
import httpx
import transport.registry as _registry_mod


# ── Helpers ───────────────────────────────────────────────────────────────────


class FakeResponse:
    """Minimal httpx.Response stand-in for testing."""

    def __init__(self, status_code: int = 200, json_body: Any = None):
        self.status_code = status_code
        self._json = json_body if json_body is not None else {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=MagicMock(),
                response=self,
            )


class FakeHTTP:
    """Fake httpx.Client replacement for controlling responses."""

    def __init__(self, responses: list[FakeResponse] | None = None):
        self._responses = list(responses or [])
        self._call_idx = 0

    def get(self, url, **kwargs):
        return self._next()

    def request(self, method, url, **kwargs):
        return self._next()

    def _next(self):
        if self._call_idx < len(self._responses):
            r = self._responses[self._call_idx]
            self._call_idx += 1
            return r
        return FakeResponse(200, {})


# ── 1.3 Unit tests for _probe_gateway ────────────────────────────────────────


class TestProbeGateway(unittest.TestCase):
    """Task 1.3: success, non-2xx, connection refused, and timeout cases."""

    def test_probe_success(self):
        """Probe returns True on 200."""
        fake_http = FakeHTTP([FakeResponse(200)])
        with patch.object(server, "_http", fake_http):
            self.assertTrue(server._probe_gateway("http://gs-test:5476"))

    def test_probe_non_2xx(self):
        """Probe returns False on non-2xx (e.g. 500)."""
        fake_http = FakeHTTP([FakeResponse(500)])
        with patch.object(server, "_http", fake_http):
            self.assertFalse(server._probe_gateway("http://gs-test:5476"))

    def test_probe_connection_refused(self):
        """Probe returns False on connection error."""
        mock_http = Mock()
        mock_http.get.side_effect = ConnectionError("Connection refused")
        with patch.object(server, "_http", mock_http):
            self.assertFalse(server._probe_gateway("http://gs-test:5476"))

    def test_probe_timeout(self):
        """Probe returns False on timeout."""
        mock_http = Mock()
        mock_http.get.side_effect = httpx.ConnectTimeout("timeout")
        with patch.object(server, "_http", mock_http):
            self.assertFalse(server._probe_gateway("http://gs-test:5476"))


# ── 2.2 Unit tests for _refresh_cookie ───────────────────────────────────────


class TestRefreshCookie(unittest.TestCase):
    """Task 2.2: successful mint, failed mint, and registry update."""

    def _make_crew(self, crew_id="test-crew"):
        return {
            "container": f"gs-{crew_id}",
            "cookie": "old-cookie",
            "volume": f"gs-vol-{crew_id}",
            "status": "running",
        }

    def test_refresh_success(self):
        """Successful cookie refresh returns True and updates crew dict."""
        crew = self._make_crew()
        mock_podman = Mock()
        reg = {"crews": {"test-crew": {**crew}}}

        with (
            patch.object(server, "_get_podman", return_value=mock_podman),
            patch.object(server, "_mint_cookie", return_value="new-cookie"),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
        ):
            result = server._refresh_cookie(crew, "test-crew")

        self.assertTrue(result)
        self.assertEqual(crew["cookie"], "new-cookie")

    def test_refresh_mint_fails(self):
        """Failed mint returns False, cookie unchanged."""
        crew = self._make_crew()
        mock_podman = Mock()

        with (
            patch.object(server, "_get_podman", return_value=mock_podman),
            patch.object(server, "_mint_cookie", return_value=None),
        ):
            result = server._refresh_cookie(crew, "test-crew")

        self.assertFalse(result)
        self.assertEqual(crew["cookie"], "old-cookie")

    def test_refresh_updates_registry(self):
        """Successful refresh writes new cookie to registry."""
        crew = self._make_crew()
        mock_podman = Mock()
        reg = {"crews": {"test-crew": {**crew}}}
        saved = {}

        def capture_save(r):
            saved["reg"] = r

        with (
            patch.object(server, "_get_podman", return_value=mock_podman),
            patch.object(server, "_mint_cookie", return_value="refreshed-cookie"),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry", side_effect=capture_save),
        ):
            server._refresh_cookie(crew, "test-crew")

        self.assertEqual(saved["reg"]["crews"]["test-crew"]["cookie"], "refreshed-cookie")


# ── 3.4 Unit tests for retry flow ────────────────────────────────────────────


class TestCrewApiWithRecovery(unittest.TestCase):
    """Task 3.4: stale-cookie path, connection-error path, double-failure."""

    def _make_crew(self, crew_id="test-crew"):
        return {
            "container": f"gs-{crew_id}",
            "cookie": "session-cookie",
            "volume": f"gs-vol-{crew_id}",
            "status": "running",
        }

    def test_stale_cookie_recovery(self):
        """400 triggers cookie refresh; retry succeeds."""
        crew = self._make_crew()
        call_count = [0]

        def mock_crew_api(c, method, path, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                resp = FakeResponse(400)
                raise httpx.HTTPStatusError("400", request=MagicMock(), response=resp)
            return {"ok": True}

        with (
            patch.object(server, "_crew_api", side_effect=mock_crew_api),
            patch.object(server, "_refresh_cookie", return_value=True),
        ):
            result = server._crew_api_with_recovery(crew, "test-crew", "GET", "/api/spawn")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(call_count[0], 2)

    def test_connection_error_recovery(self):
        """Connection error triggers restart; retry succeeds."""
        crew = self._make_crew()
        call_count = [0]

        def mock_crew_api(c, method, path, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise httpx.ConnectError("Connection refused")
            return {"recovered": True}

        with (
            patch.object(server, "_crew_api", side_effect=mock_crew_api),
            patch.object(server, "_probe_gateway", return_value=False),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            result = server._crew_api_with_recovery(crew, "test-crew", "GET", "/test")

        self.assertEqual(result, {"recovered": True})
        self.assertEqual(call_count[0], 2)

    def test_connection_error_probe_alive_retries_directly(self):
        """Connection error but probe returns True → retry without restart."""
        crew = self._make_crew()
        call_count = [0]
        ensure_called = [False]

        def mock_crew_api(c, method, path, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise httpx.ConnectError("transient blip")
            return {"recovered": True}

        def mock_ensure(c, cid, **kw):
            ensure_called[0] = True
            return c

        with (
            patch.object(server, "_crew_api", side_effect=mock_crew_api),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(server, "_ensure_crew_running", side_effect=mock_ensure),
        ):
            result = server._crew_api_with_recovery(crew, "test-crew", "GET", "/test")

        self.assertEqual(result, {"recovered": True})
        self.assertFalse(ensure_called[0], "should not restart when probe is alive")

    def test_double_failure_raises(self):
        """Both recovery attempts fail → CrewUnresponsiveError."""
        crew = self._make_crew()

        def always_fail(c, method, path, **kw):
            resp = FakeResponse(403)
            raise httpx.HTTPStatusError("403", request=MagicMock(), response=resp)

        with (
            patch.object(server, "_crew_api", side_effect=always_fail),
            patch.object(server, "_refresh_cookie", return_value=False),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            with self.assertRaises(server.CrewUnresponsiveError):
                server._crew_api_with_recovery(crew, "test-crew", "POST", "/api/spawn")

    def test_no_infinite_loops(self):
        """Retry cap: at most one retry per failure class."""
        crew = self._make_crew()
        api_calls = [0]

        def counting_fail(c, method, path, **kw):
            api_calls[0] += 1
            raise httpx.ConnectError("refused")

        with (
            patch.object(server, "_crew_api", side_effect=counting_fail),
            patch.object(server, "_probe_gateway", return_value=False),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            with self.assertRaises(server.CrewUnresponsiveError):
                server._crew_api_with_recovery(crew, "test-crew", "GET", "/test")

        # Should be exactly 2: initial attempt + one retry after recovery
        self.assertEqual(api_calls[0], 2)

    def test_per_crew_locking(self):
        """Concurrent recovery for the same crew is serialised."""
        lock = server._get_recovery_lock("lock-test")
        # Lock objects have acquire/release methods
        self.assertTrue(hasattr(lock, "acquire"))
        self.assertTrue(hasattr(lock, "release"))
        # Same crew_id returns same lock
        self.assertIs(lock, server._get_recovery_lock("lock-test"))
        # Different crew_id returns different lock
        self.assertIsNot(lock, server._get_recovery_lock("other-crew"))


# ── 4.3 Unit tests for error message formatting ──────────────────────────────


class TestErrorMessages(unittest.TestCase):
    """Task 4.3: error messages on both recovery-failure paths."""

    def _make_crew(self, crew_id="my-crew"):
        return {
            "container": f"gs-{crew_id}",
            "cookie": "cookie",
            "volume": f"gs-vol-{crew_id}",
            "status": "running",
        }

    def test_stale_cookie_failure_message(self):
        """Error message mentions crew_id and actions taken (cookie + restart)."""
        crew = self._make_crew()

        def always_fail(c, method, path, **kw):
            resp = FakeResponse(401)
            raise httpx.HTTPStatusError("401", request=MagicMock(), response=resp)

        with (
            patch.object(server, "_crew_api", side_effect=always_fail),
            patch.object(server, "_refresh_cookie", return_value=False),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            with self.assertRaises(server.CrewUnresponsiveError) as ctx:
                server._crew_api_with_recovery(crew, "my-crew", "GET", "/test")

        msg = str(ctx.exception)
        self.assertIn("my-crew", msg)
        self.assertIn("cookie refresh", msg)
        self.assertIn("container restart", msg)
        self.assertIn("Suggestion:", msg)

    def test_connection_error_failure_message(self):
        """Error message mentions crew_id and restart action."""
        crew = self._make_crew()

        def always_fail(c, method, path, **kw):
            raise httpx.ConnectError("refused")

        with (
            patch.object(server, "_crew_api", side_effect=always_fail),
            patch.object(server, "_probe_gateway", return_value=False),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            with self.assertRaises(server.CrewUnresponsiveError) as ctx:
                server._crew_api_with_recovery(crew, "my-crew", "POST", "/test")

        msg = str(ctx.exception)
        self.assertIn("my-crew", msg)
        self.assertIn("restart", msg)
        self.assertIn("Suggestion:", msg)

    def test_no_traceback_leak(self):
        """Error messages do not contain tracebacks or raw HTTP bodies."""
        crew = self._make_crew()

        def always_fail(c, method, path, **kw):
            resp = FakeResponse(400)
            raise httpx.HTTPStatusError("400 Bad CSRF", request=MagicMock(), response=resp)

        with (
            patch.object(server, "_crew_api", side_effect=always_fail),
            patch.object(server, "_refresh_cookie", return_value=False),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            with self.assertRaises(server.CrewUnresponsiveError) as ctx:
                server._crew_api_with_recovery(crew, "my-crew", "GET", "/test")

        msg = str(ctx.exception)
        self.assertNotIn("Traceback", msg)
        self.assertNotIn("gs-my-crew", msg)  # No raw container names
        self.assertNotIn("Bad CSRF", msg)  # No raw HTTP body


# ── 5.3 Regression: call-site migration ──────────────────────────────────────


class TestCallSiteMigration(unittest.TestCase):
    """Task 5.3: tool handlers use _crew_api_with_recovery, internals use raw."""

    def test_dispatch_uses_recovery(self):
        """dispatch() routes through _crew_api_with_recovery."""
        crew = {
            "container": "gs-test",
            "cookie": "c",
            "volume": "gs-vol-test",
            "status": "running",
        }
        reg = {"crews": {"test": crew}}

        with (
            patch.object(server, "_get_podman") as mock_podman_fn,
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(_registry_mod, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
            patch.object(_registry_mod, "_save_registry"),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(
                server,
                "_crew_api_with_recovery",
                return_value={"id": "task-1"},
            ) as mock_recovery,
        ):
            mock_podman_fn.return_value = Mock(container_is_running=Mock(return_value=True))
            result = server.dispatch("do something", agent="ghost", crew_id="test")

        mock_recovery.assert_called_once()
        self.assertEqual(result["task_id"], "task-1")

    def test_ensure_crew_running_uses_raw_api(self):
        """_ensure_crew_running never calls _crew_api_with_recovery (no recursion)."""
        import inspect

        source = inspect.getsource(server._ensure_crew_running)
        self.assertNotIn("_crew_api_with_recovery", source)


# ── 6.3 Unit tests for crews() gateway_healthy ───────────────────────────────


class TestCrewsGatewayHealthy(unittest.TestCase):
    """Task 6.3: healthy, unhealthy, and stopped crew scenarios."""

    def _make_registry(self, crews_dict):
        return {"crews": crews_dict}

    def test_healthy_crew(self):
        """Running crew with responsive gateway → gateway_healthy: True."""
        reg = self._make_registry({
            "alpha": {
                "container": "gs-alpha",
                "cookie": "c",
                "status": "running",
                "composition": "kirocrew",
                "created_at": "2026-01-01T00:00:00",
            }
        })
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(server, "_crew_api", return_value=[]),
        ):
            result = server.crews()

        self.assertEqual(len(result["crews"]), 1)
        self.assertTrue(result["crews"][0]["gateway_healthy"])

    def test_unhealthy_crew(self):
        """Running crew with dead gateway → gateway_healthy: False."""
        reg = self._make_registry({
            "beta": {
                "container": "gs-beta",
                "cookie": "c",
                "status": "running",
                "composition": "kirocrew",
                "created_at": "2026-01-01T00:00:00",
            }
        })
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_probe_gateway", return_value=False),
            patch.object(server, "_crew_api", side_effect=Exception("dead")),
        ):
            result = server.crews()

        self.assertEqual(len(result["crews"]), 1)
        self.assertFalse(result["crews"][0]["gateway_healthy"])

    def test_stopped_crew(self):
        """Stopped crew → gateway_healthy: False without probing."""
        reg = self._make_registry({
            "gamma": {
                "container": "gs-gamma",
                "cookie": "c",
                "status": "stopped",
                "composition": "kirocrew",
                "created_at": "2026-01-01T00:00:00",
            }
        })
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_probe_gateway") as mock_probe,
            patch.object(server, "_crew_api", side_effect=Exception("stopped")),
        ):
            result = server.crews()

        self.assertEqual(len(result["crews"]), 1)
        self.assertFalse(result["crews"][0]["gateway_healthy"])
        # Probe should NOT be called for stopped containers
        mock_probe.assert_not_called()


# ── 7.1–7.3 Integration tests ────────────────────────────────────────────────


class TestIntegrationGatewayCrash(unittest.TestCase):
    """Task 7.1: Simulate gateway crash mid-request, verify transparent recovery."""

    def test_crash_mid_request_recovers(self):
        """Connection error mid-request → restart → transparent retry."""
        crew = {
            "container": "gs-integ",
            "cookie": "c",
            "volume": "gs-vol-integ",
            "status": "running",
        }
        call_count = [0]

        def simulate_crash_then_recover(c, method, path, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise httpx.ConnectError("Connection reset by peer")
            return {"agents": []}

        with (
            patch.object(server, "_crew_api", side_effect=simulate_crash_then_recover),
            patch.object(server, "_probe_gateway", return_value=False),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            result = server._crew_api_with_recovery(crew, "integ", "GET", "/api/spawn")

        self.assertEqual(result, {"agents": []})
        self.assertEqual(call_count[0], 2)


class TestIntegrationStaleCookie(unittest.TestCase):
    """Task 7.2: Simulate stale cookie (400), verify silent refresh+retry."""

    def test_stale_cookie_silent_refresh(self):
        """400 → cookie refresh → retry succeeds silently."""
        crew = {
            "container": "gs-integ2",
            "cookie": "stale",
            "volume": "gs-vol-integ2",
            "status": "running",
        }
        call_count = [0]

        def simulate_stale_then_ok(c, method, path, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                resp = FakeResponse(400)
                raise httpx.HTTPStatusError("400", request=MagicMock(), response=resp)
            return {"id": "task-123", "done": False}

        with (
            patch.object(server, "_crew_api", side_effect=simulate_stale_then_ok),
            patch.object(server, "_refresh_cookie", return_value=True),
        ):
            result = server._crew_api_with_recovery(crew, "integ2", "POST", "/api/spawn")

        self.assertEqual(result["id"], "task-123")
        self.assertEqual(call_count[0], 2)


class TestIntegrationDoubleFailure(unittest.TestCase):
    """Task 7.3: Double failure surfaces actionable error message."""

    def test_double_failure_actionable_error(self):
        """Both recovery attempts fail → actionable error surfaced to caller."""
        crew = {
            "container": "gs-integ3",
            "cookie": "c",
            "volume": "gs-vol-integ3",
            "status": "running",
        }

        def always_refuse(c, method, path, **kw):
            raise httpx.ConnectError("Connection refused")

        with (
            patch.object(server, "_crew_api", side_effect=always_refuse),
            patch.object(server, "_probe_gateway", return_value=False),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            with self.assertRaises(server.CrewUnresponsiveError) as ctx:
                server._crew_api_with_recovery(crew, "integ3", "GET", "/status")

        msg = str(ctx.exception)
        # Actionable: mentions crew, what was tried, suggestion
        self.assertIn("integ3", msg)
        self.assertIn("restart", msg)
        self.assertIn("Suggestion:", msg)
        # Does not leak internals
        self.assertNotIn("gs-integ3", msg)
        self.assertNotIn("Traceback", msg)


if __name__ == "__main__":
    unittest.main()
