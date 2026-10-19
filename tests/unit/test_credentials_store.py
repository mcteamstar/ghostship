"""Unit tests for transport/credentials.py — CredentialStore (TRN-233 task 1.1).

Covers:
- 0600 file mode and 0700 directory mode
- atomic replace (a simulated crash mid-write leaves the old file intact)
- unsupported backend / method pair raises UnsupportedCredential
- one active credential per backend (put replaces)
- status() contains no secret values
- get() registers the payload for log redaction
"""
from __future__ import annotations

import base64
import json
import os
import stat
import unittest
from unittest import mock

from transport.credentials import (
    CredentialStore,
    UnsupportedCredential,
    _MaskedCredential,
)


def _store(tmp) -> CredentialStore:
    return CredentialStore(tmp)


class TestCredentialStore(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = self._tmp.name
        self.store = CredentialStore(self.data_dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ── modes ──────────────────────────────────────────────────────────────── 

    def test_file_mode_0600_and_dir_0700(self):
        self.store.put("claude", "setup-token", "sk-ant-secret-value")
        cred_dir = os.path.join(self.data_dir, "credentials")
        cred_file = os.path.join(cred_dir, "claude.json")
        self.assertTrue(os.path.isfile(cred_file))
        self.assertEqual(stat.S_IMODE(os.stat(cred_file).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(cred_dir).st_mode), 0o700)

    # ── atomic replace ───────────────────────────────────────────────────────

    def test_atomic_replace_crash_leaves_old_file(self):
        self.store.put("claude", "api-key", "first-secret-value")
        cred_file = os.path.join(self.data_dir, "credentials", "claude.json")
        first = json.loads(open(cred_file).read())
        self.assertEqual(first["method"], "api-key")

        # Simulate a crash during the second write: os.replace raises before the
        # temp file is moved into place. The original file must survive intact.
        import transport.credentials as cmod
        real_replace = os.replace

        def boom(src, dst):
            raise OSError("simulated crash before rename")

        orig = cmod.os.replace
        try:
            cmod.os.replace = boom  # type: ignore[assignment]
            with self.assertRaises(OSError):
                self.store.put("claude", "setup-token", "second-secret-value")
        finally:
            cmod.os.replace = real_replace  # type: ignore[assignment]

        # Old file content unchanged.
        after = json.loads(open(cred_file).read())
        self.assertEqual(after["method"], "api-key")
        got = self.store.get("claude")
        self.assertEqual(got["method"], "api-key")
        self.assertEqual(got["payload"], b"first-secret-value")
        # No stray temp files left behind.
        leftovers = [n for n in os.listdir(os.path.join(self.data_dir, "credentials"))
                     if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    # ── validation ───────────────────────────────────────────────────────────

    def test_unsupported_backend_raises(self):
        with self.assertRaises(UnsupportedCredential):
            self.store.put("gemini", "api-key", "x" * 10)

    def test_unsupported_method_for_backend_raises(self):
        # codex has no "setup-token" method.
        with self.assertRaises(UnsupportedCredential):
            self.store.put("codex", "setup-token", "x" * 10)

    def test_get_unknown_backend_raises(self):
        with self.assertRaises(UnsupportedCredential):
            self.store.get("gemini")

    # ── one active credential ────────────────────────────────────────────────

    def test_one_active_credential_per_backend_replaces(self):
        self.store.put("claude", "api-key", "key-aaaaaaaa")
        self.store.put("claude", "setup-token", "token-bbbbbbbb")
        got = self.store.get("claude")
        self.assertEqual(got["method"], "setup-token")
        self.assertEqual(got["payload"], b"token-bbbbbbbb")
        # exactly one file for the backend
        files = os.listdir(os.path.join(self.data_dir, "credentials"))
        self.assertEqual([f for f in files if f.startswith("claude")], ["claude.json"])

    def test_delete_is_idempotent(self):
        self.store.put("kiro", "api-key", "kiro-key-value")
        self.assertTrue(self.store.delete("kiro"))
        self.assertFalse(self.store.delete("kiro"))
        self.assertIsNone(self.store.get("kiro"))

    def test_delete_raises_when_unlink_fails(self):
        # A file that exists but cannot be removed must raise, not report False,
        # so logout can tell "already absent" from "still stored".
        self.store.put("kiro", "api-key", "kiro-key-value")
        with mock.patch("transport.credentials.Path.unlink", side_effect=PermissionError("denied")):
            with self.assertRaises(OSError):
                self.store.delete("kiro")
        self.assertIsNotNone(self.store.get("kiro"))

    # ── provider round-trip for identity-center ──────────────────────────────

    def test_provider_round_trip(self):
        self.store.put(
            "kiro", "identity-center", base64.b64encode(b"rows"),
            provider={"start_url": "https://example.awsapps.com/start", "region": "us-east-1"},
        )
        got = self.store.get("kiro")
        self.assertEqual(got["provider"],
                         {"start_url": "https://example.awsapps.com/start", "region": "us-east-1"})
        self.assertEqual(got["method"], "identity-center")

    # ── status carries no values ──────────────────────────────────────────────

    def test_status_contains_no_values(self):
        secret = "super-secret-anthropic-key-123456"
        self.store.put("claude", "api-key", secret)
        self.store.put(
            "kiro", "identity-center", b"rows-bytes",
            provider={"start_url": "https://example.awsapps.com/start", "region": "eu-west-1"},
        )
        status = self.store.status()
        blob = json.dumps(status)
        self.assertNotIn(secret, blob)
        self.assertNotIn("rows-bytes", blob)
        self.assertTrue(status["claude"]["configured"])
        self.assertEqual(status["claude"]["method"], "api-key")
        self.assertIsNone(status["claude"]["provider"])
        self.assertFalse(status["codex"]["configured"])
        self.assertIsNone(status["codex"]["method"])
        # identity-center provider (non-secret) is exposed in status
        self.assertEqual(status["kiro"]["provider"]["region"], "eu-west-1")

    def test_status_all_backends_present_when_empty(self):
        status = self.store.status()
        self.assertEqual(set(status), {"kiro", "claude", "codex"})
        for b in status.values():
            self.assertFalse(b["configured"])

    # ── redaction registration ────────────────────────────────────────────────

    def test_get_registers_payload_for_redaction(self):
        import transport.security as sec
        secret = "redactable-secret-value-abcdef"
        self.store.put("codex", "api-key", secret)
        self.store.get("codex")
        # After get(), the payload is registered, so redact() scrubs it.
        self.assertNotIn(secret, sec.redact(f"leaking {secret} here"))
        self.assertEqual(sec.redact(f"x {secret} y"), f"x {sec.REDACTION_MARKER} y")

    # ── masked repr ────────────────────────────────────────────────────────────

    def test_masked_repr_hides_payload(self):
        self.store.put("claude", "api-key", "visible-secret-should-not-appear")
        env = {"backend": "claude", "method": "api-key", "stored_at": "t",
               "provider": None}
        r = repr(_MaskedCredential(env))
        self.assertIn("MASKED", r)
        self.assertNotIn("visible-secret", r)


if __name__ == "__main__":
    unittest.main()
