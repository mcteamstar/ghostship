"""Unit tests for scripts/lib/yaml_config.py (TRN-253).

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

# Load the standalone module directly (it lives under scripts/lib, not a package).
_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "lib" / "yaml_config.py"
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
            {"backends": {"kiro": {"identity_provider": "https://idp"}}}
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
            loaded["backends"]["kiro"]["identity_provider"],
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


if __name__ == "__main__":
    unittest.main()
