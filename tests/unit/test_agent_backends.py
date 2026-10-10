"""Unit tests for TRN-202 trn-202-consolidate-agent-backends: GA_AGENT_BACKENDS.

Covers the scenarios in openspec/changes/trn-202-consolidate-agent-backends/
specs/agent-backends:
- Parsing: default kiro-only set, multiple backends, normalisation of case,
  whitespace, empty entries and duplicates, unknown names rejected.
- Kiro is always enabled; listing it changes nothing.
- The default backend must be an enabled backend.
- Retired GA_INCLUDE_* flags fail startup, even when set to "false".
- Inert-setting warnings: names only, never values, once per start.
- Login follows the enabled set, not the default; logout is never gated.
- The launch guard refuses a backend outside the set (defensive path).
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tests.unit._stubs import install_import_stubs
install_import_stubs()

from transport.config import (  # noqa: E402 (after stub install)
    Config,
    ConfigError,
    inert_backend_settings,
    parse_agent_backends,
)
import transport.lifecycle as _lifecycle  # noqa: E402
import transport.server as server  # noqa: E402


def _from_env(env: dict[str, str]) -> Config:
    """Build a Config from exactly ``env`` (plus nothing inherited)."""
    with patch.dict("os.environ", env, clear=True):
        return Config.from_env()


class TestParsing(unittest.TestCase):
    def test_default_set_is_kiro_only(self):
        self.assertEqual(_from_env({}).ga_agent_backends, frozenset({"kiro"}))
        self.assertEqual(_from_env({"GA_AGENT_BACKENDS": ""}).ga_agent_backends, frozenset({"kiro"}))

    def test_multiple_backends_enabled(self):
        cfg = _from_env({"GA_AGENT_BACKENDS": "claude, codex"})
        self.assertEqual(cfg.ga_agent_backends, frozenset({"kiro", "claude", "codex"}))

    def test_case_whitespace_empty_and_duplicates_normalised(self):
        cfg = _from_env({"GA_AGENT_BACKENDS": " Claude,,claude , CODEX"})
        self.assertEqual(cfg.ga_agent_backends, frozenset({"kiro", "claude", "codex"}))

    def test_parse_keeps_first_listed_order_and_drops_kiro(self):
        self.assertEqual(parse_agent_backends(" Kiro, CODEX,,claude,codex"), ("codex", "claude"))
        self.assertEqual(parse_agent_backends(""), ())

    def test_unknown_backend_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            _from_env({"GA_AGENT_BACKENDS": "claude,opencode"})
        message = str(ctx.exception)
        self.assertIn("opencode", message)
        self.assertIn("codex", message)  # names the valid backends


class TestKiroAlwaysEnabled(unittest.TestCase):
    def test_omitting_kiro_does_not_disable_it(self):
        cfg = _from_env({"GA_AGENT_BACKENDS": "claude"})
        self.assertIn("kiro", cfg.ga_agent_backends)
        self.assertEqual(cfg.ga_crew_acp_backend, "kiro")

    def test_listing_kiro_changes_nothing(self):
        self.assertEqual(
            _from_env({"GA_AGENT_BACKENDS": "kiro,claude"}).ga_agent_backends,
            _from_env({"GA_AGENT_BACKENDS": "claude"}).ga_agent_backends,
        )


class TestDefaultBackend(unittest.TestCase):
    def test_default_outside_set_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            _from_env({"GA_CREW_ACP_BACKEND": "claude"})
        message = str(ctx.exception)
        self.assertIn("GA_CREW_ACP_BACKEND", message)
        self.assertIn("GA_AGENT_BACKENDS", message)
        self.assertIn("ghostship install", message)

    def test_default_inside_set_accepted(self):
        cfg = _from_env({"GA_CREW_ACP_BACKEND": "claude", "GA_AGENT_BACKENDS": "claude"})
        self.assertEqual(cfg.ga_crew_acp_backend, "claude")


class TestRetiredFlags(unittest.TestCase):
    def test_retired_claude_flag_stops_startup(self):
        with self.assertRaises(ConfigError) as ctx:
            _from_env({"GA_INCLUDE_CLAUDE_AGENT": "true"})
        self.assertIn("GA_INCLUDE_CLAUDE_AGENT", str(ctx.exception))
        self.assertIn("GA_AGENT_BACKENDS", str(ctx.exception))

    def test_retired_flag_set_to_false_still_stops_startup(self):
        with self.assertRaises(ConfigError) as ctx:
            _from_env({"GA_INCLUDE_CODEX_AGENT": "false"})
        self.assertIn("GA_INCLUDE_CODEX_AGENT", str(ctx.exception))

    def test_empty_retired_flag_is_not_set(self):
        # "present with a non-empty value" is the trigger; an empty value is ignored.
        _from_env({"GA_INCLUDE_CLAUDE_AGENT": ""})

    def test_retired_flag_does_not_change_the_set(self):
        # The flag never enables anything: it fails before the set is built.
        with self.assertRaises(ConfigError):
            _from_env({"GA_INCLUDE_CLAUDE_AGENT": "true", "GA_CREW_ACP_BACKEND": "claude"})


class TestInertSettings(unittest.TestCase):
    SECRET = "sk-ant-THIS-MUST-NOT-BE-LOGGED"

    def test_credential_for_disabled_backend_is_inert(self):
        cfg = Config(ga_crew_anthropic_api_key=self.SECRET, ga_crew_openai_base_url="https://x")
        self.assertEqual(
            inert_backend_settings(cfg, frozenset({"ga-codex-auth"})),
            ["GA_CREW_ANTHROPIC_API_KEY", "GA_CREW_OPENAI_BASE_URL", "ga-codex-auth"],
        )

    def test_no_inert_settings_for_an_enabled_backend(self):
        cfg = Config(ga_agent_backends=frozenset({"kiro", "claude"}),
                     ga_crew_anthropic_api_key=self.SECRET)
        self.assertEqual(inert_backend_settings(cfg, frozenset({"ga-claude-auth"})), [])

    def test_warning_names_the_setting_once_and_never_its_value(self):
        cfg = Config(ga_crew_anthropic_api_key=self.SECRET)
        with patch.object(server, "cfg", cfg), \
             patch.object(server, "_claude_auth_exists", return_value=False), \
             patch.object(server, "_codex_auth_exists", return_value=False), \
             self.assertLogs(server.logger, level=logging.WARNING) as logs:
            server._warn_inert_backend_settings()
        output = "\n".join(logs.output)
        self.assertEqual(output.count("GA_CREW_ANTHROPIC_API_KEY"), 1)
        self.assertNotIn(self.SECRET, output)

    def test_loading_config_logs_no_inert_warnings(self):
        # Config loads in several modules; the warnings must come only from the
        # transport startup path, so loading config must not emit them.
        with patch.dict("os.environ", {"GA_CREW_OPENAI_API_KEY": "sk-x"}, clear=True), \
             self.assertNoLogs("transport.config", level=logging.WARNING):
            Config.from_env()


def _run(coro):
    return asyncio.run(coro)


class TestLoginGating(unittest.TestCase):
    def setUp(self):
        for lock_name, attr in (("_claude_login_pending_lock", "_claude_login_pending"),
                                ("_codex_login_pending_lock", "_codex_login_pending")):
            with getattr(_lifecycle, lock_name):
                setattr(_lifecycle, attr, None)

    def test_login_refused_for_backend_not_in_set(self):
        with patch.object(server.cfg, "ga_agent_backends", frozenset({"kiro"})), \
             patch.object(server, "_initiate_claude_login") as initiate:
            response = _run(server._handle_claude_login_post(Mock()))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"GA_AGENT_BACKENDS", response.body)
        initiate.assert_not_called()

    def test_codex_login_refused_for_backend_not_in_set(self):
        with patch.object(server.cfg, "ga_agent_backends", frozenset({"kiro", "claude"})), \
             patch.object(server, "_initiate_codex_login") as initiate:
            response = _run(server._handle_codex_login_post(Mock()))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"GA_AGENT_BACKENDS", response.body)
        initiate.assert_not_called()

    def test_login_allowed_for_enabled_backend_that_is_not_the_default(self):
        with patch.object(server.cfg, "ga_agent_backends", frozenset({"kiro", "claude"})), \
             patch.object(server, "GA_CREW_ACP_BACKEND", "kiro"), \
             patch.object(server, "_claude_auth_exists", return_value=False), \
             patch.object(server, "_get_podman", return_value=Mock()), \
             patch.object(server, "_initiate_claude_login",
                          return_value={"login_url": "https://claude.com/x", "code": None}):
            response = _run(server._handle_claude_login_post(Mock()))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"login_url", response.body)

    def test_logout_works_for_a_disabled_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = Path(tmp) / "ga-claude-auth"
            auth.write_bytes(b"x")
            with patch.object(server.cfg, "ga_agent_backends", frozenset({"kiro"})), \
                 patch.object(server, "_claude_auth_exists", return_value=True), \
                 patch.object(server, "_claude_auth_file_path", return_value=auth), \
                 patch.object(server, "_get_podman", return_value=Mock()), \
                 patch.object(server, "_registry_lock", threading.Lock()), \
                 patch.object(server, "_load_registry", return_value={"crews": {}}):
                response = _run(server._handle_claude_logout_post(Mock()))
            self.assertEqual(response.status_code, 200)
            self.assertFalse(auth.exists())

    def test_kiro_is_never_refused(self):
        for value in ("", "claude", "codex", "claude,codex"):
            self.assertIn("kiro", _from_env({"GA_AGENT_BACKENDS": value}).ga_agent_backends)


class TestLaunchGuard(unittest.TestCase):
    """Defensive: configuration can't reach this, so it's tested by patching."""

    def test_launch_refuses_backend_outside_set(self):
        with patch.object(server.cfg, "ga_agent_backends", frozenset({"kiro"})), \
             patch.object(server, "GA_CREW_ACP_BACKEND", "claude"), \
             patch.object(server, "_get_podman", return_value=Mock()), \
             patch.object(server, "_initiate_claude_login") as initiate:
            result = server.launch("guard-test")
        self.assertEqual(result.get("error"), "backend_not_enabled")
        self.assertIn("GA_AGENT_BACKENDS", result.get("instructions", ""))
        initiate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
