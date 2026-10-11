"""Unit tests for TRN-225 — captain check-in spawn under host memory pressure.

Covers the three transport helpers added to ``transport.server``:

* ``_check_in_memory_pressure`` — pre-dispatch host-memory probe.
* ``_is_memory_pressure_refusal`` — classify a gateway 429/503 refusal.
* ``_record_memory_pressure_cycle`` — per-crew counter + edge-triggered
  Admiral escalation.

Patch targets follow the call-site principle: the helpers call ``_get_podman``,
``_get_host_memory_gb_cached``, ``_load_registry``, ``_save_registry``,
``_get_crew_schedules`` and ``_mail_admiral`` by name from ``server``'s own
namespace, so each is patched as ``server.X``.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tests.unit.helpers import FakeResponse, server  # noqa: F401


class CheckInMemoryPressureTests(unittest.TestCase):
    """`_check_in_memory_pressure`: below threshold → value, at/above → None,
    exception → None, None probe → None (fail open)."""

    def test_below_critical_returns_free_value(self) -> None:
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_host_memory_gb_cached", return_value=0.5),
            patch.object(server, "GA_RESOURCE_CRITICAL_GB", 1.0),
        ):
            self.assertEqual(server._check_in_memory_pressure(), 0.5)

    def test_at_threshold_returns_none(self) -> None:
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_host_memory_gb_cached", return_value=1.0),
            patch.object(server, "GA_RESOURCE_CRITICAL_GB", 1.0),
        ):
            self.assertIsNone(server._check_in_memory_pressure())

    def test_above_threshold_returns_none(self) -> None:
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_host_memory_gb_cached", return_value=4.0),
            patch.object(server, "GA_RESOURCE_CRITICAL_GB", 1.0),
        ):
            self.assertIsNone(server._check_in_memory_pressure())

    def test_probe_none_fails_open(self) -> None:
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_get_host_memory_gb_cached", return_value=None),
            patch.object(server, "GA_RESOURCE_CRITICAL_GB", 1.0),
        ):
            self.assertIsNone(server._check_in_memory_pressure())

    def test_probe_exception_fails_open(self) -> None:
        with (
            patch.object(server, "_get_podman", side_effect=RuntimeError("no socket")),
            patch.object(server, "GA_RESOURCE_CRITICAL_GB", 1.0),
        ):
            self.assertIsNone(server._check_in_memory_pressure())


class IsMemoryPressureRefusalTests(unittest.TestCase):
    """`_is_memory_pressure_refusal`: memory-pressure 429/503 → True; a
    503-still-spawning body and unrelated bodies → False."""

    def test_503_memory_pressure_true(self) -> None:
        resp = FakeResponse(503, content=b"spawn refused: host under memory pressure")
        self.assertTrue(server._is_memory_pressure_refusal(resp))

    def test_429_insufficient_memory_true(self) -> None:
        resp = FakeResponse(429, content=b"insufficient memory to start subagent")
        self.assertTrue(server._is_memory_pressure_refusal(resp))

    def test_503_still_spawning_false(self) -> None:
        resp = FakeResponse(503, content=b"crew still spawning, retry shortly")
        self.assertFalse(server._is_memory_pressure_refusal(resp))

    def test_memory_without_pressure_token_false(self) -> None:
        # "memory" alone (no "pressure"/"insufficient") must not match.
        resp = FakeResponse(503, content=b"memory module reloading")
        self.assertFalse(server._is_memory_pressure_refusal(resp))

    def test_unrelated_500_false(self) -> None:
        resp = FakeResponse(500, content=b"internal error under memory pressure")
        self.assertFalse(server._is_memory_pressure_refusal(resp))

    def test_200_false(self) -> None:
        resp = FakeResponse(200, content=b"{}")
        self.assertFalse(server._is_memory_pressure_refusal(resp))


class RecordMemoryPressureCycleTests(unittest.TestCase):
    """`_record_memory_pressure_cycle`: increment, missing-field-as-0, single
    edge-triggered mail at the boundary, no re-mail above the bound, reset on
    success (reset is exercised via the fire-path success branch separately —
    here we assert the counter arithmetic and mail edge-trigger)."""

    def _reg(self, skips=None):
        entry = {"type": "captain"}
        if skips is not None:
            entry["consecutive_memory_pressure_skips"] = skips
        return {"crews": {"demo": {"schedules": [entry]}}}

    def _run(self, reg):
        """Run _record_memory_pressure_cycle against ``reg`` with registry +
        mail patched; return (mail_mock, reg) so the caller can assert."""
        saved = {}

        def _save(r):
            saved["reg"] = r

        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry", side_effect=_save),
            patch.object(server, "_mail_admiral") as mail,
            patch.object(server, "GA_SPAWN_PRESSURE_ESCALATE_CYCLES", 3),
        ):
            server._record_memory_pressure_cycle("demo")
        return mail, reg

    def test_increments_from_zero_missing_field(self) -> None:
        reg = self._reg()  # field absent → treated as 0
        mail, reg = self._run(reg)
        n = reg["crews"]["demo"]["schedules"][0]["consecutive_memory_pressure_skips"]
        self.assertEqual(n, 1)
        mail.assert_not_called()

    def test_increments_existing_count(self) -> None:
        reg = self._reg(1)
        mail, reg = self._run(reg)
        n = reg["crews"]["demo"]["schedules"][0]["consecutive_memory_pressure_skips"]
        self.assertEqual(n, 2)
        mail.assert_not_called()

    def test_fires_mail_exactly_at_boundary(self) -> None:
        reg = self._reg(2)  # increments to 3 == bound
        mail, reg = self._run(reg)
        n = reg["crews"]["demo"]["schedules"][0]["consecutive_memory_pressure_skips"]
        self.assertEqual(n, 3)
        mail.assert_called_once()
        _, kwargs = mail.call_args
        # Admiral mail carries the crew id in the subject and body.
        self.assertIn("demo", kwargs.get("subject", "") + kwargs.get("body", ""))
        self.assertIn("memory pressure", kwargs.get("subject", "").lower())

    def test_no_remail_above_bound(self) -> None:
        reg = self._reg(3)  # increments to 4 > bound → no mail
        mail, reg = self._run(reg)
        n = reg["crews"]["demo"]["schedules"][0]["consecutive_memory_pressure_skips"]
        self.assertEqual(n, 4)
        mail.assert_not_called()

    def test_persists_via_save_registry(self) -> None:
        reg = self._reg(0)
        saved = {}

        def _save(r):
            saved["reg"] = r

        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry", side_effect=_save) as save,
            patch.object(server, "_mail_admiral"),
            patch.object(server, "GA_SPAWN_PRESSURE_ESCALATE_CYCLES", 3),
        ):
            server._record_memory_pressure_cycle("demo")
        save.assert_called_once()
        self.assertIs(saved["reg"], reg)


class MockGatewayMemoryPressureIntegrationTests(unittest.TestCase):
    """Integration (mock gateway): a /api/spawn memory-pressure 503 sets
    immediate_dispatch_error with the ``memory_pressure:`` marker, does NOT
    advance current_task_id, and is not re-dispatched in-cycle by the fire
    path. Drives the real ``server.captain(action='order', ...)`` fire path
    with only the gateway call and the memory probe mocked."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def _reg(self):
        return {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                   "enrolled_agents": ["raven"], "schedules": []}}}

    def test_memory_pressure_503_sets_marker_and_does_not_advance(self) -> None:
        import httpx2 as httpx

        reg = self._reg()
        resp = FakeResponse(503, content=b"spawn refused: host under memory pressure")
        err = httpx.HTTPStatusError("HTTP 503", request=Mock(), response=resp)
        recovery = Mock(side_effect=err)

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_append_captain_mail"),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
            # Probe fails open so the gateway refusal (D4) is what classifies.
            patch.object(server, "_check_in_memory_pressure", return_value=None),
            patch.object(server, "_crew_api_with_recovery", recovery),
            patch.object(server, "_record_memory_pressure_cycle") as record,
            patch.object(server, "GA_SPAWN_PRESSURE_ESCALATE_CYCLES", 3),
        ):
            result = server.captain("demo", "order", message="go", interval=120)

        # Marker present and typed as memory pressure.
        self.assertIn("immediate_dispatch_error", result)
        self.assertTrue(
            result["immediate_dispatch_error"].startswith("memory_pressure:"),
            result["immediate_dispatch_error"],
        )
        # current_task_id NOT advanced.
        self.assertIsNone(result.get("current_task_id"))
        # Spawn attempted exactly once — the fire path does not retry in-cycle.
        self.assertEqual(recovery.call_count, 1)
        # The cycle was counted (escalation bookkeeping).
        record.assert_called_once_with("demo")

    def test_pre_dispatch_probe_skips_without_calling_gateway(self) -> None:
        reg = self._reg()
        recovery = Mock()

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_append_captain_mail"),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
            # Probe reports pressure → skip BEFORE /api/spawn.
            patch.object(server, "_check_in_memory_pressure", return_value=0.5),
            patch.object(server, "_crew_api_with_recovery", recovery),
            patch.object(server, "_record_memory_pressure_cycle") as record,
        ):
            result = server.captain("demo", "order", message="go", interval=120)

        self.assertTrue(
            result["immediate_dispatch_error"].startswith("memory_pressure:"),
            result["immediate_dispatch_error"],
        )
        self.assertIsNone(result.get("current_task_id"))
        recovery.assert_not_called()  # gateway never contacted
        record.assert_called_once_with("demo")


if __name__ == "__main__":
    unittest.main()
