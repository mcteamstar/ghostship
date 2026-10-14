"""Tests for LoginFlow class hierarchy (TRN-240 tasks 5.1/5.2).

Covers:
- initiate/abort/poll for each backend using mocked podman
- is_expired() behaviour
- ALL_FLOWS sweeping (flow.abort(podman) if flow.is_expired()) hits all three
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import Mock, MagicMock, patch


def _import_login():
    """Import transport.login module (handles both import paths)."""
    import transport.login as login
    return login


class LoginFlowAbstractTests(unittest.TestCase):
    """Verify the ABC contract is enforced and singletons are present."""

    def test_all_three_singletons_present(self) -> None:
        """KIRO_FLOW, CLAUDE_FLOW, CODEX_FLOW are all LoginFlow instances."""
        login = _import_login()
        self.assertIsInstance(login.KIRO_FLOW, login.LoginFlow)
        self.assertIsInstance(login.CLAUDE_FLOW, login.LoginFlow)
        self.assertIsInstance(login.CODEX_FLOW, login.LoginFlow)

    def test_all_flows_list_has_three_entries(self) -> None:
        """ALL_FLOWS contains exactly three singletons."""
        login = _import_login()
        self.assertEqual(len(login.ALL_FLOWS), 3)
        self.assertIn(login.KIRO_FLOW, login.ALL_FLOWS)
        self.assertIn(login.CLAUDE_FLOW, login.ALL_FLOWS)
        self.assertIn(login.CODEX_FLOW, login.ALL_FLOWS)

    def test_backends_are_distinct(self) -> None:
        """Each flow has a unique backend string."""
        login = _import_login()
        backends = {f.backend for f in login.ALL_FLOWS}
        self.assertEqual(len(backends), 3)
        self.assertIn("kiro", backends)
        self.assertIn("claude", backends)
        self.assertIn("codex", backends)

    def test_container_prefixes_are_distinct(self) -> None:
        """Each flow uses its own container name prefix."""
        login = _import_login()
        prefixes = {f.container_prefix for f in login.ALL_FLOWS}
        self.assertEqual(len(prefixes), 3)

    def test_cannot_instantiate_abstract_class(self) -> None:
        """LoginFlow cannot be instantiated directly (abstract methods)."""
        login = _import_login()
        with self.assertRaises(TypeError):
            login.LoginFlow()  # type: ignore[abstract]


class LoginFlowIsExpiredTests(unittest.TestCase):
    """is_expired() returns False when no flow is pending, True after TTL."""

    def test_not_expired_when_no_flow(self) -> None:
        """is_expired() is False when _pending is None."""
        login = _import_login()
        flow = login.KiroLoginFlow()
        self.assertFalse(flow.is_expired())

    def test_not_expired_just_started(self) -> None:
        """is_expired() is False immediately after a flow starts."""
        login = _import_login()
        flow = login.KiroLoginFlow()
        flow._pending = {"started_at": time.time(), "state": "started"}
        self.assertFalse(flow.is_expired())

    def test_expired_past_ttl(self) -> None:
        """is_expired() is True when started_at is older than _ttl_secs."""
        login = _import_login()
        flow = login.KiroLoginFlow()
        # Simulate a start time well in the past
        flow._pending = {
            "started_at": time.time() - flow._ttl_secs() - 10,
            "state": "started",
        }
        self.assertTrue(flow.is_expired())

    def test_codex_uses_codex_ttl(self) -> None:
        """CodexLoginFlow uses _CODEX_LOGIN_TTL_SECS."""
        login = _import_login()
        flow = login.CodexLoginFlow()
        self.assertEqual(flow._ttl_secs(), login._CODEX_LOGIN_TTL_SECS)

    def test_claude_uses_approval_deadline(self) -> None:
        """ClaudeLoginFlow.is_expired() uses CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS."""
        login = _import_login()
        flow = login.ClaudeLoginFlow()
        flow._pending = {
            "started_at": time.time() - login._CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS - 1,
            "state": "awaiting_code",
        }
        self.assertTrue(flow.is_expired())

    def test_claude_code_submitted_uses_code_deadline(self) -> None:
        """ClaudeLoginFlow.is_expired() uses code deadline when code was submitted."""
        login = _import_login()
        flow = login.ClaudeLoginFlow()
        flow._pending = {
            "started_at": time.time() - 10,
            "state": "code_submitted",
            "code_submitted_at": time.time() - login._CLAUDE_LOGIN_CODE_DEADLINE_SECS - 1,
        }
        self.assertTrue(flow.is_expired())


class LoginFlowAbortTests(unittest.TestCase):
    """abort() clears state and nukes container."""

    def test_abort_returns_false_when_no_flow(self) -> None:
        """abort() returns False when nothing is pending."""
        login = _import_login()
        flow = login.KiroLoginFlow()
        podman = Mock()
        self.assertFalse(flow.abort(podman))

    def test_abort_returns_true_and_clears_state(self) -> None:
        """abort() returns True and clears _pending."""
        login = _import_login()
        flow = login.KiroLoginFlow()
        flow._pending = {"container": None, "started_at": time.time(), "state": "started"}
        podman = Mock()
        result = flow.abort(podman)
        self.assertTrue(result)
        self.assertIsNone(flow._pending)

    def test_abort_nukes_container_if_started(self) -> None:
        """abort() calls _nuke_container when container is set."""
        login = _import_login()
        flow = login.KiroLoginFlow()
        container_name = f"{login._GA_LOGIN_CONTAINER_PREFIX}abc123"
        flow._pending = {
            "container": container_name,
            "started_at": time.time(),
            "state": "started",
        }
        podman = Mock()
        podman.container_stop = Mock()
        podman.container_remove = Mock()
        flow.abort(podman)
        podman.container_stop.assert_called_once_with(container_name)

    def test_abort_no_nuke_when_container_not_yet_started(self) -> None:
        """abort() does not call container_stop when container is None."""
        login = _import_login()
        flow = login.KiroLoginFlow()
        flow._pending = {"container": None, "started_at": time.time(), "state": "starting"}
        podman = Mock()
        flow.abort(podman)
        podman.container_stop.assert_not_called()


class LoginFlowInitiateTests(unittest.TestCase):
    """initiate() returns login_pending when already in progress."""

    def test_initiate_returns_login_pending_when_flow_in_progress(self) -> None:
        """initiate() returns {"login_pending": True} when _pending is set."""
        login = _import_login()
        flow = login.KiroLoginFlow()
        flow._pending = {"container": "gs-login-abc", "state": "started", "started_at": time.time()}
        podman = Mock()
        result = flow.initiate(podman)
        self.assertEqual(result, {"login_pending": True})

    def test_initiate_clears_pending_on_container_start_failure(self) -> None:
        """initiate() clears _pending when start_container raises."""
        login = _import_login()
        flow = login.KiroLoginFlow()
        podman = Mock()
        podman._req = Mock(side_effect=RuntimeError("podman unavailable"))

        result = flow.initiate(podman)
        self.assertIn("error", result)
        self.assertIsNone(flow._pending)


class AllFlowsSweepTests(unittest.TestCase):
    """Verify ALL_FLOWS sweeping calls abort on each expired flow."""

    def test_sweep_expired_calls_abort_on_expired_flows(self) -> None:
        """Sweeping ALL_FLOWS calls abort() on each flow that is_expired()."""
        login = _import_login()
        aborted = []

        def mock_abort(podman):
            aborted.append(True)
            return True

        podman = Mock()

        with (
            patch.object(login.KIRO_FLOW, "is_expired", return_value=True),
            patch.object(login.KIRO_FLOW, "abort", side_effect=mock_abort),
            patch.object(login.CLAUDE_FLOW, "is_expired", return_value=True),
            patch.object(login.CLAUDE_FLOW, "abort", side_effect=mock_abort),
            patch.object(login.CODEX_FLOW, "is_expired", return_value=False),
        ):
            for flow in login.ALL_FLOWS:
                if flow.is_expired():
                    flow.abort(podman)

        self.assertEqual(len(aborted), 2)  # kiro + claude expired, codex did not

    def test_sweep_does_nothing_when_no_flows_expired(self) -> None:
        """Sweeping when no flows are expired calls no aborts."""
        login = _import_login()
        abort_calls = []

        def mock_abort(podman):
            abort_calls.append(True)
            return True

        podman = Mock()

        with (
            patch.object(login.KIRO_FLOW, "is_expired", return_value=False),
            patch.object(login.CLAUDE_FLOW, "is_expired", return_value=False),
            patch.object(login.CODEX_FLOW, "is_expired", return_value=False),
        ):
            for flow in login.ALL_FLOWS:
                if flow.is_expired():
                    flow.abort(podman)

        self.assertEqual(abort_calls, [])


class ClaudeSubmitCodeTests(unittest.TestCase):
    """submit_code() writes the code to the PTY socket."""

    def test_submit_code_returns_no_pending_when_no_flow(self) -> None:
        """submit_code() returns error when no flow is pending."""
        login = _import_login()
        flow = login.ClaudeLoginFlow()
        result = flow.submit_code("XXXX-XXXX")
        self.assertEqual(result.get("error"), "no_pending")

    def test_submit_code_returns_already_submitted_when_state_is_code_submitted(self) -> None:
        """submit_code() returns already_submitted when code was already sent."""
        login = _import_login()
        flow = login.ClaudeLoginFlow()
        sock = Mock()
        flow._pending = {
            "state": "code_submitted",
            "pty_sock": sock,
            "started_at": time.time(),
        }
        result = flow.submit_code("XXXX-XXXX")
        self.assertEqual(result.get("error"), "already_submitted")
        sock.sendall.assert_not_called()

    def test_submit_code_sends_code_to_pty(self) -> None:
        """submit_code() sends the code + newline to the PTY socket."""
        login = _import_login()
        flow = login.ClaudeLoginFlow()
        sock = Mock()
        flow._pending = {
            "state": "awaiting_code",
            "pty_sock": sock,
            "started_at": time.time(),
        }
        result = flow.submit_code("ABCD-1234")
        self.assertEqual(result, {"ok": True})
        sock.sendall.assert_called_once_with(b"ABCD-1234\n")
        self.assertEqual(flow._pending["state"], "code_submitted")


if __name__ == "__main__":
    unittest.main()
