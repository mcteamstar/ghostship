"""Unit tests for the verify-admiral-sig admission script (TRN-136).

Exercises the Ed25519 verifier's exit codes: valid signature (0), signature
mismatch (1), missing X-Admiral-Sig header (1), and absent public-key file (2).
The script reads the raw 32-byte Ed25519 public key from .admiral_public_key;
the tests monkey-patch PUBKEY_PATH / PUBKEY_PATH_FALLBACK to point at a temp
file, mirroring how the earlier HMAC tests patched SECRET_PATH.
"""
from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)


# Resolve the script path relative to the repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "crews" / "_base" / "admission" / "verify-admiral-sig"


def _make_message(body: str, sig: str | None = None) -> str:
    """Construct a minimal RFC-822 message with an optional X-Admiral-Sig header."""
    lines = [
        "From: admiral@localhost",
        "To: captain@localhost",
        "Subject: test order",
    ]
    if sig is not None:
        lines.append(f"X-Admiral-Sig: {sig}")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


def _sign(body: str, private_key: Ed25519PrivateKey) -> str:
    """Produce the base64url (unpadded) Ed25519 signature for the payload."""
    normalized_body = body.rstrip("\n")
    payload = f"Subject:test order\nFrom:admiral@localhost\n\n{normalized_body}".encode(
        "utf-8"
    )
    sig = private_key.sign(payload)
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")


def _run_with_pubkey(message: str, pubkey_path: str, fallback_path: str) -> subprocess.CompletedProcess:
    """Run verify-admiral-sig with PUBKEY_PATH overridden to pubkey_path."""
    wrapper = textwrap.dedent(f"""\
        source = open({str(SCRIPT_PATH)!r}).read()
        source = source.replace(
            "PUBKEY_PATH = '/home/kirocrew/.kiro/crew/.admiral_public_key'",
            "PUBKEY_PATH = {pubkey_path!r}"
        )
        source = source.replace(
            "PUBKEY_PATH_FALLBACK = '/home/kirocrew/workplace/.admiral_public_key'",
            "PUBKEY_PATH_FALLBACK = {fallback_path!r}"
        )
        source = source.replace("RETRY_DELAY_SECS = 2", "RETRY_DELAY_SECS = 0")
        exec(compile(source, {str(SCRIPT_PATH)!r}, "exec"))
    """)
    return subprocess.run(
        ["python3", "-c", wrapper],
        input=message,
        capture_output=True,
        text=True,
        timeout=30,
    )


class VerifyAdmiralSigTests(unittest.TestCase):
    """Test exit codes for the Ed25519 verify-admiral-sig script."""

    def _write_pubkey(self, private_key: Ed25519PrivateKey) -> str:
        pub_bytes = private_key.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )
        fd, path = tempfile.mkstemp(suffix=".pubkey")
        with os.fdopen(fd, "wb") as f:
            f.write(pub_bytes)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return path

    def test_exit_0_valid_signature(self) -> None:
        """Exit 0 when X-Admiral-Sig is a valid Ed25519 signature."""
        private_key = Ed25519PrivateKey.generate()
        body = "You are conducting a review."
        sig = _sign(body, private_key)
        message = _make_message(body, sig=sig)
        pubkey_path = self._write_pubkey(private_key)

        result = _run_with_pubkey(message, pubkey_path, pubkey_path)
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_exit_1_signature_mismatch(self) -> None:
        """Exit 1 when the signature was made by a different key."""
        signing_key = Ed25519PrivateKey.generate()
        other_key = Ed25519PrivateKey.generate()
        body = "You are conducting a review."
        # Signed with signing_key, but the mounted public key is other_key's.
        sig = _sign(body, signing_key)
        message = _make_message(body, sig=sig)
        pubkey_path = self._write_pubkey(other_key)

        result = _run_with_pubkey(message, pubkey_path, pubkey_path)
        self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")

    def test_exit_1_tampered_body(self) -> None:
        """Exit 1 when the body is altered after signing (payload mismatch)."""
        private_key = Ed25519PrivateKey.generate()
        sig = _sign("original order body", private_key)
        message = _make_message("TAMPERED order body", sig=sig)
        pubkey_path = self._write_pubkey(private_key)

        result = _run_with_pubkey(message, pubkey_path, pubkey_path)
        self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")

    def test_exit_1_no_signature_header(self) -> None:
        """Exit 1 when no X-Admiral-Sig header is present."""
        message = _make_message("Some body text", sig=None)
        # No public key file needed — script exits 1 before reading it.
        result = subprocess.run(
            ["python3", str(SCRIPT_PATH)],
            input=message,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")

    def test_exit_2_pubkey_file_absent(self) -> None:
        """Exit 2 when the public-key file does not exist (after retries)."""
        body = "Order from Admiral."
        # A syntactically valid base64url sig — verification never runs because
        # the public key is missing.
        sig = base64.urlsafe_b64encode(b"\x00" * 64).rstrip(b"=").decode("ascii")
        message = _make_message(body, sig=sig)

        nonexistent_a = "/tmp/verify_sig_test_nonexistent_a_" + str(os.getpid())
        nonexistent_b = "/tmp/verify_sig_test_nonexistent_b_" + str(os.getpid())

        start = time.time()
        result = _run_with_pubkey(message, nonexistent_a, nonexistent_b)
        elapsed = time.time() - start

        self.assertEqual(result.returncode, 2, f"stderr: {result.stderr}")
        # RETRY_DELAY_SECS is overridden to 0, so this must be fast.
        self.assertLess(elapsed, 5.0, "retry delay override may have failed")


if __name__ == "__main__":
    unittest.main()
