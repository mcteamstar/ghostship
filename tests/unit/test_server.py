"""Unit tests for ``transport.server`` — MCP tools, routes, middleware, proxy.

TRN-85: migration target for classes testing the MCP tool surface
(``crews``, ``launch``, ``dispatch``, ``pickup``, ``steer``, ``nuke``,
``captain``, ``schedule``, ``evac``, ``supply``, ``resource_*``), the login
state machine routes (``_handle_login_post``/``_get``, ``_handle_logout_post``),
the bearer-auth middleware, and the crew proxy handlers.

Patch rule: patch ``server.<name>`` for names resolved in server's body (the
call site of a lifecycle/academy function imported by name). Patch
``lifecycle.<dep>`` / ``academy.<dep>`` for a dependency called two levels deep
inside the lifecycle/academy function (e.g. mock ``lifecycle._http`` inside a
``_crew_api_with_recovery`` path, ``lifecycle._crew_api as api`` for pickup).
Legitimate two-level patches (server call-site + lifecycle internal dep) are
NOT the dual-patch anti-pattern and are kept.

Call-site notes for the migrated classes (design §2):
- ``dispatch`` / ``steer`` / ``schedule`` / ``pickup`` reach the gateway through
  ``_crew_api_with_recovery`` (lifecycle), which calls ``_crew_api`` from
  lifecycle's own namespace → mock ``lifecycle._crew_api as api``. The
  ``_require_crew`` / ``_ensure_crew_running`` / ``_get_podman`` /
  ``_read_all_mail_*`` names are called by name from server's namespace →
  patch ``server.X``. The TRN-71 ``server._crew_api`` /
  ``lifecycle._require_crew`` … shadow dual-patches are dropped.
- ``resource_jobs`` calls **bare** ``_crew_api`` (not the recovery wrapper) and
  ``_load_registry`` directly from server's namespace → patch ``server._crew_api``
  and ``server._load_registry``.
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import Mock, patch

from tests.unit.helpers import server, lifecycle, academy  # noqa: F401


class PersonaValidationTests(unittest.TestCase):
    def test_dispatch_accepts_all_personas(self) -> None:
        crew = {"container": "gs-demo"}
        for agent in server.PERSONA_NAMES:
            with (
                self.subTest(agent=agent),
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server, "_ensure_crew_running", return_value=crew),
                patch.object(lifecycle, "_crew_api", return_value={"id": "task"}) as api,
            ):
                result = server.dispatch("do work", agent=agent, crew_id="demo")

            self.assertEqual(result["status"], "dispatched")
            self.assertEqual(api.call_args.kwargs["json"]["agent"], agent)

    def test_schedule_accepts_all_personas(self) -> None:
        crew = {"container": "gs-demo"}
        for agent in server.PERSONA_NAMES:
            with (
                self.subTest(agent=agent),
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server, "_ensure_crew_running", return_value=crew),
                patch.object(lifecycle, "_crew_api", return_value={"id": "job"}) as api,
            ):
                result = server.schedule(
                    "job", "do work", crew_id="demo", interval=60, agent=agent
                )

            self.assertEqual(result["status"], "scheduled")
            self.assertEqual(api.call_args.kwargs["json"]["agent"], agent)

    def test_rejected_agents_do_not_lookup_or_call_crew(self) -> None:
        rejected = ("spec-ops", "kirocrew-default", "custom-agent", "unknown")
        for agent in rejected:
            with self.subTest(agent=agent):
                with (
                    patch.object(server, "_require_crew") as require,
                    patch.object(server, "_ensure_crew_running") as ensure,
                    patch.object(lifecycle, "_crew_api") as api,
                ):
                    dispatched = server.dispatch("do work", agent=agent, crew_id="demo")
                    scheduled = server.schedule(
                        "job", "do work", crew_id="demo", interval=60, agent=agent
                    )

                self.assertIn("Invalid agent", dispatched["error"])
                self.assertIn("Invalid agent", scheduled["error"])
                require.assert_not_called()
                ensure.assert_not_called()
                api.assert_not_called()


class TaskOrchestrationTests(unittest.TestCase):
    CREW = {"container": "gs-demo"}

    def _steer_with_api(self, responses: list[dict], *, force: bool) -> tuple[dict, Mock]:
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", side_effect=responses) as api,
        ):
            result = server.steer("task", "follow up", crew_id="demo", force=force)
        return result, api

    def test_dispatch_requests_a_dedicated_retained_run(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value={"id": "task"}) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo")

        self.assertEqual(result["task_id"], "task")
        api.assert_called_once_with(
            self.CREW,
            "POST",
            "/api/spawn",
            json={"task": "do work", "agent": "ghost", "keep": True},
        )

    def test_force_steer_deletes_before_continuing_a_running_task(self) -> None:
        calls: list[tuple[str, str, dict]] = []

        def api(_crew: dict, method: str, path: str, **kwargs: object) -> dict:
            calls.append((method, path, kwargs))
            if method == "GET":
                return {"done": False}
            if method == "DELETE":
                return {"ok": True, "cancelled": True}
            return {"id": "continued-task"}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", side_effect=api),
        ):
            result = server.steer("task", "follow up", crew_id="demo", force=True)

        self.assertEqual(result, {
            "task_id": "continued-task",
            "crew_id": "demo",
            "action": "force_redeployed",
            "message": "follow up",
        })
        self.assertEqual(
            [(method, path) for method, path, _ in calls],
            [
                ("GET", "/api/spawn/task"),
                ("DELETE", "/api/spawn/task"),
                ("POST", "/api/spawn/task/continue"),
            ],
        )
        self.assertEqual(calls[1][2], {})
        self.assertEqual(calls[2][2], {"json": {"task": "follow up"}})

    def test_force_on_done_task_is_identical_to_plain_continue(self) -> None:
        forced, forced_api = self._steer_with_api(
            [{"done": True}, {"id": "continued-task"}], force=True
        )
        plain, plain_api = self._steer_with_api(
            [{"done": True}, {"id": "continued-task"}], force=False
        )

        expected = {
            "task_id": "continued-task",
            "crew_id": "demo",
            "action": "redeployed",
            "message": "follow up",
        }
        self.assertEqual(forced, expected)
        self.assertEqual(plain, expected)
        self.assertEqual(forced_api.call_args_list, plain_api.call_args_list)
        self.assertEqual(
            [call.args[1:] for call in forced_api.call_args_list],
            [
                ("GET", "/api/spawn/task"),
                ("POST", "/api/spawn/task/continue"),
            ],
        )

    def test_plain_steer_of_running_task_still_posts_to_steer(self) -> None:
        result, api = self._steer_with_api([{"done": False}, {}], force=False)

        self.assertEqual(result["action"], "steered")
        self.assertEqual(api.call_args_list[0].args[1:], ("GET", "/api/spawn/task"))
        self.assertEqual(
            api.call_args_list[1].args[1:], ("POST", "/api/spawn/task/steer")
        )
        self.assertEqual(api.call_args_list[1].kwargs, {"json": {"message": "follow up"}})

    def test_plain_steer_of_done_task_still_continues(self) -> None:
        result, api = self._steer_with_api(
            [{"done": True}, {"id": "continued-task"}], force=False
        )

        self.assertEqual(result["action"], "redeployed")
        self.assertEqual(api.call_args_list[0].args[1:], ("GET", "/api/spawn/task"))
        self.assertEqual(
            api.call_args_list[1].args[1:], ("POST", "/api/spawn/task/continue")
        )
        self.assertEqual(api.call_args_list[1].kwargs, {"json": {"task": "follow up"}})


class PickupTimeoutTests(unittest.TestCase):
    """Tests for the unified pickup with timeout_secs, mail state, and early-return."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    @staticmethod
    def _task_response(done: bool, agent: str = "ghost", elapsed: int = 7) -> dict:
        return {
            "id": "task-1",
            "agent": agent,
            "done": done,
            "turns": 2,
            "last_tool": "shell",
            "elapsed": elapsed,
            "result": "finished" if done else "",
            "error": "",
            "outcome": "success" if done else "",
        }

    def test_pickup_timeout_zero_returns_immediately_single_task(self) -> None:
        """5.1 — pickup with timeout_secs=0 returns immediately for single-task."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value=self._task_response(False)) as api,
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "sleep") as sleep,
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=0)

        self.assertFalse(result["done"])
        self.assertEqual(result["crew_id"], "demo")
        self.assertEqual(result["task_id"], "task-1")
        # No sleep should be called when timeout_secs=0
        sleep.assert_not_called()
        # Only one API call (no polling loop)
        api.assert_called_once()

    def test_pickup_timeout_zero_returns_immediately_list_all(self) -> None:
        """5.1 — pickup with timeout_secs=0 returns immediately for list-all."""
        agents = [{"id": "a", "done": False, "task": "t1", "agent": "ghost", "elapsed": 5}]
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value={"agents": agents}) as api,
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "sleep") as sleep,
        ):
            result = server.pickup(crew_id="demo", timeout_secs=0)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["crew_id"], "demo")
        self.assertIn("tasks", result)
        sleep.assert_not_called()
        api.assert_called_once()

    def test_pickup_polls_until_task_completes(self) -> None:
        """5.2 — pickup with timeout_secs > 0 polls until task completes."""
        clock = [0.0]

        def advance(seconds: float) -> None:
            clock[0] += seconds

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(
                lifecycle,
                "_crew_api",
                side_effect=[self._task_response(False), self._task_response(True)],
            ) as api,
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(server.time, "sleep", side_effect=advance) as sleep,
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=60)

        self.assertTrue(result["done"])
        self.assertEqual(result["result"], "finished")
        self.assertEqual(api.call_count, 2)
        sleep.assert_called_once()

    def test_pickup_timeout_elapses_returns_not_done(self) -> None:
        """5.3 — pickup timeout elapses, returns not-done state without error."""
        clock = [0.0]

        def advance(seconds: float) -> None:
            clock[0] += seconds

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value=self._task_response(False)),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(server.time, "sleep", side_effect=advance),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=5)

        self.assertFalse(result["done"])
        self.assertEqual(result["crew_id"], "demo")
        # Should not have "error" key set (or empty string)
        self.assertEqual(result.get("reason"), "timeout")
        self.assertFalse(result.get("error"))

    def test_pickup_poll_cap_fires_before_caller_timeout(self) -> None:
        """5.3b — internal GA_PICKUP_MAX_POLL_SECS cap fires before caller timeout_secs;
        response is a normal dict with reason='timeout', not a transport error."""
        clock = [0.0]

        def advance(seconds: float) -> None:
            clock[0] += seconds

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value=self._task_response(False)),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(server.time, "sleep", side_effect=advance),
            patch.object(server, "GA_PICKUP_MAX_POLL_SECS", 5),
        ):
            # caller requests 60s, but the internal cap is 5s
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=60)

        # Must be a normal dict — no exception raised
        self.assertIsInstance(result, dict)
        self.assertFalse(result["done"])
        self.assertEqual(result.get("reason"), "timeout")
        self.assertFalse(result.get("error"))
        self.assertEqual(result["crew_id"], "demo")

    def test_pickup_mail_counts_present_single_task(self) -> None:
        """5.4 — mail counts present in single-task response."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value=self._task_response(True, agent="ghost")),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={"ghost": 3, "admiral": 1}),
            patch.object(server, "_read_all_mail_subjects", return_value={"ghost": ["hello"], "admiral": ["order1"]}),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=0)

        self.assertEqual(result["agent_mail"], 3)
        self.assertEqual(result["admiral_mail"], 1)
        self.assertEqual(result["ghost_subjects"], ["hello"])
        self.assertEqual(result["admiral_subjects"], ["order1"])

    def test_pickup_mail_counts_present_list_all(self) -> None:
        """5.4 — mail counts present in list-all response."""
        agents = [{"id": "a", "done": True, "task": "t1", "agent": "ghost", "elapsed": 5}]

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value={"agents": agents}),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={"ghost": 2, "admiral": 1}),
            patch.object(server, "_read_all_mail_subjects", return_value={"ghost": ["done"], "admiral": ["check"]}),
        ):
            result = server.pickup(crew_id="demo", timeout_secs=0)

        self.assertIn("mail_summary", result)
        self.assertEqual(result["mail_summary"]["ghost"], 2)
        self.assertEqual(result["admiral_mail"], 1)
        self.assertEqual(result["ghost_subjects"], ["done"])
        self.assertEqual(result["admiral_subjects"], ["check"])

    def test_pickup_admiral_mail_early_return(self) -> None:
        """5.5 — Admiral mail early-return sets reason='admiral_mail'."""
        clock = [0.0]
        call_count = [0]

        def advance(seconds: float) -> None:
            clock[0] += seconds

        def mock_read_all_mail_counts(_podman, _container):
            # First call: initial capture (admiral=0).
            # Second call: first poll iteration (admiral=0).
            # Third call: second poll iteration (admiral=1 — new mail arrived).
            call_count[0] += 1
            if call_count[0] <= 2:
                return {}
            return {"admiral": 1}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value=self._task_response(False)),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", side_effect=mock_read_all_mail_counts),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(server.time, "sleep", side_effect=advance),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=60)

        self.assertFalse(result["done"])
        self.assertEqual(result["reason"], "admiral_mail")
        self.assertEqual(result["admiral_mail"], 1)


class ResourceJobsTests(unittest.TestCase):
    """Tests for resource_jobs()."""

    def test_resource_jobs_aggregates_across_crews(self) -> None:
        """4.6 — resource_jobs collects jobs from multiple running crews."""
        reg = {
            "crews": {
                "crew-a": {"container": "gs-crew-a", "status": "running", "cookie": "c1"},
                "crew-b": {"container": "gs-crew-b", "status": "running", "cookie": "c2"},
            }
        }
        crew_a_jobs = {"jobs": [
            {"id": "j1", "name": "check", "schedule": "every 60s", "agent": "ghost", "enabled": True, "last_run_ts": "now", "last_status": "ok"},
        ]}
        crew_b_jobs = {"jobs": [
            {"id": "j2", "name": "report", "schedule": "0 9 * * 1", "agent": "wraith", "enabled": False, "last_run_ts": None, "last_status": None},
        ]}

        def api(crew, method, path, **kwargs):
            if crew["container"] == "gs-crew-a":
                return crew_a_jobs
            return crew_b_jobs

        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.resource_jobs()

        self.assertIn("## crew-a", result)
        self.assertIn("## crew-b", result)
        self.assertIn("j1", result)
        self.assertIn("j2", result)
        self.assertIn("check", result)
        self.assertIn("report", result)

    def test_resource_jobs_no_running_crews(self) -> None:
        """4.6 — resource_jobs shows stopped crews with registry data (TRN-29)."""
        reg = {"crews": {"stopped": {"container": "gs-stopped", "status": "stopped"}}}
        with (
            patch.object(server, "_load_registry", return_value=reg),
        ):
            result = server.resource_jobs()

        self.assertIn("## stopped", result)
        self.assertIn("No scheduled jobs.", result)

    def test_resource_jobs_handles_crew_error_gracefully(self) -> None:
        """4.6 — resource_jobs reports crew connection errors inline."""
        reg = {"crews": {"bad": {"container": "gs-bad", "status": "running", "cookie": "c"}}}

        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_crew_api", side_effect=RuntimeError("connection refused")),
        ):
            result = server.resource_jobs()

        self.assertIn("## bad", result)
        self.assertIn("error", result)
        self.assertIn("connection refused", result)

    def test_resource_jobs_empty_jobs_for_crew(self) -> None:
        """4.6 — resource_jobs shows 'No scheduled jobs' for crew without jobs."""
        reg = {"crews": {"empty": {"container": "gs-empty", "status": "running", "cookie": "c"}}}
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_crew_api", return_value={"jobs": []}),
        ):
            result = server.resource_jobs()

        self.assertIn("## empty", result)
        self.assertIn("No scheduled jobs", result)


if __name__ == "__main__":
    unittest.main()
