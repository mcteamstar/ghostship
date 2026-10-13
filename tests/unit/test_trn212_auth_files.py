"""Unit tests for login auth-file helpers (trn-212-test-coverage-gaps D).

Covers the login credential writers and the Codex inject chunking path, which
the proposal flagged as untested (only ``_save_registry`` had equivalent
coverage):

- ``_write_auth_file``        — 0o600 mode, exact content, overwrite.
- ``_write_codex_auth_file``  — 0o600 mode, byte payload.
- ``_inject_codex_auth`` / ``_inject_claude_auth`` — mkdir first, then a single
  ``container_archive_put`` of the raw tar at ``~/.codex/`` / ``~/.claude/``
  with no ``sh``/``printf`` shell exec (SEC-1).
- ``_write_dashboard_cookie`` — in-memory tar member, mode 0600, written via
  ``container_archive_put`` with no ``python3 -c`` exec (SEC-2).

All tests use real tmpdir paths (design.md D3 — mocking os.open/os.fchmod would
not verify the on-disk permission).
"""

from __future__ import annotations

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


class TestInjectCodexAuthArchivePut(_TmpdirBase):
    """D.4 (SEC-1) — _inject_codex_auth streams the tar via container_archive_put,
    with no sh/printf shell exec and no base64 chunking."""

    @staticmethod
    def _make_tar() -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            data = (b"openai-codex-auth-json-" * 400)
            info = tarfile.TarInfo("auth.json")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def test_archive_put_and_no_shell(self) -> None:
        tar_bytes = self._make_tar()
        auth_path = Path(self.tmp) / "ga-codex-auth"
        _lifecycle._write_codex_auth_file(tar_bytes, _path=auth_path)

        exec_calls: list[list[str]] = []
        podman = Mock()
        podman.container_exec.side_effect = lambda container, cmd: exec_calls.append(cmd) or ""

        with patch.object(_lifecycle, "_codex_auth_file_path", return_value=auth_path):
            _lifecycle._inject_codex_auth(podman, "gs-crew-xyz")

        # (a) container_exec is only ever the mkdir -p — never sh or printf.
        for cmd in exec_calls:
            self.assertNotIn(cmd[0], ("sh", "printf"))
        self.assertEqual(exec_calls[0][:2], ["mkdir", "-p"])
        self.assertIn("/home/kirocrew/.codex", exec_calls[0])

        # (b) the tar is handed to container_archive_put verbatim at ~/.codex/.
        podman.container_archive_put.assert_called_once()
        args = podman.container_archive_put.call_args.args
        self.assertEqual(args[0], "gs-crew-xyz")
        self.assertEqual(args[1], "/home/kirocrew/.codex/")
        self.assertEqual(args[2], tar_bytes)

    def test_missing_auth_file_raises(self) -> None:
        missing = Path(self.tmp) / "nope" / "ga-codex-auth"
        podman = Mock()
        with patch.object(_lifecycle, "_codex_auth_file_path", return_value=missing):
            with self.assertRaises(RuntimeError):
                _lifecycle._inject_codex_auth(podman, "gs-crew-xyz")


class TestInjectClaudeAuthArchivePut(_TmpdirBase):
    """SEC-1 — _inject_claude_auth streams the tar via container_archive_put,
    with no sh/printf shell exec."""

    @staticmethod
    def _make_tar() -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            data = (b"claude-oauth-creds-" * 400)
            info = tarfile.TarInfo(".credentials.json")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def test_archive_put_and_no_shell(self) -> None:
        tar_bytes = self._make_tar()
        auth_path = Path(self.tmp) / "ga-claude-auth"
        auth_path.write_bytes(tar_bytes)

        exec_calls: list[list[str]] = []
        podman = Mock()
        podman.container_exec.side_effect = lambda container, cmd: exec_calls.append(cmd) or ""

        with patch.object(_lifecycle, "_claude_auth_file_path", return_value=auth_path):
            _lifecycle._inject_claude_auth(podman, "gs-crew-abc")

        # container_exec is only ever the mkdir -p — never sh or printf.
        for cmd in exec_calls:
            self.assertNotIn(cmd[0], ("sh", "printf"))
        self.assertEqual(exec_calls[0][:2], ["mkdir", "-p"])
        self.assertIn("/home/kirocrew/.claude", exec_calls[0])

        podman.container_archive_put.assert_called_once()
        args = podman.container_archive_put.call_args.args
        self.assertEqual(args[0], "gs-crew-abc")
        self.assertEqual(args[1], "/home/kirocrew/.claude/")
        self.assertEqual(args[2], tar_bytes)

    def test_missing_auth_file_raises(self) -> None:
        missing = Path(self.tmp) / "nope" / "ga-claude-auth"
        podman = Mock()
        with patch.object(_lifecycle, "_claude_auth_file_path", return_value=missing):
            with self.assertRaises(RuntimeError):
                _lifecycle._inject_claude_auth(podman, "gs-crew-abc")


class TestWriteDashboardCookieArchivePut(_TmpdirBase):
    """SEC-2 — _write_dashboard_cookie builds an in-memory tar and writes via
    container_archive_put, never via python3 -c."""

    def test_archive_put_no_python_exec(self) -> None:
        exec_calls: list[list[str]] = []
        podman = Mock()
        podman.container_exec.side_effect = lambda container, cmd: exec_calls.append(cmd) or ""

        cookie = "mc_token_5476=abc123-def456"
        ok = _lifecycle._write_dashboard_cookie(podman, "gs-crew-cookie", cookie)
        self.assertTrue(ok)

        # (a) python3 is never exec'd for this path (no container_exec at all).
        for cmd in exec_calls:
            self.assertNotIn("python3", cmd[0])

        # (b) exactly one archive_put, into the cookie's parent directory.
        podman.container_archive_put.assert_called_once()
        name, dest_dir, tar_body = podman.container_archive_put.call_args.args
        self.assertEqual(name, "gs-crew-cookie")
        self.assertEqual(dest_dir, os.path.dirname(_lifecycle._DASHBOARD_COOKIE_PATH))

        # (c) the tar carries the cookie value at the right member, mode 0600.
        member = os.path.basename(_lifecycle._DASHBOARD_COOKIE_PATH)
        with tarfile.open(fileobj=io.BytesIO(tar_body), mode="r") as tf:
            info = tf.getmember(member)
            self.assertEqual(info.mode & 0o777, 0o600)
            self.assertEqual(tf.extractfile(info).read().decode(), cookie)

    def test_returns_false_on_failure(self) -> None:
        podman = Mock()
        podman.container_archive_put.side_effect = RuntimeError("boom")
        ok = _lifecycle._write_dashboard_cookie(podman, "gs-crew-cookie", "x=y")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
