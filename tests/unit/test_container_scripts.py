"""Unit tests for transport/container_scripts/*.py (TRN-74).

These scripts run inside crew containers, but they are plain modules with no
KiroCrew or Podman dependency, so they import and run directly here — no
container, no PodmanClient mock. The container_scripts/ directory is added to
sys.path so each script imports as a top-level module.
"""
from __future__ import annotations

import base64
import importlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2] / "transport" / "container_scripts"
)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

inject_auth = importlib.import_module("inject_auth")
read_auth = importlib.import_module("read_auth")
wipe_auth = importlib.import_module("wipe_auth")
read_mail_counts = importlib.import_module("read_mail_counts")
read_mail_subjects = importlib.import_module("read_mail_subjects")
patch_models = importlib.import_module("patch_models")
inject_policy = importlib.import_module("inject_policy")


def _make_auth_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()


class InjectAuthTests(unittest.TestCase):
    def test_inserts_rows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "data.sqlite3")
            _make_auth_db(db)
            rows = [["token", "abc123"], ["region", "us-east-1"]]
            b64 = base64.b64encode(json.dumps(rows).encode()).decode()

            count = inject_auth.inject_auth(db, b64)

            self.assertEqual(count, 2)
            conn = sqlite3.connect(db)
            stored = dict(conn.execute("SELECT key, value FROM auth_kv").fetchall())
            conn.close()
            self.assertEqual(stored, {"token": "abc123", "region": "us-east-1"})

    def test_replaces_existing_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "data.sqlite3")
            _make_auth_db(db)
            inject_auth.inject_auth(
                db, base64.b64encode(json.dumps([["k", "old"]]).encode()).decode()
            )
            inject_auth.inject_auth(
                db, base64.b64encode(json.dumps([["k", "new"]]).encode()).decode()
            )
            conn = sqlite3.connect(db)
            value = conn.execute("SELECT value FROM auth_kv WHERE key='k'").fetchone()[0]
            conn.close()
            self.assertEqual(value, "new")


class ReadAuthTests(unittest.TestCase):
    def test_reads_rows_as_b64_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "data.sqlite3")
            _make_auth_db(db)
            conn = sqlite3.connect(db)
            conn.execute("INSERT INTO auth_kv VALUES ('token', 'xyz')")
            conn.commit()
            conn.close()

            b64 = read_auth.read_auth(db)
            rows = json.loads(base64.b64decode(b64).decode())
            self.assertEqual(rows, [["token", "xyz"]])

    def test_empty_db_returns_empty_string(self) -> None:
        # A registration-only / empty auth_kv yields "" so the caller can treat
        # it as "no auth" (aligns with the TRN-78 Bug 1 direction: an empty
        # table must not read as a completed login).
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "data.sqlite3")
            _make_auth_db(db)
            self.assertEqual(read_auth.read_auth(db), "")


class WipeAuthTests(unittest.TestCase):
    def test_deletes_all_rows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "data.sqlite3")
            _make_auth_db(db)
            conn = sqlite3.connect(db)
            conn.executemany(
                "INSERT INTO auth_kv VALUES (?, ?)", [("a", "1"), ("b", "2")]
            )
            conn.commit()
            conn.close()

            wipe_auth.wipe_auth(db)

            conn = sqlite3.connect(db)
            remaining = conn.execute("SELECT COUNT(*) FROM auth_kv").fetchone()[0]
            conn.close()
            self.assertEqual(remaining, 0)


class ReadMailCountsTests(unittest.TestCase):
    def _make_maildir(self, root: str, name: str, new: int, cur: int) -> None:
        base = os.path.join(root, name)
        for sub, n in (("new", new), ("cur", cur)):
            d = os.path.join(base, sub)
            os.makedirs(d, exist_ok=True)
            for i in range(n):
                Path(os.path.join(d, f"msg{i}")).write_text("x")

    def test_counts_maildir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self._make_maildir(td, "ghost", new=2, cur=1)
            self._make_maildir(td, "raven", new=0, cur=0)
            counts = read_mail_counts.read_counts(["ghost", "raven"], root=td)
            # ghost = 3, raven omitted (zero)
            self.assertEqual(counts, {"ghost": 3})

    def test_counts_legacy_mbox(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            Path(os.path.join(td, "spectre")).write_text(
                "From a\nbody\nFrom b\nbody\n"
            )
            counts = read_mail_counts.read_counts(["spectre"], root=td)
            self.assertEqual(counts, {"spectre": 2})

    def test_missing_mailbox_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(read_mail_counts.read_counts(["nope"], root=td), {})


class ReadMailSubjectsTests(unittest.TestCase):
    def test_reads_subjects_from_maildir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = os.path.join(td, "ghost", "new")
            os.makedirs(base, exist_ok=True)
            Path(os.path.join(base, "m1")).write_text(
                "From: a@localhost\nSubject: hello world\n\nbody\n"
            )
            Path(os.path.join(base, "m2")).write_text(
                "From: b@localhost\nSubject: second\n\nbody\n"
            )
            subjects = read_mail_subjects.read_subjects(["ghost"], root=td)
            self.assertEqual(sorted(subjects["ghost"]), ["hello world", "second"])

    def test_empty_mailbox_yields_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            subjects = read_mail_subjects.read_subjects(["ghost"], root=td)
            self.assertEqual(subjects, {"ghost": []})

    def test_reads_subjects_from_legacy_mbox(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            Path(os.path.join(td, "captain")).write_text(
                "From a\nSubject: order one\n\nbody\n"
                "From b\nSubject: order two\n\nbody\n"
            )
            subjects = read_mail_subjects.read_subjects(["captain"], root=td)
            self.assertEqual(subjects["captain"], ["order one", "order two"])


class PatchModelsTests(unittest.TestCase):
    def _write_agent(self, d: str, name: str, data: dict) -> None:
        Path(os.path.join(d, name)).write_text(json.dumps(data))

    def test_patches_eligible_agents(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self._write_agent(td, "ghost.json", {"name": "ghost", "model": "old"})
            self._write_agent(td, "raven.json", {"name": "raven"})  # no model
            self._write_agent(td, "auto.json", {"name": "a", "model": "auto"})
            self._write_agent(td, "same.json", {"name": "s", "model": "target"})
            self._write_agent(td, "._skip.json", {"name": "x", "model": "old"})

            patched = patch_models.patch_models(td, "target")

            # Only ghost.json is eligible: had a model, not auto/None/target.
            self.assertEqual(patched, ["ghost.json"])
            ghost = json.loads(Path(os.path.join(td, "ghost.json")).read_text())
            self.assertEqual(ghost["model"], "target")
            # AppleDouble file untouched.
            skip = json.loads(Path(os.path.join(td, "._skip.json")).read_text())
            self.assertEqual(skip["model"], "old")

    def test_no_eligible_agents_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self._write_agent(td, "raven.json", {"name": "raven"})
            self.assertEqual(patch_models.patch_models(td, "target"), [])


class InjectPolicyTests(unittest.TestCase):
    """Unit tests for inject_policy.inject_policy() (TRN-53).

    The script runs inside a container, but it has no KiroCrew or Podman
    dependency so it imports and runs directly here.
    """

    _SAMPLE_POLICY = {
        "version": "1",
        "rules": [{"id": "no-internet"}],
        "identity": {"issuer": "ghostship"},
    }

    def _run(self, policy: dict, key: str, tmp_dir: str) -> tuple[dict, dict]:
        """Run inject_policy and return (security_policy, admission_policy) as dicts."""
        inject_policy.inject_policy(tmp_dir, policy, key)
        security = json.loads(Path(os.path.join(tmp_dir, "security_policy.json")).read_text())
        admission = json.loads(Path(os.path.join(tmp_dir, "admission_policy.json")).read_text())
        return security, admission

    # 4.1 -- existing call sites now use policy_signing_key as the key name
    def test_inject_policy_accepts_policy_signing_key_param(self) -> None:
        """inject_policy() signature accepts policy_signing_key (not admiral_secret)."""
        with tempfile.TemporaryDirectory() as td:
            policy_signing_key = "deadbeef" * 8
            # Should not raise -- the renamed param is the correct API
            version = inject_policy.inject_policy(td, self._SAMPLE_POLICY.copy(), policy_signing_key)
            self.assertEqual(version, "1")

    # 4.2 -- admission_policy.json contains policy_signing_key, NOT admiral_secret
    def test_admission_policy_uses_policy_signing_key_in_trust_keys(self) -> None:
        """admission_policy.json trust_keys carries the policy_signing_key value."""
        with tempfile.TemporaryDirectory() as td:
            policy_signing_key = "aabbccdd" * 8
            _, admission = self._run(self._SAMPLE_POLICY.copy(), policy_signing_key, td)

            self.assertIn("trust_keys", admission)
            self.assertEqual(admission["trust_keys"]["ghostship"], policy_signing_key)

    def test_admission_policy_does_not_contain_admiral_secret_key(self) -> None:
        """admission_policy.json must NOT contain an 'admiral_secret' key."""
        with tempfile.TemporaryDirectory() as td:
            _, admission = self._run(self._SAMPLE_POLICY.copy(), "key123", td)
            admission_str = json.dumps(admission)
            self.assertNotIn("admiral_secret", admission_str,
                             "admission_policy.json must not expose admiral_secret")

    def test_security_policy_is_signed_with_policy_signing_key(self) -> None:
        """security_policy.json signature verifies with policy_signing_key."""
        import hashlib
        import hmac as _hmac
        with tempfile.TemporaryDirectory() as td:
            policy_signing_key = "sigkey" * 8
            security, _ = self._run(self._SAMPLE_POLICY.copy(), policy_signing_key, td)

            sig = security["identity"]["signature"]
            # Recompute expected signature using the same canonicalization
            body = {k: v for k, v in security.items() if k != "identity"}
            identity_rest = {k: v for k, v in security.get("identity", {}).items()
                             if k != "signature"}
            if identity_rest:
                body["identity"] = identity_rest
            payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            expected = _hmac.new(policy_signing_key.encode(), payload, hashlib.sha256).hexdigest()
            self.assertEqual(sig, expected)


if __name__ == "__main__":
    unittest.main()
