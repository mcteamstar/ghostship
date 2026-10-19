"""Unit tests for bin/lib/yaml_config.py (TRN-253).

Covers:
- deep_merge: scalar override, nested partial override, list replacement
- resolve_config: three-layer merge, XDG missing fall-through, --config skip
- flatten_to_env: every mapped key, boolean/None normalisation
- collect_unknown_paths: unknown leaf and unknown section detection
- load_yaml: missing file -> {}, empty file -> {}, syntax error -> ValueError
- migrate_conf: known key mapping, non-default-only, deprecated aliases,
  dropped credential keys, UNKNOWN comment emission
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

# Load the standalone module directly (it lives under bin/lib, not a package).
_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "bin" / "lib" / "yaml_config.py"
)
_spec = importlib.util.spec_from_file_location("yaml_config", _MODULE_PATH)
assert _spec and _spec.loader
yaml_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(yaml_config)


class TestDeepMerge(unittest.TestCase):
    def test_scalar_override(self):
        base = {"a": 1, "b": 2}
        over = {"b": 3}
        self.assertEqual(yaml_config.deep_merge(base, over), {"a": 1, "b": 3})

    def test_nested_partial_override(self):
        base = {"crew": {"max_active": 3, "idle_timeout_secs": 600}}
        over = {"crew": {"max_active": 6}}
        merged = yaml_config.deep_merge(base, over)
        self.assertEqual(merged["crew"]["max_active"], 6)
        self.assertEqual(merged["crew"]["idle_timeout_secs"], 600)

    def test_list_replaced_entirely(self):
        base = {"backends": {"enabled": ["kiro"]}}
        over = {"backends": {"enabled": ["kiro", "claude"]}}
        merged = yaml_config.deep_merge(base, over)
        self.assertEqual(merged["backends"]["enabled"], ["kiro", "claude"])

    def test_inputs_not_mutated(self):
        base = {"a": {"x": 1}}
        over = {"a": {"y": 2}}
        yaml_config.deep_merge(base, over)
        self.assertEqual(base, {"a": {"x": 1}})
        self.assertEqual(over, {"a": {"y": 2}})


class TestLoadYaml(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        self.assertEqual(yaml_config.load_yaml("/nonexistent/path.yaml"), {})

    def test_empty_path_returns_empty(self):
        self.assertEqual(yaml_config.load_yaml(""), {})

    def test_empty_file_returns_empty(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write("")
            path = fh.name
        try:
            self.assertEqual(yaml_config.load_yaml(path), {})
        finally:
            os.unlink(path)

    def test_valid_file_loads(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write("crew:\n  max_active: 6\n")
            path = fh.name
        try:
            self.assertEqual(yaml_config.load_yaml(path), {"crew": {"max_active": 6}})
        finally:
            os.unlink(path)

    def test_syntax_error_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write("crew:\n  max_active: : :\n   bad indent\n")
            path = fh.name
        try:
            with self.assertRaises(ValueError):
                yaml_config.load_yaml(path)
        finally:
            os.unlink(path)

    def test_non_mapping_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write("- just\n- a\n- list\n")
            path = fh.name
        try:
            with self.assertRaises(ValueError):
                yaml_config.load_yaml(path)
        finally:
            os.unlink(path)


class TestResolveConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, name: str, content: str) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_defaults_only_when_no_files(self):
        merged = yaml_config.resolve_config(
            repo_path=os.path.join(self.tmp, "nope.yaml"),
            xdg_path=os.path.join(self.tmp, "nope2.yaml"),
            explicit_path=None,
        )
        self.assertEqual(merged["network"]["port"], "64057")
        self.assertEqual(merged["crew"]["max_active"], "3")

    def test_repo_overrides_default(self):
        repo = self._write("repo.yaml", "crew:\n  max_active: 6\n")
        merged = yaml_config.resolve_config(repo, os.path.join(self.tmp, "x.yaml"), None)
        self.assertEqual(merged["crew"]["max_active"], 6)

    def test_xdg_overrides_repo(self):
        repo = self._write("repo.yaml", "crew:\n  max_active: 3\n")
        xdg = self._write("xdg.yaml", "crew:\n  max_active: 6\n")
        merged = yaml_config.resolve_config(repo, xdg, None)
        self.assertEqual(merged["crew"]["max_active"], 6)

    def test_xdg_partial_preserves_repo_keys(self):
        repo = self._write(
            "repo.yaml", "crew:\n  max_active: 3\n  idle_timeout_secs: 600\n"
        )
        xdg = self._write("xdg.yaml", "crew:\n  max_active: 6\n")
        merged = yaml_config.resolve_config(repo, xdg, None)
        self.assertEqual(merged["crew"]["max_active"], 6)
        self.assertEqual(merged["crew"]["idle_timeout_secs"], 600)

    def test_xdg_missing_falls_through_to_repo(self):
        repo = self._write("repo.yaml", "crew:\n  max_active: 5\n")
        merged = yaml_config.resolve_config(
            repo, os.path.join(self.tmp, "no-xdg.yaml"), None
        )
        self.assertEqual(merged["crew"]["max_active"], 5)

    def test_config_flag_skips_repo_and_xdg(self):
        repo = self._write("repo.yaml", "network:\n  port: 1111\n")
        xdg = self._write("xdg.yaml", "network:\n  port: 2222\n")
        explicit = self._write("explicit.yaml", "network:\n  port: 9000\n")
        merged = yaml_config.resolve_config(repo, xdg, explicit)
        self.assertEqual(merged["network"]["port"], 9000)
        # crew defaults still present (merged over built-in defaults)
        self.assertEqual(merged["crew"]["max_active"], "3")


class TestFlattenToEnv(unittest.TestCase):
    def test_all_defaults_map(self):
        merged = yaml_config._defaults_tree()
        env = yaml_config.flatten_to_env(merged)
        # Every DEFAULTS key appears
        for key in yaml_config.DEFAULTS:
            self.assertIn(key, env, f"{key} missing from flattened env")

    def test_port_mapping(self):
        env = yaml_config.flatten_to_env({"network": {"port": 9000}})
        self.assertEqual(env["PORT"], "9000")

    def test_nested_backend_mapping(self):
        env = yaml_config.flatten_to_env(
            {"backends": {"kiro": {"identity_center": {"url": "https://idp"}}}}
        )
        self.assertEqual(env["KIRO_IDENTITY_PROVIDER"], "https://idp")

    def test_bool_normalisation(self):
        env = yaml_config.flatten_to_env({"machine": {"dedicated": False}})
        self.assertEqual(env["GA_DEDICATED_MACHINE"], "false")
        env = yaml_config.flatten_to_env({"machine": {"dedicated": True}})
        self.assertEqual(env["GA_DEDICATED_MACHINE"], "true")

    def test_none_becomes_empty(self):
        env = yaml_config.flatten_to_env({"network": {"host_url": None}})
        self.assertEqual(env["GA_HOST_URL"], "")

    def test_unmapped_leaf_ignored(self):
        env = yaml_config.flatten_to_env({"network": {"bogus": "x"}})
        self.assertNotIn("bogus", env)


class TestCollectUnknownPaths(unittest.TestCase):
    def test_known_tree_has_no_unknowns(self):
        tree = yaml_config._defaults_tree()
        self.assertEqual(yaml_config.collect_unknown_paths(tree), [])

    def test_unknown_leaf_detected(self):
        unknown = yaml_config.collect_unknown_paths({"network": {"bogus_key": 1}})
        self.assertIn("network.bogus_key", unknown)

    def test_unknown_section_detected(self):
        unknown = yaml_config.collect_unknown_paths({"totally_made_up": {"x": 1}})
        self.assertIn("totally_made_up", unknown)

    def test_known_leaf_not_flagged(self):
        unknown = yaml_config.collect_unknown_paths({"network": {"port": 64057}})
        self.assertEqual(unknown, [])


class TestMigrateConf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conf = os.path.join(self.tmp, "ghostship.conf")
        self.out = os.path.join(self.tmp, "ghostship.yaml")

    def _write_conf(self, content: str) -> None:
        with open(self.conf, "w", encoding="utf-8") as fh:
            fh.write(content)

    def _read_out(self) -> str:
        with open(self.out, encoding="utf-8") as fh:
            return fh.read()

    def test_known_key_mapped_to_yaml_path(self):
        self._write_conf("PORT=9000\n")
        unknown = yaml_config.migrate_conf(self.conf, self.out)
        self.assertEqual(unknown, [])
        loaded = yaml_config.load_yaml(self.out)
        self.assertEqual(loaded["network"]["port"], 9000)

    def test_default_value_omitted(self):
        self._write_conf("PORT=64057\n")  # equals the default
        yaml_config.migrate_conf(self.conf, self.out)
        loaded = yaml_config.load_yaml(self.out)
        # port equals default -> should not be written
        self.assertNotIn("network", loaded)

    def test_quoted_values_handled(self):
        self._write_conf('KIRO_IDENTITY_PROVIDER="https://idp.example.com"\n')
        yaml_config.migrate_conf(self.conf, self.out)
        loaded = yaml_config.load_yaml(self.out)
        self.assertEqual(
            loaded["backends"]["kiro"]["identity_center"]["url"],
            "https://idp.example.com",
        )

    def test_deprecated_alias_mapped(self):
        self._write_conf("GA_PORTAL_PORT=9000\n")
        yaml_config.migrate_conf(self.conf, self.out)
        loaded = yaml_config.load_yaml(self.out)
        self.assertEqual(loaded["network"]["port"], 9000)

    def test_dropped_credential_key_not_unknown(self):
        self._write_conf("ANTHROPIC_API_KEY=sk-secret\n")
        unknown = yaml_config.migrate_conf(self.conf, self.out)
        self.assertEqual(unknown, [])
        self.assertNotIn("sk-secret", self._read_out())

    def test_unknown_key_emits_comment_and_returned(self):
        self._write_conf("SOME_RANDOM_KEY=value123\n")
        unknown = yaml_config.migrate_conf(self.conf, self.out)
        self.assertIn("SOME_RANDOM_KEY", unknown)
        self.assertIn("# UNKNOWN: SOME_RANDOM_KEY=value123", self._read_out())

    def test_comments_and_blank_lines_skipped(self):
        self._write_conf("# a comment\n\nGA_MAX_ACTIVE_CREWS=6\n")
        unknown = yaml_config.migrate_conf(self.conf, self.out)
        self.assertEqual(unknown, [])
        loaded = yaml_config.load_yaml(self.out)
        self.assertEqual(loaded["crew"]["max_active"], 6)

    def test_export_prefix_handled(self):
        self._write_conf("export GA_MAX_CREWS=50\n")
        yaml_config.migrate_conf(self.conf, self.out)
        loaded = yaml_config.load_yaml(self.out)
        self.assertEqual(loaded["crew"]["max_crews"], 50)

    def test_boolean_coercion(self):
        self._write_conf("GA_DEDICATED_MACHINE=false\n")
        yaml_config.migrate_conf(self.conf, self.out)
        loaded = yaml_config.load_yaml(self.out)
        self.assertIs(loaded["machine"]["dedicated"], False)


class TestComposeVarCoverage(unittest.TestCase):
    """Regression guard: vars that were previously missing from the compose.yml
    template (TRN-253 review finding).

    These vars were in yaml_config._KEY_MAP but not wired through the compose.yml
    environment block, so operator overrides were silently dropped at runtime.
    Verify they are in DEFAULTS and _KEY_MAP so the installer resolves and
    injects them correctly.
    """

    def test_spawn_pressure_escalate_cycles_in_defaults(self):
        self.assertIn("GA_SPAWN_PRESSURE_ESCALATE_CYCLES", yaml_config.DEFAULTS)

    def test_spawn_pressure_escalate_cycles_in_key_map(self):
        self.assertIn(
            "GA_SPAWN_PRESSURE_ESCALATE_CYCLES",
            yaml_config._ENV_TO_PATH,
            "GA_SPAWN_PRESSURE_ESCALATE_CYCLES must have a YAML path in _KEY_MAP",
        )

    def test_rate_limit_dashboard_auth_in_defaults(self):
        self.assertIn("GA_RATE_LIMIT_DASHBOARD_AUTH", yaml_config.DEFAULTS)

    def test_rate_limit_dashboard_auth_in_key_map(self):
        self.assertIn(
            "GA_RATE_LIMIT_DASHBOARD_AUTH",
            yaml_config._ENV_TO_PATH,
            "GA_RATE_LIMIT_DASHBOARD_AUTH must have a YAML path in _KEY_MAP",
        )

    def test_kc_image_in_defaults(self):
        self.assertIn("KC_IMAGE", yaml_config.DEFAULTS)

    def test_kc_image_in_key_map(self):
        self.assertIn(
            "KC_IMAGE",
            yaml_config._ENV_TO_PATH,
            "KC_IMAGE must have a YAML path in _KEY_MAP",
        )

    def test_kc_image_default_value(self):
        self.assertEqual(yaml_config.DEFAULTS["KC_IMAGE"], "localhost/spec-ops:latest")

    def test_flatten_includes_spawn_pressure(self):
        """flatten_to_env must emit GA_SPAWN_PRESSURE_ESCALATE_CYCLES."""
        merged = yaml_config.resolve_config("", "", None)
        env = yaml_config.flatten_to_env(merged)
        self.assertIn("GA_SPAWN_PRESSURE_ESCALATE_CYCLES", env)
        self.assertEqual(env["GA_SPAWN_PRESSURE_ESCALATE_CYCLES"], "3")

    def test_flatten_includes_dashboard_auth(self):
        """flatten_to_env must emit GA_RATE_LIMIT_DASHBOARD_AUTH."""
        merged = yaml_config.resolve_config("", "", None)
        env = yaml_config.flatten_to_env(merged)
        self.assertIn("GA_RATE_LIMIT_DASHBOARD_AUTH", env)
        self.assertEqual(env["GA_RATE_LIMIT_DASHBOARD_AUTH"], "600:60")

    def test_flatten_includes_kc_image(self):
        """flatten_to_env must emit KC_IMAGE."""
        merged = yaml_config.resolve_config("", "", None)
        env = yaml_config.flatten_to_env(merged)
        self.assertIn("KC_IMAGE", env)
        self.assertEqual(env["KC_IMAGE"], "localhost/spec-ops:latest")

    def test_subagent_max_turns_not_in_defaults(self):
        """GA_SUBAGENT_MAX_TURNS is hardcoded in the transport (lifecycle.py and
        server.py use _SUBAGENT_MAX_TURNS=200 as an internal constant). It must
        NOT appear in yaml_config.DEFAULTS or _KEY_MAP — setting it in
        ghostship.yaml would have no effect and would mislead operators.
        """
        self.assertNotIn("GA_SUBAGENT_MAX_TURNS", yaml_config.DEFAULTS)
        self.assertNotIn("GA_SUBAGENT_MAX_TURNS", yaml_config._ENV_TO_PATH)


class TestDeprecatedYamlPaths(unittest.TestCase):
    """TRN-257: old flat YAML paths rewrite to the new sub-section paths with a
    warning; the removed model.override is warned about and discarded."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, name: str, content: str) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def _resolve_env(self, yaml_text: str):
        """Resolve a single explicit-config layer, capturing stderr warnings."""
        import contextlib
        import io

        cfg = self._write("c.yaml", yaml_text)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            merged = yaml_config.resolve_config("", "", cfg)
            env = yaml_config.flatten_to_env(merged)
        return env, buf.getvalue()

    def test_git_author_name_deprecated_path(self):
        env, warnings = self._resolve_env("crew:\n  git_author_name: Bot\n")
        self.assertEqual(env["GA_GIT_AUTHOR_NAME"], "Bot")
        self.assertIn("crew.git_author_name", warnings)
        self.assertIn("crew.git.author.name", warnings)

    def test_tls_certfile_deprecated_path(self):
        env, warnings = self._resolve_env("network:\n  tls_certfile: /x/cert.pem\n")
        self.assertEqual(env["GA_TLS_CERTFILE"], "/x/cert.pem")
        self.assertIn("network.tls_certfile", warnings)

    def test_identity_provider_deprecated_path(self):
        env, warnings = self._resolve_env(
            "backends:\n  kiro:\n    identity_provider: https://idp\n"
        )
        self.assertEqual(env["KIRO_IDENTITY_PROVIDER"], "https://idp")
        self.assertIn("backends.kiro.identity_provider", warnings)
        self.assertIn("backends.kiro.identity_center.url", warnings)

    def test_machine_cpus_deprecated_path(self):
        env, warnings = self._resolve_env("machine:\n  cpus: 4\n")
        self.assertEqual(env["GA_MACHINE_CPUS"], "4")
        self.assertIn("machine.cpus", warnings)
        self.assertIn("machine.resources.cpus", warnings)

    def test_images_section_merged_into_machine(self):
        env, warnings = self._resolve_env(
            "images:\n  kc_image: localhost/custom:v2\n"
        )
        self.assertEqual(env["KC_IMAGE"], "localhost/custom:v2")
        self.assertIn("images.kc_image", warnings)
        self.assertIn("machine.images.kc_image", warnings)

    def test_dashboard_port_range_deprecated_path(self):
        env, warnings = self._resolve_env(
            "portal:\n  dashboard_port_range_start: 70000\n"
        )
        self.assertEqual(env["GA_DASHBOARD_PORT_RANGE_START"], "70000")
        self.assertIn("portal.dashboard_port_range_start", warnings)

    def test_model_override_removed_warns_and_ignored(self):
        env, warnings = self._resolve_env("model:\n  override: some-model\n")
        # No env var for a removed key, and the global default is untouched.
        self.assertNotIn("KC_MODEL_OVERRIDE", env)
        self.assertEqual(env["KC_MODEL_DEFAULT"], "")
        self.assertIn("model.override", warnings)
        self.assertIn("removed", warnings)
        self.assertIn("backends.<backend>.model.override", warnings)

    def test_kiro_license_removed_warns_and_ignored(self):
        env, warnings = self._resolve_env("backends:\n  kiro:\n    license: pro\n")
        self.assertNotIn("KIRO_LICENSE", env)
        self.assertIn("backends.kiro.license", warnings)
        self.assertIn("removed", warnings)
        self.assertNotIn("unknown config key", warnings)

    def test_deprecated_path_does_not_warn_as_unknown(self):
        _env, warnings = self._resolve_env("machine:\n  cpus: 4\n")
        # The old path is rewritten, not surfaced as an unknown-key warning.
        self.assertNotIn("unknown config key", warnings)

    def test_new_path_wins_when_both_present(self):
        env, warnings = self._resolve_env(
            "backends:\n  agent: kiro\n  default: [kiro, claude]\n"
        )
        self.assertEqual(env["GA_CREW_AGENT"], "kiro,claude")
        # No deprecation warning for backends.agent — the new path already set it.
        self.assertNotIn("backends.agent", warnings)


class TestBackendsDefaultList(unittest.TestCase):
    """TRN-257: backends.default accepts a list (canonical) or string (deprecated)."""

    def test_list_joined_to_comma_string(self):
        env = yaml_config.flatten_to_env({"backends": {"default": ["kiro", "claude"]}})
        self.assertEqual(env["GA_CREW_AGENT"], "kiro,claude")

    def test_single_element_list(self):
        env = yaml_config.flatten_to_env({"backends": {"default": ["kiro"]}})
        self.assertEqual(env["GA_CREW_AGENT"], "kiro")

    def test_string_form_warns_but_resolves(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            env = yaml_config.flatten_to_env(
                {"backends": {"default": "kiro,codex"}}
            )
        self.assertEqual(env["GA_CREW_AGENT"], "kiro,codex")
        self.assertIn("backends.default", buf.getvalue())
        self.assertIn("deprecated", buf.getvalue())

    def test_default_install_uses_list_no_warning(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            merged = yaml_config.resolve_config("", "", None)
            env = yaml_config.flatten_to_env(merged)
        self.assertEqual(env["GA_CREW_AGENT"], "kiro")
        # The built-in default is a list, so no string-deprecation warning fires.
        self.assertNotIn("backends.default as a string", buf.getvalue())


class TestPerBackendModelEnvVars(unittest.TestCase):
    """TRN-257: per-backend model env vars emitted from the new YAML paths."""

    def test_all_six_present_in_defaults(self):
        merged = yaml_config.resolve_config("", "", None)
        env = yaml_config.flatten_to_env(merged)
        for var in (
            "KC_MODEL_KIRO_OVERRIDE",
            "KC_MODEL_KIRO_DEFAULT",
            "KC_MODEL_CLAUDE_OVERRIDE",
            "KC_MODEL_CLAUDE_DEFAULT",
            "KC_MODEL_CODEX_OVERRIDE",
            "KC_MODEL_CODEX_DEFAULT",
        ):
            self.assertIn(var, env)
            self.assertEqual(env[var], "")

    def test_kiro_override_resolves(self):
        env = yaml_config.flatten_to_env(
            {"backends": {"kiro": {"model": {"override": "claude-sonnet-4-5"}}}}
        )
        self.assertEqual(env["KC_MODEL_KIRO_OVERRIDE"], "claude-sonnet-4-5")

    def test_codex_default_resolves(self):
        env = yaml_config.flatten_to_env(
            {"backends": {"codex": {"model": {"default": "gpt-x"}}}}
        )
        self.assertEqual(env["KC_MODEL_CODEX_DEFAULT"], "gpt-x")

    def test_global_model_override_absent(self):
        # The global model.override env var no longer exists anywhere.
        self.assertNotIn("KC_MODEL_OVERRIDE", yaml_config.DEFAULTS)
        self.assertNotIn("KC_MODEL_OVERRIDE", yaml_config._ENV_TO_PATH)



class TestPortalOnlyHost(unittest.TestCase):
    """portal-only-host: HOST is ga-portal's bind address, loopback by default."""

    def test_host_defaults_to_loopback(self):
        env = yaml_config.flatten_to_env(yaml_config._defaults_tree())
        self.assertEqual(env["HOST"], "127.0.0.1")

    def test_loopback_detection(self):
        for host in ("", "127.0.0.1", "127.1.2.3", "::1", "[::1]", "localhost", "LOCALHOST"):
            self.assertTrue(yaml_config.is_loopback(host), host)
        for host in ("0.0.0.0", "::", "192.168.1.10", "example.com"):
            self.assertFalse(yaml_config.is_loopback(host), host)

    def test_is_loopback_subcommand(self):
        import contextlib
        import io

        for host, want in (("127.0.0.1", "true"), ("0.0.0.0", "false")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = yaml_config.main(["is-loopback", host])
            self.assertEqual(rc, 0)
            self.assertEqual(buf.getvalue().strip(), want)


class TestApiKeyStates(unittest.TestCase):
    """portal-only-host: network.api_key is a key, unset, or false (opt-out)."""

    def _env(self, api_key):
        return yaml_config.flatten_to_env({"network": {"api_key": api_key}})

    def test_string_enables_auth(self):
        env = self._env("s3cret")
        self.assertEqual(env["GA_API_KEY"], "s3cret")
        self.assertEqual(env["GA_API_KEY_DISABLED"], "")
        self.assertEqual(env["GA_API_KEY_SOURCE"], "yaml")

    def test_false_is_explicit_opt_out(self):
        env = self._env(False)
        self.assertEqual(env["GA_API_KEY"], "")
        self.assertEqual(env["GA_API_KEY_DISABLED"], "true")
        self.assertEqual(env["GA_API_KEY_SOURCE"], "yaml")

    def test_null_and_empty_are_unset_not_opt_out(self):
        for value in (None, ""):
            env = self._env(value)
            self.assertEqual(env["GA_API_KEY"], "")
            self.assertEqual(env["GA_API_KEY_DISABLED"], "")
            self.assertEqual(env["GA_API_KEY_SOURCE"], "")

    def test_absent_is_unset(self):
        env = yaml_config.flatten_to_env({})
        self.assertEqual(env["GA_API_KEY_DISABLED"], "")
        self.assertEqual(env["GA_API_KEY_SOURCE"], "")

    def test_true_and_quoted_booleans_rejected(self):
        for value in (True, "true", "false", "FALSE", 123, ["k"]):
            with self.assertRaises(ValueError, msg=repr(value)):
                self._env(value)

    def test_resolve_subcommand_fails_on_invalid_key(self):
        import contextlib
        import io

        tmp = tempfile.mkdtemp()
        cfg = os.path.join(tmp, "c.yaml")
        with open(cfg, "w", encoding="utf-8") as fh:
            fh.write('network:\n  api_key: "false"\n')
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = yaml_config.main(["resolve", "--config", cfg])
        self.assertEqual(rc, 1)
        self.assertIn("network.api_key", err.getvalue())


class TestRequireApiKeyDeprecated(unittest.TestCase):
    """portal-only-host: network.require_api_key is deprecated; only off maps."""

    def _env(self, setting, api_key=None):
        import contextlib
        import io

        network = {"require_api_key": setting}
        if api_key is not None:
            network["api_key"] = api_key
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            env = yaml_config.flatten_to_env({"network": network})
        return env, buf.getvalue()

    def test_off_emits_deprecated_off_marker(self):
        env, warnings = self._env("off")
        self.assertEqual(env["GA_API_KEY_DEPRECATED_OFF"], "true")
        # The opt-out itself is applied by install.sh after key resolution.
        self.assertEqual(env["GA_API_KEY_DISABLED"], "")
        self.assertIn("network.api_key: false", warnings)

    def test_error_and_warn_ignored_with_warning(self):
        for setting in ("error", "warn"):
            env, warnings = self._env(setting)
            self.assertNotIn("GA_API_KEY_DEPRECATED_OFF", env)
            self.assertIn("deprecated", warnings)

    def test_never_emits_ga_require_api_key(self):
        for setting in ("off", "error", "warn"):
            env, _ = self._env(setting)
            self.assertNotIn("GA_REQUIRE_API_KEY", env)
        self.assertNotIn("GA_REQUIRE_API_KEY", yaml_config.DEFAULTS)
        self.assertNotIn("GA_REQUIRE_API_KEY", yaml_config._ENV_TO_PATH)

    def test_key_alongside_off_is_still_resolved(self):
        env, _ = self._env("off", api_key="s3cret")
        self.assertEqual(env["GA_API_KEY"], "s3cret")

    def test_not_reported_as_unknown(self):
        self.assertEqual(
            yaml_config.collect_unknown_paths({"network": {"require_api_key": "off"}}), []
        )


class TestMigrateRequireApiKey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conf = os.path.join(self.tmp, "ghostship.conf")
        self.out = os.path.join(self.tmp, "ghostship.yaml")

    def _migrate(self, content: str) -> dict:
        with open(self.conf, "w", encoding="utf-8") as fh:
            fh.write(content)
        unknown = yaml_config.migrate_conf(self.conf, self.out)
        self.assertEqual(unknown, [])
        return yaml_config.load_yaml(self.out)

    def test_off_without_key_becomes_api_key_false(self):
        loaded = self._migrate("GA_REQUIRE_API_KEY=off\n")
        self.assertIs(loaded["network"]["api_key"], False)
        self.assertNotIn("require_api_key", loaded["network"])

    def test_off_with_key_keeps_key(self):
        loaded = self._migrate("GA_REQUIRE_API_KEY=off\nGA_API_KEY=s3cret\n")
        self.assertEqual(loaded["network"]["api_key"], "s3cret")

    def test_error_dropped(self):
        loaded = self._migrate("GA_REQUIRE_API_KEY=warn\nPORT=9000\n")
        self.assertNotIn("api_key", loaded["network"])
        self.assertNotIn("require_api_key", loaded["network"])


if __name__ == "__main__":
    unittest.main()
