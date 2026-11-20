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
import subprocess
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
    """transfer_raw.transfer() — plain, archive, and bundle modes."""

    def _stage(self, workspace: str, stage_name: str, payload: bytes) -> tuple[str, str]:
        stage = os.path.join(workspace, stage_name)
        os.makedirs(stage)
        source = os.path.join(stage, "payload")
        pathlib.Path(source).write_bytes(payload)
        return source, stage

    def test_plain_copy_writes_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest_path = os.path.join(tmpdir, "dest.bin")
            src_path, stage_path = self._stage(tmpdir, "stage", b"hello world")
            result = _transfer_raw.transfer(src_path, dest_path, stage_path, unpack=False, workspace=tmpdir)
            self.assertIn("wrote", result)
            self.assertEqual(pathlib.Path(dest_path).read_bytes(), b"hello world")
            # Stage directory cleaned up
            self.assertFalse(os.path.exists(stage_path))

    def test_unpack_mode_extracts_archive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_data = _make_tar({"readme.txt": b"archive content"})
            dest_path = os.path.join(tmpdir, "extracted")
            src_path, stage_path = self._stage(tmpdir, "stage_unpack", archive_data)
            result = _transfer_raw.transfer(src_path, dest_path, stage_path, unpack=True, workspace=tmpdir)
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
                    os.path.join(stage_path, "missing.bin"),
                    os.path.join(tmpdir, "dest.bin"),
                    stage_path,
                    unpack=False,
                    workspace=tmpdir,
                )
            except Exception:
                pass
            self.assertFalse(os.path.exists(stage_path))

    def test_unpack_accepts_safe_member(self):
        """Safe members are unpacked on every supported Python version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_data = _make_tar({"safe_member.txt": b"safe"})
            dest_path = os.path.join(tmpdir, "out")
            src_path, stage_path = self._stage(tmpdir, "stage_safe", archive_data)
            result = _transfer_raw.transfer(src_path, dest_path, stage_path, unpack=True, workspace=tmpdir)
            self.assertIn("unpacked", result)

    def test_archive_traversal_rejected_before_destination_changes(self):
        """Unsafe members are rejected before any existing destination data changes."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name="../traversal_escape.txt")
            data = b"should not escape"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        traversal_bytes = buf.getvalue()

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_path = os.path.join(tmpdir, "extracted")
            os.makedirs(dest_path)
            preserved = pathlib.Path(dest_path) / "preserved.txt"
            preserved.write_bytes(b"keep this")
            src_path, stage_path = self._stage(tmpdir, "stage_trav", traversal_bytes)
            with self.assertRaises(ValueError):
                _transfer_raw.transfer(src_path, dest_path, stage_path, unpack=True, workspace=tmpdir)
            self.assertFalse(
                os.path.exists(os.path.join(tmpdir, "traversal_escape.txt")),
                "path-traversal member must not be written outside the destination",
            )
            self.assertEqual(preserved.read_bytes(), b"keep this")
            self.assertFalse(os.path.exists(stage_path))

    def test_plain_copy_accepts_nested_workspace_destination(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = pathlib.Path(tmpdir) / "workspace"
            workspace.mkdir()
            source, stage = self._stage(str(workspace), "stage_nested", b"nested bytes")
            destination = workspace / "a" / "b" / "file.bin"
            result = _transfer_raw.transfer(
                source, str(destination), stage, unpack=False, workspace=str(workspace)
            )
            self.assertIn("wrote", result)
            self.assertEqual(destination.read_bytes(), b"nested bytes")
            self.assertFalse(os.path.exists(stage))

    def test_plain_copy_rejects_destination_outside_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = pathlib.Path(tmpdir) / "workspace"
            workspace.mkdir()
            outside = pathlib.Path(tmpdir) / "outside.txt"
            outside.write_bytes(b"keep this")
            source, stage = self._stage(str(workspace), "stage_outside", b"overwrite")
            with self.assertRaises(ValueError):
                _transfer_raw.transfer(
                    source, str(outside), stage, unpack=False, workspace=str(workspace)
                )
            self.assertEqual(outside.read_bytes(), b"keep this")
            self.assertFalse(os.path.exists(stage))

    def test_plain_copy_rejects_symlinked_destination_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = pathlib.Path(tmpdir) / "workspace"
            outside = pathlib.Path(tmpdir) / "outside"
            workspace.mkdir()
            outside.mkdir()
            protected = outside / "file.txt"
            protected.write_bytes(b"keep this")
            (workspace / "link").symlink_to(outside, target_is_directory=True)
            source, stage = self._stage(str(workspace), "stage_link", b"overwrite")
            with self.assertRaises(ValueError):
                _transfer_raw.transfer(
                    source,
                    str(workspace / "link" / "file.txt"),
                    stage,
                    unpack=False,
                    workspace=str(workspace),
                )
            self.assertEqual(protected.read_bytes(), b"keep this")
            self.assertFalse(os.path.exists(stage))

    def test_unpack_accepts_nested_destination(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = pathlib.Path(tmpdir) / "workspace"
            workspace.mkdir()
            source, stage = self._stage(
                str(workspace), "stage_nested_archive", _make_tar({"a/b.txt": b"nested archive"})
            )
            destination = workspace / "nested" / "out"
            _transfer_raw.transfer(
                source, str(destination), stage, unpack=True, workspace=str(workspace)
            )
            self.assertEqual((destination / "a" / "b.txt").read_bytes(), b"nested archive")
            self.assertFalse(os.path.exists(stage))

    def test_archive_symlink_member_is_rejected_before_changes(self):
        archive_buffer = io.BytesIO()
        with tarfile.open(fileobj=archive_buffer, mode="w") as archive:
            regular = tarfile.TarInfo("new.txt")
            regular.size = 3
            archive.addfile(regular, io.BytesIO(b"new"))
            link = tarfile.TarInfo("link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../outside.txt"
            archive.addfile(link)

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = pathlib.Path(tmpdir) / "workspace"
            destination = workspace / "existing"
            destination.mkdir(parents=True)
            preserved = destination / "keep.txt"
            preserved.write_bytes(b"keep this")
            source, stage = self._stage(str(workspace), "stage_symlink_archive", archive_buffer.getvalue())
            with self.assertRaises(ValueError):
                _transfer_raw.transfer(
                    source, str(destination), stage, unpack=True, workspace=str(workspace)
                )
            self.assertEqual(preserved.read_bytes(), b"keep this")
            self.assertFalse((destination / "new.txt").exists())
            self.assertFalse(os.path.exists(stage))

    def _make_bundle(self, repo_path: pathlib.Path, bundle_path: pathlib.Path) -> None:
        repo_path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo_path)], check=True)
        (repo_path / "README.txt").write_text("bundle content\n")
        subprocess.run(["git", "-C", str(repo_path), "add", "README.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "-c", "user.name=Test", "-c",
             "user.email=test@example.invalid", "commit", "-m", "initial"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "bundle", "create", str(bundle_path), "--all"],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    def test_bundle_clone_accepts_nested_destination(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = pathlib.Path(tmpdir) / "workspace"
            workspace.mkdir()
            source, stage = self._stage(str(workspace), "stage_bundle", b"")
            self._make_bundle(pathlib.Path(tmpdir) / "source-repo", pathlib.Path(source))
            destination = workspace / "nested" / "repo"
            result = _transfer_raw.transfer(
                source,
                str(destination),
                stage,
                unpack=False,
                workspace=str(workspace),
                bundle=True,
            )
            self.assertIn("cloned to", result)
            self.assertEqual((destination / "README.txt").read_text(), "bundle content\n")
            self.assertFalse(os.path.exists(stage))

    def test_forced_bundle_replacement_waits_until_clone_is_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = pathlib.Path(tmpdir) / "workspace"
            workspace.mkdir()
            destination = workspace / "repo"
            destination.mkdir()
            (destination / "old.txt").write_text("preserve until clone succeeds")
            source, stage = self._stage(str(workspace), "stage_force_bundle", b"")
            self._make_bundle(pathlib.Path(tmpdir) / "force-source", pathlib.Path(source))
            _transfer_raw.transfer(
                source,
                str(destination),
                stage,
                unpack=False,
                workspace=str(workspace),
                bundle=True,
                force=True,
            )
            self.assertFalse((destination / "old.txt").exists())
            self.assertEqual((destination / "README.txt").read_text(), "bundle content\n")
            self.assertFalse(os.path.exists(stage))

    def test_rejected_forced_bundle_preserves_destination_and_cleans_stage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = pathlib.Path(tmpdir) / "workspace"
            destination = workspace / "repo"
            destination.mkdir(parents=True)
            preserved = destination / "old.txt"
            preserved.write_bytes(b"keep this")
            source, stage = self._stage(str(workspace), "stage_bad_bundle", b"not a git bundle")
            with self.assertRaises(RuntimeError):
                _transfer_raw.transfer(
                    source,
                    str(destination),
                    stage,
                    unpack=False,
                    workspace=str(workspace),
                    bundle=True,
                    force=True,
                )
            self.assertEqual(preserved.read_bytes(), b"keep this")
            self.assertFalse(os.path.exists(stage))


if __name__ == "__main__":
    unittest.main()
