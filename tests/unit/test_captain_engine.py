"""Unit tests for transport/captain_engine.py (TRN-276).

Covers:
- _check_in_memory_pressure: below-threshold returns free_gb; above-threshold
  returns None; probe unavailable returns None (fail-open).
- _mail_admiral: delivery failure (exec raises) is swallowed — no propagation.
- _captain_do_status: stopped crew dict (container not running) returns without
  raising and includes a 'status' field.
- _captain_do_stop: idempotency — second call does not raise.

All tests use lightweight fakes or unittest.mock.patch — no full transport
startup required.  Registry state is provided by mutating registry._reg inside
a ``with registry:`` block (patched to no-op by the autouse conftest fixture).
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import transport.registry as _reg_mod
from transport.registry import registry
from tests.fakes import FakePodmanClient


# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_crew_dict(crew_id: str, *, running: bool = False) -> dict:
    """Minimal registry crew entry."""
    return {
        "container": f"gs-{crew_id}",
        "volume": f"gs-vol-{crew_id}",
        "home_volume": f"gs-home-{crew_id}",
        "status": "running" if running else "stopped",
        "enrolled_agents": ["raven"],
    }


def _fake_crew_obj(crew_id: str, *, running: bool = False):
    """Return a minimal Crew-like object (enough for captain_engine)."""
    from transport.crew import Crew
    return Crew(
        crew_id=crew_id,
        container=f"gs-{crew_id}",
        volume=f"gs-vol-{crew_id}",
        home_volume=f"gs-home-{crew_id}",
        status="running" if running else "stopped",
        enrolled_agents=["raven"],
    )


def _captain_schedule(crew_id: str, *, enabled: bool = True) -> dict:
    """Minimal captain schedule entry."""
    return {
        "type": "captain",
        "crew_id": crew_id,
        "enabled": enabled,
        "job_id": None,
    }


# ── 4.2 _check_in_memory_pressure ─────────────────────────────────────────────

class TestCheckInMemoryPressure(unittest.TestCase):
    """_check_in_memory_pressure: returns free_gb when below threshold, else None."""

    def _call(self):
        from transport.captain_engine import _check_in_memory_pressure
        return _check_in_memory_pressure()

    def test_below_threshold_returns_free_gb(self):
        """When host memory is below GA_RESOURCE_CRITICAL_GB, return the value."""
        podman = FakePodmanClient(mem_free_bytes=512 * 1024**2)  # 0.5 GB
        # Patch _get_podman and _get_host_memory_gb_cached to return 0.5 GB (below 1.0 default).
        with (
            patch("transport.captain_engine._get_podman", return_value=podman),
            patch("transport.captain_engine._get_host_memory_gb_cached", return_value=0.5),
        ):
            result = self._call()
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.5)

    def test_above_threshold_returns_none(self):
        """When host memory is at/above threshold, return None."""
        podman = FakePodmanClient(mem_free_bytes=8 * 1024**3)  # 8 GB
        with (
            patch("transport.captain_engine._get_podman", return_value=podman),
            patch("transport.captain_engine._get_host_memory_gb_cached", return_value=8.0),
        ):
            result = self._call()
        self.assertIsNone(result)

    def test_probe_unavailable_returns_none_fail_open(self):
        """When _get_podman raises, return None (fail-open — do not block dispatch)."""
        with patch("transport.captain_engine._get_podman", side_effect=RuntimeError("no socket")):
            result = self._call()
        self.assertIsNone(result)

    def test_memory_read_returns_none_fail_open(self):
        """When _get_host_memory_gb_cached returns None, return None."""
        podman = FakePodmanClient()
        with (
            patch("transport.captain_engine._get_podman", return_value=podman),
            patch("transport.captain_engine._get_host_memory_gb_cached", return_value=None),
        ):
            result = self._call()
        self.assertIsNone(result)


# ── 4.3 _mail_admiral ─────────────────────────────────────────────────────────

class TestMailAdmiral(unittest.TestCase):
    """_mail_admiral: delivery failure is swallowed — no exception propagates."""

    def _call(self, crew_id: str = "test-crew") -> None:
        from transport.captain_engine import _mail_admiral
        _mail_admiral(crew_id, subject="test subject", body="test body")

    def test_exec_stdin_raises_does_not_propagate(self):
        """If container_exec_stdin raises, _mail_admiral must not propagate it."""
        podman = FakePodmanClient()
        podman.container_exec_stdin = MagicMock(  # type: ignore[attr-defined]
            side_effect=RuntimeError("maildeliver not found")
        )
        crew_obj = _fake_crew_obj("test-crew")
        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = _fake_crew_dict("test-crew")
        fake_lc._to_crew.return_value = crew_obj

        with (
            patch("transport.captain_engine._lc", return_value=fake_lc),
            patch("transport.captain_engine._get_podman", return_value=podman),
        ):
            # Must not raise
            self._call("test-crew")

    def test_require_crew_raises_does_not_propagate(self):
        """If _require_crew raises, _mail_admiral swallows the exception."""
        fake_lc = MagicMock()
        fake_lc._require_crew.side_effect = KeyError("crew not found")

        with patch("transport.captain_engine._lc", return_value=fake_lc):
            self._call("nonexistent-crew")

    def test_missing_container_does_not_raise(self):
        """If the Crew object has no container, _mail_admiral returns without raising."""
        from transport.crew import Crew
        crew_no_container = Crew(
            crew_id="empty",
            container="",
            volume="gs-vol-empty",
            home_volume="gs-home-empty",
        )
        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = _fake_crew_dict("empty")
        fake_lc._to_crew.return_value = crew_no_container

        with patch("transport.captain_engine._lc", return_value=fake_lc):
            self._call("empty")


# ── 4.4 _captain_do_status ────────────────────────────────────────────────────

class TestCaptainDoStatus(unittest.TestCase):
    """_captain_do_status: stopped-crew path returns without raising, includes status."""

    def setUp(self):
        self.crew_id = "status-crew"
        self.crew_dict = _fake_crew_dict(self.crew_id, running=False)
        self.crew_obj = _fake_crew_obj(self.crew_id, running=False)
        # Podman reports container NOT running
        self.podman = FakePodmanClient()
        self.podman.add_container(f"gs-{self.crew_id}", running=False)

    def _call(self):
        from transport.captain_engine import _captain_do_status
        return _captain_do_status(self.crew_id)

    def _fake_lc(self):
        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = self.crew_dict
        fake_lc._to_crew.return_value = self.crew_obj
        return fake_lc

    def test_stopped_crew_returns_dict_with_status(self):
        """Stopped crew returns a dict that includes a 'status' key."""
        crew_with_sched = dict(self.crew_dict)
        crew_with_sched["schedules"] = [_captain_schedule(self.crew_id)]
        with (
            patch("transport.captain_engine._lc", return_value=self._fake_lc()),
            patch("transport.captain_engine._get_podman", return_value=self.podman),
            patch("transport.captain_engine._skim_all_mailboxes", return_value={
                "captain": [], "admiral": [], "ghost": [], "spectre": [],
                "banshee": [], "wraith": [], "reaper": [], "raven": [],
            }),
            patch.object(_reg_mod, "_load_registry", return_value={"crews": {
                self.crew_id: crew_with_sched,
            }}),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = {"crews": {self.crew_id: crew_with_sched}}
            result = self._call()

        self.assertIsInstance(result, dict)
        self.assertIn("status", result)
        # Must not have propagated an error
        self.assertNotIn("error", result)

    def test_dormant_crew_no_captain_entry_returns_dormant(self):
        """Crew with no captain schedule entry returns status='dormant'."""
        with (
            patch("transport.captain_engine._lc", return_value=self._fake_lc()),
            patch("transport.captain_engine._get_podman", return_value=self.podman),
            patch("transport.captain_engine._skim_all_mailboxes", return_value={
                "captain": [], "admiral": [], "ghost": [], "spectre": [],
                "banshee": [], "wraith": [], "reaper": [], "raven": [],
            }),
            patch.object(_reg_mod, "_load_registry", return_value={"crews": {
                self.crew_id: self.crew_dict,
            }}),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = {"crews": {self.crew_id: self.crew_dict}}
            result = self._call()

        self.assertEqual(result.get("status"), "dormant")

    def test_crew_not_found_returns_error_dict(self):
        """Missing crew returns an error dict rather than raising."""
        fake_lc = MagicMock()
        fake_lc._require_crew.side_effect = KeyError("not found")

        with patch("transport.captain_engine._lc", return_value=fake_lc):
            result = self._call()

        self.assertIn("error", result)


# ── 4.5 _captain_do_stop idempotency ─────────────────────────────────────────

class TestCaptainDoStop(unittest.TestCase):
    """_captain_do_stop: calling twice must not raise on the second call."""

    def setUp(self):
        self.crew_id = "stop-crew"
        self.crew_dict = _fake_crew_dict(self.crew_id)
        self.crew_obj = _fake_crew_obj(self.crew_id)
        self.podman = FakePodmanClient()

    def _call(self):
        from transport.captain_engine import _captain_do_stop
        return _captain_do_stop(self.crew_id)

    def _fake_lc(self):
        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = self.crew_dict
        fake_lc._to_crew.return_value = self.crew_obj
        return fake_lc

    def _run_with_schedule(self, schedules: list[dict]):
        """Call _captain_do_stop with the given registry schedules."""
        fake_lc = self._fake_lc()
        crew_dict_with_sched = dict(self.crew_dict)
        crew_dict_with_sched["schedules"] = schedules
        with (
            patch("transport.captain_engine._lc", return_value=fake_lc),
            patch("transport.captain_engine._get_podman", return_value=self.podman),
            patch("transport.captain_engine._skim_all_mailboxes", return_value={
                k: [] for k in ["captain", "admiral", "ghost", "spectre",
                                 "banshee", "wraith", "reaper", "raven"]
            }),
            patch.object(_reg_mod, "_load_registry", return_value={"crews": {
                self.crew_id: crew_dict_with_sched,
            }}),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = {
                "crews": {self.crew_id: crew_dict_with_sched},
            }
            return self._call()

    def test_first_call_returns_stopped_status(self):
        """First stop call returns status='stopped'."""
        schedules = [_captain_schedule(self.crew_id, enabled=True)]
        result = self._run_with_schedule(schedules)
        self.assertEqual(result.get("status"), "stopped")

    def test_second_call_does_not_raise(self):
        """Second stop call (already stopped) must not raise."""
        # First call: enabled captain entry
        schedules = [_captain_schedule(self.crew_id, enabled=True)]
        self._run_with_schedule(schedules)
        # Second call: captain entry already disabled
        schedules_disabled = [_captain_schedule(self.crew_id, enabled=False)]
        result = self._run_with_schedule(schedules_disabled)
        # Should return a valid dict, not raise
        self.assertIsInstance(result, dict)

    def test_stop_with_no_captain_entry_returns_dormant(self):
        """Stop with no captain entry returns dormant, does not raise."""
        result = self._run_with_schedule([])
        self.assertEqual(result.get("status"), "dormant")

    def test_crew_not_found_returns_error_dict(self):
        """Missing crew returns an error dict rather than raising."""
        fake_lc = MagicMock()
        fake_lc._require_crew.side_effect = KeyError("not found")

        with patch("transport.captain_engine._lc", return_value=fake_lc):
            from transport.captain_engine import _captain_do_stop
            result = _captain_do_stop(self.crew_id)

        self.assertIn("error", result)
