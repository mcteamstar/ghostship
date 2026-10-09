"""Codex login completion requires ~/.codex/auth.json (0.6.0 review fix).

The poll used to treat any non-empty file under ~/.codex/ (for example
config.toml) as a completed login, store an archive with no credential, and
then report "Already authenticated". These tests call the real poll function.
"""

from __future__ import annotations

import base64
import io
import json
import tarfile
import unittest
from unittest.mock import Mock

from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)


def _tar(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _podman(present: str, tar_bytes: bytes | None):
    podman = Mock()

    def exec_(container, cmd):
        script = cmd[-1]
        if "test -s" in script:
            assert "/.codex/auth.json" in script, script
            return present
        if "tar -cf" in script:
            return base64.b64encode(tar_bytes).decode() if tar_bytes else ""
        raise AssertionError(f"unexpected exec: {script}")

    podman.container_exec.side_effect = exec_
    return podman


AUTH = json.dumps({"tokens": {"access_token": "t"}}).encode()


class TestCodexLoginPoll(unittest.TestCase):
    def test_config_only_does_not_complete(self):
        # auth.json absent: the test -s check fails, so nothing is archived.
        self.assertIsNone(_lifecycle._poll_codex_login_container(_podman("", None), "c"))

    def test_archive_without_auth_json_does_not_complete(self):
        tar = _tar({"./config.toml": b"model = 'x'"})
        self.assertIsNone(_lifecycle._poll_codex_login_container(_podman("present", tar), "c"))

    def test_empty_auth_json_does_not_complete(self):
        tar = _tar({"./auth.json": b""})
        self.assertIsNone(_lifecycle._poll_codex_login_container(_podman("present", tar), "c"))

    def test_auth_json_completes(self):
        tar = _tar({"./auth.json": AUTH, "./config.toml": b"x"})
        self.assertEqual(_lifecycle._poll_codex_login_container(_podman("present", tar), "c"), tar)


if __name__ == "__main__":
    unittest.main()
