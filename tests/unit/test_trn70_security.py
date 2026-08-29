"""Tests for trn-70-security-hardening: spec-scenario coverage across the four
capabilities (authentication-security, transport-security, secrets-management,
input-validation) plus audit logging.

Each test names the spec scenario it exercises so the mapping stays visible.
Uses the same dependency-free import stub as the other transport tests.
"""
from __future__ import annotations

import logging
import re
import time
import unittest

from transport import security as sec

# Import server through the shared stub harness (stubs mcp/starlette/httpx).
from tests.unit.test_file_transfer import server


# ── secrets-management ────────────────────────────────────────────────────────

class TestSecretsManagement(unittest.TestCase):
    def test_get_secret_prefers_file_over_env(self):
        """Secret sourced at runtime: managed file wins over env var."""
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s"
            f.write_text("  file-value-123456  \n")
            os.environ["TRN70_TEST_ENV"] = "env-value-abcdef"
            try:
                val = sec.get_secret("x", secret_file=str(f), env_var="TRN70_TEST_ENV")
                self.assertEqual(val, "file-value-123456")
            finally:
                os.environ.pop("TRN70_TEST_ENV", None)

    def test_get_secret_falls_back_to_env(self):
        import os

        os.environ["TRN70_TEST_ENV2"] = "env-fallback-xyz789"
        try:
            val = sec.get_secret("x", secret_file="/nonexistent/trn70", env_var="TRN70_TEST_ENV2")
            self.assertEqual(val, "env-fallback-xyz789")
        finally:
            os.environ.pop("TRN70_TEST_ENV2", None)

    def test_secret_redacted_in_logs(self):
        """Secret redacted in output: a registered secret never reaches a log line."""
        secret = "super-secret-value-9999"
        sec.register_secret(secret)
        filt = sec.SecretRedactionFilter()
        rec = logging.LogRecord(
            "n", logging.INFO, __file__, 1,
            "connecting with key %s done", (secret,), None,
        )
        filt.filter(rec)
        rendered = rec.getMessage()
        self.assertNotIn(secret, rendered)
        self.assertIn(sec.REDACTION_MARKER, rendered)

    def test_redact_helper(self):
        sec.register_secret("aVeryLongSecretToken")
        self.assertNotIn("aVeryLongSecretToken", sec.redact("token=aVeryLongSecretToken;"))

    def test_secret_redacted_in_exc_info(self):
        """Secret value in an exception traceback is scrubbed by the filter."""
        import sys
        secret = "exc-info-secret-abc123456789xyz"
        sec.register_secret(secret)
        try:
            raise ValueError(f"connection failed with key {secret}")
        except ValueError:
            exc_info = sys.exc_info()

        rec = logging.LogRecord(
            "n", logging.ERROR, __file__, 1, "db error", (), exc_info,
        )
        filt = sec.SecretRedactionFilter()
        filt.filter(rec)
        # exc_info should be cleared and exc_text should carry the redacted string
        self.assertIsNone(rec.exc_info)
        self.assertIsNotNone(rec.exc_text)
        self.assertNotIn(secret, rec.exc_text)
        self.assertIn(sec.REDACTION_MARKER, rec.exc_text)


# ── authentication-security: credential storage ──────────────────────────────

class TestCredentialStorage(unittest.TestCase):
    def test_hash_is_not_plaintext_and_verifies(self):
        """Password persisted at registration: only a salted adaptive hash stored."""
        pw = "correct horse battery staple"
        h = sec.hash_password(pw)
        self.assertNotIn(pw, h)
        self.assertTrue(sec.verify_password(pw, h))
        self.assertFalse(sec.verify_password("wrong", h))

    def test_hash_is_salted(self):
        """Two hashes of the same password differ (unique salt)."""
        self.assertNotEqual(sec.hash_password("pw"), sec.hash_password("pw"))

    def test_needs_rehash_flags_legacy(self):
        """A non-preferred scheme is flagged for opportunistic rehash-on-login."""
        legacy = "md5$deadbeef"
        self.assertTrue(sec.needs_rehash(legacy))


# ── authentication-security: brute-force throttling ──────────────────────────

class TestThrottling(unittest.TestCase):
    def test_locks_after_threshold(self):
        """Repeated failures locked out once threshold exceeded in the window."""
        t = sec.Throttle(max_failures=3, window_secs=100)
        now = 1000.0
        for _ in range(3):
            t.record_failure("alice", "1.2.3.4", now=now)
        self.assertTrue(t.is_locked("alice", "1.2.3.4", now=now))
        self.assertFalse(t.is_locked("bob", "1.2.3.4", now=now))

    def test_success_resets_counter(self):
        """Successful login resets the failed-attempt counter to zero."""
        t = sec.Throttle(max_failures=3, window_secs=100)
        now = 1000.0
        t.record_failure("alice", "s", now=now)
        t.record_failure("alice", "s", now=now)
        t.record_success("alice", "s")
        self.assertFalse(t.is_locked("alice", "s", now=now))

    def test_window_expiry(self):
        """Old failures fall out of the sliding window."""
        t = sec.Throttle(max_failures=2, window_secs=10)
        t.record_failure("a", "s", now=100.0)
        t.record_failure("a", "s", now=100.0)
        self.assertTrue(t.is_locked("a", "s", now=105.0))
        self.assertFalse(t.is_locked("a", "s", now=120.0))


# ── authentication-security: bounded, revocable sessions ─────────────────────

class TestSessions(unittest.TestCase):
    def test_session_expires(self):
        """Session expires: rejected once age exceeds max lifetime."""
        s = sec.SessionStore(lifetime_secs=100)
        tok = s.issue(now=1000.0)
        self.assertTrue(s.validate(tok, now=1050.0))
        self.assertFalse(s.validate(tok, now=1101.0))

    def test_session_revoked(self):
        """Session revoked: subsequent requests rejected before expiry."""
        s = sec.SessionStore(lifetime_secs=1000)
        tok = s.issue(now=1000.0)
        self.assertTrue(s.validate(tok, now=1001.0))
        s.revoke(tok)
        self.assertFalse(s.validate(tok, now=1002.0))

    def test_unknown_token_rejected(self):
        s = sec.SessionStore()
        self.assertFalse(s.validate("never-issued"))


# ── input-validation ─────────────────────────────────────────────────────────

class TestInputValidation(unittest.TestCase):
    def test_rejects_malformed(self):
        """Malformed input rejected: wrong format is refused."""
        pat = re.compile(r"[a-z]+")
        with self.assertRaises(ValueError):
            sec.validate_str("ABC123", pattern=pat, field="name")
        with self.assertRaises(ValueError):
            sec.validate_str("x" * 500, max_len=10)
        with self.assertRaises(ValueError):
            sec.validate_str(123)  # type: ignore[arg-type]

    def test_accepts_valid(self):
        self.assertEqual(sec.validate_str("abc", pattern=re.compile(r"[a-z]+")), "abc")

    def test_output_encoding(self):
        """Reflected value encoded: script markup rendered as data, not executed."""
        payload = "<script>alert(1)</script>"
        self.assertNotIn("<script>", sec.encode_html_text(payload))
        self.assertIn("&lt;script&gt;", sec.encode_html_text(payload))
        self.assertIn("&quot;", sec.encode_html_attr('a"b'))
        self.assertEqual(sec.encode_url_component("a b/c"), "a%20b%2Fc")

    def test_server_crew_id_validator_present(self):
        """Server still validates crew_id server-side regardless of client checks."""
        self.assertTrue(server.CREW_ID_RE.fullmatch("valid-crew-1"))
        self.assertIsNone(server.CREW_ID_RE.fullmatch("Invalid_Crew!"))


# ── transport-security ────────────────────────────────────────────────────────

class TestTransportSecurity(unittest.TestCase):
    def test_headers_on_https_include_hsts(self):
        """HSTS header present with non-zero max-age on HTTPS responses."""
        headers = dict(sec.security_headers(https=True))
        self.assertIn(b"strict-transport-security", headers)
        self.assertIn(b"max-age=", headers[b"strict-transport-security"])
        self.assertNotIn(b"max-age=0", headers[b"strict-transport-security"])

    def test_baseline_headers_present(self):
        """Headers on external response: nosniff, clickjacking, CSP."""
        headers = dict(sec.security_headers(https=False))
        self.assertEqual(headers[b"x-content-type-options"], b"nosniff")
        self.assertEqual(headers[b"x-frame-options"], b"DENY")
        # CSP present (report-only during staged rollout by default).
        self.assertTrue(
            b"content-security-policy-report-only" in headers
            or b"content-security-policy" in headers
        )

    def test_csp_enforce_flag(self):
        headers = dict(sec.security_headers(https=True, csp_report_only=False))
        self.assertIn(b"content-security-policy", headers)
        self.assertNotIn(b"content-security-policy-report-only", headers)

    def test_no_hsts_on_plaintext(self):
        headers = dict(sec.security_headers(https=False))
        self.assertNotIn(b"strict-transport-security", headers)

    def test_middleware_is_https_detection(self):
        mw = server.SecurityHeadersMiddleware(None)
        self.assertTrue(mw._is_https({"scheme": "https", "headers": []}))
        self.assertTrue(mw._is_https({"scheme": "http", "headers": [(b"x-forwarded-proto", b"https")]}))
        self.assertFalse(mw._is_https({"scheme": "http", "headers": []}))

    def test_plaintext_hit_logged_during_monitoring_window(self):
        """Plaintext HTTP hits are logged during the monitoring window (task 3.4).

        When GA_ENFORCE_HTTPS_REDIRECT=0 (monitoring phase) a plaintext request
        should emit a log entry so operators can identify affected clients before
        the cutover.
        """
        import asyncio

        log_records = []

        class _CapturingHandler(logging.Handler):
            def emit(self, record):
                log_records.append(record.getMessage())

        handler = _CapturingHandler()
        # Attach to the transport server logger
        import transport.server as _srv
        srv_logger = logging.getLogger("transport.server")
        srv_logger.addHandler(handler)
        old_level = srv_logger.level
        srv_logger.setLevel(logging.INFO)

        try:
            collected = []

            async def _dummy_app(scope, receive, send):
                pass

            async def _dummy_send(msg):
                collected.append(msg)

            mw = server.SecurityHeadersMiddleware(
                _dummy_app, enable_headers=True, enforce_redirect=False, csp_enforce=False
            )
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/mcp",
                "scheme": "http",
                "headers": [(b"x-forwarded-for", b"10.0.0.1")],
                "query_string": b"",
            }
            asyncio.run(mw(scope, None, _dummy_send))
        finally:
            srv_logger.removeHandler(handler)
            srv_logger.setLevel(old_level)

        plaintext_logs = [r for r in log_records if "plaintext" in r.lower()]
        self.assertTrue(
            len(plaintext_logs) >= 1,
            f"Expected a plaintext hit log entry, got: {log_records}",
        )
        # Should include the source IP
        self.assertTrue(
            any("10.0.0.1" in r for r in plaintext_logs),
            f"Expected source IP in plaintext log, got: {plaintext_logs}",
        )


# ── audit logging ─────────────────────────────────────────────────────────────

class TestAuditLogging(unittest.TestCase):
    def test_login_attempt_recorded(self):
        """Login attempt recorded: outcome, timestamp, account, source captured."""
        captured = []
        event = sec.audit_auth_event(
            action="login", outcome="failure", account="alice", source="1.2.3.4",
            emit=captured.append,
        )
        self.assertEqual(event["action"], "login")
        self.assertEqual(event["outcome"], "failure")
        self.assertEqual(event["account"], "alice")
        self.assertEqual(event["source"], "1.2.3.4")
        self.assertTrue(event["ts"])
        self.assertEqual(len(captured), 1)

    def test_audit_event_has_no_credential(self):
        """Audit events contain no credential or token value."""
        secret_token = "tok-abcdefghij-secret"
        sec.register_secret(secret_token)
        captured = []
        # Even if a caller mistakenly passed a secret-shaped account, redaction runs.
        sec.audit_auth_event(
            action="login", outcome="success", account=secret_token, source="s",
            emit=captured.append,
        )
        self.assertNotIn(secret_token, captured[0])


if __name__ == "__main__":
    unittest.main()
