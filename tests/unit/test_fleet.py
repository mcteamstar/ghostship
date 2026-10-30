"""Unit tests for TRN-97/TRN-286 Lighthouse changes.

Covers:
  - _build_crews_payload: empty fleet, running crew, stopped crew, crew with
    dashboard_url.
  - _handle_internal_crews_get: 200 JSON, correct Content-Type, correct shape
    when fleet is empty or has one crew.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from tests.fakes import FakePodmanClient


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_scope(method: str, path: str) -> dict:
    return {
        "type": "http",
        "method": method.upper(),
        "path": path,
        "query_string": b"",
        "headers": [],
    }


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _collect_send():
    messages: list[dict] = []

    async def _send(message):
        messages.append(message)

    return messages, _send


def _status_of(messages):
    for m in messages:
        if m.get("type") == "http.response.start":
            return m["status"]
    return None


def _headers_of(messages) -> dict[str, str]:
    for m in messages:
        if m.get("type") == "http.response.start":
            return {
                k.decode().lower(): v.decode()
                for k, v in m.get("headers", [])
            }
    return {}


def _body_of(messages) -> bytes:
    parts = [m.get("body", b"") for m in messages if m.get("type") == "http.response.body"]
    return b"".join(parts)


# ── import helpers ────────────────────────────────────────────────────────────

def _import_build_crews_payload():
    try:
        from tools import _build_crews_payload  # container: flat /app/
    except ModuleNotFoundError:
        from transport.tools import _build_crews_payload  # local dev
    return _build_crews_payload


def _import_registry_module():
    try:
        import registry as _reg_mod
    except ModuleNotFoundError:
        from transport import registry as _reg_mod
    return _reg_mod


def _import_server():
    try:
        import server as _s
    except ModuleNotFoundError:
        from transport import server as _s
    return _s


# ── _build_crews_payload tests ────────────────────────────────────────────────

class TestBuildCrewsPayloadEmptyFleet(unittest.TestCase):
    """_build_crews_payload returns a valid payload for an empty registry."""

    def _run_with_empty_registry(self) -> dict:
        _build_crews_payload = _import_build_crews_payload()
        _reg_mod = _import_registry_module()
        podman = FakePodmanClient()
        with patch.object(_reg_mod, "_load_registry", return_value={"crews": {}}):
            return _build_crews_payload(podman)

    def test_crews_list_is_empty(self):
        result = self._run_with_empty_registry()
        self.assertEqual(result["crews"], [])

    def test_active_crews_is_zero(self):
        result = self._run_with_empty_registry()
        self.assertEqual(result["active_crews"], 0)

    def test_max_active_crews_present(self):
        result = self._run_with_empty_registry()
        self.assertIn("max_active_crews", result)

    def test_host_memory_present(self):
        # FakePodmanClient returns a valid system_info, so host_memory_available_gb
        # should be a number (not None).
        result = self._run_with_empty_registry()
        self.assertIn("host_memory_available_gb", result)

    def test_no_podman_still_returns_valid_shape(self):
        _build_crews_payload = _import_build_crews_payload()
        _reg_mod = _import_registry_module()
        with patch.object(_reg_mod, "_load_registry", return_value={"crews": {}}):
            result = _build_crews_payload(None)
        self.assertEqual(result["crews"], [])
        self.assertIsNone(result["host_memory_available_gb"])


class TestBuildCrewsPayloadRunningCrew(unittest.TestCase):
    """_build_crews_payload with a single running crew."""

    def setUp(self):
        self._build_crews_payload = _import_build_crews_payload()
        self._reg_mod = _import_registry_module()
        self._container_name = "ga-crew-alpha"
        self._podman = FakePodmanClient()
        self._podman.add_container(
            self._container_name,
            running=True,
            inspect={
                "Name": self._container_name,
                "State": {
                    "Status": "running",
                    "StartedAt": "2026-01-01T00:00:00Z",
                },
            },
        )
        self._registry_data = {
            "crews": {
                "alpha": {
                    "container": self._container_name,
                    "status": "running",
                    "composition": "spec-ops",
                    "acp_backend": "kiro",
                    "created_at": "2026-01-01T00:00:00Z",
                    "last_task_at": None,
                }
            }
        }

    def _call(self) -> dict:
        with patch.object(self._reg_mod, "_load_registry", return_value=self._registry_data), \
             patch("transport.lifecycle._probe_gateway", return_value=True):
            return self._build_crews_payload(self._podman)

    def test_returns_one_crew(self):
        result = self._call()
        self.assertEqual(len(result["crews"]), 1)

    def test_crew_id(self):
        result = self._call()
        self.assertEqual(result["crews"][0]["crew_id"], "alpha")

    def test_status_is_running(self):
        result = self._call()
        self.assertEqual(result["crews"][0]["status"], "running")

    def test_active_crews_count(self):
        result = self._call()
        self.assertEqual(result["active_crews"], 1)

    def test_uptime_secs_present(self):
        result = self._call()
        self.assertIsNotNone(result["crews"][0]["uptime_secs"])

    def test_dashboard_url_none_when_no_port(self):
        result = self._call()
        self.assertIsNone(result["crews"][0]["dashboard_url"])


class TestBuildCrewsPayloadStoppedCrew(unittest.TestCase):
    """_build_crews_payload with a single stopped crew."""

    def setUp(self):
        self._build_crews_payload = _import_build_crews_payload()
        self._reg_mod = _import_registry_module()
        self._podman = FakePodmanClient()
        self._registry_data = {
            "crews": {
                "beta": {
                    "container": "ga-crew-beta",
                    "status": "stopped",
                    "composition": "kirocrew",
                    "acp_backend": "kiro",
                    "created_at": "2026-01-01T00:00:00Z",
                    "last_task_at": None,
                }
            }
        }

    def _call(self) -> dict:
        with patch.object(self._reg_mod, "_load_registry", return_value=self._registry_data):
            return self._build_crews_payload(self._podman)

    def test_status_is_stopped(self):
        result = self._call()
        self.assertEqual(result["crews"][0]["status"], "stopped")

    def test_gateway_healthy_false(self):
        result = self._call()
        self.assertFalse(result["crews"][0]["gateway_healthy"])

    def test_active_crews_zero(self):
        result = self._call()
        self.assertEqual(result["active_crews"], 0)

    def test_uptime_secs_none(self):
        result = self._call()
        self.assertIsNone(result["crews"][0]["uptime_secs"])


class TestBuildCrewsPayloadDashboardUrl(unittest.TestCase):
    """_build_crews_payload populates dashboard_url when dashboard_port is set."""

    def setUp(self):
        self._build_crews_payload = _import_build_crews_payload()
        self._reg_mod = _import_registry_module()
        self._podman = FakePodmanClient()
        self._registry_data = {
            "crews": {
                "gamma": {
                    "container": "ga-crew-gamma",
                    "status": "stopped",
                    "composition": "kirocrew",
                    "acp_backend": "kiro",
                    "created_at": "2026-01-01T00:00:00Z",
                    "last_task_at": None,
                    "dashboard_port": 62000,
                }
            }
        }

    def _call(self) -> dict:
        with patch.object(self._reg_mod, "_load_registry", return_value=self._registry_data):
            return self._build_crews_payload(self._podman)

    def test_dashboard_url_not_none(self):
        result = self._call()
        self.assertIsNotNone(result["crews"][0]["dashboard_url"])

    def test_dashboard_url_contains_port(self):
        result = self._call()
        url = result["crews"][0]["dashboard_url"]
        self.assertIn("62000", url)


# ── _handle_internal_crews_get tests ─────────────────────────────────────────

class TestHandleInternalCrewsGet(unittest.TestCase):
    """GET /internal/crews returns fleet payload with valid X-Transport-Token,
    and 401 when the token is missing or wrong (enforced by TransportSecretMiddleware
    which wraps the whole app — these tests call the handler directly so they
    only verify the payload shape)."""

    def _run_handler(self, registry_data: dict) -> tuple[list[dict], bytes]:
        _s = _import_server()
        _reg_mod = _import_registry_module()
        handler = _s._handle_internal_crews_get
        scope = _make_scope("GET", "/internal/crews")
        messages, send = _collect_send()

        async def _invoke():
            from starlette.requests import Request
            req = Request(scope, _receive)
            resp = await handler(req)
            await resp(scope, _receive, send)

        with patch.object(_reg_mod, "_load_registry", return_value=registry_data), \
             patch("transport.tools._get_podman", side_effect=RuntimeError("no podman in test")):
            _run(_invoke())
        return messages, _body_of(messages)

    def test_status_200_empty_fleet(self):
        messages, _ = self._run_handler({"crews": {}})
        self.assertEqual(_status_of(messages), 200)

    def test_content_type_json(self):
        messages, _ = self._run_handler({"crews": {}})
        ct = _headers_of(messages).get("content-type", "")
        self.assertIn("application/json", ct)

    def test_empty_fleet_shape(self):
        _, body = self._run_handler({"crews": {}})
        data = json.loads(body)
        self.assertIn("crews", data)
        self.assertIn("active_crews", data)
        self.assertIn("max_active_crews", data)
        self.assertEqual(data["crews"], [])

    def test_fleet_one_crew(self):
        registry_data = {
            "crews": {
                "delta": {
                    "container": "ga-crew-delta",
                    "status": "stopped",
                    "composition": "kirocrew",
                    "acp_backend": "kiro",
                    "created_at": "2026-01-01T00:00:00Z",
                    "last_task_at": None,
                }
            }
        }
        _, body = self._run_handler(registry_data)
        data = json.loads(body)
        self.assertEqual(len(data["crews"]), 1)
        self.assertEqual(data["crews"][0]["crew_id"], "delta")


if __name__ == "__main__":
    unittest.main()
