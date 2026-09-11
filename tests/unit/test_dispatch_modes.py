"""Unit tests for TRN-133 dispatch modes.

Tests cover:
  4.1  mode="headless"  — /api/spawn body has no parent_session
  4.2  mode="anchored"  — body has parent_session="dashboard:<crew-id>"
  4.3  mode="free"      — body has parent_session matching dashboard:<crew-id>-<8hex>
                         and response includes parent_session
  4.4  Two dispatch calls with unique mode produce different parent_session values
  4.5  Invalid mode returns error, no spawn call made
  4.6  No explicit mode, crew has dashboard_url set → effective mode anchored
  4.7  No explicit mode, crew has no dashboard_url → effective mode headless
  4.8  Batch with mode="free" — each task gets a distinct parent_session
  4.9  Batch with mode="anchored" — all tasks get the same parent_session
"""

from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from tests.unit.helpers import lifecycle, server  # noqa: F401


_FREE_PS_RE = re.compile(r"^dashboard:[a-z0-9-]+-[0-9a-f]{8}$")

# Crew fixture without dashboard (headless default)
_CREW_NO_DASH = {"container": "gs-demo"}
# Crew fixture with active dashboard (anchored default)
_CREW_WITH_DASH = {"container": "gs-demo", "dashboard_port": 64058}


class DispatchModeHeadlessTests(unittest.TestCase):
    """4.1 — headless mode sends no parent_session."""

    def test_headless_mode_no_parent_session(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-1"}
            ) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", mode="headless")

        self.assertEqual(result["task_id"], "task-1")
        self.assertEqual(result["mode"], "headless")
        body = api.call_args.kwargs["json"]
        self.assertNotIn("parent_session", body)

    def test_headless_default_when_no_dashboard_url(self) -> None:
        """No explicit mode + no dashboard_url → headless."""
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-2"}
            ) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo")

        self.assertEqual(result["mode"], "headless")
        body = api.call_args.kwargs["json"]
        self.assertNotIn("parent_session", body)


class DispatchModeAnchoredTests(unittest.TestCase):
    """4.2 — anchored mode sends parent_session="dashboard:<crew-id>"."""

    def test_anchored_mode_parent_session(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-3"}
            ) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", mode="anchored")

        self.assertEqual(result["mode"], "anchored")
        body = api.call_args.kwargs["json"]
        self.assertEqual(body["parent_session"], "dashboard:demo")

    def test_anchored_response_has_no_parent_session_key(self) -> None:
        """Anchored response does NOT include parent_session (only free mode does)."""
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(lifecycle, "_crew_api", return_value={"id": "task-x"}),
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", mode="anchored")

        # anchored: parent_session NOT echoed in response (only free mode echoes it)
        self.assertNotIn("parent_session", result)


class DispatchModeFreeTests(unittest.TestCase):
    """4.3 — free mode sends parent_session matching dashboard:<crew-id>-<8hex>
    and response includes parent_session."""

    def test_free_mode_body_and_response(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-4"}
            ) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", mode="free")

        self.assertEqual(result["mode"], "free")
        # parent_session in response
        self.assertIn("parent_session", result)
        ps = result["parent_session"]
        self.assertRegex(ps, _FREE_PS_RE)
        # parent_session in spawn body matches response value
        body = api.call_args.kwargs["json"]
        self.assertEqual(body["parent_session"], ps)


class DispatchModeFreeUniquenessTests(unittest.TestCase):
    """4.4 — two free dispatches produce distinct parent_session values."""

    def test_two_free_dispatches_different_parent_sessions(self) -> None:
        sessions = []
        for tid in ("task-a", "task-b"):
            with (
                patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
                patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
                patch.object(lifecycle, "_crew_api", return_value={"id": tid}),
            ):
                r = server.dispatch("do work", agent="ghost", crew_id="demo", mode="free")
            sessions.append(r["parent_session"])

        self.assertEqual(len(sessions), 2)
        self.assertNotEqual(sessions[0], sessions[1])
        for ps in sessions:
            self.assertRegex(ps, _FREE_PS_RE)


class DispatchModeInvalidTests(unittest.TestCase):
    """4.5 — invalid mode returns error, no spawn call made."""

    def test_invalid_mode_returns_error_no_spawn(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(lifecycle, "_crew_api") as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", mode="turbo")

        self.assertIn("error", result)
        self.assertIn("mode", result["error"])
        api.assert_not_called()

    def test_invalid_mode_empty_string_returns_error(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(lifecycle, "_crew_api") as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", mode="")

        self.assertIn("error", result)
        api.assert_not_called()


class DispatchModeDashboardDefaultTests(unittest.TestCase):
    """4.6 / 4.7 — default mode derived from dashboard_url at dispatch time."""

    def _dispatch_no_mode(self, crew: dict) -> tuple[dict, object]:
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(lifecycle, "_crew_api", return_value={"id": "task-r"}) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo")
        return result, api

    def test_dashboard_url_set_defaults_to_anchored(self) -> None:
        """4.6 — dashboard_url present → effective mode anchored."""
        result, api = self._dispatch_no_mode(_CREW_WITH_DASH)
        self.assertEqual(result["mode"], "anchored")
        body = api.call_args.kwargs["json"]
        self.assertEqual(body["parent_session"], "dashboard:demo")

    def test_no_dashboard_url_defaults_to_headless(self) -> None:
        """4.7 — no dashboard_url → effective mode headless, no parent_session."""
        result, api = self._dispatch_no_mode(_CREW_NO_DASH)
        self.assertEqual(result["mode"], "headless")
        body = api.call_args.kwargs["json"]
        self.assertNotIn("parent_session", body)


class DispatchModeBatchFreeTests(unittest.TestCase):
    """4.8 — batch with mode="free" gives each task a distinct parent_session."""

    def test_batch_free_distinct_parent_sessions(self) -> None:
        spawn_responses = [{"id": f"t{i}"} for i in range(3)]
        call_idx = {"n": 0}

        def fake_api(crew, crew_id, method, path, **kw):
            i = call_idx["n"]
            call_idx["n"] += 1
            return spawn_responses[i]

        with (
            patch.object(lifecycle, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(lifecycle, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=fake_api) as api,
            patch.object(lifecycle, "_write_batch", return_value=None),
            patch.object(lifecycle, "_record_last_task_at"),
        ):
            result = server.dispatch(
                tasks=["task A", "task B", "task C"],
                agent="ghost",
                crew_id="demo",
                mode="free",
            )

        self.assertNotIn("error", result)
        self.assertEqual(result["mode"], "free")
        # Each call must have had a distinct parent_session
        all_ps = [
            call.kwargs["json"].get("parent_session")
            for call in api.call_args_list
        ]
        self.assertEqual(len(all_ps), 3)
        # All present and match the pattern
        for ps in all_ps:
            self.assertIsNotNone(ps)
            self.assertRegex(ps, _FREE_PS_RE)
        # All distinct
        self.assertEqual(len(set(all_ps)), 3)
        # task_parent_sessions in response
        self.assertIn("task_parent_sessions", result)
        self.assertEqual(len(result["task_parent_sessions"]), 3)


class DispatchModeBatchAnchoredTests(unittest.TestCase):
    """4.9 — batch with mode="anchored" gives all tasks the same parent_session."""

    def test_batch_anchored_same_parent_session(self) -> None:
        spawn_responses = [{"id": f"t{i}"} for i in range(2)]
        call_idx = {"n": 0}

        def fake_api(crew, crew_id, method, path, **kw):
            i = call_idx["n"]
            call_idx["n"] += 1
            return spawn_responses[i]

        with (
            patch.object(lifecycle, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(lifecycle, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=fake_api) as api,
            patch.object(lifecycle, "_write_batch", return_value=None),
            patch.object(lifecycle, "_record_last_task_at"),
        ):
            result = server.dispatch(
                tasks=["task A", "task B"],
                agent="ghost",
                crew_id="demo",
                mode="anchored",
            )

        self.assertNotIn("error", result)
        self.assertEqual(result["mode"], "anchored")
        # Every spawn body uses the same parent_session
        all_ps = [
            call.kwargs["json"].get("parent_session")
            for call in api.call_args_list
        ]
        self.assertEqual(len(all_ps), 2)
        self.assertEqual(all_ps[0], "dashboard:demo")
        self.assertEqual(all_ps[1], "dashboard:demo")


if __name__ == "__main__":
    unittest.main()
