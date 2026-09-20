"""Unit tests for Config.from_env() error handling.

Covers:
- ConfigError raised with clear message on invalid int/float env vars
- Each numeric env var individually
- Valid values still parse correctly
- Default (no env var) still works
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from transport.config import Config, ConfigError  # noqa: E402


class TestConfigEnvIntErrors(unittest.TestCase):
    """Each integer env var raises ConfigError on invalid input."""

    def _assert_config_error(self, env_var: str, bad_value: str = "abc") -> None:
        with patch.dict("os.environ", {env_var: bad_value}):
            with self.assertRaises(ConfigError) as ctx:
                Config.from_env()
        self.assertIn(env_var, str(ctx.exception))
        self.assertIn(bad_value, str(ctx.exception))

    def test_port_invalid(self):
        self._assert_config_error("PORT", "not-a-port")

    def test_ga_max_crews_invalid(self):
        self._assert_config_error("GA_MAX_CREWS", "abc")

    def test_ga_max_active_crews_invalid(self):
        self._assert_config_error("GA_MAX_ACTIVE_CREWS", "xyz")

    def test_ga_idle_timeout_secs_invalid(self):
        self._assert_config_error("GA_IDLE_TIMEOUT_SECS", "forever")

    def test_ga_subagent_timeout_secs_invalid(self):
        self._assert_config_error("GA_SUBAGENT_TIMEOUT_SECS", "inf")

    def test_ga_subagent_max_turns_invalid(self):
        self._assert_config_error("GA_SUBAGENT_MAX_TURNS", "lots")

    def test_ga_prewarm_ttl_secs_invalid(self):
        self._assert_config_error("GA_PREWARM_TTL_SECS", "fast")

    def test_ga_dashboard_port_range_start_invalid(self):
        self._assert_config_error("GA_DASHBOARD_PORT_RANGE_START", "high")

    def test_ga_portal_session_ttl_secs_invalid(self):
        self._assert_config_error("GA_PORTAL_SESSION_TTL_SECS", "never")


class TestConfigEnvFloatErrors(unittest.TestCase):
    """Each float env var raises ConfigError on invalid input."""

    def _assert_config_error(self, env_var: str, bad_value: str = "abc") -> None:
        with patch.dict("os.environ", {env_var: bad_value}):
            with self.assertRaises(ConfigError) as ctx:
                Config.from_env()
        self.assertIn(env_var, str(ctx.exception))
        self.assertIn(bad_value, str(ctx.exception))

    def test_ga_min_free_mem_gb_invalid(self):
        self._assert_config_error("GA_MIN_FREE_MEM_GB", "lots")

    def test_ga_spawn_min_memory_gb_invalid(self):
        self._assert_config_error("GA_SPAWN_MIN_MEMORY_GB", "some")

    def test_ga_resource_pressure_gb_invalid(self):
        self._assert_config_error("GA_RESOURCE_PRESSURE_GB", "pressure")

    def test_ga_resource_critical_gb_invalid(self):
        self._assert_config_error("GA_RESOURCE_CRITICAL_GB", "critical")


class TestConfigEnvValidValues(unittest.TestCase):
    """Valid env var values still parse correctly."""

    def test_valid_int_vars(self):
        env = {
            "GA_MAX_CREWS": "5",
            "GA_MAX_ACTIVE_CREWS": "2",
            "GA_IDLE_TIMEOUT_SECS": "600",
        }
        with patch.dict("os.environ", env):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_max_crews, 5)
        self.assertEqual(cfg.ga_max_active_crews, 2)
        self.assertEqual(cfg.ga_idle_timeout_secs, 600)

    def test_valid_float_vars(self):
        env = {
            "GA_MIN_FREE_MEM_GB": "3.5",
            "GA_RESOURCE_PRESSURE_GB": "1.0",
        }
        with patch.dict("os.environ", env):
            cfg = Config.from_env()
        self.assertAlmostEqual(cfg.ga_min_free_mem_gb, 3.5)
        self.assertAlmostEqual(cfg.ga_resource_pressure_gb, 1.0)

    def test_defaults_when_unset(self):
        """Config.from_env() with no relevant env vars uses field defaults."""
        # Clear all numeric vars to ensure defaults apply
        vars_to_clear = [
            "PORT", "GA_MAX_CREWS", "GA_MAX_ACTIVE_CREWS", "GA_IDLE_TIMEOUT_SECS",
            "GA_SUBAGENT_TIMEOUT_SECS", "GA_SUBAGENT_MAX_TURNS",
            "GA_MIN_FREE_MEM_GB", "GA_SPAWN_MIN_MEMORY_GB",
            "GA_RESOURCE_PRESSURE_GB", "GA_RESOURCE_CRITICAL_GB",
            "GA_PREWARM_TTL_SECS", "GA_DASHBOARD_PORT_RANGE_START",
            "GA_PORTAL_SESSION_TTL_SECS",
        ]
        clean_env = {k: v for k, v in __import__("os").environ.items()
                     if k not in vars_to_clear}
        with patch.dict("os.environ", clean_env, clear=True):
            cfg = Config.from_env()
        self.assertEqual(cfg.port, 64057)
        self.assertEqual(cfg.ga_max_crews, 20)
        self.assertEqual(cfg.ga_idle_timeout_secs, 300)
        self.assertAlmostEqual(cfg.ga_min_free_mem_gb, 2.0)

    def test_config_error_is_value_error_subclass(self):
        """ConfigError must be a ValueError so existing bare except ValueError still catches it."""
        with patch.dict("os.environ", {"GA_MAX_CREWS": "bad"}):
            with self.assertRaises(ValueError):
                Config.from_env()


class TestConfigKcBaseImage(unittest.TestCase):
    """Config.from_env() respects KC_BASE_IMAGE env var."""

    def test_default_value(self):
        """kc_base_image defaults to the pinned upstream image."""
        env = {k: v for k, v in __import__("os").environ.items()
               if k != "KC_BASE_IMAGE"}
        with patch.dict("os.environ", env, clear=True):
            cfg = Config.from_env()
        self.assertEqual(cfg.kc_base_image, "ghcr.io/kirodotdev/kirocrew:0.6.0")

    def test_custom_value_respected(self):
        """KC_BASE_IMAGE env var overrides the default."""
        with patch.dict("os.environ", {"KC_BASE_IMAGE": "custom:latest"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.kc_base_image, "custom:latest")

    def test_empty_string_allowed(self):
        """An empty KC_BASE_IMAGE is passed through as-is."""
        with patch.dict("os.environ", {"KC_BASE_IMAGE": ""}):
            cfg = Config.from_env()
        self.assertEqual(cfg.kc_base_image, "")


class TestConfigTLSDefault(unittest.TestCase):
    """GA_PORTAL_TLS_MODE default is 'off'."""

    def test_default_is_off(self):
        with patch.dict("os.environ", {}, clear=False):
            # Remove TLS mode var if present
            env = {k: v for k, v in __import__("os").environ.items()
                   if k != "GA_PORTAL_TLS_MODE"}
            with patch.dict("os.environ", env, clear=True):
                cfg = Config.from_env()
        self.assertEqual(cfg.ga_portal_tls_mode, "off")

    def test_explicit_off(self):
        with patch.dict("os.environ", {"GA_PORTAL_TLS_MODE": "off"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_portal_tls_mode, "off")

    def test_valid_modes_accepted(self):
        for mode in ("internal", "tailscale", "acme", "off"):
            with patch.dict("os.environ", {"GA_PORTAL_TLS_MODE": mode}):
                cfg = Config.from_env()
            self.assertEqual(cfg.ga_portal_tls_mode, mode)

    def test_invalid_mode_falls_back_to_off(self):
        with patch.dict("os.environ", {"GA_PORTAL_TLS_MODE": "bogus"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_portal_tls_mode, "off")


if __name__ == "__main__":
    unittest.main()
