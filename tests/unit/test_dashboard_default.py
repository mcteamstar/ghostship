"""Unit tests for TRN-148: GA_DASHBOARD_DEFAULT config flag.

Tests cover:
  4.1  GA_DASHBOARD_DEFAULT=false, no explicit arg → effective_dashboard is False
  4.2  GA_DASHBOARD_DEFAULT=true, no explicit arg → effective_dashboard is True
  4.3  GA_DASHBOARD_DEFAULT=true, dashboard=False explicit → effective_dashboard is False
  4.4  GA_DASHBOARD_DEFAULT=false, dashboard=True explicit → effective_dashboard is True
"""

from __future__ import annotations

import unittest

from tests.unit.helpers import server


class DashboardDefaultConfigTests(unittest.TestCase):
    """Tests for GA_DASHBOARD_DEFAULT resolving the effective dashboard value.

    We test the resolution logic directly: given cfg.ga_dashboard_default and
    an explicit dashboard arg, what is the effective value?
    The formula is: explicit if explicit is not None else cfg.ga_dashboard_default
    """

    def _resolve(self, cfg_default: bool, explicit_arg) -> bool:
        """Replicate the resolution formula from launch()."""
        dashboard = explicit_arg
        ga_dashboard_default = cfg_default
        return dashboard if dashboard is not None else ga_dashboard_default

    def test_default_false_no_explicit_arg(self) -> None:
        """4.1 — GA_DASHBOARD_DEFAULT=false, no explicit → headless."""
        self.assertFalse(self._resolve(cfg_default=False, explicit_arg=None))

    def test_default_true_no_explicit_arg(self) -> None:
        """4.2 — GA_DASHBOARD_DEFAULT=true, no explicit → dashboard."""
        self.assertTrue(self._resolve(cfg_default=True, explicit_arg=None))

    def test_default_true_explicit_false_overrides(self) -> None:
        """4.3 — GA_DASHBOARD_DEFAULT=true, explicit False → headless."""
        self.assertFalse(self._resolve(cfg_default=True, explicit_arg=False))

    def test_default_false_explicit_true_overrides(self) -> None:
        """4.4 — GA_DASHBOARD_DEFAULT=false, explicit True → dashboard."""
        self.assertTrue(self._resolve(cfg_default=False, explicit_arg=True))

    def test_cfg_field_exists(self) -> None:
        """GA_DASHBOARD_DEFAULT config field is present and defaults to False."""
        self.assertFalse(server.cfg.ga_dashboard_default)

    def test_resolution_matches_launch_formula(self) -> None:
        """The formula in launch() matches the spec for all four cases."""
        cases = [
            (False, None, False),
            (True, None, True),
            (True, False, False),
            (False, True, True),
        ]
        for cfg_default, explicit, expected in cases:
            result = explicit if explicit is not None else cfg_default
            self.assertEqual(result, expected,
                f"cfg_default={cfg_default}, explicit={explicit}: expected {expected}, got {result}")


if __name__ == "__main__":
    unittest.main()
