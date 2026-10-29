"""Unit tests for transport/files.py — presigned URL signing/verification
and path-traversal boundary enforcement.

Design notes:
- GA_FILE_SECRET is set in the environment before the files module is imported
  so _load_or_create_file_secret() picks up the fixed test value.
- Tests access the module's private functions directly via monkeypatching or
  by importing the module with the env var already set.
- All I/O dependencies (PodmanClient, lifecycle, httpx2) are already stubbed
  by conftest.py's _install_transport_stubs call.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
import time
import unittest

# Fix GA_FILE_SECRET before any files.py import so _load_or_create_file_secret
# returns the test value rather than reading /data/ or generating a random one.
_TEST_FILE_SECRET = "test-file-secret-value-32chars!!"
os.environ["GA_FILE_SECRET"] = _TEST_FILE_SECRET

# Ensure transport stubs are installed (httpx2, starlette, etc.) before import.
# conftest does this at session scope; when running this file standalone we
# call it directly.
try:
    from tests.unit.conftest import _install_transport_stubs
    _install_transport_stubs()
except Exception:
    pass

try:
    import files as _files
except ModuleNotFoundError:
    from transport import files as _files


def _sign_manual(
    crew_id: str,
    path: str,
    expires: int,
    method: str = "GET",
    ref: str = "",
    flags: str = "",
) -> str:
    """Reproduce the HMAC signature the way files.py does it."""
    payload = f"{crew_id}:{path}:{expires}:{method}:{ref}:{flags}"
    return hmac.HMAC(
        _TEST_FILE_SECRET.encode(),
        payload.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()


class TestSignVerifyRoundTrip(unittest.TestCase):
    """_sign_file_url + _verify_file_token round-trip for GET and PUT."""

    def _future_expires(self) -> int:
        return int(time.time()) + 300

    def test_get_sign_verify_roundtrip(self):
        """A freshly-signed GET URL passes verification."""
        # Build a URL, then manually extract and verify the token.
        url = _files._sign_file_url("my-crew", "workspace/file.txt")
        # Parse sig and expires from the URL query string.
        qs = url.split("?", 1)[1]
        params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
        result = _files._verify_file_token(
            "my-crew",
            "workspace/file.txt",
            params["expires"],
            params["sig"],
        )
        self.assertTrue(result)

    def test_put_sign_verify_roundtrip(self):
        """A freshly-signed upload (POST) token passes verification."""
        url = _files._sign_upload_url("my-crew", "workspace/upload.tar")
        qs = url.split("?", 1)[1]
        params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
        # mode=None means GET in verify; for POST we pass mode="" (plain write)
        result = _files._verify_file_token(
            "my-crew",
            "workspace/upload.tar",
            params["expires"],
            params["sig"],
            mode="",  # plain write — no unpack/bundle flags
        )
        self.assertTrue(result)

    def test_get_token_rejected_for_put(self):
        """A GET token must be rejected when mode="".

        The payload format differs (GET encodes ref+bundle; POST encodes
        force/unpack/bundle) so a GET signature never matches a POST payload.
        """
        url = _files._sign_file_url("my-crew", "workspace/file.txt")
        qs = url.split("?", 1)[1]
        params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
        # Try to use the GET sig for a POST verification (mode="")
        result = _files._verify_file_token(
            "my-crew",
            "workspace/file.txt",
            params["expires"],
            params["sig"],
            mode="",  # POST mode — different payload format
        )
        self.assertFalse(result)


class TestTamperedSignature(unittest.TestCase):
    """Tampered sig parameter → verification fails."""

    def test_modified_sig_rejected(self):
        url = _files._sign_file_url("my-crew", "workspace/data.bin")
        qs = url.split("?", 1)[1]
        params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
        tampered_sig = params["sig"][:-4] + "0000"
        result = _files._verify_file_token(
            "my-crew",
            "workspace/data.bin",
            params["expires"],
            tampered_sig,
        )
        self.assertFalse(result)

    def test_entirely_wrong_sig_rejected(self):
        expires = str(int(time.time()) + 300)
        result = _files._verify_file_token(
            "my-crew",
            "workspace/file.txt",
            expires,
            "deadbeef" * 8,
        )
        self.assertFalse(result)


class TestExpiredToken(unittest.TestCase):
    """Tokens with a past expiry are rejected."""

    def test_expired_get_token_rejected(self):
        past_expires = int(time.time()) - 10  # already expired
        sig = _sign_manual("my-crew", "workspace/file.txt", past_expires, "GET")
        result = _files._verify_file_token(
            "my-crew",
            "workspace/file.txt",
            str(past_expires),
            sig,
        )
        self.assertFalse(result)

    def test_expired_put_token_rejected(self):
        past_expires = int(time.time()) - 10
        sig = _sign_manual("my-crew", "workspace/upload.tar", past_expires, "POST", flags="")
        result = _files._verify_file_token(
            "my-crew",
            "workspace/upload.tar",
            str(past_expires),
            sig,
            mode="",
        )
        self.assertFalse(result)

    def test_non_integer_expires_rejected(self):
        result = _files._verify_file_token(
            "my-crew", "workspace/file.txt", "not-a-number", "deadbeef" * 8
        )
        self.assertFalse(result)


class TestSafeWorkspacePath(unittest.TestCase):
    """_safe_workspace_path path-traversal rejection."""

    def test_normal_path_resolves(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved_root = str(Path(tmpdir).resolve())
            result = _files._safe_workspace_path(tmpdir, "subdir/file.txt")
            self.assertTrue(str(result).startswith(resolved_root))

    def test_path_traversal_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                _files._safe_workspace_path(tmpdir, "../escape/file.txt")

    def test_absolute_path_stripped_and_accepted(self):
        """An absolute raw_path has its leading '/' stripped and resolves inside root.

        _safe_workspace_path calls lstrip('/') on the raw path, so /etc/passwd
        becomes 'etc/passwd' which resolves inside the workspace root.
        This is by design: the function is meant for URL-path segments where a
        leading slash is just formatting, not a filesystem root escape.
        """
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved_root = str(Path(tmpdir).resolve())
            result = _files._safe_workspace_path(tmpdir, "/etc/passwd")
            self.assertTrue(str(result).startswith(resolved_root))

    def test_deeply_nested_traversal_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                _files._safe_workspace_path(tmpdir, "a/b/../../../../../../etc/shadow")

    def test_valid_nested_path_accepted(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved_root = str(Path(tmpdir).resolve())
            result = _files._safe_workspace_path(tmpdir, "a/b/c/file.txt")
            self.assertTrue(str(result).startswith(resolved_root))


if __name__ == "__main__":
    unittest.main()
