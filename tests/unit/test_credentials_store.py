"""Unit tests for transport/credentials.py — CredentialStore (TRN-233 task 1.1).

Covers:
- 0600 file mode and 0700 directory mode (per-backend subdir layout)
- atomic replace (a simulated crash mid-write leaves the old file intact)
- unsupported backend / method pair raises UnsupportedCredential
- one active credential per backend/profile (put replaces)
- status() contains no secret values
- get() registers the payload for log redaction
- profile isolation: two profiles for the same backend are independent
- lazy migration: flat credentials/<backend>.json → <backend>/default.json
- list_profiles: sorted list of profile stems; empty when no profiles
- status_all: two-level {backend: {profile: status_dict}} structure
- validate_profile: valid names pass; invalid names and reserved "default" raise
"""
from __future__ import annotations

import base64
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

from transport.credentials import (
    CredentialStore,
    UnsupportedCredential,
    _MaskedCredential,
    _validate_profile,
)


def _store(tmp) -> CredentialStore:
    return CredentialStore(tmp)


class TestCredentialStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = self._tmp.name
        self.store = CredentialStore(self.data_dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ── modes ──────────────────────────────────────────────────────────────── 

    def test_file_mode_0600_and_dir_0700(self):
        self.store.put("claude", "setup-token", "sk-ant-secret-value")
        cred_dir = os.path.join(self.data_dir, "credentials")
        # New layout: credentials/claude/default.json
        claude_dir = os.path.join(cred_dir, "claude")
        cred_file = os.path.join(claude_dir, "default.json")
        self.assertTrue(os.path.isfile(cred_file))
        self.assertEqual(stat.S_IMODE(os.stat(cred_file).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(claude_dir).st_mode), 0o700)

    # ── atomic replace ───────────────────────────────────────────────────────

    def test_atomic_replace_crash_leaves_old_file(self):
        self.store.put("claude", "api-key", "first-secret-value")
        cred_file = os.path.join(self.data_dir, "credentials", "claude", "default.json")
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
        # No stray temp files left behind in the backend directory.
        claude_dir = os.path.join(self.data_dir, "credentials", "claude")
        leftovers = [n for n in os.listdir(claude_dir) if n.endswith(".tmp")]
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
        # exactly one file for the backend (default profile)
        files = os.listdir(os.path.join(self.data_dir, "credentials", "claude"))
        self.assertEqual(files, ["default.json"])

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

    # ── profile isolation ─────────────────────────────────────────────────────

    def test_profile_isolation(self):
        """Two profiles for the same backend are fully isolated."""
        self.store.put("kiro", "api-key", "default-payload")
        self.store.put("kiro", "api-key", "corp-payload", profile="corp")
        # Each profile returns its own payload.
        got_default = self.store.get("kiro")
        self.assertIsNotNone(got_default)
        self.assertEqual(got_default["payload"], b"default-payload")
        got_corp = self.store.get("kiro", profile="corp")
        self.assertIsNotNone(got_corp)
        self.assertEqual(got_corp["payload"], b"corp-payload")
        # Deleting corp leaves default intact.
        self.assertTrue(self.store.delete("kiro", profile="corp"))
        self.assertIsNone(self.store.get("kiro", profile="corp"))
        self.assertIsNotNone(self.store.get("kiro"))

    # ── lazy migration ─────────────────────────────────────────────────────────

    def test_lazy_migration(self):
        """A flat credentials/<backend>.json is migrated on first default-profile access."""
        cred_dir = os.path.join(self.data_dir, "credentials")
        os.makedirs(cred_dir, exist_ok=True)
        flat_file = os.path.join(cred_dir, "kiro.json")
        payload_b64 = base64.b64encode(b"migrated-payload").decode("ascii")
        envelope = {
            "backend": "kiro",
            "method": "api-key",
            "stored_at": "2026-01-01T00:00:00+00:00",
            "provider": None,
            "payload": payload_b64,
        }
        with open(flat_file, "w") as f:
            json.dump(envelope, f)

        # First access triggers migration.
        got = self.store.get("kiro")
        self.assertIsNotNone(got)
        self.assertEqual(got["payload"], b"migrated-payload")

        # Flat file is gone; profile file now exists.
        self.assertFalse(os.path.exists(flat_file))
        profile_file = os.path.join(cred_dir, "kiro", "default.json")
        self.assertTrue(os.path.exists(profile_file))

    # ── list_profiles ─────────────────────────────────────────────────────────

    def test_list_profiles_sorted(self):
        """list_profiles returns sorted profile stems."""
        self.store.put("kiro", "api-key", "p1")
        self.store.put("kiro", "api-key", "p2", profile="corp")
        self.store.put("kiro", "api-key", "p3", profile="beta")
        profiles = self.store.list_profiles("kiro")
        self.assertEqual(profiles, ["beta", "corp", "default"])

    def test_list_profiles_empty(self):
        """list_profiles returns [] when no profiles exist."""
        profiles = self.store.list_profiles("claude")
        self.assertEqual(profiles, [])

    # ── status_all ────────────────────────────────────────────────────────────

    def test_status_all_two_profiles(self):
        """status_all includes both profiles when two kiro profiles are stored."""
        self.store.put("kiro", "api-key", "k1")
        self.store.put("kiro", "api-key", "k2", profile="corp")
        all_status = self.store.status_all()
        self.assertIn("kiro", all_status)
        kiro_profiles = all_status["kiro"]
        self.assertIn("default", kiro_profiles)
        self.assertIn("corp", kiro_profiles)
        self.assertTrue(kiro_profiles["default"]["configured"])
        self.assertTrue(kiro_profiles["corp"]["configured"])
        # No secret values anywhere.
        blob = json.dumps(all_status)
        self.assertNotIn("k1", blob)
        self.assertNotIn("k2", blob)

    def test_status_all_empty_backend(self):
        """status_all returns {} for backends with no profiles."""
        all_status = self.store.status_all()
        for backend in ("kiro", "claude", "codex"):
            self.assertEqual(all_status[backend], {})

    # ── _validate_profile ─────────────────────────────────────────────────────

    def test_validate_profile_accepts_valid(self):
        """Valid profile names pass without raising."""
        for name in ("corp", "my-profile", "a", "abc123", "x1-y2-z3"):
            with self.subTest(name=name):
                _validate_profile(name)  # should not raise

    def test_validate_profile_rejects_invalid(self):
        """Invalid profile names raise ValueError."""
        for name in ("Bad-Profile", "A", "abc_def", "", "-leading", "trailing-",
                     "has space", "123-", "-123"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    _validate_profile(name)

    def test_validate_profile_rejects_default(self):
        """'default' is reserved and raises ValueError by default."""
        with self.assertRaises(ValueError, msg="'default' should be reserved"):
            _validate_profile("default")

    def test_validate_profile_allows_default_with_flag(self):
        """allow_default=True lets 'default' pass validation."""
        _validate_profile("default", allow_default=True)  # must not raise


if __name__ == "__main__":
    unittest.main()
