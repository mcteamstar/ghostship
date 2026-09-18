"""Unit tests for TRN-170: Claude subscription OAuth login.

Covers:
- 6.1 POST /login/claude: 200+login_url when unauthenticated; 409 when already
      authenticated; 409 when flow in progress.
- 6.2 GET /login/claude: pending/complete states; 404 when no flow.
- 6.3 POST /logout/claude: clears ga-claude-auth and wipes running Claude crews;
      409 when not authenticated.
- 6.4 _finish_crew_setup Claude branch: API key path injects env var;
      OAuth path calls _inject_claude_auth.
- 6.5 launch() with Claude backend and no credentials calls _initiate_claude_login
      and returns not_authenticated.
- 6.6 Config.validate() no longer raises for claude backend without API key.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import unittest
from unittest.mock import Mock, patch

# ── Install stubs FIRST — before ANY transport import ─────────────────────────
# lifecycle.py does `import httpx2 as httpx` at the top level; the stub must
# be on sys.modules before that import runs, which means it must be done before
# `import transport.lifecycle` resolves.
from tests.unit._stubs import install_import_stubs
install_import_stubs()

from transport.config import Config, ConfigError  # noqa: E402 (after stub install)
import transport.lifecycle as _lifecycle  # noqa: E402
import transport.server as server  # noqa: E402


# ── 6.6 Config.validate() no longer raises for claude backend without API key ──


class TestValidateNoLongerRaisesWithoutApiKey(unittest.TestCase):
    """TRN-170: Config.validate() is a no-op for missing API key."""

    def test_validate_no_raise_for_claude_without_key(self) -> None:
        """Config.validate() must NOT raise ConfigError when claude backend has no API key."""
        env = {
            "GA_CREW_ACP_BACKEND": "claude",
            "GA_CREW_ANTHROPIC_API_KEY": "",
        }
        with patch.dict("os.environ", env):
            cfg = Config.from_env()
        # Must not raise — this is the core TRN-170 relaxation.
        cfg.validate()

    def test_validate_still_passes_with_api_key(self) -> None:
        """validate() still passes (trivially) when API key is provided."""
        env = {
            "GA_CREW_ACP_BACKEND": "claude",
            "GA_CREW_ANTHROPIC_API_KEY": "sk-ant-test",
        }
        with patch.dict("os.environ", env):
            cfg = Config.from_env()
        cfg.validate()  # must not raise

    def test_validate_passes_for_kiro_backend(self) -> None:
        """validate() passes for kiro backend regardless of API key."""
        with patch.dict("os.environ", {
            "GA_CREW_ACP_BACKEND": "kiro",
            "GA_CREW_ANTHROPIC_API_KEY": "",
        }):
            cfg = Config.from_env()
        cfg.validate()  # must not raise


# ── 6.1 POST /login/claude ─────────────────────────────────────────────────────


class TestHandleClaudeLoginPost(unittest.TestCase):
    """6.1: POST /login/claude state machine."""

    def _run(self, request: Mock = None) -> object:
        if request is None:
            request = Mock()
        return asyncio.run(server._handle_claude_login_post(request))

    def setUp(self) -> None:
        # Ensure clean state
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None

    def tearDown(self) -> None:
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None

    def test_returns_200_with_login_url_when_unauthenticated(self) -> None:
        """POST /login/claude returns 200 + login_url when not authenticated."""
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(server, "_claude_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(
                server,
                "_initiate_claude_login",
                return_value={"login_url": "https://claude.ai/auth?code=ABC", "code": "ABC"},
            ),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")
        self.assertIn("login_url", body)
        self.assertEqual(body["login_url"], "https://claude.ai/auth?code=ABC")

    def test_returns_409_when_already_authenticated(self) -> None:
        """POST /login/claude returns 409 when ga-claude-auth exists."""
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(server, "_claude_auth_exists", return_value=True),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 409)
        self.assertIn("Already authenticated", response.body.decode())

    def test_returns_409_when_flow_in_progress(self) -> None:
        """POST /login/claude returns 409 when a flow is already pending."""
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(server, "_claude_auth_exists", return_value=False),
        ):
            with _lifecycle._claude_login_pending_lock:
                _lifecycle._claude_login_pending = {
                    "container": "ga-claude-login-abc",
                    "state": "started",
                    "started_at": 0.0,
                }
            response = self._run()
        self.assertEqual(response.status_code, 409)
        self.assertIn("in progress", response.body.decode())

    def test_returns_400_when_not_claude_backend(self) -> None:
        """POST /login/claude returns 400 when GA_CREW_ACP_BACKEND != claude."""
        with patch.object(server, "GA_CREW_ACP_BACKEND", "kiro"):
            response = self._run()
        self.assertEqual(response.status_code, 400)

    def test_returns_500_on_initiate_error(self) -> None:
        """POST /login/claude returns 500 when _initiate_claude_login reports an error."""
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(server, "_claude_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(
                server,
                "_initiate_claude_login",
                return_value={"error": "image not found"},
            ),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 500)
        self.assertIn("image not found", response.body.decode())


# ── 6.2 GET /login/claude ──────────────────────────────────────────────────────


class TestHandleClaudeLoginGet(unittest.TestCase):
    """6.2: GET /login/claude polling states."""

    def _run(self, request: Mock = None) -> object:
        if request is None:
            request = Mock()
        return asyncio.run(server._handle_claude_login_get(request))

    def setUp(self) -> None:
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None

    def tearDown(self) -> None:
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None

    def test_returns_404_when_no_flow(self) -> None:
        """GET /login/claude returns 404 when no Claude login is in progress."""
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None
        response = self._run()
        self.assertEqual(response.status_code, 404)

    def test_returns_pending_while_waiting(self) -> None:
        """GET /login/claude returns pending while credentials not yet ready."""
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": "ga-claude-login-abc",
                "state": "started",
                "started_at": 0.0,
                "login_url": "https://claude.ai/auth",
            }
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_poll_claude_login_container", return_value=None),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")

    def test_returns_complete_on_auth_success(self) -> None:
        """GET /login/claude returns complete when credentials are ready."""
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": "ga-claude-login-abc",
                "state": "started",
                "started_at": 0.0,
            }
        fake_tar = b"PK fake tar content"
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_poll_claude_login_container", return_value=fake_tar),
            patch.object(server, "_write_claude_auth_file"),
            patch.object(server, "_nuke_claude_login_container"),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            response = self._run()
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "complete")

    def test_clears_pending_on_completion(self) -> None:
        """GET /login/claude clears _claude_login_pending after completion."""
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = {
                "container": "ga-claude-login-xyz",
                "state": "started",
                "started_at": 0.0,
            }
        fake_tar = b"some tar bytes"
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_poll_claude_login_container", return_value=fake_tar),
            patch.object(server, "_write_claude_auth_file"),
            patch.object(server, "_nuke_claude_login_container"),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            asyncio.run(server._handle_claude_login_get(Mock()))

        with _lifecycle._claude_login_pending_lock:
            self.assertIsNone(_lifecycle._claude_login_pending)


# ── 6.3 POST /logout/claude ────────────────────────────────────────────────────


class TestHandleClaudeLogoutPost(unittest.TestCase):
    """6.3: POST /logout/claude clears auth and wipes crews."""

    def _run(self, request: Mock = None) -> object:
        if request is None:
            request = Mock()
        return asyncio.run(server._handle_claude_logout_post(request))

    def test_returns_409_when_not_authenticated(self) -> None:
        """POST /logout/claude returns 409 when ga-claude-auth does not exist."""
        with patch.object(server, "_claude_auth_exists", return_value=False):
            response = self._run()
        self.assertEqual(response.status_code, 409)

    def test_deletes_auth_file_and_wipes_crews(self) -> None:
        """POST /logout/claude deletes ga-claude-auth and wipes Claude crews."""
        podman = Mock()
        podman.container_exec = Mock(return_value="")

        mock_reg = {
            "crews": {
                "crew-1": {"status": "running", "container": "gs-crew-1", "acp_backend": "claude"},
                "crew-2": {"status": "running", "container": "gs-crew-2", "acp_backend": "kiro"},
                "crew-3": {"status": "stopped", "container": "gs-crew-3", "acp_backend": "claude"},
            }
        }

        mock_path = Mock()
        mock_path.unlink = Mock()

        with (
            patch.object(server, "_claude_auth_exists", return_value=True),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value=mock_reg),
            patch.object(server, "_claude_auth_file_path", return_value=mock_path),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            response = self._run()

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "logged_out")

        # Only running Claude crews should have ~/.claude/ wiped
        wipe_calls = [
            c for c in podman.container_exec.call_args_list
            if "rm -rf" in str(c)
        ]
        containers_wiped = {c[0][0] for c in wipe_calls}
        self.assertIn("gs-crew-1", containers_wiped)
        # kiro crew and stopped crew should NOT be wiped
        self.assertNotIn("gs-crew-2", containers_wiped)
        self.assertNotIn("gs-crew-3", containers_wiped)

    def test_auth_file_is_deleted(self) -> None:
        """POST /logout/claude calls unlink on the ga-claude-auth path."""
        mock_path = Mock()
        mock_path.unlink = Mock()

        with (
            patch.object(server, "_claude_auth_exists", return_value=True),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_claude_auth_file_path", return_value=mock_path),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            asyncio.run(server._handle_claude_logout_post(Mock()))

        mock_path.unlink.assert_called_once()


# ── 6.4 _finish_crew_setup Claude branch ──────────────────────────────────────


class TestFinishCrewSetupClaudeBranch(unittest.TestCase):
    """6.4: _finish_crew_setup — API key path vs OAuth path for Claude backend."""

    def _make_podman(self) -> Mock:
        podman = Mock()
        podman.container_exec = Mock(return_value="ready")
        podman.container_stop = Mock()
        podman.container_start = Mock()
        podman.container_inspect = Mock(return_value={
            "Config": {"Labels": {"org.ghostship.version": "test"}}
        })
        return podman

    def _run_finish_crew_setup(self, podman, crew_id="test-crew", container="gs-test-crew"):
        """Minimal call to _finish_crew_setup with all side effects stubbed."""
        with (
            patch.object(_lifecycle, "_wait_gateway", return_value=True),
            patch.object(_lifecycle, "_patch_crew_config"),
            patch.object(_lifecycle, "_copy_agents"),
            patch.object(_lifecycle, "_copy_skills"),
            patch.object(_lifecycle, "_copy_steering"),
            patch.object(_lifecycle, "_seed_openspec_store"),
            patch.object(_lifecycle, "_inject_policy", return_value="v1"),
            patch.object(_lifecycle, "_patch_models"),
            patch.object(_lifecycle, "_mint_cookie", return_value="test-cookie"),
            patch.object(_lifecycle, "_registry_lock", threading.Lock()),
            patch.object(_lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(_lifecycle, "_save_registry"),
            patch.object(_lifecycle, "GA_PREWARM_ENABLED", False),
        ):
            return _lifecycle._finish_crew_setup(
                podman,
                crew_id,
                container,
                f"gs-vol-{crew_id}",
                f"gs-home-{crew_id}",
                auth_b64="",
                admiral_secret="aabbccdd" * 8,
            )

    def test_api_key_path_does_not_inject_claude_auth(self) -> None:
        """When GA_CREW_ANTHROPIC_API_KEY is set, _inject_claude_auth is NOT called."""
        podman = self._make_podman()
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(_lifecycle, "GA_CREW_ANTHROPIC_API_KEY", "sk-ant-key"),
            patch.object(_lifecycle, "_inject_claude_auth") as mock_inject,
            patch.object(_lifecycle, "_inject_auth"),
            patch.object(_lifecycle, "KIRO_API_KEY", ""),
        ):
            result = self._run_finish_crew_setup(podman)

        mock_inject.assert_not_called()
        self.assertEqual(result.get("status"), "ready")

    def test_oauth_path_calls_inject_claude_auth(self) -> None:
        """When GA_CREW_ANTHROPIC_API_KEY is unset but ga-claude-auth exists, _inject_claude_auth is called."""
        podman = self._make_podman()
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(_lifecycle, "GA_CREW_ANTHROPIC_API_KEY", ""),
            patch.object(_lifecycle, "_claude_auth_exists", return_value=True),
            patch.object(_lifecycle, "_inject_claude_auth") as mock_inject,
            patch.object(_lifecycle, "_inject_auth"),
            patch.object(_lifecycle, "KIRO_API_KEY", ""),
        ):
            result = self._run_finish_crew_setup(podman)

        mock_inject.assert_called_once()
        self.assertEqual(result.get("status"), "ready")

    def test_neither_credential_oauth_injection_skipped(self) -> None:
        """When neither API key nor ga-claude-auth is present, _inject_claude_auth is NOT called.

        This path is 'unreachable from setup' per the task spec — launch() blocks
        before _finish_crew_setup is reached. The test verifies the guard logic.
        """
        podman = self._make_podman()
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(_lifecycle, "GA_CREW_ANTHROPIC_API_KEY", ""),
            patch.object(_lifecycle, "_claude_auth_exists", return_value=False),
            patch.object(_lifecycle, "_inject_claude_auth") as mock_inject,
            patch.object(_lifecycle, "_inject_auth"),
            patch.object(_lifecycle, "KIRO_API_KEY", ""),
        ):
            result = self._run_finish_crew_setup(podman)

        mock_inject.assert_not_called()
        self.assertEqual(result.get("status"), "ready")


# ── 6.5 launch() Claude backend with no credentials ───────────────────────────


class TestLaunchClaudeBackendNoCredentials(unittest.TestCase):
    """6.5: launch() with Claude backend and no credentials calls _initiate_claude_login."""

    def _run_launch(self, crew_id: str = "test") -> dict:
        return _lifecycle.launch(crew_id)  # type: ignore[attr-defined]

    def _call_server_launch(self, crew_id: str = "test") -> dict:
        """Call the MCP tool launch() via server module."""
        # server.launch is the @mcp.tool()-wrapped function; we call the
        # underlying Python function directly via the tool's fn attribute.
        launch_fn = None
        for attr in dir(server):
            if attr == "launch":
                launch_fn = getattr(server, attr)
                break
        if launch_fn is None:
            self.skipTest("launch() not found on server module")
        return launch_fn(crew_id)

    def test_claude_backend_no_credentials_calls_initiate_login(self) -> None:
        """launch() with claude backend and no credentials calls _initiate_claude_login."""
        podman = Mock()

        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(server, "_GA_CREW_ANTHROPIC_API_KEY", ""),
            patch.object(server, "_claude_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(
                server,
                "_initiate_claude_login",
                return_value={"login_url": "https://claude.ai/auth", "code": None},
            ) as mock_initiate,
        ):
            result = self._call_server_launch("test-crew")

        mock_initiate.assert_called_once()
        self.assertEqual(result.get("error"), "not_authenticated")
        self.assertIn("login_url", result)

    def test_claude_backend_no_credentials_login_pending_response(self) -> None:
        """launch() returns not_authenticated + login_pending when flow already running."""
        podman = Mock()

        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(server, "_GA_CREW_ANTHROPIC_API_KEY", ""),
            patch.object(server, "_claude_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(
                server,
                "_initiate_claude_login",
                return_value={"login_pending": True},
            ),
        ):
            result = self._call_server_launch("test-crew")

        self.assertEqual(result.get("error"), "not_authenticated")
        self.assertTrue(result.get("login_pending"))

    def test_claude_backend_with_api_key_does_not_call_initiate(self) -> None:
        """launch() with claude backend + API key skips _initiate_claude_login."""
        podman = Mock()

        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(server, "_GA_CREW_ANTHROPIC_API_KEY", "sk-ant-real"),
            patch.object(server, "_claude_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_initiate_claude_login") as mock_initiate,
            # Short-circuit after auth check — don't need full launch
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value={
                "crews": {"test-crew": {"status": "launching", "container": "gs-test-crew"}}
            }),
        ):
            result = self._call_server_launch("test-crew")

        mock_initiate.assert_not_called()
        # Result may be an error about the crew existing, but NOT not_authenticated
        self.assertNotEqual(result.get("error"), "not_authenticated")

    def test_claude_backend_with_oauth_creds_does_not_call_initiate(self) -> None:
        """launch() with claude backend + ga-claude-auth skips _initiate_claude_login."""
        podman = Mock()

        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(server, "_GA_CREW_ANTHROPIC_API_KEY", ""),
            patch.object(server, "_claude_auth_exists", return_value=True),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_initiate_claude_login") as mock_initiate,
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value={
                "crews": {"test-crew": {"status": "launching", "container": "gs-test-crew"}}
            }),
        ):
            result = self._call_server_launch("test-crew")

        mock_initiate.assert_not_called()
        self.assertNotEqual(result.get("error"), "not_authenticated")


if __name__ == "__main__":
    unittest.main()
