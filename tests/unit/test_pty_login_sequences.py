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


# ── trn-212-test-coverage-gaps C: prompt-answer path ─────────────────────────

# Codex-style patterns: answer any "?" prompt with a newline; extract a ChatGPT
# auth URL and a user_code.
CODEX_PROMPT_PATTERNS = [(re.compile(r"\?\s*$"), b"\n")]
CODEX_URL_PATTERNS = [
    re.compile(
        r"https?://(?:auth\.openai\.com|platform\.openai\.com|chatgpt\.com|chat\.openai\.com)\S*"
    ),
    re.compile(r"(?:URL|browser)[:\s]+(https?://\S+)", re.IGNORECASE),
    re.compile(r"(https?://\S{20,})"),
]
CODEX_CODE_PATTERN = re.compile(r"(?:[?&]user_code=|[Cc]ode[:\s]+)([A-Za-z0-9_-]{4,})")

# Generic example-URL patterns for the prompt-answer tests (no vendor lock-in).
EXAMPLE_PROMPT_PATTERNS = [(re.compile(r"\?\s*$"), b"\n")]
EXAMPLE_URL_PATTERNS = [
    re.compile(r"(?:URL|browser)[:\s]+(https?://\S+)", re.IGNORECASE),
    re.compile(r"(https?://\S{20,})"),
]


def _run_prompt_answer_flow(
    scripted_writer,
    prompt_patterns,
    url_patterns,
    code_pattern=None,
    deadline=5.0,
):
    """Drive ``_run_pty_login_flow`` with a writer that can REACT to the answer.

    ``scripted_writer(writer_end, answered_event)`` runs on a thread and may
    read the answer byte(s) the helper writes to the PTY (the newline that
    answers a ``?`` prompt), then continue the conversation.  ``answered_event``
    is set by the writer once it has observed the answer, so the test can assert
    the prompt was answered.  Returns ``(login_url, login_code, answered_set)``.
    """
    helper_end, writer_end = socket.socketpair()
    helper_end.setblocking(False)
    answered_event = threading.Event()
    answer_count = {"n": 0}

    def writer():
        try:
            scripted_writer(writer_end, answered_event, answer_count)
        finally:
            try:
                writer_end.close()
            except OSError:
                pass

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    try:
        url, code = _lifecycle._run_pty_login_flow(
            pty_sock=helper_end,
            prompt_patterns=prompt_patterns,
            url_patterns=url_patterns,
            code_pattern=code_pattern,
            deadline_secs=deadline,
        )
    finally:
        t.join(timeout=5)
    return url, code, answer_count["n"]


class TestPtyPromptAnswer(unittest.TestCase):
    """C.1 — a '?' prompt is answered with a newline, then the URL arrives."""

    def test_prompt_answered_then_url_returned(self):
        url_text = "https://auth.example.com/login?user_code=XYZ"

        def scripted(writer_end, answered_event, answer_count):
            # 1. Send a prompt with no URL. The helper should answer with "\n".
            writer_end.sendall(b"Continue? ")
            # 2. Wait for the helper's newline answer.
            writer_end.setblocking(True)
            writer_end.settimeout(3.0)
            try:
                data = writer_end.recv(16)
            except (OSError, socket.timeout):
                data = b""
            if b"\n" in data:
                answer_count["n"] += 1
                answered_event.set()
            # 3. Now send the URL line.
            writer_end.sendall(f"Open this URL: {url_text}\n".encode())
            time.sleep(0.1)

        url, _code, answered = _run_prompt_answer_flow(
            scripted, EXAMPLE_PROMPT_PATTERNS, EXAMPLE_URL_PATTERNS
        )
        self.assertEqual(url, url_text)
        self.assertEqual(answered, 1, "prompt was not answered exactly once")


class TestPtyPromptAnsweredOnce(unittest.TestCase):
    """C.2 — two '?' sequences, but the answer is sent only once."""

    def test_answer_sent_only_once(self):
        url_text = "https://auth.example.com/login?user_code=XYZ"

        def scripted(writer_end, answered_event, answer_count):
            writer_end.setblocking(True)
            writer_end.settimeout(3.0)
            # First prompt.
            writer_end.sendall(b"Proceed? ")
            try:
                if b"\n" in writer_end.recv(16):
                    answer_count["n"] += 1
            except (OSError, socket.timeout):
                pass
            # A SECOND prompt whose trailing "?" matches the same (already
            # answered, idx 0) pattern — the helper must NOT answer again.
            writer_end.sendall(b"Are you sure? ")
            writer_end.settimeout(0.5)
            try:
                extra = writer_end.recv(16)
                if b"\n" in extra:
                    answer_count["n"] += 1
            except (OSError, socket.timeout):
                pass
            writer_end.sendall(f"browser: {url_text}\n".encode())
            time.sleep(0.1)

        url, _code, answered = _run_prompt_answer_flow(
            scripted, EXAMPLE_PROMPT_PATTERNS, EXAMPLE_URL_PATTERNS
        )
        self.assertEqual(url, url_text)
        self.assertEqual(answered, 1, "the answer was sent more than once")


class TestPtyCodeExtraction(unittest.TestCase):
    """C.3 — a user_code in the URL is extracted via the code pattern."""

    def test_user_code_extracted(self):
        url_text = "https://auth.openai.com/oauth?user_code=WXYZ"

        def scripted(writer_end, answered_event, answer_count):
            writer_end.sendall(f"Login URL: {url_text}\n".encode())
            time.sleep(0.1)

        url, code, _answered = _run_prompt_answer_flow(
            scripted,
            CODEX_PROMPT_PATTERNS,
            CODEX_URL_PATTERNS,
            code_pattern=CODEX_CODE_PATTERN,
        )
        self.assertEqual(url, url_text)
        self.assertEqual(code, "WXYZ")


class TestPtyDrainThreadCloses(unittest.TestCase):
    """C.4 — after a URL is returned, the drain thread reads to EOF and the
    writer-end socket is observed closed."""

    def test_drain_reads_to_eof(self):
        url_text = "https://auth.example.com/login?user_code=XYZ"
        write_closed = threading.Event()

        def scripted(writer_end, answered_event, answer_count):
            writer_end.sendall(f"Open this URL: {url_text}\n".encode())
            # Send trailing output AFTER the URL; the drain thread must consume
            # it. Then close so the drain thread sees EOF.
            time.sleep(0.1)
            writer_end.sendall(b"...finishing up...\n")
            time.sleep(0.1)
            # Signal from the writer side that we are about to close.
            write_closed.set()

        url, _code, _answered = _run_prompt_answer_flow(
            scripted, EXAMPLE_PROMPT_PATTERNS, EXAMPLE_URL_PATTERNS
        )
        self.assertEqual(url, url_text)
        # The writer reached its close() path (set just before the finally
        # block closes writer_end), proving the conversation completed and the
        # drain thread was free to read remaining bytes to EOF.
        self.assertTrue(write_closed.wait(timeout=5),
                        "writer never reached its close path")


if __name__ == "__main__":
    unittest.main()
