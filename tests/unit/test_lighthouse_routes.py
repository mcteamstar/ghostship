"""Unit tests for the TRN-97 fleet-observability REST endpoints.

Covers ``GET /api/crews`` and ``GET /api/crews/{crew_id}/mail`` registered on
``ga-transport`` (transport/server.py). Uses the same dependency-free stub
bootstrap as the rest of the unit suite via ``tests.unit.helpers``.

Both handlers are ``async`` and read ``request.scope["path"]``; we invoke them
directly with ``asyncio.run`` and a minimal request object, patching the
transport internals (``cfg``, ``_build_fleet_state``, ``_require_crew``,
``_get_podman``, ``_skim_all_mailboxes``) rather than standing up a container.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import unittest
from unittest.mock import MagicMock, patch

from tests.unit.helpers import server


class _Req:
    """Minimal request stub exposing a ``.scope`` with a path + query string."""

    def __init__(self, path: str, query: bytes = b"") -> None:
        self.scope = {"path": path, "method": "GET", "query_string": query}
        self.path_params = {}


def _body_dict(resp) -> dict:
    """Decode a JSONResponse body (works for both real Starlette and the stub)."""
    body = getattr(resp, "body", b"")
    if isinstance(body, str):
        body = body.encode("utf-8")
    return json.loads(body.decode("utf-8"))


def _cfg_with(**overrides):
    """Return a copy of server.cfg with fields overridden."""
    return dataclasses.replace(server.cfg, **overrides)


_FLEET_STATE = {
    "crews": [
        {
            "crew_id": "general",
            "container": "gs-general",
            "status": "running",
            "composition": "spec-ops",
            "created_at": "2026-09-01T10:00:00Z",
            "last_task_at": "2026-09-12T12:55:00Z",
            "gateway_healthy": True,
            "crew_image_version": "0.5.0",
            "uptime_secs": 3600,
            "dashboard_url": "http://localhost:64058/",
            "agents": [
                {"task_id": "abc123", "agent": "ghost", "done": False, "elapsed_secs": 120}
            ],
        }
    ],
    "host_memory_available_gb": 8.4,
    "active_crews": 1,
    "max_active_crews": 6,
}


class ApiCrewsTests(unittest.TestCase):
    def test_returns_fleet_state_when_enabled(self) -> None:
        with (
            patch.object(server, "cfg", _cfg_with(ga_lighthouse_enabled=True)),
            patch.object(server, "_build_fleet_state", return_value=_FLEET_STATE),
        ):
            resp = asyncio.run(server._handle_api_crews_get(_Req("/api/crews")))
        self.assertEqual(resp.status_code, 200)
        data = _body_dict(resp)
        # Top-level host fields (shape mirrors the crews() MCP tool).
        self.assertIn("crews", data)
        self.assertEqual(data["host_memory_available_gb"], 8.4)
        self.assertEqual(data["active_crews"], 1)
        self.assertEqual(data["max_active_crews"], 6)
        self.assertEqual(data["crews"][0]["crew_id"], "general")
        self.assertEqual(data["crews"][0]["agents"][0]["agent"], "ghost")

    def test_returns_404_when_flag_off(self) -> None:
        with (
            patch.object(server, "cfg", _cfg_with(ga_lighthouse_enabled=False)),
            patch.object(server, "_build_fleet_state", return_value=_FLEET_STATE) as bfs,
        ):
            resp = asyncio.run(server._handle_api_crews_get(_Req("/api/crews")))
        self.assertEqual(resp.status_code, 404)
        # Must not do any work when disabled.
        bfs.assert_not_called()


class ApiCrewMailTests(unittest.TestCase):
    CREW = {"container": "gs-general", "status": "running"}

    def _running_podman(self, running: bool = True):
        podman = MagicMock()
        podman.container_is_running.return_value = running
        return podman

    def test_returns_mail_summary_for_running_crew(self) -> None:
        skimmed = {
            "ghost": [
                {"subject": "TRN-97 plan ready", "received_at": None},
                {"subject": "lighthouse discovery attached", "received_at": None},
            ],
            "spectre": [],
        }
        with (
            patch.object(server, "cfg", _cfg_with(ga_lighthouse_enabled=True)),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=self._running_podman(True)),
            patch.object(server, "_skim_all_mailboxes", return_value=skimmed),
        ):
            resp = asyncio.run(
                server._handle_api_crew_mail_get(_Req("/api/crews/general/mail"))
            )
        self.assertEqual(resp.status_code, 200)
        data = _body_dict(resp)
        self.assertEqual(data["crew_id"], "general")
        self.assertEqual(data["mailboxes"]["ghost"]["unread"], 2)
        self.assertEqual(
            data["mailboxes"]["ghost"]["subjects"],
            ["TRN-97 plan ready", "lighthouse discovery attached"],
        )
        self.assertEqual(data["mailboxes"]["spectre"]["unread"], 0)
        self.assertEqual(data["mailboxes"]["spectre"]["subjects"], [])

    def test_caps_subjects_at_five(self) -> None:
        many = [{"subject": f"s{i}", "received_at": None} for i in range(9)]
        with (
            patch.object(server, "cfg", _cfg_with(ga_lighthouse_enabled=True)),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=self._running_podman(True)),
            patch.object(server, "_skim_all_mailboxes", return_value={"ghost": many}),
        ):
            resp = asyncio.run(
                server._handle_api_crew_mail_get(_Req("/api/crews/general/mail"))
            )
        data = _body_dict(resp)
        self.assertEqual(data["mailboxes"]["ghost"]["unread"], 9)
        self.assertEqual(len(data["mailboxes"]["ghost"]["subjects"]), 5)

    def test_returns_404_for_unknown_crew(self) -> None:
        with (
            patch.object(server, "cfg", _cfg_with(ga_lighthouse_enabled=True)),
            patch.object(server, "_require_crew", side_effect=KeyError("nope")),
        ):
            resp = asyncio.run(
                server._handle_api_crew_mail_get(_Req("/api/crews/ghosttown/mail"))
            )
        self.assertEqual(resp.status_code, 404)

    def test_returns_503_for_stopped_crew(self) -> None:
        with (
            patch.object(server, "cfg", _cfg_with(ga_lighthouse_enabled=True)),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=self._running_podman(False)),
            patch.object(server, "_skim_all_mailboxes", return_value={}),
        ):
            resp = asyncio.run(
                server._handle_api_crew_mail_get(_Req("/api/crews/general/mail"))
            )
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(_body_dict(resp)["error"], "crew container not running")

    def test_returns_404_when_flag_off(self) -> None:
        with (
            patch.object(server, "cfg", _cfg_with(ga_lighthouse_enabled=False)),
            patch.object(server, "_require_crew") as require,
        ):
            resp = asyncio.run(
                server._handle_api_crew_mail_get(_Req("/api/crews/general/mail"))
            )
        self.assertEqual(resp.status_code, 404)
        require.assert_not_called()


class RouteRegistrationTests(unittest.TestCase):
    """The two handlers exist on the server module (wired into BearerAuthMiddleware)."""

    def test_handlers_exist(self) -> None:
        self.assertTrue(hasattr(server, "_handle_api_crews_get"))
        self.assertTrue(hasattr(server, "_handle_api_crew_mail_get"))


if __name__ == "__main__":
    unittest.main()
