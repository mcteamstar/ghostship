"""Unit tests for login auth-file helpers (trn-212-test-coverage-gaps D).

Covers the login credential writers and the Codex inject chunking path, which
the proposal flagged as untested (only ``_save_registry`` had equivalent
coverage):

- ``_write_auth_file``        — 0o600 mode, exact content, overwrite.
- ``_write_codex_auth_file``  — 0o600 mode, byte payload.
- ``_inject_codex_auth``      — mkdir first, ≤4096-byte base64 chunks, final
  ``base64 -d … | tar -xf …``, and a byte-exact base64 round-trip.

All tests use real tmpdir paths (design.md D3 — mocking os.open/os.fchmod would
not verify the on-disk permission).
"""

from __future__ import annotations

import base64
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


class _TmpdirBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="trn212-auth-")
        self.addCleanup(self._rmtree, self.tmp)

    @staticmethod
    def _rmtree(path: str) -> None:
        import shutil
        shutil.rmtree(path, ignore_errors=True)


class TestWriteAuthFile(_TmpdirBase):
    """D.1 — _write_auth_file writes exact content with mode 0o600."""

    def test_content_and_mode(self) -> None:
        target = Path(self.tmp) / "sub" / "ga-kiro-auth"
        value = "device-auth-token-value\n"
        _lifecycle._write_auth_file(value, _path=target)
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_text(), value)
        self.assertEqual(_mode(target), 0o600)


class TestWriteAuthFileOverwrite(_TmpdirBase):
    """D.2 — a second write replaces content and keeps mode 0o600."""

    def test_overwrite_keeps_mode(self) -> None:
        target = Path(self.tmp) / "ga-kiro-auth"
        _lifecycle._write_auth_file("first-value", _path=target)
        self.assertEqual(target.read_text(), "first-value")
        _lifecycle._write_auth_file("second-value-longer", _path=target)
        self.assertEqual(target.read_text(), "second-value-longer")
        self.assertEqual(_mode(target), 0o600)


class TestWriteCodexAuthFile(_TmpdirBase):
    """D.3 — _write_codex_auth_file writes a byte payload with mode 0o600."""

    def test_bytes_and_mode(self) -> None:
        target = Path(self.tmp) / "ga-codex-auth"
        payload = os.urandom(512)
        _lifecycle._write_codex_auth_file(payload, _path=target)
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(_mode(target), 0o600)


class TestInjectCodexAuthChunking(_TmpdirBase):
    """D.4 — _inject_codex_auth chunks, round-trips, and finalises correctly."""

    @staticmethod
    def _make_tar() -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            # Payload large enough to force several ≤4096-byte base64 chunks.
            data = (b"openai-codex-auth-json-" * 400)
            info = tarfile.TarInfo("auth.json")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def test_chunking_and_roundtrip(self) -> None:
        tar_bytes = self._make_tar()
        auth_path = Path(self.tmp) / "ga-codex-auth"
        _lifecycle._write_codex_auth_file(tar_bytes, _path=auth_path)

        calls: list[list[str]] = []
        podman = Mock()
        podman.container_exec.side_effect = lambda container, cmd: calls.append(cmd) or ""

        # Point the module's codex-auth path at our tmpfile so _inject reads it.
        with patch.object(_lifecycle, "_codex_auth_file_path", return_value=auth_path):
            _lifecycle._inject_codex_auth(podman, "gs-crew-xyz")

        # (a) mkdir -p must be the first exec.
        self.assertEqual(calls[0][:2], ["mkdir", "-p"])
        self.assertIn("/home/kirocrew/.codex", calls[0])

        # Identify the chunk-append calls: `printf '%s' '<chunk>' >> <tmp>`.
        chunk_scripts = [c[-1] for c in calls if c[0] == "sh" and "printf '%s'" in c[-1]]
        self.assertGreater(len(chunk_scripts), 1, "expected multiple base64 chunks")

        # (b) each chunk's base64 payload must be ≤ 4096 bytes.
        reassembled = ""
        for script in chunk_scripts:
            # script form: printf '%s' '<b64>' >> /tmp/_ga_codex_auth.b64
            start = script.index("printf '%s' '") + len("printf '%s' '")
            end = script.index("'", start)
            chunk = script[start:end]
            self.assertLessEqual(len(chunk), 4096)
            reassembled += chunk

        # (c) the final command base64-decodes and untars.
        final = calls[-1][-1]
        self.assertIn("base64 -d", final)
        self.assertIn("tar -xf", final)
        self.assertIn("/home/kirocrew/.codex/", final)

        # (d) reassembled base64 decodes to the exact original tar bytes.
        self.assertEqual(base64.b64decode(reassembled), tar_bytes)

    def test_missing_auth_file_raises(self) -> None:
        missing = Path(self.tmp) / "nope" / "ga-codex-auth"
        podman = Mock()
        with patch.object(_lifecycle, "_codex_auth_file_path", return_value=missing):
            with self.assertRaises(RuntimeError):
                _lifecycle._inject_codex_auth(podman, "gs-crew-xyz")


if __name__ == "__main__":
    unittest.main()
