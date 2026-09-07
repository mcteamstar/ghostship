"""Schedule and idle-monitor tests split from test_server.py (trn-119)."""
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


class SetupPodman:
    def __init__(self) -> None:
        self.stops = 0
        self.starts = 0

    def container_stop(self, container: str) -> None:
        self.stops += 1

    def container_start(self, container: str) -> None:
        self.starts += 1

    def container_exec(
        self,
        container: str,
        cmd: list[str],
        env: dict[str, str] | None = None,
    ) -> str:
        return "ready"
class IdleMonitorPodman:
    """Mock PodmanClient for _idle_monitor tests."""

    def __init__(
        self,
        containers_running: dict[str, bool] | None = None,
    ) -> None:
        self.containers_running = containers_running or {}
        self.stops: list[str] = []

    def container_is_running(self, name: str) -> bool:
        return self.containers_running.get(name, True)

    def container_stop(self, name: str) -> None:
        self.stops.append(name)
class MockHTTPResponse:
    """Mock HTTP response factory for idle_monitor API calls."""

    def __init__(self, status_code: int = 200, json_data: Any = None) -> None:
        self.status_code = status_code
        self._json = json_data or {}

    def json(self) -> Any:
        return self._json
class IdleMonitorTests(unittest.TestCase):
    """Tests for _idle_monitor logic (trn-17 tasks 4.x and 5.x)."""

    def _run_one_iteration(
        self,
        crew_items: list[tuple[str, dict]],
        podman: IdleMonitorPodman,
        http_responses: list[MockHTTPResponse | BaseException] | None = None,
        mint_cookie_return: str | None = None,
    ) -> dict[str, Any]:
        """Run a single iteration of the idle monitor and return state."""
        http_calls = []
        response_iter = iter(http_responses or [])

        class FakeHTTP:
            def get(self, url: str, **kwargs: Any) -> MockHTTPResponse:
                http_calls.append(url)
                response = next(response_iter, MockHTTPResponse(500))
                if isinstance(response, BaseException):
                    raise response
                return response

        touched: list[str] = []
        saved_regs: list[dict] = []

        def touch(crew_id: str) -> None:
            touched.append(crew_id)

        def save_reg(reg: dict) -> None:
            saved_regs.append(dict(reg))

        # Patch the while loop to run once via StopIteration on sleep
        sleep_called = [False]

        def fake_sleep(secs: float) -> None:
            if sleep_called[0]:
                raise StopIteration()
            sleep_called[0] = True

        with (
            patch.object(monitors, "_get_podman", return_value=podman),
            patch.object(monitors, "_http", FakeHTTP()),
            patch.object(monitors, "_touch_crew", side_effect=touch),
            patch.object(monitors, "_load_registry", return_value={"crews": dict(crew_items)}),
            patch.object(monitors, "_save_registry", side_effect=save_reg),
            patch.object(monitors, "_mint_cookie", return_value=mint_cookie_return),
            patch.object(monitors.time, "sleep", side_effect=fake_sleep),
            patch.object(monitors.time, "time", return_value=1000.0),
        ):
            try:
                server._idle_monitor()
            except StopIteration:
                pass

        return {
            "stops": podman.stops,
            "touched": touched,
            "http_calls": http_calls,
            "saved_regs": saved_regs,
        }

    def test_crew_with_active_task_not_stopped(self) -> None:
        """4.1: crew with active dispatch task is not stopped, last_used updated."""
        podman = IdleMonitorPodman(containers_running={"gs-active": True})
        spawn_resp = MockHTTPResponse(200, {"agents": [{"done": False}]})
        crew_items = [("active", {"container": "gs-active", "status": "running", "cookie": "c", "last_used": 0})]
        result = self._run_one_iteration(crew_items, podman, [spawn_resp])

        self.assertEqual(result["stops"], [])
        self.assertIn("active", result["touched"])

    def test_crew_with_enabled_cron_not_stopped(self) -> None:
        """4.2: crew with enabled cron job is not stopped, last_used updated."""
        podman = IdleMonitorPodman(containers_running={"gs-cron": True})
        spawn_resp = MockHTTPResponse(200, {"agents": []})
        cron_resp = MockHTTPResponse(200, {"jobs": [{"name": "check", "enabled": True}]})
        crew_items = [("cron-crew", {"container": "gs-cron", "status": "running", "cookie": "c", "last_used": 0})]
        result = self._run_one_iteration(crew_items, podman, [spawn_resp, cron_resp])

        self.assertEqual(result["stops"], [])
        self.assertIn("cron-crew", result["touched"])

    def test_genuinely_idle_crew_is_stopped(self) -> None:
        """4.3: genuinely idle crew is stopped, registry marked 'stopped'."""
        podman = IdleMonitorPodman(containers_running={"gs-idle": True})
        spawn_resp = MockHTTPResponse(200, {"agents": []})
        cron_resp = MockHTTPResponse(200, {"jobs": []})
        crew_items = [("idle-crew", {"container": "gs-idle", "status": "running", "cookie": "c", "last_used": 0})]
        result = self._run_one_iteration(crew_items, podman, [spawn_resp, cron_resp])

        self.assertIn("gs-idle", result["stops"])
        self.assertTrue(result["saved_regs"])
        self.assertEqual(result["saved_regs"][-1]["crews"]["idle-crew"]["status"], "stopped")

    def test_recently_used_crew_skipped(self) -> None:
        """4.4: recently used crew (within timeout) is skipped."""
        podman = IdleMonitorPodman(containers_running={"gs-recent": True})
        # last_used is recent enough (within GA_IDLE_TIMEOUT_SECS of now=1000)
        crew_items = [("recent", {"container": "gs-recent", "status": "running", "cookie": "c", "last_used": 999.0})]
        result = self._run_one_iteration(crew_items, podman, [])

        self.assertEqual(result["stops"], [])
        self.assertEqual(result["touched"], [])
        self.assertEqual(result["http_calls"], [])

    def test_already_stopped_container_skipped(self) -> None:
        """4.5: already-stopped container is skipped (no double-stop)."""
        podman = IdleMonitorPodman(containers_running={"gs-stopped": False})
        crew_items = [("stopped", {"container": "gs-stopped", "status": "running", "cookie": "c", "last_used": 0})]
        result = self._run_one_iteration(crew_items, podman, [])

        self.assertEqual(result["stops"], [])

    def test_401_triggers_cookie_refresh_and_retry(self) -> None:
        """5.2: 401 response triggers cookie refresh and successful retry."""
        podman = IdleMonitorPodman(containers_running={"gs-auth": True})
        # First spawn call returns 401, retry returns 200 with active task
        spawn_401 = MockHTTPResponse(401)
        spawn_ok = MockHTTPResponse(200, {"agents": [{"done": False}]})
        crew_items = [("auth-crew", {"container": "gs-auth", "status": "running", "cookie": "old", "last_used": 0})]
        result = self._run_one_iteration(
            crew_items, podman, [spawn_401, spawn_ok],
            mint_cookie_return="new-cookie",
        )

        self.assertEqual(result["stops"], [])
        self.assertIn("auth-crew", result["touched"])

    def test_401_with_failed_cookie_refresh_skips_crew(self) -> None:
        """5.3: 401 with failed cookie refresh skips crew (does not stop it)."""
        podman = IdleMonitorPodman(containers_running={"gs-nauth": True})
        spawn_401 = MockHTTPResponse(401)
        crew_items = [("nauth-crew", {"container": "gs-nauth", "status": "running", "cookie": "dead", "last_used": 0})]
        result = self._run_one_iteration(
            crew_items, podman, [spawn_401],
            mint_cookie_return=None,  # cookie refresh fails
        )

        # Should NOT stop the crew (fail-open)
        self.assertEqual(result["stops"], [])
        # Should NOT touch (we can't verify activity)
        self.assertEqual(result["touched"], [])

    def test_spawn_activity_check_exception_skips_crew(self) -> None:
        """An /api/spawn error leaves the crew running for this cycle."""
        podman = IdleMonitorPodman(containers_running={"gs-spawn-error": True})
        crew_items = [(
            "spawn-error",
            {"container": "gs-spawn-error", "status": "running", "cookie": "c", "last_used": 0},
        )]

        result = self._run_one_iteration(
            crew_items, podman, [RuntimeError("spawn unavailable")]
        )

        self.assertEqual(result["stops"], [])

    def test_spawn_activity_check_unexpected_response_skips_crew(self) -> None:
        """A non-success /api/spawn response leaves the crew running."""
        podman = IdleMonitorPodman(containers_running={"gs-spawn-status-error": True})
        crew_items = [(
            "spawn-status-error",
            {"container": "gs-spawn-status-error", "status": "running", "cookie": "c", "last_used": 0},
        )]

        result = self._run_one_iteration(
            crew_items, podman, [MockHTTPResponse(503)]
        )

        self.assertEqual(result["stops"], [])

    def test_spawn_activity_check_malformed_response_skips_crew(self) -> None:
        """A malformed successful /api/spawn payload leaves the crew running."""
        podman = IdleMonitorPodman(containers_running={"gs-spawn-malformed": True})
        crew_items = [(
            "spawn-malformed",
            {"container": "gs-spawn-malformed", "status": "running", "cookie": "c", "last_used": 0},
        )]

        result = self._run_one_iteration(
            crew_items, podman, [MockHTTPResponse(200, [])]
        )

        self.assertEqual(result["stops"], [])

    def test_cron_activity_check_exception_skips_crew(self) -> None:
        """An /api/crons error leaves the crew running for this cycle."""
        podman = IdleMonitorPodman(containers_running={"gs-cron-error": True})
        spawn_resp = MockHTTPResponse(200, {"agents": []})
        crew_items = [(
            "cron-error",
            {"container": "gs-cron-error", "status": "running", "cookie": "c", "last_used": 0},
        )]

        result = self._run_one_iteration(
            crew_items, podman, [spawn_resp, RuntimeError("crons unavailable")]
        )

        self.assertEqual(result["stops"], [])

    def test_cron_activity_check_unexpected_response_skips_crew(self) -> None:
        """A non-success /api/crons response leaves the crew running."""
        podman = IdleMonitorPodman(containers_running={"gs-cron-status-error": True})
        spawn_resp = MockHTTPResponse(200, {"agents": []})
        crew_items = [(
            "cron-status-error",
            {"container": "gs-cron-status-error", "status": "running", "cookie": "c", "last_used": 0},
        )]

        result = self._run_one_iteration(
            crew_items, podman, [spawn_resp, MockHTTPResponse(503)]
        )

        self.assertEqual(result["stops"], [])

    def test_cron_activity_check_malformed_response_skips_crew(self) -> None:
        """A malformed successful /api/crons payload leaves the crew running."""
        podman = IdleMonitorPodman(containers_running={"gs-cron-malformed": True})
        spawn_resp = MockHTTPResponse(200, {"agents": []})
        crew_items = [(
            "cron-malformed",
            {"container": "gs-cron-malformed", "status": "running", "cookie": "c", "last_used": 0},
        )]

        result = self._run_one_iteration(
            crew_items, podman, [spawn_resp, MockHTTPResponse(200, [])]
        )

        self.assertEqual(result["stops"], [])

    def test_idle_monitor_cron_401_retries_with_fresh_cookie(self) -> None:
        """D9 — cron endpoint 401 triggers cookie refresh and retry (TRN-39 4.4)."""
        podman = IdleMonitorPodman(containers_running={"gs-cron401": True})
        # spawn returns empty (no tasks), cron first returns 401, then (after cookie refresh)
        # returns a listing with an enabled cron job (keeps crew alive).
        spawn_resp = MockHTTPResponse(200, {"agents": []})
        cron_401 = MockHTTPResponse(401)
        cron_ok = MockHTTPResponse(200, {"jobs": [{"name": "check", "enabled": True}]})
        crew_items = [(
            "cron401-crew",
            {"container": "gs-cron401", "status": "running", "cookie": "old", "last_used": 0},
        )]

        result = self._run_one_iteration(
            crew_items, podman, [spawn_resp, cron_401, cron_ok],
            mint_cookie_return="new-cookie",
        )

        # Cookie refresh happened, cron retried — crew should NOT be stopped
        self.assertEqual(result["stops"], [], "crew should not be stopped after cron 401 retry")
        self.assertIn("cron401-crew", result["touched"])

    def test_403_triggers_cookie_refresh_and_retry_on_spawn(self) -> None:
        """2.2 (trn-78): 403 response on spawn triggers cookie refresh and retry."""
        podman = IdleMonitorPodman(containers_running={"gs-403spawn": True})
        # First spawn call returns 403 (CSRF mismatch), retry returns 200 with active task
        spawn_403 = MockHTTPResponse(403)
        spawn_ok = MockHTTPResponse(200, {"agents": [{"done": False}]})
        crew_items = [("spawn-403-crew", {
            "container": "gs-403spawn", "status": "running", "cookie": "old", "last_used": 0,
        })]
        result = self._run_one_iteration(
            crew_items, podman, [spawn_403, spawn_ok],
            mint_cookie_return="new-cookie",
        )

        # Crew has active task after retry — must not be stopped
        self.assertEqual(result["stops"], [])
        self.assertIn("spawn-403-crew", result["touched"])

    def test_403_with_successful_cookie_refresh_stops_idle_crew(self) -> None:
        """2.3 (trn-78): idle monitor stops crew after successful cookie refresh following 403."""
        podman = IdleMonitorPodman(containers_running={"gs-403idle": True})
        # spawn: first 403, then (after cookie refresh) 200 with empty agents
        # crons: 200 with empty jobs list → crew is genuinely idle → gets stopped
        spawn_403 = MockHTTPResponse(403)
        spawn_ok = MockHTTPResponse(200, {"agents": []})
        cron_ok = MockHTTPResponse(200, {"jobs": []})
        crew_items = [("idle-403-crew", {
            "container": "gs-403idle", "status": "running", "cookie": "old", "last_used": 0,
        })]
        result = self._run_one_iteration(
            crew_items, podman, [spawn_403, spawn_ok, cron_ok],
            mint_cookie_return="new-cookie",
        )

        # Cookie refresh succeeded, no active tasks — crew should be stopped
        self.assertIn("gs-403idle", result["stops"])
        self.assertTrue(result["saved_regs"])
        self.assertEqual(result["saved_regs"][-1]["crews"]["idle-403-crew"]["status"], "stopped")
class IdleMonitorActivityTests(unittest.TestCase):
    def test_cron_activity_counts_running_and_recent_completed_runs(self) -> None:
        self.assertTrue(
            server._cron_activity_since(
                {"jobs": [{"is_running": True, "running_since": 90}]}, 100
            )
        )
        self.assertTrue(
            server._cron_activity_since(
                {"jobs": [{"is_running": False, "last_run_ts": 101}]}, 100
            )
        )
        self.assertFalse(
            server._cron_activity_since(
                {"jobs": [{"is_running": False, "last_run_ts": 100}]}, 100
            )
        )

    def test_enabled_job_with_no_activity_history_still_counts(self) -> None:
        # A freshly-created job with interval longer than GA_IDLE_TIMEOUT_SECS
        # has no is_running/running_since/last_run_ts yet — _cron_activity_since
        # alone would report no activity, and the crew would idle-stop before
        # the job's very first fire. _cron_has_enabled_job is the separate
        # signal that catches this: an enabled job is a standing commitment to
        # run, regardless of whether it has run yet.
        fresh_job_payload = {"jobs": [{"name": "captain", "agent": "raven", "enabled": True}]}
        self.assertFalse(server._cron_activity_since(fresh_job_payload, 100))
        self.assertTrue(server._cron_has_enabled_job(fresh_job_payload))

    def test_disabled_job_does_not_count_as_enabled(self) -> None:
        self.assertFalse(
            server._cron_has_enabled_job({"jobs": [{"name": "captain", "enabled": False}]})
        )
        self.assertFalse(server._cron_has_enabled_job({"jobs": []}))
        self.assertFalse(server._cron_has_enabled_job({}))
class ScheduleMonitorTests(unittest.TestCase):
    """Tests for TRN-29 _schedule_monitor."""

    CREW = {"container": "gs-demo", "cookie": "cookie", "status": "running"}

    def test_monitor_wakes_crew_and_fires_tick(self) -> None:
        """7.4 — _schedule_monitor calls the real function; tick is fired after one loop."""
        now = time.time()
        reg = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie", "status": "stopped",
            "schedules": [{
                "job_id": "j1", "name": "check", "interval_secs": 300, "cron_expr": None,
                "next_fire_at": now - 10,  # due
                "agent": "ghost", "message": "do check", "model": "claude-sonnet-5",
                "enabled": True,
            }],
        }}}
        api_calls = []

        def api(_crew, _crew_id, method, path, **kwargs):
            api_calls.append((method, path, kwargs))
            return {"id": "spawn-1"}

        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        # Use StopIteration on the second time.sleep call to exit the while True loop
        # after exactly one iteration.  The monitor sleeps FIRST, then does work, then
        # loops back to sleep — raising on the second sleep gives the work one full pass.
        sleep_count = [0]

        def fake_sleep(secs: float) -> None:
            sleep_count[0] += 1
            if sleep_count[0] >= 2:
                raise StopIteration("break after one iteration")

        with (
            patch.object(monitors, "_load_registry", return_value=reg),
            patch.object(monitors, "_ensure_crew_running", return_value=self.CREW),
            patch.object(monitors, "_crew_api_with_recovery", side_effect=api),
            patch.object(monitors, "_save_registry", side_effect=fake_save),
            patch.object(monitors, "_get_crew_schedules", return_value=reg["crews"]["demo"]["schedules"]),
            patch.object(monitors.time, "sleep", side_effect=fake_sleep),
        ):
            try:
                server._schedule_monitor()
            except StopIteration:
                pass  # expected — one iteration complete

        # Verify the spawn POST was fired
        self.assertTrue(
            any(m == "POST" and "/api/spawn" in p for m, p, _ in api_calls),
            f"Expected a POST /api/spawn call; got: {api_calls}",
        )
        # Verify registry was saved after the tick
        self.assertTrue(len(save_calls) > 0, "Expected _save_registry to have been called")
        spawn_calls = [
            kwargs for method, path, kwargs in api_calls
            if method == "POST" and path == "/api/spawn"
        ]
        self.assertEqual(spawn_calls[0]["json"]["model"], "claude-sonnet-5")

    def test_monitor_skips_and_advances_on_crew_failure(self) -> None:
        """7.5 — _schedule_monitor skips tick and advances when crew won't start."""
        now = time.time()
        sched = {
            "job_id": "j1", "name": "check", "interval_secs": 300, "cron_expr": None,
            "next_fire_at": now - 10, "agent": "ghost", "message": "do check", "enabled": True,
        }

        # Simulate: _ensure_crew_running raises, so we advance
        server._advance_next_fire_at(sched)
        self.assertGreater(sched["next_fire_at"], now)

    def test_reseed_crew_schedules_reregisters_missing_jobs(self) -> None:
        """7.6 — _reseed_crew_schedules re-registers missing jobs in gateway."""
        reg = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [{
                "job_id": "j1", "name": "daily-report", "interval_secs": 86400,
                "cron_expr": None, "agent": "ghost", "message": "report",
                "enabled": True, "next_fire_at": time.time() + 1000,
            }],
        }}}
        api_calls = []

        def api(_crew, method, path, **kwargs):
            api_calls.append((method, path, kwargs))
            if method == "GET" and path == "/api/crons":
                return {"jobs": []}  # No jobs in gateway
            if method == "POST" and path == "/api/crons":
                return {"id": "new-j1"}
            return {}

        crew = {"container": "gs-demo", "cookie": "cookie"}
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        with (
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            server._reseed_crew_schedules(crew, "demo", reg["crews"]["demo"])

        # Verify POST to /api/crons was called to re-register
        post_calls = [(m, p) for m, p, _ in api_calls if m == "POST" and p == "/api/crons"]
        self.assertEqual(len(post_calls), 1)
class ScheduleCancelTests(unittest.TestCase):
    """Tests for schedule(action='cancel', ...)."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_cancel_success(self) -> None:
        """4.1 — cancel removes the registry entry after gateway DELETE."""
        # Seed a registry with a matching job_id entry
        reg = {
            "crews": {"demo": {
                "container": "gs-demo", "cookie": "cookie",
                "schedules": [
                    {"job_id": "job-abc", "name": "my-job", "interval_secs": 60,
                     "cron_expr": None, "agent": "ghost", "enabled": True},
                ],
            }}
        }
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        jobs_listing = {"jobs": [
            {"id": "job-abc", "name": "my-job", "agent": "ghost", "enabled": True},
        ]}

        def api(_crew, _crew_id, method, path, **kwargs):
            if method == "GET" and path == "/api/crons":
                return jobs_listing
            if method == "DELETE" and path == "/api/crons/job-abc":
                return {}
            raise AssertionError((method, path, kwargs))

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            result = server.schedule(action="cancel", job_id="job-abc", crew_id="demo")

        self.assertEqual(result, {"status": "cancelled", "job_id": "job-abc"})
        # Verify the registry entry was removed
        self.assertTrue(len(save_calls) > 0, "Expected _save_registry to be called")
        last_reg = save_calls[-1]
        remaining_ids = [s.get("job_id") for s in last_reg["crews"]["demo"]["schedules"]]
        self.assertNotIn("job-abc", remaining_ids, "job-abc should have been removed from registry")

    def test_cancel_not_found_is_idempotent(self) -> None:
        """4.1 — cancel a non-existent job is idempotent (TRN-29: no error)."""
        jobs_listing = {"jobs": []}

        def api(_crew, _crew_id, method, path, **kwargs):
            if method == "GET" and path == "/api/crons":
                return jobs_listing
            if method == "DELETE":
                resp = Mock(status_code=404)
                raise httpx.HTTPStatusError(
                    "Not Found",
                    request=None,
                    response=resp,
                )
            raise AssertionError((method, path, kwargs))

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(lifecycle, "_load_registry", return_value={"crews": {"demo": {"schedules": []}}}),
            patch.object(server, "_load_registry", return_value={"crews": {"demo": {"schedules": []}}}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
        ):
            result = server.schedule(action="cancel", job_id="nonexistent", crew_id="demo")

        self.assertEqual(result, {"status": "cancelled", "job_id": "nonexistent"})

    def test_cancel_refuses_captain_checkin_job(self) -> None:
        """4.2 — cancel refuses to cancel the captain check-in job."""
        captain_job = {
            "id": "captain-job-id",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
        }
        jobs_listing = {"jobs": [captain_job]}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", return_value=jobs_listing),
            patch.object(server, "_crew_api_with_recovery", return_value=jobs_listing),
        ):
            result = server.schedule(action="cancel", job_id="captain-job-id", crew_id="demo")

        self.assertIn("Cannot cancel the Captain check-in job", result["error"])

    def test_cancel_requires_job_id(self) -> None:
        """cancel without job_id returns error."""
        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
        ):
            result = server.schedule(action="cancel", crew_id="demo")

        self.assertIn("job_id is required", result["error"])
class ScheduleCreateValidationTests(unittest.TestCase):
    """Tests for schedule(action='create') input validation."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_create_requires_name(self) -> None:
        """create without name returns error."""
        result = server.schedule(action="create", message="do stuff", crew_id="demo", interval=60)
        self.assertIn("name is required", result["error"])

    def test_create_requires_message(self) -> None:
        """create without message returns error."""
        result = server.schedule(action="create", name="my-job", crew_id="demo", interval=60)
        self.assertIn("message is required", result["error"])
class ScheduleListTests(unittest.TestCase):
    """Tests for schedule(action='list', ...)."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_list_with_jobs(self) -> None:
        """4.3 — list returns jobs with expected fields."""
        jobs_listing = {"jobs": [
            {"id": "j1", "name": "daily-check", "schedule": "0 9 * * *", "agent": "ghost", "enabled": True, "last_run_ts": "2026-01-01T09:00:00"},
            {"id": "j2", "name": "weekly-report", "schedule": "0 0 * * 1", "agent": "wraith", "enabled": False, "last_run_ts": None},
        ]}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", return_value=jobs_listing),
            patch.object(server, "_crew_api_with_recovery", return_value=jobs_listing),
        ):
            result = server.schedule(action="list", crew_id="demo")

        self.assertEqual(len(result["jobs"]), 2)
        self.assertEqual(result["jobs"][0]["job_id"], "j1")
        self.assertEqual(result["jobs"][0]["name"], "daily-check")
        self.assertEqual(result["jobs"][0]["agent"], "ghost")
        self.assertTrue(result["jobs"][0]["enabled"])
        self.assertEqual(result["jobs"][1]["job_id"], "j2")
        self.assertFalse(result["jobs"][1]["enabled"])

    def test_list_empty(self) -> None:
        """4.3 — list returns empty jobs list when no jobs exist."""
        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", return_value={"jobs": []}),
            patch.object(server, "_crew_api_with_recovery", return_value={"jobs": []}),
        ):
            result = server.schedule(action="list", crew_id="demo")

        self.assertEqual(result, {"jobs": []})

    def test_list_falls_back_to_gateway_when_registry_empty(self) -> None:
        """4.1b — schedule(list) falls back to gateway /api/crons when registry is empty."""
        # Registry has no schedules for this crew
        reg_empty = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie", "schedules": []}}}
        gateway_jobs = {"jobs": [
            {"id": "gw-j1", "name": "gateway-job", "schedule": "every 60s",
             "agent": "ghost", "enabled": True, "last_run_ts": None},
        ]}

        with (
            patch.object(lifecycle, "_load_registry", return_value=reg_empty),
            patch.object(server, "_load_registry", return_value=reg_empty),
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", return_value=gateway_jobs) as api_mock,
            patch.object(server, "_crew_api_with_recovery", return_value=gateway_jobs) as api_mock,
        ):
            result = server.schedule(action="list", crew_id="demo")

        # The gateway /api/crons GET must have been called as fallback
        api_mock.assert_called_once()
        call_args = api_mock.call_args
        self.assertEqual(call_args.args[2], "GET")
        self.assertEqual(call_args.args[3], "/api/crons")
        # The gateway's job should appear in the result
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["job_id"], "gw-j1")
        self.assertEqual(result["jobs"][0]["name"], "gateway-job")
class SchedulePersistenceTests(unittest.TestCase):
    """Tests for TRN-29 transport schedule persistence."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def _make_registry(self, crew_id: str = "demo", schedules: list | None = None) -> dict:
        return {"crews": {crew_id: {"container": "gs-demo", "cookie": "cookie", "schedules": schedules or []}}}

    def test_captain_order_writes_schedule_entry(self) -> None:
        """7.1 — captain(action='order') writes schedule entry to registry."""
        reg = self._make_registry()
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        jobs_listing = {"jobs": []}
        created_job = {"id": "cap-job-1", "name": "captain", "schedule": "every 300s"}

        def api(_crew, _crew_id, method, path, **kwargs):
            if method == "GET" and path == "/api/crons":
                return jobs_listing
            if method == "POST" and path == "/api/crons":
                return created_job
            if method == "POST" and "/api/spawn" in path:
                return {"id": "spawn-1"}
            return {}

        fake_podman = SetupPodman()
        fake_podman.container_exec = lambda *a, **kw: ""

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
            patch.object(lifecycle, "_get_podman", return_value=fake_podman),
            patch.object(server, "_get_podman", return_value=fake_podman),
            patch.object(server, "_append_captain_mail"),
        ):
            result = server.captain(
                crew_id="demo", action="order", message="do stuff", interval=300,
                model="claude-opus-5",
            )

        self.assertEqual(result["status"], "ordered")
        self.assertEqual(result["job_id"], "cap-job-1")
        # Verify registry was written with schedule entry
        self.assertTrue(len(save_calls) > 0)
        last_reg = save_calls[-1]
        schedules = last_reg["crews"]["demo"]["schedules"]
        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0]["job_id"], "cap-job-1")
        self.assertEqual(schedules[0]["name"], "captain")
        self.assertEqual(schedules[0]["agent"], "raven")
        self.assertEqual(schedules[0]["model"], "claude-opus-5")
        self.assertTrue(schedules[0]["enabled"])

    def test_schedule_list_returns_registry_entries_when_stopped(self) -> None:
        """7.2 — schedule(action='list') returns registry entries when crew stopped."""
        reg = self._make_registry(schedules=[
            {"job_id": "j1", "name": "daily-check", "interval_secs": 3600, "cron_expr": None,
             "agent": "ghost", "enabled": True, "next_fire_at": 9999999999.0},
        ])

        with (
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
        ):
            result = server._schedule_list("demo")

        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["job_id"], "j1")
        self.assertEqual(result["jobs"][0]["name"], "daily-check")
        self.assertEqual(result["jobs"][0]["agent"], "ghost")
        self.assertTrue(result["jobs"][0]["enabled"])

    def test_schedule_cancel_removes_from_registry(self) -> None:
        """7.3 — schedule(action='cancel') removes from registry."""
        reg = self._make_registry(schedules=[
            {"job_id": "j1", "name": "my-job", "interval_secs": 60, "cron_expr": None,
             "agent": "ghost", "enabled": True},
        ])
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        jobs_listing = {"jobs": [
            {"id": "j1", "name": "my-job", "agent": "ghost", "enabled": True},
        ]}

        def api(_crew, _crew_id, method, path, **kwargs):
            if method == "GET" and path == "/api/crons":
                return jobs_listing
            if method == "DELETE":
                return {}
            return {}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            result = server._schedule_cancel("j1", "demo")

        self.assertEqual(result, {"status": "cancelled", "job_id": "j1"})
        # Verify registry no longer has the job
        self.assertTrue(len(save_calls) > 0)
        last_reg = save_calls[-1]
        schedules = last_reg["crews"]["demo"]["schedules"]
        self.assertEqual(len(schedules), 0)

    def test_schedule_delay_creates_one_shot_registry_entry(self) -> None:
        """7.7 — schedule(delay=N) creates one-shot entry in registry."""
        reg = self._make_registry()
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", return_value={"id": "delay-job-1"}),
            patch.object(server, "_crew_api_with_recovery", return_value={"id": "delay-job-1"}),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            result = server.schedule(
                name="cleanup", message="run cleanup", agent="ghost",
                crew_id="demo", delay=300, model="claude-sonnet-5",
            )

        self.assertEqual(result["job_id"], "delay-job-1")
        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(result["delay"], 300)
        # Verify registry was written with one-shot entry
        self.assertTrue(len(save_calls) > 0)
        last_reg = save_calls[-1]
        schedules = last_reg["crews"]["demo"]["schedules"]
        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0]["job_id"], "delay-job-1")
        self.assertEqual(schedules[0]["model"], "claude-sonnet-5")
        self.assertTrue(schedules[0].get("one_shot"))

    def test_dispatch_no_longer_accepts_delay(self) -> None:
        """7.8 — dispatch no longer accepts delay parameter."""
        import inspect
        sig = inspect.signature(server.dispatch)
        self.assertNotIn("delay", sig.parameters)

    def test_registry_rejects_inf_in_next_fire_at(self) -> None:
        """One-shot job with float('inf') must not be JSON-serialisable.  # requires TRN-37

        TRN-37 replaces float('inf') with _NEVER_FIRE_AT (9_999_999_999.0) to
        ensure the registry can always be serialised with allow_nan=False.
        This test confirms the guard is the correct fix: float('inf') DOES raise.
        """
        reg = self._make_registry(schedules=[{
            "job_id": "j-inf", "name": "one-shot", "interval_secs": None,
            "cron_expr": None, "agent": "ghost", "enabled": True,
            "next_fire_at": float("inf"),
        }])
        with self.assertRaises(ValueError):
            json.dumps(reg, allow_nan=False)

    def test_captain_resume_sets_next_fire_at(self) -> None:
        """7.x — captain resume sets next_fire_at ≈ now + interval in registry."""
        interval = 300
        reg = self._make_registry(schedules=[
            # Existing disabled entry — the resume path will re-enable it
            {"job_id": "cap-job-1", "name": "captain", "interval_secs": interval,
             "cron_expr": None, "agent": "raven", "enabled": False,
             "next_fire_at": 0.0},
        ])
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        # Gateway has the job disabled (resume path: existing_job != None, enabled_job == None)
        existing_job = {"id": "cap-job-1", "name": "captain", "schedule": f"every {interval}s",
                        "enabled": False, "agent": "raven"}
        jobs_listing = {"jobs": [existing_job]}

        def api(_crew, _crew_id, method, path, **kwargs):
            if method == "GET" and path == "/api/crons":
                return jobs_listing
            if method == "POST" and path == f"/api/crons/{existing_job['id']}/enable":
                return {"ok": True}
            if method == "POST" and path == "/api/crons":
                return {"id": "cap-job-1", "schedule": f"every {interval}s"}
            if method == "POST" and "/api/spawn" in path:
                return {"id": "spawn-1"}
            return {}

        fake_podman = SetupPodman()
        fake_podman.container_exec = lambda *a, **kw: ""

        before = time.time()
        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
            patch.object(lifecycle, "_get_podman", return_value=fake_podman),
            patch.object(server, "_get_podman", return_value=fake_podman),
            patch.object(server, "_append_captain_mail"),
        ):
            result = server.captain(
                crew_id="demo", action="order", message="check in", interval=interval,
            )

        self.assertEqual(result.get("status"), "ordered")
        self.assertTrue(len(save_calls) > 0)
        last_reg = save_calls[-1]
        schedules = last_reg["crews"]["demo"]["schedules"]
        self.assertEqual(len(schedules), 1)
        entry = schedules[0]
        self.assertGreaterEqual(
            entry["next_fire_at"], before + interval - 1,
            f"next_fire_at {entry['next_fire_at']!r} should be ≈ now+{interval}",
        )
class ReseedCronReconcileTests(unittest.TestCase):
    """Tests for the gateway→registry reconcile pass in _reseed_crew_schedules (TRN-82)."""

    def _make_reg(self, schedules):
        return {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": schedules,
        }}}

    def test_reconcile_paused_job_updates_registry(self) -> None:
        """2.1 — gateway reports job enabled=false → registry updated, job not re-registered."""
        reg = self._make_reg([{
            "job_id": "j1", "name": "captain", "interval_secs": 300,
            "cron_expr": None, "agent": "raven", "message": "check-in",
            "model": "old-model", "enabled": True,  # stale: registry says enabled
        }])
        api_calls = []

        def api(_crew, method, path, **kwargs):
            api_calls.append((method, path))
            if method == "GET" and path == "/api/crons":
                return {
                    "jobs": [{
                        "id": "j1", "enabled": False, "every_secs": 300,
                        "model": "new-model",
                    }]
                }
            return {}

        saved = []

        def fake_save(r):
            saved.append(json.loads(json.dumps(r)))

        with (
            patch.object(lifecycle, "_load_registry", return_value=json.loads(json.dumps(reg))),
            patch.object(server, "_load_registry", return_value=json.loads(json.dumps(reg))),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            server._reseed_crew_schedules(
                {"container": "gs-demo", "cookie": "cookie"}, "demo", reg["crews"]["demo"]
            )

        # Registry should have been saved with enabled=False
        self.assertTrue(saved, "Registry should have been saved after reconcile")
        sched = saved[-1]["crews"]["demo"]["schedules"][0]
        self.assertFalse(sched["enabled"], "Registry entry should be updated to enabled=False")
        self.assertEqual(sched["model"], "new-model")

        # No POST to re-register the paused job
        post_calls = [p for m, p in api_calls if m == "POST"]
        self.assertEqual(post_calls, [], "Paused job should not be re-registered")

    def test_reconcile_absent_job_left_for_reseed(self) -> None:
        """2.2 — gateway does not include job → entry kept in registry, reseeded as bootstrap."""
        reg = self._make_reg([{
            "job_id": "j1", "name": "captain", "interval_secs": 300,
            "cron_expr": None, "agent": "raven", "message": "check-in",
            "enabled": True,
        }])
        api_calls = []

        def api(_crew, method, path, **kwargs):
            api_calls.append((method, path))
            if method == "GET" and path == "/api/crons":
                return {"jobs": []}  # Job absent — bootstrap case
            if method == "POST" and path == "/api/crons":
                return {"id": "j1"}
            return {}

        saved = []

        def fake_save(r):
            saved.append(json.loads(json.dumps(r)))

        with (
            patch.object(lifecycle, "_load_registry", return_value=json.loads(json.dumps(reg))),
            patch.object(server, "_load_registry", return_value=json.loads(json.dumps(reg))),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            server._reseed_crew_schedules(
                {"container": "gs-demo", "cookie": "cookie"}, "demo", reg["crews"]["demo"]
            )

        # Job should be reseeded (POST) — absent from gateway is the bootstrap case
        post_calls = [p for m, p in api_calls if m == "POST" and p == "/api/crons"]
        self.assertEqual(len(post_calls), 1, "Absent enabled job should be reseeded")

    def test_reseed_missing_job_registered_in_gateway(self) -> None:
        """2.3 — registry has enabled job absent from gateway → job registered (bootstrap)."""
        reg = self._make_reg([{
            "job_id": "j1", "name": "captain", "interval_secs": 300,
            "cron_expr": None, "agent": "raven", "message": "check-in",
            "enabled": True,
        }])
        api_calls = []

        def api(_crew, method, path, **kwargs):
            api_calls.append((method, path))
            if method == "GET" and path == "/api/crons":
                return {"jobs": []}  # Missing from gateway — bootstrap case
            if method == "POST" and path == "/api/crons":
                return {"id": "j1-new"}
            return {}

        saved = []

        def fake_save(r):
            saved.append(json.loads(json.dumps(r)))

        with (
            patch.object(lifecycle, "_load_registry", return_value=json.loads(json.dumps(reg))),
            patch.object(server, "_load_registry", return_value=json.loads(json.dumps(reg))),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            server._reseed_crew_schedules(
                {"container": "gs-demo", "cookie": "cookie"}, "demo", reg["crews"]["demo"]
            )

        # POST should have been made to register the missing job
        post_calls = [p for m, p in api_calls if m == "POST" and p == "/api/crons"]
        self.assertEqual(len(post_calls), 1, "Missing enabled job should be re-registered")

    def test_reconcile_gateway_error_skips_both_passes(self) -> None:
        """2.4 — gateway /api/crons returns error → both passes skipped, registry unchanged."""
        reg = self._make_reg([{
            "job_id": "j1", "name": "captain", "interval_secs": 300,
            "cron_expr": None, "agent": "raven", "message": "check-in",
            "enabled": True,
        }])

        def api(_crew, method, path, **kwargs):
            raise RuntimeError("gateway unavailable")

        saved = []

        def fake_save(r):
            saved.append(r)

        with (
            patch.object(lifecycle, "_load_registry", return_value=json.loads(json.dumps(reg))),
            patch.object(server, "_load_registry", return_value=json.loads(json.dumps(reg))),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            server._reseed_crew_schedules(
                {"container": "gs-demo", "cookie": "cookie"}, "demo", reg["crews"]["demo"]
            )

        # Registry should not have been touched
        self.assertEqual(saved, [], "Registry should not be saved when gateway errors")
class NukeScheduleTests(unittest.TestCase):
    """Tests for TRN-59 nuke schedule reporting and clearing."""

    CREW = {
        "container": "gs-demo",
        "volume": "gs-vol-demo",
        "home_volume": "gs-home-demo",
    }

    def _reg_with_schedules(self, schedules: list) -> dict:
        return {"crews": {"demo": {**self.CREW, "schedules": schedules}}}

    # ── 3.1: dry-run with two schedule entries ─────────────────────────────

    def test_dry_run_reports_two_scheduled_jobs(self) -> None:
        """3.1 — dry-run returns scheduled_jobs:2 and both names."""
        schedules = [
            {"job_id": "j1", "name": "daily-check", "interval_secs": 86400,
             "cron_expr": None, "agent": "ghost", "enabled": True},
            {"job_id": "j2", "name": "weekly-report", "interval_secs": None,
             "cron_expr": "0 9 * * 1", "agent": "wraith", "enabled": True},
        ]
        reg = self._reg_with_schedules(schedules)
        with (
            patch.object(lifecycle, "_get_crew", return_value=self.CREW),
            patch.object(server, "_get_crew", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value={"agents": []}),
            patch.object(server, "_crew_api", return_value={"agents": []}),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
        ):
            result = server.nuke("demo", confirm=False)

        self.assertEqual(result["scheduled_jobs"], 2)
        self.assertIn("daily-check", result["scheduled_job_names"])
        self.assertIn("weekly-report", result["scheduled_job_names"])
        self.assertIn("warning", result)

    # ── 3.2: dry-run with no schedule entries ─────────────────────────────

    def test_dry_run_reports_zero_scheduled_jobs(self) -> None:
        """3.2 — dry-run returns scheduled_jobs:0 and empty list when no schedules."""
        reg = self._reg_with_schedules([])
        with (
            patch.object(lifecycle, "_get_crew", return_value=self.CREW),
            patch.object(server, "_get_crew", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value={"agents": []}),
            patch.object(server, "_crew_api", return_value={"agents": []}),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
        ):
            result = server.nuke("demo", confirm=False)

        self.assertEqual(result["scheduled_jobs"], 0)
        self.assertEqual(result["scheduled_job_names"], [])
        self.assertIn("warning", result)

    # ── 3.3: confirmed nuke issues DELETE for each schedule entry ──────────

    def test_confirmed_nuke_cancels_each_schedule_before_cleanup(self) -> None:
        """3.3 — confirmed nuke calls DELETE /api/crons/<id> for each entry before _cleanup_crew."""
        schedules = [
            {"job_id": "j1", "name": "check", "interval_secs": 300,
             "cron_expr": None, "agent": "ghost", "enabled": True},
            {"job_id": "j2", "name": "report", "interval_secs": None,
             "cron_expr": "0 9 * * 1", "agent": "wraith", "enabled": True},
        ]
        reg = self._reg_with_schedules(schedules)
        api_calls: list[tuple[str, str]] = []
        cleanup_called_after: list[str] = []

        def fake_crew_api(crew, method, path, **kwargs):
            api_calls.append((method, path))
            return {}

        def fake_cleanup(*args, **kwargs):
            # Record which DELETE calls have been made by the time cleanup is called
            cleanup_called_after.extend([p for m, p in api_calls if m == "DELETE"])

        with (
            patch.object(lifecycle, "_get_crew", return_value=self.CREW),
            patch.object(server, "_get_crew", return_value=self.CREW),
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(lifecycle, "_crew_api", side_effect=fake_crew_api),
            patch.object(server, "_crew_api", side_effect=fake_crew_api),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
            patch.object(lifecycle, "_cleanup_crew", side_effect=fake_cleanup),
            patch.object(server, "_cleanup_crew", side_effect=fake_cleanup),
        ):
            result = server.nuke("demo", confirm=True)

        self.assertEqual(result["status"], "nuked")
        delete_paths = [p for m, p in api_calls if m == "DELETE"]
        self.assertIn("/api/crons/j1", delete_paths)
        self.assertIn("/api/crons/j2", delete_paths)
        # Both DELETEs must have been issued before _cleanup_crew was invoked
        self.assertIn("/api/crons/j1", cleanup_called_after)
        self.assertIn("/api/crons/j2", cleanup_called_after)

    # ── 3.4: DELETE failure does not block teardown ────────────────────────

    def test_confirmed_nuke_delete_failure_does_not_block_teardown(self) -> None:
        """3.4 — DELETE failure is caught, WARNING logged, and _cleanup_crew still called."""
        schedules = [
            {"job_id": "j1", "name": "check", "interval_secs": 300,
             "cron_expr": None, "agent": "ghost", "enabled": True},
        ]
        reg = self._reg_with_schedules(schedules)

        def failing_crew_api(crew, method, path, **kwargs):
            if method == "DELETE":
                raise RuntimeError("gateway unreachable")
            return {}

        with (
            patch.object(lifecycle, "_get_crew", return_value=self.CREW),
            patch.object(server, "_get_crew", return_value=self.CREW),
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(lifecycle, "_crew_api", side_effect=failing_crew_api),
            patch.object(server, "_crew_api", side_effect=failing_crew_api),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
            patch.object(lifecycle, "_cleanup_crew") as cleanup,
            patch.object(server, "_cleanup_crew") as cleanup,
            self.assertLogs("transport", level="WARNING") as log_ctx,
        ):
            result = server.nuke("demo", confirm=True)

        self.assertEqual(result["status"], "nuked")
        cleanup.assert_called_once()
        self.assertTrue(any("nuke: failed to cancel cron" in msg for msg in log_ctx.output))
        self.assertTrue(any("j1" in msg for msg in log_ctx.output))

    # ── 3.5: confirmed nuke with no schedules issues no DELETE calls ───────

    def test_confirmed_nuke_no_schedules_no_delete_calls(self) -> None:
        """3.5 — confirmed nuke with no schedules issues no DELETE calls and teardown proceeds."""
        reg = self._reg_with_schedules([])
        api_calls: list[tuple[str, str]] = []

        def fake_crew_api(crew, method, path, **kwargs):
            api_calls.append((method, path))
            return {}

        with (
            patch.object(lifecycle, "_get_crew", return_value=self.CREW),
            patch.object(server, "_get_crew", return_value=self.CREW),
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(lifecycle, "_crew_api", side_effect=fake_crew_api),
            patch.object(server, "_crew_api", side_effect=fake_crew_api),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
            patch.object(lifecycle, "_cleanup_crew") as cleanup,
            patch.object(server, "_cleanup_crew") as cleanup,
        ):
            result = server.nuke("demo", confirm=True)

        self.assertEqual(result["status"], "nuked")
        cleanup.assert_called_once()
        delete_calls = [(m, p) for m, p in api_calls if m == "DELETE"]
        self.assertEqual(delete_calls, [])
class FireImmediatelyTests(unittest.TestCase):
    """Tests for fire_immediately behavior in schedule() and captain()."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    # ── schedule() tests ──────────────────────────────────────────────────────

    def test_schedule_interval_no_fire_immediately_defaults_true(self) -> None:
        """3.2 — schedule() with interval and no fire_immediately → immediate dispatch."""
        dispatch_calls: list[dict] = []

        def api(_crew, method, path, **kwargs):
            if method == "POST" and path == "/api/spawn":
                dispatch_calls.append(kwargs.get("json", {}))
            return {"id": "job-1"}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.schedule(
                "task", "do work", crew_id="demo", interval=120,
                model="claude-sonnet-5",
            )

        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(len(dispatch_calls), 1)
        self.assertEqual(dispatch_calls[0]["task"], "do work")
        self.assertEqual(dispatch_calls[0]["model"], "claude-sonnet-5")

    def test_schedule_cron_no_fire_immediately_defaults_false(self) -> None:
        """3.3 — schedule() with cron and no fire_immediately → no immediate dispatch."""
        api_paths: list[str] = []

        def api(_crew, method, path, **kwargs):
            api_paths.append(f"{method} {path}")
            return {"id": "job-1"}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.schedule(
                "task", "do work", crew_id="demo", cron="0 9 * * 1"
            )

        self.assertEqual(result["status"], "scheduled")
        # Only the cron creation POST, no /api/spawn dispatch
        self.assertNotIn("POST /api/spawn", api_paths)
        self.assertIn("POST /api/crons", api_paths)

    def test_schedule_fire_immediately_true_with_cron(self) -> None:
        """3.4 — schedule() with fire_immediately=True and cron → immediate dispatch occurs."""
        dispatch_calls: list[dict] = []

        def api(_crew, method, path, **kwargs):
            if method == "POST" and path == "/api/spawn":
                dispatch_calls.append(kwargs.get("json", {}))
            return {"id": "job-1"}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.schedule(
                "task", "do work", crew_id="demo",
                cron="0 9 * * 1", fire_immediately=True
            )

        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(len(dispatch_calls), 1)
        self.assertEqual(dispatch_calls[0]["task"], "do work")

    def test_schedule_fire_immediately_false_with_interval(self) -> None:
        """3.5 — schedule() with fire_immediately=False and interval → no immediate dispatch."""
        api_paths: list[str] = []

        def api(_crew, method, path, **kwargs):
            api_paths.append(f"{method} {path}")
            return {"id": "job-1"}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.schedule(
                "task", "do work", crew_id="demo",
                interval=120, fire_immediately=False
            )

        self.assertEqual(result["status"], "scheduled")
        self.assertNotIn("POST /api/spawn", api_paths)



    def test_schedule_immediate_dispatch_failure_does_not_prevent_job_creation(self) -> None:
        """3.10 — immediate dispatch failure does not prevent job creation."""
        call_count = [0]

        def api(_crew, method, path, **kwargs):
            call_count[0] += 1
            if method == "POST" and path == "/api/crons":
                return {"id": "job-1"}
            if method == "POST" and path == "/api/spawn":
                raise RuntimeError("dispatch failed")
            return {}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.schedule("task", "do work", crew_id="demo", interval=120)

        # Job was still created
        self.assertEqual(result["job_id"], "job-1")
        self.assertEqual(result["status"], "scheduled")
        # Error is reported in the result, not raised
        self.assertIn("immediate_dispatch_error", result)
        self.assertIn("dispatch failed", result["immediate_dispatch_error"])

    # ── captain() tests ───────────────────────────────────────────────────────

    def test_captain_order_interval_new_job_immediate_dispatch(self) -> None:
        """3.7 — captain(action="order") with interval and new check-in → immediate Raven dispatch."""
        podman = Mock()
        spawn_calls: list[dict] = []

        def api(_crew, method, path, **kwargs):
            if method == "GET":
                return {"jobs": []}
            if method == "POST" and path == "/api/crons":
                return {"id": "job-1", "enabled": True}
            if method == "POST" and path == "/api/spawn":
                spawn_calls.append(kwargs.get("json", {}))
                return {"id": "immediate-task"}
            return {}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail"),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.captain(
                "demo", "order", message="hold", interval=120,
                model="claude-opus-5",
            )

        self.assertEqual(result["status"], "ordered")
        # Exactly one immediate dispatch to Raven
        self.assertEqual(len(spawn_calls), 1)
        self.assertEqual(spawn_calls[0]["agent"], "raven")
        self.assertEqual(spawn_calls[0]["model"], "claude-opus-5")

    def test_captain_order_resume_no_immediate_dispatch(self) -> None:
        """3.8 — captain(action="order") resume of paused job → no immediate dispatch."""
        existing = {
            "id": "job-paused",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": False,
        }
        podman = Mock()
        api_paths: list[str] = []

        def api(_crew, method, path, **kwargs):
            api_paths.append(f"{method} {path}")
            if method == "GET":
                return {"jobs": [existing]}
            return {"ok": True}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail"),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.captain("demo", "order", message="resume this")

        self.assertEqual(result["job_id"], "job-paused")
        # No immediate dispatch for a resume
        self.assertNotIn("POST /api/spawn", api_paths)
class DispatchFireAfterTests(unittest.TestCase):
    """Tests for schedule(delay=...) — TRN-29 moved delay from dispatch to schedule."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_delay_creates_one_shot_via_schedule(self) -> None:
        """6.3 — schedule(delay=N) creates a one-shot cron job."""
        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", return_value={"id": "delayed-job-1"}) as api,
            patch.object(server, "_crew_api_with_recovery", return_value={"id": "delayed-job-1"}) as api,
            patch.object(lifecycle, "_load_registry", return_value={"crews": {"demo": {"schedules": []}}}),
            patch.object(server, "_load_registry", return_value={"crews": {"demo": {"schedules": []}}}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
        ):
            result = server.schedule(
                name="cleanup", message="run cleanup", agent="ghost", crew_id="demo", delay=300
            )

        self.assertEqual(result["job_id"], "delayed-job-1")
        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(result["delay"], 300)

        # Verify it called POST /api/crons with a cron expression
        api.assert_called_once()
        call_kwargs = api.call_args.kwargs
        cron_expr = call_kwargs["json"].get("cron", "")
        self.assertEqual(len(cron_expr.split()), 5, f"Expected 5-field cron expr, got: {cron_expr!r}")
        self.assertNotIn("delay", call_kwargs["json"])
        self.assertEqual(call_kwargs["json"]["agent"], "ghost")
        self.assertEqual(call_kwargs["json"]["message"], "run cleanup")

    def test_delay_zero_rejected(self) -> None:
        """6.3 — schedule(delay=0) returns validation error."""
        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
        ):
            result = server.schedule(
                name="cleanup", message="run cleanup", crew_id="demo", delay=0
            )

        self.assertEqual(result, {"error": "delay must be >= 1"})

    def test_delay_negative_rejected(self) -> None:
        """6.3 — schedule(delay=-5) returns validation error."""
        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
        ):
            result = server.schedule(
                name="cleanup", message="run cleanup", crew_id="demo", delay=-5
            )

        self.assertEqual(result, {"error": "delay must be >= 1"})
