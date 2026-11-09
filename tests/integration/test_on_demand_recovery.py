"""Isolated restart exercise for on-demand crew recovery.

Uses FakePodmanClient and an in-memory registry so the exercise never touches
operator containers. It covers startup reconciliation, health readiness,
tracked schedule and Captain wakeups, dormant work, and explicit recovery.
"""

from __future__ import annotations

import asyncio
import os
import time
import unittest
from unittest.mock import MagicMock, patch

from tests.fakes import FakePodmanClient


class TestOnDemandRecoveryRestartExercise(unittest.TestCase):
    def setUp(self):
        # Reuse the unit suite's dependency stubs when this isolated exercise is
        # run in a minimal checkout without the transport's optional packages.
        import tests.unit.conftest  # noqa: F401
        import transport.lifecycle as life
        import transport.monitors as monitors
        import transport.registry as reg_mod
        from transport.launcher import _launcher
        from transport.registry import registry
        with patch.dict(os.environ, {"GA_FILE_SECRET": "isolated-restart-exercise"}):
            import transport.server as server

        self.life = life
        self.monitors = monitors
        self.reg_mod = reg_mod
        self.server = server
        self.launcher = _launcher
        self.registry = registry
        self.podman = FakePodmanClient()
        self.podman._req = MagicMock(return_value=[])
        now = time.time()
        self.now = now

        self.crews = {
            "due-schedule": {
                "container": "gs-due-schedule", "volume": "vol-due",
                "home_volume": "home-due", "cookie": "old-due",
                "status": "running", "dashboard_port": 64058,
                "schedules": [{
                    "job_id": "job-due", "name": "due",
                    "interval_secs": 3600, "next_fire_at": now - 1,
                    "agent": "ghost", "message": "run due work", "enabled": True,
                }],
            },
            "stale-schedule": {
                "container": "gs-stale-schedule", "volume": "vol-stale",
                "home_volume": "home-stale", "cookie": "old-stale",
                "status": "stopped", "schedules": [{
                    "job_id": "job-stale", "name": "stale-enabled-cache",
                    "interval_secs": 3600, "next_fire_at": now - 1,
                    "agent": "ghost", "message": "must stay paused", "enabled": True,
                }],
            },
            "due-captain": {
                "container": "gs-due-captain", "volume": "vol-captain",
                "home_volume": "home-captain", "cookie": "old-captain",
                "status": "stopped", "schedules": [{
                    "type": "captain", "enabled": True,
                    "interval_secs": 3600, "next_fire_at": now - 1,
                    "current_task_id": "captain-task",
                }],
            },
            "dormant": {
                "container": "gs-dormant", "volume": "vol-dormant",
                "home_volume": "home-dormant", "cookie": "old-dormant",
                "status": "running", "schedules": [
                    {
                        "job_id": "job-future", "name": "future",
                        "interval_secs": 3600, "next_fire_at": now + 3600,
                        "agent": "ghost", "message": "future work", "enabled": True,
                    },
                    {
                        "job_id": "job-disabled", "name": "disabled",
                        "interval_secs": 3600, "next_fire_at": now - 1,
                        "agent": "ghost", "message": "disabled work", "enabled": False,
                    },
                ],
            },
            "gateway-only": {
                "container": "gs-gateway-only", "volume": "vol-gateway-only",
                "home_volume": "home-gateway-only", "cookie": "old-gateway-only",
                "status": "stopped", "schedules": [],
            },
            "already-running": {
                "container": "gs-already-running", "volume": "vol-running",
                "home_volume": "home-running", "cookie": "old-running",
                "status": "running", "schedules": [],
            },
        }
        self.backing = {"crews": self.crews}
        for crew_id, crew in self.crews.items():
            self.podman.add_container(
                crew["container"], running=(crew_id == "already-running"),
            )

        self.gateway_crons = {
            "due-schedule": {"jobs": [{"id": "job-due", "enabled": True, "every_secs": 3600}]},
            "stale-schedule": {"jobs": [{"id": "job-stale", "enabled": False, "every_secs": 3600}]},
            "due-captain": {"jobs": []},
            "dormant": {"jobs": []},
            "gateway-only": {"jobs": [{
                "id": "gateway-only-job", "name": "gateway-owned",
                "enabled": True, "every_secs": 3600,
            }]},
        }

        with self.launcher._startup_events_lock:
            self.launcher._startup_events.clear()
            self.launcher._startup_generation.clear()
            self.launcher._crew_restart_outcomes.clear()
        with self.launcher._capacity_lock:
            self.launcher._start_reservations.clear()

    def _gateway_api(self, crew, method, path, **kwargs):
        container = getattr(crew, "container", None) or crew.get("container")
        crew_id = container.removeprefix("gs-")
        if method == "GET" and path == "/api/crons":
            return self.gateway_crons.get(crew_id, {"jobs": []})
        if method == "POST" and path == "/api/crons":
            return {"id": f"reseeded-{crew_id}"}
        return {}

    def _run_schedule_tick(self):
        with (
            patch.object(self.monitors.time, "sleep", side_effect=[None, StopIteration()]),
            patch.object(self.monitors.time, "time", return_value=self.now),
        ):
            try:
                self.monitors._schedule_monitor()
            except StopIteration:
                pass

    def _run_captain_tick(self, steer):
        with (
            patch.object(self.monitors.time, "sleep", side_effect=StopIteration()),
            patch.object(self.monitors.time, "time", return_value=self.now),
            patch.object(self.monitors, "_get_podman", return_value=self.podman),
            patch("transport.captain._read_sentinel_file", return_value=None),
            patch.object(self.monitors, "_steer_captain_checkin", steer),
        ):
            try:
                self.monitors._captain_monitor()
            except StopIteration:
                pass

    def test_startup_and_on_demand_recovery_with_multiple_crews(self):
        recovery_api = MagicMock(return_value={})
        api_calls = []

        def _recording_api(crew, method, path, **kwargs):
            api_calls.append((crew, method, path, kwargs))
            return self._gateway_api(crew, method, path, **kwargs)

        with (
            patch.object(self.life, "GA_MAX_ACTIVE_CREWS", 10),
            patch.object(self.reg_mod, "_load_registry", return_value=self.backing),
            patch.object(self.reg_mod, "_save_registry"),
            patch.object(self.life, "_get_podman", return_value=self.podman),
            patch.object(self.life._cred_store, "get", return_value={"method": "api-key", "payload": b"synthetic-test-key"}),
            patch("transport.launcher._validate_static_credential"),
            patch.object(self.life, "_sweep_expired_logins"),
            patch.object(self.life, "_probe_gateway", return_value=True),
            patch.object(self.life, "_wait_gateway", return_value=True),
            patch.object(self.life, "_mint_cookie", side_effect=lambda _p, c, _u: f"fresh-{c}"),
            patch.object(self.life, "_mint_internal_cookie", return_value=None),
            patch.object(self.life, "_patch_crew_config") as patch_config,
            patch.object(self.life, "_deployed_agent_names", return_value=["ghost.json"]),
            patch.object(self.life, "_enroll_crew_members") as enroll,
            patch.object(self.life, "_write_dashboard_cookie"),
            patch.object(self.life, "_crew_api", side_effect=_recording_api),
            patch.object(self.life, "_crew_api_with_recovery", recovery_api),
            patch.object(self.reg_mod, "_touch_crew"),
        ):
            self.monitors.bind_lifecycle(
                ga_idle_timeout_secs=self.life.GA_IDLE_TIMEOUT_SECS,
                schedule_monitor_interval=1,
                ensure_crew_running=self.life._ensure_crew_running,
                crew_api=self.life._crew_api,
                crew_api_with_recovery=self.life._crew_api_with_recovery,
                mint_cookie=self.life._mint_cookie,
            )

            # Startup reconciliation is read-only with respect to existing
            # stopped containers, and health readiness does not wait for them.
            self.life._reconcile_registry()
            self.assertEqual(self.podman.calls_for("container_start"), [])
            health = asyncio.run(self.server._handle_health(None))
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.body, b"ok")
            self.assertEqual(self.crews["due-schedule"]["status"], "stopped")
            self.assertEqual(self.crews["dormant"]["status"], "stopped")
            self.assertEqual(self.crews["due-schedule"]["dashboard_port"], 64058)
            self.assertEqual(self.crews["due-schedule"]["volume"], "vol-due")
            self.assertEqual(self.crews["due-schedule"]["home_volume"], "home-due")

            self._run_schedule_tick()
            self.assertEqual(self.crews["due-schedule"]["status"], "running")
            self.assertEqual(self.crews["stale-schedule"]["status"], "running")
            self.assertFalse(self.crews["stale-schedule"]["schedules"][0]["enabled"])
            self.assertEqual(self.crews["due-captain"]["status"], "stopped")
            self.assertEqual(self.crews["dormant"]["status"], "stopped")
            self.assertEqual(self.crews["gateway-only"]["status"], "stopped")
            self.assertEqual(self.crews["already-running"]["status"], "running")
            self.assertEqual(
                [call[1:] for call in self.podman.calls_for("container_start")],
                [
                    ("gs-due-schedule",), ("gs-due-schedule",),
                    ("gs-stale-schedule",), ("gs-stale-schedule",),
                ],
            )
            self.assertTrue(any(
                call.args[1:4] == ("due-schedule", "POST", "/api/spawn")
                for call in recovery_api.call_args_list
            ))
            self.assertFalse(any(
                call.args[1:4] == ("stale-schedule", "POST", "/api/spawn")
                for call in recovery_api.call_args_list
            ))

            stale_generation = self.launcher._startup_generation["stale-schedule"]
            self._run_schedule_tick()
            self.assertEqual(
                self.launcher._startup_generation["stale-schedule"], stale_generation,
            )

            # A due Captain check-in uses the same guarded recovery path; its
            # future tracked work remains dormant when another crew is woken.
            steer = MagicMock()
            self._run_captain_tick(steer)
            self.assertEqual(self.crews["due-captain"]["status"], "running")
            steer.assert_called_once()
            self.assertEqual(self.crews["dormant"]["status"], "stopped")

            # An explicit operation wakes a future/disabled schedule crew. The
            # future item is reseeded in the gateway, while disabled work is
            # left dormant and does not dispatch.
            self.life._ensure_crew_running(dict(self.crews["dormant"]), "dormant")
            self.assertEqual(self.crews["dormant"]["status"], "running")
            self.assertFalse(self.crews["dormant"]["schedules"][1]["enabled"])
            self.assertEqual(recovery_api.call_count, 1)

            # Gateway-only schedules become observable only after an explicit
            # wake and are left gateway-owned instead of copied into the
            # transport's tracked schedule list.
            self.life._ensure_crew_running(dict(self.crews["gateway-only"]), "gateway-only")
            self.assertEqual(self.crews["gateway-only"]["status"], "running")
            self.assertEqual(self.crews["gateway-only"]["schedules"], [])
            self.assertTrue(any(
                crew.get("container") == "gs-gateway-only"
                and method == "GET" and path == "/api/crons"
                for crew, method, path, _kwargs in api_calls
            ))

            self.assertEqual(self.launcher._start_reservations, {})
            self.assertEqual(patch_config.call_count, 5)
            self.assertEqual(enroll.call_count, 5)


if __name__ == "__main__":
    unittest.main()
