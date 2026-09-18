"""Unit tests for TRN-171: Anthropic endpoint override.

Covers:
- 4.1 GA_CREW_ANTHROPIC_BASE_URL set with Claude backend →
      ANTHROPIC_BASE_URL present in container_env passed to container_create.
- 4.2 GA_CREW_ANTHROPIC_BASE_URL unset with Claude backend →
      ANTHROPIC_BASE_URL absent from container_env.
- 4.3 GA_CREW_ANTHROPIC_BASE_URL set with kiro backend →
      ANTHROPIC_BASE_URL absent from container_env (kiro is unaffected).
- 4.4 Lifecycle WARNING log names effective endpoint:
      api.anthropic.com when GA_CREW_ANTHROPIC_BASE_URL is unset;
      the configured URL when it is set.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from transport.config import Config

# Install stdlib stubs so transport modules load in a dependency-free env.
from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)
import transport.server as _server       # noqa: E402


# ── Helper: drive launch() far enough to capture container_env ────────────────


def _launch_and_capture_env(
    *,
    backend: str,
    anthropic_api_key: str,
    anthropic_base_url: str,
) -> dict:
    """Run server.launch() with the given Claude-backend settings and return the
    container_env dict that would be passed to podman.container_create().

    Stubs out all I/O so the test never touches disk, Podman, or the network.
    """
    captured_env: dict = {}

    def fake_container_create(*args, **kwargs) -> None:
        captured_env.update(kwargs.get("env", {}))

    podman = Mock()
    podman.container_create.side_effect = fake_container_create

    finish_setup = Mock(return_value={"crew_id": "test-crew", "status": "ready"})

    original_backend = _server.GA_CREW_ACP_BACKEND
    original_api_key = _server._GA_CREW_ANTHROPIC_API_KEY
    original_base_url = _server._GA_CREW_ANTHROPIC_BASE_URL
    try:
        _server.GA_CREW_ACP_BACKEND = backend
        _server._GA_CREW_ANTHROPIC_API_KEY = anthropic_api_key
        _server._GA_CREW_ANTHROPIC_BASE_URL = anthropic_base_url

        with (
            patch.object(_server, "KIRO_API_KEY", ""),
            patch.object(_server, "_read_auth_file", return_value=""),
            patch.object(_server, "_get_podman", return_value=podman),
            patch.object(_lifecycle, "_get_podman", return_value=podman),
            patch.object(_server, "_load_registry", return_value={"crews": {}}),
            patch.object(_lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(_server, "_save_registry"),
            patch.object(_lifecycle, "_save_registry"),
            patch.object(_server, "_wait_gateway", return_value=True),
            patch.object(_server, "_finish_crew_setup", finish_setup),
            patch.object(_server, "_write_crew_secret"),
        ):
            _server.launch("test-crew")
    finally:
        _server.GA_CREW_ACP_BACKEND = original_backend
        _server._GA_CREW_ANTHROPIC_API_KEY = original_api_key
        _server._GA_CREW_ANTHROPIC_BASE_URL = original_base_url

    return captured_env


# ── 4.1 Claude backend + base URL set → ANTHROPIC_BASE_URL in container_env ──


class TestAnthropicBaseUrlClaudeBackendSet(unittest.TestCase):
    """4.1: GA_CREW_ANTHROPIC_BASE_URL set with Claude backend → ANTHROPIC_BASE_URL
    present in the container_env passed to container_create."""

    def test_anthropic_base_url_injected_when_set(self) -> None:
        """ANTHROPIC_BASE_URL is present when backend=claude and base URL is set."""
        env = _launch_and_capture_env(
            backend="claude",
            anthropic_api_key="sk-ant-test-key",
            anthropic_base_url="http://localhost:8000/v1",
        )
        self.assertIn(
            "ANTHROPIC_BASE_URL", env,
            "ANTHROPIC_BASE_URL must be present in container_env when "
            "GA_CREW_ACP_BACKEND=claude and GA_CREW_ANTHROPIC_BASE_URL is set",
        )
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://localhost:8000/v1")

    def test_anthropic_api_key_still_injected_alongside_base_url(self) -> None:
        """ANTHROPIC_API_KEY is present alongside ANTHROPIC_BASE_URL."""
        env = _launch_and_capture_env(
            backend="claude",
            anthropic_api_key="sk-ant-test-key",
            anthropic_base_url="http://localhost:8000/v1",
        )
        self.assertIn("ANTHROPIC_API_KEY", env)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "sk-ant-test-key")


# ── 4.2 Claude backend + base URL unset → ANTHROPIC_BASE_URL absent ───────────


class TestAnthropicBaseUrlClaudeBackendUnset(unittest.TestCase):
    """4.2: GA_CREW_ANTHROPIC_BASE_URL unset with Claude backend → ANTHROPIC_BASE_URL
    absent from container_env (default behaviour preserved)."""

    def test_anthropic_base_url_absent_when_unset(self) -> None:
        """ANTHROPIC_BASE_URL is NOT injected when GA_CREW_ANTHROPIC_BASE_URL is empty."""
        env = _launch_and_capture_env(
            backend="claude",
            anthropic_api_key="sk-ant-test-key",
            anthropic_base_url="",
        )
        self.assertNotIn(
            "ANTHROPIC_BASE_URL", env,
            "ANTHROPIC_BASE_URL must NOT appear when GA_CREW_ANTHROPIC_BASE_URL "
            "is unset — default (api.anthropic.com) behaviour must be unchanged",
        )

    def test_anthropic_api_key_still_injected_without_base_url(self) -> None:
        """ANTHROPIC_API_KEY is still injected when base URL is unset."""
        env = _launch_and_capture_env(
            backend="claude",
            anthropic_api_key="sk-ant-test-key",
            anthropic_base_url="",
        )
        self.assertIn("ANTHROPIC_API_KEY", env)


# ── 4.3 kiro backend + base URL set → ANTHROPIC_BASE_URL absent ───────────────


class TestAnthropicBaseUrlKiroBackend(unittest.TestCase):
    """4.3: GA_CREW_ANTHROPIC_BASE_URL set with kiro backend → ANTHROPIC_BASE_URL
    absent from container_env (kiro backend is unaffected by this setting)."""

    def test_anthropic_base_url_absent_for_kiro_backend(self) -> None:
        """ANTHROPIC_BASE_URL is NOT injected for kiro backend even if the var is set."""
        env = _launch_and_capture_env(
            backend="kiro",
            anthropic_api_key="",
            anthropic_base_url="http://localhost:8000/v1",
        )
        self.assertNotIn(
            "ANTHROPIC_BASE_URL", env,
            "ANTHROPIC_BASE_URL must NOT appear for kiro backend — "
            "GA_CREW_ANTHROPIC_BASE_URL has no effect when backend != claude",
        )

    def test_anthropic_api_key_absent_for_kiro_backend(self) -> None:
        """ANTHROPIC_API_KEY is also absent for kiro backend (unchanged behaviour)."""
        env = _launch_and_capture_env(
            backend="kiro",
            anthropic_api_key="",
            anthropic_base_url="http://localhost:8000/v1",
        )
        self.assertNotIn("ANTHROPIC_API_KEY", env)


# ── Config from_env: GA_CREW_ANTHROPIC_BASE_URL binding ───────────────────────


class TestConfigAnthropicBaseUrl(unittest.TestCase):
    """Config.from_env() correctly reads GA_CREW_ANTHROPIC_BASE_URL."""

    def test_base_url_read_from_env(self) -> None:
        """GA_CREW_ANTHROPIC_BASE_URL is read and stripped."""
        with patch.dict("os.environ", {
            "GA_CREW_ANTHROPIC_BASE_URL": "  http://proxy.example.com/v1  ",
            "GA_CREW_ACP_BACKEND": "kiro",
        }):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_crew_anthropic_base_url, "http://proxy.example.com/v1")

    def test_base_url_default_is_empty(self) -> None:
        """GA_CREW_ANTHROPIC_BASE_URL defaults to empty string when unset."""
        import os
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("GA_CREW_ANTHROPIC_BASE_URL",)}
        with patch.dict("os.environ", clean, clear=True):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_crew_anthropic_base_url, "")


# ── 4.4 Lifecycle WARNING names the effective endpoint ────────────────────────


class TestLifecycleWarningEffectiveEndpoint(unittest.TestCase):
    """4.4: _finish_crew_setup WARNING names the effective endpoint.

    Design requirement (design.md D3): "When GA_CREW_ANTHROPIC_BASE_URL is set,
    the warning should name the override instead."
    Delta spec: "The WARNING log entry … SHALL name the effective endpoint:
    api.anthropic.com when GA_CREW_ANTHROPIC_BASE_URL is unset, or the configured
    URL when it is set."
    """

    def _run_finish(self, *, base_url: str) -> list[str]:
        """Drive _finish_crew_setup with claude backend and given base_url.
        Returns the list of WARNING log output strings."""
        import contextlib

        podman = Mock()
        podman.container_exec.return_value = "ready"
        podman.container_exec_checked = Mock(return_value="injected")
        podman.container_inspect.return_value = {
            "Config": {"Labels": {"org.ghostship.version": "test-version"}},
            "State": {"StartedAt": "2026-01-01T00:00:00Z"},
        }

        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(_lifecycle, "_wait_gateway", return_value=True))
        stack.enter_context(patch.object(_lifecycle, "_inject_auth"))
        stack.enter_context(patch.object(_lifecycle, "_patch_crew_config"))
        stack.enter_context(patch.object(_lifecycle, "_copy_agents"))
        stack.enter_context(patch.object(_lifecycle, "_copy_skills"))
        stack.enter_context(patch.object(_lifecycle, "_copy_steering"))
        stack.enter_context(patch.object(_lifecycle, "_seed_openspec_store"))
        stack.enter_context(patch.object(_lifecycle, "_patch_models"))
        stack.enter_context(
            patch.object(_lifecycle, "_mint_cookie", return_value="test-cookie")
        )
        stack.enter_context(
            patch.object(_lifecycle, "_inject_policy", return_value="v1")
        )
        stack.enter_context(
            patch.object(
                _lifecycle, "_load_registry",
                return_value={"crews": {"test-crew": {}}},
            )
        )
        stack.enter_context(patch.object(_lifecycle, "_save_registry"))
        stack.enter_context(patch.object(_lifecycle, "_cleanup_crew"))

        original_backend = _lifecycle.GA_CREW_ACP_BACKEND
        original_base_url = _lifecycle.GA_CREW_ANTHROPIC_BASE_URL
        log_output: list[str] = []
        try:
            _lifecycle.GA_CREW_ACP_BACKEND = "claude"
            _lifecycle.GA_CREW_ANTHROPIC_BASE_URL = base_url
            with stack:
                with self.assertLogs("transport.lifecycle", level="WARNING") as log_ctx:
                    _lifecycle._finish_crew_setup(
                        podman, "test-crew", "gs-test-crew",
                        "gs-vol-test", "gs-home-test",
                        None,
                        admiral_secret="a" * 64,
                    )
            log_output = log_ctx.output
        finally:
            _lifecycle.GA_CREW_ACP_BACKEND = original_backend
            _lifecycle.GA_CREW_ANTHROPIC_BASE_URL = original_base_url
        return log_output

    def test_warning_names_default_endpoint_when_base_url_unset(self) -> None:
        """When GA_CREW_ANTHROPIC_BASE_URL is unset, WARNING names api.anthropic.com."""
        log_output = self._run_finish(base_url="")
        self.assertTrue(
            any("api.anthropic.com" in msg for msg in log_output),
            f"Expected WARNING mentioning api.anthropic.com when base_url is unset, "
            f"got: {log_output}",
        )

    def test_warning_names_override_endpoint_when_base_url_set(self) -> None:
        """When GA_CREW_ANTHROPIC_BASE_URL is set, WARNING names the override URL."""
        override_url = "http://localhost:11434/v1"
        log_output = self._run_finish(base_url=override_url)
        self.assertTrue(
            any(override_url in msg for msg in log_output),
            f"Expected WARNING mentioning '{override_url}' when base_url is set, "
            f"got: {log_output}",
        )
        # The default endpoint must NOT appear when the override is active.
        self.assertFalse(
            any("api.anthropic.com" in msg for msg in log_output),
            f"WARNING must NOT mention api.anthropic.com when the override URL is set, "
            f"got: {log_output}",
        )


if __name__ == "__main__":
    unittest.main()
