"""Unit tests for ``transport.crew`` — the Crew dataclass (TRN-240 task 2.1)."""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from tests.unit.helpers import crew_mod  # noqa: F401

Crew = crew_mod.Crew


class CrewRoundTripTests(unittest.TestCase):
    """to_dict / from_dict round-trip must preserve the crew exactly."""

    def _full_crew(self) -> "Crew":
        return Crew(
            crew_id="gs-demo",
            container="gs-gs-demo",
            volume="gs-vol-gs-demo",
            home_volume="gs-home-gs-demo",
            port=5476,
            cookie="cook",
            internal_cookie="intcook",
            status="running",
            composition="spec-ops",
            acp_backend="claude",
            created_at="2026-01-01T00:00:00+00:00",
            last_used=1234.5,
            warm_until=0.0,  # in-memory only; round-trip resets it to 0.0
            enrolled_agents=["raven", "ghost"],
            admiral_secret_id="sid",
            policy_version="pv1",
            policy_signing_key_id="pskid",
            crew_image_version="0.7.1",
            schedules=[{"job_id": "j1"}],
            batches=[{"batch_id": "b1", "task_ids": ["t1"]}],
        )

    def test_round_trip_full(self) -> None:
        crew = self._full_crew()
        restored = Crew.from_dict(crew.crew_id, crew.to_dict())
        self.assertEqual(restored, crew)

    def test_round_trip_minimal(self) -> None:
        """A minimal crew (defaults) round-trips too."""
        crew = Crew(
            crew_id="gs-min",
            container="gs-gs-min",
            volume="v",
            home_volume="h",
        )
        restored = Crew.from_dict(crew.crew_id, crew.to_dict())
        self.assertEqual(restored, crew)

    def test_to_dict_omits_warm_until(self) -> None:
        crew = self._full_crew()
        crew.warm_until = time.monotonic() + 1000
        self.assertNotIn("warm_until", crew.to_dict())

    def test_to_dict_omits_empty_optionals(self) -> None:
        """internal_cookie / policy_* / schedules / batches are omitted when empty."""
        crew = Crew(crew_id="c", container="gs-c", volume="v", home_volume="h")
        d = crew.to_dict()
        self.assertNotIn("internal_cookie", d)
        self.assertNotIn("policy_version", d)
        self.assertNotIn("policy_signing_key_id", d)
        self.assertNotIn("schedules", d)
        self.assertNotIn("batches", d)

    def test_to_dict_matches_finish_crew_setup_shape(self) -> None:
        """The always-present keys match the crew_entry dict from _finish_crew_setup."""
        crew = Crew(
            crew_id="c",
            container="gs-c",
            volume="gs-vol-c",
            home_volume="gs-home-c",
            cookie="ck",
            status="running",
            composition="spec-ops",
            created_at="2026-01-01T00:00:00+00:00",
            last_used=1.0,
            admiral_secret_id="aid",
            crew_image_version="0.7.1",
            acp_backend="kiro",
            enrolled_agents=["raven"],
        )
        d = crew.to_dict()
        self.assertEqual(
            set(d.keys()),
            {
                "container", "volume", "home_volume", "port", "cookie", "status",
                "composition", "created_at", "last_used", "admiral_secret_id",
                "crew_image_version", "acp_backend", "enrolled_agents",
            },
        )

    def test_from_dict_ignores_unknown_keys(self) -> None:
        crew = Crew.from_dict("c", {"container": "gs-c", "volume": "v", "home_volume": "h", "bogus": 1})
        self.assertEqual(crew.container, "gs-c")

    def test_from_dict_defaults_for_missing(self) -> None:
        crew = Crew.from_dict("c", {})
        self.assertEqual(crew.port, 5476)
        self.assertEqual(crew.status, "stopped")
        self.assertEqual(crew.acp_backend, "kiro")
        self.assertEqual(crew.crew_image_version, "unknown")
        self.assertEqual(crew.warm_until, 0.0)


class GatewayUrlTests(unittest.TestCase):
    def test_gateway_url(self) -> None:
        crew = Crew(crew_id="c", container="gs-demo", volume="v", home_volume="h")
        self.assertEqual(crew.gateway_url(), "http://gs-demo:5476")

    def test_cookie_header(self) -> None:
        crew = Crew(crew_id="c", container="gs-demo", volume="v", home_volume="h", cookie="abc")
        self.assertEqual(crew.cookie_header(), "mc_token_5476=abc")


class IsIdleTests(unittest.TestCase):
    def test_is_idle_true_when_old(self) -> None:
        crew = Crew(crew_id="c", container="gs", volume="v", home_volume="h")
        with patch.object(crew_mod.time, "time", return_value=1000.0):
            crew.last_used = 1000.0 - 500
            self.assertTrue(crew.is_idle(300))

    def test_is_idle_false_when_recent(self) -> None:
        crew = Crew(crew_id="c", container="gs", volume="v", home_volume="h")
        with patch.object(crew_mod.time, "time", return_value=1000.0):
            crew.last_used = 1000.0 - 100
            self.assertFalse(crew.is_idle(300))

    def test_is_idle_false_when_never_used(self) -> None:
        crew = Crew(crew_id="c", container="gs", volume="v", home_volume="h")
        crew.last_used = 0.0
        self.assertFalse(crew.is_idle(300))


class IsWarmTests(unittest.TestCase):
    def test_is_warm_true_when_marker_fresh(self) -> None:
        crew = Crew(crew_id="c", container="gs", volume="v", home_volume="h")
        with patch.object(crew_mod.time, "monotonic", return_value=100.0):
            crew.warm_until = 200.0
            self.assertTrue(crew.is_warm())

    def test_is_warm_false_when_marker_stale(self) -> None:
        crew = Crew(crew_id="c", container="gs", volume="v", home_volume="h")
        with patch.object(crew_mod.time, "monotonic", return_value=300.0):
            crew.warm_until = 200.0
            self.assertFalse(crew.is_warm())

    def test_is_warm_false_by_default(self) -> None:
        crew = Crew(crew_id="c", container="gs", volume="v", home_volume="h")
        self.assertFalse(crew.is_warm())


if __name__ == "__main__":
    unittest.main()
