"""Unit tests for captain.py sentinel file helpers (TRN-243).

Covers:
- _parse_sentinel_file: key=value parsing, edge cases
- _read_sentinel_file: reads file content from FakePodmanClient archive
- _read_sentinel_file: returns None when archive raises / no entry scripted
- _delete_sentinel_file: calls container_exec with rm -f
- _delete_sentinel_file: logs warning on failure, does not raise
- Captain monitor sentinel branch logic (inline via mock)
- _format_captain_mail: message structure, no-signing path
- _parse_order_front_matter: with and without front-matter
- _validate_captain_change_name: valid and invalid names

All tests use FakePodmanClient — no unittest.mock.Mock() for Podman calls.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.fakes import FakePodmanClient


class TestParseSentinelFile(unittest.TestCase):
    """_parse_sentinel_file: parse key=value lines into a dict."""

    def setUp(self):
        from transport.captain import _parse_sentinel_file
        self._parse = _parse_sentinel_file

    def test_basic_parsing(self):
        content = "captain_id=test-crew\ncompleted_at=2026-01-01T00:00:00Z\n"
        result = self._parse(content)
        self.assertEqual(result["captain_id"], "test-crew")
        self.assertEqual(result["completed_at"], "2026-01-01T00:00:00Z")

    def test_reason_field(self):
        content = "rewrite=complete\nreason=standing orders met\n"
        result = self._parse(content)
        self.assertEqual(result["rewrite"], "complete")
        self.assertEqual(result["reason"], "standing orders met")

    def test_empty_content_returns_empty_dict(self):
        result = self._parse("")
        self.assertEqual(result, {})

    def test_blank_lines_ignored(self):
        content = "\n\ncaptain_id=abc\n\n"
        result = self._parse(content)
        self.assertEqual(result["captain_id"], "abc")

    def test_lines_without_equals_ignored(self):
        content = "no_equals_here\ncaptain_id=abc\n"
        result = self._parse(content)
        self.assertNotIn("no_equals_here", result)
        self.assertEqual(result["captain_id"], "abc")

    def test_value_with_equals_sign(self):
        """Value may contain '=' — only the first '=' is the separator."""
        content = "url=https://example.com/path?a=1\n"
        result = self._parse(content)
        self.assertEqual(result["url"], "https://example.com/path?a=1")

    def test_whitespace_stripped_from_keys_and_values(self):
        content = "  captain_id  =  test-crew  \n"
        result = self._parse(content)
        self.assertEqual(result["captain_id"], "test-crew")

    def test_returns_dict(self):
        self.assertIsInstance(self._parse("a=b"), dict)

    def test_full_sentinel_format(self):
        """The canonical Raven-written sentinel format parses correctly."""
        content = (
            "captain_id=abc123\n"
            "completed_at=2026-10-15T03:32:15Z\n"
            "reason=standing orders met\n"
        )
        result = self._parse(content)
        self.assertEqual(result["captain_id"], "abc123")
        self.assertIn("2026", result["completed_at"])


class TestReadSentinelFile(unittest.TestCase):
    """_read_sentinel_file: reads via FakePodmanClient.container_archive_get."""

    SENTINEL_PATH = "/home/kirocrew/workplace/kirocrew-workspace/.captain_done"
    CONTAINER = "gs-test-crew"

    def _read(self, podman, container=None):
        from transport.captain import _read_sentinel_file
        return _read_sentinel_file(podman, container or self.CONTAINER)

    def test_returns_content_when_file_present(self):
        podman = FakePodmanClient()
        podman.set_archive_file(
            container=self.CONTAINER,
            path=self.SENTINEL_PATH,
            content=b"rewrite=complete\ncaptain_id=test\n",
            filename=".captain_done",
        )
        result = self._read(podman)
        self.assertIsNotNone(result)
        self.assertIn("rewrite=complete", result)

    def test_returns_none_when_archive_raises(self):
        podman = FakePodmanClient()
        podman.set_archive_error(
            container=self.CONTAINER,
            path=self.SENTINEL_PATH,
            exc=RuntimeError("no such container"),
        )
        result = self._read(podman)
        self.assertIsNone(result)

    def test_returns_none_when_no_archive_scripted(self):
        """container_archive_get raises RuntimeError for unscripted paths — treated as None."""
        podman = FakePodmanClient()
        # No archive scripted; FakePodmanClient raises RuntimeError for missing entries
        result = self._read(podman)
        self.assertIsNone(result)

    def test_container_archive_get_called_with_correct_args(self):
        podman = FakePodmanClient()
        podman.set_archive_error(self.CONTAINER, self.SENTINEL_PATH, RuntimeError("nope"))
        self._read(podman)
        archive_calls = podman.calls_for("container_archive_get")
        self.assertTrue(len(archive_calls) >= 1)
        # Call is (method, container, path)
        self.assertEqual(archive_calls[0][1], self.CONTAINER)
        self.assertEqual(archive_calls[0][2], self.SENTINEL_PATH)

    def test_returns_string_not_bytes(self):
        podman = FakePodmanClient()
        podman.set_archive_file(
            self.CONTAINER, self.SENTINEL_PATH, b"key=val\n", filename=".captain_done"
        )
        result = self._read(podman)
        self.assertIsInstance(result, str)

    def test_utf8_content_decoded(self):
        podman = FakePodmanClient()
        content = "reason=все хорошо\n".encode("utf-8")
        podman.set_archive_file(
            self.CONTAINER, self.SENTINEL_PATH, content, filename=".captain_done"
        )
        result = self._read(podman)
        self.assertIn("reason=", result)


class TestDeleteSentinelFile(unittest.TestCase):
    """_delete_sentinel_file: calls exec rm -f, best-effort on failure."""

    SENTINEL_PATH = "/home/kirocrew/workplace/kirocrew-workspace/.captain_done"
    CONTAINER = "gs-test-crew"

    def _delete(self, podman, container=None):
        from transport.captain import _delete_sentinel_file
        _delete_sentinel_file(podman, container or self.CONTAINER)

    def test_calls_exec_rm(self):
        podman = FakePodmanClient()
        self._delete(podman)
        exec_calls = podman.calls_for("container_exec")
        self.assertTrue(len(exec_calls) >= 1)
        # The rm command must include the sentinel path
        found_rm = False
        for call in exec_calls:
            cmd = call[2]  # (method, container, cmd)
            if "rm" in cmd and self.SENTINEL_PATH in cmd:
                found_rm = True
                break
        self.assertTrue(found_rm, f"Expected rm {self.SENTINEL_PATH!r} in exec calls: {exec_calls}")

    def test_does_not_raise_on_exception(self):
        """_delete_sentinel_file is best-effort — must not propagate errors."""
        class BrokenPodman(FakePodmanClient):
            def container_exec(self, name, cmd, env=None):
                raise RuntimeError("podman is broken")

        podman = BrokenPodman()
        # Should not raise
        try:
            self._delete(podman)
        except Exception as exc:
            self.fail(f"_delete_sentinel_file raised unexpectedly: {exc}")

    def test_warns_on_failure(self):
        """_delete_sentinel_file logs a warning when the exec fails."""
        class BrokenPodman(FakePodmanClient):
            def container_exec(self, name, cmd, env=None):
                raise RuntimeError("podman is broken")

        podman = BrokenPodman()
        with self.assertLogs("transport.captain", level="WARNING"):
            self._delete(podman)


class TestSentinelMonitorBranch(unittest.TestCase):
    """Inline logic test: sentinel-present causes schedule to be disabled.

    This mirrors the logic in monitors.py _captain_monitor_tick:
    if sentinel_content is not None → set s["enabled"] = False and continue.

    Rather than testing monitors.py directly (which has heavy dependencies),
    we test the pure logic by simulating what the monitor does.
    """

    def test_sentinel_present_disables_schedule(self):
        """When sentinel is found, the schedule entry's enabled flag is set to False."""
        schedule_entry = {"type": "captain", "enabled": True, "next_fire_at": 9999.0}
        crew_schedules = [schedule_entry]

        from transport.captain import _parse_sentinel_file, _read_sentinel_file

        podman = FakePodmanClient()
        container = "gs-abc123"
        sentinel_path = "/home/kirocrew/workplace/kirocrew-workspace/.captain_done"
        podman.set_archive_file(
            container, sentinel_path,
            b"captain_id=abc123\ncompleted_at=2026-10-15T00:00:00Z\n",
            filename=".captain_done",
        )

        # Simulate the monitor sentinel check
        sentinel_content = _read_sentinel_file(podman, container)
        if sentinel_content is not None:
            _parsed = _parse_sentinel_file(sentinel_content)
            for s in crew_schedules:
                if s.get("type") == "captain":
                    s["enabled"] = False
                    break

        self.assertFalse(schedule_entry["enabled"])

    def test_sentinel_absent_leaves_schedule_enabled(self):
        """When no sentinel, the schedule entry's enabled flag is untouched."""
        schedule_entry = {"type": "captain", "enabled": True, "next_fire_at": 9999.0}
        crew_schedules = [schedule_entry]

        from transport.captain import _parse_sentinel_file, _read_sentinel_file

        podman = FakePodmanClient()
        container = "gs-abc123"
        # No archive scripted — _read_sentinel_file returns None

        sentinel_content = _read_sentinel_file(podman, container)
        if sentinel_content is not None:
            _parsed = _parse_sentinel_file(sentinel_content)
            for s in crew_schedules:
                if s.get("type") == "captain":
                    s["enabled"] = False
                    break

        self.assertTrue(schedule_entry["enabled"])

    def test_parse_sentinel_captain_id_extracted(self):
        from transport.captain import _parse_sentinel_file
        content = "captain_id=my-crew-42\ncompleted_at=2026-10-15T00:00:00Z\n"
        parsed = _parse_sentinel_file(content)
        self.assertEqual(parsed.get("captain_id"), "my-crew-42")

    def test_parse_sentinel_completed_at_extracted(self):
        from transport.captain import _parse_sentinel_file
        content = "captain_id=test\ncompleted_at=2026-10-15T03:32:15Z\n"
        parsed = _parse_sentinel_file(content)
        self.assertEqual(parsed.get("completed_at"), "2026-10-15T03:32:15Z")


class TestFormatCaptainMail(unittest.TestCase):
    """_format_captain_mail: message structure, required headers, no-signing path."""

    def _format(self, body: str, signing_secret=None, supersedes_id=None):
        from transport.captain import _format_captain_mail
        return _format_captain_mail(body, signing_secret=signing_secret, supersedes_id=supersedes_id)

    def test_returns_tuple_of_str_str(self):
        msg, msg_id = self._format("test order body")
        self.assertIsInstance(msg, str)
        self.assertIsInstance(msg_id, str)

    def test_message_id_is_uuid_format(self):
        _, msg_id = self._format("body")
        # Message-ID format: <uuid@localhost>
        self.assertTrue(msg_id.startswith("<"))
        self.assertTrue(msg_id.endswith(">"))
        self.assertIn("@localhost", msg_id)

    def test_from_header_is_admiral(self):
        msg, _ = self._format("body")
        self.assertIn("From: admiral@localhost", msg)

    def test_to_header_is_captain(self):
        msg, _ = self._format("body")
        self.assertIn("To: captain@localhost", msg)

    def test_subject_from_first_nonempty_line(self):
        msg, _ = self._format("Stand down all crews\nMore details here.")
        self.assertIn("Subject: Stand down all crews", msg)

    def test_subject_truncated_to_72_chars(self):
        long_subject = "A" * 100
        msg, _ = self._format(long_subject)
        for line in msg.splitlines():
            if line.startswith("Subject:"):
                subject_val = line[len("Subject:"):].strip()
                self.assertLessEqual(len(subject_val), 72)
                break

    def test_body_present_after_headers(self):
        msg, _ = self._format("order body here")
        self.assertIn("order body here", msg)

    def test_no_x_admiral_sig_without_secret(self):
        msg, _ = self._format("body")
        self.assertNotIn("X-Admiral-Sig", msg)

    def test_x_admiral_sig_with_secret(self):
        # A valid 32-byte hex seed
        secret = "00" * 32
        msg, _ = self._format("body", signing_secret=secret)
        self.assertIn("X-Admiral-Sig:", msg)

    def test_supersedes_header_when_provided(self):
        msg, _ = self._format("body", supersedes_id="<prior-uuid@localhost>")
        self.assertIn("Supersedes:", msg)
        self.assertIn("<prior-uuid@localhost>", msg)

    def test_no_supersedes_header_when_not_provided(self):
        msg, _ = self._format("body")
        self.assertNotIn("Supersedes:", msg)

    def test_date_header_present(self):
        msg, _ = self._format("body")
        self.assertIn("Date:", msg)

    def test_blank_body_uses_default_subject(self):
        msg, _ = self._format("")
        self.assertIn("Subject: Standing order", msg)

    def test_multiline_body_uses_first_line_as_subject(self):
        """Multi-line body: subject is derived from the first non-empty line."""
        body = "First line subject\nSecond line is body"
        msg, _ = self._format(body)
        self.assertIn("Subject: First line subject", msg)
        self.assertNotIn("Second line is body", msg.split("\n\n")[0])


class TestParseOrderFrontMatter(unittest.TestCase):
    """_parse_order_front_matter: YAML front-matter parsing."""

    def _parse(self, content: str):
        from transport.captain import _parse_order_front_matter
        return _parse_order_front_matter(content)

    def test_no_front_matter_returns_empty_description(self):
        desc, aliases, body = self._parse("Body content here")
        self.assertEqual(desc, "")
        self.assertEqual(body, "Body content here")

    def test_description_field_extracted(self):
        content = '---\ndescription: "My order"\n---\nBody here'
        desc, aliases, body = self._parse(content)
        self.assertEqual(desc, "My order")

    def test_description_without_quotes(self):
        content = "---\ndescription: My unquoted description\n---\nBody"
        desc, aliases, body = self._parse(content)
        self.assertEqual(desc, "My unquoted description")

    def test_body_after_closing_delimiter(self):
        content = "---\ndescription: Test\n---\nThe body"
        _, _, body = self._parse(content)
        self.assertEqual(body.strip(), "The body")

    def test_aliases_extracted(self):
        content = '---\naliases: ["alt1", "alt2"]\n---\nBody'
        _, aliases, _ = self._parse(content)
        self.assertIn("alt1", aliases)
        self.assertIn("alt2", aliases)

    def test_no_aliases_returns_empty_list(self):
        content = "---\ndescription: Test\n---\nBody"
        _, aliases, _ = self._parse(content)
        self.assertEqual(aliases, [])

    def test_returns_three_tuple(self):
        result = self._parse("content")
        self.assertEqual(len(result), 3)


class TestValidateCaptainChangeName(unittest.TestCase):
    """_validate_captain_change_name: kebab-case validation."""

    def _validate(self, name: str):
        from transport.captain import _validate_captain_change_name
        _validate_captain_change_name(name)

    def test_valid_single_word(self):
        self._validate("mychange")  # no exception

    def test_valid_hyphenated(self):
        self._validate("my-change-123")  # no exception

    def test_valid_numbers(self):
        self._validate("fix-244")  # no exception

    def test_uppercase_raises(self):
        with self.assertRaises(ValueError):
            self._validate("MyChange")

    def test_underscore_raises(self):
        with self.assertRaises(ValueError):
            self._validate("my_change")

    def test_spaces_raise(self):
        with self.assertRaises(ValueError):
            self._validate("my change")

    def test_leading_hyphen_raises(self):
        with self.assertRaises(ValueError):
            self._validate("-mychange")

    def test_trailing_hyphen_raises(self):
        with self.assertRaises(ValueError):
            self._validate("mychange-")

    def test_double_hyphen_raises(self):
        with self.assertRaises(ValueError):
            self._validate("my--change")

    def test_non_string_raises(self):
        with self.assertRaises((ValueError, TypeError)):
            self._validate(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
