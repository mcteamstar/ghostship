"""Unit tests for the verify-admiral-sig admission script.

Exercises the Ed25519 verifier's exit codes: valid signature (0), signature
mismatch (1), missing X-Admiral-Sig header (1), and absent public-key file (2).
The script reads the raw 32-byte Ed25519 public key from PUBKEY_PATH; the tests
monkey-patch that constant to point at a temp file, mirroring how the earlier
HMAC tests patched SECRET_PATH.

HardeningDefectTests covers the TRN-216 hardening: the length-prefixed payload
format, the multipart guard (no AttributeError crash), header-newline rejection,
no body-whitespace strip asymmetry, and rejection of old-format signatures.
SignerVerifierIntegrationTests round-trips the real signer
(transport.captain._format_captain_mail) through the verifier end-to-end.

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


def _make_message(
    body: str,
    sig: str | None = None,
    subject: str = "test order",
    sender: str = "admiral@localhost",
    extra_headers: list[str] | None = None,
) -> str:
    """Construct a minimal RFC-822 message with an optional X-Admiral-Sig header."""
    lines = [
        f"From: {sender}",
        "To: captain@localhost",
        f"Subject: {subject}",
    ]
    if extra_headers:
        lines.extend(extra_headers)
    if sig is not None:
        lines.append(f"X-Admiral-Sig: {sig}")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


def _sign(
    body: str,
    private_key: Ed25519PrivateKey,
    subject: str = "test order",
    sender: str = "admiral@localhost",
) -> str:
    """Produce the base64url (unpadded) Ed25519 signature for the payload.

    Uses the length-prefixed payload format (TRN-216): the UTF-8 byte length of
    each header value as ASCII decimal + newline, the value's bytes, then the
    body bytes verbatim. Mirrors transport.captain._format_captain_mail.
    """
    subject_utf8 = subject.encode("utf-8")
    from_utf8 = sender.encode("utf-8")
    body_bytes = body.encode("utf-8")
    payload = (
        f"{len(subject_utf8)}\n".encode("ascii")
        + subject_utf8
        + f"{len(from_utf8)}\n".encode("ascii")
        + from_utf8
        + body_bytes
    )
    sig = private_key.sign(payload)
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")


def _sign_old_format(body: str, private_key: Ed25519PrivateKey) -> str:
    """Produce a signature using the OLD string-interpolation payload format.

    Used only to prove the new verifier rejects old-format signatures.
    """
    normalized_body = body.rstrip("\n")
    payload = (
        f"Subject:test order\nFrom:admiral@localhost\n\n{normalized_body}".encode(
            "utf-8"
        )
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


class HardeningDefectTests(_PubkeyFileMixin):
    """TRN-216 regression tests for the three hardened defects."""

    def test_exit_1_multipart_message(self) -> None:
        """Exit 1 (no AttributeError) when the message is MIME multipart."""
        private_key = Ed25519PrivateKey.generate()
        pubkey_path = self._write_pubkey(private_key)
        # A syntactically valid signature; verification never runs because the
        # multipart guard fires first.
        sig = base64.urlsafe_b64encode(b"\x00" * 64).rstrip(b"=").decode("ascii")
        message = (
            "From: admiral@localhost\n"
            "To: captain@localhost\n"
            "Subject: test order\n"
            f"X-Admiral-Sig: {sig}\n"
            'Content-Type: multipart/mixed; boundary="BOUND"\n'
            "\n"
            "--BOUND\n"
            "Content-Type: text/plain\n"
            "\n"
            "part one\n"
            "--BOUND--\n"
        )
        result = _run_with_pubkey(message, pubkey_path)
        self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")
        self.assertNotIn(
            "AttributeError", result.stderr, "multipart must not crash the verifier"
        )
        self.assertNotIn("Traceback", result.stderr)

    def test_exit_1_newline_in_subject(self) -> None:
        """Exit 1 when the Subject header value contains an injected newline."""
        private_key = Ed25519PrivateKey.generate()
        pubkey_path = self._write_pubkey(private_key)
        body = "You are conducting a review."
        # The signature is over an injected subject; the verifier must reject on
        # the header-newline guard regardless of signature validity. A folded
        # Subject header reconstructs to a value containing a newline.
        sig = _sign(body, private_key, subject="line one\nInjected: evil")
        message = (
            "From: admiral@localhost\n"
            "To: captain@localhost\n"
            "Subject: line one\n Injected: evil\n"
            f"X-Admiral-Sig: {sig}\n"
            "\n"
            f"{body}\n"
        )
        result = _run_with_pubkey(message, pubkey_path)
        self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")

    def test_exit_1_newline_in_from(self) -> None:
        """Exit 1 when the From header value contains an injected newline."""
        private_key = Ed25519PrivateKey.generate()
        pubkey_path = self._write_pubkey(private_key)
        body = "You are conducting a review."
        sig = _sign(body, private_key, sender="admiral@localhost\nInjected: evil")
        message = (
            "From: admiral@localhost\n Injected: evil\n"
            "To: captain@localhost\n"
            "Subject: test order\n"
            f"X-Admiral-Sig: {sig}\n"
            "\n"
            f"{body}\n"
        )
        result = _run_with_pubkey(message, pubkey_path)
        self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")

    def test_exit_0_body_with_trailing_whitespace(self) -> None:
        """Exit 0 for a body ending in spaces/tabs (no strip asymmetry)."""
        private_key = Ed25519PrivateKey.generate()
        pubkey_path = self._write_pubkey(private_key)
        # Trailing spaces/tabs — not \r\n, so the signer would not strip these.
        # The verifier must not strip them either; the round-trip must succeed.
        body = "Order with trailing whitespace.  \t  "
        sig = _sign(body, private_key)
        message = _make_message(body, sig=sig)
        result = _run_with_pubkey(message, pubkey_path)
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_exit_1_old_format_payload(self) -> None:
        """Exit 1 for a signature made with the pre-TRN-216 payload format."""
        private_key = Ed25519PrivateKey.generate()
        pubkey_path = self._write_pubkey(private_key)
        body = "You are conducting a review."
        sig = _sign_old_format(body, private_key)
        message = _make_message(body, sig=sig)
        result = _run_with_pubkey(message, pubkey_path)
        self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")


class SignerVerifierIntegrationTests(_PubkeyFileMixin):
    """End-to-end round-trip: sign with _format_captain_mail, verify with the script."""

    @staticmethod
    def _format_captain_mail(body: str, signing_secret: str) -> str:
        import importlib.util
        import sys
        import types

        # transport/captain.py imports transport.podman at module scope, which in
        # turn pulls in an httpx client and the `podman` package — neither needed
        # by the pure _format_captain_mail function and neither guaranteed present
        # in the test environment. Stub the import graph so the module loads; the
        # signing path under test uses only `cryptography`, `datetime` and `uuid`.
        stub_names = ("podman", "httpx2", "transport.podman")
        saved = {name: sys.modules.get(name) for name in stub_names}
        try:
            for name in ("podman", "httpx2"):
                mod = types.ModuleType(name)
                mod.PodmanClient = type("PodmanClient", (), {})
                sys.modules[name] = mod
            # Ensure `transport` is a package so `transport.podman` resolves.
            if "transport" not in sys.modules:
                pkg = types.ModuleType("transport")
                pkg.__path__ = [str(REPO_ROOT / "transport")]
                sys.modules["transport"] = pkg
            podman_stub = types.ModuleType("transport.podman")
            podman_stub.PodmanClient = type("PodmanClient", (), {})
            sys.modules["transport.podman"] = podman_stub

            spec = importlib.util.spec_from_file_location(
                "_captain_under_test", REPO_ROOT / "transport" / "captain.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            message, _mid = module._format_captain_mail(
                body, signing_secret=signing_secret
            )
            return message
        finally:
            for name, prev in saved.items():
                if prev is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = prev

    @staticmethod
    def _signing_secret_and_pubkey() -> tuple[str, bytes]:
        private_key = Ed25519PrivateKey.generate()
        from cryptography.hazmat.primitives.serialization import (
            Encoding as _Enc,
            PrivateFormat as _PrivFmt,
            NoEncryption as _NoEnc,
        )

        seed = private_key.private_bytes(_Enc.Raw, _PrivFmt.Raw, _NoEnc())
        pub = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return seed.hex(), pub

    def test_round_trip_exit_0(self) -> None:
        """A message signed by the real signer verifies with exit 0."""
        secret, pub = self._signing_secret_and_pubkey()
        pubkey_path = self._write_pubkey_bytes(pub)
        message = self._format_captain_mail(
            "You are conducting a review of the queue.", secret
        )
        result = _run_with_pubkey(message, pubkey_path)
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_round_trip_non_ascii_body_exit_0(self) -> None:
        """A body with multi-byte UTF-8 characters verifies (byte-length encoding)."""
        secret, pub = self._signing_secret_and_pubkey()
        pubkey_path = self._write_pubkey_bytes(pub)
        message = self._format_captain_mail(
            "Révision immédiate — 日本語テスト — café ☕", secret
        )
        result = _run_with_pubkey(message, pubkey_path)
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_round_trip_tampered_body_exit_1(self) -> None:
        """Tampering the body after signing fails verification (exit 1)."""
        secret, pub = self._signing_secret_and_pubkey()
        pubkey_path = self._write_pubkey_bytes(pub)
        message = self._format_captain_mail(
            "You are conducting a review of the queue.", secret
        )
        # Replace a word in the body while leaving the signature header intact.
        tampered = message.replace("review", "deletion")
        self.assertNotEqual(tampered, message, "tamper fixture must change the body")
        result = _run_with_pubkey(tampered, pubkey_path)
        self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")


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
