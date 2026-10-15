"""Unit tests for Config.from_env() error handling and conf.example sync.

Covers:
- ConfigError raised with clear message on invalid int/float env vars
- Each numeric env var individually
- Valid values still parse correctly
- Default (no env var) still works
- Every Config field has a commented entry in ghostship.conf.example (merged
  from test_config_sync.py)
"""
from __future__ import annotations

import dataclasses
import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from transport.config import Config, ConfigError, parse_agent_backends  # noqa: E402


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

    def test_ga_dashboard_port_range_start_invalid(self):
        self._assert_config_error("GA_DASHBOARD_PORT_RANGE_START", "high")

    def test_ga_dashboard_port_range_size_invalid(self):
        self._assert_config_error("GA_DASHBOARD_PORT_RANGE_SIZE", "big")

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

    def test_ga_dashboard_port_range_size_configured(self):
        """GA_DASHBOARD_PORT_RANGE_SIZE env var overrides the default."""
        with patch.dict("os.environ", {"GA_DASHBOARD_PORT_RANGE_SIZE": "50"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_dashboard_port_range_size, 50)

    def test_ga_dashboard_port_range_size_default(self):
        """GA_DASHBOARD_PORT_RANGE_SIZE defaults to 64 when unset."""
        env = {k: v for k, v in __import__("os").environ.items()
               if k != "GA_DASHBOARD_PORT_RANGE_SIZE"}
        with patch.dict("os.environ", env, clear=True):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_dashboard_port_range_size, 64)

    def test_defaults_when_unset(self):
        """Config.from_env() with no relevant env vars uses field defaults."""
        # Clear all numeric vars to ensure defaults apply
        vars_to_clear = [
            "PORT", "GA_MAX_CREWS", "GA_MAX_ACTIVE_CREWS", "GA_IDLE_TIMEOUT_SECS",
            "GA_SUBAGENT_TIMEOUT_SECS",
            "GA_MIN_FREE_MEM_GB", "GA_SPAWN_MIN_MEMORY_GB",
            "GA_RESOURCE_PRESSURE_GB", "GA_RESOURCE_CRITICAL_GB",
            "GA_DASHBOARD_PORT_RANGE_START",
            "GA_DASHBOARD_PORT_RANGE_SIZE",
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

    # TRN-219: bumped from :0.8.0 to the immutable digest of 0.9.0-insider.4.
    _EXPECTED_DEFAULT = (
        "ghcr.io/kirodotdev/kirocrew@sha256:"
        "f4f4801898572175a1988e61a8696769821528860edceaf5ca253f8123a77009"
    )

    def test_default_value(self):
        """kc_base_image defaults to the pinned 0.9.0-insider.4 digest (TRN-219)."""
        env = {k: v for k, v in __import__("os").environ.items()
               if k != "KC_BASE_IMAGE"}
        with patch.dict("os.environ", env, clear=True):
            cfg = Config.from_env()
        self.assertEqual(cfg.kc_base_image, self._EXPECTED_DEFAULT)

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


class TestConfigPrewarmDefaults(unittest.TestCase):
    """Prewarm TTL is hardcoded to 300 in lifecycle.py (TRN-213).

    GA_PREWARM_ENABLED and GA_PREWARM_TTL_SECS are no longer Config fields —
    they were hardcoded in TRN-213. These tests verify the module constants.
    """

    def test_ga_prewarm_ttl_module_constant(self) -> None:
        """_PREWARM_TTL_SECS is hardcoded to 300 in lifecycle.py."""
        import transport.lifecycle as _lifecycle
        self.assertEqual(_lifecycle._PREWARM_TTL_SECS, 300)

    def test_ga_prewarm_enabled_module_constant(self) -> None:
        """GA_PREWARM_ENABLED is True (gate removed) in lifecycle.py."""
        import transport.lifecycle as _lifecycle
        self.assertIs(_lifecycle.GA_PREWARM_ENABLED, True)


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


class TestConfigConfExampleSync(unittest.TestCase):
    """Every Config field must have a commented entry in ghostship.conf.example.

    Merged from test_config_sync.py (TRN-244 consolidation).
    """

    def test_every_config_field_present_in_conf_example(self):
        repo_root = Path(__file__).resolve().parents[2]
        conf_example = repo_root / "config" / "ghostship.conf.example"
        text = conf_example.read_text()
        # An entry looks like a commented assignment: "# GA_MAX_CREWS=..." —
        # match the env var name at the start of a commented line, allowing
        # for leading whitespace, so we don't get fooled by prose mentions.
        present = set(
            re.findall(r"(?m)^\s*#\s*([A-Z][A-Z0-9_]*)\s*=", text)
        )
        missing = []
        for f in dataclasses.fields(Config):
            env_name = f.name.upper()
            if env_name not in present:
                missing.append(env_name)
        self.assertEqual(
            missing,
            [],
            "Config fields missing a commented entry in "
            f"{conf_example.name}: {missing}. Add each as a commented-out line "
            "(e.g. '# GA_FOO=default').",
        )


if __name__ == "__main__":
    unittest.main()


# ── Config.__repr__ secret masking (merged from test_trn235_config_repr_masking.py) ──
# TRN-235 (SEC-3): Config.__repr__ must never emit live credentials.

_SECRET_FIELDS = (
    "kiro_api_key",
    "anthropic_api_key",
    "openai_api_key",
    "claude_code_oauth_token",
)


class TestConfigReprMasking(unittest.TestCase):
    """Config.__repr__ replaces non-empty secret fields with '***'."""

    def test_nonempty_secrets_masked(self) -> None:
        cfg = Config(
            kiro_api_key="kiro-SECRET-1",
            anthropic_api_key="anthropic-SECRET-2",
            openai_api_key="openai-SECRET-3",
            claude_code_oauth_token="oauth-SECRET-4",
        )
        r = repr(cfg)
        for value in (
            "kiro-SECRET-1",
            "anthropic-SECRET-2",
            "openai-SECRET-3",
            "oauth-SECRET-4",
        ):
            self.assertNotIn(value, r)
        self.assertIn("***", r)
        for field in _SECRET_FIELDS:
            self.assertIn(f"{field}='***'", r)

    def test_empty_secret_fields_not_masked(self) -> None:
        r = repr(Config())
        for field in _SECRET_FIELDS:
            self.assertIn(f"{field}=''", r)
        self.assertNotIn("***", r)

    def test_nonsecret_fields_rendered(self) -> None:
        cfg = Config(host="127.0.0.1", port=12345, kiro_api_key="x")
        r = repr(cfg)
        self.assertIn("host='127.0.0.1'", r)
        self.assertIn("port=12345", r)
        self.assertNotIn("kiro_api_key='x'", r)
        self.assertIn("kiro_api_key='***'", r)

    def test_str_also_masks(self) -> None:
        cfg = Config(anthropic_api_key="live-token")
        self.assertNotIn("live-token", str(cfg))

    def test_repr_marker_not_a_dataclass_field(self) -> None:
        names = {f.name for f in dataclasses.fields(Config())}
        self.assertNotIn("_SECRET_FIELDS", names)


# ── Finite-float and backend-list line-break guards ───────────────────────────
# Merged from test_review_quick_fixes.py (TRN-244 consolidation).

_AGENT_BACKENDS_SH = (
    Path(__file__).resolve().parents[2] / "scripts" / "lib" / "agent_backends.sh"
)


class TestFiniteFloats(unittest.TestCase):
    """NaN and Inf are rejected by Config.from_env() for float fields."""

    def test_nan_and_inf_are_rejected(self):
        for value in ("nan", "NaN", "inf", "-inf"):
            with self.subTest(value=value):
                with patch.dict("os.environ", {"GA_MIN_FREE_MEM_GB": value}, clear=True):
                    with self.assertRaises(ConfigError):
                        Config.from_env()

    def test_normal_float_accepted(self):
        with patch.dict("os.environ", {"GA_MIN_FREE_MEM_GB": "1.5"}, clear=True):
            self.assertEqual(Config.from_env().ga_min_free_mem_gb, 1.5)


class TestBackendListLineBreak(unittest.TestCase):
    """Both the Python and shell backend parsers reject a line break in the list."""

    def test_both_parsers_reject_a_line_break(self):
        raw = "claude,codex\nbogus"
        with self.assertRaises(ConfigError):
            parse_agent_backends(raw)
        if not _AGENT_BACKENDS_SH.exists():
            return  # skip shell half when scripts/ is absent
        result = subprocess.run(
            ["bash", "-c", f'source "{_AGENT_BACKENDS_SH}"; agent_backends_normalise "$1"',
             "bash", raw],
            capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("single line", result.stderr)
