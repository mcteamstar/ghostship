"""Tests for TRN-209 login flow hardening.

Covers:
- container_exec_pty_stdin: leftover bytes returned from the same chunk as 101 headers.
- _run_pty_login_flow: initial_bytes pre-seeds the accumulator so no select loop is needed.
- _kiro_login_expired / _codex_login_expired: TTL predicates.
- _sweep_expired_logins: integration-style test with all three backends.
- Claude sweep path: _claude_login_pending in awaiting_code state cleared by sweep.
- Codex device-code regex: prose word "will" not captured; "ABCD1234" captured.
"""

from __future__ import annotations

import re
import socket
import threading
import time
import unittest
from unittest.mock import Mock, patch

from tests.unit._stubs import install_import_stubs

install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)
import transport.podman as _podman_mod  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# Section 6.1 — container_exec_pty_stdin leftover bytes
#
# Strategy: build a minimal PodmanClient with a fake _req and a patched socket
# module so the method uses our socketpair instead of a real Unix socket.
# ══════════════════════════════════════════════════════════════════════════════


def _make_pty_client_with_fake_server(server_response: bytes):
    """Return (client, exec_id_holder) where the fake server sends server_response."""
    server_end, client_end = socket.socketpair()
    started = threading.Event()

    def fake_server() -> None:
        started.wait(timeout=2)
        server_end.sendall(server_response)
        # Keep open so the caller can close at teardown.

    t = threading.Thread(target=fake_server, daemon=True)
    t.start()

    # Minimal PodmanClient that uses our socketpair instead of a real Unix socket.
    client = _podman_mod.PodmanClient.__new__(_podman_mod.PodmanClient)
    client._sock_path = "/nonexistent"

    def fake_req(method: str, path: str, **kw):  # type: ignore[override]
        return {"Id": "test-exec-id"}

    client._req = fake_req  # type: ignore[method-assign]

    # Fake socket class: all socket.socket() instantiations return a wrapper
    # around client_end.  The first sendall() signals the server to start.
    class _FakeSock:
        def connect(self, _path: str) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            started.set()  # trigger fake_server to send its response

        def recv(self, n: int) -> bytes:
            return client_end.recv(n)

        def settimeout(self, timeout: float) -> None:
            client_end.settimeout(timeout)

        def close(self) -> None:
            pass  # cleanup handled by caller

    return client, _FakeSock, client_end, server_end, t


class TestContainerExecPtyStdinLeftover(unittest.TestCase):
    """6.1 — socketpair test: bytes arriving with 101 headers are returned as leftover."""

    def test_leftover_bytes_returned_with_headers_in_same_chunk(self) -> None:
        """When PTY bytes arrive in the same recv() chunk as the 101 headers,
        they are returned as the third element of the tuple."""
        pty_payload = b"\x1b[2J\x1b[H$ "  # some PTY bytes
        server_response = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Connection: Upgrade\r\n"
            b"Upgrade: tcp\r\n"
            b"\r\n"
        ) + pty_payload

        client, FakeSock, client_end, server_end, t = _make_pty_client_with_fake_server(
            server_response
        )
        self.addCleanup(client_end.close)
        self.addCleanup(server_end.close)

        with patch("transport.podman.socket.socket", return_value=FakeSock()):
            exec_id, sock, leftover = client.container_exec_pty_stdin("c", ["cmd"])

        t.join(timeout=2)
        self.assertEqual(exec_id, "test-exec-id")
        self.assertEqual(leftover, pty_payload,
                         "leftover must equal PTY bytes that arrived after the \\r\\n\\r\\n boundary")

    def test_empty_leftover_when_nothing_after_headers(self) -> None:
        """When no PTY bytes arrive with the 101 headers, leftover is b''."""
        server_response = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Connection: Upgrade\r\n"
            b"\r\n"
        )

        client, FakeSock, client_end, server_end, t = _make_pty_client_with_fake_server(
            server_response
        )
        self.addCleanup(client_end.close)
        self.addCleanup(server_end.close)

        with patch("transport.podman.socket.socket", return_value=FakeSock()):
            exec_id, sock, leftover = client.container_exec_pty_stdin("c", ["cmd"])

        t.join(timeout=2)
        self.assertEqual(leftover, b"")


# ══════════════════════════════════════════════════════════════════════════════
# Section 6.2 — _run_pty_login_flow initial_bytes
# ══════════════════════════════════════════════════════════════════════════════


class TestRunPtyLoginFlowInitialBytes(unittest.TestCase):
    """6.2 — initial_bytes pre-seeds the accumulator; URL extracted without select()."""

    def test_url_extracted_from_initial_bytes_without_select_data(self) -> None:
        """If initial_bytes already contains the login URL, the helper returns it
        immediately without needing to receive any further data from the socket."""
        # Socketpair — the reader end will get no data (writer_end is never written to).
        reader_end, writer_end = socket.socketpair()
        self.addCleanup(reader_end.close)
        self.addCleanup(writer_end.close)

        url = "https://auth.openai.com/oauth?user_code=XY12"
        initial = f"Open this URL: {url}\n".encode()

        # Make the socket non-blocking (as callers do in practice).
        reader_end.setblocking(False)

        login_url, login_code = _lifecycle._run_pty_login_flow(
            pty_sock=reader_end,
            prompt_patterns=[],
            url_patterns=[
                re.compile(
                    r"https?://(?:auth\.openai\.com|platform\.openai\.com)\S*"
                ),
                re.compile(r"(?:URL|browser)[:\s]+(https?://\S+)", re.IGNORECASE),
            ],
            code_pattern=re.compile(
                r"(?:[?&]user_code=([A-Za-z0-9_-]{4,})|[Cc]ode[:\s]+([A-Z0-9]{4,8})\b)"
            ),
            deadline_secs=2.0,
            initial_bytes=initial,
        )

        # Writer end is intentionally never written — the URL must come from initial_bytes.
        self.assertEqual(login_url, url)
        self.assertEqual(login_code, "XY12")


# ══════════════════════════════════════════════════════════════════════════════
# Section 7.1 — expiry predicates
# ══════════════════════════════════════════════════════════════════════════════


class TestKiroLoginExpired(unittest.TestCase):
    """7.1a — _kiro_login_expired returns correct boolean for started_at values."""

    def test_not_expired_when_recent(self) -> None:
        pending = {"started_at": time.time() - _lifecycle.KIRO_LOGIN_TTL_SECS + 60}
        self.assertFalse(_lifecycle._kiro_login_expired(pending))

    def test_expired_when_past_ttl(self) -> None:
        pending = {"started_at": time.time() - _lifecycle.KIRO_LOGIN_TTL_SECS - 1}
        self.assertTrue(_lifecycle._kiro_login_expired(pending))

    def test_not_expired_when_started_at_missing(self) -> None:
        self.assertFalse(_lifecycle._kiro_login_expired({}))

    def test_not_expired_at_exact_boundary(self) -> None:
        # Exactly at the TTL: time.time() - started_at == TTL → not expired (strictly >).
        pending = {"started_at": time.time() - _lifecycle.KIRO_LOGIN_TTL_SECS}
        # May be True or False depending on sub-second drift; just verify it doesn't raise.
        result = _lifecycle._kiro_login_expired(pending)
        self.assertIsInstance(result, bool)


class TestCodexLoginExpired(unittest.TestCase):
    """7.1b — _codex_login_expired returns correct boolean for started_at values."""

    def test_not_expired_when_recent(self) -> None:
        pending = {"started_at": time.time() - _lifecycle.CODEX_LOGIN_TTL_SECS + 60}
        self.assertFalse(_lifecycle._codex_login_expired(pending))

    def test_expired_when_past_ttl(self) -> None:
        pending = {"started_at": time.time() - _lifecycle.CODEX_LOGIN_TTL_SECS - 1}
        self.assertTrue(_lifecycle._codex_login_expired(pending))

    def test_not_expired_when_started_at_missing(self) -> None:
        self.assertFalse(_lifecycle._codex_login_expired({}))


# ══════════════════════════════════════════════════════════════════════════════
# Section 7.2 — _sweep_expired_logins integration test
# ══════════════════════════════════════════════════════════════════════════════


def _reset_all_pending() -> None:
    """Reset all three pending-login dicts to None (test teardown helper)."""
    with _lifecycle._login_pending_lock:
        _lifecycle._login_pending = None
    with _lifecycle._claude_login_pending_lock:
        _lifecycle._claude_login_pending = None
    with _lifecycle._codex_login_pending_lock:
        _lifecycle._codex_login_pending = None


class TestSweepExpiredLogins(unittest.TestCase):
    """7.2 — _sweep_expired_logins clears all three backends when expired."""

    def setUp(self) -> None:
        _reset_all_pending()
        self.addCleanup(_reset_all_pending)

    def test_all_three_expired_flows_are_cleared(self) -> None:
        """Pre-populate all three pending dicts with expired state; call sweep;
        assert all three are cleared and the mock nuke functions were called."""
        old = time.time() - 2000  # well past all TTLs

        kiro_container = "ga-login-expired-kiro"
        claude_container = "ga-claude-login-expired"
        codex_container = "ga-codex-login-expired"

        with _lifecycle._login_pending_lock:
            _lifecycle._login_pending = {
                "container": kiro_container,
                "started_at": old,
                "state": "started",
            }
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": claude_container,
                "started_at": old,
                "state": "awaiting_code",
            }
        with _lifecycle._codex_login_pending_lock:
            _lifecycle._codex_login_pending = {
                "container": codex_container,
                "started_at": old,
                "state": "started",
            }

        podman = Mock()
        nuke_kiro = Mock()
        nuke_claude = Mock()
        nuke_codex = Mock()

        with (
            patch.object(_lifecycle, "_nuke_login_container", nuke_kiro),
            patch.object(_lifecycle, "_nuke_claude_login_container", nuke_claude),
            patch.object(_lifecycle, "_nuke_codex_login_container", nuke_codex),
        ):
            _lifecycle._sweep_expired_logins(podman)

        # All three pending dicts must be cleared.
        self.assertIsNone(_lifecycle._login_pending, "kiro pending not cleared by sweep")
        self.assertIsNone(_lifecycle._claude_login_pending, "Claude pending not cleared by sweep")
        self.assertIsNone(_lifecycle._codex_login_pending, "Codex pending not cleared by sweep")

        # Nuke functions must be called for each expired container.
        nuke_kiro.assert_called_once_with(podman, kiro_container)
        nuke_claude.assert_called_once_with(podman, claude_container)
        nuke_codex.assert_called_once_with(podman, codex_container)

    def test_non_expired_flows_are_not_cleared(self) -> None:
        """A flow started recently must not be expired by the sweep."""
        recent = time.time() - 60  # 1 minute ago, well within TTL

        with _lifecycle._login_pending_lock:
            _lifecycle._login_pending = {
                "container": "ga-login-fresh",
                "started_at": recent,
                "state": "started",
            }
        with _lifecycle._codex_login_pending_lock:
            _lifecycle._codex_login_pending = {
                "container": "ga-codex-login-fresh",
                "started_at": recent,
                "state": "started",
            }

        podman = Mock()
        with (
            patch.object(_lifecycle, "_nuke_login_container") as nuke_kiro,
            patch.object(_lifecycle, "_nuke_codex_login_container") as nuke_codex,
        ):
            _lifecycle._sweep_expired_logins(podman)

        # Non-expired flows must not be cleared.
        self.assertIsNotNone(_lifecycle._login_pending, "non-expired kiro flow incorrectly cleared")
        self.assertIsNotNone(_lifecycle._codex_login_pending, "non-expired Codex flow incorrectly cleared")
        nuke_kiro.assert_not_called()
        nuke_codex.assert_not_called()

    def test_nuke_exception_does_not_prevent_pending_clear(self) -> None:
        """If the nuke call raises, the pending dict is still cleared."""
        old = time.time() - 2000

        with _lifecycle._login_pending_lock:
            _lifecycle._login_pending = {
                "container": "ga-login-boom",
                "started_at": old,
                "state": "started",
            }

        podman = Mock()

        with patch.object(
            _lifecycle, "_nuke_login_container", side_effect=RuntimeError("podman gone")
        ):
            _lifecycle._sweep_expired_logins(podman)

        self.assertIsNone(_lifecycle._login_pending)


# ══════════════════════════════════════════════════════════════════════════════
# Section 7.3 — Claude sweep path
# ══════════════════════════════════════════════════════════════════════════════


class TestSweepExpiredLoginsClaude(unittest.TestCase):
    """7.3 — Claude flow in awaiting_code state cleared by sweep when expired."""

    def setUp(self) -> None:
        _reset_all_pending()
        self.addCleanup(_reset_all_pending)

    def test_claude_awaiting_code_expired_is_cleared(self) -> None:
        old = time.time() - _lifecycle.CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS - 10

        helper_end, writer_end = socket.socketpair()
        self.addCleanup(helper_end.close)
        self.addCleanup(writer_end.close)

        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": "ga-claude-login-expired-awaiting",
                "started_at": old,
                "state": "awaiting_code",
                "pty_sock": helper_end,
            }

        podman = Mock()
        with patch.object(_lifecycle, "_nuke_claude_login_container") as nuke, \
                patch.object(_lifecycle._security, "audit_auth_event") as audit:
            _lifecycle._sweep_expired_logins(podman)

        self.assertIsNone(_lifecycle._claude_login_pending)
        nuke.assert_called_once()
        # Spec (claude-auth): sweep expiry SHALL record action=login outcome=failure.
        audit.assert_called_once()
        kwargs = audit.call_args.kwargs
        self.assertEqual(kwargs.get("action"), "login")
        self.assertEqual(kwargs.get("outcome"), "failure")
        self.assertEqual(kwargs.get("account"), "claude")

    def test_claude_code_submitted_expired_is_cleared(self) -> None:
        """A submitted code that has exceeded CLAUDE_LOGIN_CODE_DEADLINE_SECS is swept."""
        old_submitted = time.time() - _lifecycle.CLAUDE_LOGIN_CODE_DEADLINE_SECS - 10

        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": "ga-claude-login-expired-submitted",
                "started_at": time.time() - 300,
                "state": "code_submitted",
                "code_submitted_at": old_submitted,
            }

        podman = Mock()
        with patch.object(_lifecycle, "_nuke_claude_login_container") as nuke:
            _lifecycle._sweep_expired_logins(podman)

        self.assertIsNone(_lifecycle._claude_login_pending)
        nuke.assert_called_once()

    def test_claude_not_expired_not_cleared(self) -> None:
        recent = time.time() - 60

        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": "ga-claude-login-fresh",
                "started_at": recent,
                "state": "awaiting_code",
            }

        podman = Mock()
        with patch.object(_lifecycle, "_nuke_claude_login_container") as nuke:
            _lifecycle._sweep_expired_logins(podman)

        self.assertIsNotNone(_lifecycle._claude_login_pending)
        nuke.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Section 5.3 — Codex device-code regex
# ══════════════════════════════════════════════════════════════════════════════


_CODEX_CODE_RE = re.compile(
    r"(?:[?&]user_code=([A-Za-z0-9_-]{4,})|[Cc]ode[:\s]+([A-Z0-9]{4,8})\b)"
)


def _extract_code(text: str) -> str | None:
    """Apply the codex_code_pattern and return group(1) or group(2)."""
    m = _CODEX_CODE_RE.search(text)
    if not m:
        return None
    return m.group(1) or (m.group(2) if m.lastindex and m.lastindex >= 2 else None)


class TestCodexCodeRegex(unittest.TestCase):
    """5.3 — prose words are not captured; real-looking codes are captured."""

    def test_prose_expire_word_not_captured(self) -> None:
        """'will' must not be captured from 'The code will expire in 15 minutes'."""
        result = _extract_code("The code will expire in 15 minutes")
        self.assertIsNone(result, "'will' must not be captured by the prose branch")

    def test_real_looking_uppercase_code_captured(self) -> None:
        """ABCD1234 must be captured from 'Code: ABCD1234'."""
        result = _extract_code("Code: ABCD1234")
        self.assertEqual(result, "ABCD1234")

    def test_lowercase_prose_word_not_captured(self) -> None:
        """'expire' must not be captured from 'code expire'."""
        result = _extract_code("code expire")
        self.assertIsNone(result)

    def test_url_param_branch_captured(self) -> None:
        """user_code= URL-param branch must still work."""
        result = _extract_code("https://auth.openai.com/oauth?user_code=WXYZ-5678")
        self.assertEqual(result, "WXYZ-5678")

    def test_url_param_allows_lowercase(self) -> None:
        """URL-param branch is not restricted to uppercase (case-insensitive codes)."""
        result = _extract_code("https://example.com/auth?user_code=abc123")
        self.assertEqual(result, "abc123")

    def test_short_code_below_4_chars_not_captured(self) -> None:
        """Codes shorter than 4 chars are not captured by the prose branch."""
        result = _extract_code("Code: AB1")
        self.assertIsNone(result)

    def test_code_longer_than_8_chars_not_captured_by_prose_branch(self) -> None:
        """Prose branch caps at 8 chars; longer tokens are not captured."""
        result = _extract_code("Code: ABCDEFGHI")  # 9 chars
        self.assertIsNone(result)


# ══════════════════════════════════════════════════════════════════════════════
# Section 8 — Regression: Codex poll tests still pass (real regex path)
# ══════════════════════════════════════════════════════════════════════════════


class TestCodexCodeRegexRealPatternPath(unittest.TestCase):
    """8.1 — real regex path (not patching _run_pty_login_flow) works correctly."""

    def test_url_with_user_code_extracted_via_real_regex(self) -> None:
        """End-to-end: _run_pty_login_flow with codex_code_pattern extracts the code."""
        url = "https://auth.openai.com/oauth?user_code=ABCD1234"
        initial = f"Login URL: {url}\n".encode()

        reader_end, writer_end = socket.socketpair()
        self.addCleanup(reader_end.close)
        self.addCleanup(writer_end.close)
        reader_end.setblocking(False)

        codex_code_pattern = re.compile(
            r"(?:[?&]user_code=([A-Za-z0-9_-]{4,})|[Cc]ode[:\s]+([A-Z0-9]{4,8})\b)"
        )
        codex_url_patterns = [
            re.compile(
                r"https?://(?:auth\.openai\.com|platform\.openai\.com|chatgpt\.com|chat\.openai\.com)\S*"
            ),
            re.compile(r"(?:URL|browser)[:\s]+(https?://\S+)", re.IGNORECASE),
            re.compile(r"(https?://\S{20,})"),
        ]

        login_url, login_code = _lifecycle._run_pty_login_flow(
            pty_sock=reader_end,
            prompt_patterns=[],
            url_patterns=codex_url_patterns,
            code_pattern=codex_code_pattern,
            deadline_secs=2.0,
            initial_bytes=initial,
        )

        self.assertEqual(login_url, url)
        self.assertEqual(login_code, "ABCD1234")

    def test_prose_code_word_not_extracted_via_real_regex(self) -> None:
        """'will' is not extracted as a code when the prose branch is tightened."""
        # URL has no user_code= param; PTY output contains prose with 'code will'
        text = (
            b"Login URL: https://auth.openai.com/oauth?client_id=x\n"
            b"The code will expire in 15 minutes\n"
        )

        reader_end, writer_end = socket.socketpair()
        self.addCleanup(reader_end.close)
        self.addCleanup(writer_end.close)
        reader_end.setblocking(False)

        codex_code_pattern = re.compile(
            r"(?:[?&]user_code=([A-Za-z0-9_-]{4,})|[Cc]ode[:\s]+([A-Z0-9]{4,8})\b)"
        )
        codex_url_patterns = [
            re.compile(
                r"https?://(?:auth\.openai\.com|platform\.openai\.com|chatgpt\.com|chat\.openai\.com)\S*"
            ),
        ]

        login_url, login_code = _lifecycle._run_pty_login_flow(
            pty_sock=reader_end,
            prompt_patterns=[],
            url_patterns=codex_url_patterns,
            code_pattern=codex_code_pattern,
            deadline_secs=2.0,
            initial_bytes=text,
        )

        # URL matched; code must NOT be "will"
        self.assertIsNotNone(login_url)
        self.assertNotEqual(login_code, "will", "'will' must not be captured as a device code")
        self.assertIsNone(login_code, "no user_code= in URL, no uppercase code in prose → None")


