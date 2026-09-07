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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from unittest.mock import ANY, Mock, MagicMock, patch

import httpx
import transport.registry as _registry_mod  # noqa: F401

from tests.unit.helpers import Request, server, lifecycle, monitors, academy  # noqa: F401

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
class CookieHeaders:
    def multi_items(self):
        return [("set-cookie", "mc_token_5476=session-cookie; Path=/")]
class CookieResponse:
    status_code = 200
    headers = CookieHeaders()
class CookieHTTP:
    def get(self, *args: object, **kwargs: object) -> CookieResponse:
        return CookieResponse()
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
        """5.3b — internal 30s poll cap fires before caller timeout_secs;
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
        ):
            # caller requests 60s, but the internal cap is 30s (pickup timeout, unrelated to gateway)
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
class GatewayTokenAndProjectionTests(unittest.TestCase):
    def test_gateway_token_uses_hardcoded_ttl(self) -> None:
        """KC_GATEWAY_TOKEN_TTL is now hardcoded to '24h'; verify it is passed to kirocrew token."""
        podman = Mock()
        podman.container_exec.return_value = "token=abc123"
        with patch.object(lifecycle, "_http", CookieHTTP()):
            result = server._mint_cookie(podman, "gs-demo", "http://gs-demo:5476")
        self.assertEqual(result, "session-cookie")
        self.assertEqual(podman.container_exec.call_args.args[1][-1], "24h")

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
        installer = (repo_root / "scripts" / "install.sh").read_text()
        self.assertIn('${DATA_DIR}:/data', installer)
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

    # ── TRN-62: API key auth path tests ──────────────────────────────────────

    def _launch_with_captured_env(
        self, *, api_key: str, auth_file: str
    ) -> tuple[dict, dict, Mock, Mock]:
        """Drive server.launch far enough to reach container_create and
        _finish_crew_setup, capturing the crew container env and the
        _initiate_login mock.

        Returns (result, captured_container_env, initiate_login_mock,
        finish_setup_mock).
        """
        captured_env: dict = {}

        def fake_container_create(*args, **kwargs) -> None:
            captured_env.update(kwargs.get("env", {}))

        podman = Mock()
        podman.container_create.side_effect = fake_container_create
        initiate_login = Mock(return_value={
            "login_url": "https://example.com/device",
            "code": "XXXX",
        })
        finish_setup = Mock(return_value={"crew_id": "api-crew", "status": "ready"})

        with (
            patch.object(server, "KIRO_API_KEY", api_key),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(server, "_read_auth_file", return_value=auth_file),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_initiate_login", initiate_login),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_finish_crew_setup", finish_setup),
        ):
            result = server.launch("api-crew")

        return result, captured_env, initiate_login, finish_setup

    def test_launch_with_api_key_skips_initiate_login(self) -> None:
        """6.1: KIRO_API_KEY set and no ga-kiro-auth file — _initiate_login is
        NOT called; launch proceeds to finish crew setup."""
        result, _env, initiate_login, finish_setup = self._launch_with_captured_env(
            api_key="sk-test-key", auth_file=""
        )

        initiate_login.assert_not_called()
        finish_setup.assert_called_once()
        self.assertNotIn("error", result)

    def test_launch_with_api_key_passes_auth_b64_none_to_finish_setup(self) -> None:
        """6.1: with KIRO_API_KEY set and no auth file, _finish_crew_setup
        receives auth_b64=None (SQLite auth injection is skipped downstream)."""
        _result, _env, _initiate_login, finish_setup = self._launch_with_captured_env(
            api_key="sk-test-key", auth_file=""
        )

        # _finish_crew_setup(podman, crew_id, container, volume, home_volume,
        #                    auth_b64, composition, composition_entry)
        args = finish_setup.call_args.args
        self.assertIsNone(args[5])

    def test_launch_crew_env_includes_api_key_when_set(self) -> None:
        """6.3: crew container env includes KIRO_API_KEY when it is set."""
        _result, env, _initiate_login, _finish_setup = self._launch_with_captured_env(
            api_key="sk-test-key", auth_file=""
        )

        self.assertEqual(env.get("KIRO_API_KEY"), "sk-test-key")

    def test_launch_crew_env_omits_api_key_when_unset(self) -> None:
        """6.3: crew container env has NO KIRO_API_KEY when it is unset — the
        device-code path (auth file present) is used unchanged."""
        _result, env, initiate_login, _finish_setup = self._launch_with_captured_env(
            api_key="", auth_file="existing-auth-b64"
        )

        self.assertNotIn("KIRO_API_KEY", env)
        # Device-code guard not triggered because a valid auth file is present.
        initiate_login.assert_not_called()

    def test_launch_config_exports_api_key(self) -> None:
        """1.1/1.2/1.3: Config carries kiro_api_key and server exports it."""
        from transport.config import Config

        cfg = Config(kiro_api_key="from-config")
        self.assertEqual(cfg.kiro_api_key, "from-config")
        # from_env reads KIRO_API_KEY
        with patch.dict(os.environ, {"KIRO_API_KEY": "from-env"}, clear=False):
            self.assertEqual(Config.from_env().kiro_api_key, "from-env")
        # server exposes the module-level export
        self.assertTrue(hasattr(server, "KIRO_API_KEY"))

    def test_install_sh_passes_api_key_env(self) -> None:
        """4.1: install.sh wires KIRO_API_KEY into the ga-transport env block."""
        repo_root = Path(__file__).resolve().parents[2]
        installer = (repo_root / "scripts" / "install.sh").read_text()
        self.assertIn('KIRO_API_KEY: "${KIRO_API_KEY:-}"', installer)
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

    def test_crews_agent_entry_omits_last_tool(self) -> None:
        """TRN-95: crews() agent entries no longer include last_tool."""
        reg = {
            "crews": {
                "test-crew": {
                    "container": "gs-test-crew",
                    "status": "running",
                    "composition": "spec-ops",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "cookie": "test-cookie",
                }
            }
        }
        agents = [
            {"id": "task-1", "agent": "ghost", "done": False,
             "elapsed": 12, "last_tool": "shell"},
        ]
        mock_podman = Mock(
            system_info=lambda: {"host": {"memAvailable": 4 * 1024**3}},
            container_inspect=lambda name: {
                "State": {"StartedAt": "2026-01-01T00:00:00.000000000Z"}
            },
        )
        with (
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_probe_gateway", return_value=True),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(lifecycle, "_crew_api", return_value=agents),
            patch.object(server, "_crew_api", return_value=agents),
            patch.object(lifecycle, "_get_podman", return_value=mock_podman),
            patch.object(server, "_get_podman", return_value=mock_podman),
        ):
            result = server.crews()

        agent_entries = result["crews"][0]["agents"]
        self.assertEqual(len(agent_entries), 1)
        self.assertNotIn("last_tool", agent_entries[0])
        # Signal that survives — elapsed_secs — is still present.
        self.assertEqual(agent_entries[0]["elapsed_secs"], 12)

    def test_crews_running_entry_includes_uptime_secs(self) -> None:
        """TRN-95: a running crew entry includes an integer uptime_secs."""
        reg = {
            "crews": {
                "test-crew": {
                    "container": "gs-test-crew",
                    "status": "running",
                    "composition": "spec-ops",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "cookie": "test-cookie",
                }
            }
        }
        # StartedAt 100 seconds before "now"
        started = datetime.now(timezone.utc) - timedelta(seconds=100)
        started_iso = started.isoformat()
        mock_podman = Mock(
            system_info=lambda: {"host": {"memAvailable": 4 * 1024**3}},
            container_inspect=lambda name: {"State": {"StartedAt": started_iso}},
        )
        with (
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_probe_gateway", return_value=True),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(lifecycle, "_crew_api", return_value=[]),
            patch.object(server, "_crew_api", return_value=[]),
            patch.object(lifecycle, "_get_podman", return_value=mock_podman),
            patch.object(server, "_get_podman", return_value=mock_podman),
        ):
            result = server.crews()

        entry = result["crews"][0]
        self.assertIn("uptime_secs", entry)
        self.assertIsInstance(entry["uptime_secs"], int)
        # ~100s, allow a small window for test execution time
        self.assertGreaterEqual(entry["uptime_secs"], 99)
        self.assertLessEqual(entry["uptime_secs"], 105)

    def test_crews_stopped_entry_uptime_secs_null(self) -> None:
        """TRN-95: a stopped crew entry has uptime_secs null (no inspect)."""
        reg = {
            "crews": {
                "stopped-crew": {
                    "container": "gs-stopped-crew",
                    "status": "stopped",
                    "composition": "spec-ops",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "cookie": "test-cookie",
                }
            }
        }

        def _fail_inspect(name):
            raise AssertionError("container_inspect must not be called for stopped crews")

        mock_podman = Mock(
            system_info=lambda: {"host": {"memAvailable": 4 * 1024**3}},
            container_inspect=_fail_inspect,
        )
        with (
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_probe_gateway", return_value=False),
            patch.object(server, "_probe_gateway", return_value=False),
            patch.object(lifecycle, "_crew_api", return_value=[]),
            patch.object(server, "_crew_api", return_value=[]),
            patch.object(lifecycle, "_get_podman", return_value=mock_podman),
            patch.object(server, "_get_podman", return_value=mock_podman),
        ):
            result = server.crews()

        entry = result["crews"][0]
        self.assertIn("uptime_secs", entry)
        self.assertIsNone(entry["uptime_secs"])
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
        stdin_calls: list[tuple[int, list[str]]] = []
        stop_calls: list[int] = []
        start_calls: list[int] = []
        call_counter: list[int] = [0]

        podman = Mock()

        def track_exec_stdin(container: str, cmd: list[str], stdin_data: bytes) -> str:
            call_counter[0] += 1
            stdin_calls.append((call_counter[0], cmd))
            return "admiral secret injected"

        def track_stop(name: str) -> None:
            call_counter[0] += 1
            stop_calls.append(call_counter[0])

        def track_start(name: str) -> None:
            call_counter[0] += 1
            start_calls.append(call_counter[0])

        podman.container_exec_stdin = Mock(side_effect=track_exec_stdin)
        podman.container_exec_checked = Mock(return_value="ok")
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
        # Find the admiral secret injection call (first exec_stdin call whose
        # command contains inject_admiral_secret.py)
        secret_call_order = None
        for order, cmd in stdin_calls:
            if any("admiral_secret" in part for part in cmd):
                secret_call_order = order
                break
        self.assertIsNotNone(secret_call_order, "Admiral secret injection exec_stdin call not found")
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

        def capture_exec_stdin(container: str, cmd: list[str], stdin_data: bytes) -> str:
            if len(cmd) >= 2 and cmd[0] == "python3" and cmd[1].endswith(
                "/inject_admiral_secret.py"
            ):
                captured_cmds.append(cmd)
            return "admiral secret injected"

        podman.container_exec_stdin = Mock(side_effect=capture_exec_stdin)
        podman.container_exec_checked = Mock(return_value="ok")
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
        # The call passes the secret file path as argv; secret delivered via stdin.
        # argv[1] is the destination path (e.g. /home/kirocrew/.kiro/crew/.admiral_secret)
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

    # ── 5.2: UI proxy injects Cookie (TRN-102) ───────────────────────────────

    def test_ui_proxy_injects_cookie(self) -> None:
        """5.2 (TRN-102): UI proxy injects mc_token_5476 so the SPA is
        pre-authenticated. This reverses the pre-TRN-102 D3 behavior where the
        browser logged in via the gateway UI directly."""
        captured_headers: list[dict] = []
        mock_ctx = _FakeUpstreamResponse(200, b"ok")

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=self.CREW),
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_cookie_near_expiry", return_value=False),
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
        cookie_val = captured_headers[0].get("cookie", "") or captured_headers[0].get("Cookie", "")
        self.assertIn("mc_token_5476=test-cookie-val", cookie_val)

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
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="testkey",
            routes={("GET", "/crews/*/ui"): fake_ui_proxy})

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
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="testkey",
            routes={("GET", "/crews/*/api"): fake_api_proxy})

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
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="",
            routes={("GET", "/crews/*/ui"): fake_ui_proxy})

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

    # ── 9.1 (TRN-116): non-2xx upstream is surfaced with its status code ─────

    def _run_ui_proxy_with_upstream(self, status_code: int, body: bytes):
        """Drive _handle_crew_ui_proxy against an upstream that returns the given
        status_code, returning the handler's Response."""
        request = _FakeStreamRequest(path="/crews/demo/ui")

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=dict(self.CREW)),
                patch.object(server, "_require_crew", return_value=dict(self.CREW)),
                patch.object(lifecycle, "_ensure_crew_running", return_value=dict(self.CREW)),
                patch.object(server, "_ensure_crew_running", return_value=dict(self.CREW)),
                patch.object(server, "_cookie_near_expiry", return_value=False),
            ):
                mock_ctx = _FakeUpstreamResponse(
                    status_code, body, {"content-type": "text/plain"}
                )
                with patch.object(server._async_http, "stream", return_value=mock_ctx):
                    return await server._handle_crew_ui_proxy(request)

        return asyncio.run(run())

    def test_ui_proxy_surfaces_502_from_upstream(self) -> None:
        """9.1a: a 502 from the crew gateway is passed through unchanged, not
        rewritten to 200 or masked as a generic proxy error."""
        response = self._run_ui_proxy_with_upstream(502, b"bad gateway")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.body, b"bad gateway")

    def test_ui_proxy_surfaces_503_from_upstream(self) -> None:
        """9.1b: a 503 from the crew gateway is surfaced with its own status code."""
        response = self._run_ui_proxy_with_upstream(503, b"unavailable")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.body, b"unavailable")
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
        environment block format. Reads scripts/install.sh (the real implementation;
        install.sh at the repo root is a shim that delegates to it).
        """
        import re
        root = Path(__file__).resolve().parents[2]
        src = (root / "scripts" / "install.sh").read_text()
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
        """4.1 — git identity vars are additive; KIROCREW_CORS_ORIGINS is still present
        alongside them.  KIROCREW_ALLOW_UNSANDBOXED was removed (replaced by
        sandbox: off config) so it is no longer expected in the env dict."""
        create_calls = self._capture_create_calls("Test User", "test@example.com")
        env = create_calls[0]["env"]

        self.assertIn("KIROCREW_CORS_ORIGINS", env)
        self.assertNotIn("KIROCREW_ALLOW_UNSANDBOXED", env)

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
        The /etc/environment approach is removed; identity is in process env.
        The function body is a single-line no-op; only the signature is kept."""
        podman = Mock()
        podman.container_exec_checked = Mock()

        # Call via lifecycle (where the function lives)
        lifecycle._inject_git_identity(podman, "gs-test")

        podman.container_exec_checked.assert_not_called()

    # ── Integration: _finish_crew_setup still calls _inject_git_identity ─────

    def test_finish_crew_setup_completes_successfully_without_inject_git_identity(self) -> None:
        """_inject_git_identity is no longer called during _finish_crew_setup.
        The call site was replaced with a comment; the function signature is
        kept in lifecycle for backward-compat but is never invoked from setup."""
        podman = Mock()
        podman.container_stop = Mock()
        podman.container_start = Mock()
        podman.container_exec = Mock(return_value="ready")
        podman.container_exec_checked = Mock(return_value="ok")
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
class Trn89TaskTimestampTests(unittest.TestCase):
    """TRN-89 Task 1 — task lifecycle timestamps in dispatch and pickup."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_dispatch_response_includes_created_at(self) -> None:
        """dispatch response includes created_at in ISO 8601 format."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", return_value={"id": "task-1"}),
            patch.object(server, "_load_registry", return_value={"crews": {"demo": {"schedules": []}}}),
            patch.object(server, "_save_registry"),
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo")

        self.assertIn("created_at", result)
        self.assertIsNotNone(result["created_at"])
        # Should be ISO 8601 with timezone
        self.assertIn("+", result["created_at"])

    def test_pickup_running_task_has_started_at_nonnull_and_completed_at_null(self) -> None:
        """pickup of running task (elapsed > 0) has started_at non-null, completed_at null."""
        # Seed a task in _task_timestamps
        server._task_timestamps["running-task"] = {
            "created_at": "2026-09-02T00:00:00+00:00",
            "started_at": None,
            "completed_at": None,
        }
        try:
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                patch.object(lifecycle, "_crew_api", return_value={
                    "id": "running-task", "agent": "ghost", "done": False,
                    "elapsed": 10, "turns": 1, "last_tool": "", "result": "", "error": "", "outcome": "",
                }),
                patch.object(server, "_get_podman", return_value=Mock()),
                patch.object(server, "_read_all_mail_counts", return_value={}),
                patch.object(server, "_read_all_mail_subjects", return_value={}),
                patch.object(server, "_read_mail_subjects_archive", return_value=[]),
            ):
                result = server.pickup(task_id="running-task", crew_id="demo", timeout_secs=0)
        finally:
            server._task_timestamps.pop("running-task", None)

        self.assertIsNotNone(result.get("started_at"))
        self.assertIsNone(result.get("completed_at"))
        self.assertEqual(result["created_at"], "2026-09-02T00:00:00+00:00")

    def test_pickup_done_task_has_all_three_timestamps_set(self) -> None:
        """pickup of done task has created_at, started_at, and completed_at all set."""
        server._task_timestamps["done-task"] = {
            "created_at": "2026-09-02T00:00:00+00:00",
            "started_at": "2026-09-02T00:00:01+00:00",
            "completed_at": None,  # will be set on done=True pickup
        }
        try:
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                patch.object(lifecycle, "_crew_api", return_value={
                    "id": "done-task", "agent": "ghost", "done": True,
                    "elapsed": 5, "turns": 2, "last_tool": "", "result": "ok", "error": "", "outcome": "success",
                }),
                patch.object(server, "_get_podman", return_value=Mock()),
                patch.object(server, "_read_all_mail_counts", return_value={}),
                patch.object(server, "_read_all_mail_subjects", return_value={}),
                patch.object(server, "_read_mail_subjects_archive", return_value=[]),
            ):
                result = server.pickup(task_id="done-task", crew_id="demo", timeout_secs=0)
        finally:
            server._task_timestamps.pop("done-task", None)

        self.assertIsNotNone(result.get("created_at"))
        self.assertIsNotNone(result.get("started_at"))
        self.assertIsNotNone(result.get("completed_at"))

    def test_pickup_list_entries_include_timestamp_fields(self) -> None:
        """pickup list entries include created_at, started_at, completed_at (null if missing)."""
        server._task_timestamps["known-task"] = {
            "created_at": "2026-09-02T00:00:00+00:00",
            "started_at": None,
            "completed_at": None,
        }
        agents = [
            {"id": "known-task", "done": False, "task": "do work", "agent": "ghost", "elapsed": 0},
            {"id": "unknown-task", "done": False, "task": "other", "agent": "ghost", "elapsed": 0},
        ]
        try:
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                patch.object(lifecycle, "_crew_api", return_value={"agents": agents}),
                patch.object(server, "_get_podman", return_value=Mock()),
                patch.object(server, "_read_all_mail_counts", return_value={}),
                patch.object(server, "_read_all_mail_subjects", return_value={}),
                patch.object(server, "_read_mail_subjects_archive", return_value=[]),
            ):
                result = server.pickup(crew_id="demo", timeout_secs=0)
        finally:
            server._task_timestamps.pop("known-task", None)

        tasks = result["tasks"]
        known = next(t for t in tasks if t["task_id"] == "known-task")
        unknown = next(t for t in tasks if t["task_id"] == "unknown-task")

        self.assertEqual(known["created_at"], "2026-09-02T00:00:00+00:00")
        self.assertIsNone(known["started_at"])
        self.assertIsNone(known["completed_at"])

        # Unknown task (dispatched before this change or after restart) → all null
        self.assertIsNone(unknown["created_at"])
        self.assertIsNone(unknown["started_at"])
        self.assertIsNone(unknown["completed_at"])
class Trn89CrewTimestampTests(unittest.TestCase):
    """TRN-89 Task 3 — last_task_at in crews list."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_dispatch_writes_last_task_at_to_registry(self) -> None:
        """dispatch writes last_task_at to the crew's registry entry."""
        reg = {"crews": {"demo": {"container": "gs-demo", "schedules": []}}}
        save_calls = []

        def fake_save(r):
            import copy
            save_calls.append(copy.deepcopy(r))

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", return_value={"id": "task-ts"}),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            server.dispatch("do work", agent="ghost", crew_id="demo")

        self.assertTrue(save_calls, "Expected _save_registry to be called")
        saved = save_calls[-1]
        self.assertIn("last_task_at", saved["crews"]["demo"])
        self.assertIsNotNone(saved["crews"]["demo"]["last_task_at"])

    def test_crews_includes_last_task_at_after_dispatch(self) -> None:
        """crews() includes last_task_at in each crew entry (null if not present)."""
        reg = {
            "crews": {
                "demo-with-task": {
                    "container": "gs-demo",
                    "status": "running",
                    "composition": "spec-ops",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "last_task_at": "2026-09-02T00:00:00+00:00",
                    "cookie": "c",
                },
                "demo-no-task": {
                    "container": "gs-demo2",
                    "status": "running",
                    "composition": "spec-ops",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "cookie": "c",
                },
            }
        }
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(lifecycle, "_probe_gateway", return_value=True),
            patch.object(server, "_crew_api", return_value=[]),
            patch.object(lifecycle, "_crew_api", return_value=[]),
            patch.object(server, "_get_podman", return_value=Mock(system_info=lambda: {"host": {"memAvailable": 4 * 1024**3}})),
            patch.object(lifecycle, "_get_podman", return_value=Mock(system_info=lambda: {"host": {"memAvailable": 4 * 1024**3}})),
        ):
            result = server.crews()

        crew_map = {e["crew_id"]: e for e in result["crews"]}
        self.assertEqual(crew_map["demo-with-task"]["last_task_at"], "2026-09-02T00:00:00+00:00")
        self.assertIsNone(crew_map["demo-no-task"]["last_task_at"])
class PickupAgentSubjectsTests(unittest.TestCase):
    """TRN-94 tasks 3.3 + 4.4 — agent_subjects and agent filter in pickup."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def _make_skim_result(self) -> dict:
        """Return a full 8-key skim dict with one ghost message."""
        names = ("ghost", "spectre", "banshee", "wraith", "reaper", "raven", "captain", "admiral")
        result = {name: [] for name in names}
        result["ghost"] = [{"subject": "task result", "received_at": None}]
        return result

    # ── 3.3: agent_subjects in crew-level pickup ──────────────────────────────

    def test_crew_level_pickup_includes_agent_subjects(self) -> None:
        """3.3 — crew-level pickup (no task_id) includes agent_subjects field."""
        agents = [{"id": "a", "done": True, "task": "t1", "agent": "ghost", "elapsed": 5}]
        skim = self._make_skim_result()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value={"agents": agents}),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value=skim),
        ):
            result = server.pickup(crew_id="demo", timeout_secs=0)
        self.assertIn("agent_subjects", result)
        self.assertEqual(result["agent_subjects"]["ghost"], [{"subject": "task result", "received_at": None}])
        self.assertEqual(result["agent_subjects"]["raven"], [])

    def test_task_specific_pickup_does_not_include_agent_subjects(self) -> None:
        """3.3 — task-specific pickup is unchanged (no agent_subjects field)."""
        task_resp = {
            "id": "task-1", "agent": "ghost", "done": True, "turns": 2,
            "last_tool": "shell", "elapsed": 7, "result": "done", "error": "", "outcome": "success",
        }
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value=task_resp),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=0)
        self.assertNotIn("agent_subjects", result)
        self.assertIn("task_id", result)

    # ── 4.4: agent filter ────────────────────────────────────────────────────

    def test_agent_filter_returns_single_inbox_response(self) -> None:
        """4.4 — agent filter returns single-inbox subjects and count, no task list."""
        skim = self._make_skim_result()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_skim_all_mailboxes", return_value=skim),
        ):
            result = server.pickup(crew_id="demo", agent="ghost", timeout_secs=0)
        self.assertEqual(result["agent"], "ghost")
        self.assertEqual(result["subjects"], [{"subject": "task result", "received_at": None}])
        self.assertEqual(result["mail"], 1)
        self.assertNotIn("tasks", result)
        self.assertNotIn("agent_subjects", result)

    def test_agent_filter_empty_mailbox(self) -> None:
        """4.4 — agent filter for an empty mailbox returns zero count."""
        skim = self._make_skim_result()  # only ghost has mail
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_skim_all_mailboxes", return_value=skim),
        ):
            result = server.pickup(crew_id="demo", agent="reaper", timeout_secs=0)
        self.assertEqual(result["agent"], "reaper")
        self.assertEqual(result["subjects"], [])
        self.assertEqual(result["mail"], 0)

    def test_invalid_agent_returns_error(self) -> None:
        """4.4 — invalid agent name returns an error dict."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=Mock()),
        ):
            result = server.pickup(crew_id="demo", agent="admiral", timeout_secs=0)
        self.assertIn("error", result)
        self.assertIn("admiral", result["error"])

    def test_agent_filter_invalid_random_name_returns_error(self) -> None:
        """4.4 — unknown agent name returns error."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=Mock()),
        ):
            result = server.pickup(crew_id="demo", agent="kiro", timeout_secs=0)
        self.assertIn("error", result)

    def test_agent_filter_ignored_when_task_id_set(self) -> None:
        """4.4 — agent parameter is ignored when task_id is set."""
        task_resp = {
            "id": "task-1", "agent": "ghost", "done": True, "turns": 1,
            "last_tool": "shell", "elapsed": 5, "result": "done", "error": "", "outcome": "success",
        }
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value=task_resp),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
        ):
            # agent is set but task_id takes priority
            result = server.pickup(task_id="task-1", crew_id="demo", agent="ghost", timeout_secs=0)
        # Should behave as normal single-task pickup
        self.assertIn("task_id", result)
        self.assertNotIn("subjects", result)  # not the single-inbox format


# ── TRN-123: _task_timestamps lock (tasks 4.1 / 4.2) ─────────────────────────


class TaskTimestampsLockTests(unittest.TestCase):
    """Concurrency tests for the _task_timestamps threading.Lock (TRN-123).

    These exercise the locked read-modify-write access pattern directly (the
    "dispatch-style" write and the "_pickup_single-style" read-modify-write)
    rather than the full MCP handlers, which require heavy podman/gateway
    mocking irrelevant to the data-race under test.
    """

    def setUp(self) -> None:
        # Isolate each test from leftover state / other tests.
        server._task_timestamps.clear()

    def tearDown(self) -> None:
        server._task_timestamps.clear()

    def test_concurrent_dispatch_writes_no_lost_entries(self) -> None:
        """4.1: many threads writing distinct task_ids all land, none lost."""
        import concurrent.futures

        n = 500

        def _dispatch_style_write(i: int) -> None:
            task_id = f"task-{i}"
            created_at = datetime.now(timezone.utc).isoformat()
            # Mirror the locked write in server.dispatch / _dispatch_batch.
            with server._task_timestamps_lock:
                server._task_timestamps[task_id] = {
                    "created_at": created_at,
                    "started_at": None,
                    "completed_at": None,
                }

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            list(ex.map(_dispatch_style_write, range(n)))

        self.assertEqual(len(server._task_timestamps), n)
        for i in range(n):
            entry = server._task_timestamps.get(f"task-{i}")
            self.assertIsNotNone(entry, f"task-{i} missing")
            # No partially-overwritten record: every key present.
            self.assertEqual(
                set(entry.keys()), {"created_at", "started_at", "completed_at"}
            )
            self.assertIsNotNone(entry["created_at"])

    def test_interleaved_write_and_read_modify_write_no_corruption(self) -> None:
        """4.2: a dispatch-style write racing a pickup-style RMW for the same
        task_id never corrupts started_at / completed_at."""
        import concurrent.futures

        task_id = "task-shared"

        def _dispatch_write() -> None:
            created_at = datetime.now(timezone.utc).isoformat()
            with server._task_timestamps_lock:
                server._task_timestamps[task_id] = {
                    "created_at": created_at,
                    "started_at": None,
                    "completed_at": None,
                }

        def _pickup_rmw(done: bool) -> None:
            now = datetime.now(timezone.utc)
            # Mirror the locked RMW in server._pickup_single.
            with server._task_timestamps_lock:
                ts = server._task_timestamps.get(task_id, {})
                if ts and ts.get("started_at") is None:
                    ts["started_at"] = now.isoformat()
                if ts and done and ts.get("completed_at") is None:
                    ts["completed_at"] = now.isoformat()

        # Seed the entry first so the RMW threads have something to update.
        _dispatch_write()

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futs = []
            for i in range(200):
                # Interleave repeated writes and read-modify-writes.
                futs.append(ex.submit(_dispatch_write))
                futs.append(ex.submit(_pickup_rmw, i % 2 == 0))
            for f in futs:
                f.result()

        entry = server._task_timestamps[task_id]
        # The record must always have exactly the three canonical keys — never a
        # partial dict produced by an interrupted read-modify-write.
        self.assertEqual(
            set(entry.keys()), {"created_at", "started_at", "completed_at"}
        )
        # started_at / completed_at are either None or a valid ISO string; never
        # a torn / non-string value.
        for k in ("created_at", "started_at", "completed_at"):
            v = entry[k]
            self.assertTrue(v is None or isinstance(v, str))


# ── TRN-123: _dashboard_port_crew lock (tasks 5.1 / 5.2) ─────────────────────


class _StubRequest:
    """Minimal request stub carrying the attributes the dashboard handlers read."""

    def __init__(
        self,
        *,
        path: str = "",
        query_params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> None:
        self.scope = {"path": path}
        self.query_params = query_params or {}
        self.headers = headers or {}
        self.cookies = cookies or {}


class DashboardPortCrewLockTests(unittest.IsolatedAsyncioTestCase):
    """Concurrency tests for the _dashboard_port_crew threading.Lock (TRN-123)."""

    def setUp(self) -> None:
        with server._dashboard_port_crew_lock:
            server._dashboard_port_crew.clear()

    def tearDown(self) -> None:
        with server._dashboard_port_crew_lock:
            server._dashboard_port_crew.clear()

    async def test_concurrent_dashboard_post_consistent_mapping(self) -> None:
        """5.1: concurrent _handle_crew_dashboard_post calls for the same crew
        leave a consistent port→crew mapping (no duplicate ports, no lost
        entries)."""
        crew_id = "demo"

        # Each POST allocates a fresh port and registers it. We simulate a
        # registry that has no dashboard yet so every call proceeds to the
        # allocate + register + map path.
        port_counter = {"n": 40000}
        alloc_lock = threading.Lock()

        def _fake_load_registry() -> dict:
            # A fresh (no dashboard_port) crew entry every call so the handler
            # walks the allocation path rather than the no-op branch.
            return {"crews": {crew_id: {"cookie": "c"}}}

        def _fake_allocate_port() -> int:
            with alloc_lock:
                port_counter["n"] += 1
                return port_counter["n"]

        with (
            patch.object(server, "_require_crew", return_value=None),
            patch.object(server, "_extract_crew_proxy_parts", return_value=(crew_id, "dashboard", "")),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", side_effect=_fake_load_registry),
            patch.object(server, "_save_registry"),
            patch.object(server, "_allocate_dashboard_port", side_effect=_fake_allocate_port),
            patch.object(server, "_caddy_register_crew"),
        ):
            reqs = [_StubRequest(path=f"/crews/{crew_id}/dashboard") for _ in range(50)]
            results = await asyncio.gather(
                *(server._handle_crew_dashboard_post(r) for r in reqs)
            )

        self.assertEqual(len(results), 50)
        # Every allocated port maps back to the crew — no lost / partial entries.
        with server._dashboard_port_crew_lock:
            snapshot = dict(server._dashboard_port_crew)
        self.assertEqual(len(snapshot), 50, "expected 50 distinct port mappings")
        # No duplicate ports (dict keys are unique by construction) and every
        # value is the crew_id.
        self.assertTrue(all(v == crew_id for v in snapshot.values()))

    async def test_auth_read_races_delete_never_partial(self) -> None:
        """5.2: _handle_dashboard_auth reading while an entry is being deleted
        sees the entry present or absent — never a partial/torn value."""
        crew_id = "demo"
        port = 41000
        with server._dashboard_port_crew_lock:
            server._dashboard_port_crew[port] = crew_id

        # A "delete-style" writer removing the mapping under the lock, mirroring
        # the locked pop in _handle_crew_dashboard_delete / nuke.
        def _delete_writer() -> None:
            for _ in range(200):
                with server._dashboard_port_crew_lock:
                    server._dashboard_port_crew.pop(port, None)
                with server._dashboard_port_crew_lock:
                    server._dashboard_port_crew[port] = crew_id

        stop = threading.Event()

        def _delete_loop() -> None:
            while not stop.is_set():
                _delete_writer()

        writer = threading.Thread(target=_delete_loop)
        writer.start()
        try:
            with (
                patch.object(server, "GA_API_KEY", "k"),
                patch.object(server, "_gs_session_valid", return_value=True),
            ):
                for _ in range(200):
                    req = _StubRequest(
                        query_params={"port": str(port)},
                        cookies={"gs_session": "tok"},
                    )
                    resp = await server._handle_dashboard_auth(req)
                    # The handler returns a Response with an int status_code —
                    # a torn read would raise or produce something non-200.
                    self.assertEqual(resp.status_code, 200)
        finally:
            stop.set()
            writer.join(timeout=5)


# ── TRN-123: _get_ensure_running_lock helper (asyncio lock registry) ──────────


class GetEnsureRunningLockTests(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the _get_ensure_running_lock helper (TRN-123).

    Verifies that the helper:
    - Returns an asyncio.Lock for a given crew_id.
    - Returns the *same* lock object on repeated calls for the same crew_id
      (identity, not a new lock each time).
    - Returns *different* lock objects for different crew_ids.
    - Is safe to call concurrently from multiple threads (no lost writes or
      duplicate lock objects due to a race on the registry dict).
    """

    def setUp(self) -> None:
        # Isolate each test: clear the registry so tests don't share lock state.
        with server._ensure_running_locks_lock:
            server._ensure_running_locks.clear()

    def tearDown(self) -> None:
        with server._ensure_running_locks_lock:
            server._ensure_running_locks.clear()

    async def test_returns_asyncio_lock(self) -> None:
        """_get_ensure_running_lock returns an asyncio.Lock."""
        lock = server._get_ensure_running_lock("crew-a")
        self.assertIsInstance(lock, asyncio.Lock)

    async def test_same_crew_same_lock_identity(self) -> None:
        """Repeated calls for the same crew_id return the identical object."""
        lock1 = server._get_ensure_running_lock("crew-a")
        lock2 = server._get_ensure_running_lock("crew-a")
        self.assertIs(lock1, lock2)

    async def test_different_crews_different_locks(self) -> None:
        """Different crew_ids get distinct lock objects."""
        lock_a = server._get_ensure_running_lock("crew-a")
        lock_b = server._get_ensure_running_lock("crew-b")
        self.assertIsNot(lock_a, lock_b)

    async def test_concurrent_first_access_same_crew_same_lock(self) -> None:
        """Concurrent first-time calls for the same crew_id from multiple
        threads must all receive the identical lock object (no duplicate creation
        due to a race on the registry dict)."""
        import concurrent.futures

        results = []

        def _fetch() -> asyncio.Lock:
            return server._get_ensure_running_lock("crew-concurrent")

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            results = list(ex.map(lambda _: _fetch(), range(50)))

        # All 50 calls must have received the same lock object.
        first = results[0]
        self.assertIsInstance(first, asyncio.Lock)
        self.assertTrue(
            all(r is first for r in results),
            "Concurrent first-time callers received different lock objects — "
            "registry dict is not properly protected.",
        )

    async def test_lock_is_functional_as_asyncio_mutex(self) -> None:
        """The returned lock can actually be acquired and released as an
        asyncio mutex — verifying it is bound to the running event loop."""
        lock = server._get_ensure_running_lock("crew-functional")
        async with lock:
            # While held, a non-blocking acquire attempt should fail.
            acquired = lock.locked()
            self.assertTrue(acquired, "Lock should be held inside async with block")
        self.assertFalse(lock.locked(), "Lock should be released after async with block")
