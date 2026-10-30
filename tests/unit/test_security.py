"""Unit tests for transport/security.py — security primitives.

Covers:
- ``TestHashPassword``           — hash_password / verify_password round-trips
- ``TestThrottle``               — lockout, window expiry, reset on success
- ``TestSessionStore``           — issue / validate / revoke with time control
- ``TestValidateStr``            — bounds and pattern validation
- ``TestSecretRedactionFilter``  — exception safety in filter()
"""

from __future__ import annotations

import logging
import time
import unittest

try:
    import security as _security
except ModuleNotFoundError:
    from transport import security as _security


# ── TestHashPassword ──────────────────────────────────────────────────────────


class TestHashPassword(unittest.TestCase):
    """hash_password / verify_password round-trip."""

    def test_correct_password_verifies(self):
        stored = _security.hash_password("correct-horse-battery-staple")
        self.assertTrue(_security.verify_password("correct-horse-battery-staple", stored))

    def test_wrong_password_rejected(self):
        stored = _security.hash_password("correct-horse-battery-staple")
        self.assertFalse(_security.verify_password("wrong-password", stored))

    def test_empty_password_raises(self):
        with self.assertRaises((ValueError, Exception)):
            _security.hash_password("")

    def test_two_hashes_of_same_password_differ(self):
        # Salt should make them distinct.
        h1 = _security.hash_password("same-password")
        h2 = _security.hash_password("same-password")
        self.assertNotEqual(h1, h2)

    def test_verify_empty_password_returns_false(self):
        stored = _security.hash_password("a-real-password")
        self.assertFalse(_security.verify_password("", stored))

    def test_verify_empty_stored_returns_false(self):
        self.assertFalse(_security.verify_password("a-password", ""))

    def test_verify_scrypt_oserror_returns_false(self):
        """scrypt raising OSError (e.g. OpenSSL unavailable) returns False without raising."""
        import hashlib
        from unittest.mock import patch
        stored = (
            "scrypt$32768$8$1$"
            + "00" * 16  # salt_hex (16 bytes = 32 hex chars)
            + "$"
            + "00" * 32  # dk_hex (32 bytes = 64 hex chars)
        )
        with patch.object(hashlib, "scrypt", side_effect=OSError("test")):
            result = _security.verify_password("password", stored)
        self.assertFalse(result)

    def test_verify_scrypt_overflowerror_returns_false(self):
        """scrypt raising OverflowError (e.g. extreme parameters) returns False without raising."""
        import hashlib
        from unittest.mock import patch
        stored = (
            "scrypt$32768$8$1$"
            + "00" * 16
            + "$"
            + "00" * 32
        )
        with patch.object(hashlib, "scrypt", side_effect=OverflowError("test")):
            result = _security.verify_password("password", stored)
        self.assertFalse(result)


# ── TestThrottle ──────────────────────────────────────────────────────────────


class TestThrottle(unittest.TestCase):
    """Sliding-window brute-force throttle."""

    def _throttle(self, max_failures=3, window_secs=300.0):
        return _security.Throttle(max_failures=max_failures, window_secs=window_secs)

    def test_not_locked_initially(self):
        t = self._throttle()
        self.assertFalse(t.is_locked("user", "1.2.3.4"))

    def test_locked_after_max_failures(self):
        t = self._throttle(max_failures=3)
        now = time.time()
        t.record_failure("user", "1.2.3.4", now=now)
        t.record_failure("user", "1.2.3.4", now=now + 1)
        t.record_failure("user", "1.2.3.4", now=now + 2)
        self.assertTrue(t.is_locked("user", "1.2.3.4", now=now + 3))

    def test_not_locked_below_max_failures(self):
        t = self._throttle(max_failures=3)
        now = time.time()
        t.record_failure("user", "1.2.3.4", now=now)
        t.record_failure("user", "1.2.3.4", now=now + 1)
        self.assertFalse(t.is_locked("user", "1.2.3.4", now=now + 2))

    def test_unlocked_after_window_expiry(self):
        t = self._throttle(max_failures=3, window_secs=10.0)
        base = 1_000_000.0
        t.record_failure("user", "1.2.3.4", now=base)
        t.record_failure("user", "1.2.3.4", now=base + 1)
        t.record_failure("user", "1.2.3.4", now=base + 2)
        # Locked within window
        self.assertTrue(t.is_locked("user", "1.2.3.4", now=base + 5))
        # Unlocked after window expires
        self.assertFalse(t.is_locked("user", "1.2.3.4", now=base + 15))

    def test_reset_on_record_success(self):
        t = self._throttle(max_failures=3)
        now = time.time()
        t.record_failure("user", "1.2.3.4", now=now)
        t.record_failure("user", "1.2.3.4", now=now + 1)
        t.record_failure("user", "1.2.3.4", now=now + 2)
        # Locked
        self.assertTrue(t.is_locked("user", "1.2.3.4", now=now + 3))
        # Reset on success
        t.record_success("user", "1.2.3.4")
        self.assertFalse(t.is_locked("user", "1.2.3.4", now=now + 4))

    def test_different_sources_are_independent(self):
        t = self._throttle(max_failures=2)
        now = time.time()
        t.record_failure("user", "source-a", now=now)
        t.record_failure("user", "source-a", now=now + 1)
        # source-a is locked; source-b is clean
        self.assertTrue(t.is_locked("user", "source-a", now=now + 2))
        self.assertFalse(t.is_locked("user", "source-b", now=now + 2))


# ── TestSessionStore ──────────────────────────────────────────────────────────


class TestSessionStore(unittest.TestCase):
    """Bounded, revocable session store — time control via explicit now arg."""

    def _store(self, lifetime_secs=3600.0):
        return _security.SessionStore(lifetime_secs=lifetime_secs)

    def test_issue_then_validate_succeeds(self):
        store = self._store()
        base = 1_000_000.0
        token = store.issue(now=base)
        self.assertTrue(store.validate(token, now=base + 1))

    def test_expired_token_rejected(self):
        store = self._store(lifetime_secs=100.0)
        base = 1_000_000.0
        token = store.issue(now=base)
        # Validate just after expiry
        self.assertFalse(store.validate(token, now=base + 101))

    def test_revoked_token_rejected_immediately(self):
        store = self._store(lifetime_secs=3600.0)
        base = 1_000_000.0
        token = store.issue(now=base)
        # Valid before revocation
        self.assertTrue(store.validate(token, now=base + 1))
        store.revoke(token)
        # Invalid immediately after revocation (well within lifetime)
        self.assertFalse(store.validate(token, now=base + 2))

    def test_unknown_token_rejected(self):
        store = self._store()
        self.assertFalse(store.validate("not-a-real-token"))

    def test_two_tokens_are_distinct(self):
        store = self._store()
        t1 = store.issue()
        t2 = store.issue()
        self.assertNotEqual(t1, t2)

    def test_revoked_token_not_revalidated_after_revocation(self):
        store = self._store(lifetime_secs=3600.0)
        base = 1_000_000.0
        token = store.issue(now=base)
        store.revoke(token)
        self.assertFalse(store.validate(token, now=base + 10))
        self.assertFalse(store.validate(token, now=base + 20))


# ── TestValidateStr ───────────────────────────────────────────────────────────


class TestValidateStr(unittest.TestCase):
    """Input validation — length bounds and pattern checks."""

    def test_valid_input_passes_through(self):
        result = _security.validate_str("hello", max_len=10)
        self.assertEqual(result, "hello")

    def test_too_long_raises_value_error(self):
        with self.assertRaises(ValueError):
            _security.validate_str("a" * 257, max_len=256)

    def test_exactly_max_len_passes(self):
        _security.validate_str("a" * 256, max_len=256)

    def test_disallowed_chars_raises_value_error(self):
        import re
        pattern = re.compile(r"^[a-z]+$")
        with self.assertRaises(ValueError):
            _security.validate_str("UPPER", pattern=pattern)

    def test_pattern_match_passes(self):
        import re
        pattern = re.compile(r"^[a-z]+$")
        result = _security.validate_str("lower", pattern=pattern)
        self.assertEqual(result, "lower")

    def test_min_len_too_short_raises(self):
        with self.assertRaises(ValueError):
            _security.validate_str("", min_len=1)

    def test_non_string_raises(self):
        with self.assertRaises(ValueError):
            _security.validate_str(123, max_len=10)  # type: ignore[arg-type]


# ── TestSecretRedactionFilter ─────────────────────────────────────────────────


class TestSecretRedactionFilter(unittest.TestCase):
    """SecretRedactionFilter must not crash even on pathological records."""

    def _make_record(self, msg, args=None):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=args or (),
            exc_info=None,
        )
        return record

    def test_filter_returns_true(self):
        filt = _security.SecretRedactionFilter()
        record = self._make_record("some message")
        result = filt.filter(record)
        self.assertTrue(result)

    def test_exception_in_redaction_returns_original_message(self):
        """A record whose msg is not a string should not crash the filter."""
        filt = _security.SecretRedactionFilter()
        # Pass a non-string msg — the filter must still return True (not crash).
        record = self._make_record(42)
        result = filt.filter(record)
        self.assertTrue(result)

    def test_secret_is_redacted_in_message(self):
        secret = "supersecret_value_32chars_padding"
        _security.register_secret(secret)
        try:
            filt = _security.SecretRedactionFilter()
            record = self._make_record(f"the secret is {secret} here")
            filt.filter(record)
            self.assertNotIn(secret, str(record.msg))
            self.assertIn(_security.REDACTION_MARKER, str(record.msg))
        finally:
            _security.deregister_secret(secret)

    def test_filter_with_none_exc_info(self):
        filt = _security.SecretRedactionFilter()
        record = self._make_record("normal message")
        record.exc_info = None
        result = filt.filter(record)
        self.assertTrue(result)


# ─────────────────────────────────────────────────────────────────────────────
# T4 — TestCspNonce, TestNeedsRehash, TestOutputEncoding  (TRN-292)
# ─────────────────────────────────────────────────────────────────────────────

import re
from unittest.mock import patch
from urllib.parse import unquote


class TestCspNonce(unittest.TestCase):
    """generate_csp_nonce: length, charset, uniqueness, return type (N1–N4)."""

    def _nonce(self) -> str:
        return _security.generate_csp_nonce()

    # ── N1 — length ≥ 16 chars ────────────────────────────────────────────

    def test_n1_length_at_least_16(self):
        """N1: nonce is at least 16 characters long."""
        self.assertGreaterEqual(len(self._nonce()), 16)

    # ── N2 — charset is URL-safe base64 only ─────────────────────────────

    def test_n2_charset_url_safe_base64(self):
        """N2: only [A-Za-z0-9_-] — no padding '=' and no '+' or '/'."""
        nonce = self._nonce()
        self.assertTrue(
            re.fullmatch(r"[A-Za-z0-9_\-]+", nonce),
            f"Nonce contains unexpected characters: {nonce!r}",
        )

    # ── N3 — uniqueness: 100 calls all distinct ───────────────────────────

    def test_n3_uniqueness_100_calls(self):
        """N3: 100 calls produce 100 distinct nonces."""
        nonces = [self._nonce() for _ in range(100)]
        self.assertEqual(len(set(nonces)), 100)

    # ── N4 — return type is str ───────────────────────────────────────────

    def test_n4_return_type_is_str(self):
        """N4: return type is str."""
        self.assertIsInstance(self._nonce(), str)


class TestNeedsRehash(unittest.TestCase):
    """needs_rehash: argon2 available/unavailable and stored hash prefixes (R1–R5)."""

    # ── R1 — argon2 available + argon2 stored → False ────────────────────

    def test_r1_argon2_available_argon2_stored_false(self):
        """R1: argon2 available + $argon2 stored → needs_rehash is False."""
        with patch.object(_security, "_argon2_available", return_value=True):
            result = _security.needs_rehash("$argon2id$v=19$m=65536,t=3,p=4$salt$hash")
        self.assertFalse(result)

    # ── R2 — argon2 available + scrypt stored → True ─────────────────────

    def test_r2_argon2_available_scrypt_stored_true(self):
        """R2: argon2 available + scrypt stored → needs_rehash is True (upgrade candidate)."""
        with patch.object(_security, "_argon2_available", return_value=True):
            result = _security.needs_rehash("scrypt$32768$8$1$aabbcc$ddeeff")
        self.assertTrue(result)

    # ── R3 — argon2 available + bcrypt stored → True ─────────────────────

    def test_r3_argon2_available_bcrypt_stored_true(self):
        """R3: argon2 available + bcrypt stored → needs_rehash is True."""
        with patch.object(_security, "_argon2_available", return_value=True):
            result = _security.needs_rehash("$2b$12$somebcrypthash")
        self.assertTrue(result)

    # ── R4 — no argon2 + scrypt stored → False ───────────────────────────

    def test_r4_no_argon2_scrypt_stored_false(self):
        """R4: argon2 unavailable + scrypt stored → needs_rehash is False."""
        with patch.object(_security, "_argon2_available", return_value=False):
            result = _security.needs_rehash("scrypt$32768$8$1$aabbcc$ddeeff")
        self.assertFalse(result)

    # ── R5 — no argon2 + plaintext stored → True ─────────────────────────

    def test_r5_no_argon2_plaintext_stored_true(self):
        """R5: argon2 unavailable + plaintext (no prefix) → needs_rehash is True."""
        with patch.object(_security, "_argon2_available", return_value=False):
            result = _security.needs_rehash("plaintextpassword")
        self.assertTrue(result)


class TestOutputEncoding(unittest.TestCase):
    """encode_html_text, encode_html_attr, encode_url_component (E1–E5)."""

    # ── E1 — encode_html_text escapes <>&  but not quotes ────────────────

    def test_e1_html_text_escapes_lt_gt_amp(self):
        """E1: <, >, & are escaped; ' and \" are not."""
        result = _security.encode_html_text('<script>alert("x&y")</script>')
        self.assertIn("&lt;", result)
        self.assertIn("&gt;", result)
        self.assertIn("&amp;", result)
        # Quotes must NOT be escaped in a text context.
        self.assertNotIn("&quot;", result)
        self.assertNotIn("&#x27;", result)

    # ── E2 — encode_html_attr escapes <>&" ────────────────────────────────

    def test_e2_html_attr_escapes_lt_gt_amp_quot(self):
        """E2: <, >, &, and \" are all escaped in an attribute context."""
        result = _security.encode_html_attr('<a href="x&y">')
        self.assertIn("&lt;", result)
        self.assertIn("&gt;", result)
        self.assertIn("&amp;", result)
        self.assertIn("&quot;", result)

    # ── E3 — encode_url_component encodes spaces and slashes ─────────────

    def test_e3_url_component_encodes_space_and_slash(self):
        """E3: space → %20, / → %2F."""
        result = _security.encode_url_component("hello world/path")
        self.assertIn("%20", result)
        self.assertIn("%2F", result)

    # ── E4 — encode_url_component round-trips via urllib.parse.unquote ───

    def test_e4_url_component_roundtrip(self):
        """E4: unquote(encode(x)) == x."""
        original = "hello world/path?q=1&r=2"
        encoded = _security.encode_url_component(original)
        self.assertEqual(unquote(encoded), original)

    # ── E5 — encode_html_text passes safe ASCII through unchanged ─────────

    def test_e5_html_text_safe_ascii_unchanged(self):
        """E5: safe ASCII (no HTML-special chars) passes through unchanged."""
        safe = "Hello, World! This is fine 123."
        result = _security.encode_html_text(safe)
        self.assertEqual(result, safe)


if __name__ == "__main__":
    unittest.main()
