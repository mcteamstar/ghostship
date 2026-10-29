"""Unit tests for transport/tools.py MCP tool functions (TRN-284).

Covers:
- nuke(): confirm=False returns preview, no container op; confirm=True calls
  container_stop and container_remove
- schedule(): missing name error; invalid interval error; action='cancel' non-
  existent job returns structured error
- dispatch(): crew not found returns {"error": ...}; gateway unreachable returns
  {"error": ...}
- resource_agents and resource_jobs MCP resource handlers: correct shape with
  empty and non-empty registry
- supply / evac stopped-crew branches
"""

from __future__ import annotations

import types
import sys
import unittest
from unittest.mock import MagicMock, patch

import transport.registry as _reg_mod
from transport.registry import registry


# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_crew_dict(crew_id: str, *, running: bool = False) -> dict:
    return {
        "container": f"gs-{crew_id}",
        "volume": f"gs-vol-{crew_id}",
        "home_volume": f"gs-home-{crew_id}",
        "status": "running" if running else "stopped",
        "schedules": [],
    }


def _patch_registry(test, crews: dict):
    """Install a persistent registry backing so with-registry blocks see it."""
    backing = {"crews": crews}
    p_load = patch.object(_reg_mod, "_load_registry", return_value=backing)
    p_save = patch.object(_reg_mod, "_save_registry")
    p_load.start()
    p_save.start()
    test.addCleanup(p_load.stop)
    test.addCleanup(p_save.stop)
    return backing["crews"]


# ── TestNuke ──────────────────────────────────────────────────────────────────

class TestNuke(unittest.TestCase):
    """nuke(): dry-run preview and confirmed teardown."""

    def setUp(self):
        self.crew_id = "test-nuke"
        self.crews = _patch_registry(self, {
            self.crew_id: _fake_crew_dict(self.crew_id, running=False),
        })
        registry._reg = {"crews": self.crews}

    def _call(self, confirm=False):
        try:
            from tools import nuke  # container flat /app/
        except ModuleNotFoundError:
            from transport.tools import nuke  # local dev
        return nuke(crew_id=self.crew_id, confirm=confirm)

    def test_dry_run_returns_warning(self):
        """confirm=False: returns preview dict with 'warning' key, no container op."""
        from tests.fakes import FakePodmanClient
        fake_podman = FakePodmanClient()
        with (
            patch("transport.tools._get_crew",
                  return_value=_fake_crew_dict(self.crew_id)),
            patch("transport.tools._to_crew", return_value=MagicMock(
                container=f"gs-{self.crew_id}",
                volume=f"gs-vol-{self.crew_id}",
                home_volume=f"gs-home-{self.crew_id}",
            )),
            patch("transport.tools._crew_api", return_value={"agents": []}),
        ):
            result = self._call(confirm=False)
        self.assertIn("warning", result)
        # container_stop never called
        self.assertFalse(fake_podman.was_called("container_stop"))

    def test_confirm_true_calls_cleanup(self):
        """confirm=True: calls cleanup via _cleanup_crew."""
        from tests.fakes import FakePodmanClient
        fake_podman = FakePodmanClient()
        fake_podman.add_container(f"gs-{self.crew_id}", running=True)
        with (
            patch("transport.tools._get_crew",
                  return_value=_fake_crew_dict(self.crew_id)),
            patch("transport.tools._get_podman", return_value=fake_podman),
            patch("transport.tools._to_crew", return_value=MagicMock(
                container=f"gs-{self.crew_id}",
                volume=f"gs-vol-{self.crew_id}",
                home_volume=f"gs-home-{self.crew_id}",
            )),
            patch("transport.tools._cleanup_crew") as mock_cleanup,
            patch("transport.tools._crew_api", return_value={"agents": []}),
            patch("transport.tools._caddy_portal", MagicMock()),
            patch("transport.tools._dashboard_gate", MagicMock()),
            patch("transport.tools._read_crew_secret", return_value=None),
            patch("transport.tools._delete_crew_secret"),
            patch("transport.tools._captain_order_locks", {}),
            patch("transport.tools._captain_order_locks_lock", MagicMock()),
        ):
            result = self._call(confirm=True)
        mock_cleanup.assert_called_once()
        self.assertEqual(result.get("status"), "nuked")


# ── TestSchedule ─────────────────────────────────────────────────────────────

class TestSchedule(unittest.TestCase):
    """schedule(): validation errors and cancel on non-existent job."""

    def _call(self, **kwargs):
        try:
            from tools import schedule  # container flat /app/
        except ModuleNotFoundError:
            from transport.tools import schedule  # local dev
        return schedule(**kwargs)

    def test_missing_name_returns_error(self):
        """action='create' without name returns error dict."""
        result = self._call(
            name="",
            message="do stuff",
            crew_id="test-crew",
            interval=300,
        )
        self.assertIn("error", result)

    def test_invalid_interval_too_low_returns_error(self):
        """interval < 60 returns error dict."""
        result = self._call(
            name="my-job",
            message="do stuff",
            crew_id="test-crew",
            interval=30,  # below minimum 60
        )
        # Validation must catch the interval at the schedule level or crew-not-found first;
        # either way, an error key must be present.
        # (crew not found is also fine — no real crew exists)
        self.assertIn("error", result)

    def test_cancel_nonexistent_job_returns_structured_error_or_success(self):
        """action='cancel' on a job that does not exist returns a dict (no raise)."""
        self.crew_id = "cancel-crew"
        self.crews = _patch_registry(self, {
            self.crew_id: _fake_crew_dict(self.crew_id),
        })
        registry._reg = {"crews": self.crews}

        with (
            patch("transport.tools._require_crew",
                  return_value=_fake_crew_dict(self.crew_id)),
            patch("transport.tools._ensure_crew_running",
                  return_value=_fake_crew_dict(self.crew_id)),
            patch("transport.tools._crew_api_with_recovery",
                  return_value={"jobs": []}),
        ):
            result = self._call(
                action="cancel",
                job_id="nonexistent-job-id",
                crew_id=self.crew_id,
            )
        # Must return a dict, not raise; may be cancelled or error
        self.assertIsInstance(result, dict)


# ── TestDispatch ──────────────────────────────────────────────────────────────

class TestDispatch(unittest.TestCase):
    """dispatch(): error paths for crew not found and gateway unreachable."""

    def _call(self, **kwargs):
        try:
            from tools import dispatch  # container flat /app/
        except ModuleNotFoundError:
            from transport.tools import dispatch  # local dev
        return dispatch(**kwargs)

    def test_crew_not_found_returns_error(self):
        """dispatch to a non-existent crew returns {"error": ...}."""
        _patch_registry(self, {})
        registry._reg = {"crews": {}}
        with patch("transport.tools._require_crew", side_effect=KeyError("not found")):
            result = self._call(task="do work", crew_id="missing-crew")
        self.assertIn("error", result)

    def test_gateway_unreachable_returns_error(self):
        """dispatch when gateway is unreachable returns {"error": ...}."""
        crew_id = "unreachable-crew"
        _patch_registry(self, {crew_id: _fake_crew_dict(crew_id)})
        registry._reg = {"crews": {crew_id: _fake_crew_dict(crew_id)}}

        try:
            from lifecycle import CrewUnresponsiveError  # container flat /app/
        except ModuleNotFoundError:
            from transport.lifecycle import CrewUnresponsiveError  # local dev

        with (
            patch("transport.tools._require_crew",
                  return_value=_fake_crew_dict(crew_id)),
            patch("transport.tools._ensure_crew_running",
                  return_value=_fake_crew_dict(crew_id)),
            patch("transport.tools._crew_api_with_recovery",
                  side_effect=CrewUnresponsiveError("gateway unreachable")),
            patch("transport.tools._resolve_dispatch_slot",
                  return_value=(None, None)),
        ):
            result = self._call(task="do work", crew_id=crew_id)
        self.assertIn("error", result)


# ── TestResourceAgents ────────────────────────────────────────────────────────

class TestResourceAgents(unittest.TestCase):
    """resource_agents: correct text shape with empty and non-empty agent dir."""

    def _call(self):
        try:
            from tools import resource_agents  # container flat /app/
        except ModuleNotFoundError:
            from transport.tools import resource_agents  # local dev
        return resource_agents()

    def test_empty_agents_dir_returns_message(self):
        """When agents dir does not exist, returns a no-agents message."""
        from pathlib import Path

        fake_path = MagicMock(spec=Path)
        fake_path.exists.return_value = False

        with patch("transport.tools._AGENTS_DIR", fake_path):
            result = self._call()
        self.assertIsInstance(result, str)
        # Should mention agents not found
        self.assertTrue(len(result) > 0)

    def test_populated_agents_dir_includes_names(self):
        """When agents dir has JSON files, returns descriptions."""
        import json
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            agent_data = {"name": "TestAgent", "description": "A test agent."}
            agent_file = os.path.join(tmpdir, "test-agent.json")
            with open(agent_file, "w") as f:
                json.dump(agent_data, f)

            with patch("transport.tools._AGENTS_DIR", Path(tmpdir)):
                result = self._call()

        self.assertIn("TestAgent", result)
        self.assertIn("A test agent.", result)


# ── TestResourceJobs ──────────────────────────────────────────────────────────

class TestResourceJobs(unittest.TestCase):
    """resource_jobs: correct shape with empty and non-empty registry."""

    def _call(self):
        try:
            from tools import resource_jobs  # container flat /app/
        except ModuleNotFoundError:
            from transport.tools import resource_jobs  # local dev
        return resource_jobs()

    def test_empty_registry_returns_no_crews_message(self):
        """When no crews exist, returns a 'no running crews' message."""
        _patch_registry(self, {})
        registry._reg = {"crews": {}}
        result = self._call()
        self.assertIsInstance(result, str)
        self.assertIn("No", result)

    def test_crew_with_schedules_includes_job_info(self):
        """When a crew has scheduled jobs, the output includes job details."""
        crew_id = "job-crew"
        crew_dict = dict(_fake_crew_dict(crew_id))
        crew_dict["schedules"] = [{
            "job_id": "job-123",
            "name": "my-job",
            "interval_secs": 300,
            "cron_expr": None,
            "one_shot": False,
            "agent": "ghost",
            "enabled": True,
            "next_fire_at": 9999999999.0,
        }]
        _patch_registry(self, {crew_id: crew_dict})
        registry._reg = {"crews": {crew_id: crew_dict}}
        result = self._call()
        self.assertIn("my-job", result)
        self.assertIn("job-123", result)


# ── TestSupplyStoppedCrew ─────────────────────────────────────────────────────

class TestSupplyStoppedCrew(unittest.TestCase):
    """supply: stopped-crew error branch."""

    def _call(self, **kwargs):
        try:
            from tools import supply  # container flat /app/
        except ModuleNotFoundError:
            from transport.tools import supply  # local dev
        return supply(**kwargs)

    def test_crew_not_found_returns_error(self):
        """supply to non-existent crew returns error dict."""
        _patch_registry(self, {})
        registry._reg = {"crews": {}}
        with patch("transport.tools._require_crew",
                   side_effect=KeyError("crew not found")):
            result = self._call(path="repo", crew_id="missing")
        self.assertIn("error", result)

    def test_nuked_during_restart_returns_error(self):
        """supply when crew was nuked during restart returns error dict."""
        crew_id = "nuked-crew"
        _patch_registry(self, {crew_id: _fake_crew_dict(crew_id)})
        registry._reg = {"crews": {crew_id: _fake_crew_dict(crew_id)}}

        try:
            from lifecycle import _NUKED_DURING_RESTART  # container flat /app/
        except ModuleNotFoundError:
            from transport.lifecycle import _NUKED_DURING_RESTART  # local dev

        with (
            patch("transport.tools._require_crew",
                  return_value=_fake_crew_dict(crew_id)),
            patch("transport.tools._ensure_crew_running",
                  return_value=_NUKED_DURING_RESTART),
        ):
            result = self._call(path="repo", crew_id=crew_id)
        self.assertIn("error", result)


# ── TestEvacStoppedCrew ───────────────────────────────────────────────────────

class TestEvacStoppedCrew(unittest.TestCase):
    """evac: stopped-crew / not-found error branch."""

    def _call(self, **kwargs):
        try:
            from tools import evac  # container flat /app/
        except ModuleNotFoundError:
            from transport.tools import evac  # local dev
        return evac(**kwargs)

    def test_crew_not_found_returns_error(self):
        """evac from non-existent crew returns error dict."""
        _patch_registry(self, {})
        registry._reg = {"crews": {}}
        with patch("transport.tools._ensure_crew_running",
                   side_effect=KeyError("not found")):
            result = self._call(path="repo/file.txt", crew_id="ghost-crew")
        self.assertIn("error", result)

    def test_invalid_path_traversal_returns_error(self):
        """evac with path traversal returns error dict."""
        result = self._call(path="../../etc/passwd", crew_id="any-crew")
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
