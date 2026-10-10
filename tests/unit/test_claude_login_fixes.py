"""Unit tests for trn-202-claude-backend-fixes section 3: the Claude OAuth login flow.

Covers the scenarios in openspec/changes/trn-202-claude-backend-fixes/specs/claude-auth:
- Paste-back: POST /login/claude/code writes the code to the PTY (202), and
  rejects a missing flow (404), a malformed body (400) and a repeat (409).
  The code is never logged.
- Completion: only a non-empty .credentials.json completes the login. A config
  backup alone does not, and the archive must contain the credential.
- Expiry: a submitted code that does not complete within the deadline abandons
  the flow (410, container removed, audit failure).
- The returned code is null for this flow.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import socket
import tarfile
import time
import unittest
from unittest.mock import Mock, patch

from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)
import transport.server as server  # noqa: E402


def _tar_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


CRED_JSON = json.dumps({"claudeAiOauth": {"accessToken": "t"}}).encode()
BACKUP_JSON = json.dumps({"firstStartTime": "x"}).encode()


def _reset_pending():
    with _lifecycle._claude_login_pending_lock:
        _lifecycle._claude_login_pending = None


class TestArchiveHasCredential(unittest.TestCase):
    def test_backup_only_archive_does_not_count(self):
        tar = _tar_bytes({"./backups/.claude.json.backup.1": BACKUP_JSON})
        self.assertFalse(_lifecycle._archive_has_claude_credential(tar))

    def test_archive_with_non_empty_credential_counts(self):
        tar = _tar_bytes({
            "./.credentials.json": CRED_JSON,
            "./backups/.claude.json.backup.1": BACKUP_JSON,
        })
        self.assertTrue(_lifecycle._archive_has_claude_credential(tar))

    def test_empty_credential_file_does_not_count(self):
        tar = _tar_bytes({"./.credentials.json": b""})
        self.assertFalse(_lifecycle._archive_has_claude_credential(tar))

    def test_non_tar_bytes_do_not_count(self):
        self.assertFalse(_lifecycle._archive_has_claude_credential(b"not a tar"))


class TestPollClaudeLoginContainer(unittest.TestCase):
    """Completion check: the credential must exist before the archive is taken."""

    def _podman(self, present_output: str, tar_b64: str | None):
        podman = Mock()

        def exec_(container, cmd):
            script = cmd[-1]
            if "test -s" in script:
                return present_output
            if "tar -cf" in script:
                return tar_b64 or ""
            raise AssertionError(f"unexpected exec: {script}")

        podman.container_exec.side_effect = exec_
        return podman

    def test_no_credential_file_returns_none(self):
        self.assertIsNone(
            _lifecycle._poll_claude_login_container(self._podman("", None), "c")
        )

    def test_backup_only_returns_none(self):
        tar = _tar_bytes({"./backups/.claude.json.backup.1": BACKUP_JSON})
        podman = self._podman("present", base64.b64encode(tar).decode())
        self.assertIsNone(_lifecycle._poll_claude_login_container(podman, "c"))

    def test_credential_present_returns_archive(self):
        tar = _tar_bytes({"./.credentials.json": CRED_JSON})
        podman = self._podman("present", base64.b64encode(tar).decode())
        self.assertEqual(_lifecycle._poll_claude_login_container(podman, "c"), tar)


class TestSubmitClaudeLoginCode(unittest.TestCase):
    def setUp(self):
        _reset_pending()
        self.addCleanup(_reset_pending)
        self.helper_end, self.writer_end = socket.socketpair()
        self.writer_end.settimeout(2)
        self.addCleanup(self.helper_end.close)
        self.addCleanup(self.writer_end.close)

    def _set_awaiting(self):
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": "ga-claude-login-test",
                "state": "awaiting_code",
                "pty_sock": self.helper_end,
                "login_url": "https://claude.com/cai/oauth/authorize?x=1",
                "started_at": time.time(),
            }

    def test_no_pending_flow_returns_no_pending(self):
        self.assertEqual(_lifecycle._submit_claude_login_code("abc#def"),
                         {"error": "no_pending"})

    def test_code_written_to_pty_with_newline(self):
        self._set_awaiting()
        self.assertEqual(_lifecycle._submit_claude_login_code("abc#def"), {"ok": True})
        self.assertEqual(self.writer_end.recv(1024), b"abc#def\n")
        self.assertEqual(_lifecycle._claude_login_pending["state"], "code_submitted")

    def test_second_submission_is_rejected(self):
        self._set_awaiting()
        _lifecycle._submit_claude_login_code("abc#def")
        self.assertEqual(_lifecycle._submit_claude_login_code("again"),
                         {"error": "already_submitted"})

    def test_code_never_logged(self):
        self._set_awaiting()
        with self.assertLogs(level=logging.DEBUG) as logs:
            _lifecycle._submit_claude_login_code("SECRET-CODE#STATE")
            logging.getLogger(__name__).info("sentinel")
        self.assertNotIn("SECRET-CODE", "\n".join(logs.output))

    def test_unapproved_login_expires_after_approval_deadline(self):
        now = time.time()
        deadline = _lifecycle.CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS
        self.assertFalse(_lifecycle._claude_login_code_expired(
            {"state": "awaiting_code", "started_at": now - deadline + 60}))
        self.assertTrue(_lifecycle._claude_login_code_expired(
            {"state": "awaiting_code", "started_at": now - deadline - 1}))

    def test_expiry_check(self):
        now = time.time()
        self.assertFalse(_lifecycle._claude_login_code_expired(
            {"state": "awaiting_code"}))
        self.assertFalse(_lifecycle._claude_login_code_expired(
            {"state": "code_submitted", "code_submitted_at": now}))
        self.assertTrue(_lifecycle._claude_login_code_expired(
            {"state": "code_submitted",
             "code_submitted_at": now - _lifecycle.CLAUDE_LOGIN_CODE_DEADLINE_SECS - 1}))


class _FakeRequest:
    def __init__(self, body=None, raises=False):
        self._body = body
        self._raises = raises
        self.client = None
        self.headers = {}

    async def json(self):
        if self._raises:
            raise ValueError("not json")
        return self._body


class TestCodeEndpoint(unittest.TestCase):
    def setUp(self):
        _reset_pending()
        self.addCleanup(_reset_pending)
        self._backend = server.GA_CREW_ACP_BACKEND
        server.GA_CREW_ACP_BACKEND = "claude"
        self.addCleanup(setattr, server, "GA_CREW_ACP_BACKEND", self._backend)
        patcher = patch.object(server.cfg, "ga_agent_backends", frozenset({"kiro", "claude"}))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _call(self, request):
        return asyncio.run(server._handle_claude_login_code_post(request))

    def test_malformed_body_returns_400(self):
        self.assertEqual(self._call(_FakeRequest(raises=True)).status_code, 400)

    def test_missing_or_empty_code_returns_400(self):
        self.assertEqual(self._call(_FakeRequest(body={})).status_code, 400)
        self.assertEqual(self._call(_FakeRequest(body={"code": "  "})).status_code, 400)
        self.assertEqual(self._call(_FakeRequest(body={"code": 5})).status_code, 400)

    def test_no_pending_flow_returns_404(self):
        self.assertEqual(
            self._call(_FakeRequest(body={"code": "abc#def"})).status_code, 404)

    def test_wrong_backend_returns_400(self):
        with patch.object(server.cfg, "ga_agent_backends", frozenset({"kiro"})):
            self.assertEqual(
                self._call(_FakeRequest(body={"code": "abc#def"})).status_code, 400)

    def test_disabled_backend_checked_before_body(self):
        """agent-backends: the membership check runs before body validation."""
        with patch.object(server.cfg, "ga_agent_backends", frozenset({"kiro"})):
            response = self._call(_FakeRequest(raises=True))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"GA_AGENT_BACKENDS", response.body)

    def test_enabled_but_not_default_accepts_code(self):
        """agent-backends: claude login works while kiro is the default backend."""
        server.GA_CREW_ACP_BACKEND = "kiro"
        self.assertEqual(
            self._call(_FakeRequest(body={"code": "abc#def"})).status_code, 404)

    def test_valid_code_returns_202_and_response_does_not_echo_code(self):
        helper_end, writer_end = socket.socketpair()
        self.addCleanup(helper_end.close)
        self.addCleanup(writer_end.close)
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": "ga-claude-login-test",
                "state": "awaiting_code",
                "pty_sock": helper_end,
                "started_at": time.time(),
            }
        response = self._call(_FakeRequest(body={"code": "SECRET#STATE"}))
        self.assertEqual(response.status_code, 202)
        self.assertNotIn(b"SECRET", response.body)


class TestExpiredCodeOnPoll(unittest.TestCase):
    def setUp(self):
        _reset_pending()
        self.addCleanup(_reset_pending)

    def test_expired_flow_is_abandoned_with_410_and_failure_audit(self):
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": "ga-claude-login-test",
                "state": "code_submitted",
                "code_submitted_at": time.time() - _lifecycle.CLAUDE_LOGIN_CODE_DEADLINE_SECS - 5,
                "started_at": time.time(),
            }
        request = _FakeRequest()
        with patch.object(server, "_get_podman", return_value=Mock()), \
             patch.object(server, "_nuke_claude_login_container") as nuke, \
             patch.object(server._security, "audit_auth_event") as audit, \
             patch.object(server, "_poll_claude_login_container") as poll:
            response = asyncio.run(server._handle_claude_login_get(request))
        self.assertEqual(response.status_code, 410)
        nuke.assert_called_once()
        poll.assert_not_called()
        self.assertEqual(audit.call_args.kwargs["outcome"], "failure")
        self.assertIsNone(_lifecycle._claude_login_pending)


class TestClaudeOptIn(unittest.TestCase):
    """Claude is opt-in: the login endpoint refuses unless claude is in GA_AGENT_BACKENDS."""

    def test_login_refused_when_image_not_built_for_claude(self):
        from unittest.mock import Mock as _Mock
        with patch.object(server.cfg, "ga_agent_backends", frozenset({"kiro"})), \
             patch.object(server, "_initiate_claude_login") as initiate:
            response = asyncio.run(server._handle_claude_login_post(_Mock()))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"GA_AGENT_BACKENDS", response.body)
        initiate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
