"""Unit tests for the dispatch slot parameter.

After TRN-192 the ``slot`` parameter has two modes only (``slot: bool | None``):

  slot=None  — let the system decide:
                 enrolled agent   → member DM slot
                                    (parent_session="dashboard:member-<slug>",
                                     response "slot" echoes the agent name)
                 unenrolled agent → headless (no parent_session, "slot": null)
  slot=False — explicit headless, regardless of enrollment
               (no parent_session, "slot": null)

``slot=True`` (UUID auto-generation) and arbitrary string slot names
(e.g. "bridge", "custom-name") are no longer accepted values — member slots
cover all legitimate slotted-dispatch use cases, and member slots are
pre-created at enrollment time so no dispatch-time slot pre-creation occurs.

Note: dispatch() reaches the crew via _crew_api_with_recovery, which delegates
to _crew_api on its first attempt. There is no longer any slot pre-creation
call, so the spawn is the only _crew_api call and api.call_args is the spawn.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.unit.helpers import lifecycle, server  # noqa: F401


# Crew fixture without dashboard (headless default)
_CREW_NO_DASH = {"container": "gs-demo", "enrolled_agents": ["ghost", "spectre", "banshee", "wraith", "reaper", "raven"]}
# Crew fixture with active dashboard — member routing is independent of this now
_CREW_WITH_DASH = {"container": "gs-demo", "dashboard_port": 64058, "enrolled_agents": ["ghost", "spectre", "banshee", "wraith", "reaper", "raven"]}


class DispatchSlotNoneTests(unittest.TestCase):
    """slot=None routes an enrolled agent to its member DM slot."""

    def test_slot_none_enrolled_uses_member_slot(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-1"}
            ) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", slot=None)

        self.assertEqual(result["task_id"], "task-1")
        self.assertEqual(result["slot"], "ghost")
        body = api.call_args.kwargs["json"]
        self.assertEqual(body.get("parent_session"), "dashboard:member-ghost")


class DispatchSlotFalseTests(unittest.TestCase):
    """slot=False is explicit headless even for an enrolled agent."""

    def test_slot_false_enrolled_is_headless(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-2"}
            ) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", slot=False)

        self.assertIsNone(result["slot"])
        body = api.call_args.kwargs["json"]
        self.assertNotIn("parent_session", body)

    def test_slot_false_dashboard_crew_is_headless(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_WITH_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_WITH_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-2b"}
            ) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", slot=False)

        self.assertIsNone(result["slot"])
        body = api.call_args.kwargs["json"]
        self.assertNotIn("parent_session", body)


class DispatchSlotDefaultResolutionTests(unittest.TestCase):
    """Default (slot omitted) routes enrolled agents to the member DM slot,
    independent of whether the crew has a dashboard_port."""

    def _dispatch_no_slot(self, crew: dict) -> tuple[dict, object]:
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(lifecycle, "_crew_api", return_value={"id": "task-r"}) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo")
        return result, api

    def test_dashboard_port_set_defaults_to_member_slot(self) -> None:
        result, api = self._dispatch_no_slot(_CREW_WITH_DASH)
        self.assertEqual(result["slot"], "ghost")
        body = api.call_args.kwargs["json"]
        self.assertEqual(body["parent_session"], "dashboard:member-ghost")

    def test_no_dashboard_port_defaults_to_member_slot(self) -> None:
        result, api = self._dispatch_no_slot(_CREW_NO_DASH)
        self.assertEqual(result["slot"], "ghost")
        body = api.call_args.kwargs["json"]
        self.assertEqual(body["parent_session"], "dashboard:member-ghost")


class DispatchSlotUnenrolledTests(unittest.TestCase):
    """Unenrolled agents (no enrolled_agents key) dispatch headless regardless
    of dashboard_port — the bridge fallback is removed."""

    _CREW_NO_DASH_UNENROLLED = {"container": "gs-demo"}
    _CREW_WITH_DASH_UNENROLLED = {"container": "gs-demo", "dashboard_port": 64058}

    def _dispatch_unenrolled(self, crew: dict) -> tuple[dict, object]:
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(lifecycle, "_crew_api", return_value={"id": "task-u"}) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo")
        return result, api

    def test_unenrolled_dashboard_crew_is_headless(self) -> None:
        """Unenrolled agent on a dashboard crew → headless (bridge removed)."""
        result, api = self._dispatch_unenrolled(self._CREW_WITH_DASH_UNENROLLED)
        self.assertIsNone(result["slot"])
        body = api.call_args.kwargs["json"]
        self.assertNotIn("parent_session", body)

    def test_unenrolled_non_dashboard_crew_is_headless(self) -> None:
        """Unenrolled agent on a non-dashboard crew → headless."""
        result, api = self._dispatch_unenrolled(self._CREW_NO_DASH_UNENROLLED)
        self.assertIsNone(result["slot"])
        body = api.call_args.kwargs["json"]
        self.assertNotIn("parent_session", body)


class DispatchSlotBatchMemberTests(unittest.TestCase):
    """Batch with slot omitted gives every task the shared member DM slot;
    no task_slots field is emitted."""

    def test_batch_member_slot_shared(self) -> None:
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
            patch.object(lifecycle, "_crew_api", return_value={}),
            patch.object(lifecycle, "_write_batch", return_value=None),
            patch.object(lifecycle, "_record_last_task_at"),
        ):
            result = server.dispatch(
                tasks=["task A", "task B", "task C"],
                agent="ghost",
                crew_id="demo",
            )

        self.assertNotIn("error", result)
        self.assertEqual(result["slot"], "ghost")
        self.assertNotIn("task_slots", result)
        all_ps = [
            call.kwargs["json"].get("parent_session")
            for call in api.call_args_list
        ]
        self.assertEqual(len(all_ps), 3)
        for ps in all_ps:
            self.assertEqual(ps, "dashboard:member-ghost")


class DispatchSlotBatchHeadlessTests(unittest.TestCase):
    """Batch with slot=False dispatches every task headless; no task_slots."""

    def test_batch_headless_no_parent_session(self) -> None:
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
            patch.object(lifecycle, "_crew_api", return_value={}),
            patch.object(lifecycle, "_write_batch", return_value=None),
            patch.object(lifecycle, "_record_last_task_at"),
        ):
            result = server.dispatch(
                tasks=["task A", "task B"],
                agent="ghost",
                crew_id="demo",
                slot=False,
            )

        self.assertNotIn("error", result)
        self.assertIsNone(result["slot"])
        self.assertNotIn("task_slots", result)
        for call in api.call_args_list:
            self.assertNotIn("parent_session", call.kwargs["json"])


if __name__ == "__main__":
    unittest.main()
