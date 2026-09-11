"""Unit tests for TRN-147 dispatch slot parameter.

Replaces the TRN-133 ``mode`` tests. The ``mode`` parameter is gone; dispatch
now takes ``slot: str | bool | None``:

  3.2  slot=None          — /api/spawn body has no parent_session, response "slot": null
  3.3  slot="bridge"      — body parent_session="dashboard:bridge", response "slot": "bridge"
  3.4  slot=True          — body parent_session matches ^dashboard:[0-9a-f]{8}$,
                            response "slot" carries that 8-hex name
  3.5  two slot=True       — distinct parent_session values
  3.6  slot="custom-name"  — body parent_session="dashboard:custom-name"
  3.7  no slot + dashboard_port set  — effective slot "bridge"
  3.8  no slot + no dashboard_port    — effective slot null (headless)
  3.9  batch slot=True     — each task gets a distinct parent_session
  3.10 batch slot="shared" — all tasks get parent_session="dashboard:shared"

Note: dispatch() reaches the crew via _crew_api_with_recovery, which delegates
to _crew_api on its first attempt. Slot pre-creation calls _crew_api directly
and happens before the spawn, so patching lifecycle._crew_api intercepts both;
the spawn is always the LAST _crew_api call, hence api.call_args is the spawn.
"""

from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from tests.unit.helpers import lifecycle, server  # noqa: F401


_TRUE_SLOT_PS_RE = re.compile(r"^dashboard:[0-9a-f]{8}$")
_TRUE_SLOT_NAME_RE = re.compile(r"^[0-9a-f]{8}$")

# Crew fixture without dashboard (headless default)
_CREW_NO_DASH = {"container": "gs-demo"}
# Crew fixture with active dashboard (bridge default)
_CREW_WITH_DASH = {"container": "gs-demo", "dashboard_port": 64058}


class DispatchSlotNoneTests(unittest.TestCase):
    """3.2 — slot=None sends no parent_session and echoes null."""

    def test_slot_none_no_parent_session(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-1"}
            ) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", slot=None)

        self.assertEqual(result["task_id"], "task-1")
        self.assertIsNone(result["slot"])
        body = api.call_args.kwargs["json"]
        self.assertNotIn("parent_session", body)


class DispatchSlotBridgeTests(unittest.TestCase):
    """3.3 — slot="bridge" attaches to dashboard:bridge and echoes "bridge"."""

    def test_slot_bridge_parent_session(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-3"}
            ) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", slot="bridge")

        self.assertEqual(result["slot"], "bridge")
        body = api.call_args.kwargs["json"]
        self.assertEqual(body["parent_session"], "dashboard:bridge")


class DispatchSlotTrueTests(unittest.TestCase):
    """3.4 — slot=True generates an 8-hex slot; body + response agree."""

    def test_slot_true_body_and_response(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-4"}
            ) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo", slot=True)

        slot_name = result["slot"]
        self.assertIsNotNone(slot_name)
        self.assertRegex(slot_name, _TRUE_SLOT_NAME_RE)
        body = api.call_args.kwargs["json"]
        self.assertRegex(body["parent_session"], _TRUE_SLOT_PS_RE)
        # response slot name is the suffix of the body's parent_session
        self.assertEqual(body["parent_session"], f"dashboard:{slot_name}")


class DispatchSlotTrueUniquenessTests(unittest.TestCase):
    """3.5 — two slot=True dispatches produce distinct parent_session values."""

    def test_two_slot_true_dispatches_distinct(self) -> None:
        sessions = []
        for tid in ("task-a", "task-b"):
            with (
                patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
                patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
                patch.object(
                    lifecycle, "_crew_api", return_value={"id": tid}
                ) as api,
            ):
                server.dispatch("do work", agent="ghost", crew_id="demo", slot=True)
                sessions.append(api.call_args.kwargs["json"]["parent_session"])

        self.assertEqual(len(sessions), 2)
        self.assertNotEqual(sessions[0], sessions[1])
        for ps in sessions:
            self.assertRegex(ps, _TRUE_SLOT_PS_RE)


class DispatchSlotCustomNameTests(unittest.TestCase):
    """3.6 — slot="custom-name" → parent_session="dashboard:custom-name"."""

    def test_slot_custom_name(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=_CREW_NO_DASH),
            patch.object(server, "_ensure_crew_running", return_value=_CREW_NO_DASH),
            patch.object(
                lifecycle, "_crew_api", return_value={"id": "task-c"}
            ) as api,
        ):
            result = server.dispatch(
                "do work", agent="ghost", crew_id="demo", slot="custom-name"
            )

        self.assertEqual(result["slot"], "custom-name")
        body = api.call_args.kwargs["json"]
        self.assertEqual(body["parent_session"], "dashboard:custom-name")


class DispatchSlotDefaultResolutionTests(unittest.TestCase):
    """3.7 / 3.8 — default slot derived from dashboard_port at dispatch time."""

    def _dispatch_no_slot(self, crew: dict) -> tuple[dict, object]:
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(lifecycle, "_crew_api", return_value={"id": "task-r"}) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo")
        return result, api

    def test_dashboard_port_set_defaults_to_bridge(self) -> None:
        """3.7 — dashboard_port present → effective slot "bridge"."""
        result, api = self._dispatch_no_slot(_CREW_WITH_DASH)
        self.assertEqual(result["slot"], "bridge")
        body = api.call_args.kwargs["json"]
        self.assertEqual(body["parent_session"], "dashboard:bridge")

    def test_no_dashboard_port_defaults_to_null(self) -> None:
        """3.8 — no dashboard_port → effective slot null (headless)."""
        result, api = self._dispatch_no_slot(_CREW_NO_DASH)
        self.assertIsNone(result["slot"])
        body = api.call_args.kwargs["json"]
        self.assertNotIn("parent_session", body)


class DispatchSlotBatchTrueTests(unittest.TestCase):
    """3.9 — batch with slot=True gives each task a distinct parent_session."""

    def test_batch_slot_true_distinct(self) -> None:
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
                slot=True,
            )

        self.assertNotIn("error", result)
        self.assertTrue(result["slot"] is True)
        all_ps = [
            call.kwargs["json"].get("parent_session")
            for call in api.call_args_list
        ]
        self.assertEqual(len(all_ps), 3)
        for ps in all_ps:
            self.assertIsNotNone(ps)
            self.assertRegex(ps, _TRUE_SLOT_PS_RE)
        self.assertEqual(len(set(all_ps)), 3)
        # task_slots maps each task_id to its slot name
        self.assertIn("task_slots", result)
        self.assertEqual(len(result["task_slots"]), 3)
        for tid, name in result["task_slots"].items():
            self.assertRegex(name, _TRUE_SLOT_NAME_RE)


class DispatchSlotBatchNamedTests(unittest.TestCase):
    """3.10 — batch with slot="shared" gives all tasks the same parent_session."""

    def test_batch_named_slot_shared(self) -> None:
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
                slot="shared",
            )

        self.assertNotIn("error", result)
        self.assertEqual(result["slot"], "shared")
        all_ps = [
            call.kwargs["json"].get("parent_session")
            for call in api.call_args_list
        ]
        self.assertEqual(len(all_ps), 2)
        self.assertEqual(all_ps[0], "dashboard:shared")
        self.assertEqual(all_ps[1], "dashboard:shared")


if __name__ == "__main__":
    unittest.main()
