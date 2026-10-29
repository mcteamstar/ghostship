"""Unit tests for captain.py check-in, mail-counting, order-template, and
Admiral-mail helpers (TRN-245).

Covers:
- _captain_jobs: dict/list/non-list payload normalisation
- _captain_checkin_job: name+agent match, wrong agent, enabled_only, empty
- _captain_order_lock: per-crew lock identity and type
- _mail_count: Maildir two-number, mbox single-number, zero, malformed
- _read_all_mail_counts: valid JSON, malformed JSON, zero omitted
- _read_all_mail_subjects: dict-of-lists shape
- _skim_all_mailboxes: all 8 keys happy path, exec-failure fallback
- _list_order_templates: built-ins, missing GA_ORDERS_DIR warning, override
- _load_order_template: known built-in, unknown ValueError
- _substitute_placeholders: known token replaced, unknown token warns
- _resolve_order_template: <change>/<change?> variants and validation
- _captain_standing_view: enabled/paused status, schedule fields
- _append_captain_mail: no-signing / signing / supersedes I/O path

All tests use FakePodmanClient — no unittest.mock.Mock() for Podman calls.
Registry I/O is blocked by the autouse conftest fixture; tests that need
crew state mutate ``registry._reg`` inside a ``with registry:`` block.
"""

from __future__ import annotations

import base64
import threading
import unittest
from unittest.mock import patch

from tests.fakes import FakePodmanClient


# ── 2.1 _captain_jobs ─────────────────────────────────────────────────────────

class TestCaptainJobs(unittest.TestCase):
    """_captain_jobs: normalise the /api/crons payload into a list of dicts."""

    def _jobs(self, payload):
        from transport.captain import _captain_jobs
        return _captain_jobs(payload)

    def test_dict_payload_with_jobs_key(self):
        payload = {"jobs": [{"name": "captain"}, {"name": "other"}]}
        result = self._jobs(payload)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "captain")

    def test_list_payload(self):
        payload = [{"name": "a"}, {"name": "b"}]
        result = self._jobs(payload)
        self.assertEqual(len(result), 2)

    def test_non_list_payload_returns_empty_list(self):
        self.assertEqual(self._jobs("not-a-list"), [])
        self.assertEqual(self._jobs(123), [])

    def test_dict_without_jobs_key_returns_empty_list(self):
        self.assertEqual(self._jobs({"something": "else"}), [])

    def test_non_dict_entries_filtered_out(self):
        payload = [{"name": "a"}, "garbage", 42, {"name": "b"}]
        result = self._jobs(payload)
        self.assertEqual(result, [{"name": "a"}, {"name": "b"}])

    def test_returns_list(self):
        self.assertIsInstance(self._jobs({"jobs": []}), list)


# ── 2.2 _captain_checkin_job ───────────────────────────────────────────────────

class TestCaptainCheckinJob(unittest.TestCase):
    """_captain_checkin_job: find the raven-owned captain check-in job."""

    def _find(self, payload, *, enabled_only=False):
        from transport.captain import _captain_checkin_job
        return _captain_checkin_job(payload, enabled_only=enabled_only)

    def test_matches_on_name_and_agent(self):
        payload = {"jobs": [{"name": "captain", "agent": "raven", "id": "job-1"}]}
        result = self._find(payload)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "job-1")

    def test_ignores_wrong_agent(self):
        payload = {"jobs": [{"name": "captain", "agent": "ghost", "id": "job-1"}]}
        self.assertIsNone(self._find(payload))

    def test_ignores_wrong_name(self):
        payload = {"jobs": [{"name": "lookout", "agent": "raven"}]}
        self.assertIsNone(self._find(payload))

    def test_enabled_only_filters_disabled(self):
        payload = {"jobs": [{"name": "captain", "agent": "raven", "enabled": False}]}
        self.assertIsNone(self._find(payload, enabled_only=True))

    def test_enabled_only_returns_enabled(self):
        payload = {"jobs": [{"name": "captain", "agent": "raven", "enabled": True}]}
        result = self._find(payload, enabled_only=True)
        self.assertIsNotNone(result)
        self.assertTrue(result["enabled"])

    def test_empty_payload_returns_none(self):
        self.assertIsNone(self._find({"jobs": []}))
        self.assertIsNone(self._find([]))
        self.assertIsNone(self._find("garbage"))

    def test_first_match_wins_among_multiple(self):
        payload = {"jobs": [
            {"name": "other", "agent": "raven"},
            {"name": "captain", "agent": "raven", "id": "the-one"},
        ]}
        result = self._find(payload)
        self.assertEqual(result["id"], "the-one")


# ── 3.1 _captain_order_lock ────────────────────────────────────────────────────

class TestCaptainOrderLock(unittest.TestCase):
    """_captain_order_lock: per-crew_id lock identity."""

    def _lock(self, crew_id):
        from transport.captain import _captain_order_lock
        return _captain_order_lock(crew_id)

    def test_same_crew_returns_same_lock(self):
        a = self._lock("crew-same")
        b = self._lock("crew-same")
        self.assertIs(a, b)

    def test_different_crew_returns_different_lock(self):
        a = self._lock("crew-x")
        b = self._lock("crew-y")
        self.assertIsNot(a, b)

    def test_returns_lock_type(self):
        lock = self._lock("crew-type-check")
        # threading.Lock() is a factory; the instance type is the lock class.
        self.assertIsInstance(lock, type(threading.Lock()))

    def test_lock_is_usable(self):
        lock = self._lock("crew-usable")
        acquired = lock.acquire(blocking=False)
        self.assertTrue(acquired)
        lock.release()


# ── 4.1 _mail_count ────────────────────────────────────────────────────────────

class TestMailCount(unittest.TestCase):
    """_mail_count: parse the counting-script output into an int."""

    CONTAINER = "gs-test-crew"
    MAILBOX = "/var/mail/captain"

    def _count(self, output):
        from transport.captain import _mail_count
        podman = FakePodmanClient()
        # Catch-all response keyed by container name.
        podman.exec_checked_responses[self.CONTAINER] = output
        return _mail_count(podman, self.CONTAINER, self.MAILBOX)

    def test_maildir_two_numbers_summed(self):
        self.assertEqual(self._count("3 2"), 5)

    def test_mbox_single_number(self):
        self.assertEqual(self._count("7"), 7)

    def test_zero_output(self):
        self.assertEqual(self._count("0 0"), 0)

    def test_malformed_non_numeric_returns_zero(self):
        self.assertEqual(self._count("not a number"), 0)

    def test_empty_output_returns_zero(self):
        self.assertEqual(self._count(""), 0)

    def test_whitespace_trimmed(self):
        self.assertEqual(self._count("  4 1  \n"), 5)


# ── 4.2 _read_all_mail_counts ───────────────────────────────────────────────────

class TestReadAllMailCounts(unittest.TestCase):
    """_read_all_mail_counts: JSON mailbox→count dict, zero entries omitted."""

    CONTAINER = "gs-test-crew"

    def _counts(self, output):
        from transport.captain import _read_all_mail_counts
        podman = FakePodmanClient()
        podman.exec_checked_responses[self.CONTAINER] = output
        return _read_all_mail_counts(podman, self.CONTAINER)

    def test_valid_json_returns_int_dict(self):
        result = self._counts('{"ghost": 3}')
        self.assertEqual(result, {"ghost": 3})
        self.assertIsInstance(result["ghost"], int)

    def test_malformed_json_returns_empty_dict(self):
        self.assertEqual(self._counts("not json {"), {})

    def test_non_int_values_omitted(self):
        # The script contract yields ints; non-int values are filtered out.
        result = self._counts('{"ghost": 2, "spectre": "x"}')
        self.assertEqual(result, {"ghost": 2})

    def test_non_dict_json_returns_empty_dict(self):
        self.assertEqual(self._counts("[1, 2, 3]"), {})

    def test_empty_object_returns_empty_dict(self):
        self.assertEqual(self._counts("{}"), {})


# ── 4.3 _read_all_mail_subjects ─────────────────────────────────────────────────

class TestReadAllMailSubjects(unittest.TestCase):
    """_read_all_mail_subjects: JSON mailbox→list-of-subject-dicts."""

    CONTAINER = "gs-test-crew"

    def _subjects(self, output):
        from transport.captain import _read_all_mail_subjects
        podman = FakePodmanClient()
        podman.exec_checked_responses[self.CONTAINER] = output
        return _read_all_mail_subjects(podman, self.CONTAINER)

    def test_returns_dict_of_lists(self):
        payload = (
            '{"ghost": [{"subject": "hi", "received_at": null}], '
            '"captain": []}'
        )
        result = self._subjects(payload)
        self.assertIsInstance(result, dict)
        self.assertIsInstance(result["ghost"], list)
        self.assertEqual(result["ghost"][0]["subject"], "hi")
        self.assertEqual(result["captain"], [])

    def test_non_dict_entries_filtered_within_lists(self):
        payload = '{"ghost": [{"subject": "ok"}, "garbage", 42]}'
        result = self._subjects(payload)
        self.assertEqual(result["ghost"], [{"subject": "ok"}])

    def test_malformed_json_returns_empty_dict(self):
        self.assertEqual(self._subjects("not json"), {})

    def test_non_list_values_filtered_out(self):
        payload = '{"ghost": [{"subject": "ok"}], "spectre": "notalist"}'
        result = self._subjects(payload)
        self.assertIn("ghost", result)
        self.assertNotIn("spectre", result)


# ── 4.4 _skim_all_mailboxes ─────────────────────────────────────────────────────

class TestSkimAllMailboxes(unittest.TestCase):
    """_skim_all_mailboxes: 8-key happy path and exec-failure fallback."""

    CONTAINER = "gs-test-crew"
    EXPECTED_KEYS = {
        "ghost", "spectre", "banshee", "wraith",
        "reaper", "raven", "captain", "admiral",
    }

    def test_happy_path_all_eight_keys_present(self):
        from transport.captain import _skim_all_mailboxes
        podman = FakePodmanClient()
        # Script the single read_mail_subjects exec to return a partial dict;
        # _skim fills in the missing keys with empty lists.
        podman.exec_checked_responses[self.CONTAINER] = (
            '{"ghost": [{"subject": "report"}]}'
        )
        result = _skim_all_mailboxes(podman, self.CONTAINER)
        self.assertEqual(set(result.keys()), self.EXPECTED_KEYS)
        self.assertEqual(result["ghost"], [{"subject": "report"}])
        self.assertEqual(result["admiral"], [])

    def test_exec_failure_falls_back_to_archive_without_raising(self):
        from transport.captain import _skim_all_mailboxes

        class ExecFailPodman(FakePodmanClient):
            def container_exec_checked(self, name, cmd, env=None):
                raise RuntimeError("container stopped")

        podman = ExecFailPodman()
        # No archive scripted → container_archive_get raises per mailbox →
        # fallback returns empty lists rather than propagating.
        result = _skim_all_mailboxes(podman, self.CONTAINER)
        self.assertEqual(set(result.keys()), self.EXPECTED_KEYS)
        for key in self.EXPECTED_KEYS:
            self.assertEqual(result[key], [])
        # Fallback attempts the archive API per mailbox.
        self.assertTrue(podman.was_called("container_archive_get"))

    def test_empty_exec_result_falls_through_to_fallback(self):
        from transport.captain import _skim_all_mailboxes
        podman = FakePodmanClient()
        # Empty JSON object → falsy result → fallback path, still 8 keys.
        podman.exec_checked_responses[self.CONTAINER] = "{}"
        result = _skim_all_mailboxes(podman, self.CONTAINER)
        self.assertEqual(set(result.keys()), self.EXPECTED_KEYS)


# ── 5.1 _list_order_templates ───────────────────────────────────────────────────

class TestListOrderTemplates(unittest.TestCase):
    """_list_order_templates: built-ins, missing-dir warning, user override."""

    def test_builtins_non_empty_list_of_pairs(self):
        import transport.captain as captain
        with patch.object(captain, "GA_ORDERS_DIR", ""):
            result = captain._list_order_templates()
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)
        for entry in result:
            self.assertEqual(len(entry), 2)
        names = [name for name, _desc in result]
        self.assertIn("sdd", names)

    def test_missing_ga_orders_dir_warns_and_returns_builtins(self):
        import transport.captain as captain
        missing = "/nonexistent/orders/path/xyz"
        # Reset the one-time warning flag so the WARNING fires in this test.
        with patch.object(captain, "GA_ORDERS_DIR", missing), \
             patch.object(captain, "_ga_orders_dir_warned", False):
            with self.assertLogs("transport.captain", level="WARNING"):
                result = captain._list_order_templates()
        self.assertTrue(len(result) > 0)

    def test_user_template_overrides_builtin(self, ):
        import transport.captain as captain
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmp:
            # Synthetic .md whose stem matches a built-in ("sdd").
            user_file = os.path.join(tmp, "sdd.md")
            with open(user_file, "w", encoding="utf-8") as fh:
                fh.write('---\ndescription: "USER OVERRIDE DESC"\n---\nbody\n')
            with patch.object(captain, "GA_ORDERS_DIR", tmp):
                result = dict(captain._list_order_templates())
        self.assertEqual(result.get("sdd"), "USER OVERRIDE DESC")


# ── 5.2 _load_order_template ────────────────────────────────────────────────────

class TestLoadOrderTemplate(unittest.TestCase):
    """_load_order_template: known built-in tuple, unknown ValueError."""

    def test_known_builtin_returns_description_body(self):
        import transport.captain as captain
        with patch.object(captain, "GA_ORDERS_DIR", ""):
            description, body = captain._load_order_template("sdd")
        self.assertIsInstance(description, str)
        self.assertIsInstance(body, str)
        self.assertTrue(len(body) > 0)

    def test_unknown_name_raises_value_error(self):
        import transport.captain as captain
        with patch.object(captain, "GA_ORDERS_DIR", ""):
            with self.assertRaises(ValueError):
                captain._load_order_template("no-such-template-xyz")


# ── 5.3 _substitute_placeholders ────────────────────────────────────────────────

class TestSubstitutePlaceholders(unittest.TestCase):
    """_substitute_placeholders: known tokens replaced, unknown token warns."""

    def test_known_token_replaced(self):
        from transport.captain import (
            _substitute_placeholders,
            _RAVEN_GATEWAY_ORIENTATION,
        )
        body = "before {{RAVEN_GATEWAY_ORIENTATION}} after"
        result = _substitute_placeholders(body)
        self.assertNotIn("{{RAVEN_GATEWAY_ORIENTATION}}", result)
        # The constant's text is substituted in; spot-check a stable fragment.
        self.assertIn(_RAVEN_GATEWAY_ORIENTATION[:30], result)

    def test_unknown_token_logs_warning(self):
        from transport.captain import _substitute_placeholders
        with self.assertLogs("transport.captain", level="WARNING"):
            result = _substitute_placeholders("text {{UNKNOWN_TOKEN}} more")
        # Residual placeholder is left intact (only a warning, no replacement).
        self.assertIn("{{UNKNOWN_TOKEN}}", result)

    def test_no_placeholders_no_warning(self):
        from transport.captain import _substitute_placeholders
        import logging
        logger = logging.getLogger("transport.captain")
        # assertNoLogs is 3.10+; guard with a manual handler if unavailable.
        with patch.object(logger, "warning") as warn:
            result = _substitute_placeholders("plain body, no tokens")
        self.assertEqual(result, "plain body, no tokens")
        warn.assert_not_called()


# ── 6.1 _resolve_order_template ─────────────────────────────────────────────────

class TestResolveOrderTemplate(unittest.TestCase):
    """_resolve_order_template: <change> / <change?> variants and validation.

    Each variant patches _load_order_template to return a controlled body so
    the test does not depend on any on-disk template's exact token.
    """

    def _resolve(self, body, change_name, message=None):
        import transport.captain as captain
        with patch.object(
            captain, "_load_order_template", return_value=("desc", body)
        ):
            return captain._resolve_order_template("ctrl", change_name, message=message)

    def test_change_with_valid_name_injected(self):
        result = self._resolve("implement <change> now", "trn-245-test")
        self.assertIn("trn-245-test", result)
        self.assertNotIn("<change>", result)

    def test_change_without_name_raises(self):
        with self.assertRaises(ValueError):
            self._resolve("implement <change> now", None)

    def test_optional_change_with_name_injected(self):
        result = self._resolve("scope: <change?>", "trn-245-test")
        self.assertIn("trn-245-test", result)
        self.assertNotIn("<change?>", result)

    def test_optional_change_without_name_uses_entire_codebase(self):
        result = self._resolve("scope: <change?>", None)
        self.assertIn("entire codebase", result)
        self.assertNotIn("<change?>", result)

    def test_invalid_uppercase_name_raises(self):
        with self.assertRaises(ValueError):
            self._resolve("implement <change>", "TRN-UPPER")

    def test_template_none_raises(self):
        import transport.captain as captain
        with self.assertRaises(ValueError):
            captain._resolve_order_template(None, "trn-245-test")

    def test_message_placeholder_substituted(self):
        result = self._resolve("Standing order: <message>", None, message="investigate disk usage")
        self.assertIn("investigate disk usage", result)
        self.assertNotIn("<message>", result)

    def test_message_placeholder_without_message_raises(self):
        with self.assertRaises(ValueError):
            self._resolve("Standing order: <message>", None, message=None)

    def test_message_placeholder_with_empty_message_raises(self):
        with self.assertRaises(ValueError):
            self._resolve("Standing order: <message>", None, message="")

    def test_no_message_placeholder_message_ignored(self):
        # Templates that don't use <message> accept message= without error
        result = self._resolve("do the thing", None, message="ignored")
        self.assertEqual(result.strip(), "do the thing")


# ── 7.1 _captain_standing_view ──────────────────────────────────────────────────

class TestCaptainStandingView(unittest.TestCase):
    """_captain_standing_view: status surface with mail counts and schedule."""

    CREW_ID = "test-crew"
    CONTAINER = "gs-test-crew"

    def _podman(self):
        podman = FakePodmanClient()
        # Both _mail_count calls (captain + admiral) hit the catch-all.
        podman.exec_checked_responses[self.CONTAINER] = "2 0"
        return podman

    def test_enabled_job_status_enabled(self):
        from transport.captain import _captain_standing_view
        job = {"enabled": True, "id": "job-1"}
        result = _captain_standing_view(
            self.CREW_ID, "status", job, self._podman(), self.CONTAINER
        )
        self.assertEqual(result["status"], "enabled")
        self.assertTrue(result["enabled"])
        # Required keys present.
        for key in (
            "crew_id", "action", "status", "mode", "unread_mail",
            "unread_admiral_mail", "mailbox", "admiral_mailbox", "last_run",
        ):
            self.assertIn(key, result)
        self.assertEqual(result["unread_mail"], 2)

    def test_disabled_job_status_paused(self):
        from transport.captain import _captain_standing_view
        job = {"enabled": False, "id": "job-1"}
        result = _captain_standing_view(
            self.CREW_ID, "status", job, self._podman(), self.CONTAINER
        )
        self.assertEqual(result["status"], "paused")
        self.assertFalse(result["enabled"])

    def test_schedule_fields_surfaced(self):
        from transport.captain import _captain_standing_view
        job = {"enabled": True, "id": "job-1"}

        # Patch _load_registry to return a registry with our captain schedule
        # so we don't touch the filesystem (avoids deadlock with _registry_lock).
        fake_reg = {
            "crews": {
                "test-crew": {
                    "schedules": [
                        {
                            "type": "captain",
                            "last_checkin_at": "2026-10-15T05:00:00Z",
                            "current_task_id": "task-abc",
                        }
                    ]
                }
            }
        }
        with patch("transport.registry._load_registry", return_value=fake_reg), \
             patch("transport.registry._save_registry"):
            result = _captain_standing_view(
                self.CREW_ID, "status", job, self._podman(), self.CONTAINER
            )

        self.assertEqual(result["last_checkin_at"], "2026-10-15T05:00:00Z")
        self.assertEqual(result["current_task_id"], "task-abc")


# ── 8.1 _append_captain_mail ────────────────────────────────────────────────────

class TestAppendCaptainMail(unittest.TestCase):
    """_append_captain_mail: no-signing / signing / supersedes I/O path."""

    CREW_ID = "test-crew"
    CONTAINER = "gs-test-crew"

    def _decode_sent_payload(self, podman) -> str:
        """Extract and base64-decode the mail payload from the exec call."""
        exec_calls = podman.calls_for("container_exec_checked")
        self.assertTrue(len(exec_calls) >= 1, "expected an exec call")
        cmd = exec_calls[-1][2]  # (method, container, cmd)
        # cmd = ["python3", ".../append_captain_mail.py", <base64 payload>]
        payload_b64 = cmd[-1]
        return base64.b64decode(payload_b64).decode("utf-8")

    def test_no_signing_secret_omits_sig_header(self):
        from transport.captain import _append_captain_mail
        podman = FakePodmanClient()
        with patch("transport.captain._read_crew_secret", return_value=None):
            _append_captain_mail(podman, self.CONTAINER, "order body", crew_id=self.CREW_ID)
        decoded = self._decode_sent_payload(podman)
        self.assertNotIn("X-Admiral-Sig", decoded)
        self.assertIn("order body", decoded)

    def test_signing_secret_adds_sig_header(self):
        from transport.captain import _append_captain_mail
        podman = FakePodmanClient()
        seed = "ab" * 32  # 32-byte hex seed
        with patch("transport.captain._read_crew_secret", return_value=seed):
            _append_captain_mail(podman, self.CONTAINER, "order body", crew_id=self.CREW_ID)
        decoded = self._decode_sent_payload(podman)
        self.assertIn("X-Admiral-Sig:", decoded)

    def test_supersedes_references_prior_message_id(self):
        from transport.captain import _append_captain_mail
        from transport.registry import registry
        prior_id = "<prior-uuid@localhost>"
        podman = FakePodmanClient()
        with registry:
            registry._reg["crews"]["test-crew"] = {
                "last_captain_message_id": prior_id,
            }
        with patch("transport.captain._read_crew_secret", return_value=None):
            _append_captain_mail(podman, self.CONTAINER, "order body", crew_id=self.CREW_ID)
        decoded = self._decode_sent_payload(podman)
        self.assertIn("Supersedes:", decoded)
        self.assertIn(prior_id, decoded)

    def test_exec_checked_called(self):
        from transport.captain import _append_captain_mail
        podman = FakePodmanClient()
        with patch("transport.captain._read_crew_secret", return_value=None):
            _append_captain_mail(podman, self.CONTAINER, "order body", crew_id=self.CREW_ID)
        self.assertTrue(podman.was_called("container_exec_checked"))


# ── 9.1 _parse_order_front_matter ──────────────────────────────────────────────

class TestParseOrderFrontMatter(unittest.TestCase):
    """_parse_order_front_matter: YAML front-matter split (description, aliases, body)."""

    def _parse(self, content):
        from transport.captain import _parse_order_front_matter
        return _parse_order_front_matter(content)

    def test_no_front_matter_returns_whole_body(self):
        content = "just a plain body\nwith two lines"
        description, aliases, body = self._parse(content)
        self.assertEqual(body, content)
        self.assertEqual(description, "")
        self.assertEqual(aliases, [])

    def test_description_quotes_stripped(self):
        content = '---\ndescription: "Some text"\n---\nbody here\n'
        description, _aliases, _body = self._parse(content)
        self.assertEqual(description, "Some text")

    def test_aliases_parsed_as_list(self):
        content = '---\naliases: ["a", "b"]\n---\nbody\n'
        _description, aliases, _body = self._parse(content)
        self.assertEqual(aliases, ["a", "b"])

    def test_body_excludes_front_matter_block(self):
        content = '---\ndescription: "d"\n---\nthe real body\n'
        _description, _aliases, body = self._parse(content)
        self.assertNotIn("---", body)
        self.assertNotIn("description:", body)
        self.assertIn("the real body", body)

    def test_unclosed_fence_treated_as_no_front_matter(self):
        content = "---\ndescription: \"never closed\"\nstill body"
        description, _aliases, body = self._parse(content)
        self.assertEqual(body, content)
        self.assertEqual(description, "")


# ── 9.2 _validate_captain_change_name ───────────────────────────────────────────

class TestValidateCaptainChangeName(unittest.TestCase):
    """_validate_captain_change_name: kebab-case acceptance / rejection."""

    def _validate(self, name):
        from transport.captain import _validate_captain_change_name
        return _validate_captain_change_name(name)

    def test_valid_kebab_case_passes(self):
        # Should not raise.
        self.assertIsNone(self._validate("trn-245-test-captain"))

    def test_uppercase_rejected(self):
        with self.assertRaises(ValueError):
            self._validate("TRN-245")

    def test_trailing_hyphen_rejected(self):
        with self.assertRaises(ValueError):
            self._validate("trn-245-")

    def test_double_hyphen_rejected(self):
        with self.assertRaises(ValueError):
            self._validate("trn--245")

    def test_none_rejected(self):
        with self.assertRaises(ValueError):
            self._validate(None)


# ── 9.3 _format_captain_mail ────────────────────────────────────────────────────

class TestFormatCaptainMail(unittest.TestCase):
    """_format_captain_mail: RFC 5322 message rendering, with/without signing.

    Signing is exercised against the conftest ``cryptography`` stub, so only
    header *presence* is asserted — not the (non-real-curve) signature bytes.
    """

    SEED = "ab" * 32  # 32-byte hex Ed25519 seed

    def _format(self, body, **kwargs):
        from transport.captain import _format_captain_mail
        return _format_captain_mail(body, **kwargs)

    def test_required_headers_present(self):
        message, _mid = self._format("order body line\nmore")
        self.assertIn("From: admiral@localhost", message)
        self.assertIn("To: captain@localhost", message)
        self.assertIn("Subject:", message)
        self.assertIn("Message-ID:", message)
        self.assertIn("Date:", message)

    def test_message_id_shape(self):
        _message, mid = self._format("subject line\nbody")
        self.assertTrue(mid.startswith("<"))
        self.assertTrue(mid.endswith("@localhost>"))

    def test_subject_from_first_non_empty_line(self):
        message, _mid = self._format("This is the subject\nmore body")
        self.assertIn("Subject: This is the subject", message)

    def test_subject_truncated_to_72_chars(self):
        long_line = "x" * 200
        message, _mid = self._format(long_line + "\nbody")
        # Extract the Subject header value.
        subject_line = next(
            ln for ln in message.splitlines() if ln.startswith("Subject: ")
        )
        subject_val = subject_line[len("Subject: "):]
        self.assertLessEqual(len(subject_val), 72)

    def test_signing_secret_adds_sig_header(self):
        message, _mid = self._format("order body\nmore", signing_secret=self.SEED)
        self.assertIn("X-Admiral-Sig:", message)

    def test_signing_clean_multiline_body_does_not_raise(self):
        # Spec §6.6 names a ValueError guard for a newline in the derived
        # Subject on the signing path. In the current implementation that guard
        # is UNREACHABLE through the public ``body`` argument: _format_captain_mail
        # derives the subject with str.splitlines()/strip(), which removes every
        # newline before the guard runs, so no caller-supplied body can carry a
        # newline into the subject. (Recorded as finding F2.) The observable,
        # reachable contract is the negative control: signing a clean multi-line
        # body succeeds and emits the signature header.
        message, _mid = self._format(
            "clean subject\nsecond line\nthird", signing_secret=self.SEED
        )
        self.assertIn("X-Admiral-Sig:", message)
        self.assertIn("Subject: clean subject", message)

    def test_supersedes_header_present(self):
        prior = "<prior-uuid@localhost>"
        message, _mid = self._format("body", supersedes_id=prior)
        self.assertIn(f"Supersedes: {prior}", message)

    def test_blank_line_separates_headers_and_body(self):
        message, _mid = self._format("subject\nthe body")
        self.assertIn("\n\n", message)
        headers, _, body = message.partition("\n\n")
        self.assertIn("From: admiral@localhost", headers)
        self.assertIn("the body", body)


# ── 9.4 _parse_sentinel_file ────────────────────────────────────────────────────

class TestParseSentinelFile(unittest.TestCase):
    """_parse_sentinel_file: key=value lines → dict."""

    def _parse(self, content):
        from transport.captain import _parse_sentinel_file
        return _parse_sentinel_file(content)

    def test_valid_key_value_content(self):
        content = "captain_id=test-crew\ncompleted_at=2026-01-01T00:00:00Z\n"
        result = self._parse(content)
        self.assertEqual(result["captain_id"], "test-crew")
        self.assertEqual(result["completed_at"], "2026-01-01T00:00:00Z")

    def test_empty_content_returns_empty_dict(self):
        self.assertEqual(self._parse(""), {})

    def test_lines_without_equals_skipped(self):
        content = "captain_id=test-crew\nno-equals-here\nmode=done\n"
        result = self._parse(content)
        self.assertIn("captain_id", result)
        self.assertIn("mode", result)
        self.assertNotIn("no-equals-here", result)


# ── 9.5 _read_sentinel_file (FakePodmanClient) ──────────────────────────────────

class TestReadSentinelFile(unittest.TestCase):
    """_read_sentinel_file: decode sentinel via Podman archive API, None on failure."""

    CONTAINER = "gs-test-crew"

    def _sentinel_path(self):
        from transport.captain import _SENTINEL_WORKSPACE_PATH
        return _SENTINEL_WORKSPACE_PATH

    def test_returns_decoded_content_when_sentinel_exists(self):
        from transport.captain import _read_sentinel_file
        podman = FakePodmanClient()
        podman.set_archive_file(
            self.CONTAINER,
            self._sentinel_path(),
            b"captain_id=test-crew\ncompleted_at=2026-01-01T00:00:00Z\n",
        )
        result = _read_sentinel_file(podman, self.CONTAINER)
        self.assertIsNotNone(result)
        self.assertIn("captain_id=test-crew", result)

    def test_returns_none_when_archive_api_raises(self):
        from transport.captain import _read_sentinel_file
        podman = FakePodmanClient()
        podman.set_archive_error(
            self.CONTAINER, self._sentinel_path(), RuntimeError("no such container")
        )
        self.assertIsNone(_read_sentinel_file(podman, self.CONTAINER))


if __name__ == "__main__":
    unittest.main()
