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

try:
    import httpx2 as httpx
except ModuleNotFoundError:
    import httpx

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


# ---------------------------------------------------------------------------
# TRN-284: New tests for _dispatch_captain_checkin and _captain_do_order
# ---------------------------------------------------------------------------

class TestDispatchCaptainCheckinMemoryPressure(unittest.TestCase):
    """_dispatch_captain_checkin: memory-pressure skip path (task 4.1)."""

    def setUp(self):
        self.crew_id = "pressure-crew"
        self.crew_dict = _fake_crew_dict(self.crew_id, running=True)
        self.crew_obj = _fake_crew_obj(self.crew_id, running=True)

    def _call(self):
        from transport.captain_engine import _dispatch_captain_checkin
        return _dispatch_captain_checkin(self.crew_dict, self.crew_id)

    def _fake_lc(self):
        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = self.crew_dict
        fake_lc._to_crew.return_value = self.crew_obj
        fake_lc._write_dashboard_cookie = MagicMock()
        fake_lc._crew_api_with_recovery = MagicMock()
        return fake_lc

    def test_memory_pressure_no_spawn_and_error_starts_with_marker(self):
        """When host memory is below threshold, dispatch raises _MemoryPressureSkip
        with an error message that starts with the memory_pressure marker."""
        from transport.captain_engine import _MemoryPressureSkip, _MEMORY_PRESSURE_MARKER

        # Patch enrolled agents check
        crew_with_raven = dict(self.crew_dict)
        crew_with_raven["enrolled_agents"] = ["raven"]
        self.crew_obj.enrolled_agents = ["raven"]

        # Patch _get_host_memory_gb_cached to return a value below threshold
        # (return not-None means below threshold)
        with (
            patch("transport.captain_engine._lc", return_value=self._fake_lc()),
            patch("transport.captain_engine._get_podman", return_value=MagicMock()),
            patch("transport.captain_engine._get_host_memory_gb_cached",
                  return_value=0.3),  # below GA_RESOURCE_CRITICAL_GB
            patch.object(_reg_mod, "_load_registry",
                         return_value={"crews": {
                             self.crew_id: crew_with_raven,
                         }}),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = {"crews": {self.crew_id: crew_with_raven}}
            with self.assertRaises(_MemoryPressureSkip) as ctx:
                self._call()
        self.assertTrue(
            str(ctx.exception).startswith(_MEMORY_PRESSURE_MARKER),
            f"Expected error to start with {_MEMORY_PRESSURE_MARKER!r}, "
            f"got: {str(ctx.exception)!r}",
        )

    def test_memory_pressure_no_spawn_called(self):
        """Under memory pressure, POST /api/spawn is never called."""
        from transport.captain_engine import _MemoryPressureSkip

        crew_with_raven = dict(self.crew_dict)
        crew_with_raven["enrolled_agents"] = ["raven"]
        self.crew_obj.enrolled_agents = ["raven"]

        fake_lc = self._fake_lc()

        with (
            patch("transport.captain_engine._lc", return_value=fake_lc),
            patch("transport.captain_engine._get_podman", return_value=MagicMock()),
            patch("transport.captain_engine._get_host_memory_gb_cached",
                  return_value=0.3),
            patch.object(_reg_mod, "_load_registry",
                         return_value={"crews": {self.crew_id: crew_with_raven}}),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = {"crews": {self.crew_id: crew_with_raven}}
            try:
                self._call()
            except _MemoryPressureSkip:
                pass
        # _crew_api_with_recovery should never have been called
        fake_lc._crew_api_with_recovery.assert_not_called()


class TestDispatchCaptainCheckinClaudeModelOverride(unittest.TestCase):
    """_dispatch_captain_checkin: Claude backend uses crew model (task 4.2)."""

    def setUp(self):
        self.crew_id = "claude-crew"

    def test_claude_backend_uses_crew_model_not_raven_model(self):
        """For a Claude-backend crew with a configured model, the spawn request
        uses that crew model rather than a raven.json default model."""
        from transport.captain_engine import _dispatch_captain_checkin

        crew_dict = _fake_crew_dict(self.crew_id, running=True)
        crew_dict["acp_backend"] = "claude"
        crew_dict["model"] = "claude-sonnet-4-5"
        crew_dict["enrolled_agents"] = ["raven"]

        crew_obj = _fake_crew_obj(self.crew_id, running=True)
        crew_obj.acp_backend = "claude"
        crew_obj.enrolled_agents = ["raven"]

        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = crew_dict
        fake_lc._to_crew.return_value = crew_obj
        fake_lc._write_dashboard_cookie = MagicMock()

        spawn_calls = []

        def fake_crew_api(crew, crew_id, method, path, **kwargs):
            if method == "POST" and "/api/spawn" in path:
                spawn_calls.append(kwargs.get("json", {}))
                return {"id": "task-claude-001"}
            return {}

        fake_lc._crew_api_with_recovery.side_effect = fake_crew_api

        with (
            patch("transport.captain_engine._lc", return_value=fake_lc),
            patch("transport.captain_engine._get_podman", return_value=MagicMock()),
            patch("transport.captain_engine._get_host_memory_gb_cached",
                  return_value=None),  # no memory pressure
            patch.object(_reg_mod, "_load_registry",
                         return_value={"crews": {
                             self.crew_id: crew_dict,
                         }}),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = {"crews": {self.crew_id: crew_dict}}
            result = _dispatch_captain_checkin(crew_dict, self.crew_id)

        self.assertEqual(result, "task-claude-001")
        self.assertEqual(len(spawn_calls), 1)
        # The spawn body must carry the crew model
        self.assertEqual(spawn_calls[0].get("model"), "claude-sonnet-4-5")


class TestSteerCaptainCheckinFallback(unittest.TestCase):
    """_steer_captain_checkin: 400-on-continue falls back to dispatch (task 4.3)."""

    def setUp(self):
        self.crew_id = "steer-fallback-crew"
        self.crew_dict = _fake_crew_dict(self.crew_id, running=True)
        self.crew_obj = _fake_crew_obj(self.crew_id, running=True)
        self.crew_obj.enrolled_agents = ["raven"]

    def test_400_on_continue_triggers_redispatch(self):
        """When /continue returns 400, _steer_captain_checkin falls back to
        _dispatch_captain_checkin (fresh dispatch)."""
        from transport.captain_engine import _steer_captain_checkin

        captain_sched = {
            "type": "captain",
            "current_task_id": "old-task-001",
            "model": None,
            "enabled": True,
        }
        crew_dict = dict(self.crew_dict)
        crew_dict["enrolled_agents"] = ["raven"]
        crew_dict["schedules"] = [captain_sched]

        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = crew_dict
        fake_lc._to_crew.return_value = self.crew_obj
        fake_lc._write_dashboard_cookie = MagicMock()

        # /continue raises with "400 Bad Request" and "/continue" in the message
        try:
            import httpx2 as httpx
        except ModuleNotFoundError:
            import httpx

        bad_resp = MagicMock()
        bad_resp.status_code = 400
        bad_resp.text = "400 Bad Request"
        err_400 = httpx.HTTPStatusError(
            "400 Bad Request /continue",
            request=None,
            response=bad_resp,
        )
        err_400_str = "400 Bad Request /api/spawn/old-task-001/continue"

        dispatched_tasks = []

        def fake_crew_api(crew, crew_id, method, path, **kwargs):
            if "/continue" in path:
                raise RuntimeError(err_400_str)
            if method == "POST" and "/api/spawn" in path:
                dispatched_tasks.append(kwargs.get("json", {}))
                return {"id": "redispatch-001"}
            return {}

        fake_lc._crew_api_with_recovery.side_effect = fake_crew_api

        with (
            patch("transport.captain_engine._lc", return_value=fake_lc),
            patch("transport.captain_engine._get_podman", return_value=MagicMock()),
            patch("transport.captain_engine._get_host_memory_gb_cached",
                  return_value=None),
            patch.object(_reg_mod, "_load_registry",
                         return_value={"crews": {self.crew_id: crew_dict}}),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = {"crews": {self.crew_id: crew_dict}}
            result = _steer_captain_checkin(crew_dict, self.crew_id)

        # A fresh dispatch must have been made
        self.assertEqual(result, "redispatch-001")


class TestCaptainDoOrderReorder(unittest.TestCase):
    """_captain_do_order: re-order of existing schedule does not duplicate (task 4.4)."""

    def setUp(self):
        self.crew_id = "reorder-crew"
        self.crew_dict = _fake_crew_dict(self.crew_id, running=True)
        self.crew_obj = _fake_crew_obj(self.crew_id, running=True)
        self.crew_obj.enrolled_agents = ["raven"]

    def _fake_lc(self):
        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = self.crew_dict
        fake_lc._to_crew.return_value = self.crew_obj
        fake_lc._ensure_crew_running.return_value = self.crew_dict
        fake_lc._write_dashboard_cookie = MagicMock()
        fake_lc._crew_api_with_recovery = MagicMock(
            return_value={"id": "new-raven-task"}
        )
        return fake_lc

    def test_existing_captain_entry_is_updated_not_duplicated(self):
        """Calling _captain_do_order when a captain entry already exists updates
        the entry rather than adding a second one."""
        from transport.captain_engine import _captain_do_order

        existing_captain = {
            "type": "captain",
            "name": "__captain__",
            "interval_secs": 300,
            "cron_expr": None,
            "next_fire_at": 9999999999.0,
            "agent": "raven",
            "message": "check in",
            "enabled": True,
            "model": None,
            "current_task_id": "existing-task-id",
        }
        crew_dict = dict(self.crew_dict)
        crew_dict["schedules"] = [existing_captain]

        backing = {"crews": {self.crew_id: crew_dict}}

        with (
            patch("transport.captain_engine._lc", return_value=self._fake_lc()),
            patch("transport.captain_engine._get_podman", return_value=MagicMock()),
            patch("transport.captain_engine._get_host_memory_gb_cached",
                  return_value=None),
            patch("transport.captain_engine._append_captain_mail"),
            patch("transport.captain_engine._delete_sentinel_file"),
            patch.object(_reg_mod, "_load_registry", return_value=backing),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = backing

            result = _captain_do_order(
                crew_id=self.crew_id,
                message="new standing order",
                template=None,
                change_name=None,
                cron=None,
                interval=None,  # no new interval — reuses existing
                fire_immediately=False,
                model=None,
            )


        # Count captain-type schedules — must be exactly 1 (no duplication)
        captain_entries = [
            s for s in backing["crews"].get(self.crew_id, {}).get("schedules", [])
            if s.get("type") == "captain"
        ]
        self.assertEqual(
            len(captain_entries), 1,
            f"Expected 1 captain entry, found {len(captain_entries)}",
        )




class TestCaptainDoOrderCronFirstFire(unittest.TestCase):
    """_captain_do_order: cron schedules compute next_fire_at from the expression."""

    def setUp(self):
        self.crew_id = "cron-crew"
        self.crew_dict = _fake_crew_dict(self.crew_id, running=True)
        self.crew_obj = _fake_crew_obj(self.crew_id, running=True)
        self.podman = FakePodmanClient()

    def _fake_lc(self, crew_dict=None):
        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = crew_dict or self.crew_dict
        fake_lc._to_crew.return_value = self.crew_obj
        fake_lc._ensure_crew_running.return_value = crew_dict or self.crew_dict
        fake_lc._delete_sentinel_file = MagicMock()
        return fake_lc

    def _call(self, cron=None, interval=None, fake_lc=None):
        from transport.captain_engine import _captain_do_order
        _lc = fake_lc or self._fake_lc()
        with (
            patch("transport.captain_engine._lc", return_value=_lc),
            patch("transport.captain_engine._get_podman", return_value=self.podman),
            patch("transport.captain_engine._append_captain_mail"),
            patch("transport.captain_engine._delete_sentinel_file"),
            patch.object(_reg_mod, "_load_registry", return_value={"crews": {
                self.crew_id: self.crew_dict,
            }}),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = {"crews": {self.crew_id: self.crew_dict}}
            return _captain_do_order(
                crew_id=self.crew_id,
                message="test order",
                template=None,
                change_name=None,
                cron=cron,
                interval=interval,
                fire_immediately=False,
                model=None,
            )

        """With cron='0 9 * * *' at 08:00, next_fire_at should be ≈next 09:00, not now+60."""
        import time as _time
        # Pick a known reference time: 2026-01-01 08:00:00 UTC
        from datetime import datetime, timezone
        ref_ts = datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc).timestamp()
        expected_next_09 = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc).timestamp()

        captured = {}

        def fake_upsert(crew_id, entry):
            captured["entry"] = dict(entry)

        with (
            patch("transport.captain_engine._lc", return_value=self._fake_lc()),
            patch("transport.captain_engine._get_podman", return_value=self.podman),
            patch("transport.captain_engine._append_captain_mail"),
            patch("transport.captain_engine._delete_sentinel_file"),
            patch("transport.captain_engine.time") as mock_time,
            patch.object(_reg_mod, "_load_registry", return_value={"crews": {
                self.crew_id: self.crew_dict,
            }}),
            patch.object(_reg_mod, "_save_registry"),
            patch.object(registry, "upsert_schedule", side_effect=fake_upsert),
        ):
            mock_time.time.return_value = ref_ts
            registry._reg = {"crews": {self.crew_id: self.crew_dict}}
            from transport.captain_engine import _captain_do_order
            _captain_do_order(
                crew_id=self.crew_id,
                message="test order",
                template=None,
                change_name=None,
                cron="0 9 * * *",
                interval=None,
                timezone="UTC",
                fire_immediately=False,
                model=None,
            )

        self.assertIn("entry", captured, "upsert_schedule was not called")
        next_fire_at = captured["entry"].get("next_fire_at")
        self.assertIsNotNone(next_fire_at)
        # Should be close to 09:00, not now+60 (08:01)
        self.assertAlmostEqual(next_fire_at, expected_next_09, delta=5,
            msg=f"next_fire_at={next_fire_at} expected ~{expected_next_09} (09:00), "
                f"not ~{ref_ts + 60} (now+60)")

    def test_interval_still_uses_60s_initial_delay(self):
        """With interval=3600, next_fire_at should be now + 3600, not a cron tick."""
        import time as _time
        from datetime import datetime, timezone
        ref_ts = datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc).timestamp()

        captured = {}

        def fake_upsert(crew_id, entry):
            captured["entry"] = dict(entry)

        with (
            patch("transport.captain_engine._lc", return_value=self._fake_lc()),
            patch("transport.captain_engine._get_podman", return_value=self.podman),
            patch("transport.captain_engine._append_captain_mail"),
            patch("transport.captain_engine._delete_sentinel_file"),
            patch("transport.captain_engine.time") as mock_time,
            patch.object(_reg_mod, "_load_registry", return_value={"crews": {
                self.crew_id: self.crew_dict,
            }}),
            patch.object(_reg_mod, "_save_registry"),
            patch.object(registry, "upsert_schedule", side_effect=fake_upsert),
        ):
            mock_time.time.return_value = ref_ts
            registry._reg = {"crews": {self.crew_id: self.crew_dict}}
            from transport.captain_engine import _captain_do_order
            _captain_do_order(
                crew_id=self.crew_id,
                message="test order",
                template=None,
                change_name=None,
                cron=None,
                interval=3600,
                timezone="UTC",
                fire_immediately=False,
                model=None,
            )

        self.assertIn("entry", captured, "upsert_schedule was not called")
        next_fire_at = captured["entry"].get("next_fire_at")
        self.assertIsNotNone(next_fire_at)
        self.assertAlmostEqual(next_fire_at, ref_ts + 3600, delta=5,
            msg=f"next_fire_at={next_fire_at} expected ~{ref_ts + 3600} (now+3600)")


# ── M-4 _steer_captain_checkin httpx status-code classification ───────────────


class TestSteerCaptainCheckinHttpxErrors(unittest.TestCase):
    """_steer_captain_checkin: httpx.HTTPStatusError classification (TRN-285 M-4)."""

    def setUp(self):
        self.crew_id = "steer-crew"
        self.crew_dict = _fake_crew_dict(self.crew_id, running=True)
        self.crew_obj = _fake_crew_obj(self.crew_id, running=True)
        self.podman = FakePodmanClient()
        # Pre-populate a captain schedule entry with a task_id
        self._schedule = {
            "type": "captain",
            "crew_id": self.crew_id,
            "enabled": True,
            "job_id": None,
            "current_task_id": "task-abc",
            "model": None,
            "interval_secs": 3600,
            "cron_expr": None,
        }
        self.crew_dict_with_sched = dict(self.crew_dict)
        self.crew_dict_with_sched["schedules"] = [self._schedule]

    def _make_httpx_error(self, status_code: int, url_path: str):
        """Build a minimal httpx.HTTPStatusError with the given status and path."""
        response = MagicMock()
        response.status_code = status_code
        request = MagicMock()
        request.url.path = url_path
        return httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=request,
            response=response,
        )

    def _call_steer(self, api_side_effect):
        """Call _steer_captain_checkin with _crew_api_with_recovery raising api_side_effect."""
        import transport.captain_engine as _ce
        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = self.crew_dict_with_sched
        fake_lc._to_crew.return_value = self.crew_obj
        fake_lc._crew_api_with_recovery.side_effect = api_side_effect
        fake_lc._write_dashboard_cookie = MagicMock()

        with (
            patch("transport.captain_engine._lc", return_value=fake_lc),
            patch("transport.captain_engine._get_podman", return_value=self.podman),
            patch.object(_reg_mod, "_load_registry", return_value={"crews": {
                self.crew_id: self.crew_dict_with_sched,
            }}),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = {"crews": {self.crew_id: self.crew_dict_with_sched}}
            registry._reg["crews"][self.crew_id]["schedules"] = [dict(self._schedule)]
            from transport.captain_engine import _steer_captain_checkin
            return _steer_captain_checkin(self.crew_dict_with_sched, self.crew_id)

    def test_400_on_continue_triggers_redispatch(self):
        """HTTPStatusError 400 on /continue triggers steer fallback (re-dispatch)."""
        exc = self._make_httpx_error(400, f"/api/spawn/task-abc/continue")
        new_task_id = "new-task-id"

        # On re-dispatch (after 400), _dispatch_captain_checkin will call
        # _crew_api_with_recovery again; make it succeed for the re-dispatch.
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise exc  # first call: raise 400
            # second call: return a new task
            return {"id": new_task_id}

        fake_lc = MagicMock()
        fake_lc._require_crew.return_value = self.crew_dict_with_sched
        fake_lc._to_crew.return_value = self.crew_obj
        fake_lc._crew_api_with_recovery.side_effect = side_effect
        fake_lc._write_dashboard_cookie = MagicMock()

        with (
            patch("transport.captain_engine._lc", return_value=fake_lc),
            patch("transport.captain_engine._get_podman", return_value=self.podman),
            patch("transport.captain_engine._check_in_memory_pressure", return_value=None),
            patch.object(_reg_mod, "_load_registry", return_value={"crews": {
                self.crew_id: self.crew_dict_with_sched,
            }}),
            patch.object(_reg_mod, "_save_registry"),
        ):
            registry._reg = {"crews": {self.crew_id: self.crew_dict_with_sched}}
            registry._reg["crews"][self.crew_id]["schedules"] = [dict(self._schedule)]
            # Enroll raven so dispatch does not fail enrollment check
            registry._reg["crews"][self.crew_id]["enrolled_agents"] = ["raven"]
            from transport.captain_engine import _steer_captain_checkin
            result = _steer_captain_checkin(self.crew_dict_with_sched, self.crew_id)

        # Should have returned the new task id (re-dispatched)
        self.assertEqual(result, new_task_id)
        self.assertEqual(call_count[0], 2)  # first call raised, second succeeded

    def test_500_on_continue_is_propagated(self):
        """HTTPStatusError 500 is NOT treated as continue-400; it propagates."""
        exc = self._make_httpx_error(500, "/api/spawn/task-abc/continue")

        with self.assertRaises(httpx.HTTPStatusError) as cm:
            self._call_steer(api_side_effect=exc)

        self.assertEqual(cm.exception.response.status_code, 500)
