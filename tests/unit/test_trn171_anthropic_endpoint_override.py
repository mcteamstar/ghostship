"""Unit tests for TRN-171: Anthropic endpoint override.

Covers:
- 4.1 GA_CREW_ANTHROPIC_BASE_URL set with Claude backend →
      ANTHROPIC_BASE_URL present in container_env passed to container_create.
- 4.2 GA_CREW_ANTHROPIC_BASE_URL unset with Claude backend →
      ANTHROPIC_BASE_URL absent from container_env.
- 4.3 GA_CREW_ANTHROPIC_BASE_URL set with kiro backend →
      ANTHROPIC_BASE_URL absent from container_env (kiro is unaffected).
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


if __name__ == "__main__":
    unittest.main()
