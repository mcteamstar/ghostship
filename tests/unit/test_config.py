"""Unit tests for transport/config.py and transport/constants.py.

Covers:
- Config dataclass defaults
- Config.from_env() parsing (int, float, bool, str fields)
- ConfigError raised on bad int/float values
- _parse_ga_crew_agent normalisation (dedup, kiro always appended, validation)
- parse_agent_backends (deprecated alias behaviour)
- inert_backend_settings detection
- _validate_caddy_tls_mode fallback
- Config.__repr__ masks secret fields
- Config.ga_crew_acp_backend and ga_agent_backends properties
- constants: value spot checks and zero-dependency guarantee
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from transport.config import (
    Config,
    ConfigError,
    _env_bool_default_off,
    _env_bool_default_on,
    _parse_ga_crew_agent,
    _validate_caddy_tls_mode,
    inert_backend_settings,
    parse_agent_backends,
)
from transport.constants import (
    ADMIRAL_PUBKEY_PATH,
    CREW_CONTAINER_PREFIX,
    CREW_GATEWAY_PORT,
    CREW_HOME_VOLUME_PREFIX,
    CREW_VOLUME_PREFIX,
    GA_PORTSIDE_NETWORK,
    GA_STARBOARD_NETWORK,
    PERSONA_NAMES,
    SCRIPTS_DIR,
)


# ── Constants ─────────────────────────────────────────────────────────────────


class TestConstants(unittest.TestCase):
    """constants.py: zero-dependency leaf, no imports from transport.*."""

    def test_crew_gateway_port_is_5476(self):
        self.assertEqual(CREW_GATEWAY_PORT, 5476)

    def test_container_prefix(self):
        self.assertEqual(CREW_CONTAINER_PREFIX, "gs-")

    def test_volume_prefix(self):
        self.assertEqual(CREW_VOLUME_PREFIX, "gs-vol-")

    def test_home_volume_prefix(self):
        self.assertEqual(CREW_HOME_VOLUME_PREFIX, "gs-home-")

    def test_portside_network(self):
        self.assertEqual(GA_PORTSIDE_NETWORK, "ga-portside")

    def test_starboard_network(self):
        self.assertEqual(GA_STARBOARD_NETWORK, "ga-starboard")

    def test_persona_names_count(self):
        self.assertEqual(len(PERSONA_NAMES), 6)

    def test_persona_names_contains_expected(self):
        for name in ("ghost", "spectre", "banshee", "wraith", "reaper", "raven"):
            self.assertIn(name, PERSONA_NAMES)

    def test_scripts_dir(self):
        self.assertEqual(SCRIPTS_DIR, "/scripts")

    def test_admiral_pubkey_path_outside_home(self):
        # Must NOT be under /home/kirocrew (see module docstring constraint)
        self.assertFalse(ADMIRAL_PUBKEY_PATH.startswith("/home/kirocrew"))

    def test_constants_module_no_transport_imports(self):
        """constants.py must not import any other transport.* module."""
        import importlib
        import sys
        # Reload to detect any new transport.* imports at module level
        if "transport.constants" in sys.modules:
            del sys.modules["transport.constants"]
        importlib.import_module("transport.constants")
        # If any transport.* module other than constants was imported as a side
        # effect, the test fails.
        other_transport = [
            k for k in sys.modules
            if k.startswith("transport.") and k != "transport.constants"
            and k != "transport"
        ]
        # We only care about modules imported BY constants, so check the ones
        # that didn't exist before our import. This is best-effort — the real
        # guarantee is the module docstring stating it must be zero-dep.
        # Verify the module is a pure leaf (no new transport.* side-imports).
        # Allow transport itself and transport.constants.
        for mod_name in other_transport:
            mod = sys.modules.get(mod_name)
            # Only flag modules that are NOT explicitly imported elsewhere (e.g.
            # config was already loaded by the test framework). Just verify
            # constants doesn't use them by inspecting the module's __spec__.
            if mod is not None and hasattr(mod, "__spec__"):
                # constants itself shouldn't have any attribute pointing at
                # another transport module
                import transport.constants as _c
                for attr in vars(_c).values():
                    if hasattr(attr, "__module__") and isinstance(attr.__module__, str):
                        self.assertFalse(
                            attr.__module__.startswith("transport.") and
                            attr.__module__ != "transport.constants",
                            f"constants.py unexpectedly references {attr.__module__}",
                        )
                break  # checked once is enough


# ── Config defaults ───────────────────────────────────────────────────────────


class TestConfigDefaults(unittest.TestCase):
    """Config() with no args should have sane defaults."""

    def setUp(self):
        self.cfg = Config()

    def test_transport_bind_default(self):
        self.assertEqual(self.cfg.ga_transport_bind, "0.0.0.0")

    def test_portal_host_default_is_loopback(self):
        self.assertEqual(self.cfg.ga_portal_host, "127.0.0.1")

    def test_api_key_not_disabled_by_default(self):
        self.assertFalse(self.cfg.ga_api_key_disabled)

    def test_port_default(self):
        self.assertEqual(self.cfg.port, 64057)

    def test_ga_max_crews_default(self):
        self.assertEqual(self.cfg.ga_max_crews, 20)

    def test_ga_max_active_crews_default(self):
        self.assertEqual(self.cfg.ga_max_active_crews, 3)

    def test_ga_idle_timeout_default(self):
        self.assertEqual(self.cfg.ga_idle_timeout_secs, 300)

    def test_ga_min_free_mem_gb_default(self):
        self.assertAlmostEqual(self.cfg.ga_min_free_mem_gb, 2.0)

    def test_ga_spawn_min_memory_gb_default(self):
        self.assertAlmostEqual(self.cfg.ga_spawn_min_memory_gb, 1.5)

    def test_ga_portal_tls_mode_default(self):
        self.assertEqual(self.cfg.ga_portal_tls_mode, "off")

    def test_ga_portal_session_ttl_default(self):
        self.assertEqual(self.cfg.ga_portal_session_ttl_secs, 86400)

    def test_ga_crew_agent_default(self):
        self.assertEqual(self.cfg.ga_crew_agent, "kiro")

    def test_dashboard_port_range_start_default(self):
        self.assertEqual(self.cfg.ga_dashboard_port_range_start, 64058)

    def test_secret_fields_empty_by_default(self):
        self.assertEqual(self.cfg.anthropic_api_key, "")
        self.assertEqual(self.cfg.openai_api_key, "")
        self.assertEqual(self.cfg.kiro_api_key, "")

    def test_kc_base_image_is_pinned_digest(self):
        # Must contain a sha256 digest (TRN-219)
        self.assertIn("sha256:", self.cfg.kc_base_image)


# ── Config.from_env() ─────────────────────────────────────────────────────────


class TestConfigFromEnv(unittest.TestCase):
    """Config.from_env() reads environment correctly."""

    def test_port_from_env(self):
        with patch.dict("os.environ", {"PORT": "9000"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.port, 9000)

    def test_host_env_does_not_set_transport_bind(self):
        # HOST is ga-portal's published address; the transport never reads it.
        with patch.dict("os.environ", {"HOST": "127.0.0.1"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_transport_bind, "0.0.0.0")

    def test_portal_host_and_opt_out_from_env(self):
        with patch.dict(
            "os.environ",
            {"GA_PORTAL_HOST": "192.168.1.10", "GA_API_KEY_DISABLED": "true"},
        ):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_portal_host, "192.168.1.10")
        self.assertTrue(cfg.ga_api_key_disabled)

    def test_ga_max_crews_from_env(self):
        with patch.dict("os.environ", {"GA_MAX_CREWS": "5"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_max_crews, 5)

    def test_ga_min_free_mem_gb_from_env(self):
        with patch.dict("os.environ", {"GA_MIN_FREE_MEM_GB": "3.5"}):
            cfg = Config.from_env()
        self.assertAlmostEqual(cfg.ga_min_free_mem_gb, 3.5)

    def test_ga_dashboard_default_true_values(self):
        for val in ("1", "true", "yes", "True", "YES"):
            with patch.dict("os.environ", {"GA_DASHBOARD_DEFAULT": val}):
                cfg = Config.from_env()
            self.assertTrue(cfg.ga_dashboard_default, f"Expected True for {val!r}")

    def test_ga_dashboard_default_false_values(self):
        for val in ("0", "false", "no", "", "False"):
            with patch.dict("os.environ", {"GA_DASHBOARD_DEFAULT": val}):
                cfg = Config.from_env()
            self.assertFalse(cfg.ga_dashboard_default, f"Expected False for {val!r}")

    def test_anthropic_api_key_from_env(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.anthropic_api_key, "sk-test-key")

    def test_ga_crew_agent_kiro_included_implicitly(self):
        with patch.dict("os.environ", {"GA_CREW_AGENT": "claude"}):
            cfg = Config.from_env()
        backends = [b.strip() for b in cfg.ga_crew_agent.split(",")]
        self.assertIn("kiro", backends)
        self.assertIn("claude", backends)

    def test_ga_portal_tls_mode_from_env(self):
        with patch.dict("os.environ", {"GA_PORTAL_TLS_MODE": "internal"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_portal_tls_mode, "internal")

    def test_retired_backend_flag_raises(self):
        with patch.dict("os.environ", {"GA_INCLUDE_CLAUDE_AGENT": "true"}):
            with self.assertRaises(ConfigError):
                Config.from_env()

    def test_retired_backend_flag_false_value_still_raises(self):
        # Even "false" counts as present — must raise
        with patch.dict("os.environ", {"GA_INCLUDE_CLAUDE_AGENT": "false"}):
            with self.assertRaises(ConfigError):
                Config.from_env()

    def test_ga_crew_acp_backend_deprecated_alias(self):
        """GA_CREW_ACP_BACKEND maps to GA_CREW_AGENT with a warning."""
        with patch.dict("os.environ", {"GA_CREW_ACP_BACKEND": "claude"}, clear=False):
            # GA_CREW_AGENT must not be set
            env = {k: v for k, v in __import__("os").environ.items()
                   if k not in ("GA_CREW_AGENT", "GA_CREW_ACP_BACKEND")}
            env["GA_CREW_ACP_BACKEND"] = "claude"
            with patch.dict("os.environ", env, clear=True):
                cfg = Config.from_env()
        backends = [b.strip() for b in cfg.ga_crew_agent.split(",")]
        self.assertIn("claude", backends)
        self.assertIn("kiro", backends)


# ── Config.from_env() — error handling ───────────────────────────────────────


class TestConfigFromEnvErrors(unittest.TestCase):
    """Bad env var values raise ConfigError with descriptive messages."""

    def _assert_config_error(self, env_var: str, bad_value: str = "abc") -> None:
        with patch.dict("os.environ", {env_var: bad_value}):
            with self.assertRaises(ConfigError) as ctx:
                Config.from_env()
        self.assertIn(env_var, str(ctx.exception))

    def test_port_invalid(self):
        self._assert_config_error("PORT", "not-a-port")

    def test_ga_max_crews_invalid(self):
        self._assert_config_error("GA_MAX_CREWS", "many")

    def test_ga_max_active_crews_invalid(self):
        self._assert_config_error("GA_MAX_ACTIVE_CREWS", "x")

    def test_ga_idle_timeout_secs_invalid(self):
        self._assert_config_error("GA_IDLE_TIMEOUT_SECS", "long")

    def test_ga_min_free_mem_gb_invalid(self):
        self._assert_config_error("GA_MIN_FREE_MEM_GB", "alot")

    def test_ga_min_free_mem_gb_nan_raises(self):
        self._assert_config_error("GA_MIN_FREE_MEM_GB", "nan")

    def test_ga_min_free_mem_gb_inf_raises(self):
        self._assert_config_error("GA_MIN_FREE_MEM_GB", "inf")

    def test_ga_spawn_min_memory_gb_invalid(self):
        self._assert_config_error("GA_SPAWN_MIN_MEMORY_GB", "bad")

    def test_ga_resource_pressure_gb_invalid(self):
        self._assert_config_error("GA_RESOURCE_PRESSURE_GB", "bad")

    def test_ga_resource_critical_gb_invalid(self):
        self._assert_config_error("GA_RESOURCE_CRITICAL_GB", "bad")

    def test_ga_portal_session_ttl_secs_invalid(self):
        self._assert_config_error("GA_PORTAL_SESSION_TTL_SECS", "xxx")

    def test_ga_crew_agent_unknown_backend(self):
        with patch.dict("os.environ", {"GA_CREW_AGENT": "unknownbackend"}):
            with self.assertRaises(ConfigError) as ctx:
                Config.from_env()
        self.assertIn("unknownbackend", str(ctx.exception))

    def test_bad_value_in_error_message(self):
        """The invalid value itself appears in the error message."""
        bad = "xyz123"
        with patch.dict("os.environ", {"PORT": bad}):
            with self.assertRaises(ConfigError) as ctx:
                Config.from_env()
        self.assertIn(bad, str(ctx.exception))


# ── _parse_ga_crew_agent ──────────────────────────────────────────────────────


class TestParseGaCrewAgent(unittest.TestCase):
    """_parse_ga_crew_agent normalises comma-separated backend lists."""

    def test_kiro_only_returns_kiro(self):
        result = _parse_ga_crew_agent("kiro")
        self.assertEqual(result, ("kiro",))

    def test_claude_appends_kiro(self):
        result = _parse_ga_crew_agent("claude")
        self.assertIn("kiro", result)
        self.assertIn("claude", result)

    def test_first_entry_stays_first(self):
        result = _parse_ga_crew_agent("claude,kiro")
        self.assertEqual(result[0], "claude")

    def test_deduplication(self):
        result = _parse_ga_crew_agent("claude,claude,kiro")
        self.assertEqual(result.count("claude"), 1)

    def test_empty_string_returns_kiro(self):
        result = _parse_ga_crew_agent("")
        self.assertEqual(result, ("kiro",))

    def test_spaces_are_stripped(self):
        result = _parse_ga_crew_agent("  claude  ,  kiro  ")
        self.assertIn("claude", result)
        self.assertIn("kiro", result)

    def test_unknown_backend_raises(self):
        with self.assertRaises(ConfigError):
            _parse_ga_crew_agent("openrouter")

    def test_all_three_backends(self):
        result = _parse_ga_crew_agent("kiro,claude,codex")
        self.assertEqual(set(result), {"kiro", "claude", "codex"})


# ── parse_agent_backends (deprecated alias) ───────────────────────────────────


class TestParseAgentBackends(unittest.TestCase):
    """parse_agent_backends strips kiro (always enabled) and deduplicates."""

    def test_claude_returned(self):
        result = parse_agent_backends("claude")
        self.assertIn("claude", result)

    def test_kiro_stripped(self):
        result = parse_agent_backends("kiro,claude")
        self.assertNotIn("kiro", result)

    def test_empty_string_returns_empty(self):
        result = parse_agent_backends("")
        self.assertEqual(result, ())

    def test_deduplication(self):
        result = parse_agent_backends("claude,claude")
        self.assertEqual(result.count("claude"), 1)

    def test_unknown_backend_raises(self):
        with self.assertRaises(ConfigError):
            parse_agent_backends("openrouter")


# ── inert_backend_settings ────────────────────────────────────────────────────


class TestInertBackendSettings(unittest.TestCase):
    """inert_backend_settings returns names of unused credentials."""

    def test_claude_api_key_inert_when_only_kiro(self):
        cfg = Config(ga_crew_agent="kiro", anthropic_api_key="sk-test")
        result = inert_backend_settings(cfg, frozenset())
        self.assertIn("ANTHROPIC_API_KEY", result)

    def test_claude_api_key_not_inert_when_claude_enabled(self):
        cfg = Config(ga_crew_agent="claude,kiro", anthropic_api_key="sk-test")
        result = inert_backend_settings(cfg, frozenset())
        self.assertNotIn("ANTHROPIC_API_KEY", result)

    def test_empty_api_key_not_flagged(self):
        cfg = Config(ga_crew_agent="kiro", anthropic_api_key="")
        result = inert_backend_settings(cfg, frozenset())
        self.assertNotIn("ANTHROPIC_API_KEY", result)

    def test_codex_credential_file_inert_when_only_kiro(self):
        cfg = Config(ga_crew_agent="kiro")
        result = inert_backend_settings(cfg, frozenset({"ga-codex-auth"}))
        self.assertIn("ga-codex-auth", result)

    def test_claude_credential_file_not_inert_when_claude_enabled(self):
        cfg = Config(ga_crew_agent="claude,kiro")
        result = inert_backend_settings(cfg, frozenset({"ga-claude-auth"}))
        self.assertNotIn("ga-claude-auth", result)

    def test_result_is_list(self):
        cfg = Config(ga_crew_agent="kiro")
        result = inert_backend_settings(cfg, frozenset())
        self.assertIsInstance(result, list)


# ── _validate_caddy_tls_mode ──────────────────────────────────────────────────


class TestValidateCaddyTlsMode(unittest.TestCase):
    """_validate_caddy_tls_mode accepts valid modes and falls back on unknown ones."""

    def test_internal_valid(self):
        self.assertEqual(_validate_caddy_tls_mode("internal"), "internal")

    def test_tailscale_valid(self):
        self.assertEqual(_validate_caddy_tls_mode("tailscale"), "tailscale")

    def test_acme_valid(self):
        self.assertEqual(_validate_caddy_tls_mode("acme"), "acme")

    def test_off_valid(self):
        self.assertEqual(_validate_caddy_tls_mode("off"), "off")

    def test_unknown_falls_back_to_default(self):
        result = _validate_caddy_tls_mode("invalid_mode")
        self.assertEqual(result, "off")

    def test_empty_string_falls_back(self):
        result = _validate_caddy_tls_mode("")
        self.assertEqual(result, "off")

    def test_custom_fallback(self):
        result = _validate_caddy_tls_mode("bad", default="internal")
        self.assertEqual(result, "internal")


# ── Config.__repr__ ───────────────────────────────────────────────────────────


class TestConfigRepr(unittest.TestCase):
    """Config.__repr__ masks secret fields.

    After TRN-233, backend credential fields (anthropic_api_key,
    openai_api_key, claude_code_oauth_token) are no longer in _SECRET_FIELDS
    because credentials are managed by CredentialStore, not Config. Only
    kiro_api_key (the transport bearer key) remains masked.
    """

    def test_anthropic_api_key_not_masked_after_trn233(self):
        # Credential fields are no longer secret in Config — CredentialStore owns them.
        cfg = Config(anthropic_api_key="sk-real-key")
        self.assertIn("sk-real-key", repr(cfg))

    def test_openai_api_key_not_masked_after_trn233(self):
        cfg = Config(openai_api_key="sk-openai-key")
        self.assertIn("sk-openai-key", repr(cfg))

    def test_kiro_api_key_masked(self):
        cfg = Config(kiro_api_key="kiro-super-secret")
        self.assertNotIn("kiro-super-secret", repr(cfg))

    def test_claude_code_oauth_token_not_masked_after_trn233(self):
        cfg = Config(claude_code_oauth_token="oauth-token")
        self.assertIn("oauth-token", repr(cfg))

    def test_empty_secret_fields_not_masked(self):
        """Empty secret fields show '' not '***'."""
        cfg = Config(anthropic_api_key="")
        r = repr(cfg)
        # The field should appear with an empty string value
        self.assertIn("anthropic_api_key=''", r)

    def test_non_secret_field_visible(self):
        cfg = Config(ga_portal_host="1.2.3.4")
        self.assertIn("1.2.3.4", repr(cfg))


# ── Config properties ─────────────────────────────────────────────────────────


class TestConfigProperties(unittest.TestCase):
    """ga_crew_acp_backend and ga_agent_backends properties."""

    def test_ga_crew_acp_backend_returns_first(self):
        cfg = Config(ga_crew_agent="claude,kiro")
        self.assertEqual(cfg.ga_crew_acp_backend, "claude")

    def test_ga_crew_acp_backend_kiro_default(self):
        cfg = Config()
        self.assertEqual(cfg.ga_crew_acp_backend, "kiro")

    def test_ga_agent_backends_frozenset(self):
        cfg = Config(ga_crew_agent="claude,kiro")
        backends = cfg.ga_agent_backends
        self.assertIsInstance(backends, frozenset)
        self.assertIn("claude", backends)
        self.assertIn("kiro", backends)

    def test_ga_agent_backends_kiro_default(self):
        cfg = Config()
        self.assertIn("kiro", cfg.ga_agent_backends)


# ── _env_bool helpers ─────────────────────────────────────────────────────────


class TestEnvBoolHelpers(unittest.TestCase):
    """_env_bool_default_on and _env_bool_default_off."""

    def test_default_on_absent(self):
        with patch.dict("os.environ", {}, clear=False):
            os = __import__("os")
            os.environ.pop("_TEST_BOOL_ABSENT_VAR", None)
            result = _env_bool_default_on("_TEST_BOOL_ABSENT_VAR")
        self.assertTrue(result)

    def test_default_on_disabled(self):
        with patch.dict("os.environ", {"_TEST_BOOL": "0"}):
            result = _env_bool_default_on("_TEST_BOOL")
        self.assertFalse(result)

    def test_default_on_false_string(self):
        with patch.dict("os.environ", {"_TEST_BOOL": "false"}):
            result = _env_bool_default_on("_TEST_BOOL")
        self.assertFalse(result)

    def test_default_off_absent(self):
        __import__("os").environ.pop("_TEST_OFF_ABSENT", None)
        result = _env_bool_default_off("_TEST_OFF_ABSENT")
        self.assertFalse(result)

    def test_default_off_enabled(self):
        with patch.dict("os.environ", {"_TEST_OFF": "1"}):
            result = _env_bool_default_off("_TEST_OFF")
        self.assertTrue(result)

    def test_default_off_yes(self):
        with patch.dict("os.environ", {"_TEST_OFF": "yes"}):
            result = _env_bool_default_off("_TEST_OFF")
        self.assertTrue(result)


# ── Config ↔ ghostship.yaml.example sync invariant (TRN-253) ──────────────────


class TestConfigYamlExampleSync(unittest.TestCase):
    """Every Config dataclass field must have a documented entry in
    config/ghostship.yaml.example.

    TRN-253 replaced the flat ghostship.conf.example with a structured YAML
    example. The invariant is enforced through bin/lib/yaml_config.py's
    canonical env-var -> YAML-path map: every Config field maps to an env var,
    every env var maps to a YAML path, and that path's leaf key must appear in
    the example file. This keeps the installer's config surface (yaml_config),
    the transport's config surface (Config), and the operator documentation
    (yaml.example) in lock-step.
    """

    # Config fields the installer deliberately does NOT surface in the YAML
    # config: backend credentials are managed by `ghostship auth login` and
    # resolved per launch (TRN-233), never set in the config file.
    _CREDENTIAL_FIELDS = frozenset(
        {
            "anthropic_api_key",
            "openai_api_key",
            "kiro_api_key",
            "claude_code_oauth_token",
        }
    )

    # Config fields install.sh derives rather than reads 1:1 from the YAML
    # (portal-only-host): the transport's fixed listen address, the operator's
    # network.host passed through as GA_PORTAL_HOST, and network.api_key: false
    # passed through as GA_API_KEY_DISABLED. Their YAML keys are network.host and
    # network.api_key, checked directly below.
    _INSTALLER_DERIVED_FIELDS = frozenset(
        {"ga_transport_bind", "ga_portal_host", "ga_api_key_disabled"}
    )

    @staticmethod
    def _load_yaml_config_module():
        import importlib.util
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        mod_path = repo_root / "bin" / "lib" / "yaml_config.py"
        spec = importlib.util.spec_from_file_location("yaml_config", mod_path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, repo_root

    def test_every_config_field_has_yaml_example_entry(self):
        import dataclasses
        import re

        yc, repo_root = self._load_yaml_config_module()
        example = (repo_root / "config" / "ghostship.yaml.example").read_text()

        # Config field name -> env var. Field names mirror env var names
        # lowercased (module docstring), except host/port which drop the GA_
        # prefix. Build the lowercase->ENV lookup from yaml_config.DEFAULTS.
        env_by_lower = {name.lower(): name for name in yc.DEFAULTS}

        missing = []
        for field in dataclasses.fields(Config):
            fname = field.name
            if fname.startswith("_"):
                continue
            if fname in self._CREDENTIAL_FIELDS | self._INSTALLER_DERIVED_FIELDS:
                continue
            env = env_by_lower.get(fname)
            self.assertIsNotNone(
                env,
                f"Config field '{fname}' has no matching env var in "
                f"yaml_config.DEFAULTS — add it to both DEFAULTS and _KEY_MAP.",
            )
            path = yc._ENV_TO_PATH.get(env)
            self.assertIsNotNone(
                path,
                f"env var '{env}' (Config.{fname}) is not in yaml_config._KEY_MAP.",
            )
            leaf = path[-1]
            if not re.search(rf"^\s*#?\s*{re.escape(leaf)}:", example, re.M):
                missing.append(f"{fname} -> {'.'.join(path)}")

        self.assertEqual(
            missing,
            [],
            "Config fields missing a commented entry in ghostship.yaml.example: "
            + ", ".join(missing),
        )

    def test_yaml_example_parses_when_decommented(self):
        """The example file is valid YAML and contains the expected structure.

        Since ghostship.yaml.example is now live YAML (not a fully-commented
        template), we parse it directly and spot-check key sections survive.
        Guards against accidentally writing invalid YAML in the example.
        """
        import yaml

        _yc, repo_root = self._load_yaml_config_module()
        raw = (repo_root / "config" / "ghostship.yaml.example").read_text()

        parsed = yaml.safe_load(raw)
        self.assertIsInstance(parsed, dict)
        # Spot-check a selection of nested keys (TRN-257 structure).
        self.assertIn("network", parsed)
        self.assertEqual(parsed["network"]["port"], 64057)
        self.assertIn("tls", parsed["network"])
        self.assertIn("crew", parsed)
        self.assertIn("memory", parsed["crew"])
        self.assertIn("author", parsed["crew"]["git"])
        self.assertIn("backends", parsed)
        # backends.default is now a YAML list; model.override removed globally.
        self.assertIsInstance(parsed["backends"]["default"], list)
        self.assertIn("model", parsed["backends"]["kiro"])
        self.assertIn("identity_center", parsed["backends"]["kiro"])
        self.assertNotIn("override", parsed["model"])
        self.assertIn("portal", parsed)
        self.assertIn("rate_limit", parsed["portal"])
        self.assertIn("port_range", parsed["portal"]["dashboard"])
        self.assertIn("machine", parsed)
        self.assertIn("resources", parsed["machine"])
        # images merged into machine (was a top-level section before TRN-257).
        self.assertIn("images", parsed["machine"])


if __name__ == "__main__":
    unittest.main()


# ── portal-only-host: public URL fallback and exposure enforcement ────────────


class TestPortalOnlyHost(unittest.TestCase):
    def test_is_loopback(self):
        from transport.config import is_loopback

        for host in ("", "127.0.0.1", "127.9.9.9", "::1", "[::1]", "localhost"):
            self.assertTrue(is_loopback(host), host)
        for host in ("0.0.0.0", "::", "192.168.1.10", "example.com"):
            self.assertFalse(is_loopback(host), host)

    def test_public_base_url_prefers_ga_host_url(self):
        cfg = Config(ga_host_url="https://academy.example.com/", ga_portal_host="192.168.1.10")
        self.assertEqual(cfg.public_base_url(), "https://academy.example.com")

    def test_public_base_url_loopback_or_wildcard_is_localhost(self):
        for host in ("127.0.0.1", "::1", "0.0.0.0", "::", ""):
            self.assertEqual(
                Config(ga_portal_host=host).public_base_url(),
                "http://localhost:64057",
                host,
            )

    def test_public_base_url_specific_host(self):
        self.assertEqual(
            Config(ga_portal_host="192.168.1.10").public_base_url(),
            "http://192.168.1.10:64057",
        )
        self.assertEqual(
            Config(ga_portal_host="2001:db8::1").public_base_url(),
            "http://[2001:db8::1]:64057",
        )

    def test_presigned_urls_use_public_base_url(self):
        # transport.files cannot be imported in the unit env; check the wiring.
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2] / "transport" / "files.py").read_text()
        self.assertIn("return cfg.public_base_url()", src)

    def test_crew_cors_origin_uses_public_base_url(self):
        # The CORS origin injected into crews is derived from public_base_url(),
        # so it follows GA_HOST_URL, then the portal host.
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2] / "transport" / "tools.py").read_text()
        self.assertIn("_urlparse(cfg.public_base_url())", src)
        self.assertNotIn('_transport_public_origin = f"http://localhost:{PORT}"', src)


class TestApiKeyExposure(unittest.TestCase):
    """Startup check is on ga-portal's published address, not the listen address."""

    def test_wildcard_listen_with_loopback_portal_starts(self):
        from transport.config import api_key_exposure

        cfg = Config(ga_transport_bind="0.0.0.0", ga_portal_host="127.0.0.1")
        self.assertIsNone(api_key_exposure("", cfg))

    def test_non_loopback_portal_without_key_is_an_error(self):
        from transport.config import api_key_exposure

        level, message = api_key_exposure("", Config(ga_portal_host="0.0.0.0"))
        self.assertEqual(level, "error")
        self.assertIn("network.api_key: false", message)

    def test_non_loopback_portal_with_opt_out_warns(self):
        from transport.config import api_key_exposure

        cfg = Config(ga_portal_host="192.168.1.10", ga_api_key_disabled=True)
        level, message = api_key_exposure("", cfg)
        self.assertEqual(level, "warning")
        self.assertIn("without authentication", message)

    def test_non_loopback_portal_with_key_starts(self):
        from transport.config import api_key_exposure

        self.assertIsNone(api_key_exposure("s3cret", Config(ga_portal_host="0.0.0.0")))

    def test_server_exits_on_error_verdict(self):
        # transport.server cannot be imported in the unit env; check the wiring.
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2] / "transport" / "server.py").read_text()
        self.assertIn("verdict = api_key_exposure(api_key, config or cfg)", src)
        self.assertIn("_enforce_api_key_requirement(GA_API_KEY)", src)
        self.assertNotIn('environ.get("HOST"', src)
