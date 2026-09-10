"""Unit tests for the verify-admiral-sig admission script (TRN-136).

Exercises the Ed25519 verifier's exit codes: valid signature (0), signature
mismatch (1), missing X-Admiral-Sig header (1), and absent public-key file (2).
The script reads the raw 32-byte Ed25519 public key from PUBKEY_PATH; the tests
monkey-patch that constant to point at a temp file, mirroring how the earlier
HMAC tests patched SECRET_PATH.

WhitespaceBoundaryKeyTests covers the regression that made the first
implementation pass unusable: the verifier trimmed the raw key bytes, so any
key beginning or ending with an ASCII whitespace byte (~4.7% of them) was
truncated to 31 bytes and rejected as absent. The other tests generate random
keypairs, so they only caught it a few percent of the time — these two are
deterministic.
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

# The bytes bytes.strip() would remove from either end of raw key material.
ASCII_WHITESPACE = b" \t\n\r\x0b\x0c"


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


def _run_with_pubkey(message: str, pubkey_path: str) -> subprocess.CompletedProcess:
    """Run verify-admiral-sig with PUBKEY_PATH overridden to pubkey_path."""
    wrapper = textwrap.dedent(f"""\
        source = open({str(SCRIPT_PATH)!r}).read()
        source = source.replace(
            "PUBKEY_PATH = '/run/secrets/.admiral_public_key'",
            "PUBKEY_PATH = {pubkey_path!r}"
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


class _PubkeyFileMixin(unittest.TestCase):
    """Writes raw public-key bytes to a temp file that is cleaned up after."""

    def _write_pubkey_bytes(self, pub_bytes: bytes) -> str:
        fd, path = tempfile.mkstemp(suffix=".pubkey")
        with os.fdopen(fd, "wb") as f:
            f.write(pub_bytes)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return path

    def _write_pubkey(self, private_key: Ed25519PrivateKey) -> str:
        return self._write_pubkey_bytes(
            private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        )


class VerifyAdmiralSigTests(_PubkeyFileMixin):
    """Test exit codes for the Ed25519 verify-admiral-sig script."""

    def test_exit_0_valid_signature(self) -> None:
        """Exit 0 when X-Admiral-Sig is a valid Ed25519 signature."""
        private_key = Ed25519PrivateKey.generate()
        body = "You are conducting a review."
        sig = _sign(body, private_key)
        message = _make_message(body, sig=sig)
        pubkey_path = self._write_pubkey(private_key)

        result = _run_with_pubkey(message, pubkey_path)
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

        result = _run_with_pubkey(message, pubkey_path)
        self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")

    def test_exit_1_tampered_body(self) -> None:
        """Exit 1 when the body is altered after signing (payload mismatch)."""
        private_key = Ed25519PrivateKey.generate()
        sig = _sign("original order body", private_key)
        message = _make_message("TAMPERED order body", sig=sig)
        pubkey_path = self._write_pubkey(private_key)

        result = _run_with_pubkey(message, pubkey_path)
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

        nonexistent = "/tmp/verify_sig_test_nonexistent_" + str(os.getpid())

        start = time.time()
        result = _run_with_pubkey(message, nonexistent)
        elapsed = time.time() - start

        self.assertEqual(result.returncode, 2, f"stderr: {result.stderr}")
        # RETRY_DELAY_SECS is overridden to 0, so this must be fast.
        self.assertLess(elapsed, 5.0, "retry delay override may have failed")

    def test_exit_2_pubkey_wrong_length(self) -> None:
        """Exit 2 when the key file is present but is not 32 bytes."""
        sig = base64.urlsafe_b64encode(b"\x00" * 64).rstrip(b"=").decode("ascii")
        message = _make_message("Order from Admiral.", sig=sig)
        pubkey_path = self._write_pubkey_bytes(b"\x01" * 31)

        result = _run_with_pubkey(message, pubkey_path)
        self.assertEqual(result.returncode, 2, f"stderr: {result.stderr}")


class WhitespaceBoundaryKeyTests(_PubkeyFileMixin):
    """The key file is raw bytes and must never be whitespace-trimmed.

    A previous implementation read it as ``f.read().strip()``. Roughly 4.7% of
    Ed25519 public keys start or end with an ASCII whitespace byte, and each of
    those was silently truncated to 31 bytes, so the crew exited 2 on every
    Admiral mail for its entire life.
    """

    @staticmethod
    def _keypair_with_whitespace_boundary() -> tuple[Ed25519PrivateKey, bytes]:
        """Find a keypair whose raw public key begins or ends with whitespace.

        Each draw has a ~4.7% chance, so this converges in a few dozen
        iterations; the bound only stops a pathological RNG from hanging tests.
        """
        for _ in range(5000):
            private_key = Ed25519PrivateKey.generate()
            pub = private_key.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw
            )
            if pub[:1] in ASCII_WHITESPACE or pub[-1:] in ASCII_WHITESPACE:
                return private_key, pub
        raise AssertionError("no whitespace-boundary key found in 5000 draws")

    def test_valid_signature_accepted_for_whitespace_boundary_key(self) -> None:
        """Exit 0 for a real key whose bytes would be damaged by .strip()."""
        private_key, pub = self._keypair_with_whitespace_boundary()
        self.assertNotEqual(
            pub.strip(), pub, "fixture must be a key .strip() would alter"
        )

        body = "You are conducting a review."
        message = _make_message(body, sig=_sign(body, private_key))
        pubkey_path = self._write_pubkey_bytes(pub)

        result = _run_with_pubkey(message, pubkey_path)
        self.assertEqual(
            result.returncode,
            0,
            "a whitespace-boundary key must verify normally; exit 2 means the "
            f"key bytes were trimmed. stderr: {result.stderr}",
        )

    def test_leading_and_trailing_whitespace_keys_reach_verification(self) -> None:
        """A 32-byte key with whitespace at either end is not treated as absent.

        Fully deterministic: the key material is crafted rather than searched
        for. The signature cannot verify against it, so the correct outcome is
        exit 1 (verification ran and failed), never exit 2 (key unusable).
        """
        sig = base64.urlsafe_b64encode(b"\x00" * 64).rstrip(b"=").decode("ascii")
        message = _make_message("Order from Admiral.", sig=sig)

        for label, pub in (
            ("leading space", b"\x20" + b"\x01" * 31),
            ("trailing newline", b"\x01" * 31 + b"\x0a"),
        ):
            with self.subTest(boundary=label):
                pubkey_path = self._write_pubkey_bytes(pub)
                result = _run_with_pubkey(message, pubkey_path)
                self.assertEqual(
                    result.returncode,
                    1,
                    f"{label}: expected verification to run and fail (1), got "
                    f"{result.returncode}. stderr: {result.stderr}",
                )


if __name__ == "__main__":
    unittest.main()
