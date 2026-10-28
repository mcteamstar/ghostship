"""Unit tests for transport/container_scripts/.

Covers:
- ``TestSignPolicy``    — inject_policy.py sign_policy HMAC round-trip
- ``TestTransferRaw``   — transfer_raw.py normal extraction, path-traversal rejection

The container_scripts directory is added to sys.path so modules can be
imported by name without the transport package prefix.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import pathlib
import sys
import tarfile
import tempfile
import unittest

# Add container_scripts to sys.path so inject_policy / transfer_raw import cleanly.
_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "transport" / "container_scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import inject_policy as _inject_policy  # noqa: E402
import transfer_raw as _transfer_raw    # noqa: E402


# ── TestSignPolicy ────────────────────────────────────────────────────────────


class TestSignPolicy(unittest.TestCase):
    """sign_policy round-trip: signed policy can be independently verified."""

    _SECRET = "test-signing-secret-padded-value"

    def _make_policy(self, version="1"):
        return {
            "version": version,
            "rules": {"allow_all": True},
            "identity": {"issuer": "test"},
        }

    def _verify_sig(self, policy: dict, secret: str) -> bool:
        """Re-derive the HMAC and compare to the stored signature."""
        body = {k: v for k, v in policy.items() if k != "identity"}
        identity = policy.get("identity", {})
        rest = {k: v for k, v in identity.items() if k != "signature"}
        if rest:
            body["identity"] = rest
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected = hmac.HMAC(
            secret.encode("utf-8"),
            payload,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, policy.get("identity", {}).get("signature", ""))

    def test_sign_policy_adds_signature(self):
        policy = self._make_policy()
        signed = _inject_policy.sign_policy(policy, self._SECRET)
        self.assertIn("signature", signed.get("identity", {}))

    def test_sign_policy_signature_is_valid(self):
        policy = self._make_policy()
        signed = _inject_policy.sign_policy(policy, self._SECRET)
        self.assertTrue(self._verify_sig(signed, self._SECRET))

    def test_sign_policy_wrong_secret_fails(self):
        policy = self._make_policy()
        signed = _inject_policy.sign_policy(policy, self._SECRET)
        self.assertFalse(self._verify_sig(signed, "wrong-secret"))

    def test_sign_policy_idempotent_signature(self):
        """Signing the same policy with the same secret yields the same sig."""
        policy = self._make_policy()
        sig1 = _inject_policy.sign_policy(policy, self._SECRET)["identity"]["signature"]
        sig2 = _inject_policy.sign_policy(policy, self._SECRET)["identity"]["signature"]
        self.assertEqual(sig1, sig2)

    def test_sign_policy_issuer_covered(self):
        """Changing identity.issuer produces a different signature."""
        p1 = {"version": "1", "rules": {}, "identity": {"issuer": "issuer-a"}}
        p2 = {"version": "1", "rules": {}, "identity": {"issuer": "issuer-b"}}
        sig1 = _inject_policy.sign_policy(p1, self._SECRET)["identity"]["signature"]
        sig2 = _inject_policy.sign_policy(p2, self._SECRET)["identity"]["signature"]
        self.assertNotEqual(sig1, sig2)

    def test_inject_policy_writes_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = self._make_policy()
            version = _inject_policy.inject_policy(tmpdir, policy, self._SECRET)
            self.assertEqual(version, "1")
            self.assertTrue((pathlib.Path(tmpdir) / "security_policy.json").is_file())
            self.assertTrue((pathlib.Path(tmpdir) / "admission_policy.json").is_file())

    def test_inject_policy_signed_content_verifiable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = self._make_policy()
            _inject_policy.inject_policy(tmpdir, policy, self._SECRET)
            stored = json.loads((pathlib.Path(tmpdir) / "security_policy.json").read_text())
            self.assertTrue(self._verify_sig(stored, self._SECRET))


# ── TestTransferRaw ───────────────────────────────────────────────────────────


def _make_tar(contents: dict[str, bytes]) -> bytes:
    """Return tar archive bytes with the given {member_name: data} dict."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in contents.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TestTransferRaw(unittest.TestCase):
    """transfer_raw.transfer() — copy and unpack modes."""

    def test_plain_copy_writes_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "source.bin")
            dest_path = os.path.join(tmpdir, "dest.bin")
            stage_path = os.path.join(tmpdir, "stage")
            os.makedirs(stage_path)
            with open(src_path, "wb") as f:
                f.write(b"hello world")
            result = _transfer_raw.transfer(src_path, dest_path, stage_path, unpack=False)
            self.assertIn("wrote", result)
            self.assertEqual(pathlib.Path(dest_path).read_bytes(), b"hello world")
            # Stage directory cleaned up
            self.assertFalse(os.path.exists(stage_path))

    def test_unpack_mode_extracts_archive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_data = _make_tar({"readme.txt": b"archive content"})
            src_path = os.path.join(tmpdir, "archive.tar")
            dest_path = os.path.join(tmpdir, "extracted")
            stage_path = os.path.join(tmpdir, "stage_unpack")
            os.makedirs(stage_path)
            with open(src_path, "wb") as f:
                f.write(archive_data)
            result = _transfer_raw.transfer(src_path, dest_path, stage_path, unpack=True)
            self.assertIn("unpacked", result)
            extracted_file = pathlib.Path(dest_path) / "readme.txt"
            self.assertTrue(extracted_file.exists())
            self.assertEqual(extracted_file.read_bytes(), b"archive content")

    def test_stage_cleaned_on_error(self):
        """Stage directory is removed even when transfer fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_path = os.path.join(tmpdir, "stage_err")
            os.makedirs(stage_path)
            # Source does not exist — should raise, but stage must be cleaned up.
            try:
                _transfer_raw.transfer(
                    os.path.join(tmpdir, "missing.bin"),
                    os.path.join(tmpdir, "dest.bin"),
                    stage_path,
                    unpack=False,
                )
            except Exception:
                pass
            self.assertFalse(os.path.exists(stage_path))

    @unittest.skipIf(sys.version_info < (3, 12), "filter='data' only on Python 3.12+")
    def test_unpack_uses_data_filter_python312(self):
        """On Python 3.12+, extractall should not raise for safe member names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_data = _make_tar({"safe_member.txt": b"safe"})
            src_path = os.path.join(tmpdir, "safe.tar")
            dest_path = os.path.join(tmpdir, "out")
            stage_path = os.path.join(tmpdir, "stage_312")
            os.makedirs(stage_path)
            with open(src_path, "wb") as f:
                f.write(archive_data)
            # Should succeed — safe members pass through filter="data".
            result = _transfer_raw.transfer(src_path, dest_path, stage_path, unpack=True)
            self.assertIn("unpacked", result)

    @unittest.skipIf(sys.version_info < (3, 12), "filter='data' path-traversal guard only on Python 3.12+")
    def test_path_traversal_member_rejected_python312(self):
        """filter='data' causes tarfile to raise OutsideDestinationError for ../
        members, preventing extraction outside the destination directory.

        This confirms the security invariant that transfer_raw.transfer() in
        unpack mode cannot be used to write files outside the intended dest.
        """
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name="../traversal_escape.txt")
            data = b"should not escape"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        traversal_bytes = buf.getvalue()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "traversal.tar")
            dest_path = os.path.join(tmpdir, "extracted")
            stage_path = os.path.join(tmpdir, "stage_trav")
            os.makedirs(stage_path)
            with open(src_path, "wb") as f:
                f.write(traversal_bytes)
            # filter="data" raises on path-traversal member names.
            with self.assertRaises(Exception):
                _transfer_raw.transfer(src_path, dest_path, stage_path, unpack=True)
            # The escaped file must not exist outside dest.
            self.assertFalse(
                os.path.exists(os.path.join(tmpdir, "traversal_escape.txt")),
                "path-traversal member must not be written outside the destination",
            )


if __name__ == "__main__":
    unittest.main()
