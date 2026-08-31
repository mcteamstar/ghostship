"""Unit tests for ``transport.registry`` — crew registry + schedule persistence.

TRN-85 migration target for classes whose function-under-test is defined in
``registry.py`` (``_load_registry``, ``_save_registry``, ``_get_crew``,
``_touch_crew``, ``_get_crew_schedules``, ``_upsert_crew_schedule``,
``_remove_crew_schedule``, ``_advance_next_fire_at``). Patch via
``transport.registry`` — the call-site principle: these run in registry.py's
namespace even though ``server`` re-exports them.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from tests.unit.helpers import registry, server  # noqa: F401


class AdvanceNextFireAtTests(unittest.TestCase):
    """Tests for _advance_next_fire_at (D4 in TRN-39 design.md)."""

    def test_interval_branch(self) -> None:
        """interval_secs=300 advances next_fire_at by ~300 seconds."""
        now = time.time()
        job = {"job_id": "j1", "interval_secs": 300, "cron_expr": None, "one_shot": False}
        registry._advance_next_fire_at(job)
        self.assertAlmostEqual(job["next_fire_at"], now + 300, delta=2.0)

    def test_cron_branch(self) -> None:
        """cron_expr branch matches croniter at a simulated HH:59 time."""
        from datetime import datetime, timezone
        from croniter import croniter

        job = {"job_id": "j2", "interval_secs": None, "cron_expr": "0 * * * *", "one_shot": False}
        now = datetime(2026, 8, 24, 12, 59, 30, tzinfo=timezone.utc).timestamp()
        with patch.object(registry.time, "time", return_value=now):
            registry._advance_next_fire_at(job)

        expected = croniter("0 * * * *", now).get_next(float)
        self.assertEqual(job["next_fire_at"], expected)

    def test_one_shot_branch(self) -> None:
        """one_shot=True sets next_fire_at to _NEVER_FIRE_AT sentinel."""
        job = {"job_id": "j3", "interval_secs": 60, "cron_expr": None, "one_shot": True}
        registry._advance_next_fire_at(job)
        self.assertEqual(job["next_fire_at"], registry._NEVER_FIRE_AT)

    def test_malformed_cron_falls_back_to_60s(self) -> None:
        """Malformed cron expression falls back to +60s (nit 5.3)."""
        now = time.time()
        job = {"job_id": "j4", "interval_secs": None, "cron_expr": "not-a-cron", "one_shot": False}
        with self.assertLogs("transport", level="WARNING") as log_ctx:
            registry._advance_next_fire_at(job)
        self.assertAlmostEqual(job["next_fire_at"], now + 60, delta=2.0)
        self.assertTrue(
            any("croniter failed" in msg and "not-a-cron" in msg for msg in log_ctx.output),
            "Expected warning mentioning 'croniter failed' and the expression",
        )

    def test_unknown_schedule_type_sets_never_fire_at(self) -> None:
        """No interval_secs, no cron_expr, no one_shot → _NEVER_FIRE_AT (nit 5.3)."""
        job = {"job_id": "j5", "interval_secs": None, "cron_expr": None, "one_shot": False}
        registry._advance_next_fire_at(job)
        self.assertEqual(job["next_fire_at"], registry._NEVER_FIRE_AT)


if __name__ == "__main__":
    unittest.main()
