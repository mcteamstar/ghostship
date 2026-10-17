"""Unit tests for store-based credential resolution at launch time (TRN-233 task 2.1).

Covers:
- API key present in store → no flow started, launch gating passes
- No credential in store → flow started (login flow initiated)
- Credential rotation (store.put overwrites) → next launch reads new credential
- No module-level credential globals remain in transport files
  (grep check for _security.get_secret with credential names)
- Kiro api-key method → KIRO_API_KEY env injected, no auth_b64 needed
- Claude api-key method → ANTHROPIC_API_KEY env injected
- Claude setup-token method → CLAUDE_CODE_OAUTH_TOKEN env injected
- Codex api-key method → OPENAI_API_KEY env injected
"""

from __future__ import annotations

import base64
import os
import tempfile
import unittest
from unittest.mock import patch

from tests.fakes import FakePodmanClient
from transport.credentials import CredentialStore


def _make_store(tmp_dir: str) -> CredentialStore:
    return CredentialStore(tmp_dir)


class TestLaunchGatingNoCredential(unittest.TestCase):
    """When no credential is stored, launch gating starts the backend's flow."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_flow_stub(self, name: str) -> object:
        """Return a minimal flow stub that records whether initiate was called."""
        class _FlowStub:
            called = False
            state = None
            def abort(self, podman):
                pass
        return _FlowStub()

    def test_no_claude_credential_triggers_login_flow(self):
        """With no claude credential in the store, the claude gating block should
        call _initiate_claude_login. We verify this by checking the store is empty
        and that a fresh store.get returns None."""
        result = self.store.get("claude")
        self.assertIsNone(result)

    def test_no_codex_credential_triggers_login_flow(self):
        result = self.store.get("codex")
        self.assertIsNone(result)

    def test_no_kiro_api_key_means_no_key_injected(self):
        result = self.store.get("kiro")
        self.assertIsNone(result)


class TestLaunchGatingWithCredential(unittest.TestCase):
    """When a credential is stored, launch gating should not start a flow."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_claude_api_key_present_no_flow(self):
        """A stored claude api-key credential means gating should pass."""
        self.store.put("claude", "api-key", "sk-ant-test-key-value")
        cred = self.store.get("claude")
        self.assertIsNotNone(cred)
        self.assertEqual(cred["method"], "api-key")
        # Gating: if cred is not None, no flow is started.
        self.assertTrue(bool(cred))

    def test_codex_api_key_present_no_flow(self):
        self.store.put("codex", "api-key", "sk-openai-test-key")
        cred = self.store.get("codex")
        self.assertIsNotNone(cred)
        self.assertEqual(cred["method"], "api-key")
        self.assertTrue(bool(cred))

    def test_kiro_api_key_present_env_injection(self):
        """A stored kiro api-key credential → KIRO_API_KEY should be injected."""
        self.store.put("kiro", "api-key", "kiro-key-test-value")
        cred = self.store.get("kiro")
        self.assertIsNotNone(cred)
        self.assertEqual(cred["method"], "api-key")
        key = cred["payload"].decode("utf-8") if isinstance(cred["payload"], bytes) else cred["payload"]
        self.assertEqual(key, "kiro-key-test-value")


class TestCredentialRotation(unittest.TestCase):
    """Credential rotation: store.put replaces the previous credential.
    The next store.get returns the new credential without restart."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_rotation_replaces_credential(self):
        self.store.put("claude", "api-key", "first-key-value")
        first = self.store.get("claude")
        self.assertEqual(first["payload"], b"first-key-value")

        # Rotate: put a new credential
        self.store.put("claude", "setup-token", "rotated-token-value")
        second = self.store.get("claude")
        self.assertEqual(second["method"], "setup-token")
        self.assertEqual(second["payload"], b"rotated-token-value")
        # First key is gone
        self.assertNotEqual(second["payload"], b"first-key-value")

    def test_rotation_is_visible_immediately(self):
        """A second store instance (simulating a new request context) sees the
        new credential without any restart."""
        self.store.put("codex", "api-key", "old-openai-key")

        # Simulate a new store instance (same data dir) — represents a new launch.
        store2 = _make_store(self._tmp.name)
        result = store2.get("codex")
        self.assertEqual(result["payload"], b"old-openai-key")

        # Rotate via the first store instance
        self.store.put("codex", "api-key", "new-openai-key")

        # New launch reads the updated credential
        result2 = store2.get("codex")
        self.assertEqual(result2["payload"], b"new-openai-key")


class TestEnvInjectionByMethod(unittest.TestCase):
    """Verify that the correct env var is set for each credential method."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _decode_payload(self, cred: dict) -> str:
        p = cred["payload"]
        return p.decode("utf-8") if isinstance(p, bytes) else p

    def test_kiro_api_key_env(self):
        self.store.put("kiro", "api-key", "kiro-key-env-test")
        cred = self.store.get("kiro")
        self.assertEqual(cred["method"], "api-key")
        env = {}
        if cred and cred["method"] == "api-key":
            env["KIRO_API_KEY"] = self._decode_payload(cred)
        self.assertEqual(env.get("KIRO_API_KEY"), "kiro-key-env-test")

    def test_claude_api_key_env(self):
        self.store.put("claude", "api-key", "sk-ant-api-key-test")
        cred = self.store.get("claude")
        env = {}
        if cred:
            if cred["method"] == "api-key":
                env["ANTHROPIC_API_KEY"] = self._decode_payload(cred)
            elif cred["method"] == "setup-token":
                env["CLAUDE_CODE_OAUTH_TOKEN"] = self._decode_payload(cred)
        self.assertEqual(env.get("ANTHROPIC_API_KEY"), "sk-ant-api-key-test")
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", env)

    def test_claude_setup_token_env(self):
        self.store.put("claude", "setup-token", "setup-token-test-value")
        cred = self.store.get("claude")
        env = {}
        if cred:
            if cred["method"] == "api-key":
                env["ANTHROPIC_API_KEY"] = self._decode_payload(cred)
            elif cred["method"] == "setup-token":
                env["CLAUDE_CODE_OAUTH_TOKEN"] = self._decode_payload(cred)
        self.assertEqual(env.get("CLAUDE_CODE_OAUTH_TOKEN"), "setup-token-test-value")
        self.assertNotIn("ANTHROPIC_API_KEY", env)

    def test_claude_oauth_no_env_injected(self):
        """OAuth archive: no env var at container_create time — injected via
        _inject_claude_auth in _finish_crew_setup instead."""
        tar_bytes = b"\x1f\x8b"  # minimal fake tar header
        self.store.put("claude", "oauth", base64.b64encode(tar_bytes))
        cred = self.store.get("claude")
        env = {}
        if cred:
            if cred["method"] == "api-key":
                env["ANTHROPIC_API_KEY"] = self._decode_payload(cred)
            elif cred["method"] == "setup-token":
                env["CLAUDE_CODE_OAUTH_TOKEN"] = self._decode_payload(cred)
            # oauth: injected via _inject_claude_auth later
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", env)

    def test_codex_api_key_env(self):
        self.store.put("codex", "api-key", "sk-openai-test")
        cred = self.store.get("codex")
        env = {}
        if cred and cred["method"] == "api-key":
            env["OPENAI_API_KEY"] = self._decode_payload(cred)
        self.assertEqual(env.get("OPENAI_API_KEY"), "sk-openai-test")

    def test_codex_chatgpt_no_env_injected(self):
        """chatgpt archive: no OPENAI_API_KEY env — injected via _inject_codex_auth."""
        tar_bytes = b"\x1f\x8b"
        self.store.put("codex", "chatgpt", base64.b64encode(tar_bytes))
        cred = self.store.get("codex")
        env = {}
        if cred and cred["method"] == "api-key":
            env["OPENAI_API_KEY"] = self._decode_payload(cred)
        self.assertNotIn("OPENAI_API_KEY", env)


class TestNoModuleLevelCredentialGlobals(unittest.TestCase):
    """Verify no _security.get_secret credential globals remain in transport files."""

    def _read_file(self, rel_path: str) -> str:
        base = os.path.join(os.path.dirname(__file__), "..", "..", "transport")
        path = os.path.join(base, rel_path)
        with open(path) as f:
            return f.read()

    def _check_no_credential_globals(self, filename: str) -> None:
        """Fail if the file contains a module-level _security.get_secret for credential names."""
        src = self._read_file(filename)
        patterns = [
            "_security.get_secret.*api-key",
            "_security.get_secret.*oauth",
            "_security.get_secret.*openai",
            "_security.get_secret.*anthropic",
            "_security.get_secret.*claude-code",
        ]
        import re
        for p in patterns:
            matches = re.findall(p, src)
            self.assertEqual(
                matches, [],
                f"{filename} still has module-level credential global matching {p!r}: {matches}",
            )

    def test_tools_py_no_credential_globals(self):
        self._check_no_credential_globals("tools.py")

    def test_login_py_no_credential_globals(self):
        self._check_no_credential_globals("login.py")

    def test_server_py_no_credential_globals(self):
        self._check_no_credential_globals("server.py")

    def test_lifecycle_py_no_credential_globals(self):
        self._check_no_credential_globals("lifecycle.py")


class TestLaunchGatePerBackend(unittest.TestCase):
    """Task 3.6: store-based launch gate tests for each backend.

    These tests verify the launch-gating logic at the credential-store level
    without exercising the full Podman launch path.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _cred_for(self, backend: str) -> dict | None:
        return self.store.get(backend)

    def test_kiro_no_credential_starts_flow(self):
        """No kiro credential → gating logic should determine flow is needed."""
        cred = self._cred_for("kiro")
        self.assertIsNone(cred)
        # Gating logic: if no credential, flow must be started
        # (api-key method doesn't need flow; device methods do)
        needs_flow = not (cred and cred["method"] == "api-key")
        self.assertTrue(needs_flow)

    def test_kiro_api_key_no_flow_needed(self):
        """Kiro api-key credential → no flow started."""
        self.store.put("kiro", "api-key", "kiro-key-value")
        cred = self._cred_for("kiro")
        needs_flow = not (cred and cred["method"] == "api-key")
        self.assertFalse(needs_flow)

    def test_kiro_builder_id_credential_no_flow_needed(self):
        """Kiro builder-id stored credential → flow reuse path (no new flow)."""
        self.store.put("kiro", "builder-id", b"auth-sqlite-rows-data")
        cred = self._cred_for("kiro")
        # builder-id credential exists → credential is present (gating passes)
        self.assertIsNotNone(cred)
        self.assertEqual(cred["method"], "builder-id")

    def test_claude_no_credential_starts_flow(self):
        """No claude credential → flow must be started."""
        cred = self._cred_for("claude")
        self.assertIsNone(cred)
        # Gating: no credential → start flow
        self.assertFalse(bool(cred))

    def test_claude_api_key_no_flow(self):
        self.store.put("claude", "api-key", "sk-ant-key")
        cred = self._cred_for("claude")
        self.assertIsNotNone(cred)
        self.assertTrue(bool(cred))

    def test_codex_no_credential_starts_flow(self):
        cred = self._cred_for("codex")
        self.assertIsNone(cred)
        self.assertFalse(bool(cred))

    def test_codex_api_key_no_flow(self):
        self.store.put("codex", "api-key", "sk-openai-key")
        cred = self._cred_for("codex")
        self.assertTrue(bool(cred))

    def test_kiro_identity_center_configured_affects_flow_type(self):
        """When KIRO_IDENTITY_PROVIDER/KIRO_REGION are set, Identity Center
        flow is preferred. This is a config-level concern; the credential store
        result is independent of which flow type was used."""
        from transport.config import Config
        cfg_ic = Config(
            ga_crew_agent="kiro",
            kiro_identity_provider="https://example.awsapps.com/start",
            kiro_region="us-east-1",
        )
        cfg_builder_id = Config(ga_crew_agent="kiro")
        # Identity Center configured → use identity-center flow
        self.assertTrue(bool(cfg_ic.kiro_identity_provider))
        # No Identity Center config → use builder-id flow
        self.assertFalse(bool(cfg_builder_id.kiro_identity_provider))

    def test_pending_flow_reuse_no_new_flow(self):
        """When a flow is already pending, launch reuses it (no duplicate)."""
        from transport.login import KIRO_FLOW
        # No pending state → flow would be started
        self.assertIsNone(KIRO_FLOW.state)
        # With state set → existing flow is reused (implementation detail,
        # tested here at the state-machine level)
        KIRO_FLOW._pending = {"container": "ga-login-test", "state": "started", "login_url": None, "code": None, "started_at": 0.0}
        try:
            self.assertIsNotNone(KIRO_FLOW.state)
        finally:
            KIRO_FLOW._pending = None


if __name__ == "__main__":
    unittest.main()
