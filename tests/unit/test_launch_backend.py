"""Unit tests for per-crew backend selection on launch (TRN-259).

Drives ``tools.launch`` with a fake Podman client, a temp credential store and
stubbed setup/login collaborators, under a transport whose default backend is
``claude`` (so every ``backend="kiro"`` case proves the argument wins).

Covers:
- backend omitted → transport default; explicit backend overrides it
- disabled / unknown backend → backend_not_enabled, nothing created
- kiro is always launchable even when not listed in GA_CREW_AGENT
- auth gating, login flow and env injection follow the crew's backend
- the resolved backend reaches finish_setup (which records acp_backend)
"""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from unittest.mock import patch

# transport.tools imports transport.files, which needs real starlette routing
# that the unit-test stubs (conftest) don't provide. launch never signs file
# URLs, so a stand-in exposing the two imported names is enough.
if "transport.files" not in sys.modules:
    try:
        import transport.files  # noqa: F401
    except ImportError:
        _files_stub = types.ModuleType("transport.files")
        _files_stub._sign_file_url = lambda *a, **k: ""
        _files_stub._sign_upload_url = lambda *a, **k: ""
        sys.modules["transport.files"] = _files_stub

from tests.fakes import FakePodmanClient
from transport.config import Config
from transport.credentials import CredentialStore

from tests.unit.test_lifecycle import _patch_registry_backing


def _crypto_modules() -> dict:
    """Stand-ins for the Ed25519 imports launch makes inline; conftest's
    cryptography stub is not a package, and the key bytes don't matter here."""

    class _Pub:
        def public_bytes(self, *a):
            return b"\x01" * 32

    class Ed25519PrivateKey:
        @classmethod
        def generate(cls):
            return cls()

        def private_bytes(self, *a):
            return b"\x02" * 32

        def public_key(self):
            return _Pub()

    ed = types.ModuleType("cryptography.hazmat.primitives.asymmetric.ed25519")
    ed.Ed25519PrivateKey = Ed25519PrivateKey
    ser = types.ModuleType("cryptography.hazmat.primitives.serialization")
    for name in ("Encoding", "PrivateFormat", "PublicFormat"):
        setattr(ser, name, types.SimpleNamespace(Raw="raw"))
    ser.NoEncryption = lambda: None
    return {
        "cryptography.hazmat.primitives.asymmetric.ed25519": ed,
        "cryptography.hazmat.primitives.serialization": ser,
    }


class _EnvRecordingPodman(FakePodmanClient):
    """FakePodmanClient that also keeps the env passed to container_create."""

    def __init__(self):
        super().__init__()
        self.created_envs: list[dict] = []

    def container_create(self, name, image, env, *args, **kwargs):
        self.created_envs.append(dict(env))
        return super().container_create(name, image, env, *args, **kwargs)


class _LaunchHarness(unittest.TestCase):
    ENABLED = "claude"  # GA_CREW_AGENT: kiro is implicitly enabled too

    def setUp(self):
        import transport.login as login_mod
        import transport.registry as reg_mod
        import transport.tools as tools

        self.tools = tools
        self.podman = _EnvRecordingPodman()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = CredentialStore(self._tmp.name)
        self.crews = _patch_registry_backing(self, reg_mod, {})
        self.finish_calls: list[dict] = []
        self.login_calls: list[str] = []

        def fake_finish(podman, crew_id, *args, **kwargs):
            self.finish_calls.append(kwargs)
            return {"crew_id": crew_id, "status": "running", "acp_backend": kwargs["backend"]}

        def fake_login(name):
            def _start(podman, *a, **kw):
                self.login_calls.append(name)
                return {"login_url": f"https://login/{name}", "code": "CODE"}
            return _start

        patchers = [
            patch.dict(sys.modules, _crypto_modules()),
            patch.object(tools, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(login_mod, "cfg", Config(ga_crew_agent=self.ENABLED)),
            patch.object(tools, "_get_podman", return_value=self.podman),
            patch.object(tools, "_cred_store", self.store),
            patch.object(tools, "_finish_crew_setup", side_effect=fake_finish),
            patch.object(tools, "_wait_gateway", return_value=True),
            patch.object(tools, "_write_crew_secret"),
            patch.object(tools, "_initiate_login", side_effect=fake_login("kiro")),
            patch.object(tools, "_initiate_claude_login", side_effect=fake_login("claude")),
            patch.object(tools, "_initiate_codex_login", side_effect=fake_login("codex")),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)

    def launch(self, **kwargs):
        return self.tools.launch("crew-a", dashboard=False, **kwargs)

    def created_env(self) -> dict:
        env, = self.podman.created_envs
        return env


class TestBackendSelection(_LaunchHarness):

    def setUp(self):
        super().setUp()
        self.store.put("kiro", "api-key", "kiro-key")
        self.store.put("claude", "setup-token", "claude-token")

    def test_omitted_uses_default(self):
        result = self.launch()
        self.assertNotIn("error", result)
        self.assertEqual(self.finish_calls[-1]["backend"], "claude")

    def test_explicit_overrides_default(self):
        result = self.launch(backend="kiro")
        self.assertNotIn("error", result)
        self.assertEqual(self.finish_calls[-1]["backend"], "kiro")
        self.assertEqual(result["acp_backend"], "kiro")

    def test_case_insensitive(self):
        self.launch(backend="KIRO")
        self.assertEqual(self.finish_calls[-1]["backend"], "kiro")

    def test_blank_uses_default(self):
        self.launch(backend="  ")
        self.assertEqual(self.finish_calls[-1]["backend"], "claude")

    def test_kiro_always_enabled(self):
        # GA_CREW_AGENT is "claude" only; kiro is still launchable.
        self.assertNotIn("error", self.launch(backend="kiro"))


class TestBackendRejected(_LaunchHarness):

    def _assert_rejected(self, backend):
        result = self.launch(backend=backend)
        self.assertEqual(result["error"], "backend_not_enabled")
        self.assertEqual(result["backend"], backend)
        self.assertEqual(result["enabled"], ["claude", "kiro"])
        self.assertFalse(self.podman.was_called("container_create"))
        self.assertFalse(self.podman.was_called("volume_create"))
        self.assertEqual(self.crews, {})
        self.assertEqual(self.login_calls, [])

    def test_disabled_backend(self):
        self._assert_rejected("codex")
        result = self.launch(backend="codex")
        self.assertIn("backends.default in ghostship.yaml", result["instructions"])

    def test_unknown_backend(self):
        self._assert_rejected("gemini")
        result = self.launch(backend="gemini")
        self.assertIn("not a known backend", result["instructions"])
        self.assertNotIn("backends.default", result["instructions"])


class TestAuthFollowsBackend(_LaunchHarness):

    def test_missing_kiro_credential_starts_kiro_flow(self):
        self.store.put("claude", "setup-token", "claude-token")
        result = self.launch(backend="kiro")
        self.assertEqual(result["error"], "not_authenticated")
        self.assertEqual(result["login_url"], "https://login/kiro")
        self.assertEqual(self.login_calls, ["kiro"])
        self.assertFalse(self.podman.was_called("container_create"))

    def test_only_crew_credential_delivered(self):
        self.store.put("kiro", "api-key", "kiro-key")
        self.store.put("claude", "setup-token", "claude-token")
        self.launch(backend="kiro")
        env = self.created_env()
        self.assertEqual(env["KIRO_API_KEY"], "kiro-key")
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", env)
        self.assertNotIn("ANTHROPIC_API_KEY", env)

    def test_default_claude_crew_gets_claude_credential_only(self):
        self.store.put("kiro", "api-key", "kiro-key")
        self.store.put("claude", "setup-token", "claude-token")
        self.launch()
        env = self.created_env()
        self.assertEqual(env["CLAUDE_CODE_OAUTH_TOKEN"], "claude-token")
        self.assertNotIn("KIRO_API_KEY", env)


class TestLaunchPollCommit(_LaunchHarness):
    """The launch-time kiro poll commits only while its login flow is still pending (TRN-258)."""

    def setUp(self):
        super().setUp()
        import time
        import transport.login as login_mod
        self.flow = login_mod.KIRO_FLOW
        self.flow._pending = {"container": "ga-login-poll", "state": "started", "started_at": time.time()}
        self.addCleanup(setattr, self.flow, "_pending", None)

    def test_logout_during_poll_stops_launch_without_storing(self):
        def poll_then_logout(podman, container):
            # Logout's abort lands between the poll and the commit.
            self.flow.abort(podman)
            return "kiro-auth-rows"

        with patch.object(self.tools, "_read_auth_from_crew", side_effect=poll_then_logout):
            result = self.launch(backend="kiro")
        self.assertEqual(result["error"], "not_authenticated")
        self.assertIn("cancelled by logout", result["instructions"])
        self.assertIsNone(self.store.get("kiro"))
        self.assertEqual(self.login_calls, [])
        self.assertFalse(self.podman.was_called("container_create"))
        self.assertIsNone(self.flow.state)

    def test_current_poll_stores_credential_and_launches(self):
        with patch.object(self.tools, "_read_auth_from_crew", return_value="kiro-auth-rows"):
            result = self.launch(backend="kiro")
        self.assertNotIn("error", result)
        self.assertEqual(self.store.get("kiro")["method"], "builder-id")
        self.assertIsNone(self.flow.state)


if __name__ == "__main__":
    unittest.main()


class TestCrewsReportsBackend(_LaunchHarness):
    """crews() surfaces each crew's recorded acp_backend side by side."""

    def test_mixed_backends_listed(self):
        self.crews.update({
            "kiro-crew": {"container": "gs-crew-kiro", "status": "stopped", "acp_backend": "kiro"},
            "claude-crew": {"container": "gs-crew-claude", "status": "stopped", "acp_backend": "claude"},
        })
        with patch.object(self.tools, "_get_host_memory_gb_cached", return_value=None):
            listed = {c["crew_id"]: c["acp_backend"] for c in self.tools.crews()["crews"]}
        self.assertEqual(listed, {"kiro-crew": "kiro", "claude-crew": "claude"})
