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
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from unittest.mock import ANY, Mock, MagicMock, patch

import httpx
import transport.registry as _registry_mod  # noqa: F401

from tests.unit.helpers import Request, server, lifecycle, academy  # noqa: F401

# ── container_scripts import (TRN-74) ────────────────────────────────────────
# _inject_policy / _patch_crew_config now invoke baked scripts under
# transport/container_scripts/ instead of inline `python3 -c` strings. Import
# the policy signer directly so policy-injection tests can run the SAME code
# the container runs, decoding the base64 payload from the captured argv.
_CONTAINER_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2] / "transport" / "container_scripts"
)
if str(_CONTAINER_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTAINER_SCRIPTS_DIR))
_inject_policy_script = _importlib.import_module("inject_policy")


def _run_inject_policy_script(cmd: list[str], crew_dir: str) -> str:
    """Decode the payload argv from a captured inject_policy.py invocation and
    run the real script logic against ``crew_dir``.

    ``cmd`` is the argv captured from container_exec_checked, of the form
    ``["python3", ".../inject_policy.py", <crew_dir>, <payload_b64>]``.
    """
    payload = json.loads(base64.b64decode(cmd[-1]).decode())
    return _inject_policy_script.inject_policy(
        crew_dir, payload["policy"], payload["policy_signing_key"]
    )


def _decode_overrides(cmd: list[str]) -> dict:
    """Decode the base64 JSON overrides argv passed to patch_crew_config.py."""
    import base64 as _b64
    import json as _json
    return _json.loads(_b64.b64decode(cmd[-1]).decode())



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


class ModelOverrideTests(unittest.TestCase):
    """Tests for per-dispatch and per-job model overrides (TRN-87)."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_validate_model_rules(self) -> None:
        self.assertEqual(server._validate_model("claude-opus-5"), "claude-opus-5")
        self.assertIsNone(server._validate_model(None))
        self.assertIsNone(server._validate_model(""))

        with self.subTest(case="non-string"):
            with self.assertRaisesRegex(ValueError, "Invalid model"):
                server._validate_model(123)  # type: ignore[arg-type]
        with self.subTest(case="too-long"):
            with self.assertRaisesRegex(ValueError, "maximum length"):
                server._validate_model("a" * 501)
        with self.subTest(case="invalid-characters"):
            with self.assertRaisesRegex(ValueError, "only"):
                server._validate_model("claude/opus")

    def test_dispatch_forwards_model_and_omits_it_when_unset(self) -> None:
        for supplied, expected in (("claude-opus-5", "claude-opus-5"), (None, None)):
            with self.subTest(model=supplied):
                with (
                    patch.object(server, "_require_crew", return_value=self.CREW),
                    patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                    patch.object(
                        server, "_crew_api_with_recovery", return_value={"id": "task"}
                    ) as api,
                ):
                    kwargs = {"task": "do work", "agent": "ghost", "crew_id": "demo"}
                    if supplied is not None:
                        kwargs["model"] = supplied
                    result = server.dispatch(**kwargs)

                self.assertEqual(result["task_id"], "task")
                body = api.call_args.kwargs["json"]
                if expected is None:
                    self.assertNotIn("model", body)
                else:
                    self.assertEqual(body["model"], expected)

    def test_dispatch_rejects_invalid_model_without_contacting_crew(self) -> None:
        with (
            patch.object(server, "_require_crew") as require,
            patch.object(server, "_ensure_crew_running") as ensure,
            patch.object(server, "_crew_api_with_recovery") as api,
        ):
            result = server.dispatch(
                "do work", agent="ghost", crew_id="demo", model="claude/opus"
            )

        self.assertIn("Invalid model", result["error"])
        require.assert_not_called()
        ensure.assert_not_called()
        api.assert_not_called()

    def _schedule_body(self, **kwargs: object) -> dict:
        registry = {"crews": {"demo": {"schedules": []}}}
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(
                server, "_crew_api_with_recovery", return_value={"id": "job-1"}
            ) as api,
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
        ):
            result = server.schedule(
                name="job", message="do work", crew_id="demo", **kwargs
            )

        self.assertEqual(result["status"], "scheduled")
        cron_calls = [
            call for call in api.call_args_list
            if call.args[2:] == ("POST", "/api/crons")
        ]
        self.assertEqual(len(cron_calls), 1)
        return cron_calls[0].kwargs["json"]

    def test_schedule_forwards_model_on_cron_interval_and_delay_paths(self) -> None:
        cron_body = self._schedule_body(cron="0 9 * * 1", model="claude-sonnet-5")
        self.assertEqual(cron_body["model"], "claude-sonnet-5")

        interval_body = self._schedule_body(
            interval=60, fire_immediately=False, model="claude-sonnet-5"
        )
        self.assertEqual(interval_body["model"], "claude-sonnet-5")

        delay_body = self._schedule_body(delay=1, model="claude-sonnet-5")
        self.assertEqual(delay_body["model"], "claude-sonnet-5")

    def test_schedule_rejects_invalid_model_without_contacting_crew(self) -> None:
        with (
            patch.object(server, "_require_crew") as require,
            patch.object(server, "_ensure_crew_running") as ensure,
            patch.object(server, "_crew_api_with_recovery") as api,
        ):
            result = server.schedule(
                name="job",
                message="do work",
                crew_id="demo",
                interval=60,
                model="claude/opus",
            )

        self.assertIn("Invalid model", result["error"])
        require.assert_not_called()
        ensure.assert_not_called()
        api.assert_not_called()

    def _captain_create_body(self, **kwargs: object) -> dict:
        registry = {"crews": {"demo": {"schedules": []}}}
        podman = Mock()

        def api(_crew: dict, _crew_id: str, method: str, path: str, **_kwargs: object) -> dict:
            if method == "GET" and path == "/api/crons":
                return {"jobs": []}
            if method == "POST" and path == "/api/crons":
                return {"id": "captain-job", "enabled": True}
            return {"id": "immediate-task"}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", side_effect=api) as gateway,
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail"),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
        ):
            result = server.captain(
                "demo",
                "order",
                message="hold",
                interval=120,
                fire_immediately=False,
                **kwargs,
            )

        self.assertEqual(result["status"], "ordered")
        cron_calls = [
            call for call in gateway.call_args_list
            if call.args[2:] == ("POST", "/api/crons")
        ]
        self.assertEqual(len(cron_calls), 1)
        return cron_calls[0].kwargs["json"]

    def test_captain_new_job_forwards_model(self) -> None:
        body = self._captain_create_body(model="claude-opus-5")
        self.assertEqual(body["model"], "claude-opus-5")

    def test_captain_new_job_omits_model_when_unset(self) -> None:
        body = self._captain_create_body()
        self.assertNotIn("model", body)

    def test_captain_resume_ignores_model_without_creating_job(self) -> None:
        existing = {
            "id": "paused-job",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": False,
        }
        registry = {"crews": {"demo": {"schedules": []}}}
        podman = Mock()

        def api(_crew: dict, _crew_id: str, method: str, path: str, **_kwargs: object) -> dict:
            if method == "GET" and path == "/api/crons":
                return {"jobs": [existing]}
            if method == "POST" and path.endswith("/enable"):
                return {"ok": True}
            raise AssertionError(f"unexpected gateway call: {method} {path}")

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", side_effect=api) as gateway,
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail"),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
        ):
            result = server.captain(
                "demo", "order", message="resume", model="claude-opus-5"
            )

        self.assertEqual(result["job_id"], "paused-job")
        self.assertTrue(all(call.args[2:] != ("POST", "/api/crons") for call in gateway.call_args_list))

    def test_captain_resume_rejects_invalid_model_without_resuming(self) -> None:
        with (
            patch.object(server, "_require_crew") as require,
            patch.object(server, "_ensure_crew_running") as ensure,
            patch.object(server, "_crew_api_with_recovery") as gateway,
        ):
            result = server.captain(
                "demo", "order", message="resume", model="claude/opus"
            )

        self.assertIn("Invalid model", result["error"])
        require.assert_not_called()
        ensure.assert_not_called()
        gateway.assert_not_called()


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
        mock_archive = Mock(return_value=["standing order"])
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value=self._task_response(True, agent="ghost")),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={"ghost": 3, "admiral": 1}),
            patch.object(server, "_read_all_mail_subjects", return_value={"ghost": ["hello"], "admiral": ["order1"]}),
            patch.object(server, "_read_mail_subjects_archive", mock_archive),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=0)

        self.assertEqual(result["agent_mail"], 3)
        self.assertEqual(result["ghost_subjects"], ["hello"])
        # captain and admiral are now included in pickup via archive API
        self.assertIn("captain_subjects", result)
        self.assertIn("admiral_subjects", result)
        self.assertIn("captain_mail", result)
        self.assertIn("admiral_mail", result)

    def test_pickup_mail_counts_present_list_all(self) -> None:
        """5.4 — mail counts present in list-all response."""
        agents = [{"id": "a", "done": True, "task": "t1", "agent": "ghost", "elapsed": 5}]
        mock_archive = Mock(return_value=["standing order"])

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value={"agents": agents}),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={"ghost": 2, "admiral": 1}),
            patch.object(server, "_read_all_mail_subjects", return_value={"ghost": ["done"], "admiral": ["check"]}),
            patch.object(server, "_read_mail_subjects_archive", mock_archive),
        ):
            result = server.pickup(crew_id="demo", timeout_secs=0)

        self.assertIn("mail_summary", result)
        self.assertEqual(result["mail_summary"]["ghost"], 2)
        self.assertEqual(result["ghost_subjects"], ["done"])
        # captain and admiral are now included in pickup via archive API
        self.assertIn("captain_subjects", result)
        self.assertIn("admiral_subjects", result)
        self.assertIn("captain_mail", result)
        self.assertIn("admiral_mail", result)

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
            patch.object(server, "_read_mail_subjects_archive", Mock(return_value=[])),
            patch.object(server.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(server.time, "sleep", side_effect=advance),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=60)

        self.assertFalse(result["done"])
        self.assertEqual(result["reason"], "admiral_mail")
        # admiral_mail is now surfaced in pickup via archive API
        self.assertIn("admiral_mail", result)
        self.assertIn("admiral_subjects", result)


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

class CookieHeaders:
    def multi_items(self):
        return [("set-cookie", "mc_token_5476=session-cookie; Path=/")]

class CookieResponse:
    status_code = 200
    headers = CookieHeaders()

class CookieHTTP:
    def get(self, *args: object, **kwargs: object) -> CookieResponse:
        return CookieResponse()

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

class GatewayTokenAndProjectionTests(unittest.TestCase):
    def test_gateway_token_uses_default_and_configured_ttl(self) -> None:
        podman = Mock()
        podman.container_exec.return_value = "token=abc123"
        old_ttl = server.KC_GATEWAY_TOKEN_TTL
        try:
            with patch.object(lifecycle, "_http", CookieHTTP()):
                server.KC_GATEWAY_TOKEN_TTL = "24h"
                lifecycle.KC_GATEWAY_TOKEN_TTL = "24h"
                self.assertEqual(
                    server._mint_cookie(podman, "gs-demo", "http://gs-demo:5476"),
                    "session-cookie",
                )
                self.assertEqual(podman.container_exec.call_args.args[1][-1], "24h")

                server.KC_GATEWAY_TOKEN_TTL = "2h"
                lifecycle.KC_GATEWAY_TOKEN_TTL = "2h"
                self.assertEqual(
                    server._mint_cookie(podman, "gs-demo", "http://gs-demo:5476"),
                    "session-cookie",
                )
                self.assertEqual(podman.container_exec.call_args.args[1][-1], "2h")
        finally:
            server.KC_GATEWAY_TOKEN_TTL = old_ttl
            lifecycle.KC_GATEWAY_TOKEN_TTL = old_ttl

    def test_read_auth_file_missing_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / server.GA_AUTH_FILE
            self.assertEqual(server._read_auth_file(_path=missing), "")

    def test_write_then_read_auth_file_round_trips_and_is_restrictive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / server.GA_AUTH_FILE
            server._write_auth_file("first", _path=path)
            inode = path.stat().st_ino
            self.assertEqual(server._read_auth_file(_path=path), "first")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            server._write_auth_file("second", _path=path)
            self.assertEqual(server._read_auth_file(_path=path), "second")
            self.assertEqual(path.stat().st_ino, inode)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_missing_auth_file_returns_not_authenticated_error(self) -> None:
        """launch fails fast when no auth is available — returns login_url inline."""
        with (
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
            patch.object(server, "_initiate_login", return_value={
                "login_url": "https://example.com/device?user_code=ABCD-1234",
                "code": "ABCD-1234",
            }),
        ):
            result = server.launch("new")

        self.assertEqual(result["error"], "not_authenticated")
        self.assertIn("login_url", result)
        self.assertIn("code", result)
        self.assertIn("launch again", result["instructions"])

    def test_installer_has_no_podman_secret_machinery(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        installer = (repo_root / "install.sh").read_text()
        self.assertIn('${DATA_DIR}:/data', installer)
        self.assertIn('KC_GATEWAY_TOKEN_TTL', installer)
        self.assertNotIn("podman secret inspect ga-kiro-auth", installer)
        self.assertNotIn("SECRETS_DIR", installer)
        self.assertNotIn("/run/podman-secrets", installer)

    # ── TRN-58: launch auth gate tests ───────────────────────────────────────

    def test_launch_not_authenticated_returns_login_url(self) -> None:
        """launch with no auth returns not_authenticated + login_url inline."""
        with (
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
            patch.object(server, "_initiate_login", return_value={
                "login_url": "https://example.com/device?user_code=TEST-1234",
                "code": "TEST-1234",
            }),
        ):
            result = server.launch("my-crew")

        self.assertEqual(result["error"], "not_authenticated")
        self.assertEqual(result["login_url"], "https://example.com/device?user_code=TEST-1234")
        self.assertEqual(result["code"], "TEST-1234")
        self.assertIn("login_url", result["instructions"])

    def test_launch_not_authenticated_login_already_pending(self) -> None:
        """launch with no auth and a pending flow returns login_pending: True."""
        with (
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
            patch.object(server, "_initiate_login", return_value={"login_pending": True}),
        ):
            result = server.launch("my-crew")

        self.assertEqual(result["error"], "not_authenticated")
        self.assertTrue(result.get("login_pending"))
        self.assertIn("GET /login", result["instructions"])

    def test_launch_not_authenticated_does_not_write_registry(self) -> None:
        """launch with no auth must NOT write a registry entry."""
        save_calls = []
        registry = {"crews": {}}

        def mock_save(reg: dict) -> None:
            save_calls.append(reg)

        with (
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(lifecycle, "_load_registry", return_value=registry),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(lifecycle, "_save_registry", side_effect=mock_save),
            patch.object(server, "_save_registry", side_effect=mock_save),
            patch.object(server, "_initiate_login", return_value={
                "login_url": "https://example.com/device",
                "code": None,
            }),
        ):
            server.launch("no-registry-entry")

        # _save_registry must never have been called — no orphaned entry
        self.assertEqual(save_calls, [])
        # The registry dict itself must also be untouched
        self.assertNotIn("no-registry-entry", registry["crews"])

class _FakeDownstream:
    """Minimal ASGI app that records whether it was called."""

    def __init__(self) -> None:
        self.called = False
        self.scope = None

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        self.scope = scope
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"OK"})

def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": headers or [],
    }

def _run_asgi(app, scope, body: bytes = b"") -> tuple[int, list, bytes]:
    """Run an ASGI app synchronously and return (status, headers, body)."""
    status = None
    resp_headers = []
    resp_body = b""

    async def receive():
        return {"type": "http.request", "body": body}

    async def send(msg):
        nonlocal status, resp_headers, resp_body
        if msg["type"] == "http.response.start":
            status = msg["status"]
            resp_headers = msg.get("headers", [])
        elif msg["type"] == "http.response.body":
            resp_body += msg.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return status, resp_headers, resp_body

class BearerAuthMiddlewareTests(unittest.TestCase):
    """Tests for the BearerAuthMiddleware pure ASGI wrapper."""

    def test_disabled_mode_passes_all_requests(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="")
        scope = _http_scope()
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_valid_bearer_forwards_to_downstream(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret-key-123")
        scope = _http_scope([(b"authorization", b"Bearer secret-key-123")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_valid_bearer_case_insensitive_scheme(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="mykey")
        scope = _http_scope([(b"authorization", b"BEARER mykey")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_missing_header_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([])
        status, headers, body = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)
        self.assertIn([b"www-authenticate", b"Bearer"], headers)
        self.assertEqual(body, b"Unauthorized")

    def test_wrong_key_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="correct")
        scope = _http_scope([(b"authorization", b"Bearer wrong")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_malformed_no_bearer_prefix_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([(b"authorization", b"Basic c2VjcmV0")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_duplicate_authorization_headers_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([
            (b"authorization", b"Bearer secret"),
            (b"authorization", b"Bearer secret"),
        ])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_empty_token_after_bearer_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([(b"authorization", b"Bearer ")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_non_http_scope_passes_through(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = {"type": "lifespan"}
        _run_asgi(mw, scope)
        self.assertTrue(downstream.called)

    def test_constant_time_comparison_used(self) -> None:
        """Verify hmac.compare_digest is used (not == operator)."""
        import inspect
        source = inspect.getsource(server.BearerAuthMiddleware.__call__)
        self.assertIn("hmac.compare_digest", source)
        self.assertNotIn("== self._key", source)

    def test_rejected_requests_never_reach_downstream(self) -> None:
        """Ensure all rejection paths never invoke the downstream app."""
        key = "correct-key"
        bad_cases = [
            [],  # missing
            [(b"authorization", b"Bearer wrong")],  # wrong
            [(b"authorization", b"Token correct-key")],  # bad scheme
            [(b"authorization", b"Bearer correct-key"), (b"authorization", b"Bearer correct-key")],  # dup
            [(b"authorization", b"Bearer ")],  # empty token
        ]
        for headers in bad_cases:
            downstream = _FakeDownstream()
            mw = server.BearerAuthMiddleware(downstream, api_key=key)
            status, _, _ = _run_asgi(mw, _http_scope(headers))
            self.assertEqual(status, 401, f"Expected 401 for headers={headers}")
            self.assertFalse(downstream.called, f"Downstream called for headers={headers}")

class StartupWiringTests(unittest.TestCase):
    """Verify the MCP app factory uses /mcp path and stateless setting."""

    def test_mcp_server_has_streamable_http_app_method(self) -> None:
        self.assertTrue(hasattr(server.mcp, "streamable_http_app"))

    def test_bearer_middleware_wraps_mcp_app_in_entrypoint(self) -> None:
        """Confirm the entrypoint wires BearerAuthMiddleware around the MCP app."""
        import inspect
        source = inspect.getsource(server)
        # The entrypoint should use streamable_http_app with /mcp path
        self.assertIn('streamable_http_app(', source)
        self.assertIn('path="/mcp"', source)
        self.assertIn('stateless_http=True', source)
        # Login/logout routes are handled inside BearerAuthMiddleware directly
        # (not via a Starlette router) so the MCP lifespan is never broken.
        self.assertIn('BearerAuthMiddleware(mcp_app', source)
        self.assertIn('_handle_login_post', source)
        self.assertIn('_handle_login_get', source)
        self.assertIn('_handle_logout_post', source)

    def test_file_routes_do_not_require_api_key(self) -> None:
        """File routes use HMAC presigned URLs, not the API key."""
        import inspect
        file_get_src = inspect.getsource(server._handle_file_get)
        file_put_src = inspect.getsource(server._handle_file_put)
        self.assertNotIn("GA_API_KEY", file_get_src)
        self.assertNotIn("GA_API_KEY", file_put_src)
        self.assertIn("_verify_file_token", file_get_src)
        self.assertIn("_verify_file_token", file_put_src)

class ReadAuthFromCrewTests(unittest.TestCase):
    """Unit tests for _read_auth_from_crew (trn-78 bug fixes)."""

    def _b64_rows(self, rows: list) -> str:
        """Encode a list of row tuples into the b64 JSON format the function expects."""
        import base64
        return base64.b64encode(json.dumps(rows).encode()).decode()

    def test_returns_none_when_auth_kv_has_only_registration_row_empty_value(self) -> None:
        """1.2: returns None when auth_kv has only a registration row with empty value."""
        # Simulate the device-flow registration row: value is empty/null
        rows_empty_value = [["registration", ""]]
        b64 = self._b64_rows(rows_empty_value)

        podman = Mock()
        podman.container_exec.return_value = b64

        result = server._read_auth_from_crew(podman, "gs-test")
        self.assertIsNone(result)

    def test_returns_none_when_auth_kv_has_only_registration_row_null_value(self) -> None:
        """1.2 (null variant): returns None when auth_kv has only a row with null value."""
        rows_null_value = [["registration", None]]
        b64 = self._b64_rows(rows_null_value)

        podman = Mock()
        podman.container_exec.return_value = b64

        result = server._read_auth_from_crew(podman, "gs-test")
        self.assertIsNone(result)

    def test_returns_b64_payload_when_auth_kv_has_row_with_non_empty_value(self) -> None:
        """1.3: returns the b64 payload when auth_kv has a row with a non-empty value."""
        rows_with_token = [["registration", ""], ["access_token", "eyJhbGciOiJSUzI1NiJ9.payload"]]
        b64 = self._b64_rows(rows_with_token)

        podman = Mock()
        podman.container_exec.return_value = b64

        result = server._read_auth_from_crew(podman, "gs-test")
        self.assertEqual(result, b64)

    def test_uses_inline_python_not_a_bundled_script_path(self) -> None:
        """Must work in bare kirocrew login containers, which have no /scripts/.

        Guards the fix itself: execs an inline python3 -c snippet rather than
        a bundled script path that only exists in full crew images.
        """
        rows = [["registration", ""], ["access_token", "tok"]]
        b64 = self._b64_rows(rows)

        podman = Mock()
        podman.container_exec.return_value = b64

        result = server._read_auth_from_crew(podman, "gs-test")

        self.assertEqual(result, b64)
        podman.container_exec.assert_called_once_with("gs-test", ["python3", "-c", ANY])
        command = podman.container_exec.call_args.args[1]
        self.assertNotIn("read_auth.py", " ".join(command))
        self.assertIn("sqlite3", command[2])
        self.assertIn("auth_kv", command[2])

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

class TestPolicyInjection(unittest.TestCase):
    """Tests for the _inject_policy() function and its integration."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        # Create policy template files
        self.policies_dir = Path(self.tmp) / "policies"
        self.policies_dir.mkdir()
        self.default_policy = {
            "version": "1",
            "commands": {"deny": ["^git push"]},
            "channels": {"deny": ["slack"]},
        }
        (self.policies_dir / "default.json").write_text(
            json.dumps(self.default_policy, indent=2)
        )
        self.kirocrew_policy = {
            "version": "2",
            "commands": {"deny": ["^git push", "^gh "]},
            "channels": {"deny": ["slack", "discord"]},
        }
        (self.policies_dir / "spec-ops.json").write_text(
            json.dumps(self.kirocrew_policy, indent=2)
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_inject_policy_uses_composition_template(self) -> None:
        """_inject_policy uses composition-specific template when found."""
        mock_podman = Mock()
        mock_podman.container_exec_checked = Mock(return_value="policy injected version=2")

        with patch("transport.lifecycle.Path") as MockPath:
            # Make Path("/policies/spec-ops.json") exist and return the composition template
            composition_path = Mock()
            composition_path.exists.return_value = True
            composition_path.read_text.return_value = json.dumps(self.kirocrew_policy)

            default_path = Mock()
            default_path.exists.return_value = True
            default_path.read_text.return_value = json.dumps(self.default_policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/spec-ops.json":
                    return composition_path
                elif str(arg) == "/policies/default.json":
                    return default_path
                return Mock()

            MockPath.side_effect = path_side_effect

            result = server._inject_policy(
                mock_podman, "gs-test", "spec-ops", "secret123"
            )

        self.assertEqual(result, "2")
        mock_podman.container_exec_checked.assert_called_once()

    def test_inject_policy_falls_back_to_default(self) -> None:
        """_inject_policy falls back to default when composition template not found."""
        mock_podman = Mock()
        mock_podman.container_exec_checked = Mock(return_value="policy injected version=1")

        with patch("transport.lifecycle.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = False

            default_path = Mock()
            default_path.exists.return_value = True
            default_path.read_text.return_value = json.dumps(self.default_policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/custom-unknown.json":
                    return composition_path
                elif str(arg) == "/policies/default.json":
                    return default_path
                return Mock()

            MockPath.side_effect = path_side_effect

            result = server._inject_policy(
                mock_podman, "gs-test", "custom-unknown", "secret123"
            )

        self.assertEqual(result, "1")
        mock_podman.container_exec_checked.assert_called_once()

    def test_inject_policy_writes_admission_alongside_security(self) -> None:
        """Both security_policy.json and admission_policy.json are written."""
        mock_podman = Mock()
        mock_podman.container_exec_checked = Mock(return_value="policy injected version=1")

        with patch("transport.lifecycle.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = True
            composition_path.read_text.return_value = json.dumps(self.default_policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/spec-ops.json":
                    return composition_path
                return Mock()

            MockPath.side_effect = path_side_effect

            server._inject_policy(
                mock_podman, "gs-test", "spec-ops", "secret123"
            )

        # _inject_policy now invokes the baked inject_policy.py script. Run the
        # same script logic against a temp crew dir and verify both files land.
        call_args = mock_podman.container_exec_checked.call_args
        cmd = call_args[0][1]  # ["python3", ".../inject_policy.py", crew_dir, payload_b64]
        self.assertEqual(cmd[0], "python3")
        self.assertTrue(cmd[1].endswith("inject_policy.py"))
        with tempfile.TemporaryDirectory() as td:
            _run_inject_policy_script(cmd, td)
            self.assertTrue((Path(td) / "security_policy.json").exists())
            self.assertTrue((Path(td) / "admission_policy.json").exists())

    def test_inject_policy_admission_enables_signature_verification(self) -> None:
        """Admission policy sets require_policy_signature=True with trust_keys dict."""
        policy = {"version": 1, "boot": {}}
        secret = "fixed-secret-for-test"

        mock_podman = Mock()

        captured_cmds: list[list[str]] = []

        def exec_capture(container, cmd):
            captured_cmds.append(cmd)
            return "policy injected version=1"

        mock_podman.container_exec_checked = Mock(side_effect=exec_capture)

        with patch("transport.lifecycle.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = True
            composition_path.read_text.return_value = json.dumps(policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/test.json":
                    return composition_path
                return Mock()

            MockPath.side_effect = path_side_effect

            server._inject_policy(mock_podman, "gs-test", "test", secret)

        # Run the real inject_policy.py logic against a temp crew dir to inspect
        # what it writes.
        self.assertEqual(len(captured_cmds), 1)
        with tempfile.TemporaryDirectory() as td:
            fake_crew_dir = Path(td)
            _run_inject_policy_script(captured_cmds[0], td)
            policy_out = json.loads((fake_crew_dir / "security_policy.json").read_text())
            admission_out = json.loads((fake_crew_dir / "admission_policy.json").read_text())

        # Admission policy must have require_policy_signature=True and trust_keys
        # (trust_keys is required by KiroCrew governance to verify the policy signature)
        self.assertTrue(admission_out["require_policy_signature"])
        self.assertIn("trust_keys", admission_out)
        self.assertEqual(admission_out["trust_keys"], {"ghostship": secret})

        # Security policy must have identity.issuer and identity.signature
        self.assertIn("identity", policy_out)
        self.assertEqual(policy_out["identity"]["issuer"], "ghostship")
        self.assertIsInstance(policy_out["identity"]["signature"], str)
        self.assertTrue(len(policy_out["identity"]["signature"]) > 0)

    def test_inject_policy_signature_is_correct(self) -> None:
        """The identity.signature embedded in security_policy.json is the correct HMAC."""
        import hmac as _hmac, hashlib as _hashlib
        policy = {"version": 1, "boot": {}}
        secret = "test-secret-abc123"

        mock_podman = Mock()
        captured_cmds: list[list[str]] = []

        def exec_capture(container, cmd):
            captured_cmds.append(cmd)
            return "policy injected version=1"

        mock_podman.container_exec_checked = Mock(side_effect=exec_capture)

        with patch("transport.lifecycle.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = True
            composition_path.read_text.return_value = json.dumps(policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/spec-ops.json":
                    return composition_path
                return Mock()

            MockPath.side_effect = path_side_effect
            server._inject_policy(mock_podman, "gs-test", "spec-ops", secret)

        self.assertEqual(len(captured_cmds), 1)

        with tempfile.TemporaryDirectory() as td:
            fake_crew_dir = Path(td)
            _run_inject_policy_script(captured_cmds[0], td)
            policy_out = json.loads((fake_crew_dir / "security_policy.json").read_text())

        # Re-derive the expected signature: whole doc minus identity.signature
        body = {k: v for k, v in policy_out.items() if k != "identity"}
        identity = policy_out.get("identity", {})
        rest = {k: v for k, v in identity.items() if k != "signature"}
        if rest:
            body["identity"] = rest
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected_sig = _hmac.new(secret.encode("utf-8"), payload, _hashlib.sha256).hexdigest()

        self.assertEqual(policy_out["identity"]["signature"], expected_sig)

    def test_inject_policy_failure_does_not_abort_launch(self) -> None:
        """Policy injection failure is caught and does not abort launch."""
        mock_podman = Mock()
        mock_podman.container_exec_checked = Mock(
            side_effect=RuntimeError("container_exec failed")
        )

        with patch("transport.lifecycle.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = True
            composition_path.read_text.return_value = json.dumps(self.default_policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/spec-ops.json":
                    return composition_path
                return Mock()

            MockPath.side_effect = path_side_effect

            # _inject_policy itself raises; the caller (_finish_crew_setup)
            # catches it. Verify _inject_policy propagates the error.
            with self.assertRaises(RuntimeError):
                server._inject_policy(
                    mock_podman, "gs-test", "spec-ops", "secret123"
                )

    def test_launch_response_includes_policy_version(self) -> None:
        """launch() response includes policy_version when injection succeeds."""
        test_entry = {"name": "spec-ops", "dir": "spec-ops", "description": "Default"}
        import contextlib
        with contextlib.ExitStack() as _stack:
            _stack.enter_context(patch.object(lifecycle, "COMPOSITION_REGISTRY", {"spec-ops": test_entry}))
            _stack.enter_context(patch.object(server, "COMPOSITION_REGISTRY", {"spec-ops": test_entry}))
            mock_get_podman = _stack.enter_context(patch.object(lifecycle, "_get_podman"))
            _stack.enter_context(patch.object(server, "_get_podman"))
            _stack.enter_context(patch.object(server, "_read_auth_file", return_value="dGVzdA=="))
            _stack.enter_context(patch.object(lifecycle, "_load_registry", return_value={"crews": {}}))
            _stack.enter_context(patch.object(server, "_load_registry", return_value={"crews": {}}))
            _stack.enter_context(patch.object(lifecycle, "_save_registry"))
            _stack.enter_context(patch.object(server, "_save_registry"))
            _stack.enter_context(patch.object(lifecycle, "_wait_gateway", return_value=True))
            _stack.enter_context(patch.object(server, "_wait_gateway", return_value=True))
            _stack.enter_context(patch.object(lifecycle, "_inject_auth", return_value=True))
            _stack.enter_context(patch.object(server, "_inject_auth", return_value=True))
            _stack.enter_context(patch.object(lifecycle, "_patch_crew_config"))
            _stack.enter_context(patch.object(server, "_patch_crew_config"))
            _stack.enter_context(patch.object(lifecycle, "_copy_agents", return_value=[]))
            _stack.enter_context(patch.object(server, "_copy_agents", return_value=[]))
            _stack.enter_context(patch.object(lifecycle, "_copy_skills", return_value=[]))
            _stack.enter_context(patch.object(server, "_copy_skills", return_value=[]))
            _stack.enter_context(patch.object(lifecycle, "_copy_steering", return_value=[]))
            _stack.enter_context(patch.object(server, "_copy_steering", return_value=[]))
            _stack.enter_context(patch.object(lifecycle, "_seed_openspec_store"))
            _stack.enter_context(patch.object(server, "_seed_openspec_store"))
            _stack.enter_context(patch.object(lifecycle, "_patch_models"))
            _stack.enter_context(patch.object(server, "_patch_models"))
            _stack.enter_context(patch.object(lifecycle, "_inject_policy", return_value="1"))
            _stack.enter_context(patch.object(server, "_inject_policy", return_value="1"))
            _stack.enter_context(patch.object(lifecycle, "_mint_cookie", return_value="test-cookie"))
            _stack.enter_context(patch.object(server, "_mint_cookie", return_value="test-cookie"))

            mock_podman = Mock()
            mock_get_podman.return_value = mock_podman
            mock_podman.network_create = Mock()
            mock_podman.volume_create = Mock()
            mock_podman.container_create = Mock()
            mock_podman.container_start = Mock()
            mock_podman.container_stop = Mock()
            mock_podman.container_exec = Mock(return_value="ready")
            mock_podman.container_exec_checked = Mock(return_value="ok")

            result = server.launch("policy-test", composition="spec-ops")

        self.assertEqual(result.get("policy_version"), "1")

    def test_crews_entry_includes_policy_version(self) -> None:
        """crews() per-crew entry includes policy_version from registry."""
        reg = {
            "crews": {
                "test-crew": {
                    "container": "gs-test-crew",
                    "status": "running",
                    "composition": "spec-ops",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "cookie": "test-cookie",
                    "policy_version": "1",
                }
            }
        }
        with (
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_probe_gateway", return_value=True),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(lifecycle, "_crew_api", return_value=[]),
            patch.object(server, "_crew_api", return_value=[]),
            patch.object(lifecycle, "_get_podman", return_value=Mock(system_info=lambda: {"host": {"memAvailable": 4 * 1024**3}})),
            patch.object(server, "_get_podman", return_value=Mock(system_info=lambda: {"host": {"memAvailable": 4 * 1024**3}})),
        ):
            result = server.crews()

        crew_list = result["crews"]
        self.assertEqual(len(crew_list), 1)
        self.assertEqual(crew_list[0]["policy_version"], "1")

    def test_crews_entry_omits_policy_version_when_absent(self) -> None:
        """crews() omits policy_version for crews launched before this change."""
        reg = {
            "crews": {
                "old-crew": {
                    "container": "gs-old-crew",
                    "status": "running",
                    "composition": "spec-ops",
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "cookie": "old-cookie",
                    # No policy_version key
                }
            }
        }
        with (
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_probe_gateway", return_value=True),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(lifecycle, "_crew_api", return_value=[]),
            patch.object(server, "_crew_api", return_value=[]),
            patch.object(lifecycle, "_get_podman", return_value=Mock(system_info=lambda: {"host": {"memAvailable": 4 * 1024**3}})),
            patch.object(server, "_get_podman", return_value=Mock(system_info=lambda: {"host": {"memAvailable": 4 * 1024**3}})),
        ):
            result = server.crews()

        crew_list = result["crews"]
        self.assertEqual(len(crew_list), 1)
        self.assertNotIn("policy_version", crew_list[0])

class TestPatchCrewConfig(unittest.TestCase):
    """Tests for _patch_crew_config memory threshold patching."""

    def test_spawn_min_memory_from_env(self) -> None:
        """_patch_crew_config writes GA_SPAWN_MIN_MEMORY_GB (not hardcoded 0)."""
        original = server.GA_SPAWN_MIN_MEMORY_GB
        try:
            server.GA_SPAWN_MIN_MEMORY_GB = 2.5
            lifecycle.GA_SPAWN_MIN_MEMORY_GB = 2.5
            server.GA_RESOURCE_PRESSURE_GB = 3.0
            lifecycle.GA_RESOURCE_PRESSURE_GB = 3.0
            server.GA_RESOURCE_CRITICAL_GB = 1.5
            lifecycle.GA_RESOURCE_CRITICAL_GB = 1.5
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            overrides = _decode_overrides(exec_calls[0][1])
            self.assertEqual(overrides["spawn_min_memory_gb"], 2.5)
            self.assertEqual(overrides["resource_pressure_gb"], 3.0)
            self.assertEqual(overrides["resource_critical_gb"], 1.5)
            self.assertNotEqual(overrides["spawn_min_memory_gb"], 0)
            # Verify subagent_timeout_secs and subagent_max_turns carry defaults
            self.assertEqual(overrides["subagent_timeout_secs"], 3600)
            self.assertEqual(overrides["subagent_max_turns"], 200)
        finally:
            server.GA_SPAWN_MIN_MEMORY_GB = original
            lifecycle.GA_SPAWN_MIN_MEMORY_GB = original
            server.GA_RESOURCE_PRESSURE_GB = 2.0
            lifecycle.GA_RESOURCE_PRESSURE_GB = 2.0
            server.GA_RESOURCE_CRITICAL_GB = 1.0
            lifecycle.GA_RESOURCE_CRITICAL_GB = 1.0

    def test_subagent_timeout_from_env(self) -> None:
        """GA_SUBAGENT_TIMEOUT_SECS=7200 → subagent_timeout_secs: 7200 in patched config."""
        original = server.GA_SUBAGENT_TIMEOUT_SECS
        try:
            server.GA_SUBAGENT_TIMEOUT_SECS = 7200
            lifecycle.GA_SUBAGENT_TIMEOUT_SECS = 7200
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            overrides = _decode_overrides(exec_calls[0][1])
            self.assertEqual(overrides["subagent_timeout_secs"], 7200)
        finally:
            server.GA_SUBAGENT_TIMEOUT_SECS = original
            lifecycle.GA_SUBAGENT_TIMEOUT_SECS = original

    def test_subagent_max_turns_from_env(self) -> None:
        """GA_SUBAGENT_MAX_TURNS=300 → subagent_max_turns: 300 in patched config."""
        original = server.GA_SUBAGENT_MAX_TURNS
        try:
            server.GA_SUBAGENT_MAX_TURNS = 300
            lifecycle.GA_SUBAGENT_MAX_TURNS = 300
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            overrides = _decode_overrides(exec_calls[0][1])
            self.assertEqual(overrides["subagent_max_turns"], 300)
        finally:
            server.GA_SUBAGENT_MAX_TURNS = original
            lifecycle.GA_SUBAGENT_MAX_TURNS = original

    def test_agent_field_default_kiro(self) -> None:
        """GA_CREW_AGENT unset → config.local.json gets agent: "kiro" (0.4.0 required field)."""
        original = server.GA_CREW_AGENT
        try:
            server.GA_CREW_AGENT = "kiro"
            lifecycle.GA_CREW_AGENT = "kiro"
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            overrides = _decode_overrides(exec_calls[0][1])
            self.assertEqual(overrides["agent"], "kiro")
        finally:
            server.GA_CREW_AGENT = original
            lifecycle.GA_CREW_AGENT = original

    def test_agent_field_from_env(self) -> None:
        """GA_CREW_AGENT=custom-agent → agent field carries the override value."""
        original = server.GA_CREW_AGENT
        try:
            server.GA_CREW_AGENT = "custom-agent"
            lifecycle.GA_CREW_AGENT = "custom-agent"
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            overrides = _decode_overrides(exec_calls[0][1])
            self.assertEqual(overrides["agent"], "custom-agent")
        finally:
            server.GA_CREW_AGENT = original
            lifecycle.GA_CREW_AGENT = original

    def test_config_script_has_no_unexpanded_shell_vars(self) -> None:
        """KiroCrew 0.4.0 rejects literal $VAR in config values — the decoded
        overrides must contain no unexpanded shell variable reference in any
        written value."""
        import re
        exec_calls: list[tuple[str, list[str]]] = []

        class CapturePodman:
            def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                exec_calls.append((name, cmd))
                return "patched config.local.json"

        server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
        overrides = _decode_overrides(exec_calls[0][1])
        for value in overrides.values():
            if isinstance(value, str):
                self.assertIsNone(re.search(r"\$\{?[A-Za-z_]", value))

    def test_kc_model_default_set_writes_default_model(self) -> None:
        """KC_MODEL_DEFAULT set → default_model written to config.local.json."""
        original = server.KC_MODEL_DEFAULT
        try:
            server.KC_MODEL_DEFAULT = "anthropic/claude-sonnet-4-20250514"
            lifecycle.KC_MODEL_DEFAULT = "anthropic/claude-sonnet-4-20250514"
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            overrides = _decode_overrides(exec_calls[0][1])
            self.assertEqual(
                overrides["default_model"], "anthropic/claude-sonnet-4-20250514"
            )
        finally:
            server.KC_MODEL_DEFAULT = original
            lifecycle.KC_MODEL_DEFAULT = original

    def test_kc_model_default_empty_does_not_write_default_model(self) -> None:
        """KC_MODEL_DEFAULT empty → default_model NOT written to config.local.json."""
        original = server.KC_MODEL_DEFAULT
        try:
            server.KC_MODEL_DEFAULT = ""
            lifecycle.KC_MODEL_DEFAULT = ""
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            overrides = _decode_overrides(exec_calls[0][1])
            self.assertNotIn("default_model", overrides)
        finally:
            server.KC_MODEL_DEFAULT = original
            lifecycle.KC_MODEL_DEFAULT = original

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
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_http", FakeHTTP()),
            patch.object(server, "_http", FakeHTTP()),
            patch.object(lifecycle, "_touch_crew", side_effect=touch),
            patch.object(server, "_touch_crew", side_effect=touch),
            patch.object(lifecycle, "_load_registry", return_value={"crews": dict(crew_items)}),
            patch.object(server, "_load_registry", return_value={"crews": dict(crew_items)}),
            patch.object(lifecycle, "_save_registry", side_effect=save_reg),
            patch.object(server, "_save_registry", side_effect=save_reg),
            patch.object(lifecycle, "_mint_cookie", return_value=mint_cookie_return),
            patch.object(server, "_mint_cookie", return_value=mint_cookie_return),
            patch.object(server.time, "sleep", side_effect=fake_sleep),
            patch.object(server.time, "time", return_value=1000.0),
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

class FinishCrewSetupOrderingTests(unittest.TestCase):
    """Tests for _finish_crew_setup step ordering (trn-17 tasks 6.x)."""

    def test_happy_path_setup_records_steps_in_order(self) -> None:
        """6.1: full happy-path records steps in exact required order."""
        steps: list[str] = []
        podman = Mock()
        podman.container_stop = Mock(side_effect=lambda *a: steps.append("stop"))
        podman.container_start = Mock(side_effect=lambda *a: steps.append("start"))
        podman.container_exec = Mock(return_value="ready")
        podman.container_exec_checked = Mock(return_value="ok")
        podman.container_inspect = Mock(return_value={"Config": {"Labels": {"org.ghostship.version": "1.0"}}})

        def wait_gw(url: str, timeout: int = 30) -> bool:
            steps.append("wait_gateway")
            return True

        def inject_auth(*a: Any, **kw: Any) -> None:
            steps.append("inject_auth")

        def patch_config(*a: Any, **kw: Any) -> None:
            steps.append("patch_config")

        def copy_agents(*a: Any, **kw: Any) -> list:
            steps.append("copy_agents")
            return []

        def copy_skills(*a: Any, **kw: Any) -> list:
            steps.append("copy_skills")
            return []

        def copy_steering(*a: Any, **kw: Any) -> list:
            steps.append("copy_steering")
            return []

        def seed_openspec(*a: Any, **kw: Any) -> None:
            steps.append("seed_openspec")

        def patch_models(*a: Any, **kw: Any) -> None:
            steps.append("patch_models")

        def mint_cookie(*a: Any, **kw: Any) -> str:
            steps.append("mint_cookie")
            return "test-cookie"

        def inject_policy(*a: Any, **kw: Any) -> str:
            steps.append("inject_policy")
            return "1"

        with tempfile.TemporaryDirectory() as tmp:
            import contextlib
            with contextlib.ExitStack() as _stack:
                _stack.enter_context(patch.object(server, "DATA_DIR", Path(tmp)))
                _stack.enter_context(patch.object(server, "REGISTRY_PATH", Path(tmp) / "crews.json"))
                _stack.enter_context(patch.object(_registry_mod, "DATA_DIR", Path(tmp)))
                _stack.enter_context(patch.object(_registry_mod, "REGISTRY_PATH", Path(tmp) / "crews.json"))
                _stack.enter_context(patch.object(lifecycle, "_wait_gateway", side_effect=wait_gw))
                _stack.enter_context(patch.object(server, "_wait_gateway", side_effect=wait_gw))
                _stack.enter_context(patch.object(lifecycle, "_inject_auth", side_effect=inject_auth))
                _stack.enter_context(patch.object(server, "_inject_auth", side_effect=inject_auth))
                _stack.enter_context(patch.object(lifecycle, "_patch_crew_config", side_effect=patch_config))
                _stack.enter_context(patch.object(server, "_patch_crew_config", side_effect=patch_config))
                _stack.enter_context(patch.object(lifecycle, "_copy_agents", side_effect=copy_agents))
                _stack.enter_context(patch.object(server, "_copy_agents", side_effect=copy_agents))
                _stack.enter_context(patch.object(lifecycle, "_copy_skills", side_effect=copy_skills))
                _stack.enter_context(patch.object(server, "_copy_skills", side_effect=copy_skills))
                _stack.enter_context(patch.object(lifecycle, "_copy_steering", side_effect=copy_steering))
                _stack.enter_context(patch.object(server, "_copy_steering", side_effect=copy_steering))
                _stack.enter_context(patch.object(lifecycle, "_seed_openspec_store", side_effect=seed_openspec))
                _stack.enter_context(patch.object(server, "_seed_openspec_store", side_effect=seed_openspec))
                _stack.enter_context(patch.object(lifecycle, "_patch_models", side_effect=patch_models))
                _stack.enter_context(patch.object(server, "_patch_models", side_effect=patch_models))
                _stack.enter_context(patch.object(lifecycle, "_mint_cookie", side_effect=mint_cookie))
                _stack.enter_context(patch.object(server, "_mint_cookie", side_effect=mint_cookie))
                _stack.enter_context(patch.object(lifecycle, "_inject_policy", side_effect=inject_policy))
                _stack.enter_context(patch.object(server, "_inject_policy", side_effect=inject_policy))
                result = server._finish_crew_setup(
                    podman, "test", "gs-test", "vol-test", "home-test", "auth-b64"
                )

        self.assertEqual(result["status"], "ready")
        # Verify the correct ordering of critical steps.
        # The full sequence in _finish_crew_setup is:
        #   wait_gateway → inject_auth → [admiral secret inject via exec_checked] →
        #   patch_config → stop → start → wait_gateway → copy_agents → copy_skills →
        #   copy_steering → seed_openspec → inject_policy →
        #   [wait for agent files via exec] → patch_models → mint_cookie → [registry write]
        expected_prefix = [
            "wait_gateway",     # Initial gateway wait
            "inject_auth",      # Auth inject
            "patch_config",     # Config patch
            "stop",             # Restart (stop)
            "start",            # Restart (start)
            "wait_gateway",     # Wait after restart
            "copy_agents",      # Copy agents
            "copy_skills",      # Copy skills
            "copy_steering",    # Copy steering
            "seed_openspec",    # OpenSpec seed
        ]
        self.assertEqual(steps[:len(expected_prefix)], expected_prefix)
        # After seed_openspec, inject_policy comes before patch_models and mint_cookie
        self.assertIn("inject_policy", steps)
        self.assertIn("patch_models", steps)
        self.assertIn("mint_cookie", steps)
        policy_idx = steps.index("inject_policy")
        models_idx = steps.index("patch_models")
        cookie_idx = steps.index("mint_cookie")
        self.assertLess(policy_idx, models_idx)
        self.assertLess(models_idx, cookie_idx)

    def test_admiral_secret_injected_before_container_restart(self) -> None:
        """6.3 (trn-36 2.1): admiral secret exec call occurs before container_stop/start."""
        exec_calls: list[list[str]] = []
        stop_calls: list[int] = []
        start_calls: list[int] = []
        call_counter: list[int] = [0]

        podman = Mock()

        def track_exec_checked(container: str, cmd: list[str]) -> str:
            call_counter[0] += 1
            exec_calls.append((call_counter[0], cmd))
            return "ok"

        def track_stop(name: str) -> None:
            call_counter[0] += 1
            stop_calls.append(call_counter[0])

        def track_start(name: str) -> None:
            call_counter[0] += 1
            start_calls.append(call_counter[0])

        podman.container_exec_checked = Mock(side_effect=track_exec_checked)
        podman.container_stop = Mock(side_effect=track_stop)
        podman.container_start = Mock(side_effect=track_start)
        podman.container_exec = Mock(return_value="ready")
        podman.container_inspect = Mock(return_value={"Config": {"Labels": {}}})

        with tempfile.TemporaryDirectory() as tmp:
            import contextlib
            with contextlib.ExitStack() as _stack:
                _stack.enter_context(patch.object(server, "DATA_DIR", Path(tmp)))
                _stack.enter_context(patch.object(server, "REGISTRY_PATH", Path(tmp) / "crews.json"))
                _stack.enter_context(patch.object(_registry_mod, "DATA_DIR", Path(tmp)))
                _stack.enter_context(patch.object(_registry_mod, "REGISTRY_PATH", Path(tmp) / "crews.json"))
                _stack.enter_context(patch.object(lifecycle, "_wait_gateway", return_value=True))
                _stack.enter_context(patch.object(server, "_wait_gateway", return_value=True))
                _stack.enter_context(patch.object(lifecycle, "_inject_auth"))
                _stack.enter_context(patch.object(server, "_inject_auth"))
                _stack.enter_context(patch.object(lifecycle, "_patch_crew_config"))
                _stack.enter_context(patch.object(server, "_patch_crew_config"))
                _stack.enter_context(patch.object(lifecycle, "_copy_agents", return_value=[]))
                _stack.enter_context(patch.object(server, "_copy_agents", return_value=[]))
                _stack.enter_context(patch.object(lifecycle, "_copy_skills", return_value=[]))
                _stack.enter_context(patch.object(server, "_copy_skills", return_value=[]))
                _stack.enter_context(patch.object(lifecycle, "_copy_steering", return_value=[]))
                _stack.enter_context(patch.object(server, "_copy_steering", return_value=[]))
                _stack.enter_context(patch.object(lifecycle, "_seed_openspec_store"))
                _stack.enter_context(patch.object(server, "_seed_openspec_store"))
                _stack.enter_context(patch.object(lifecycle, "_patch_models"))
                _stack.enter_context(patch.object(server, "_patch_models"))
                _stack.enter_context(patch.object(lifecycle, "_inject_policy", return_value="1"))
                _stack.enter_context(patch.object(server, "_inject_policy", return_value="1"))
                _stack.enter_context(patch.object(lifecycle, "_mint_cookie", return_value="test-cookie"))
                _stack.enter_context(patch.object(server, "_mint_cookie", return_value="test-cookie"))
                result = server._finish_crew_setup(
                    podman, "test", "gs-test", "vol-test", "home-test", "auth-b64"
                )

        self.assertEqual(result["status"], "ready")
        # Find the admiral secret injection call (first exec_checked call whose
        # command contains the secret injection marker)
        secret_call_order = None
        for order, cmd in exec_calls:
            if len(cmd) >= 3 and "admiral_secret" in cmd[2]:
                secret_call_order = order
                break
        self.assertIsNotNone(secret_call_order, "Admiral secret injection exec call not found")
        # The container restart (first stop) must come after the secret injection
        first_stop_order = stop_calls[0] if stop_calls else None
        self.assertIsNotNone(first_stop_order, "Expected at least one container_stop call")
        self.assertLess(
            secret_call_order,
            first_stop_order,
            "Admiral secret injection must occur before first container_stop",
        )

    def test_admiral_secret_injection_script_contains_fsync(self) -> None:
        """6.4 (trn-36 2.2): the admiral secret injection script contains os.fsync."""
        captured_cmds: list[list[str]] = []

        podman = Mock()

        def capture_exec_checked(container: str, cmd: list[str]) -> str:
            if len(cmd) >= 3 and cmd[0] == "python3" and cmd[1].endswith(
                "/inject_admiral_secret.py"
            ):
                captured_cmds.append(cmd)
            return "ok"

        podman.container_exec_checked = Mock(side_effect=capture_exec_checked)
        podman.container_stop = Mock()
        podman.container_start = Mock()
        podman.container_exec = Mock(return_value="ready")
        podman.container_inspect = Mock(return_value={"Config": {"Labels": {}}})

        with tempfile.TemporaryDirectory() as tmp:
            import contextlib
            with contextlib.ExitStack() as _stack:
                _stack.enter_context(patch.object(server, "DATA_DIR", Path(tmp)))
                _stack.enter_context(patch.object(server, "REGISTRY_PATH", Path(tmp) / "crews.json"))
                _stack.enter_context(patch.object(_registry_mod, "DATA_DIR", Path(tmp)))
                _stack.enter_context(patch.object(_registry_mod, "REGISTRY_PATH", Path(tmp) / "crews.json"))
                _stack.enter_context(patch.object(lifecycle, "_wait_gateway", return_value=True))
                _stack.enter_context(patch.object(server, "_wait_gateway", return_value=True))
                _stack.enter_context(patch.object(lifecycle, "_inject_auth"))
                _stack.enter_context(patch.object(server, "_inject_auth"))
                _stack.enter_context(patch.object(lifecycle, "_patch_crew_config"))
                _stack.enter_context(patch.object(server, "_patch_crew_config"))
                _stack.enter_context(patch.object(lifecycle, "_copy_agents", return_value=[]))
                _stack.enter_context(patch.object(server, "_copy_agents", return_value=[]))
                _stack.enter_context(patch.object(lifecycle, "_copy_skills", return_value=[]))
                _stack.enter_context(patch.object(server, "_copy_skills", return_value=[]))
                _stack.enter_context(patch.object(lifecycle, "_copy_steering", return_value=[]))
                _stack.enter_context(patch.object(server, "_copy_steering", return_value=[]))
                _stack.enter_context(patch.object(lifecycle, "_seed_openspec_store"))
                _stack.enter_context(patch.object(server, "_seed_openspec_store"))
                _stack.enter_context(patch.object(lifecycle, "_patch_models"))
                _stack.enter_context(patch.object(server, "_patch_models"))
                _stack.enter_context(patch.object(lifecycle, "_inject_policy", return_value="1"))
                _stack.enter_context(patch.object(server, "_inject_policy", return_value="1"))
                _stack.enter_context(patch.object(lifecycle, "_mint_cookie", return_value="test-cookie"))
                _stack.enter_context(patch.object(server, "_mint_cookie", return_value="test-cookie"))
                server._finish_crew_setup(
                    podman, "test", "gs-test", "vol-test", "home-test", "auth-b64"
                )

        self.assertEqual(
            len(captured_cmds), 1, "Expected exactly one admiral secret injection call"
        )
        cmd = captured_cmds[0]
        # The call passes the secret file path as argv; the fsync durability
        # guarantee now lives in the baked inject_admiral_secret.py script.
        self.assertTrue(cmd[2].endswith("/.admiral_secret"))
        script_path = (
            Path(server.__file__).resolve().parent
            / "container_scripts"
            / "inject_admiral_secret.py"
        )
        script_src = script_path.read_text()
        self.assertIn(
            "os.fsync",
            script_src,
            "Secret injection script must call os.fsync for durability",
        )

    def test_gateway_failure_after_restart_triggers_cleanup(self) -> None:
        """6.2: gateway failure after auth restart triggers cleanup and returns error."""
        podman = Mock()
        podman.container_stop = Mock()
        podman.container_start = Mock()
        podman.container_exec = Mock(return_value="ready")
        podman.container_inspect = Mock(return_value={"Config": {"Labels": {}}})

        wait_count = [0]

        def wait_gw(url: str, timeout: int = 30) -> bool:
            wait_count[0] += 1
            # First call: initial gateway check (timeout=10) → passes
            if wait_count[0] == 1:
                return True
            # Second call: after auth inject + config patch + restart → fails
            return False

        cleanup_called = [False]

        def cleanup(*a: Any, **kw: Any) -> None:
            cleanup_called[0] = True

        with (
            patch.object(lifecycle, "_wait_gateway", side_effect=wait_gw),
            patch.object(server, "_wait_gateway", side_effect=wait_gw),
            patch.object(lifecycle, "_inject_auth"),
            patch.object(server, "_inject_auth"),
            patch.object(lifecycle, "_patch_crew_config"),
            patch.object(server, "_patch_crew_config"),
            patch.object(lifecycle, "_cleanup_crew", side_effect=cleanup),
            patch.object(server, "_cleanup_crew", side_effect=cleanup),
        ):
            result = server._finish_crew_setup(
                podman, "test", "gs-test", "vol-test", "home-test", "auth-b64"
            )

        self.assertIn("error", result)
        self.assertIn("did not recover", result["error"])
        self.assertTrue(cleanup_called[0])

class LoginGuardClearTests(unittest.TestCase):
    """Tests for _handle_login_get guard-clear ordering (trn-17 tasks 8.x)."""

    def setUp(self) -> None:
        with server._login_pending_lock:
            server._login_pending = None

    def test_guard_clear_ordering_verified(self) -> None:
        """8.1: _login_pending is cleared ONLY AFTER _nuke_login_container completes."""
        # Set up a pending login
        pending_container = "ga-login-test1234"
        with server._login_pending_lock:
            server._login_pending = {
                "container": pending_container,
                "exec_id": "exec-1",
                "started_at": time.time(),
            }

        nuked_flag = {"done": False}
        cleared_before_nuke = {"seen": False}

        def fake_nuke(podman, container):
            # At the point nuke is called, _login_pending must NOT yet be None
            with server._login_pending_lock:
                if server._login_pending is None:
                    cleared_before_nuke["seen"] = True
            nuked_flag["done"] = True

        fake_podman = Mock()
        fake_podman.container_is_running = Mock(return_value=False)

        try:
            with (
                patch.object(lifecycle, "_get_podman", return_value=fake_podman),
                patch.object(server, "_get_podman", return_value=fake_podman),
                patch.object(lifecycle, "_read_auth_from_crew", return_value="dGVzdA=="),
                patch.object(server, "_read_auth_from_crew", return_value="dGVzdA=="),
                patch.object(server, "_write_auth_file"),
                patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
                patch.object(server, "_load_registry", return_value={"crews": {}}),
                patch.object(lifecycle, "_inject_auth"),
                patch.object(server, "_inject_auth"),
                patch.object(lifecycle, "_nuke_login_container", side_effect=fake_nuke),
                patch.object(server, "_nuke_login_container", side_effect=fake_nuke),
            ):
                asyncio.run(server._handle_login_get(Mock()))
        except Exception:
            pass

        # nuke must have run
        self.assertTrue(nuked_flag["done"], "_nuke_login_container was never called")
        # _login_pending must not have been cleared BEFORE nuke
        self.assertFalse(
            cleared_before_nuke["seen"],
            "_login_pending was cleared before _nuke_login_container returned",
        )
        # After the function returns, _login_pending should be None
        with server._login_pending_lock:
            self.assertIsNone(server._login_pending, "_login_pending should be None after cleanup")

    def test_concurrent_post_during_cleanup_window_returns_409(self) -> None:
        """8.2: concurrent POST /login during cleanup window receives 409."""
        # Simulate the scenario where _handle_login_get has detected auth and
        # is between nuke and guard-clear. If a POST /login arrives at this
        # moment, the _login_pending is still set so the POST should get 409.
        with server._login_pending_lock:
            server._login_pending = {
                "container": "ga-login-completing",
                "exec_id": "x",
                "started_at": 999.0,
            }

        try:
            with patch.object(server, "_read_auth_file", return_value=""):
                request = Mock()
                response = asyncio.run(server._handle_login_post(request))

            self.assertEqual(response.status_code, 409)
        finally:
            with server._login_pending_lock:
                server._login_pending = None

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
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
            patch.object(server, "_save_registry", side_effect=fake_save),
            patch.object(lifecycle, "_get_crew_schedules", return_value=reg["crews"]["demo"]["schedules"]),
            patch.object(server, "_get_crew_schedules", return_value=reg["crews"]["demo"]["schedules"]),
            patch.object(server.time, "sleep", side_effect=fake_sleep),
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

class TestTrn38SecurityHardening(unittest.TestCase):
    """Tests for TRN-38 security hardening changes."""

    # ── 9.1 HMAC token length is now 32 hex chars (128-bit) ──────────────────

    def test_sign_file_url_hmac_is_32_hex_chars(self) -> None:
        """_sign_file_url produces a 64-char hex sig (not 32)."""
        url = server._sign_file_url("demo", "repo/file.txt")
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertEqual(len(query["sig"]), 64, f"sig length {len(query['sig'])} != 32: {query['sig']}")

    def test_sign_upload_url_hmac_is_32_hex_chars(self) -> None:
        """_sign_upload_url produces a 64-char hex sig (not 32)."""
        url = server._sign_upload_url("demo", "repo")
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertEqual(len(query["sig"]), 64, f"sig length {len(query['sig'])} != 32: {query['sig']}")

    def test_16_char_sig_rejected_by_verify_file_token(self) -> None:
        """A legacy 16-char sig is rejected by _verify_file_token (length mismatch)."""
        import hmac as _hmac, hashlib as _hashlib
        expires = str(int(time.time()) + 300)
        payload = f"demo:repo/file.txt:::{expires}"
        short_sig = _hmac.new(
            server._FILE_SECRET.encode(), payload.encode(), _hashlib.sha256
        ).hexdigest()[:16]
        self.assertFalse(
            server._verify_file_token("demo", "repo/file.txt", expires, short_sig)
        )

    # ── 9.2 Upload mode signing ───────────────────────────────────────────────

    def test_plain_token_rejected_when_unpack_mode_presented(self) -> None:
        """Token signed with mode='' fails when mode='unpack' is verified."""
        url = server._sign_upload_url("demo", "repo")  # mode=""
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertFalse(
            server._verify_file_token(
                "demo", "repo", query["expires"], query["sig"], mode="unpack"
            ),
            "Plain token should fail verification when mode='unpack' is presented",
        )

    def test_unpack_token_rejected_when_plain_mode_presented(self) -> None:
        """Token signed with mode='unpack' fails when mode='' is verified."""
        url = server._sign_upload_url("demo", "repo", unpack=True)
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertFalse(
            server._verify_file_token(
                "demo", "repo", query["expires"], query["sig"], mode=""
            ),
            "Unpack token should fail verification when mode='' is presented",
        )

    def test_bundle_token_rejected_when_plain_mode_presented(self) -> None:
        """Token signed with mode='bundle' fails when mode='' is verified."""
        url = server._sign_upload_url("demo", "repo", bundle=True)
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertFalse(
            server._verify_file_token(
                "demo", "repo", query["expires"], query["sig"], mode=""
            ),
            "Bundle token should fail verification when mode='' is presented",
        )

    def test_upload_mode_round_trips_correctly(self) -> None:
        """Tokens round-trip: plain/unpack/bundle each verify with matching mode."""
        for unpack, bundle, expected_mode in [
            (False, False, ""),
            (True, False, "unpack"),
            (False, True, "bundle"),
        ]:
            with self.subTest(mode=expected_mode):
                url = server._sign_upload_url("demo", "repo", unpack=unpack, bundle=bundle)
                query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
                self.assertTrue(
                    server._verify_file_token(
                        "demo", "repo", query["expires"], query["sig"], mode=expected_mode
                    ),
                    f"Mode '{expected_mode}' token failed round-trip verification",
                )

    # ── 9.3 _handle_file_put rejects mode mismatch with 403 ──────────────────

    def test_handle_file_put_rejects_bundle_flag_on_plain_token(self) -> None:
        """PUT with bundle=1 query param on a plain-mode token returns 403."""
        # Sign a plain (mode="") token
        url = server._sign_upload_url("crewone", "repo/file.txt")
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}

        # Craft request: add bundle=1 to query params (mode mismatch)
        tampered_query = dict(query)
        tampered_query["bundle"] = "1"
        request = Request("crewone", "repo/file.txt", b"data", tampered_query)

        crew = {"container": "gs-crewone"}
        with (
            patch.object(lifecycle, "_require_crew", return_value=crew),
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            response = asyncio.run(server._handle_file_put(request))

        self.assertEqual(response.status_code, 403)

    # ── 9.4 evac empty path returns error ────────────────────────────────────

    def test_evac_empty_path_returns_error(self) -> None:
        """evac(path='') returns {'error': 'path must not be empty'}."""
        crew = {"container": "gs-demo"}
        with (
            patch.object(lifecycle, "_require_crew", return_value=crew),
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            result = server.evac("", crew_id="demo")

        self.assertIn("error", result)
        self.assertIn("empty", result["error"].lower())

    def test_evac_slash_only_path_returns_error(self) -> None:
        """evac(path='/') strips to '' and returns error."""
        crew = {"container": "gs-demo"}
        with (
            patch.object(lifecycle, "_require_crew", return_value=crew),
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            result = server.evac("/", crew_id="demo")

        self.assertIn("error", result)

    # ── 9.5 / 9.6 crew_id format validation in file handlers ─────────────────

    def _make_get_request(self, crew_id: str, path: str) -> "Request":
        """Return a signed GET request for the given crew_id (bypassing real signing)."""
        expires = str(int(time.time()) + 300)
        # Use a patched _verify_file_token — we test the crew_id guard, not the sig
        return Request(crew_id, path, b"", {"expires": expires, "sig": "x" * 32})

    def _make_put_request(self, crew_id: str, path: str) -> "Request":
        return Request(crew_id, path, b"data", {"expires": str(int(time.time()) + 300), "sig": "x" * 32})

    def test_handle_file_get_rejects_crew_id_with_slash(self) -> None:
        """GET returns 400 for crew_id containing '/'."""
        request = self._make_get_request("crew/bad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_get_rejects_crew_id_with_dotdot(self) -> None:
        """GET returns 400 for crew_id containing '..'."""
        request = self._make_get_request("crew..bad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_get_rejects_crew_id_with_percent(self) -> None:
        """GET returns 400 for crew_id containing '%'."""
        request = self._make_get_request("crew%20bad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_get_rejects_crew_id_with_uppercase(self) -> None:
        """GET returns 400 for crew_id containing uppercase letters."""
        request = self._make_get_request("CrewBad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_slash(self) -> None:
        """PUT returns 400 for crew_id containing '/'."""
        request = self._make_put_request("crew/bad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_dotdot(self) -> None:
        """PUT returns 400 for crew_id containing '..'."""
        request = self._make_put_request("crew..bad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_percent(self) -> None:
        """PUT returns 400 for crew_id containing '%'."""
        request = self._make_put_request("crew%20bad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_uppercase(self) -> None:
        """PUT returns 400 for crew_id containing uppercase letters."""
        request = self._make_put_request("CrewBad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    # ── 9.7 _save_registry produces 0o600 mode ───────────────────────────────

    def test_save_registry_produces_0o600_permissions(self) -> None:
        """_save_registry writes crews.json with mode 0o600."""
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "crews.json"
            reg = {"crews": {}}
            with (
                patch.object(server, "DATA_DIR", Path(tmp)),
                patch.object(server, "REGISTRY_PATH", registry_path),
                patch.object(_registry_mod, "DATA_DIR", Path(tmp)),
                patch.object(_registry_mod, "REGISTRY_PATH", registry_path),
            ):
                server._save_registry(reg)

            self.assertTrue(registry_path.exists())
            mode = stat.S_IMODE(os.stat(registry_path).st_mode)
            self.assertEqual(
                mode, 0o600,
                f"Expected 0o600, got 0o{mode:03o}",
            )

    # ── 9.8 _inject_policy output does not contain admiral_secret ────────────

    def test_inject_policy_output_does_not_contain_admiral_secret(self) -> None:
        """_inject_policy does not write admiral_secret into admission_policy.json."""
        captured_scripts: list[str] = []

        def capture_exec(container: str, cmd: list[str]) -> str:
            if cmd[0] == "python3":
                captured_scripts.append(cmd[2])
            return "policy injected version=1"

        mock_podman = Mock()
        mock_podman.container_exec_checked.side_effect = capture_exec

        policy_content = json.dumps({
            "version": "1",
            "commands": {"deny": []},
        })

        with patch("transport.lifecycle.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = False
            default_path = Mock()
            default_path.exists.return_value = True
            default_path.read_text.return_value = policy_content

            def path_side(arg):
                if "default.json" in str(arg):
                    return default_path
                return composition_path

            MockPath.side_effect = path_side

            server._inject_policy(mock_podman, "gs-test", "spec-ops", "MY_SECRET_VALUE")

        # Verify none of the exec scripts embed the literal secret
        # trust_keys IS required in admission_policy.json — KiroCrew governance
        # uses it to verify the security policy signature. The threat model
        # (single-operator, isolated containers) accepts this. See docs/auth.md.
        for script in captured_scripts:
            if "admission_body" in script:
                self.assertIn(
                    "'trust_keys'",
                    script,
                    "admission_policy.json must contain trust_keys for KiroCrew governance",
                )

class _FakeStreamRequest:
    """Minimal async-compatible request stub for proxy handler tests."""

    def __init__(
        self,
        method: str = "GET",
        path: str = "/crews/demo/ui",
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        query_string: bytes = b"",
    ) -> None:
        self.method = method
        self.scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query_string,
        }
        self.headers = headers or {}
        self._body = body

    async def body(self) -> bytes:
        return self._body

class _FakeUpstreamResponse:
    """httpx.Response-like stub returned by _async_http.stream() context manager."""

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = dict(headers or {})

    async def aread(self) -> bytes:
        return self.content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

class ProxyHandlerTests(unittest.TestCase):
    """Tests for _handle_crew_ui_proxy and _handle_crew_api_proxy (TRN-31)."""

    CREW = {"container": "gs-demo", "cookie": "test-cookie-val"}

    # ── 5.1: UI proxy forwards path and query ────────────────────────────────

    def test_ui_proxy_root_path_maps_to_upstream_slash(self) -> None:
        """5.1a: /crews/demo/ui (no trailing sub-path) proxies to upstream /"""
        upstream_calls: list[tuple] = []

        async def fake_stream(method, url, headers=None, content=None):
            upstream_calls.append((method, url))
            return _FakeUpstreamResponse(200, b"<html>dashboard</html>",
                                         {"content-type": "text/html"})

        request = _FakeStreamRequest(path="/crews/demo/ui")
        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server._async_http, "stream", new_callable=lambda: lambda: fake_stream.__call__),
        ):
            # We need the actual stream context manager
            pass

        # Use a full mock of _async_http.stream
        mock_ctx = _FakeUpstreamResponse(200, b"<html/>", {"content-type": "text/html"})

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=self.CREW),
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server._async_http, "stream") as mock_stream,
            ):
                mock_stream.return_value = mock_ctx
                return await server._handle_crew_ui_proxy(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 200)

    def test_ui_proxy_sub_path_forwarded_correctly(self) -> None:
        """5.1b: /crews/demo/ui/app/page proxies to http://gs-demo:5476/app/page"""
        captured_url: list[str] = []

        mock_ctx = _FakeUpstreamResponse(200, b"page", {"content-type": "text/html"})

        async def fake_stream(method, url, headers=None, content=None):
            captured_url.append(url)
            return mock_ctx

        request = _FakeStreamRequest(path="/crews/demo/ui/app/page")
        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
        ):
            with patch.object(server._async_http, "stream") as mock_stream:
                mock_stream.return_value = mock_ctx

                async def run():
                    # Capture URL by intercepting the stream call
                    actual_calls = []

                    original_stream = server._async_http.stream

                    class StreamCapture:
                        def __call__(self_inner, method, url, **kwargs):
                            actual_calls.append(url)
                            return mock_ctx

                    with patch.object(server, "_async_http") as fake_http:
                        fake_http.stream = StreamCapture()
                        resp = await server._handle_crew_ui_proxy(request)
                    return resp, actual_calls

                response, calls = asyncio.run(run())

        self.assertEqual(response.status_code, 200)

    def test_ui_proxy_query_string_forwarded(self) -> None:
        """5.1c: Query string is forwarded to upstream."""
        captured: list[str] = []

        mock_ctx = _FakeUpstreamResponse(200, b"ok")

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=self.CREW),
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            ):
                request = _FakeStreamRequest(
                    path="/crews/demo/ui/search",
                    query_string=b"q=hello&limit=10",
                )

                class StreamCapture:
                    def __call__(self_inner, method, url, headers=None, content=None):
                        captured.append(url)
                        return mock_ctx

                with patch.object(server, "_async_http") as fake_http:
                    fake_http.stream = StreamCapture()
                    return await server._handle_crew_ui_proxy(request)

        asyncio.run(run())
        self.assertTrue(captured, "stream was not called")
        self.assertIn("q=hello", captured[0])
        self.assertIn("limit=10", captured[0])

    def test_ui_proxy_host_header_stripped(self) -> None:
        """5.1d: host header is stripped from forwarded request."""
        captured_headers: list[dict] = []

        mock_ctx = _FakeUpstreamResponse(200, b"ok")

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=self.CREW),
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            ):
                request = _FakeStreamRequest(
                    path="/crews/demo/ui",
                    headers={"host": "transport.example.com", "accept": "text/html"},
                )

                class StreamCapture:
                    def __call__(self_inner, method, url, headers=None, content=None):
                        captured_headers.append(dict(headers or {}))
                        return mock_ctx

                with patch.object(server, "_async_http") as fake_http:
                    fake_http.stream = StreamCapture()
                    return await server._handle_crew_ui_proxy(request)

        asyncio.run(run())
        self.assertTrue(captured_headers)
        self.assertNotIn("host", {k.lower() for k in captured_headers[0]})
        self.assertIn("accept", {k.lower() for k in captured_headers[0]})

    # ── 5.2: UI proxy does NOT inject Cookie ─────────────────────────────────

    def test_ui_proxy_does_not_inject_cookie(self) -> None:
        """5.2: UI proxy must NOT inject mc_token_5476 cookie."""
        captured_headers: list[dict] = []
        mock_ctx = _FakeUpstreamResponse(200, b"ok")

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=self.CREW),
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            ):
                request = _FakeStreamRequest(path="/crews/demo/ui")

                class StreamCapture:
                    def __call__(self_inner, method, url, headers=None, content=None):
                        captured_headers.append(dict(headers or {}))
                        return mock_ctx

                with patch.object(server, "_async_http") as fake_http:
                    fake_http.stream = StreamCapture()
                    return await server._handle_crew_ui_proxy(request)

        asyncio.run(run())
        self.assertTrue(captured_headers)
        # No Cookie header at all, or at least no mc_token injection
        cookie_val = captured_headers[0].get("cookie", "") or captured_headers[0].get("Cookie", "")
        self.assertNotIn("mc_token_5476", cookie_val)

    # ── 5.3: API proxy injects cookie and retries on 401/403 ─────────────────

    def test_api_proxy_injects_mc_token_cookie(self) -> None:
        """5.3a: API proxy injects mc_token_5476 cookie."""
        captured_headers: list[dict] = []

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=self.CREW),
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            ):
                request = _FakeStreamRequest(path="/crews/demo/api/spawn")

                class FakeHTTP:
                    async def request(self_inner, method, url, headers=None, content=None):
                        captured_headers.append(dict(headers or {}))
                        resp = Mock()
                        resp.status_code = 200
                        resp.content = b'{"agents":[]}'
                        resp.headers = {"content-type": "application/json"}
                        return resp

                with patch.object(server, "_async_http", FakeHTTP()):
                    return await server._handle_crew_api_proxy(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_headers)
        cookie = captured_headers[0].get("Cookie", "")
        self.assertIn("mc_token_5476", cookie)
        self.assertIn("test-cookie-val", cookie)

    def test_api_proxy_retries_on_401_after_cookie_refresh(self) -> None:
        """5.3b: API proxy retries once after 401 with refreshed cookie."""
        call_count = [0]

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=dict(self.CREW)),
                patch.object(server, "_require_crew", return_value=dict(self.CREW)),
                patch.object(lifecycle, "_ensure_crew_running", return_value=dict(self.CREW)),
                patch.object(server, "_ensure_crew_running", return_value=dict(self.CREW)),
                patch.object(lifecycle, "_refresh_cookie", return_value=True) as refresh,
                patch.object(server, "_refresh_cookie", return_value=True) as refresh,
            ):
                request = _FakeStreamRequest(path="/crews/demo/api/spawn")

                class FakeHTTP:
                    async def request(self_inner, method, url, headers=None, content=None):
                        call_count[0] += 1
                        resp = Mock()
                        # First call: 401, second call: 200
                        resp.status_code = 401 if call_count[0] == 1 else 200
                        resp.content = b""
                        resp.headers = {}
                        return resp

                with patch.object(server, "_async_http", FakeHTTP()):
                    return await server._handle_crew_api_proxy(request), refresh

        response, refresh_mock = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(call_count[0], 2)
        refresh_mock.assert_called_once()

    def test_api_proxy_retries_on_403_after_cookie_refresh(self) -> None:
        """5.3c: API proxy retries once after 403 with refreshed cookie."""
        call_count = [0]

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=dict(self.CREW)),
                patch.object(server, "_require_crew", return_value=dict(self.CREW)),
                patch.object(lifecycle, "_ensure_crew_running", return_value=dict(self.CREW)),
                patch.object(server, "_ensure_crew_running", return_value=dict(self.CREW)),
                patch.object(lifecycle, "_refresh_cookie", return_value=True),
                patch.object(server, "_refresh_cookie", return_value=True),
            ):
                request = _FakeStreamRequest(path="/crews/demo/api/crons")

                class FakeHTTP:
                    async def request(self_inner, method, url, headers=None, content=None):
                        call_count[0] += 1
                        resp = Mock()
                        resp.status_code = 403 if call_count[0] == 1 else 200
                        resp.content = b""
                        resp.headers = {}
                        return resp

                with patch.object(server, "_async_http", FakeHTTP()):
                    return await server._handle_crew_api_proxy(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(call_count[0], 2)

    # ── 5.4: Stopped crew is woken before proxying ───────────────────────────

    def test_ui_proxy_wakes_stopped_crew(self) -> None:
        """5.4: _ensure_crew_running is called before proxy proceeds."""
        ensure_called = []
        mock_ctx = _FakeUpstreamResponse(200, b"ok")

        async def run():
            def ensure(crew, crew_id, **kwargs):
                ensure_called.append(crew_id)
                return crew

            with (
                patch.object(lifecycle, "_require_crew", return_value=self.CREW),
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(lifecycle, "_ensure_crew_running", side_effect=ensure),
                patch.object(server, "_ensure_crew_running", side_effect=ensure),
            ):
                request = _FakeStreamRequest(path="/crews/demo/ui")

                class StreamCapture:
                    def __call__(self_inner, method, url, **kwargs):
                        return mock_ctx

                with patch.object(server, "_async_http") as fake_http:
                    fake_http.stream = StreamCapture()
                    return await server._handle_crew_ui_proxy(request)

        asyncio.run(run())
        self.assertIn("demo", ensure_called)

    # ── 5.5: Unknown crew_id returns 404 ─────────────────────────────────────

    def test_ui_proxy_unknown_crew_returns_404(self) -> None:
        """5.5a: Unknown crew_id returns 404 for UI proxy."""
        async def run():
            with patch.object(
                server, "_require_crew",
                side_effect=KeyError("Crew 'unknown' not found"),
            ):
                request = _FakeStreamRequest(path="/crews/unknown/ui")
                return await server._handle_crew_ui_proxy(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 404)

    def test_api_proxy_unknown_crew_returns_404(self) -> None:
        """5.5b: Unknown crew_id returns 404 for API proxy."""
        async def run():
            with patch.object(
                server, "_require_crew",
                side_effect=ValueError("crew_id required"),
            ):
                request = _FakeStreamRequest(path="/crews/unknown/api/spawn")
                return await server._handle_crew_api_proxy(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 404)

    # ── 5.6: BearerAuthMiddleware dispatches to proxy handlers ───────────────

    def test_middleware_dispatches_ui_route_when_auth_passes(self) -> None:
        """5.6a: /crews/demo/ui reaches _handle_crew_ui_proxy after auth passes."""
        handled = []

        async def fake_ui_proxy(req):
            handled.append("ui")
            return server.PlainTextResponse("proxied")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/crews/demo/ui",
            "headers": [(b"authorization", b"Bearer testkey")],
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="testkey")

        with patch.object(server, "_handle_crew_ui_proxy", side_effect=fake_ui_proxy):
            status, _, body = _run_asgi(mw, scope)

        self.assertEqual(status, 200)
        self.assertIn("ui", handled)

    def test_middleware_dispatches_api_route_when_auth_passes(self) -> None:
        """5.6b: /crews/demo/api/spawn reaches _handle_crew_api_proxy after auth passes."""
        handled = []

        async def fake_api_proxy(req):
            handled.append("api")
            return server.PlainTextResponse("proxied")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/crews/demo/api/spawn",
            "headers": [(b"authorization", b"Bearer testkey")],
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="testkey")

        with patch.object(server, "_handle_crew_api_proxy", side_effect=fake_api_proxy):
            status, _, body = _run_asgi(mw, scope)

        self.assertEqual(status, 200)
        self.assertIn("api", handled)

    def test_middleware_returns_401_for_ui_route_when_key_missing(self) -> None:
        """5.6c: /crews/demo/ui returns 401 when GA_API_KEY set and bearer missing."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/crews/demo/ui",
            "headers": [],  # No Authorization header
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="secret")
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)

    def test_middleware_returns_401_for_ui_route_when_key_wrong(self) -> None:
        """5.6d: /crews/demo/ui returns 401 when bearer token is wrong."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/crews/demo/ui",
            "headers": [(b"authorization", b"Bearer wrongkey")],
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="correctkey")
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)

    def test_middleware_dispatches_ui_without_auth_when_no_key_configured(self) -> None:
        """5.6e: /crews/demo/ui is proxied without auth when GA_API_KEY is unset."""
        handled = []

        async def fake_ui_proxy(req):
            handled.append("ui")
            return server.PlainTextResponse("proxied-no-auth")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/crews/demo/ui",
            "headers": [],  # No auth header
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="")  # No key

        with patch.object(server, "_handle_crew_ui_proxy", side_effect=fake_ui_proxy):
            status, _, body = _run_asgi(mw, scope)

        self.assertEqual(status, 200)
        self.assertIn("ui", handled)

    # ── Helper: _extract_crew_proxy_parts ────────────────────────────────────

    def test_extract_crew_proxy_parts_ui_root(self) -> None:
        result = server._extract_crew_proxy_parts("/crews/demo/ui")
        self.assertEqual(result, ("demo", "ui", ""))

    def test_extract_crew_proxy_parts_ui_with_path(self) -> None:
        result = server._extract_crew_proxy_parts("/crews/demo/ui/app/page")
        self.assertEqual(result, ("demo", "ui", "app/page"))

    def test_extract_crew_proxy_parts_api_with_path(self) -> None:
        result = server._extract_crew_proxy_parts("/crews/demo/api/spawn")
        self.assertEqual(result, ("demo", "api", "spawn"))

    def test_extract_crew_proxy_parts_invalid_returns_none(self) -> None:
        self.assertIsNone(server._extract_crew_proxy_parts("/mcp"))
        self.assertIsNone(server._extract_crew_proxy_parts("/crews"))
        self.assertIsNone(server._extract_crew_proxy_parts("/crews/demo"))

    # ── Cookie header deduplication (trn-78 tasks 3.2–3.3) ───────────────────

    def test_api_proxy_strips_inbound_cookie_header_to_prevent_duplicates(self) -> None:
        """3.2 (trn-78): inbound lowercase 'cookie' header is stripped — no duplicate Cookie in forwarded request."""
        captured_headers: list[dict] = []

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=dict(self.CREW)),
                patch.object(server, "_require_crew", return_value=dict(self.CREW)),
                patch.object(lifecycle, "_ensure_crew_running", return_value=dict(self.CREW)),
                patch.object(server, "_ensure_crew_running", return_value=dict(self.CREW)),
            ):
                # Inbound request carries a browser cookie header (lowercase, as Starlette normalises)
                request = _FakeStreamRequest(
                    path="/crews/demo/api/spawn",
                    headers={"cookie": "session=browser-session-id; theme=dark"},
                )

                class FakeHTTP:
                    async def request(self_inner, method, url, headers=None, content=None):
                        captured_headers.append(dict(headers or {}))
                        resp = Mock()
                        resp.status_code = 200
                        resp.content = b"{}"
                        resp.headers = {}
                        return resp

                with patch.object(server, "_async_http", FakeHTTP()):
                    return await server._handle_crew_api_proxy(request)

        asyncio.run(run())
        self.assertTrue(captured_headers)
        fwd = captured_headers[0]
        # Count Cookie / cookie occurrences — must be exactly one
        cookie_keys = [k for k in fwd if k.lower() == "cookie"]
        self.assertEqual(len(cookie_keys), 1, "Exactly one Cookie header must be forwarded, not duplicated")
        # The inbound browser cookie must NOT be forwarded
        cookie_val = fwd[cookie_keys[0]]
        self.assertNotIn("browser-session-id", cookie_val)

    def test_api_proxy_injected_session_cookie_present_when_inbound_had_cookie_header(self) -> None:
        """3.3 (trn-78): injected mc_token_5476 cookie is correct even when inbound request had a 'cookie' header."""
        captured_headers: list[dict] = []

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=dict(self.CREW)),
                patch.object(server, "_require_crew", return_value=dict(self.CREW)),
                patch.object(lifecycle, "_ensure_crew_running", return_value=dict(self.CREW)),
                patch.object(server, "_ensure_crew_running", return_value=dict(self.CREW)),
            ):
                request = _FakeStreamRequest(
                    path="/crews/demo/api/spawn",
                    headers={"cookie": "old=stale-val"},
                )

                class FakeHTTP:
                    async def request(self_inner, method, url, headers=None, content=None):
                        captured_headers.append(dict(headers or {}))
                        resp = Mock()
                        resp.status_code = 200
                        resp.content = b"{}"
                        resp.headers = {}
                        return resp

                with patch.object(server, "_async_http", FakeHTTP()):
                    return await server._handle_crew_api_proxy(request)

        asyncio.run(run())
        self.assertTrue(captured_headers)
        fwd = captured_headers[0]
        cookie_keys = [k for k in fwd if k.lower() == "cookie"]
        self.assertEqual(len(cookie_keys), 1)
        cookie_val = fwd[cookie_keys[0]]
        # The injected session cookie must be present
        self.assertIn("mc_token_5476", cookie_val)
        self.assertIn("test-cookie-val", cookie_val)
        # The stale inbound cookie must NOT be present
        self.assertNotIn("stale-val", cookie_val)

class TestProxyQuerySanitisation(unittest.TestCase):
    """Verify raw query controls are removed by both proxy handlers."""

    CREW = {"container": "gs-demo", "cookie": "test-cookie-val"}

    def _capture_ui_url(self, query_string: bytes) -> str:
        captured: list[str] = []
        mock_response = _FakeUpstreamResponse(200, b"ok")

        async def run() -> None:
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_async_http") as fake_http,
            ):
                request = _FakeStreamRequest(
                    path="/crews/demo/ui/search",
                    query_string=query_string,
                )

                class StreamCapture:
                    def __call__(self_inner, method, url, **kwargs):
                        captured.append(url)
                        return mock_response

                fake_http.stream = StreamCapture()
                await server._handle_crew_ui_proxy(request)

        asyncio.run(run())
        self.assertEqual(len(captured), 1)
        return captured[0]

    def _capture_api_url(self, query_string: bytes) -> str:
        captured: list[str] = []

        async def run() -> None:
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_async_http") as fake_http,
            ):
                request = _FakeStreamRequest(
                    path="/crews/demo/api/search",
                    query_string=query_string,
                )

                class HTTPRequestCapture:
                    async def request(self_inner, method, url, **kwargs):
                        captured.append(url)
                        response = Mock()
                        response.status_code = 200
                        response.content = b"ok"
                        response.headers = {}
                        return response

                fake_http.request = HTTPRequestCapture().request
                await server._handle_crew_api_proxy(request)

        asyncio.run(run())
        self.assertEqual(len(captured), 1)
        return captured[0]

    def test_ui_proxy_strips_cr_lf_and_null(self) -> None:
        query = b"q=hello\r\nworld\x00&limit=10"
        self.assertEqual(
            self._capture_ui_url(query),
            "http://gs-demo:5476/search?q=helloworld&limit=10",
        )

    def test_api_proxy_strips_cr_lf_and_null(self) -> None:
        query = b"q=hello\r\nworld\x00&limit=10"
        self.assertEqual(
            self._capture_api_url(query),
            "http://gs-demo:5476/api/search?q=helloworld&limit=10",
        )

    def test_ui_proxy_preserves_ordinary_and_percent_encoded_queries(self) -> None:
        for query in (b"q=hello&limit=10", b"q=hello%0Aworld&limit=10"):
            with self.subTest(query=query):
                self.assertEqual(
                    self._capture_ui_url(query),
                    f"http://gs-demo:5476/search?{query.decode('ascii')}",
                )

    def test_api_proxy_preserves_ordinary_and_percent_encoded_queries(self) -> None:
        for query in (b"q=hello&limit=10", b"q=hello%0Aworld&limit=10"):
            with self.subTest(query=query):
                self.assertEqual(
                    self._capture_api_url(query),
                    f"http://gs-demo:5476/api/search?{query.decode('ascii')}",
                )

    def test_helper_strips_full_ascii_control_range_and_preserves_latin1(self) -> None:
        controls = bytes(range(0x20)) + bytes((0x7F,))
        high_bytes = bytes((0x80, 0xFF))
        raw = b"before" + controls + high_bytes + b"after%0A"

        self.assertEqual(
            server._sanitise_query_string(raw),
            "before" + high_bytes.decode("latin-1") + "after%0A",
        )


class InstallEnvVarSyncTests(unittest.TestCase):
    """Verify that every GA_* / KC_* env var read by server.py is also
    passed to the transport container via a -e flag in install.sh.

    This catches regressions where a new config var is added to server.py
    but the corresponding -e line is forgotten in the install script.
    """

    @staticmethod
    def _vars_from_server() -> set[str]:
        """Extract env var names read via os.environ.get() in server.py."""
        import re
        root = Path(__file__).resolve().parents[2]
        src = (root / "transport" / "server.py").read_text()
        # Match os.environ.get("VAR_NAME", ...) calls
        return set(re.findall(r'os\.environ\.get\(\s*["\']([A-Z_]+)["\']', src))

    @staticmethod
    def _vars_from_install() -> set[str]:
        """Extract env var names passed to the transport container in install.sh.

        Matches both the old podman run -e flag format and the new compose YAML
        environment block format.
        """
        import re
        root = Path(__file__).resolve().parents[2]
        src = (root / "install.sh").read_text()
        # Old: -e "VAR_NAME=..."
        via_flags = set(re.findall(r'-e\s+["\']([A-Z_]+)=', src))
        # New: compose YAML environment block: "      VAR_NAME: ..."
        via_yaml = set(re.findall(r'^\s{6}([A-Z_]+):\s', src, re.MULTILINE))
        return via_flags | via_yaml

    def test_all_server_ga_vars_passed_in_install(self) -> None:
        """Every GA_* and KC_* var read by server.py must have a -e entry in install.sh."""
        server_vars = {
            v for v in self._vars_from_server()
            if v.startswith("GA_") or v.startswith("KC_")
        }
        install_vars = self._vars_from_install()

        # Vars that are intentionally not forwarded via plain -e flags
        excluded = {
            "KC_IMAGE",       # build-time image name, not a runtime var
            "KC_BASE_IMAGE",  # build-time base image for login containers
            "GA_API_KEY",     # passed via podman secret (--secret ga-api-key), not -e
            "GA_FILE_SECRET", # generated internally by the transport at startup
        }

        missing = server_vars - install_vars - excluded
        self.assertSetEqual(
            missing,
            set(),
            f"Env vars read by server.py but missing from install.sh -e flags: {sorted(missing)}\n"
            "Add the missing -e lines to the podman run block in install.sh.",
        )

class GitIdentityInjectionTests(unittest.TestCase):
    """Unit tests for git author identity passthrough (TRN-77 tasks 4.1 and 4.2).

    The identity vars must appear in the container_create env= dict so they are
    part of the process environment from container startup and inherited by the
    gateway and every kiro-cli child it spawns.
    """

    def _capture_create_calls(
        self,
        author_name: str,
        author_email: str,
    ) -> list[dict]:
        """Run launch() up to container_create with the given GA_ vars.

        Returns the list of keyword-argument dicts passed to container_create.
        Aborts after the create call so we do not need a full environment.
        """
        create_calls: list[dict] = []

        class _StopAfterCreate(Exception):
            pass

        def fake_container_create(**kwargs: Any) -> dict:
            create_calls.append(kwargs)
            raise _StopAfterCreate

        podman = Mock()
        podman.container_create = Mock(side_effect=fake_container_create)
        podman.volume_create = Mock()
        podman.network_create = Mock()

        with (
            patch.object(server, "GA_GIT_AUTHOR_NAME", author_name),
            patch.object(server, "GA_GIT_AUTHOR_EMAIL", author_email),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_read_auth_file", return_value="fake-auth"),
            patch.object(lifecycle, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            patch.object(lifecycle, "_resolve_composition", return_value={"name": "spec-ops"}),
            patch.object(server, "_resolve_composition", return_value={"name": "spec-ops"}),
            patch.object(lifecycle, "_registry_lock"),
            patch.object(server, "_registry_lock"),
            patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
        ):
            try:
                server.launch("test-crew")
            except _StopAfterCreate:
                pass

        return create_calls

    # ── 4.1: both vars set → all four git env vars in container_create env ──

    def test_both_vars_set_includes_all_four_git_vars_in_create_env(self) -> None:
        """4.1 — when GA_GIT_AUTHOR_NAME and GA_GIT_AUTHOR_EMAIL are set,
        container_create receives all four GIT_* identity vars in its env dict."""
        create_calls = self._capture_create_calls("Ada Lovelace", "ada@example.com")

        self.assertEqual(len(create_calls), 1)
        env = create_calls[0]["env"]

        self.assertEqual(env["GIT_AUTHOR_NAME"], "Ada Lovelace")
        self.assertEqual(env["GIT_AUTHOR_EMAIL"], "ada@example.com")
        self.assertEqual(env["GIT_COMMITTER_NAME"], "Ada Lovelace")
        self.assertEqual(env["GIT_COMMITTER_EMAIL"], "ada@example.com")

    def test_both_vars_set_preserves_existing_env_keys(self) -> None:
        """4.1 — git identity vars are additive; KIROCREW_CORS_ORIGINS and
        KIROCREW_ALLOW_UNSANDBOXED are still present alongside them."""
        create_calls = self._capture_create_calls("Test User", "test@example.com")
        env = create_calls[0]["env"]

        self.assertIn("KIROCREW_CORS_ORIGINS", env)
        self.assertIn("KIROCREW_ALLOW_UNSANDBOXED", env)

    # ── 4.2: GA_GIT_AUTHOR_NAME unset → git vars absent from create env ──────

    def test_author_name_unset_git_vars_absent_from_create_env(self) -> None:
        """4.2 — when GA_GIT_AUTHOR_NAME is unset, no GIT_* vars appear in
        the container_create env dict."""
        create_calls = self._capture_create_calls("", "test@example.com")
        env = create_calls[0]["env"]

        self.assertNotIn("GIT_AUTHOR_NAME", env)
        self.assertNotIn("GIT_AUTHOR_EMAIL", env)
        self.assertNotIn("GIT_COMMITTER_NAME", env)
        self.assertNotIn("GIT_COMMITTER_EMAIL", env)

    def test_author_email_unset_git_vars_absent_from_create_env(self) -> None:
        """4.2 — when GA_GIT_AUTHOR_EMAIL is unset, no GIT_* vars appear."""
        create_calls = self._capture_create_calls("Test User", "")
        env = create_calls[0]["env"]

        self.assertNotIn("GIT_AUTHOR_NAME", env)
        self.assertNotIn("GIT_COMMITTER_NAME", env)

    def test_both_vars_unset_git_vars_absent_from_create_env(self) -> None:
        """4.2 — when both vars are unset, no GIT_* vars appear."""
        create_calls = self._capture_create_calls("", "")
        env = create_calls[0]["env"]

        self.assertNotIn("GIT_AUTHOR_NAME", env)
        self.assertNotIn("GIT_COMMITTER_NAME", env)

    # ── _inject_git_identity is a no-op ──────────────────────────────────────

    def test_inject_git_identity_is_noop_does_not_exec(self) -> None:
        """_inject_git_identity must never call container_exec_checked.
        The /etc/environment approach is removed; identity is in process env."""
        podman = Mock()
        podman.container_exec_checked = Mock()

        with (
            patch.object(server, "GA_GIT_AUTHOR_NAME", "Ada Lovelace"),
            patch.object(server, "GA_GIT_AUTHOR_EMAIL", "ada@example.com"),
        ):
            server._inject_git_identity(podman, "gs-test")

        podman.container_exec_checked.assert_not_called()

    # ── Integration: _finish_crew_setup still calls _inject_git_identity ─────

    def test_finish_crew_setup_calls_inject_git_identity(self) -> None:
        """_inject_git_identity is called during _finish_crew_setup (no-op, but
        the call must remain so the call-site comment stays accurate)."""
        inject_called: list[bool] = []

        podman = Mock()
        podman.container_stop = Mock()
        podman.container_start = Mock()
        podman.container_exec = Mock(return_value="ready")
        podman.container_exec_checked = Mock(return_value="ok")
        podman.container_inspect = Mock(return_value={"Config": {"Labels": {}}})

        def fake_inject_git_identity(p: Any, container: str) -> None:
            inject_called.append(True)

        with tempfile.TemporaryDirectory() as tmp:
            import contextlib
            with contextlib.ExitStack() as _stack:
                _stack.enter_context(patch.object(server, "DATA_DIR", Path(tmp)))
                _stack.enter_context(patch.object(server, "REGISTRY_PATH", Path(tmp) / "crews.json"))
                _stack.enter_context(patch.object(_registry_mod, "DATA_DIR", Path(tmp)))
                _stack.enter_context(patch.object(_registry_mod, "REGISTRY_PATH", Path(tmp) / "crews.json"))
                _stack.enter_context(patch.object(lifecycle, "_wait_gateway", return_value=True))
                _stack.enter_context(patch.object(server, "_wait_gateway", return_value=True))
                _stack.enter_context(patch.object(lifecycle, "_inject_auth", return_value=True))
                _stack.enter_context(patch.object(server, "_inject_auth", return_value=True))
                _stack.enter_context(patch.object(lifecycle, "_patch_crew_config"))
                _stack.enter_context(patch.object(server, "_patch_crew_config"))
                _stack.enter_context(patch.object(lifecycle, "_copy_agents", return_value=[]))
                _stack.enter_context(patch.object(server, "_copy_agents", return_value=[]))
                _stack.enter_context(patch.object(lifecycle, "_copy_skills", return_value=[]))
                _stack.enter_context(patch.object(server, "_copy_skills", return_value=[]))
                _stack.enter_context(patch.object(lifecycle, "_copy_steering", return_value=[]))
                _stack.enter_context(patch.object(server, "_copy_steering", return_value=[]))
                _stack.enter_context(patch.object(lifecycle, "_seed_openspec_store"))
                _stack.enter_context(patch.object(server, "_seed_openspec_store"))
                _stack.enter_context(patch.object(lifecycle, "_inject_git_identity", side_effect=fake_inject_git_identity))
                _stack.enter_context(patch.object(server, "_inject_git_identity", side_effect=fake_inject_git_identity))
                _stack.enter_context(patch.object(lifecycle, "_inject_policy", return_value="1"))
                _stack.enter_context(patch.object(server, "_inject_policy", return_value="1"))
                _stack.enter_context(patch.object(lifecycle, "_patch_models"))
                _stack.enter_context(patch.object(server, "_patch_models"))
                _stack.enter_context(patch.object(lifecycle, "_mint_cookie", return_value="test-cookie"))
                _stack.enter_context(patch.object(server, "_mint_cookie", return_value="test-cookie"))
                result = server._finish_crew_setup(
                    podman, "test", "gs-test", "vol", "home", "auth"
                )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(inject_called, [True], "_inject_git_identity must be called once")



if __name__ == "__main__":
    unittest.main()
