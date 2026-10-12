"""Unit tests for TRN-168: OpenCode ACP backend support.

Covers the route and launch-time behaviour that tasks.md 6.1 and 6.2 require,
mirroring the Codex coverage in test_trn172_codex_backend.py but adapted for
OpenCode's differences: login-flow auth ONLY (no API-key env-var path).

- 6.1 /login/opencode and /logout/opencode routes:
      - POST /login/opencode 200 (pending) / 409 (already auth) / 409 (in
        progress) / 400 (opencode not enabled) / 500 (initiate error)
      - GET /login/opencode 404 (no flow) / pending / complete (writes
        ga-opencode-auth, nukes container, clears pending)
      - POST /logout/opencode deletes ga-opencode-auth and wipes opencode crews;
        idempotent when already logged out; available when backend disabled.
- 6.2 launch() with GA_CREW_AGENT=opencode and no ga-opencode-auth → launch
      fails with not_authenticated naming the login step (no API-key fallback).
- _finish_crew_setup opencode branch: kiro auth injection skipped; OAuth
  credential injected via _inject_opencode_auth.
"""

from __future__ import annotations

import asyncio
import json
import threading
import unittest
from unittest.mock import Mock, patch

# ── Install stubs FIRST — before ANY transport import ─────────────────────────
from tests.unit._stubs import install_import_stubs
install_import_stubs()

from transport.config import Config, ConfigError  # noqa: E402 (after stub install)
import transport.lifecycle as _lifecycle  # noqa: E402
import transport.server as server  # noqa: E402


# ── Config validation ─────────────────────────────────────────────────────────


class TestOpenCodeBackendConfigValidation(unittest.TestCase):
    """GA_CREW_AGENT=opencode accepted; unknown value errors; opencode lazy."""

    def test_opencode_backend_is_valid(self) -> None:
        with patch.dict("os.environ", {"GA_CREW_AGENT": "opencode"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_crew_acp_backend, "opencode")
        # kiro is always in the enabled set
        self.assertIn("kiro", cfg.ga_agent_backends)
        self.assertIn("opencode", cfg.ga_agent_backends)

    def test_opencode_without_credential_does_not_error_at_startup(self) -> None:
        """opencode + no credential must NOT raise at validate() (lazy, launch-time)."""
        with patch.dict("os.environ", {"GA_CREW_AGENT": "opencode"}):
            cfg = Config.from_env()
        cfg.validate()  # must not raise


# ── _finish_crew_setup opencode branch ────────────────────────────────────────


class TestFinishCrewSetupOpenCodeBranch(unittest.TestCase):
    """kiro auth injection skipped; OAuth credential injected via _inject_opencode_auth."""

    def _make_podman(self) -> Mock:
        podman = Mock()
        podman.container_exec = Mock(return_value="ready")
        podman.container_stop = Mock()
        podman.container_start = Mock()
        podman.container_inspect = Mock(return_value={
            "Config": {"Labels": {"org.ghostship.version": "test"}},
            "State": {"StartedAt": "2026-01-01T00:00:00Z"},
        })
        return podman

    def _run_finish(self, podman, crew_id="test-crew", container="gs-test-crew"):
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
        ):
            return _lifecycle._finish_crew_setup(
                podman, crew_id, container,
                f"gs-vol-{crew_id}", f"gs-home-{crew_id}",
                auth_b64=None,
                admiral_secret="aabbccdd" * 8,
            )

    def test_opencode_path_skips_inject_auth(self) -> None:
        """On opencode backend, _inject_auth (kiro path) is never called."""
        podman = self._make_podman()
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "opencode"),
            patch.object(_lifecycle, "_opencode_auth_exists", return_value=True),
            patch.object(_lifecycle, "_inject_opencode_auth"),
            patch.object(_lifecycle, "_inject_auth") as mock_inject_auth,
            patch.object(_lifecycle, "KIRO_API_KEY", ""),
        ):
            result = self._run_finish(podman)
        mock_inject_auth.assert_not_called()
        self.assertEqual(result.get("status"), "ready")

    def test_oauth_path_calls_inject_opencode_auth(self) -> None:
        """ga-opencode-auth present → _inject_opencode_auth is called."""
        podman = self._make_podman()
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "opencode"),
            patch.object(_lifecycle, "_opencode_auth_exists", return_value=True),
            patch.object(_lifecycle, "_inject_opencode_auth") as mock_inject,
            patch.object(_lifecycle, "_inject_auth"),
            patch.object(_lifecycle, "KIRO_API_KEY", ""),
        ):
            result = self._run_finish(podman)
        mock_inject.assert_called_once()
        self.assertEqual(result.get("status"), "ready")


# ── 6.2 launch() with OpenCode backend and no credentials ─────────────────────


class TestLaunchOpenCodeBackendNoCredentials(unittest.TestCase):

    def setUp(self) -> None:
        # opencode is opt-in via GA_CREW_AGENT: enable it for these tests.
        patcher = patch.object(server.cfg, "ga_crew_agent", "kiro,opencode")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _call_launch(self, crew_id: str = "test-crew") -> dict:
        return server.launch(crew_id)

    def test_no_credential_calls_initiate_opencode_login(self) -> None:
        """GA_CREW_AGENT=opencode + no ga-opencode-auth → not_authenticated, no crew start."""
        podman = Mock()
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "opencode"),
            patch.object(server, "_opencode_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(
                server, "_initiate_opencode_login",
                return_value={"login_url": "https://auth.opencode.ai/x", "code": None},
            ) as mock_initiate,
        ):
            result = self._call_launch()
        mock_initiate.assert_called_once()
        self.assertEqual(result.get("error"), "not_authenticated")
        self.assertIn("login_url", result)
        # No API-key fallback for opencode — the crew must not have started.
        podman.container_create.assert_not_called()

    def test_login_pending_response(self) -> None:
        podman = Mock()
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "opencode"),
            patch.object(server, "_opencode_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_initiate_opencode_login", return_value={"login_pending": True}),
        ):
            result = self._call_launch()
        self.assertEqual(result.get("error"), "not_authenticated")
        self.assertTrue(result.get("login_pending"))

    def test_with_oauth_creds_does_not_call_initiate(self) -> None:
        podman = Mock()
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "opencode"),
            patch.object(server, "_opencode_auth_exists", return_value=True),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_initiate_opencode_login") as mock_initiate,
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value={
                "crews": {"test-crew": {"status": "launching", "container": "gs-test-crew"}}
            }),
        ):
            result = self._call_launch()
        mock_initiate.assert_not_called()
        self.assertNotEqual(result.get("error"), "not_authenticated")


# ── 6.1 OpenCode login state machine ──────────────────────────────────────────


class TestHandleOpenCodeLoginPost(unittest.TestCase):
    def _run(self, request: Mock = None) -> object:
        return asyncio.run(server._handle_opencode_login_post(request or Mock()))

    def setUp(self) -> None:
        with _lifecycle._opencode_login_pending_lock:
            _lifecycle._opencode_login_pending = None
        patcher = patch.object(server.cfg, "ga_crew_agent", "kiro,opencode")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        with _lifecycle._opencode_login_pending_lock:
            _lifecycle._opencode_login_pending = None

    def test_returns_200_with_login_url_when_unauthenticated(self) -> None:
        with (
            patch.object(server, "_opencode_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(
                server, "_initiate_opencode_login",
                return_value={"login_url": "https://auth.opencode.ai/x", "code": None},
            ),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["login_url"], "https://auth.opencode.ai/x")

    def test_returns_409_when_already_authenticated(self) -> None:
        with patch.object(server, "_opencode_auth_exists", return_value=True):
            response = self._run()
        self.assertEqual(response.status_code, 409)
        self.assertIn("Already authenticated", response.body.decode())

    def test_returns_409_when_flow_in_progress(self) -> None:
        with patch.object(server, "_opencode_auth_exists", return_value=False):
            with _lifecycle._opencode_login_pending_lock:
                _lifecycle._opencode_login_pending = {
                    "container": "ga-opencode-login-abc",
                    "state": "started",
                    "started_at": 0.0,
                }
            response = self._run()
        self.assertEqual(response.status_code, 409)
        self.assertIn("in progress", response.body.decode())

    def test_returns_400_when_opencode_not_enabled(self) -> None:
        """Refused with HTTP 400 naming GA_CREW_AGENT when opencode is not enabled."""
        with patch.object(server.cfg, "ga_crew_agent", "kiro"):
            response = self._run()
        self.assertEqual(response.status_code, 400)
        self.assertIn("GA_CREW_AGENT", response.body.decode())

    def test_disabled_check_runs_before_body_or_auth(self) -> None:
        """The disabled-backend check short-circuits before _opencode_auth_exists."""
        with (
            patch.object(server.cfg, "ga_crew_agent", "kiro"),
            patch.object(server, "_opencode_auth_exists") as mock_exists,
        ):
            response = self._run()
        self.assertEqual(response.status_code, 400)
        mock_exists.assert_not_called()

    def test_returns_500_on_initiate_error(self) -> None:
        with (
            patch.object(server, "_opencode_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_initiate_opencode_login", return_value={"error": "image not found"}),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 500)
        self.assertIn("image not found", response.body.decode())


class TestHandleOpenCodeLoginGet(unittest.TestCase):
    def _run(self, request: Mock = None) -> object:
        return asyncio.run(server._handle_opencode_login_get(request or Mock()))

    def setUp(self) -> None:
        with _lifecycle._opencode_login_pending_lock:
            _lifecycle._opencode_login_pending = None

    def tearDown(self) -> None:
        with _lifecycle._opencode_login_pending_lock:
            _lifecycle._opencode_login_pending = None

    def test_returns_404_when_no_flow(self) -> None:
        response = self._run()
        self.assertEqual(response.status_code, 404)

    def test_returns_pending_while_waiting(self) -> None:
        with _lifecycle._opencode_login_pending_lock:
            _lifecycle._opencode_login_pending = {
                "container": "ga-opencode-login-abc",
                "state": "started",
                "started_at": 0.0,
                "login_url": "https://auth.opencode.ai/x",
            }
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_poll_opencode_login_container", return_value=None),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["status"], "pending")

    def test_returns_complete_and_writes_auth_on_success(self) -> None:
        with _lifecycle._opencode_login_pending_lock:
            _lifecycle._opencode_login_pending = {
                "container": "ga-opencode-login-abc",
                "state": "started",
                "started_at": 0.0,
            }
        fake_tar = b"fake opencode tar"
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_poll_opencode_login_container", return_value=fake_tar),
            patch.object(server, "_write_opencode_auth_file") as mock_write,
            patch.object(server, "_nuke_opencode_login_container"),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            response = self._run()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["status"], "complete")
        mock_write.assert_called_once_with(fake_tar)

    def test_clears_pending_on_completion(self) -> None:
        with _lifecycle._opencode_login_pending_lock:
            _lifecycle._opencode_login_pending = {
                "container": "ga-opencode-login-xyz",
                "state": "started",
                "started_at": 0.0,
            }
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_poll_opencode_login_container", return_value=b"tar"),
            patch.object(server, "_write_opencode_auth_file"),
            patch.object(server, "_nuke_opencode_login_container"),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            self._run()
        with _lifecycle._opencode_login_pending_lock:
            self.assertIsNone(_lifecycle._opencode_login_pending)


class TestHandleOpenCodeLogoutPost(unittest.TestCase):
    def _run(self, request: Mock = None) -> object:
        return asyncio.run(server._handle_opencode_logout_post(request or Mock()))

    def test_returns_logged_out_when_not_authenticated(self) -> None:
        """Logout is idempotent — returns logged_out even when ga-opencode-auth is absent."""
        with patch.object(server, "_opencode_auth_exists", return_value=False):
            response = self._run()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["status"], "logged_out")

    def test_logout_available_when_backend_disabled(self) -> None:
        """logout works regardless of whether opencode is enabled (no 400 gate)."""
        with (
            patch.object(server.cfg, "ga_crew_agent", "kiro"),
            patch.object(server, "_opencode_auth_exists", return_value=False),
        ):
            response = self._run()
        self.assertNotEqual(response.status_code, 400)
        self.assertEqual(response.status_code, 200)

    def test_deletes_auth_file_and_wipes_opencode_crews(self) -> None:
        podman = Mock()
        podman.container_exec = Mock(return_value="")
        mock_reg = {
            "crews": {
                "crew-1": {"status": "running", "container": "gs-crew-1", "acp_backend": "opencode"},
                "crew-2": {"status": "running", "container": "gs-crew-2", "acp_backend": "kiro"},
                "crew-3": {"status": "stopped", "container": "gs-crew-3", "acp_backend": "opencode"},
            }
        }
        mock_path = Mock()
        mock_path.unlink = Mock()
        with (
            patch.object(server, "_opencode_auth_exists", return_value=True),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value=mock_reg),
            patch.object(server, "_opencode_auth_file_path", return_value=mock_path),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            response = self._run()
        self.assertEqual(response.status_code, 200)
        wipe_calls = [c for c in podman.container_exec.call_args_list if "rm -rf" in str(c)]
        containers_wiped = {c[0][0] for c in wipe_calls}
        self.assertIn("gs-crew-1", containers_wiped)
        self.assertNotIn("gs-crew-2", containers_wiped)  # kiro crew
        self.assertNotIn("gs-crew-3", containers_wiped)  # stopped crew
        mock_path.unlink.assert_called_once()


if __name__ == "__main__":
    unittest.main()
