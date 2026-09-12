"""Unit tests for TRN-156 — lifecycle memory-leak eviction + one-shot cron replay.

Covers:

* ``lifecycle._pickup_single`` / ``lifecycle._pickup_list`` — TTL eviction of
  completed-task entries from the module-global ``_task_timestamps`` dict, so it
  does not grow without bound over the process lifetime.
* ``lifecycle._prewarm_crew`` — TTL eviction of stale ``_warm_markers`` entries.
* ``monitors._schedule_monitor`` — registry-first disablement of one-shot
  (delay) jobs, so a failed gateway DELETE cannot leave the annual cron
  expression armed for a replay a year later.

Patch-target rule (test_lifecycle §2, the call-site principle): the functions
under test are defined in ``lifecycle.py`` / ``monitors.py`` and resolve their
dependencies from that module's globals, so dependencies are patched
``lifecycle.X`` / ``monitors.X``. ``_schedule_monitor`` is invoked through the
``server`` namespace exactly as the sibling ``ScheduleMonitorTests`` do.
"""

from __future__ import annotations

import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tests.unit.helpers import server, lifecycle, monitors  # noqa: F401


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class TaskTimestampEvictionTests(unittest.TestCase):
    """Tasks 1 & 2 — completed entries older than the TTL are dropped."""

    CREW = {"container": "gs-demo", "cookie": "c", "status": "running"}

    def setUp(self) -> None:
        # Isolate the shared module global for each test.
        with lifecycle._task_timestamps_lock:
            self._saved = dict(lifecycle._task_timestamps)
            lifecycle._task_timestamps.clear()

    def tearDown(self) -> None:
        with lifecycle._task_timestamps_lock:
            lifecycle._task_timestamps.clear()
            lifecycle._task_timestamps.update(self._saved)

    def _seed(self) -> None:
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=2)      # completed long ago -> evict
        fresh = now - timedelta(seconds=5)  # completed just now -> keep
        with lifecycle._task_timestamps_lock:
            lifecycle._task_timestamps.update(
                {
                    "old-done": {"created_at": _iso(old), "completed_at": _iso(old)},
                    "fresh-done": {
                        "created_at": _iso(fresh),
                        "completed_at": _iso(fresh),
                    },
                    "in-progress": {
                        "created_at": _iso(now),
                        "started_at": _iso(now),
                        "completed_at": None,
                    },
                }
            )

    def test_task_timestamps_eviction_in_pickup_single(self) -> None:
        self._seed()
        # target task_id is the in-progress one so the entry is present.
        with (
            patch.object(
                lifecycle,
                "_crew_api_with_recovery",
                return_value={"done": True, "agent": "ghost", "elapsed": 0},
            ),
            patch.object(lifecycle, "_read_all_mail_counts", return_value={}),
            patch.object(lifecycle, "_read_all_mail_subjects", return_value={}),
        ):
            lifecycle._pickup_single(
                self.CREW, "demo", "in-progress", podman=object(),
                container="gs-demo", timeout_secs=0,
            )

        with lifecycle._task_timestamps_lock:
            keys = set(lifecycle._task_timestamps)
        self.assertNotIn("old-done", keys, "stale completed entry should be evicted")
        self.assertIn("fresh-done", keys, "fresh completed entry must be retained")
        self.assertIn("in-progress", keys, "in-progress entry must be retained")

    def test_task_timestamps_eviction_in_pickup_list(self) -> None:
        self._seed()
        agents = [
            {"id": "old-done", "done": True},
            {"id": "fresh-done", "done": True},
            {"id": "in-progress", "done": False},
        ]
        with (
            patch.object(
                lifecycle, "_crew_api_with_recovery", return_value={"agents": agents}
            ),
            patch.object(lifecycle, "_read_all_mail_counts", return_value={}),
            patch.object(lifecycle, "_read_all_mail_subjects", return_value={}),
        ):
            lifecycle._pickup_list(
                self.CREW, "demo", podman=object(),
                container="gs-demo", timeout_secs=0,
            )

        with lifecycle._task_timestamps_lock:
            keys = set(lifecycle._task_timestamps)
        self.assertNotIn("old-done", keys, "stale completed entry should be evicted")
        self.assertIn("fresh-done", keys, "fresh completed entry must be retained")
        self.assertIn("in-progress", keys, "in-progress entry must be retained")


class WarmMarkerEvictionTests(unittest.TestCase):
    """Task 3 — stale _warm_markers entries are evicted on prewarm."""

    def setUp(self) -> None:
        with lifecycle._warm_markers_lock:
            self._saved = dict(lifecycle._warm_markers)
            lifecycle._warm_markers.clear()

    def tearDown(self) -> None:
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()
            lifecycle._warm_markers.update(self._saved)

    def test_warm_markers_eviction(self) -> None:
        # A stale marker two hours old must be gone after the next prewarm;
        # the crew being warmed is recorded fresh. _wm_ttl floors at 3600s.
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers["stale-crew"] = time.monotonic() - 7200

        crew = {"container": "gs-demo", "cookie": "c", "status": "running"}
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "GA_PREWARM_TTL_SECS", 1),
            patch.object(lifecycle, "_get_podman", return_value=_ReadyPodman()),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(lifecycle, "_issue_warmup", return_value=None),
        ):
            result = lifecycle._prewarm_crew(crew, "demo")

        self.assertEqual(result.get("status"), "warmed")
        with lifecycle._warm_markers_lock:
            keys = set(lifecycle._warm_markers)
        self.assertNotIn("stale-crew", keys, "stale warm marker should be evicted")
        self.assertIn("demo", keys, "the freshly warmed crew must be recorded")


class _ReadyPodman:
    """Minimal PodmanClient stand-in: reports the crew container as running."""

    def container_is_running(self, name: str) -> bool:
        return True

    def container_start(self, name: str) -> None:  # pragma: no cover - defensive
        pass


class OneShotRegistryFirstTests(unittest.TestCase):
    """Tasks 4 & 5 — one-shot jobs are disabled in the registry before DELETE."""

    CREW = {"container": "gs-demo", "cookie": "cookie", "status": "running"}

    def _run_one_iteration(self, delete_raises: bool):
        """Drive server._schedule_monitor() for exactly one loop with a due
        one-shot job. Returns (reg, api_calls)."""
        now = time.time()
        reg = {
            "crews": {
                "demo": {
                    "container": "gs-demo",
                    "cookie": "cookie",
                    "status": "stopped",
                    "schedules": [
                        {
                            "job_id": "one-1",
                            "name": "annual-replay",
                            "interval_secs": None,
                            "cron_expr": "0 0 1 1 *",
                            "next_fire_at": now - 10,  # due
                            "agent": "ghost",
                            "message": "fire once",
                            "enabled": True,
                            "one_shot": True,
                        }
                    ],
                }
            }
        }
        schedules = reg["crews"]["demo"]["schedules"]
        api_calls: list[tuple] = []

        def api(_crew, _crew_id, method, path, **kwargs):
            api_calls.append((method, path))
            if method == "DELETE" and delete_raises:
                raise RuntimeError("gateway DELETE failed")
            return {"id": "spawn-1"}

        def fake_save(_r):
            # Registry mutations happen in-place on ``reg``; nothing to persist.
            pass

        # Fail-open gateway enabled-state check: no matching gateway job.
        def crew_api(_crew, method, path, **kwargs):
            return {"jobs": []}

        sleep_count = [0]

        def fake_sleep(_secs: float) -> None:
            sleep_count[0] += 1
            if sleep_count[0] >= 2:
                raise StopIteration("break after one iteration")

        with (
            patch.object(monitors, "_load_registry", return_value=reg),
            patch.object(monitors, "_ensure_crew_running", return_value=self.CREW),
            patch.object(monitors, "_crew_api_with_recovery", side_effect=api),
            patch.object(monitors, "_crew_api", side_effect=crew_api),
            patch.object(monitors, "_save_registry", side_effect=fake_save),
            patch.object(
                monitors, "_get_crew_schedules", return_value=schedules
            ),
            patch.object(monitors.time, "sleep", side_effect=fake_sleep),
        ):
            try:
                server._schedule_monitor()
            except StopIteration:
                pass  # expected — one iteration complete

        return reg, schedules, api_calls

    def test_one_shot_registry_disabled_before_delete(self) -> None:
        """DELETE raises — registry entry is still disabled and never re-fires."""
        reg, schedules, api_calls = self._run_one_iteration(delete_raises=True)

        entry = schedules[0]
        self.assertFalse(entry["enabled"], "one-shot must be disabled in registry")
        self.assertEqual(
            entry["next_fire_at"],
            monitors._NEVER_FIRE_AT,
            "next_fire_at must be pinned to never after a one-shot fire",
        )
        # A DELETE was attempted (best-effort) even though it raised.
        self.assertTrue(
            any(m == "DELETE" for m, _ in api_calls),
            f"expected a best-effort DELETE attempt; got {api_calls}",
        )

    def test_one_shot_delete_success_still_disables_registry(self) -> None:
        """DELETE succeeds — registry entry is still disabled unconditionally."""
        reg, schedules, api_calls = self._run_one_iteration(delete_raises=False)

        entry = schedules[0]
        self.assertFalse(entry["enabled"], "one-shot must be disabled in registry")
        self.assertEqual(entry["next_fire_at"], monitors._NEVER_FIRE_AT)
        self.assertTrue(
            any(m == "DELETE" for m, _ in api_calls),
            f"expected the DELETE call; got {api_calls}",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
