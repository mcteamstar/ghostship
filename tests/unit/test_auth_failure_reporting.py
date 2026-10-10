"""Login completion and logout must not report success after a failed write
or delete (0.6.0 review fix).

Before: a failed credential write was logged as a warning and the handler still
returned "complete", nuked the login container and audited success, losing the
credential. A failed logout delete still returned "logged_out"; the kiro logout
also audited success before doing any work.
"""

from __future__ import annotations

import asyncio
import threading
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)
import transport.server as server  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _outcomes(audit_mock):
    return [c.kwargs.get("outcome") for c in audit_mock.call_args_list]


class TestLoginWriteFailure(unittest.TestCase):
    def setUp(self):
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": "ga-claude-login-x", "state": "code_submitted",
                "code_submitted_at": time.time(), "started_at": time.time(),
            }
        self.addCleanup(self._clear)

    def _clear(self):
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None

    def test_claude_write_failure_returns_500_and_keeps_flow_retryable(self):
        with patch.object(server, "_get_podman", return_value=Mock()), \
             patch.object(server, "_poll_claude_login_container", return_value=b"tar"), \
             patch.object(server, "_write_claude_auth_file", side_effect=OSError("disk full")), \
             patch.object(server, "_nuke_claude_login_container") as nuke, \
             patch.object(server._security, "audit_auth_event") as audit:
            response = _run(server._handle_claude_login_get(Mock()))
        self.assertEqual(response.status_code, 500)
        nuke.assert_not_called()
        self.assertIsNotNone(_lifecycle._claude_login_pending, "pending flow must survive for a retry")
        self.assertEqual(_outcomes(audit), ["failure"])


class TestLogoutDeleteFailure(unittest.TestCase):
    def _failing_path(self):
        path = MagicMock()
        path.unlink.side_effect = OSError("read-only file system")
        return path

    def test_kiro_logout_delete_failure_returns_500_without_success_audit(self):
        with patch.object(server, "_read_auth_file", return_value="x"), \
             patch.object(server, "_get_podman", return_value=Mock()), \
             patch.object(server, "_auth_file_path", return_value=self._failing_path()), \
             patch.object(server._security, "audit_auth_event") as audit:
            response = _run(server._handle_logout_post(Mock()))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(_outcomes(audit), ["failure"])

    def test_kiro_logout_audits_success_only_after_delete(self):
        order = []
        path = MagicMock()
        path.unlink.side_effect = lambda **kw: order.append("unlink")
        with patch.object(server, "_read_auth_file", return_value="x"), \
             patch.object(server, "_get_podman", return_value=Mock()), \
             patch.object(server, "_auth_file_path", return_value=path), \
             patch.object(server, "_registry_lock", threading.Lock()), \
             patch.object(server, "_load_registry", return_value={"crews": {}}), \
             patch.object(server._security, "audit_auth_event",
                          side_effect=lambda **kw: order.append(kw["outcome"])):
            response = _run(server._handle_logout_post(Mock()))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order, ["unlink", "success"])

    def test_claude_logout_delete_failure_returns_500(self):
        with patch.object(server, "_claude_auth_exists", return_value=True), \
             patch.object(server, "_get_podman", return_value=Mock()), \
             patch.object(server, "_claude_auth_file_path", return_value=self._failing_path()), \
             patch.object(server._security, "audit_auth_event") as audit:
            response = _run(server._handle_claude_logout_post(Mock()))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(_outcomes(audit), ["failure"])

    def test_logout_lists_crews_whose_wipe_failed(self):
        podman = Mock()
        podman.container_exec.side_effect = RuntimeError("exec failed")
        path = MagicMock()
        with patch.object(server, "_claude_auth_exists", return_value=True), \
             patch.object(server, "_get_podman", return_value=podman), \
             patch.object(server, "_claude_auth_file_path", return_value=path), \
             patch.object(server, "_registry_lock", threading.Lock()), \
             patch.object(server, "_load_registry", return_value={"crews": {
                 "c1": {"status": "running", "acp_backend": "claude", "container": "gs-c1"}}}), \
             patch.object(server._security, "audit_auth_event"):
            response = _run(server._handle_claude_logout_post(Mock()))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'"wipe_failed":["c1"]', response.body.replace(b" ", b""))


if __name__ == "__main__":
    unittest.main()
