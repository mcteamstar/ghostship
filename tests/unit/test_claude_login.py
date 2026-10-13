"""Unit tests for the Claude OAuth login lifecycle (trn-236 task 2.1).

Covers:
- _start_claude_login_container: starts container and probes for 'claude' binary.
- _initiate_claude_login: extracts URL from PTY output (happy path).
- _initiate_claude_login: times out when no URL appears and nukes container.
- _nuke_claude_login_container: removes the container; refuses non-login names.

Mirrors the structure of ``tests/unit/test_trn212_codex_login.py`` as directed
by design D5.  ``container_exec_pty_stdin`` is mocked for PTY interaction.
"""

from __future__ import annotations

import socket
import threading
import time
import unittest
from unittest.mock import Mock, patch

# ── Install stubs FIRST — before ANY transport import ────────────────────────
from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)


def _reset_claude_pending() -> None:
    """Clear module-global Claude login state between tests."""
    with _lifecycle._claude_login_pending_lock:
        _lifecycle._claude_login_pending = None


class _ClaudeLoginBase(unittest.TestCase):
    def setUp(self) -> None:
        _reset_claude_pending()
        self.addCleanup(_reset_claude_pending)
        # Container name must carry the Claude-login prefix so nuke accepts it.
        self.container = f"{_lifecycle.GA_CLAUDE_LOGIN_CONTAINER_PREFIX}deadbeef"


# ── _start_claude_login_container ────────────────────────────────────────────


class TestStartClaudeLoginContainer(_ClaudeLoginBase):
    """_start_claude_login_container creates and starts the ephemeral container."""

    def test_container_created_and_started(self) -> None:
        podman = Mock()
        podman.network_create = Mock()
        podman.container_start = Mock()
        podman._req = Mock(return_value={"Id": "dummy-exec-id"})

        name = _lifecycle._start_claude_login_container(podman)

        # Should have called network_create and container_start.
        podman.network_create.assert_called_once()
        podman.container_start.assert_called_once_with(name)
        # Name must carry the Claude login prefix.
        self.assertTrue(
            name.startswith(_lifecycle.GA_CLAUDE_LOGIN_CONTAINER_PREFIX),
            f"Unexpected container name: {name!r}",
        )

    def test_container_create_failure_raises(self) -> None:
        podman = Mock()
        podman.network_create = Mock()
        podman._req = Mock(side_effect=RuntimeError("image not found"))

        with self.assertRaises(RuntimeError) as ctx:
            _lifecycle._start_claude_login_container(podman)

        self.assertIn("image not found", str(ctx.exception))


# ── _nuke_claude_login_container ─────────────────────────────────────────────


class TestNukeClaudeLoginContainer(_ClaudeLoginBase):
    """_nuke_claude_login_container removes the container; refuses wrong names."""

    def test_stop_and_remove_called(self) -> None:
        podman = Mock()
        podman.container_stop = Mock()
        podman.container_remove = Mock()

        _lifecycle._nuke_claude_login_container(podman, self.container)

        podman.container_stop.assert_called_once_with(self.container)
        podman.container_remove.assert_called_once_with(self.container)

    def test_stop_error_swallowed(self) -> None:
        """Stop errors are swallowed so remove still runs."""
        podman = Mock()
        podman.container_stop = Mock(side_effect=RuntimeError("already stopped"))
        podman.container_remove = Mock()

        # Must not raise.
        _lifecycle._nuke_claude_login_container(podman, self.container)

        podman.container_remove.assert_called_once_with(self.container)

    def test_refuses_non_login_container(self) -> None:
        podman = Mock()
        with self.assertRaises(RuntimeError) as ctx:
            _lifecycle._nuke_claude_login_container(podman, "gs-crew-abc")
        self.assertIn("Refusing", str(ctx.exception))


# ── _initiate_claude_login — happy path ──────────────────────────────────────


class TestInitiateClaudeLoginHappyPath(_ClaudeLoginBase):
    """URL extracted from PTY output → login_url returned."""

    def test_url_extracted_from_pty_output(self) -> None:
        podman = Mock()
        # 'which claude' probe succeeds.
        podman.container_exec = Mock(return_value="/usr/local/bin/claude")

        helper_end, writer_end = socket.socketpair()

        def writer() -> None:
            try:
                time.sleep(0.05)
                writer_end.sendall(
                    b"Please open the following URL in your browser:\n"
                    b"https://console.anthropic.com/auth/login?code=TESTCODE\n"
                )
                time.sleep(0.2)
            finally:
                writer_end.close()

        t = threading.Thread(target=writer, daemon=True)

        with (
            patch.object(_lifecycle, "_start_claude_login_container",
                         return_value=self.container),
            patch.object(podman, "container_exec_pty_stdin",
                         return_value=("exec-1", helper_end, b"")),
        ):
            t.start()
            try:
                result = _lifecycle._initiate_claude_login(podman)
            finally:
                t.join(timeout=5)
                self.assertFalse(t.is_alive(), "writer thread did not join within 5s")

        self.assertIn("login_url", result,
                      f"Expected login_url in result: {result}")
        self.assertIn("anthropic.com", result["login_url"])

    def test_container_name_stored_in_pending(self) -> None:
        """After a successful flow, _claude_login_pending records the container."""
        podman = Mock()
        podman.container_exec = Mock(return_value="/usr/local/bin/claude")

        helper_end, writer_end = socket.socketpair()

        def writer() -> None:
            try:
                writer_end.sendall(
                    b"https://claude.ai/auth/login?token=abc123\n"
                )
                time.sleep(0.2)
            finally:
                writer_end.close()

        t = threading.Thread(target=writer, daemon=True)

        with (
            patch.object(_lifecycle, "_start_claude_login_container",
                         return_value=self.container),
            patch.object(podman, "container_exec_pty_stdin",
                         return_value=("exec-2", helper_end, b"")),
        ):
            t.start()
            try:
                _lifecycle._initiate_claude_login(podman)
            finally:
                t.join(timeout=5)

        with _lifecycle._claude_login_pending_lock:
            pending = _lifecycle._claude_login_pending

        self.assertIsNotNone(pending)
        self.assertEqual(pending["container"], self.container)


# ── _initiate_claude_login — timeout path ────────────────────────────────────


class TestInitiateClaudeLoginTimeout(_ClaudeLoginBase):
    """No URL within deadline → error returned, container nuked."""

    def test_timeout_returns_error_and_nukes(self) -> None:
        podman = Mock()
        podman.container_exec = Mock(return_value="/usr/local/bin/claude")

        helper_end, writer_end = socket.socketpair()

        def writer() -> None:
            try:
                writer_end.sendall(b"starting login...\n")
                time.sleep(0.5)
            finally:
                writer_end.close()

        t = threading.Thread(target=writer, daemon=True)
        nuke = Mock()

        real_flow = _lifecycle._run_pty_login_flow

        def short_flow(*args, **kwargs):
            kwargs["deadline_secs"] = 0.2
            return real_flow(*args, **kwargs)

        with (
            patch.object(_lifecycle, "_start_claude_login_container",
                         return_value=self.container),
            patch.object(_lifecycle, "_nuke_claude_login_container", nuke),
            patch.object(_lifecycle, "_run_pty_login_flow", short_flow),
            patch.object(podman, "container_exec_pty_stdin",
                         return_value=("exec-3", helper_end, b"")),
        ):
            t.start()
            try:
                result = _lifecycle._initiate_claude_login(podman)
            finally:
                t.join(timeout=5)

        self.assertIn("error", result)
        self.assertIn("did not produce a login URL", result["error"])
        nuke.assert_called_once_with(podman, self.container)

        with _lifecycle._claude_login_pending_lock:
            self.assertIsNone(_lifecycle._claude_login_pending)

    def test_timeout_clears_pending_state(self) -> None:
        """Pending state is None after a timeout, not left in 'started'."""
        podman = Mock()
        podman.container_exec = Mock(return_value="/usr/local/bin/claude")

        helper_end, writer_end = socket.socketpair()

        def writer() -> None:
            try:
                time.sleep(0.4)
            finally:
                writer_end.close()

        t = threading.Thread(target=writer, daemon=True)

        real_flow = _lifecycle._run_pty_login_flow

        def short_flow(*args, **kwargs):
            kwargs["deadline_secs"] = 0.1
            return real_flow(*args, **kwargs)

        with (
            patch.object(_lifecycle, "_start_claude_login_container",
                         return_value=self.container),
            patch.object(_lifecycle, "_nuke_claude_login_container", Mock()),
            patch.object(_lifecycle, "_run_pty_login_flow", short_flow),
            patch.object(podman, "container_exec_pty_stdin",
                         return_value=("exec-4", helper_end, b"")),
        ):
            t.start()
            try:
                _lifecycle._initiate_claude_login(podman)
            finally:
                t.join(timeout=5)

        with _lifecycle._claude_login_pending_lock:
            self.assertIsNone(_lifecycle._claude_login_pending)


# ── _initiate_claude_login — container start failure ─────────────────────────


class TestInitiateClaudeLoginContainerFailure(_ClaudeLoginBase):
    """Container start raises → pending reset, error returned."""

    def test_start_failure_resets_pending_and_returns_error(self) -> None:
        podman = Mock()

        def boom(_podman):
            raise RuntimeError("image not found in registry")

        with patch.object(_lifecycle, "_start_claude_login_container",
                          side_effect=boom):
            result = _lifecycle._initiate_claude_login(podman)

        self.assertIn("error", result)
        self.assertIn("image not found in registry", result["error"])

        with _lifecycle._claude_login_pending_lock:
            self.assertIsNone(_lifecycle._claude_login_pending)


# ── _initiate_claude_login — binary probe failure ─────────────────────────────


class TestInitiateClaudeLoginBinaryMissing(_ClaudeLoginBase):
    """'claude' binary not found after retries → container nuked, error returned."""

    def test_binary_absent_errors_and_nukes(self) -> None:
        podman = Mock()
        # All probe calls return empty string → binary not found.
        podman.container_exec = Mock(return_value="")

        nuke = Mock()

        with (
            patch.object(_lifecycle, "_start_claude_login_container",
                         return_value=self.container),
            patch.object(_lifecycle, "_nuke_claude_login_container", nuke),
            patch.object(_lifecycle.time, "sleep", lambda *_a, **_k: None),
        ):
            result = _lifecycle._initiate_claude_login(podman)

        self.assertIn("error", result)
        self.assertIn("claude", result["error"].lower())
        nuke.assert_called_once_with(podman, self.container)

        with _lifecycle._claude_login_pending_lock:
            self.assertIsNone(_lifecycle._claude_login_pending)


# ── _initiate_claude_login — concurrent call guard ───────────────────────────


class TestInitiateClaudeLoginConcurrentGuard(_ClaudeLoginBase):
    """TOCTOU guard: concurrent call while flow in flight returns login_pending."""

    def test_concurrent_call_returns_login_pending(self) -> None:
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": self.container,
                "state": "started",
                "started_at": time.time(),
            }

        result = _lifecycle._initiate_claude_login(Mock())
        self.assertEqual(result, {"login_pending": True})


if __name__ == "__main__":
    unittest.main()
