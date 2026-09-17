"""Unit tests for TRN-167: Claude Code ACP backend support.

Covers:
- 6.1 GA_CREW_ACP_BACKEND config validation (invalid value → ConfigError;
      GA_CREW_ACP_BACKEND=claude without API key → ConfigError at startup).
- 6.2 _patch_crew_config writes acp_backend: "claude" when claude backend selected.
- 6.3 kiro auth injection is skipped and ANTHROPIC_API_KEY is injected when
      GA_CREW_ACP_BACKEND=claude.
- 6.4 crews() response includes acp_backend per crew entry.
"""

from __future__ import annotations

import base64
import importlib
import json
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

from transport.config import Config, ConfigError

# Install stdlib stubs for httpx2/mcp/starlette/uvicorn so the server and
# lifecycle modules load in a dependency-free test environment (same bootstrap
# as test_file_transfer.py uses, which helpers.py re-exports as `server`).
from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)
import transport.server as _server       # noqa: E402


# ── 6.1 Config validation ──────────────────────────────────────────────────────


class TestAcpBackendConfigValidation(unittest.TestCase):
    """GA_CREW_ACP_BACKEND validation: invalid value → startup ConfigError."""

    def test_invalid_value_raises_config_error(self) -> None:
        """Unrecognised GA_CREW_ACP_BACKEND value raises ConfigError at from_env()."""
        with patch.dict("os.environ", {"GA_CREW_ACP_BACKEND": "openai"}):
            with self.assertRaises(ConfigError) as ctx:
                Config.from_env()
        self.assertIn("GA_CREW_ACP_BACKEND", str(ctx.exception))
        self.assertIn("openai", str(ctx.exception))

    def test_invalid_value_is_config_error_subclass(self) -> None:
        """ConfigError is a ValueError subclass — existing bare ValueError catches still work."""
        with patch.dict("os.environ", {"GA_CREW_ACP_BACKEND": "bogus"}):
            with self.assertRaises(ValueError):
                Config.from_env()

    def test_kiro_backend_is_valid(self) -> None:
        with patch.dict("os.environ", {"GA_CREW_ACP_BACKEND": "kiro"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_crew_acp_backend, "kiro")

    def test_claude_backend_is_valid_with_key(self) -> None:
        env = {
            "GA_CREW_ACP_BACKEND": "claude",
            "GA_CREW_ANTHROPIC_API_KEY": "sk-ant-test123",
        }
        with patch.dict("os.environ", env):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_crew_acp_backend, "claude")

    def test_default_backend_is_kiro(self) -> None:
        # Clear GA_CREW_ACP_BACKEND to exercise the default.
        clean = {k: v for k, v in __import__("os").environ.items()
                 if k not in ("GA_CREW_ACP_BACKEND",)}
        with patch.dict("os.environ", clean, clear=True):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_crew_acp_backend, "kiro")

    def test_claude_without_api_key_fails_validate(self) -> None:
        """GA_CREW_ACP_BACKEND=claude + no API key raises ConfigError on validate()."""
        env = {
            "GA_CREW_ACP_BACKEND": "claude",
            "GA_CREW_ANTHROPIC_API_KEY": "",
        }
        with patch.dict("os.environ", env):
            cfg = Config.from_env()
        with self.assertRaises(ConfigError) as ctx:
            cfg.validate()
        self.assertIn("GA_CREW_ANTHROPIC_API_KEY", str(ctx.exception))
        self.assertIn("GA_CREW_ACP_BACKEND", str(ctx.exception))

    def test_kiro_backend_validate_passes_without_api_key(self) -> None:
        """validate() does not raise for kiro backend even without an Anthropic key."""
        with patch.dict("os.environ", {"GA_CREW_ACP_BACKEND": "kiro",
                                        "GA_CREW_ANTHROPIC_API_KEY": ""}):
            cfg = Config.from_env()
        cfg.validate()  # must not raise

    def test_ga_include_claude_agent_bool_default_off(self) -> None:
        """GA_INCLUDE_CLAUDE_AGENT defaults to False."""
        clean = {k: v for k, v in __import__("os").environ.items()
                 if k not in ("GA_INCLUDE_CLAUDE_AGENT",)}
        with patch.dict("os.environ", clean, clear=True):
            cfg = Config.from_env()
        self.assertFalse(cfg.ga_include_claude_agent)

    def test_ga_include_claude_agent_true(self) -> None:
        with patch.dict("os.environ", {"GA_INCLUDE_CLAUDE_AGENT": "true"}):
            cfg = Config.from_env()
        self.assertTrue(cfg.ga_include_claude_agent)


# ── 6.2 _patch_crew_config writes acp_backend ─────────────────────────────────


class TestPatchCrewConfigClaudeBackend(unittest.TestCase):
    """_patch_crew_config writes acp_backend: "claude" when claude backend selected."""

    def _run_patch(self, exec_result: str = "patched config.local.json") -> dict:
        """Run _patch_crew_config with GA_CREW_ACP_BACKEND=claude and capture the
        b64_overrides payload delivered to the patch_crew_config.py script."""
        podman = Mock()
        podman.container_exec.return_value = exec_result
        captured: list[str] = []

        def capture_exec(container, cmd, **kwargs):
            if len(cmd) >= 4 and "patch_crew_config.py" in cmd[1]:
                captured.append(cmd[3])
            return exec_result

        podman.container_exec.side_effect = capture_exec

        original_backend = _lifecycle.GA_CREW_ACP_BACKEND
        try:
            _lifecycle.GA_CREW_ACP_BACKEND = "claude"
            _lifecycle._patch_crew_config(podman, "gs-test")
        finally:
            _lifecycle.GA_CREW_ACP_BACKEND = original_backend

        self.assertEqual(len(captured), 1, "expected exactly one patch_crew_config.py exec call")
        overrides = json.loads(base64.b64decode(captured[0]).decode())
        return overrides

    def test_acp_backend_claude_written_to_agent_config(self) -> None:
        """acp_backend: 'claude' is present in the agent overrides when backend=claude."""
        overrides = self._run_patch()
        agent = overrides.get("agent", {})
        self.assertEqual(agent.get("acp_backend"), "claude")

    def test_acp_backend_not_written_for_kiro(self) -> None:
        """acp_backend key is absent from agent overrides when backend=kiro (default)."""
        podman = Mock()
        captured: list[str] = []

        def capture_exec(container, cmd, **kwargs):
            if len(cmd) >= 4 and "patch_crew_config.py" in cmd[1]:
                captured.append(cmd[3])
            return "patched config.local.json"

        podman.container_exec.side_effect = capture_exec

        original = _lifecycle.GA_CREW_ACP_BACKEND
        try:
            _lifecycle.GA_CREW_ACP_BACKEND = "kiro"
            _lifecycle._patch_crew_config(podman, "gs-test")
        finally:
            _lifecycle.GA_CREW_ACP_BACKEND = original

        self.assertEqual(len(captured), 1)
        overrides = json.loads(base64.b64decode(captured[0]).decode())
        agent = overrides.get("agent", {})
        self.assertNotIn("acp_backend", agent)


# ── 6.3 Auth injection branching for Claude backend ───────────────────────────


class TestFinishCrewSetupClaudeAuthBranch(unittest.TestCase):
    """kiro auth injection skipped; ANTHROPIC_API_KEY injected when backend=claude."""

    def _make_minimal_finish_setup_patches(self, backend: str):
        """Return a context-manager stack that patches all dependencies of
        _finish_crew_setup so it can run without real Podman/containers.
        Returns (stack, podman_mock, inject_auth_mock) so callers can inspect
        which calls were made to _inject_auth and container_exec."""
        import contextlib

        podman = Mock()
        podman.container_exec.return_value = "ready"
        podman.container_exec_checked = Mock(return_value="injected")
        podman.container_inspect.return_value = {
            "Config": {"Labels": {"org.ghostship.version": "test-version"}},
            "State": {"StartedAt": "2026-01-01T00:00:00Z"},
        }

        fake_cookie = "test-cookie-value"

        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(_lifecycle, "_wait_gateway", return_value=True))
        inject_auth_mock = stack.enter_context(patch.object(_lifecycle, "_inject_auth"))
        stack.enter_context(patch.object(_lifecycle, "_patch_crew_config"))
        stack.enter_context(patch.object(_lifecycle, "_copy_agents"))
        stack.enter_context(patch.object(_lifecycle, "_copy_skills"))
        stack.enter_context(patch.object(_lifecycle, "_copy_steering"))
        stack.enter_context(patch.object(_lifecycle, "_seed_openspec_store"))
        stack.enter_context(patch.object(_lifecycle, "_patch_models"))
        stack.enter_context(patch.object(_lifecycle, "_mint_cookie", return_value=fake_cookie))
        stack.enter_context(patch.object(_lifecycle, "_inject_policy", return_value="v1"))
        stack.enter_context(patch.object(_lifecycle, "_load_registry",
                                         return_value={"crews": {"test-crew": {}}}))
        stack.enter_context(patch.object(_lifecycle, "_save_registry"))
        stack.enter_context(patch.object(_lifecycle, "_cleanup_crew"))
        return stack, podman, inject_auth_mock

    def test_kiro_path_injects_auth_when_no_api_key(self) -> None:
        """On kiro backend without KIRO_API_KEY, _inject_auth is called."""
        stack, podman, inject_auth_mock = self._make_minimal_finish_setup_patches("kiro")
        original_kiro_key = _lifecycle.KIRO_API_KEY
        original_backend = _lifecycle.GA_CREW_ACP_BACKEND
        try:
            with stack:
                _lifecycle.KIRO_API_KEY = ""
                _lifecycle.GA_CREW_ACP_BACKEND = "kiro"
                _lifecycle._finish_crew_setup(
                    podman, "test-crew", "gs-test-crew",
                    "gs-vol-test", "gs-home-test",
                    "dGVzdA==",  # auth_b64
                    admiral_secret="a" * 64,
                )
        finally:
            _lifecycle.KIRO_API_KEY = original_kiro_key
            _lifecycle.GA_CREW_ACP_BACKEND = original_backend

        inject_auth_mock.assert_called_once()

    def test_claude_path_skips_inject_auth(self) -> None:
        """On claude backend, _inject_auth is never called."""
        stack, podman, inject_auth_mock = self._make_minimal_finish_setup_patches("claude")
        original_backend = _lifecycle.GA_CREW_ACP_BACKEND
        try:
            with stack:
                _lifecycle.GA_CREW_ACP_BACKEND = "claude"
                _lifecycle._finish_crew_setup(
                    podman, "test-crew", "gs-test-crew",
                    "gs-vol-test", "gs-home-test",
                    None,  # auth_b64 is None on the claude path
                    admiral_secret="a" * 64,
                )
        finally:
            _lifecycle.GA_CREW_ACP_BACKEND = original_backend

        inject_auth_mock.assert_not_called()

    def test_claude_path_injects_headless_env_var(self) -> None:
        """On claude backend, CLAUDE_CODE_HEADLESS=1 is written via container_exec."""
        stack, podman, _ = self._make_minimal_finish_setup_patches("claude")
        original_backend = _lifecycle.GA_CREW_ACP_BACKEND
        try:
            with stack:
                _lifecycle.GA_CREW_ACP_BACKEND = "claude"
                _lifecycle._finish_crew_setup(
                    podman, "test-crew", "gs-test-crew",
                    "gs-vol-test", "gs-home-test",
                    None,
                    admiral_secret="a" * 64,
                )
        finally:
            _lifecycle.GA_CREW_ACP_BACKEND = original_backend

        # Verify at least one container_exec call wrote CLAUDE_CODE_HEADLESS
        exec_cmds = [str(c) for c in podman.container_exec.call_args_list]
        self.assertTrue(
            any("CLAUDE_CODE_HEADLESS" in cmd for cmd in exec_cmds),
            f"Expected CLAUDE_CODE_HEADLESS injected via container_exec, got: {exec_cmds}",
        )

    def test_claude_path_emits_warning_about_anthropic(self) -> None:
        """On claude backend, a WARNING is logged naming api.anthropic.com."""
        stack, podman, _ = self._make_minimal_finish_setup_patches("claude")
        original_backend = _lifecycle.GA_CREW_ACP_BACKEND
        try:
            with stack:
                _lifecycle.GA_CREW_ACP_BACKEND = "claude"
                with self.assertLogs("transport.lifecycle", level="WARNING") as log_ctx:
                    _lifecycle._finish_crew_setup(
                        podman, "test-crew", "gs-test-crew",
                        "gs-vol-test", "gs-home-test",
                        None,
                        admiral_secret="a" * 64,
                    )
        finally:
            _lifecycle.GA_CREW_ACP_BACKEND = original_backend

        self.assertTrue(
            any("api.anthropic.com" in msg for msg in log_ctx.output),
            f"Expected WARNING mentioning api.anthropic.com, got: {log_ctx.output}",
        )


# ── 6.4 crews() response includes acp_backend ─────────────────────────────────


class TestCrewsResponseAcpBackend(unittest.TestCase):
    """crews() MCP tool response includes acp_backend per entry."""

    def _crews_result(self, crew_entry: dict) -> list[dict]:
        """Run server.crews() with a single fake registry entry and return the result."""
        reg = {"crews": {"test-crew": crew_entry}}
        with (
            patch.object(_server, "_load_registry", return_value=reg),
            patch.object(_server, "_get_podman", return_value=None),
        ):
            result = _server.crews()
        return result.get("crews", [])

    def test_acp_backend_present_for_claude_entry(self) -> None:
        """A registry entry with acp_backend='claude' surfaces it in crews()."""
        entry = {
            "container": "gs-test",
            "status": "stopped",
            "acp_backend": "claude",
            "composition": "spec-ops",
        }
        crews = self._crews_result(entry)
        self.assertEqual(len(crews), 1)
        self.assertEqual(crews[0]["acp_backend"], "claude")

    def test_acp_backend_defaults_to_kiro_for_legacy_entries(self) -> None:
        """Registry entries without acp_backend (pre-TRN-167) default to 'kiro'."""
        entry = {
            "container": "gs-legacy",
            "status": "stopped",
            # no acp_backend field — pre-TRN-167 entry
        }
        crews = self._crews_result(entry)
        self.assertEqual(len(crews), 1)
        self.assertEqual(crews[0]["acp_backend"], "kiro")

    def test_acp_backend_kiro_for_kiro_entry(self) -> None:
        """A registry entry with acp_backend='kiro' surfaces it correctly."""
        entry = {
            "container": "gs-kiro",
            "status": "stopped",
            "acp_backend": "kiro",
        }
        crews = self._crews_result(entry)
        self.assertEqual(crews[0]["acp_backend"], "kiro")


if __name__ == "__main__":
    unittest.main()
