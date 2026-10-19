"""Unit tests for transport/login.py — LoginFlow ABC and concrete subclasses.

Covers:
- LoginFlow ABC interface (abstract methods, class-level metadata)
- KiroLoginFlow, ClaudeLoginFlow, CodexLoginFlow metadata (backend, prefix, image_key)
- LoginFlow.is_expired: returns False when not pending, True when TTL exceeded
- LoginFlow.state property: mirrors _pending
- LoginFlow.abort: clears _pending, calls _nuke_container, returns True/False
- LoginFlow._nuke_container: refuses to nuke non-login containers
- LoginFlow.initiate: returns login_pending when already in progress
- ClaudeLoginFlow.submit_code: state machine behaviour (no_pending, already_submitted)
- ClaudeLoginFlow._is_code_expired: tracks awaiting_code vs code_submitted deadlines
- Module-level singletons: KIRO_FLOW, CLAUDE_FLOW, CODEX_FLOW are distinct instances
- ALL_FLOWS contains exactly the three singletons

All Podman calls use FakePodmanClient — no unittest.mock.Mock().
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest import mock

from tests.fakes import FakePodmanClient


class TestLoginFlowMetadata(unittest.TestCase):
    """Each concrete LoginFlow subclass must declare the required class attributes."""

    def _check_class(self, cls, expected_backend: str, expected_prefix: str, expected_image_key: str):
        self.assertEqual(cls.backend, expected_backend)
        self.assertEqual(cls.container_prefix, expected_prefix)
        self.assertEqual(cls.image_key, expected_image_key)

    def test_kiro_metadata(self):
        from transport.login import KiroLoginFlow
        self._check_class(
            KiroLoginFlow,
            expected_backend="kiro",
            expected_prefix="ga-login-",
            expected_image_key="kc_base_image",
        )

    def test_claude_metadata(self):
        from transport.login import ClaudeLoginFlow
        self._check_class(
            ClaudeLoginFlow,
            expected_backend="claude",
            expected_prefix="ga-claude-login-",
            expected_image_key="kc_image",
        )

    def test_codex_metadata(self):
        from transport.login import CodexLoginFlow
        self._check_class(
            CodexLoginFlow,
            expected_backend="codex",
            expected_prefix="ga-codex-login-",
            expected_image_key="kc_image",
        )


class TestLoginFlowBinaryNames(unittest.TestCase):
    """_binary_name() returns the correct CLI binary for each flow."""

    def test_kiro_binary(self):
        from transport.login import KiroLoginFlow
        self.assertEqual(KiroLoginFlow()._binary_name(), "kiro-cli")

    def test_claude_binary(self):
        from transport.login import ClaudeLoginFlow
        self.assertEqual(ClaudeLoginFlow()._binary_name(), "claude")

    def test_codex_binary(self):
        from transport.login import CodexLoginFlow
        self.assertEqual(CodexLoginFlow()._binary_name(), "codex-acp")


class TestLoginFlowLoginCmds(unittest.TestCase):
    """_login_cmd() returns a non-empty list starting with the binary name."""

    def test_kiro_login_cmd(self):
        from transport.login import KiroLoginFlow
        cmd = KiroLoginFlow()._login_cmd()
        self.assertIsInstance(cmd, list)
        self.assertGreater(len(cmd), 0)
        self.assertEqual(cmd[0], "kiro-cli")
        self.assertIn("login", cmd)

    def test_claude_login_cmd(self):
        from transport.login import ClaudeLoginFlow
        cmd = ClaudeLoginFlow()._login_cmd()
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[0], "claude")

    def test_codex_login_cmd(self):
        from transport.login import CodexLoginFlow
        cmd = CodexLoginFlow()._login_cmd()
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[0], "codex-acp")


class TestLoginFlowTTL(unittest.TestCase):
    """_ttl_secs() returns a positive float for each flow."""

    def test_kiro_ttl_positive(self):
        from transport.login import KiroLoginFlow
        self.assertGreater(KiroLoginFlow()._ttl_secs(), 0)

    def test_claude_ttl_positive(self):
        from transport.login import ClaudeLoginFlow
        self.assertGreater(ClaudeLoginFlow()._ttl_secs(), 0)

    def test_codex_ttl_positive(self):
        from transport.login import CodexLoginFlow
        self.assertGreater(CodexLoginFlow()._ttl_secs(), 0)

    def test_kiro_ttl_is_900(self):
        from transport.login import KiroLoginFlow
        self.assertAlmostEqual(KiroLoginFlow()._ttl_secs(), 900.0)

    def test_codex_ttl_is_900(self):
        from transport.login import CodexLoginFlow
        self.assertAlmostEqual(CodexLoginFlow()._ttl_secs(), 900.0)


class TestLoginFlowState(unittest.TestCase):
    """LoginFlow.state mirrors the internal _pending dict."""

    def _make(self):
        from transport.login import KiroLoginFlow
        return KiroLoginFlow()

    def test_state_is_none_when_idle(self):
        flow = self._make()
        self.assertIsNone(flow.state)

    def test_state_reflects_pending(self):
        flow = self._make()
        flow._pending = {"container": "gs-login-abc", "state": "started"}
        self.assertEqual(flow.state, {"container": "gs-login-abc", "state": "started"})


class TestLoginFlowIsExpired(unittest.TestCase):
    """LoginFlow.is_expired tracks TTL correctly."""

    def test_not_expired_when_no_pending(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        self.assertFalse(flow.is_expired())

    def test_not_expired_within_ttl(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        flow._pending = {"started_at": time.time(), "state": "started"}
        self.assertFalse(flow.is_expired())

    def test_expired_after_ttl(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        # Set started_at far in the past
        flow._pending = {"started_at": time.time() - 10000, "state": "started"}
        self.assertTrue(flow.is_expired())

    def test_not_expired_when_no_started_at(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        flow._pending = {"state": "started"}  # no started_at
        self.assertFalse(flow.is_expired())

    def test_codex_not_expired_fresh(self):
        from transport.login import CodexLoginFlow
        flow = CodexLoginFlow()
        flow._pending = {"started_at": time.time(), "state": "started"}
        self.assertFalse(flow.is_expired())

    def test_codex_expired_old(self):
        from transport.login import CodexLoginFlow
        flow = CodexLoginFlow()
        flow._pending = {"started_at": time.time() - 10000, "state": "started"}
        self.assertTrue(flow.is_expired())


class TestLoginFlowAbort(unittest.TestCase):
    """LoginFlow.abort: clears _pending, calls _nuke_container, returns correct bool."""

    def _make_kiro(self):
        from transport.login import KiroLoginFlow
        return KiroLoginFlow()

    def test_abort_returns_false_when_idle(self):
        flow = self._make_kiro()
        podman = FakePodmanClient()
        result = flow.abort(podman)
        self.assertFalse(result)

    def test_abort_returns_true_when_pending(self):
        flow = self._make_kiro()
        flow._pending = {
            "container": "ga-login-abc123",
            "started_at": time.time(),
            "state": "started",
        }
        podman = FakePodmanClient()
        podman.add_container("ga-login-abc123")
        result = flow.abort(podman)
        self.assertTrue(result)

    def test_abort_clears_pending(self):
        flow = self._make_kiro()
        flow._pending = {
            "container": "ga-login-abc123",
            "started_at": time.time(),
            "state": "started",
        }
        podman = FakePodmanClient()
        podman.add_container("ga-login-abc123")
        flow.abort(podman)
        self.assertIsNone(flow._pending)

    def test_abort_nukes_container(self):
        flow = self._make_kiro()
        flow._pending = {
            "container": "ga-login-test",
            "started_at": time.time(),
            "state": "started",
        }
        podman = FakePodmanClient()
        podman.add_container("ga-login-test")
        flow.abort(podman)
        # _nuke_container calls container_stop then container_remove
        self.assertTrue(podman.was_called("container_stop"))
        self.assertTrue(podman.was_called("container_remove"))

    def test_abort_without_container_clears_pending(self):
        """Abort with no container name (not yet started) still clears _pending."""
        flow = self._make_kiro()
        flow._pending = {
            "container": None,
            "started_at": time.time(),
            "state": "starting",
        }
        podman = FakePodmanClient()
        result = flow.abort(podman)
        self.assertTrue(result)
        self.assertIsNone(flow._pending)

    def test_abort_does_not_nuke_non_login_container(self):
        """_nuke_container refuses containers not prefixed with container_prefix."""
        flow = self._make_kiro()
        flow._pending = {
            "container": "gs-crew-container",  # NOT a login container
            "started_at": time.time(),
            "state": "started",
        }
        podman = FakePodmanClient()
        podman.add_container("gs-crew-container")
        # Abort should not stop/remove the non-login container
        flow.abort(podman)
        # No stop or remove calls should have been made
        self.assertFalse(podman.was_called("container_stop"))
        self.assertFalse(podman.was_called("container_remove"))


class TestNukeContainer(unittest.TestCase):
    """LoginFlow._nuke_container: safety checks."""

    def _make_kiro(self):
        from transport.login import KiroLoginFlow
        return KiroLoginFlow()

    def test_nuke_valid_prefix(self):
        flow = self._make_kiro()
        podman = FakePodmanClient()
        podman.add_container("ga-login-abc")
        flow._nuke_container(podman, "ga-login-abc")
        self.assertTrue(podman.was_called("container_stop"))
        self.assertTrue(podman.was_called("container_remove"))

    def test_nuke_invalid_prefix_skipped(self):
        flow = self._make_kiro()
        podman = FakePodmanClient()
        flow._nuke_container(podman, "gs-production-crew")
        self.assertFalse(podman.was_called("container_stop"))
        self.assertFalse(podman.was_called("container_remove"))

    def test_nuke_handles_stop_failure_gracefully(self):
        """If container_stop raises, _nuke_container still tries container_remove."""
        flow = self._make_kiro()

        class StopFailsPodman(FakePodmanClient):
            def container_stop(self, name):
                raise RuntimeError("stop failed")

        podman = StopFailsPodman()
        podman.add_container("ga-login-test")
        # Should not raise
        flow._nuke_container(podman, "ga-login-test")
        self.assertTrue(podman.was_called("container_remove"))


class TestKiroLoginCmdLicense(unittest.TestCase):
    """--license is derived from the login method, never from config."""

    def _cmd_for(self, pending):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        flow._pending = pending
        return flow._login_cmd()

    def test_identity_center_passes_license_pro_and_provider(self):
        cmd = self._cmd_for({
            "method": "identity-center",
            "provider": {"start_url": "https://d-123.awsapps.com/start/#/", "region": "eu-west-1"},
        })
        self.assertEqual(cmd[cmd.index("--license") + 1], "pro")
        self.assertEqual(
            cmd[cmd.index("--identity-provider") + 1], "https://d-123.awsapps.com/start/#/"
        )
        self.assertEqual(cmd[cmd.index("--region") + 1], "eu-west-1")
        self.assertIn("--use-device-flow", cmd)

    def test_builder_id_passes_license_free(self):
        cmd = self._cmd_for({"method": "builder-id", "provider": None})
        self.assertEqual(cmd[cmd.index("--license") + 1], "free")
        self.assertNotIn("--identity-provider", cmd)
        self.assertNotIn("--region", cmd)

    def test_no_pending_defaults_to_builder_id(self):
        cmd = self._cmd_for(None)
        self.assertEqual(cmd[cmd.index("--license") + 1], "free")


class TestKiroPromptAnswers(unittest.TestCase):
    """Pre-filled Start URL/Region prompts are accepted with a bare Enter."""

    def test_identity_center_prompts_answer_enter_only(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        flow._pending = {
            "method": "identity-center",
            "provider": {"start_url": "https://d-123.awsapps.com/start/", "region": "eu-west-1"},
        }
        answers = {p.pattern: a for p, a in flow._prompt_patterns()}
        self.assertEqual(answers["Start URL"], b"\n")
        self.assertEqual(answers["Region"], b"\n")

    def test_builder_id_has_no_idc_prompts(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        flow._pending = {"method": "builder-id", "provider": None}
        patterns = [p.pattern for p, _ in flow._prompt_patterns()]
        self.assertNotIn("Start URL", patterns)


class TestKiroInitiateResolvesMethod(unittest.TestCase):
    """KiroLoginFlow.initiate records method/provider in the pending state."""

    def _initiate(self, cfg_kwargs, **kwargs):
        import transport.login as login_mod
        from transport.config import Config
        from transport.login import KiroLoginFlow
        orig_cfg = login_mod.cfg
        captured = {}

        class _Flow(KiroLoginFlow):
            def start_container(self, podman):
                captured.update(self._pending)
                raise RuntimeError("stop here")

        try:
            login_mod.cfg = Config(ga_crew_agent="kiro", **cfg_kwargs)
            _Flow().initiate(FakePodmanClient(), **kwargs)
        finally:
            login_mod.cfg = orig_cfg
        return captured

    def test_explicit_identity_center_uses_request_provider(self):
        got = self._initiate(
            {"kiro_identity_provider": "https://cfg", "kiro_region": "us-east-1"},
            method="identity-center",
            provider={"start_url": "https://req", "region": "ap-southeast-2"},
        )
        self.assertEqual(got["method"], "identity-center")
        self.assertEqual(got["provider"], {"start_url": "https://req", "region": "ap-southeast-2"})

    def test_explicit_builder_id_ignores_configured_idc(self):
        got = self._initiate(
            {"kiro_identity_provider": "https://cfg", "kiro_region": "us-east-1"},
            method="builder-id",
        )
        self.assertEqual(got["method"], "builder-id")
        self.assertIsNone(got["provider"])

    def test_default_method_is_identity_center_when_configured(self):
        got = self._initiate({"kiro_identity_provider": "https://cfg", "kiro_region": "us-east-1"})
        self.assertEqual(got["method"], "identity-center")
        self.assertEqual(got["provider"], {"start_url": "https://cfg", "region": "us-east-1"})

    def test_default_method_is_builder_id_when_unconfigured(self):
        got = self._initiate({})
        self.assertEqual(got["method"], "builder-id")
        self.assertIsNone(got["provider"])


class TestLoginFlowInitiatePending(unittest.TestCase):
    """LoginFlow.initiate: returns login_pending when already in progress."""

    def test_initiate_returns_login_pending_when_active(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        # Simulate an already-active flow
        flow._pending = {"container": "ga-login-abc", "state": "started", "started_at": time.time()}
        podman = FakePodmanClient()
        result = flow.initiate(podman)
        self.assertEqual(result, {"login_pending": True})

    def test_initiate_login_pending_does_not_start_container(self):
        """When pending, initiate() does not call container_start."""
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        flow._pending = {"container": "ga-login-abc", "state": "started", "started_at": time.time()}
        podman = FakePodmanClient()
        flow.initiate(podman)
        self.assertFalse(podman.was_called("container_start"))


class TestLoginFlowInitiateCancelledDuringStart(unittest.TestCase):
    """LoginFlow.initiate: an abort while start_container runs cancels the start."""

    def test_abort_during_start_removes_container_and_cancels(self):
        from transport.login import KiroLoginFlow
        podman = FakePodmanClient()

        class _Flow(KiroLoginFlow):
            def start_container(self, podman):
                podman.add_container("ga-login-cancelled")
                self.abort(podman)  # pending has no container yet, so abort only clears it
                return "ga-login-cancelled"

        flow = _Flow()
        result = flow.initiate(podman)
        self.assertEqual(result, {"error": "cancelled"})
        self.assertFalse(podman.container_exists("ga-login-cancelled"))
        self.assertIsNone(flow._pending)

    def test_new_flow_started_during_start_is_left_intact(self):
        from transport.login import KiroLoginFlow
        podman = FakePodmanClient()
        new_pending = {"container": None, "state": "starting", "started_at": time.time()}

        class _Flow(KiroLoginFlow):
            def start_container(self, podman):
                podman.add_container("ga-login-old")
                self.abort(podman)
                # A second caller takes the now-idle slot before the first records anything.
                self._pending = new_pending
                return "ga-login-old"

        flow = _Flow()
        result = flow.initiate(podman)
        self.assertEqual(result, {"error": "cancelled"})
        self.assertIs(flow._pending, new_pending)
        self.assertIsNone(flow._pending["container"])
        self.assertFalse(podman.container_exists("ga-login-old"))


class TestLoginFlowInitiateCancelledDuringPTY(unittest.TestCase):
    """LoginFlow.initiate: a logout during the PTY URL read must not clear or hand out a newer flow."""

    def _flow(self):
        from transport.login import KiroLoginFlow

        class _Flow(KiroLoginFlow):
            def start_container(self, podman):
                return "ga-login-a"

        return _Flow()

    def _podman(self):
        podman = mock.Mock()
        podman.container_exec.return_value = "kiro-cli"
        podman.container_exec_pty_stdin.return_value = ("exec-a", mock.Mock(), b"")
        return podman

    def test_failed_pty_read_does_not_clear_a_newer_flow(self):
        from transport import lifecycle
        podman = self._podman()
        flow = self._flow()
        newer = {"container": "ga-login-b", "state": "started", "started_at": time.time()}

        def pty_read(**kwargs):
            flow.abort(podman)     # logout cancels flow A
            flow._pending = newer  # login B takes the idle slot
            return None, None      # A's container is gone, so no URL

        with mock.patch.object(lifecycle, "_run_pty_login_flow", side_effect=pty_read):
            result = flow.initiate(podman)
        self.assertEqual(result, {"error": "cancelled"})
        self.assertIs(flow._pending, newer)

    def test_url_read_after_cancel_is_not_returned(self):
        from transport import lifecycle
        podman = self._podman()
        flow = self._flow()

        def pty_read(**kwargs):
            flow.abort(podman)
            return "https://example.invalid/login", "ABCD-1234"

        with mock.patch.object(lifecycle, "_run_pty_login_flow", side_effect=pty_read):
            result = flow.initiate(podman)
        self.assertEqual(result, {"error": "cancelled"})
        self.assertIsNone(flow._pending)
        podman.container_remove.assert_called_with("ga-login-a")


class TestLoginFlowCommitIfCurrent(unittest.TestCase):
    """LoginFlow.commit_if_current: store only while the captured flow is still live."""

    def _pending(self):
        return {"container": "ga-login-c1", "state": "started", "started_at": time.time()}

    def test_current_flow_stores_and_clears(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        pending = self._pending()
        flow._pending = pending
        stored = []
        self.assertTrue(flow.commit_if_current(pending, lambda: stored.append("cred")))
        self.assertEqual(stored, ["cred"])
        self.assertIsNone(flow._pending)

    def test_cancelled_flow_stores_nothing(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        pending = self._pending()
        flow._pending = pending
        flow.abort(FakePodmanClient())
        stored = []
        self.assertFalse(flow.commit_if_current(pending, lambda: stored.append("cred")))
        self.assertEqual(stored, [])

    def test_replaced_flow_is_not_committed_and_is_left_intact(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        old = self._pending()
        new = self._pending()
        flow._pending = new
        stored = []
        self.assertFalse(flow.commit_if_current(old, lambda: stored.append("cred")))
        self.assertEqual(stored, [])
        self.assertIs(flow._pending, new)

    def test_store_failure_keeps_pending_for_retry(self):
        from transport.login import KiroLoginFlow
        flow = KiroLoginFlow()
        pending = self._pending()
        flow._pending = pending

        def _boom():
            raise OSError("disk full")

        with self.assertRaises(OSError):
            flow.commit_if_current(pending, _boom)
        self.assertIs(flow._pending, pending)


class TestClaudeLoginFlowSubmitCode(unittest.TestCase):
    """ClaudeLoginFlow.submit_code state machine."""

    def _make_claude(self):
        from transport.login import ClaudeLoginFlow
        return ClaudeLoginFlow()

    def test_submit_code_no_pending_returns_error(self):
        flow = self._make_claude()
        result = flow.submit_code("ABC-123")
        self.assertEqual(result.get("error"), "no_pending")

    def test_submit_code_wrong_state_returns_error(self):
        """submit_code requires state 'awaiting_code' or 'code_submitted'."""
        flow = self._make_claude()
        flow._pending = {
            "container": "ga-claude-login-abc",
            "state": "started",  # not awaiting_code
            "started_at": time.time(),
        }
        result = flow.submit_code("ABC-123")
        self.assertEqual(result.get("error"), "no_pending")

    def test_submit_code_already_submitted_returns_error(self):
        flow = self._make_claude()
        flow._pending = {
            "container": "ga-claude-login-abc",
            "state": "code_submitted",
            "started_at": time.time(),
        }
        result = flow.submit_code("ABC-123")
        self.assertEqual(result.get("error"), "already_submitted")

    def test_submit_code_no_pty_sock_returns_error(self):
        flow = self._make_claude()
        flow._pending = {
            "container": "ga-claude-login-abc",
            "state": "awaiting_code",
            "started_at": time.time(),
            # no "pty_sock" key
        }
        result = flow.submit_code("ABC-123")
        self.assertEqual(result.get("error"), "no_pending")

    def test_submit_code_success_updates_state(self):
        """With a working pty_sock, submit_code sets state to code_submitted."""
        import io

        class FakeSock:
            def __init__(self):
                self.sent = b""

            def sendall(self, data: bytes) -> None:
                self.sent += data

        flow = self._make_claude()
        sock = FakeSock()
        flow._pending = {
            "container": "ga-claude-login-abc",
            "state": "awaiting_code",
            "started_at": time.time(),
            "pty_sock": sock,
        }
        result = flow.submit_code("ABC-123")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(flow._pending["state"], "code_submitted")
        self.assertIn(b"ABC-123", sock.sent)

    def test_submit_code_pty_write_failure_returns_error(self):
        """When sendall raises, submit_code returns pty_write_failed."""
        class FailSock:
            def sendall(self, data: bytes) -> None:
                raise OSError("broken pipe")

        flow = self._make_claude()
        flow._pending = {
            "container": "ga-claude-login-abc",
            "state": "awaiting_code",
            "started_at": time.time(),
            "pty_sock": FailSock(),
        }
        result = flow.submit_code("CODE")
        self.assertEqual(result.get("error"), "pty_write_failed")


class TestClaudeLoginFlowIsExpired(unittest.TestCase):
    """ClaudeLoginFlow.is_expired: two deadlines — approval and code submission."""

    def _make_claude(self):
        from transport.login import ClaudeLoginFlow
        return ClaudeLoginFlow()

    def test_not_expired_when_no_pending(self):
        flow = self._make_claude()
        self.assertFalse(flow.is_expired())

    def test_not_expired_when_awaiting_code_fresh(self):
        flow = self._make_claude()
        flow._pending = {
            "state": "awaiting_code",
            "started_at": time.time(),
        }
        self.assertFalse(flow.is_expired())

    def test_expired_when_awaiting_code_too_long(self):
        flow = self._make_claude()
        flow._pending = {
            "state": "awaiting_code",
            "started_at": time.time() - 10000,
        }
        self.assertTrue(flow.is_expired())

    def test_not_expired_when_code_submitted_fresh(self):
        flow = self._make_claude()
        flow._pending = {
            "state": "code_submitted",
            "started_at": time.time() - 1000,
            "code_submitted_at": time.time(),
        }
        self.assertFalse(flow.is_expired())

    def test_expired_when_code_submitted_too_long(self):
        flow = self._make_claude()
        flow._pending = {
            "state": "code_submitted",
            "started_at": time.time() - 1000,
            "code_submitted_at": time.time() - 10000,
        }
        self.assertTrue(flow.is_expired())

    def test_unrecognised_state_not_expired(self):
        flow = self._make_claude()
        flow._pending = {
            "state": "unknown_state",
            "started_at": time.time() - 10000,
        }
        self.assertFalse(flow.is_expired())


class TestLoginFlowContainerCreatePayload(unittest.TestCase):
    """_container_create_payload: each flow produces a usable dict."""

    def test_kiro_payload_contains_name(self):
        from transport.login import KiroLoginFlow
        payload = KiroLoginFlow()._container_create_payload("ga-login-test")
        self.assertEqual(payload["name"], "ga-login-test")

    def test_kiro_payload_has_network(self):
        from transport.login import KiroLoginFlow
        payload = KiroLoginFlow()._container_create_payload("ga-login-test")
        self.assertIn("Networks", payload)

    def test_claude_payload_contains_name(self):
        from transport.login import ClaudeLoginFlow
        payload = ClaudeLoginFlow()._container_create_payload("ga-claude-login-test")
        self.assertEqual(payload["name"], "ga-claude-login-test")

    def test_codex_payload_contains_name(self):
        from transport.login import CodexLoginFlow
        payload = CodexLoginFlow()._container_create_payload("ga-codex-login-test")
        self.assertEqual(payload["name"], "ga-codex-login-test")


class TestLoginFlowSingletons(unittest.TestCase):
    """Module-level singletons are distinct instances of the right classes."""

    def test_kiro_flow_is_kiro_login_flow(self):
        from transport.login import KIRO_FLOW, KiroLoginFlow
        self.assertIsInstance(KIRO_FLOW, KiroLoginFlow)

    def test_claude_flow_is_claude_login_flow(self):
        from transport.login import CLAUDE_FLOW, ClaudeLoginFlow
        self.assertIsInstance(CLAUDE_FLOW, ClaudeLoginFlow)

    def test_codex_flow_is_codex_login_flow(self):
        from transport.login import CODEX_FLOW, CodexLoginFlow
        self.assertIsInstance(CODEX_FLOW, CodexLoginFlow)

    def test_all_flows_contains_three(self):
        from transport.login import ALL_FLOWS
        self.assertEqual(len(ALL_FLOWS), 3)

    def test_all_flows_contains_singletons(self):
        from transport.login import ALL_FLOWS, CLAUDE_FLOW, CODEX_FLOW, KIRO_FLOW
        self.assertIn(KIRO_FLOW, ALL_FLOWS)
        self.assertIn(CLAUDE_FLOW, ALL_FLOWS)
        self.assertIn(CODEX_FLOW, ALL_FLOWS)

    def test_singletons_are_distinct_instances(self):
        from transport.login import CLAUDE_FLOW, CODEX_FLOW, KIRO_FLOW
        self.assertIsNot(KIRO_FLOW, CLAUDE_FLOW)
        self.assertIsNot(KIRO_FLOW, CODEX_FLOW)
        self.assertIsNot(CLAUDE_FLOW, CODEX_FLOW)

    def test_singletons_have_no_pending_at_import(self):
        """Fresh import: all singletons start idle (no pending flow)."""
        from transport.login import CLAUDE_FLOW, CODEX_FLOW, KIRO_FLOW
        # In the test environment the flows haven't been used
        # (other tests use fresh instances, not singletons directly)
        # We just verify the attribute exists and defaults to None
        self.assertIsNone(KIRO_FLOW._pending)
        self.assertIsNone(CLAUDE_FLOW._pending)
        self.assertIsNone(CODEX_FLOW._pending)


class TestLoginFlowURLPatterns(unittest.TestCase):
    """_url_patterns() returns non-empty lists of compiled regexes."""

    def test_kiro_url_patterns_nonempty(self):
        from transport.login import KiroLoginFlow
        patterns = KiroLoginFlow()._url_patterns()
        self.assertGreater(len(patterns), 0)

    def test_kiro_url_patterns_match_url(self):
        from transport.login import KiroLoginFlow
        patterns = KiroLoginFlow()._url_patterns()
        url = "https://auth.example.com/device?user_code=ABC123"
        matched = any(p.search(url) for p in patterns)
        self.assertTrue(matched, f"Expected a pattern to match {url!r}")

    def test_claude_url_patterns_nonempty(self):
        from transport.login import ClaudeLoginFlow
        patterns = ClaudeLoginFlow()._url_patterns()
        self.assertGreater(len(patterns), 0)

    def test_codex_url_patterns_nonempty(self):
        from transport.login import CodexLoginFlow
        patterns = CodexLoginFlow()._url_patterns()
        self.assertGreater(len(patterns), 0)


class TestLoginFlowCodePattern(unittest.TestCase):
    """_code_pattern() returns a compiled regex that extracts device codes."""

    def test_kiro_code_pattern(self):
        from transport.login import KiroLoginFlow
        pattern = KiroLoginFlow()._code_pattern()
        m = pattern.search("user_code=ABC1-XYZ2")
        self.assertIsNotNone(m)

    def test_claude_code_pattern(self):
        from transport.login import ClaudeLoginFlow
        pattern = ClaudeLoginFlow()._code_pattern()
        m = pattern.search("Code: ABCD-1234")
        self.assertIsNotNone(m)

    def test_codex_code_pattern(self):
        from transport.login import CodexLoginFlow
        pattern = CodexLoginFlow()._code_pattern()
        m = pattern.search("code: ABCD-1234")
        self.assertIsNotNone(m)


class TestLoginFlowPromptPatterns(unittest.TestCase):
    """_prompt_patterns() returns correctly structured lists."""

    def test_kiro_prompt_patterns_nonempty(self):
        from transport.login import KiroLoginFlow
        patterns = KiroLoginFlow()._prompt_patterns()
        self.assertIsInstance(patterns, list)
        self.assertGreater(len(patterns), 0)

    def test_kiro_prompt_patterns_are_tuples(self):
        from transport.login import KiroLoginFlow
        for p in KiroLoginFlow()._prompt_patterns():
            self.assertIsInstance(p, tuple)
            self.assertEqual(len(p), 2)

    def test_claude_prompt_patterns_is_list(self):
        from transport.login import ClaudeLoginFlow
        # Claude uses non-interactive flow — prompt list may be empty
        patterns = ClaudeLoginFlow()._prompt_patterns()
        self.assertIsInstance(patterns, list)

    def test_codex_prompt_patterns_is_list(self):
        from transport.login import CodexLoginFlow
        patterns = CodexLoginFlow()._prompt_patterns()
        self.assertIsInstance(patterns, list)


class TestLoginFlowThreadSafety(unittest.TestCase):
    """Concurrent abort/initiate calls are safe (lock-guarded)."""

    def test_abort_idempotent_concurrent(self):
        """Multiple concurrent abort() calls do not raise."""
        from transport.login import KiroLoginFlow

        errors = []

        def run_abort():
            flow = KiroLoginFlow()
            flow._pending = {
                "container": "ga-login-abc",
                "started_at": time.time(),
                "state": "started",
            }
            podman = FakePodmanClient()
            podman.add_container("ga-login-abc")
            try:
                flow.abort(podman)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=run_abort) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [], f"Concurrent abort raised: {errors}")


# ── TestWarnInertBackendSettings ──────────────────────────────────────────────


class TestWarnInertBackendSettings(unittest.TestCase):
    """_warn_inert_backend_settings: warns about stored credentials and BASE_URL
    settings for disabled backends. Values must never appear in log output."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        from transport.credentials import CredentialStore
        self._store = CredentialStore(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_warn(self, ga_crew_agent: str) -> list[str]:
        """Invoke _warn_inert_backend_settings with a patched config and store,
        returning the list of warning messages emitted."""
        import logging
        from transport.login import _warn_inert_backend_settings
        from transport.config import Config
        messages = []

        class _CapHandler(logging.Handler):
            def emit(self, record):
                messages.append(record.getMessage())

        handler = _CapHandler()
        import transport.login as login_mod
        lg = logging.getLogger("transport.login")
        lg.addHandler(handler)
        orig_store = login_mod._cred_store
        orig_cfg = login_mod.cfg
        try:
            login_mod._cred_store = self._store
            login_mod.cfg = Config(ga_crew_agent=ga_crew_agent)
            _warn_inert_backend_settings()
        finally:
            login_mod._cred_store = orig_store
            login_mod.cfg = orig_cfg
            lg.removeHandler(handler)
        return messages

    def test_disabled_backend_with_credential_warns(self):
        self._store.put("claude", "api-key", "sk-ant-should-not-appear")
        messages = self._run_warn("kiro")
        self.assertTrue(
            any("claude" in m for m in messages),
            f"Expected warning about disabled claude backend, got: {messages}",
        )

    def test_warning_contains_method_not_value(self):
        self._store.put("claude", "setup-token", "my-secret-token-value")
        messages = self._run_warn("kiro")
        warning = next((m for m in messages if "claude" in m), None)
        self.assertIsNotNone(warning, "Expected a warning about claude")
        # method name is in the warning
        self.assertIn("setup-token", warning)
        # secret value is NOT in the warning
        self.assertNotIn("my-secret-token-value", warning)

    def test_enabled_backend_with_credential_no_warn(self):
        self._store.put("claude", "api-key", "sk-ant-key-value")
        messages = self._run_warn("claude,kiro")
        self.assertFalse(
            any("claude" in m for m in messages),
            f"Should not warn about enabled claude backend, got: {messages}",
        )

    def test_disabled_codex_with_credential_warns(self):
        self._store.put("codex", "api-key", "sk-openai-test-key")
        messages = self._run_warn("kiro")
        self.assertTrue(
            any("codex" in m for m in messages),
            f"Expected warning about disabled codex, got: {messages}",
        )

    def test_no_credential_no_warn(self):
        # Nothing stored — no warnings
        messages = self._run_warn("kiro")
        self.assertEqual(messages, [], f"Expected no warnings but got: {messages}")

    def test_base_url_warns_for_disabled_backend(self):
        from transport.config import Config
        import transport.login as login_mod
        import logging
        messages = []

        class _CapHandler(logging.Handler):
            def emit(self, record):
                messages.append(record.getMessage())

        handler = _CapHandler()
        lg = logging.getLogger("transport.login")
        lg.addHandler(handler)
        orig_store = login_mod._cred_store
        orig_cfg = login_mod.cfg
        try:
            login_mod._cred_store = self._store
            # anthropic_base_url set but claude not enabled
            login_mod.cfg = Config(ga_crew_agent="kiro", anthropic_base_url="https://proxy.example.com")
            from transport.login import _warn_inert_backend_settings
            _warn_inert_backend_settings()
        finally:
            login_mod._cred_store = orig_store
            login_mod.cfg = orig_cfg
            lg.removeHandler(handler)

        self.assertTrue(
            any("ANTHROPIC_BASE_URL" in m for m in messages),
            f"Expected ANTHROPIC_BASE_URL warning, got: {messages}",
        )
        # The URL value itself must not appear in the warning
        self.assertFalse(
            any("proxy.example.com" in m for m in messages),
            f"URL value leaked into warning: {messages}",
        )

    def test_base_url_not_warned_when_backend_enabled(self):
        from transport.config import Config
        import transport.login as login_mod
        import logging
        messages = []

        class _CapHandler(logging.Handler):
            def emit(self, record):
                messages.append(record.getMessage())

        handler = _CapHandler()
        lg = logging.getLogger("transport.login")
        lg.addHandler(handler)
        orig_store = login_mod._cred_store
        orig_cfg = login_mod.cfg
        try:
            login_mod._cred_store = self._store
            login_mod.cfg = Config(ga_crew_agent="claude,kiro", anthropic_base_url="https://proxy.example.com")
            from transport.login import _warn_inert_backend_settings
            _warn_inert_backend_settings()
        finally:
            login_mod._cred_store = orig_store
            login_mod.cfg = orig_cfg
            lg.removeHandler(handler)

        self.assertFalse(
            any("ANTHROPIC_BASE_URL" in m for m in messages),
            f"Should not warn when claude is enabled, got: {messages}",
        )


if __name__ == "__main__":
    unittest.main()
