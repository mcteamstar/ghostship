"""Unit tests for transport/monitors.py (TRN-249).

Covers:
- _cron_activity_since: branch coverage of all active/inactive/edge cases
- _cron_has_enabled_job: branch coverage of enabled/disabled/edge cases
- _note_idle_skip: deduplication — logs once on first/changed reason, not on repeat
- _schedule_monitor iteration: due/not-due, disabled, captain-skip, gateway-sync,
  one-shot teardown, _ensure_crew_running failure, gateway fetch failure (fail-open)
- _idle_monitor iteration: active tasks, cron hold, captain schedule hold, cookie
  refresh, TOCTOU guard, _stopping flag lifecycle, skip conditions
- _captain_monitor iteration: sentinel auto-pause, due/not-due, _ensure_crew_running
  failure, skip on disabled

All tests use FakePodmanClient — no unittest.mock.Mock() for Podman calls.
bind_lifecycle() stubs are set in setUp for each test class.
Registry state is provided by patching _load_registry to return controlled data.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

import transport.monitors as monitors
import transport.registry as _reg_mod
from tests.fakes import FakePodmanClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_stub_lifecycle(**overrides):
    """Return keyword args suitable for monitors.bind_lifecycle()."""
    defaults = dict(
        ga_idle_timeout_secs=300.0,
        schedule_monitor_interval=30,
        ensure_crew_running=MagicMock(return_value={"container": "gs-abc", "cookie": "tok"}),
        crew_api=MagicMock(return_value={"jobs": []}),
        crew_api_with_recovery=MagicMock(),
        mint_cookie=MagicMock(return_value=None),
    )
    defaults.update(overrides)
    return defaults


def _make_reg(crews: dict) -> dict:
    """Build a registry dict with the given crews."""
    return {"crews": crews}


# ── Task 1.1: TestCronActivityHelpers ────────────────────────────────────────


class TestCronActivityHelpers(unittest.TestCase):
    """_cron_activity_since: branch coverage."""

    def setUp(self):
        self.last_used = 1000.0

    def test_is_running_true_returns_true(self):
        payload = {"jobs": [{"is_running": True}]}
        self.assertTrue(monitors._cron_activity_since(payload, self.last_used))

    def test_running_since_newer_than_last_used_returns_true(self):
        payload = {"jobs": [{"is_running": False, "running_since": self.last_used + 10}]}
        self.assertTrue(monitors._cron_activity_since(payload, self.last_used))

    def test_last_run_ts_newer_than_last_used_returns_true(self):
        payload = {"jobs": [{"last_run_ts": self.last_used + 5}]}
        self.assertTrue(monitors._cron_activity_since(payload, self.last_used))

    def test_all_timestamps_older_not_running_returns_false(self):
        payload = {"jobs": [{"is_running": False, "last_run_ts": self.last_used - 1, "running_since": self.last_used - 2}]}
        self.assertFalse(monitors._cron_activity_since(payload, self.last_used))

    def test_empty_jobs_list_returns_false(self):
        payload = {"jobs": []}
        self.assertFalse(monitors._cron_activity_since(payload, self.last_used))

    def test_non_dict_payload_returns_false(self):
        self.assertFalse(monitors._cron_activity_since("not-a-dict", self.last_used))
        self.assertFalse(monitors._cron_activity_since(None, self.last_used))
        self.assertFalse(monitors._cron_activity_since([], self.last_used))

    def test_non_dict_job_entry_skipped(self):
        payload = {"jobs": ["not-a-dict", None, 42]}
        self.assertFalse(monitors._cron_activity_since(payload, self.last_used))

    def test_bool_timestamps_ignored(self):
        """bool is a subclass of int/float — must not be treated as a timestamp."""
        payload = {"jobs": [{"last_run_ts": True}]}
        self.assertFalse(monitors._cron_activity_since(payload, self.last_used))


# ── Task 1.2: TestCronHasEnabledJob ──────────────────────────────────────────


class TestCronHasEnabledJob(unittest.TestCase):
    """_cron_has_enabled_job: branch coverage."""

    def test_at_least_one_enabled_returns_true(self):
        payload = {"jobs": [{"enabled": True}]}
        self.assertTrue(monitors._cron_has_enabled_job(payload))

    def test_all_disabled_returns_false(self):
        payload = {"jobs": [{"enabled": False}, {"enabled": False}]}
        self.assertFalse(monitors._cron_has_enabled_job(payload))

    def test_enabled_missing_returns_false(self):
        payload = {"jobs": [{"name": "job1"}]}
        self.assertFalse(monitors._cron_has_enabled_job(payload))

    def test_empty_list_returns_false(self):
        payload = {"jobs": []}
        self.assertFalse(monitors._cron_has_enabled_job(payload))

    def test_non_dict_payload_returns_false(self):
        self.assertFalse(monitors._cron_has_enabled_job("not-a-dict"))
        self.assertFalse(monitors._cron_has_enabled_job(None))
        self.assertFalse(monitors._cron_has_enabled_job([]))

    def test_non_dict_job_entry_skipped(self):
        payload = {"jobs": ["not-a-dict", {"enabled": True}]}
        self.assertTrue(monitors._cron_has_enabled_job(payload))

    def test_mixed_enabled_returns_true(self):
        payload = {"jobs": [{"enabled": False}, {"enabled": True}]}
        self.assertTrue(monitors._cron_has_enabled_job(payload))


# ── Task 2.1: TestNoteIdleSkip ────────────────────────────────────────────────


class TestNoteIdleSkip(unittest.TestCase):
    """_note_idle_skip: deduplication of idle-skip log messages."""

    def setUp(self):
        monitors._idle_skip_reasons.clear()

    def tearDown(self):
        monitors._idle_skip_reasons.clear()

    def test_first_call_logs_at_info(self):
        with self.assertLogs("transport.lifecycle", level="INFO") as cm:
            monitors._note_idle_skip("crew-1", "tasks running")
        self.assertTrue(any("crew-1" in line and "tasks running" in line for line in cm.output))

    def test_second_call_same_reason_no_log(self):
        # First call must log
        monitors._note_idle_skip("crew-1", "tasks running")
        # Capture any new logs during the second call — none should appear.
        # We verify by checking _idle_skip_reasons is set correctly and
        # rely on the fact that assertLogs raises if nothing is logged.
        with self.assertRaises(AssertionError):
            with self.assertLogs("transport.lifecycle", level="INFO"):
                monitors._note_idle_skip("crew-1", "tasks running")

    def test_second_call_different_reason_logs(self):
        monitors._note_idle_skip("crew-1", "tasks running")
        with self.assertLogs("transport.lifecycle", level="INFO") as cm:
            monitors._note_idle_skip("crew-1", "cron job enabled or recently ran")
        self.assertTrue(any("crew-1" in line for line in cm.output))

    def test_different_crew_always_logs(self):
        monitors._note_idle_skip("crew-1", "tasks running")
        with self.assertLogs("transport.lifecycle", level="INFO") as cm:
            monitors._note_idle_skip("crew-2", "tasks running")
        self.assertTrue(any("crew-2" in line for line in cm.output))


# ── Task 3.x: TestScheduleMonitorIteration ───────────────────────────────────


class TestScheduleMonitorIteration(unittest.TestCase):
    """_schedule_monitor iteration: single-tick body logic."""

    CREW_ID = "crew-abc"
    CONTAINER = "gs-crew-abc"
    NOW = 5000.0

    def _make_crew_entry(self, schedules=None, **kwargs):
        entry = {
            "container": self.CONTAINER,
            "cookie": "tok",
            "status": "running",
            "last_used": self.NOW - 400,
        }
        entry.update(kwargs)
        if schedules is not None:
            entry["schedules"] = schedules
        return entry

    def _make_sched(self, **kwargs):
        base = {
            "job_id": "job-1",
            "enabled": True,
            "next_fire_at": self.NOW - 10,
            "interval_secs": 60,
            "message": "tick",
            "agent": "ghost",
        }
        base.update(kwargs)
        return base

    def setUp(self):
        stubs = _make_stub_lifecycle()
        self._ensure = stubs["ensure_crew_running"]
        self._crew_api = stubs["crew_api"]
        self._crew_api_with_recovery = stubs["crew_api_with_recovery"]
        monitors.bind_lifecycle(**stubs)

    def tearDown(self):
        monitors._idle_skip_reasons.clear()

    def _run_one_tick(self, crews):
        """Run exactly one schedule-monitor body iteration.

        _schedule_monitor sleeps at the TOP of its while loop before running the
        body. We must let the first sleep return normally (the interval wait) and
        only raise StopIteration on the second sleep (the next interval) so the
        body between them executes exactly once.

        Patches:
        - time.sleep: returns None on call 1, raises StopIteration on call 2
        - time.time:  returns self.NOW
        - _load_registry: returns our scripted registry
        - _save_registry: no-op
        """
        reg = _make_reg(crews)

        with patch.object(monitors.time, "sleep", side_effect=[None, StopIteration()]), \
             patch.object(monitors.time, "time", return_value=self.NOW), \
             patch.object(_reg_mod, "_load_registry", return_value=reg), \
             patch.object(_reg_mod, "_save_registry"):
            try:
                monitors._schedule_monitor()
            except StopIteration:
                pass

    def test_due_job_calls_crew_api_with_recovery_post(self):
        """Due job → _crew_api_with_recovery called with POST /api/spawn."""
        sched = self._make_sched()
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(schedules=[sched])})
        self._crew_api_with_recovery.assert_called()
        # Verify it was POST /api/spawn
        found_post = any(
            "POST" in str(c) and "/api/spawn" in str(c)
            for c in self._crew_api_with_recovery.call_args_list
        )
        self.assertTrue(found_post)

    def test_due_job_advances_next_fire_at(self):
        """Due job that fires → next_fire_at advances beyond now."""
        sched = self._make_sched()
        old_nfa = sched["next_fire_at"]
        reg = _make_reg({self.CREW_ID: self._make_crew_entry(schedules=[sched])})
        with patch.object(monitors.time, "sleep", side_effect=[None, StopIteration()]), \
             patch.object(monitors.time, "time", return_value=self.NOW), \
             patch.object(_reg_mod, "_load_registry", return_value=reg), \
             patch.object(_reg_mod, "_save_registry"):
            try:
                monitors._schedule_monitor()
            except StopIteration:
                pass
        # _advance_next_fire_at mutates the sched in the reg dict
        live_scheds = reg["crews"][self.CREW_ID].get("schedules", [])
        live_sched = next((s for s in live_scheds if s.get("job_id") == "job-1"), sched)
        self.assertGreater(live_sched["next_fire_at"], old_nfa)

    def test_not_yet_due_job_not_fired(self):
        """next_fire_at in future → _crew_api_with_recovery not called."""
        sched = self._make_sched(next_fire_at=self.NOW + 9999)
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(schedules=[sched])})
        self._crew_api_with_recovery.assert_not_called()

    def test_disabled_job_skipped(self):
        """enabled=False → _crew_api_with_recovery not called."""
        sched = self._make_sched(enabled=False)
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(schedules=[sched])})
        self._crew_api_with_recovery.assert_not_called()

    def test_captain_type_job_skipped(self):
        """type==captain → _crew_api_with_recovery not called."""
        sched = self._make_sched(type="captain")
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(schedules=[sched])})
        self._crew_api_with_recovery.assert_not_called()

    def test_ensure_crew_running_raises_advances_next_fire_at(self):
        """_ensure_crew_running raises → next_fire_at advanced, no spawn call."""
        self._ensure.side_effect = RuntimeError("container dead")
        sched = self._make_sched()
        old_nfa = sched["next_fire_at"]
        reg = _make_reg({self.CREW_ID: self._make_crew_entry(schedules=[sched])})
        with patch.object(monitors.time, "sleep", side_effect=[None, StopIteration()]), \
             patch.object(monitors.time, "time", return_value=self.NOW), \
             patch.object(_reg_mod, "_load_registry", return_value=reg), \
             patch.object(_reg_mod, "_save_registry"):
            try:
                monitors._schedule_monitor()
            except StopIteration:
                pass
        self._crew_api_with_recovery.assert_not_called()
        live_scheds = reg["crews"][self.CREW_ID].get("schedules", [])
        live_sched = next((s for s in live_scheds if s.get("job_id") == "job-1"), sched)
        self.assertGreater(live_sched["next_fire_at"], old_nfa)

    def test_gateway_disabled_job_sets_registry_disabled(self):
        """Gateway returns job with enabled=false → registry entry disabled, no spawn."""
        self._crew_api.return_value = {"jobs": [{"id": "job-1", "enabled": False}]}
        sched = self._make_sched(job_id="job-1")
        reg = _make_reg({self.CREW_ID: self._make_crew_entry(schedules=[sched])})

        # We need _load_registry to return the same reg object so mutations land
        with patch.object(monitors.time, "sleep", side_effect=[None, StopIteration()]), \
             patch.object(monitors.time, "time", return_value=self.NOW), \
             patch.object(_reg_mod, "_load_registry", return_value=reg), \
             patch.object(_reg_mod, "_save_registry"):
            try:
                monitors._schedule_monitor()
            except StopIteration:
                pass

        self._crew_api_with_recovery.assert_not_called()
        crew_scheds = reg["crews"][self.CREW_ID].get("schedules", [])
        disabled = [s for s in crew_scheds if s.get("job_id") == "job-1" and not s.get("enabled", True)]
        self.assertTrue(len(disabled) >= 1)

    def test_gateway_fetch_raises_fail_open_spawns(self):
        """Gateway fetch raises → fail-open, spawn still called."""
        self._crew_api.side_effect = RuntimeError("gateway unreachable")
        sched = self._make_sched()
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(schedules=[sched])})
        self._crew_api_with_recovery.assert_called()

    def test_one_shot_job_sets_registry_disabled_and_never_fire_at(self):
        """one_shot=True job fires → registry entry enabled=False, next_fire_at=_NEVER_FIRE_AT."""
        sched = self._make_sched(one_shot=True, job_id="oneshot-1")
        reg = _make_reg({self.CREW_ID: self._make_crew_entry(schedules=[sched])})

        with patch.object(monitors.time, "sleep", side_effect=[None, StopIteration()]), \
             patch.object(monitors.time, "time", return_value=self.NOW), \
             patch.object(_reg_mod, "_load_registry", return_value=reg), \
             patch.object(_reg_mod, "_save_registry"):
            try:
                monitors._schedule_monitor()
            except StopIteration:
                pass

        crew_scheds = reg["crews"][self.CREW_ID].get("schedules", [])
        oneshot = next((s for s in crew_scheds if s.get("job_id") == "oneshot-1"), None)
        self.assertIsNotNone(oneshot)
        self.assertFalse(oneshot.get("enabled", True))
        self.assertEqual(oneshot.get("next_fire_at"), _reg_mod._NEVER_FIRE_AT)

    def test_one_shot_job_calls_delete_on_gateway(self):
        """one_shot=True job fires → _crew_api_with_recovery called with DELETE /api/crons/<id>."""
        sched = self._make_sched(one_shot=True, job_id="oneshot-1")
        reg = _make_reg({self.CREW_ID: self._make_crew_entry(schedules=[sched])})

        with patch.object(monitors.time, "sleep", side_effect=[None, StopIteration()]), \
             patch.object(monitors.time, "time", return_value=self.NOW), \
             patch.object(_reg_mod, "_load_registry", return_value=reg), \
             patch.object(_reg_mod, "_save_registry"):
            try:
                monitors._schedule_monitor()
            except StopIteration:
                pass

        delete_calls = [
            c for c in self._crew_api_with_recovery.call_args_list
            if "DELETE" in c.args
        ]
        self.assertTrue(len(delete_calls) >= 1)
        self.assertTrue(any("/api/crons/oneshot-1" in str(c) for c in delete_calls))


# ── Task 4.x: TestIdleMonitorIteration ───────────────────────────────────────


class _MockResponse:
    """Minimal HTTP response double."""
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data if data is not None else {}

    def json(self):
        return self._data


class _FakeHTTPModule:
    """Replaces monitors._http with scripted GET responses."""

    def __init__(self):
        self._responses = {}  # url-substring → _MockResponse
        self._calls = []

    def script(self, url_contains, response):
        self._responses[url_contains] = response

    def get(self, url, **kwargs):
        self._calls.append(url)
        for key, resp in self._responses.items():
            if key in url:
                return resp
        return _MockResponse(200, {})


class TestIdleMonitorIteration(unittest.TestCase):
    """_idle_monitor iteration: single-tick body logic."""

    CREW_ID = "crew-idle"
    CONTAINER = "gs-crew-idle"
    NOW = 2000.0  # fixed "now"

    def _make_crew_entry(self, **kwargs):
        entry = {
            "container": self.CONTAINER,
            "cookie": "tok",
            "status": "running",
            "last_used": self.NOW - 400,  # past idle timeout (300s)
            "schedules": [],
        }
        entry.update(kwargs)
        return entry

    def setUp(self):
        stubs = _make_stub_lifecycle(ga_idle_timeout_secs=300.0)
        self._mint_cookie = stubs["mint_cookie"]
        monitors.bind_lifecycle(**stubs)
        # FakePodmanClient with the crew container running
        self._podman = FakePodmanClient()
        self._podman.add_container(self.CONTAINER, running=True)
        # Default HTTP stubs: no active tasks, no cron jobs
        self._http = _FakeHTTPModule()
        self._http.script(
            "/api/spawn",
            _MockResponse(200, {"agents": [{"done": True}]}),
        )
        self._http.script(
            "/api/crons",
            _MockResponse(200, {"jobs": []}),
        )
        monitors._idle_skip_reasons.clear()

    def tearDown(self):
        monitors._idle_skip_reasons.clear()

    def _run_one_tick(self, crews):
        """Run exactly one idle-monitor body iteration.

        _idle_monitor sleeps at the TOP of its while loop before running the body.
        Let the first sleep return normally; raise StopIteration on the second.

        Sets self._mock_touch and self._last_reg for post-run inspection.
        """
        reg = _make_reg(crews)

        with patch.object(monitors.time, "sleep", side_effect=[None, StopIteration()]), \
             patch.object(monitors.time, "time", return_value=self.NOW), \
             patch.object(monitors, "_get_podman", return_value=self._podman), \
             patch.object(monitors, "_http", self._http), \
             patch.object(monitors, "_touch_crew") as mock_touch, \
             patch.object(_reg_mod, "_load_registry", return_value=reg), \
             patch.object(_reg_mod, "_save_registry"):
            self._mock_touch = mock_touch
            self._last_reg = reg
            try:
                monitors._idle_monitor()
            except StopIteration:
                pass

    def test_active_task_not_stopped_touch_called(self):
        """Crew with active task (done=False in /api/spawn) → container_stop not called, _touch_crew called."""
        self._http.script(
            "/api/spawn",
            _MockResponse(200, {"agents": [{"done": False}]}),
        )
        self._run_one_tick({self.CREW_ID: self._make_crew_entry()})
        self.assertFalse(self._podman.was_called("container_stop"))
        self._mock_touch.assert_called_with(self.CREW_ID)

    def test_cron_enabled_not_stopped(self):
        """/api/crons returns a job with enabled=True → container_stop not called."""
        self._http.script(
            "/api/crons",
            _MockResponse(200, {"jobs": [{"enabled": True}]}),
        )
        self._run_one_tick({self.CREW_ID: self._make_crew_entry()})
        self.assertFalse(self._podman.was_called("container_stop"))

    def test_cron_recent_last_run_ts_not_stopped(self):
        """job last_run_ts more recent than last_used → container_stop not called."""
        entry = self._make_crew_entry()
        last_used = entry["last_used"]
        self._http.script(
            "/api/crons",
            _MockResponse(200, {"jobs": [{"last_run_ts": last_used + 10}]}),
        )
        self._run_one_tick({self.CREW_ID: entry})
        self.assertFalse(self._podman.was_called("container_stop"))

    def test_no_active_tasks_no_cron_stops_container(self):
        """No active tasks and no cron jobs → container_stop called, status set to 'stopped'."""
        entry = self._make_crew_entry()
        self._run_one_tick({self.CREW_ID: entry})
        self.assertTrue(self._podman.was_called("container_stop"))
        # Verify status was updated in the registry
        status = self._last_reg["crews"].get(self.CREW_ID, {}).get("status")
        self.assertEqual(status, "stopped")

    def test_container_not_running_skip(self):
        """Container not running → container_stop not called."""
        self._podman = FakePodmanClient()
        self._podman.add_container(self.CONTAINER, running=False)
        self._run_one_tick({self.CREW_ID: self._make_crew_entry()})
        self.assertFalse(self._podman.was_called("container_stop"))

    def test_auth_required_status_skipped(self):
        """status=='auth_required' → skipped entirely, container_stop not called."""
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(status="auth_required")})
        self.assertFalse(self._podman.was_called("container_stop"))

    def test_within_idle_timeout_not_stopped(self):
        """last_used within GA_IDLE_TIMEOUT_SECS → not stopped."""
        # last_used only 10s ago, timeout is 300s
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(last_used=self.NOW - 10)})
        self.assertFalse(self._podman.was_called("container_stop"))

    def test_spawn_401_mint_cookie_succeeds_retries(self):
        """/api/spawn returns 401 AND _mint_cookie returns new cookie → request retried."""
        responses = {"calls": 0}

        def patched_get(url, **kwargs):
            if "/api/spawn" in url:
                responses["calls"] += 1
                if responses["calls"] == 1:
                    return _MockResponse(401)
                return _MockResponse(200, {"agents": []})
            return _MockResponse(200, {"jobs": []})

        self._http.get = patched_get
        self._mint_cookie.return_value = "new-cookie-value"
        monitors.bind_lifecycle(**_make_stub_lifecycle(
            ga_idle_timeout_secs=300.0,
            mint_cookie=self._mint_cookie,
        ))
        self._run_one_tick({self.CREW_ID: self._make_crew_entry()})
        # Should have attempted at least 2 spawn calls (original + retry)
        self.assertGreaterEqual(responses["calls"], 2)

    def test_spawn_401_mint_cookie_returns_none_fail_open(self):
        """/api/spawn returns 401 AND _mint_cookie returns None → fail-open, no stop."""
        self._http.script("/api/spawn", _MockResponse(401))
        self._mint_cookie.return_value = None
        monitors.bind_lifecycle(**_make_stub_lifecycle(
            ga_idle_timeout_secs=300.0,
            mint_cookie=self._mint_cookie,
        ))
        self._run_one_tick({self.CREW_ID: self._make_crew_entry()})
        self.assertFalse(self._podman.was_called("container_stop"))

    def test_crons_401_mint_cookie_succeeds_retries(self):
        """/api/crons returns 401 AND _mint_cookie returns new cookie → request retried."""
        responses = {"cron_calls": 0}

        def patched_get(url, **kwargs):
            if "/api/crons" in url:
                responses["cron_calls"] += 1
                if responses["cron_calls"] == 1:
                    return _MockResponse(401)
                return _MockResponse(200, {"jobs": []})
            # spawn: no active tasks
            return _MockResponse(200, {"agents": []})

        self._http.get = patched_get
        self._mint_cookie.return_value = "new-cookie-value"
        monitors.bind_lifecycle(**_make_stub_lifecycle(
            ga_idle_timeout_secs=300.0,
            mint_cookie=self._mint_cookie,
        ))
        self._run_one_tick({self.CREW_ID: self._make_crew_entry()})
        self.assertGreaterEqual(responses["cron_calls"], 2)

    def test_crons_401_mint_cookie_returns_none_fail_open(self):
        """/api/crons returns 401 AND _mint_cookie returns None → fail-open, no stop."""
        self._http.script("/api/crons", _MockResponse(401))
        self._mint_cookie.return_value = None
        monitors.bind_lifecycle(**_make_stub_lifecycle(
            ga_idle_timeout_secs=300.0,
            mint_cookie=self._mint_cookie,
        ))
        self._run_one_tick({self.CREW_ID: self._make_crew_entry()})
        self.assertFalse(self._podman.was_called("container_stop"))

    def test_captain_schedule_hold_not_stopped(self):
        """Registry entry has captain-type schedule enabled + next_fire_at < _NEVER_FIRE_AT → no stop, _touch_crew called."""
        captain_sched = {
            "type": "captain",
            "enabled": True,
            "next_fire_at": self.NOW + 60,  # real schedule, not _NEVER_FIRE_AT
        }
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(schedules=[captain_sched])})
        self.assertFalse(self._podman.was_called("container_stop"))
        self._mock_touch.assert_called_with(self.CREW_ID)

    def test_toctou_guard_prevents_stop(self):
        """TOCTOU guard: if last_used < GA_IDLE_TIMEOUT_SECS from now inside the lock → container_stop not called."""
        # Set last_used to right at NOW so idle_secs == 0 < 300
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(last_used=self.NOW)})
        self.assertFalse(self._podman.was_called("container_stop"))

    def test_toctou_inlock_guard_prevents_stop(self):
        """In-lock TOCTOU re-check: last_used advanced to now between the early check and the lock.

        The idle monitor performs an early-out check (idle_secs < GA_IDLE_TIMEOUT_SECS)
        before HTTP calls.  A separate, in-lock re-check at the stop gate (line 547 of
        monitors.py) re-reads last_used from the registry under the lock so that a
        concurrent _touch_crew that lands during the HTTP-check window is honoured.

        This test simulates that race: the first _load_registry call (crew_items
        snapshot) returns an entry with last_used far in the past (passes the
        early-out); the second _load_registry call (inside the TOCTOU lock block)
        returns an entry with last_used == NOW (fresh touch just arrived).
        container_stop must NOT be called.
        """
        old_entry = self._make_crew_entry()          # last_used = NOW - 400, passes early-out
        refreshed_entry = self._make_crew_entry(last_used=self.NOW)  # touched during checks

        call_count = [0]
        old_reg = _make_reg({self.CREW_ID: old_entry})
        refreshed_reg = _make_reg({self.CREW_ID: refreshed_entry})

        def scripted_load():
            call_count[0] += 1
            # First call: crew_items snapshot (passes early idle check)
            if call_count[0] == 1:
                return old_reg
            # Subsequent calls (TOCTOU lock block + write-back): refreshed last_used
            return refreshed_reg

        with patch.object(monitors.time, "sleep", side_effect=[None, StopIteration()]), \
             patch.object(monitors.time, "time", return_value=self.NOW), \
             patch.object(monitors, "_get_podman", return_value=self._podman), \
             patch.object(monitors, "_http", self._http), \
             patch.object(monitors, "_touch_crew"), \
             patch.object(_reg_mod, "_load_registry", side_effect=scripted_load), \
             patch.object(_reg_mod, "_save_registry"):
            try:
                monitors._idle_monitor()
            except StopIteration:
                pass

        self.assertFalse(self._podman.was_called("container_stop"))

    def test_stopping_flag_prevents_double_stop(self):
        """_stopping=True pre-set → container_stop not called."""
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(_stopping=True)})
        self.assertFalse(self._podman.was_called("container_stop"))

    def test_successful_stop_clears_stopping_and_sets_status(self):
        """After successful container_stop → _stopping removed, status=='stopped'."""
        entry = self._make_crew_entry()
        self._run_one_tick({self.CREW_ID: entry})
        live = self._last_reg["crews"].get(self.CREW_ID, {})
        self.assertNotIn("_stopping", live)
        self.assertEqual(live.get("status"), "stopped")

    def test_container_stop_raises_clears_stopping_no_status_change(self):
        """container_stop raises → _stopping cleared, status NOT changed to 'stopped'."""
        # Script container_stop to raise
        original_stop = self._podman.container_stop

        def raising_stop(name):
            original_stop(name)
            raise RuntimeError("stop timeout")

        self._podman.container_stop = raising_stop

        entry = self._make_crew_entry(status="running")
        self._run_one_tick({self.CREW_ID: entry})

        live = self._last_reg["crews"].get(self.CREW_ID, {})
        self.assertNotIn("_stopping", live)
        self.assertNotEqual(live.get("status"), "stopped")


# ── Task 5.x: TestCaptainMonitorIteration ────────────────────────────────────


class TestCaptainMonitorIteration(unittest.TestCase):
    """_captain_monitor iteration: single-tick body logic."""

    CREW_ID = "crew-cap"
    CONTAINER = "gs-crew-cap"
    NOW = 3000.0

    def _make_crew_entry(self, schedules=None, **kwargs):
        entry = {
            "container": self.CONTAINER,
            "cookie": "tok",
            "status": "running",
            "last_used": self.NOW - 100,
        }
        entry.update(kwargs)
        entry["schedules"] = schedules if schedules is not None else []
        return entry

    def _make_captain_sched(self, **kwargs):
        base = {
            "type": "captain",
            "enabled": True,
            "next_fire_at": self.NOW - 5,
            "interval_secs": 3600,
        }
        base.update(kwargs)
        return base

    def setUp(self):
        stubs = _make_stub_lifecycle()
        self._ensure = stubs["ensure_crew_running"]
        monitors.bind_lifecycle(**stubs)

        # TRN-242: _steer_captain_checkin / _dispatch_captain_checkin are now
        # imported at monitors module top from captain_engine (no longer a
        # call-time import from server), so patch them on the monitors module.
        self._fake_steer = MagicMock()
        self._orig_steer = monitors._steer_captain_checkin
        self._orig_dispatch = monitors._dispatch_captain_checkin
        monitors._steer_captain_checkin = self._fake_steer
        monitors._dispatch_captain_checkin = MagicMock()

        # FakePodmanClient (no sentinel by default)
        self._podman = FakePodmanClient()
        self._podman.add_container(self.CONTAINER, running=True)

        monitors._idle_skip_reasons.clear()

    def tearDown(self):
        monitors._steer_captain_checkin = self._orig_steer
        monitors._dispatch_captain_checkin = self._orig_dispatch
        monitors._idle_skip_reasons.clear()

    def _run_one_tick(self, crews):
        """Run exactly one captain-monitor body iteration."""
        reg = _make_reg(crews)
        call_count = [0]

        def fake_sleep(n):
            call_count[0] += 1
            if call_count[0] >= 1:
                raise StopIteration

        with patch.object(monitors.time, "sleep", side_effect=fake_sleep), \
             patch.object(monitors.time, "time", return_value=self.NOW), \
             patch.object(monitors, "_get_podman", return_value=self._podman), \
             patch.object(_reg_mod, "_load_registry", return_value=reg), \
             patch.object(_reg_mod, "_save_registry"):
            self._last_reg = reg
            try:
                monitors._captain_monitor()
            except StopIteration:
                pass

    def test_due_entry_calls_steer_captain_checkin(self):
        """Due captain entry, no sentinel → _steer_captain_checkin called, next_fire_at advanced."""
        sched = self._make_captain_sched()
        old_nfa = sched["next_fire_at"]
        crews = {self.CREW_ID: self._make_crew_entry(schedules=[sched])}
        self._run_one_tick(crews)
        self._fake_steer.assert_called()
        live_scheds = self._last_reg["crews"].get(self.CREW_ID, {}).get("schedules", [])
        live_sched = next((s for s in live_scheds if s.get("type") == "captain"), sched)
        self.assertGreater(live_sched["next_fire_at"], old_nfa)

    def test_not_yet_due_not_called(self):
        """next_fire_at in future → _steer_captain_checkin not called."""
        sched = self._make_captain_sched(next_fire_at=self.NOW + 9999)
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(schedules=[sched])})
        self._fake_steer.assert_not_called()

    def test_disabled_entry_skipped(self):
        """enabled=False → _steer_captain_checkin not called."""
        sched = self._make_captain_sched(enabled=False)
        self._run_one_tick({self.CREW_ID: self._make_crew_entry(schedules=[sched])})
        self._fake_steer.assert_not_called()

    def test_sentinel_auto_pause(self):
        """Sentinel present → schedule entry enabled=False, _steer_captain_checkin not called."""
        SENTINEL_PATH = "/home/kirocrew/workplace/kirocrew-workspace/.captain_done"
        self._podman.set_archive_file(
            self.CONTAINER,
            SENTINEL_PATH,
            b"captain_id=crew-cap\ncompleted_at=2026-10-15T00:00:00Z\n",
            filename=".captain_done",
        )
        sched = self._make_captain_sched()
        crews = {self.CREW_ID: self._make_crew_entry(schedules=[sched])}
        self._run_one_tick(crews)
        self._fake_steer.assert_not_called()
        # Schedule should be disabled in the registry dict
        live_scheds = self._last_reg["crews"].get(self.CREW_ID, {}).get("schedules", [])
        cap_sched = next((s for s in live_scheds if s.get("type") == "captain"), None)
        self.assertIsNotNone(cap_sched)
        self.assertFalse(cap_sched.get("enabled", True))

    def test_ensure_crew_running_raises_advances_next_fire_at(self):
        """_ensure_crew_running raises → next_fire_at advanced, _steer_captain_checkin not called."""
        self._ensure.side_effect = RuntimeError("container dead")
        sched = self._make_captain_sched()
        old_nfa = sched["next_fire_at"]
        crews = {self.CREW_ID: self._make_crew_entry(schedules=[sched])}
        self._run_one_tick(crews)
        self._fake_steer.assert_not_called()
        live_scheds = self._last_reg["crews"].get(self.CREW_ID, {}).get("schedules", [])
        live_sched = next((s for s in live_scheds if s.get("type") == "captain"), sched)
        self.assertGreater(live_sched["next_fire_at"], old_nfa)


# ── Task 6.1: Integration check (regression guard) ────────────────────────────


class TestNoRegressions(unittest.TestCase):
    """Smoke test: confirm all helper functions are importable and functional."""

    def test_cron_activity_since_basic(self):
        self.assertTrue(monitors._cron_activity_since({"jobs": [{"is_running": True}]}, 0.0))
        self.assertFalse(monitors._cron_activity_since({"jobs": []}, 0.0))

    def test_cron_has_enabled_job_basic(self):
        self.assertTrue(monitors._cron_has_enabled_job({"jobs": [{"enabled": True}]}))
        self.assertFalse(monitors._cron_has_enabled_job({"jobs": []}))

    def test_bind_lifecycle_callable(self):
        stubs = _make_stub_lifecycle()
        monitors.bind_lifecycle(**stubs)
        self.assertIs(monitors._ensure_crew_running, stubs["ensure_crew_running"])


if __name__ == "__main__":
    unittest.main()
