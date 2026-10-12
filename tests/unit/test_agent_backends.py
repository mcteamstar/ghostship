"""Unit tests for TRN-213 trn-213-config-install-consistency: GA_CREW_AGENT consolidation.

GA_CREW_AGENT replaces GA_AGENT_BACKENDS + GA_CREW_ACP_BACKEND (TRN-213).

Covers:
- Parsing: default kiro-only, multiple backends, normalisation, unknown names rejected.
- Kiro is always enabled; listing it changes nothing.
- Deprecated alias GA_CREW_ACP_BACKEND maps to GA_CREW_AGENT with a logged warning.
- Retired GA_INCLUDE_* flags fail startup.
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


def _enabled_backends(cfg: Config) -> frozenset[str]:
    """Derive the frozenset of enabled backends from ga_crew_agent."""
    return frozenset(
        name.strip().lower()
        for name in cfg.ga_crew_agent.split(",")
        if name.strip()
    )


class TestParsing(unittest.TestCase):
    def test_default_set_is_kiro_only(self):
        self.assertEqual(_enabled_backends(_from_env({})), frozenset({"kiro"}))
        self.assertEqual(_enabled_backends(_from_env({"GA_CREW_AGENT": ""})), frozenset({"kiro"}))

    def test_multiple_backends_enabled(self):
        cfg = _from_env({"GA_CREW_AGENT": "kiro,claude,codex"})
        self.assertEqual(_enabled_backends(cfg), frozenset({"kiro", "claude", "codex"}))

    def test_case_whitespace_empty_and_duplicates_normalised(self):
        cfg = _from_env({"GA_CREW_AGENT": " Claude,,claude , CODEX"})
        self.assertEqual(_enabled_backends(cfg), frozenset({"kiro", "claude", "codex"}))

    def test_parse_keeps_first_listed_order_and_drops_kiro(self):
        self.assertEqual(parse_agent_backends(" Kiro, CODEX,,claude,codex"), ("codex", "claude"))
        self.assertEqual(parse_agent_backends(""), ())

    def test_opencode_is_a_valid_backend(self):
        cfg = _from_env({"GA_CREW_AGENT": "claude,opencode"})
        self.assertEqual(_enabled_backends(cfg), frozenset({"kiro", "claude", "opencode"}))

    def test_opencode_case_normalised(self):
        cfg = _from_env({"GA_CREW_AGENT": " OpenCode "})
        self.assertEqual(_enabled_backends(cfg), frozenset({"kiro", "opencode"}))
        # First listed entry is the runtime default
        self.assertEqual(cfg.ga_crew_agent.split(",")[0].strip(), "opencode")

    def test_unknown_backend_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            _from_env({"GA_CREW_AGENT": "claude,nonesuch"})
        message = str(ctx.exception)
        self.assertIn("nonesuch", message)
        self.assertIn("opencode", message)  # names the valid backends (now incl. opencode)


class TestKiroAlwaysEnabled(unittest.TestCase):
    def test_omitting_kiro_does_not_disable_it(self):
        cfg = _from_env({"GA_CREW_AGENT": "claude"})
        self.assertIn("kiro", _enabled_backends(cfg))
        # First entry (runtime default) is the first listed backend
        self.assertEqual(cfg.ga_crew_agent.split(",")[0].strip(), "claude")

    def test_listing_kiro_changes_nothing(self):
        self.assertEqual(
            _enabled_backends(_from_env({"GA_CREW_AGENT": "kiro,claude"})),
            _enabled_backends(_from_env({"GA_CREW_AGENT": "claude"})),
        )


class TestDefaultBackend(unittest.TestCase):
    def test_default_inside_set_accepted(self):
        cfg = _from_env({"GA_CREW_AGENT": "claude,codex"})
        # Runtime default is first entry
        self.assertEqual(cfg.ga_crew_agent.split(",")[0].strip(), "claude")

    def test_default_outside_set_accepted_and_kiro_is_default(self):
        # With just "kiro", runtime default is kiro
        cfg = _from_env({"GA_CREW_AGENT": "kiro"})
        self.assertEqual(cfg.ga_crew_agent, "kiro")


class TestDeprecatedAlias(unittest.TestCase):
    def test_deprecated_ga_crew_acp_backend_maps_to_ga_crew_agent_with_warning(self):
        """GA_CREW_ACP_BACKEND is a deprecated alias — maps to GA_CREW_AGENT with a WARNING."""
        with patch.dict("os.environ", {"GA_CREW_ACP_BACKEND": "claude"}, clear=True):
            with self.assertLogs("transport.config", level=logging.WARNING) as logs:
                cfg = Config.from_env()
        output = "\n".join(logs.output)
        self.assertIn("GA_CREW_ACP_BACKEND", output)
        self.assertIn("deprecated", output.lower())
        # The mapping must have taken effect
        self.assertIn("claude", cfg.ga_crew_agent)


class TestRetiredFlags(unittest.TestCase):
    def test_retired_claude_flag_stops_startup(self):
        with self.assertRaises(ConfigError) as ctx:
            _from_env({"GA_INCLUDE_CLAUDE_AGENT": "true"})
        self.assertIn("GA_INCLUDE_CLAUDE_AGENT", str(ctx.exception))
        self.assertIn("GA_CREW_AGENT", str(ctx.exception))

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
            _from_env({"GA_INCLUDE_CLAUDE_AGENT": "true", "GA_CREW_AGENT": "claude"})


class TestInertSettings(unittest.TestCase):
    SECRET = "sk-ant-THIS-MUST-NOT-BE-LOGGED"

    def test_credential_for_disabled_backend_is_inert(self):
        cfg = Config(ga_crew_agent="kiro", ga_crew_anthropic_api_key=self.SECRET, ga_crew_openai_base_url="https://x")
        self.assertEqual(
            inert_backend_settings(cfg, frozenset({"ga-codex-auth"})),
            ["GA_CREW_ANTHROPIC_API_KEY", "GA_CREW_OPENAI_BASE_URL", "ga-codex-auth"],
        )

    def test_opencode_credential_is_inert_when_disabled(self):
        cfg = Config(ga_crew_agent="kiro")
        self.assertEqual(
            inert_backend_settings(cfg, frozenset({"ga-opencode-auth"})),
            ["ga-opencode-auth"],
        )

    def test_opencode_credential_not_inert_when_enabled(self):
        cfg = Config(ga_crew_agent="kiro,opencode")
        self.assertEqual(inert_backend_settings(cfg, frozenset({"ga-opencode-auth"})), [])

    def test_no_inert_settings_for_an_enabled_backend(self):
        cfg = Config(ga_crew_agent="kiro,claude",
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
                                ("_codex_login_pending_lock", "_codex_login_pending"),
                                ("_opencode_login_pending_lock", "_opencode_login_pending")):
            with getattr(_lifecycle, lock_name):
                setattr(_lifecycle, attr, None)

    def test_login_refused_for_backend_not_in_set(self):
        with patch.object(server.cfg, "ga_crew_agent", "kiro"), \
             patch.object(server, "_initiate_claude_login") as initiate:
            response = _run(server._handle_claude_login_post(Mock()))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"GA_CREW_AGENT", response.body)
        initiate.assert_not_called()

    def test_codex_login_refused_for_backend_not_in_set(self):
        with patch.object(server.cfg, "ga_crew_agent", "kiro,claude"), \
             patch.object(server, "_initiate_codex_login") as initiate:
            response = _run(server._handle_codex_login_post(Mock()))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"GA_CREW_AGENT", response.body)
        initiate.assert_not_called()

    def test_login_allowed_for_enabled_backend_that_is_not_the_default(self):
        with patch.object(server.cfg, "ga_crew_agent", "kiro,claude"), \
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
            with patch.object(server.cfg, "ga_crew_agent", "kiro"), \
                 patch.object(server, "_claude_auth_exists", return_value=True), \
                 patch.object(server, "_claude_auth_file_path", return_value=auth), \
                 patch.object(server, "_get_podman", return_value=Mock()), \
                 patch.object(server, "_registry_lock", threading.Lock()), \
                 patch.object(server, "_load_registry", return_value={"crews": {}}):
                response = _run(server._handle_claude_logout_post(Mock()))
            self.assertEqual(response.status_code, 200)
            self.assertFalse(auth.exists())

    def test_opencode_login_refused_for_backend_not_in_set(self):
        with patch.object(server.cfg, "ga_crew_agent", "kiro"), \
             patch.object(server, "_initiate_opencode_login") as initiate:
            response = _run(server._handle_opencode_login_post(Mock()))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"GA_CREW_AGENT", response.body)
        initiate.assert_not_called()

    def test_opencode_login_allowed_for_enabled_backend_launches_container(self):
        with patch.object(server.cfg, "ga_crew_agent", "kiro,opencode"), \
             patch.object(server, "GA_CREW_ACP_BACKEND", "kiro"), \
             patch.object(server, "_opencode_auth_exists", return_value=False), \
             patch.object(server, "_get_podman", return_value=Mock()), \
             patch.object(server, "_initiate_opencode_login",
                          return_value={"login_url": "https://opencode.ai/x", "code": None}) as initiate:
            response = _run(server._handle_opencode_login_post(Mock()))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"login_url", response.body)
        initiate.assert_called_once()

    def test_opencode_logout_deletes_credential_regardless_of_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = Path(tmp) / "ga-opencode-auth"
            auth.write_bytes(b"x")
            with patch.object(server.cfg, "ga_crew_agent", "kiro"), \
                 patch.object(server, "_opencode_auth_exists", return_value=True), \
                 patch.object(server, "_opencode_auth_file_path", return_value=auth), \
                 patch.object(server, "_get_podman", return_value=Mock()), \
                 patch.object(server, "_registry_lock", threading.Lock()), \
                 patch.object(server, "_load_registry", return_value={"crews": {}}):
                response = _run(server._handle_opencode_logout_post(Mock()))
            self.assertEqual(response.status_code, 200)
            self.assertFalse(auth.exists())

    def test_opencode_logout_idempotent_when_unauthenticated(self):
        with patch.object(server, "_opencode_auth_exists", return_value=False):
            response = _run(server._handle_opencode_logout_post(Mock()))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"logged_out", response.body)

    def test_kiro_is_never_refused(self):
        for value in ("", "claude", "codex", "claude,codex"):
            cfg = _from_env({"GA_CREW_AGENT": value})
            self.assertIn("kiro", _enabled_backends(cfg))


class TestLaunchGuard(unittest.TestCase):
    """Defensive: configuration can't reach this, so it's tested by patching."""

    def test_launch_refuses_backend_outside_set(self):
        with patch.object(server.cfg, "ga_crew_agent", "kiro"), \
             patch.object(server, "GA_CREW_ACP_BACKEND", "claude"), \
             patch.object(server, "_get_podman", return_value=Mock()), \
             patch.object(server, "_initiate_claude_login") as initiate:
            result = server.launch("guard-test")
        self.assertEqual(result.get("error"), "backend_not_enabled")
        self.assertIn("GA_CREW_AGENT", result.get("instructions", ""))
        initiate.assert_not_called()

    def test_opencode_launch_without_credential_initiates_login_and_does_not_start(self):
        # GA_CREW_AGENT=opencode with no ga-opencode-auth → launch returns
        # not_authenticated with the login step, and the crew is not created.
        with patch.object(server.cfg, "ga_crew_agent", "opencode,kiro"), \
             patch.object(server, "GA_CREW_ACP_BACKEND", "opencode"), \
             patch.object(server, "_get_podman", return_value=Mock()), \
             patch.object(server, "_opencode_auth_exists", return_value=False), \
             patch.object(server, "_initiate_opencode_login",
                          return_value={"login_url": "https://opencode.ai/x", "code": None}) as initiate, \
             patch.object(server, "_load_registry") as load_reg:
            result = server.launch("opencode-guard-test")
        self.assertEqual(result.get("error"), "not_authenticated")
        self.assertIn("opencode", result.get("instructions", "").lower())
        initiate.assert_called_once()
        # Crew must not be registered — the guard returns before registry writes.
        load_reg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
