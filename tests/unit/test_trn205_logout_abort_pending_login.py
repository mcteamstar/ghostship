"""Tests for TRN-205: POST /logout aborts a pending login flow.

Covers:
- _abort_pending_login / _abort_claude_pending_login / _abort_codex_pending_login
  helper logic (state cleared, container nuked, returns True/False)
- _handle_logout_post / _handle_claude_logout_post / _handle_codex_logout_post
  include aborted_pending_login: true in the response when a flow was in flight
- No regression on the response shape when no flow is pending
"""
from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
import tempfile

from tests.unit.helpers import lifecycle, server  # noqa: F401


class AbortPendingLoginTests(unittest.TestCase):
    """Unit tests for _abort_pending_login() in lifecycle.py."""

    def setUp(self) -> None:
        # Reset state before each test
        with lifecycle._login_pending_lock:
            lifecycle._login_pending = None

    def tearDown(self) -> None:
        with lifecycle._login_pending_lock:
            lifecycle._login_pending = None

    def test_abort_with_active_container_nukes_and_clears(self) -> None:
        """When a login flow is pending with a container, nuke is called and state cleared."""
        podman = Mock()
        with lifecycle._login_pending_lock:
            lifecycle._login_pending = {
                "container": "ga-login-abc123",
                "state": "started",
                "started_at": 0.0,
            }

        with patch.object(lifecycle, "_nuke_login_container") as mock_nuke:
            result = lifecycle._abort_pending_login(podman)

        self.assertTrue(result)
        mock_nuke.assert_called_once_with(podman, "ga-login-abc123")
        with lifecycle._login_pending_lock:
            self.assertIsNone(lifecycle._login_pending)

    def test_abort_with_no_pending_state_is_noop(self) -> None:
        """When nothing is pending, _abort_pending_login returns False without error."""
        podman = Mock()
        with patch.object(lifecycle, "_nuke_login_container") as mock_nuke:
            result = lifecycle._abort_pending_login(podman)

        self.assertFalse(result)
        mock_nuke.assert_not_called()

    def test_abort_with_container_none_does_not_call_nuke(self) -> None:
        """If pending state exists but container is None (still starting), no nuke call."""
        podman = Mock()
        with lifecycle._login_pending_lock:
            lifecycle._login_pending = {
                "container": None,
                "state": "starting",
                "started_at": 0.0,
            }

        with patch.object(lifecycle, "_nuke_login_container") as mock_nuke:
            result = lifecycle._abort_pending_login(podman)

        self.assertTrue(result)
        mock_nuke.assert_not_called()
        with lifecycle._login_pending_lock:
            self.assertIsNone(lifecycle._login_pending)


class AbortClaudePendingLoginTests(unittest.TestCase):
    """Unit tests for _abort_claude_pending_login() in lifecycle.py."""

    def setUp(self) -> None:
        with lifecycle._claude_login_pending_lock:
            lifecycle._claude_login_pending = None

    def tearDown(self) -> None:
        with lifecycle._claude_login_pending_lock:
            lifecycle._claude_login_pending = None

    def test_abort_claude_with_active_container_nukes_and_clears(self) -> None:
        podman = Mock()
        with lifecycle._claude_login_pending_lock:
            lifecycle._claude_login_pending = {
                "container": "ga-claude-login-abc123",
                "state": "started",
                "started_at": 0.0,
            }

        with patch.object(lifecycle, "_nuke_claude_login_container") as mock_nuke:
            result = lifecycle._abort_claude_pending_login(podman)

        self.assertTrue(result)
        mock_nuke.assert_called_once_with(podman, "ga-claude-login-abc123")
        with lifecycle._claude_login_pending_lock:
            self.assertIsNone(lifecycle._claude_login_pending)

    def test_abort_claude_with_no_pending_is_noop(self) -> None:
        podman = Mock()
        with patch.object(lifecycle, "_nuke_claude_login_container") as mock_nuke:
            result = lifecycle._abort_claude_pending_login(podman)

        self.assertFalse(result)
        mock_nuke.assert_not_called()

    def test_abort_claude_closes_pty_sock_if_present(self) -> None:
        """PTY socket is closed when present in the pending state."""
        podman = Mock()
        mock_sock = Mock()
        with lifecycle._claude_login_pending_lock:
            lifecycle._claude_login_pending = {
                "container": "ga-claude-login-abc123",
                "state": "started",
                "started_at": 0.0,
                "pty_sock": mock_sock,
            }

        with patch.object(lifecycle, "_nuke_claude_login_container"):
            lifecycle._abort_claude_pending_login(podman)

        mock_sock.close.assert_called_once()


class AbortCodexPendingLoginTests(unittest.TestCase):
    """Unit tests for _abort_codex_pending_login() in lifecycle.py."""

    def setUp(self) -> None:
        with lifecycle._codex_login_pending_lock:
            lifecycle._codex_login_pending = None

    def tearDown(self) -> None:
        with lifecycle._codex_login_pending_lock:
            lifecycle._codex_login_pending = None

    def test_abort_codex_with_active_container_nukes_and_clears(self) -> None:
        podman = Mock()
        with lifecycle._codex_login_pending_lock:
            lifecycle._codex_login_pending = {
                "container": "ga-codex-login-abc123",
                "state": "started",
                "started_at": 0.0,
            }

        with patch.object(lifecycle, "_nuke_codex_login_container") as mock_nuke:
            result = lifecycle._abort_codex_pending_login(podman)

        self.assertTrue(result)
        mock_nuke.assert_called_once_with(podman, "ga-codex-login-abc123")
        with lifecycle._codex_login_pending_lock:
            self.assertIsNone(lifecycle._codex_login_pending)

    def test_abort_codex_with_no_pending_is_noop(self) -> None:
        podman = Mock()
        with patch.object(lifecycle, "_nuke_codex_login_container") as mock_nuke:
            result = lifecycle._abort_codex_pending_login(podman)

        self.assertFalse(result)
        mock_nuke.assert_not_called()


class LogoutAbortsKiroPendingLoginTests(unittest.TestCase):
    """_handle_logout_post includes aborted_pending_login when a flow is killed."""

    def _run_logout(self, pending_aborted: bool) -> dict:
        registry = {"crews": {}}
        podman = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            auth_path = data_dir / server.GA_AUTH_FILE
            auth_path.write_text("dGVzdA==")
            auth_path.chmod(0o600)

            with (
                patch.object(server, "DATA_DIR", data_dir),
                patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
                patch.object(server, "_get_podman", return_value=podman),
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(
                    server._lifecycle,
                    "_abort_pending_login",
                    return_value=pending_aborted,
                ),
            ):
                request = Mock()
                response = asyncio.run(server._handle_logout_post(request))

        return json.loads(response.body)

    def test_logout_with_pending_login_includes_aborted_flag(self) -> None:
        body = self._run_logout(pending_aborted=True)
        self.assertEqual(body["status"], "logged_out")
        self.assertTrue(body.get("aborted_pending_login"))

    def test_logout_without_pending_login_omits_aborted_flag(self) -> None:
        body = self._run_logout(pending_aborted=False)
        self.assertEqual(body["status"], "logged_out")
        self.assertNotIn("aborted_pending_login", body)


class LogoutAbortsClaudePendingLoginTests(unittest.TestCase):
    """_handle_claude_logout_post includes aborted_pending_login when a flow is killed."""

    def _run_logout(self, pending_aborted: bool) -> dict:
        registry = {"crews": {}}
        podman = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            auth_path = data_dir / "ga-claude-auth"
            auth_path.write_text("dGVzdA==")
            auth_path.chmod(0o600)

            with (
                patch.object(server, "_claude_auth_exists", return_value=True),
                patch.object(server, "_claude_auth_file_path", return_value=auth_path),
                patch.object(server, "_get_podman", return_value=podman),
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(
                    server._lifecycle,
                    "_abort_claude_pending_login",
                    return_value=pending_aborted,
                ),
            ):
                request = Mock()
                response = asyncio.run(server._handle_claude_logout_post(request))

        return json.loads(response.body)

    def test_claude_logout_with_pending_login_includes_aborted_flag(self) -> None:
        body = self._run_logout(pending_aborted=True)
        self.assertEqual(body["status"], "logged_out")
        self.assertTrue(body.get("aborted_pending_login"))

    def test_claude_logout_without_pending_login_omits_aborted_flag(self) -> None:
        body = self._run_logout(pending_aborted=False)
        self.assertEqual(body["status"], "logged_out")
        self.assertNotIn("aborted_pending_login", body)


class LogoutAbortsCodexPendingLoginTests(unittest.TestCase):
    """_handle_codex_logout_post includes aborted_pending_login when a flow is killed."""

    def _run_logout(self, pending_aborted: bool) -> dict:
        registry = {"crews": {}}
        podman = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            auth_path = data_dir / "ga-codex-auth"
            auth_path.write_text("dGVzdA==")
            auth_path.chmod(0o600)

            with (
                patch.object(server, "_codex_auth_exists", return_value=True),
                patch.object(server, "_codex_auth_file_path", return_value=auth_path),
                patch.object(server, "_get_podman", return_value=podman),
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(
                    server._lifecycle,
                    "_abort_codex_pending_login",
                    return_value=pending_aborted,
                ),
            ):
                request = Mock()
                response = asyncio.run(server._handle_codex_logout_post(request))

        return json.loads(response.body)

    def test_codex_logout_with_pending_login_includes_aborted_flag(self) -> None:
        body = self._run_logout(pending_aborted=True)
        self.assertEqual(body["status"], "logged_out")
        self.assertTrue(body.get("aborted_pending_login"))

    def test_codex_logout_without_pending_login_omits_aborted_flag(self) -> None:
        body = self._run_logout(pending_aborted=False)
        self.assertEqual(body["status"], "logged_out")
        self.assertNotIn("aborted_pending_login", body)
