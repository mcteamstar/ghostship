"""Tests for crews/_base/orientation/verify-admiral-sig exit codes (trn-44).

Verifies:
  - Exit 0 when the secret matches the X-Admiral-Sig header
  - Exit 1 when the signature mismatches
  - Exit 2 (after retries) when the secret file is absent

Uses subprocess with a temp file to avoid modifying real crew state.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


# Resolve the script path relative to the repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "crews" / "_base" / "orientation" / "verify-admiral-sig"


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


def _compute_sig(body: str, secret: str) -> str:
    """Compute the expected HMAC-SHA256 signature for the message payload."""
    normalized_body = body.rstrip("\n")
    payload = f"Subject:test order\nFrom:admiral@localhost\n\n{normalized_body}"
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class VerifyAdmiralSigTests(unittest.TestCase):
    """Test exit codes for verify-admiral-sig script."""

    def _run_script(self, message: str, env_override: dict | None = None) -> int:
        """Run verify-admiral-sig with the given message on stdin.

        Returns the exit code.
        """
        env = dict(os.environ)
        if env_override:
            env.update(env_override)
        result = subprocess.run(
            ["python3", str(SCRIPT_PATH)],
            input=message,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        return result.returncode

    def test_exit_0_valid_signature(self) -> None:
        """Exit code 0 when X-Admiral-Sig matches the body HMAC."""
        secret = "test-secret-for-exit-0"
        body = "You are conducting a review."
        sig = _compute_sig(body, secret)
        message = _make_message(body, sig=sig)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".secret", delete=False) as f:
            f.write(secret)
            secret_path = f.name

        try:
            # Patch the script's SECRET_PATH to use our temp file.
            # We create a wrapper script that overrides the paths.
            wrapper = textwrap.dedent(f"""\
                import sys
                sys.argv = sys.argv  # no-op
                # Monkey-patch before exec
                import importlib.util
                spec = importlib.util.spec_from_file_location("verify", "{SCRIPT_PATH}")
                source = open("{SCRIPT_PATH}").read()
                source = source.replace(
                    "SECRET_PATH = '/home/kirocrew/.kiro/crew/.admiral_secret'",
                    "SECRET_PATH = '{secret_path}'"
                )
                source = source.replace(
                    "SECRET_PATH_FALLBACK = '/home/kirocrew/workplace/.admiral_secret'",
                    "SECRET_PATH_FALLBACK = '{secret_path}'"
                )
                exec(compile(source, "{SCRIPT_PATH}", "exec"))
            """)
            result = subprocess.run(
                ["python3", "-c", wrapper],
                input=message,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        finally:
            os.unlink(secret_path)

    def test_exit_1_signature_mismatch(self) -> None:
        """Exit code 1 when X-Admiral-Sig does not match the body."""
        secret = "test-secret-for-exit-1"
        body = "You are conducting a review."
        wrong_sig = "deadbeef" * 8  # 64 hex chars, wrong value
        message = _make_message(body, sig=wrong_sig)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".secret", delete=False) as f:
            f.write(secret)
            secret_path = f.name

        try:
            wrapper = textwrap.dedent(f"""\
                import sys
                source = open("{SCRIPT_PATH}").read()
                source = source.replace(
                    "SECRET_PATH = '/home/kirocrew/.kiro/crew/.admiral_secret'",
                    "SECRET_PATH = '{secret_path}'"
                )
                source = source.replace(
                    "SECRET_PATH_FALLBACK = '/home/kirocrew/workplace/.admiral_secret'",
                    "SECRET_PATH_FALLBACK = '{secret_path}'"
                )
                exec(compile(source, "{SCRIPT_PATH}", "exec"))
            """)
            result = subprocess.run(
                ["python3", "-c", wrapper],
                input=message,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")
        finally:
            os.unlink(secret_path)

    def test_exit_1_no_signature_header(self) -> None:
        """Exit code 1 when no X-Admiral-Sig header is present."""
        message = _make_message("Some body text", sig=None)

        # No secret file needed — script exits 1 before reading it
        result = subprocess.run(
            ["python3", str(SCRIPT_PATH)],
            input=message,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 1, f"stderr: {result.stderr}")

    def test_exit_2_secret_file_absent(self) -> None:
        """Exit code 2 when the secret file does not exist (after retries).

        Uses non-existent paths and overrides RETRY_DELAY_SECS to 0 to avoid
        waiting 4 seconds in the test.
        """
        body = "Order from Admiral."
        sig = "a" * 64  # Dummy sig — won't get to verification
        message = _make_message(body, sig=sig)

        # Use paths that definitely don't exist
        nonexistent_a = "/tmp/verify_sig_test_nonexistent_a_" + str(os.getpid())
        nonexistent_b = "/tmp/verify_sig_test_nonexistent_b_" + str(os.getpid())

        wrapper = textwrap.dedent(f"""\
            import sys
            source = open("{SCRIPT_PATH}").read()
            source = source.replace(
                "SECRET_PATH = '/home/kirocrew/.kiro/crew/.admiral_secret'",
                "SECRET_PATH = '{nonexistent_a}'"
            )
            source = source.replace(
                "SECRET_PATH_FALLBACK = '/home/kirocrew/workplace/.admiral_secret'",
                "SECRET_PATH_FALLBACK = '{nonexistent_b}'"
            )
            # Speed up retries for test
            source = source.replace(
                "RETRY_DELAY_SECS = 2",
                "RETRY_DELAY_SECS = 0"
            )
            exec(compile(source, "{SCRIPT_PATH}", "exec"))
        """)

        start = time.time()
        result = subprocess.run(
            ["python3", "-c", wrapper],
            input=message,
            capture_output=True,
            text=True,
            timeout=30,
        )
        elapsed = time.time() - start

        self.assertEqual(result.returncode, 2, f"stderr: {result.stderr}")
        # Confirm it did NOT take the full 4 seconds (we set delay to 0)
        self.assertLess(elapsed, 5.0, "Test took too long — retry delay override may have failed")


if __name__ == "__main__":
    unittest.main()
