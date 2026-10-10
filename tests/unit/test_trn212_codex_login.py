"""Direct unit tests for ``_initiate_codex_login`` (trn-212-test-coverage-gaps B).

The proposal's finding: every server-level Codex test patches the poll, which
hid a false-completion bug. These tests exercise ``_initiate_codex_login``'s own
logic — the TOCTOU guard, the codex-acp binary-probe loop, the real PTY read via
``_run_pty_login_flow`` over a socketpair, the timeout path, and the
container-start failure path — mocking only Podman lifecycle and the PTY exec.

Pattern mirrors ``test_pty_login_sequences.py`` (socketpair + writer thread,
joined with a finite timeout). See design.md D2.
"""

from __future__ import annotations

import socket
import threading
import time
import unittest
from unittest.mock import Mock, patch

from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)


def _reset_pending() -> None:
    """Clear module-global login state so tests do not leak into one another."""
    _lifecycle._codex_login_pending = None


class _CodexLoginBase(unittest.TestCase):
    def setUp(self) -> None:
        _reset_pending()
        self.addCleanup(_reset_pending)
        # Stop/remove are no-ops; container name must carry the codex prefix so
        # _nuke_codex_login_container does not refuse it.
        self.container = f"{_lifecycle.GA_CODEX_LOGIN_CONTAINER_PREFIX}deadbeef"


class TestCodexLoginTOCTOUGuard(_CodexLoginBase):
    """B.1 — the login-pending sentinel serialises concurrent callers."""

    def test_concurrent_call_while_in_flight_returns_login_pending(self) -> None:
        # Inject an in-flight state as if a first call were mid-flow.
        with patch.object(_lifecycle, "_codex_login_pending", {"state": "starting"}):
            result = _lifecycle._initiate_codex_login(Mock())
        self.assertEqual(result, {"login_pending": True})

    def test_first_call_sets_pending_then_succeeds(self) -> None:
        podman = Mock()
        podman.container_exec.return_value = "/usr/local/bin/codex-acp"

        helper_end, writer_end = socket.socketpair()

        def writer() -> None:
            try:
                time.sleep(0.05)
                writer_end.sendall(
                    b"Login URL: https://auth.openai.com/oauth?user_code=ABCD\n"
                )
            finally:
                writer_end.close()

        t = threading.Thread(target=writer, daemon=True)

        with patch.object(_lifecycle, "_start_codex_login_container", return_value=self.container), \
             patch.object(podman, "container_exec_pty_stdin", return_value=("exec-1", helper_end)):
            t.start()
            try:
                result = _lifecycle._initiate_codex_login(podman)
            finally:
                t.join(timeout=5)
                self.assertFalse(t.is_alive(), "writer thread did not join within 5s")

        self.assertIn("login_url", result)
        self.assertEqual(result["login_url"], "https://auth.openai.com/oauth?user_code=ABCD")
        self.assertEqual(result.get("code"), "ABCD")
        # Sentinel kept the "started" container recorded (flow left running).
        self.assertIsNotNone(_lifecycle._codex_login_pending)
        self.assertEqual(_lifecycle._codex_login_pending["container"], self.container)


class TestCodexBinaryProbe(_CodexLoginBase):
    """B.2 — the codex-acp binary-probe loop."""

    def test_binary_absent_after_probes_errors_and_nukes(self) -> None:
        podman = Mock()
        podman.container_exec.return_value = ""  # which codex-acp -> nothing

        nuke = Mock()
        with patch.object(_lifecycle, "_start_codex_login_container", return_value=self.container), \
             patch.object(_lifecycle, "_nuke_codex_login_container", nuke), \
             patch.object(_lifecycle.time, "sleep", lambda *_a, **_k: None):
            result = _lifecycle._initiate_codex_login(podman)

        self.assertIn("error", result)
        self.assertIn("codex-acp", result["error"])
        self.assertIn("not found", result["error"])
        nuke.assert_called_once_with(podman, self.container)
        self.assertIsNone(_lifecycle._codex_login_pending)

    def test_binary_found_first_probe_proceeds_to_pty(self) -> None:
        podman = Mock()
        podman.container_exec.return_value = "/usr/local/bin/codex-acp"

        helper_end, writer_end = socket.socketpair()

        def writer() -> None:
            try:
                writer_end.sendall(
                    b"Open this URL: https://auth.openai.com/oauth?user_code=WXYZ\n"
                )
            finally:
                writer_end.close()

        t = threading.Thread(target=writer, daemon=True)
        pty_stub = Mock(return_value=("exec-1", helper_end))

        with patch.object(_lifecycle, "_start_codex_login_container", return_value=self.container), \
             patch.object(podman, "container_exec_pty_stdin", pty_stub):
            t.start()
            try:
                result = _lifecycle._initiate_codex_login(podman)
            finally:
                t.join(timeout=5)

        # Reached the PTY exec with the codex-acp login command.
        pty_stub.assert_called_once()
        self.assertEqual(pty_stub.call_args.args[1], ["codex-acp", "login"])
        self.assertEqual(result.get("login_url"),
                         "https://auth.openai.com/oauth?user_code=WXYZ")


class TestCodexPtyUrlExtraction(_CodexLoginBase):
    """B.3 — the real PTY helper extracts URL + code from socketpair output."""

    def test_url_and_code_extracted_from_pty(self) -> None:
        podman = Mock()
        podman.container_exec.return_value = "/usr/local/bin/codex-acp"

        helper_end, writer_end = socket.socketpair()
        closed = threading.Event()

        def writer() -> None:
            try:
                writer_end.sendall(
                    b"Login URL: https://auth.openai.com/oauth?user_code=ABCD\n"
                )
                # Keep the socket open briefly so the drain thread reads EOF
                # only after the helper has returned the URL.
                time.sleep(0.1)
            finally:
                writer_end.close()
                closed.set()

        t = threading.Thread(target=writer, daemon=True)

        with patch.object(_lifecycle, "_start_codex_login_container", return_value=self.container), \
             patch.object(podman, "container_exec_pty_stdin", return_value=("exec-1", helper_end)):
            t.start()
            try:
                result = _lifecycle._initiate_codex_login(podman)
            finally:
                joined = t.join(timeout=5) or (not t.is_alive())
                self.assertTrue(joined, "writer thread did not join within 5s")

        self.assertEqual(result["login_url"],
                         "https://auth.openai.com/oauth?user_code=ABCD")
        self.assertEqual(result["code"], "ABCD")


class TestCodexPtyTimeout(_CodexLoginBase):
    """B.4 — no URL within the deadline → error + container nuked."""

    def test_no_url_times_out_and_nukes(self) -> None:
        podman = Mock()
        podman.container_exec.return_value = "/usr/local/bin/codex-acp"

        helper_end, writer_end = socket.socketpair()

        def writer() -> None:
            # Send noise but never a URL; close after the (short) deadline.
            try:
                writer_end.sendall(b"starting login...\n")
                time.sleep(0.4)
            finally:
                writer_end.close()

        t = threading.Thread(target=writer, daemon=True)
        nuke = Mock()

        # Force the 45 s deadline down to 0.2 s by wrapping the real helper.
        real_flow = _lifecycle._run_pty_login_flow

        def short_flow(*args, **kwargs):
            kwargs["deadline_secs"] = 0.2
            return real_flow(*args, **kwargs)

        with patch.object(_lifecycle, "_start_codex_login_container", return_value=self.container), \
             patch.object(_lifecycle, "_nuke_codex_login_container", nuke), \
             patch.object(_lifecycle, "_run_pty_login_flow", short_flow), \
             patch.object(podman, "container_exec_pty_stdin", return_value=("exec-1", helper_end)):
            t.start()
            try:
                result = _lifecycle._initiate_codex_login(podman)
            finally:
                t.join(timeout=5)

        self.assertIn("error", result)
        self.assertIn("did not produce a login URL", result["error"])
        nuke.assert_called_once_with(podman, self.container)
        self.assertIsNone(_lifecycle._codex_login_pending)


class TestCodexContainerStartFailure(_CodexLoginBase):
    """B.5 — container start raises → pending reset to None, error returned."""

    def test_start_failure_resets_pending(self) -> None:
        podman = Mock()

        def boom(_podman):
            raise RuntimeError("could not create codex login container")

        with patch.object(_lifecycle, "_start_codex_login_container", side_effect=boom):
            result = _lifecycle._initiate_codex_login(podman)

        self.assertIn("error", result)
        self.assertIn("could not create codex login container", result["error"])
        self.assertIsNone(_lifecycle._codex_login_pending)


if __name__ == "__main__":
    unittest.main()
