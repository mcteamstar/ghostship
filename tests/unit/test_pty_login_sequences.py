"""Unit tests for trn-202-claude-backend-fixes task 2: terminal-sequence handling in the
shared PTY login helper (_run_pty_login_flow).

Covers:
- 2.2 A URL wrapped in OSC-8 hyperlink and colour sequences is returned clean,
      including when a sequence is split across two reads.
- 2.3 The kiro login URL extraction returns the same value as before the change
      for plain kiro output.
"""

from __future__ import annotations

import re
import socket
import threading
import time
import unittest

from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)

CLAUDE_URL = (
    "https://claude.com/cai/oauth/authorize?code=true&client_id=abc"
    "&response_type=code&state=XYZ123"
)

# Patterns as used by _initiate_claude_login.
CLAUDE_URL_PATTERNS = [
    re.compile(r"https?://(?:claude\.ai|console\.anthropic\.com|auth\.anthropic\.com)\S*"),
    re.compile(r"(?:URL|browser)[:\s]+(https?://\S+)", re.IGNORECASE),
    re.compile(r"(https?://\S{20,})"),
]

# Patterns as used by _initiate_login (kiro).
KIRO_URL_PATTERNS = [
    re.compile(r"Open this URL[:\s]+(https?://\S+)"),
    re.compile(r"(https?://\S+user_code=\S+)"),
]


def _run_with_chunks(chunks, url_patterns, delay=0.15):
    """Feed PTY output chunks through the real helper over a socket pair.

    The helper reads one end; a writer thread sends the chunks from the other
    end with a delay between them, so a sequence can be split across reads.
    """
    helper_end, writer_end = socket.socketpair()
    helper_end.setblocking(False)

    def writer():
        try:
            for chunk in chunks:
                writer_end.sendall(chunk)
                time.sleep(delay)
        finally:
            writer_end.close()

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    try:
        url, _ = _lifecycle._run_pty_login_flow(
            pty_sock=helper_end,
            prompt_patterns=[],
            url_patterns=url_patterns,
            code_pattern=None,
            deadline_secs=5.0,
        )
    finally:
        t.join(timeout=5)
        try:
            helper_end.close()
        except OSError:
            pass
    return url


class TestStripTerminalSequences(unittest.TestCase):
    def test_removes_osc8_colour_and_bel(self):
        raw = "\x1b[94m\x1b]8;;https://x.example/a\x07https://x.example/a\x1b]8;;\x07\x1b[39m\x07"
        self.assertEqual(
            _lifecycle._strip_terminal_sequences(raw),
            "https://x.example/a",
        )

    def test_plain_text_is_unchanged(self):
        plain = "Open this URL: https://example.com/?user_code=ABCD-1234\r\n"
        self.assertEqual(_lifecycle._strip_terminal_sequences(plain), plain)


class TestClaudeUrlExtraction(unittest.TestCase):
    """2.2: the returned URL is clean."""

    def test_url_wrapped_in_osc8_and_colour_is_returned_clean(self):
        # Shape of the transport's captured output: colour codes around an
        # OSC-8 hyperlink whose visible text is the same URL.
        out = (
            "If the browser didn't open, visit: "
            f"\x1b]8;;{CLAUDE_URL}\x07\x1b[94m{CLAUDE_URL}\x1b[39m\x1b]8;;\x07\r\n"
            "Paste code here if prompted > "
        ).encode()
        url = _run_with_chunks([out], CLAUDE_URL_PATTERNS, delay=0)
        self.assertEqual(url, CLAUDE_URL)

    def test_sequence_split_across_reads_is_returned_clean(self):
        # The OSC-8 open sequence arrives in two reads, split inside the URL.
        cut = len(CLAUDE_URL) // 2
        first = f"visit: \x1b]8;;{CLAUDE_URL[:cut]}".encode()
        second = (
            f"{CLAUDE_URL[cut:]}\x07{CLAUDE_URL}\x1b]8;;\x07\r\n"
            "Paste code here if prompted > "
        ).encode()
        url = _run_with_chunks([first, second], CLAUDE_URL_PATTERNS)
        self.assertEqual(url, CLAUDE_URL)

    def test_url_not_returned_truncated_while_osc_is_open(self):
        # Without the open-sequence guard, the first read would return a
        # truncated URL. The helper must wait for the terminator.
        cut = len(CLAUDE_URL) - 6
        first = f"\x1b]8;;{CLAUDE_URL[:cut]}".encode()
        second = f"{CLAUDE_URL[cut:]}\x07{CLAUDE_URL}\x1b]8;;\x07\r\n".encode()
        url = _run_with_chunks([first, second], CLAUDE_URL_PATTERNS)
        self.assertEqual(url, CLAUDE_URL)


class TestKiroUrlExtractionUnchanged(unittest.TestCase):
    """2.3: kiro login extraction returns the same value as before the change."""

    FIXTURE = (
        "Open this URL: https://device.sso.ap-southeast-2.amazonaws.com/"
        "?user_code=ABCD-EFGH\r\nEnter the code shown in your browser.\r\n"
    )
    EXPECTED = (
        "https://device.sso.ap-southeast-2.amazonaws.com/?user_code=ABCD-EFGH"
    )

    def test_plain_kiro_output_extracts_same_url(self):
        url = _run_with_chunks([self.FIXTURE.encode()], KIRO_URL_PATTERNS, delay=0)
        self.assertEqual(url, self.EXPECTED)

    def test_stripping_is_a_no_op_on_kiro_fixture(self):
        self.assertEqual(
            _lifecycle._strip_terminal_sequences(self.FIXTURE), self.FIXTURE
        )


if __name__ == "__main__":
    unittest.main()
