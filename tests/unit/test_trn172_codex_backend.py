"""Unit tests for TRN-172: Codex ACP backend support.

Covers:
- 7.1 GA_CREW_ACP_BACKEND=codex is accepted; an unknown value still errors at
      startup; codex with no credential does NOT error at startup.
- 7.2 _patch_crew_config writes acp_backend: "codex" when the Codex backend is
      selected.
- 7.3 kiro auth injection is skipped and OPENAI_API_KEY is injected when
      GA_CREW_ACP_BACKEND=codex with GA_CREW_OPENAI_API_KEY set.
- 7.4 With no API key, ga-codex-auth present → OAuth archive injected into
      ~/.codex/; neither present → launch() returns not_authenticated + login_url.
- 7.5 OPENAI_BASE_URL is injected only for codex crews when set, not for
      kiro/claude crews; launch WARNING names the effective endpoint.
- 7.6 crews() reports acp_backend: "codex" for a codex crew.
- 7.7 The codex login state machine — POST /login/codex 200/409 transitions,
      GET /login/codex pending→authenticated writing ga-codex-auth,
      POST /logout/codex clears it, POST /login/codex rejected when backend != codex.
"""

from __future__ import annotations

import asyncio
import base64
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


# ── 7.1 Config validation ──────────────────────────────────────────────────────


class TestCodexBackendConfigValidation(unittest.TestCase):
    """GA_CREW_ACP_BACKEND=codex accepted; unknown value errors; codex lazy."""

    def test_codex_backend_is_valid(self) -> None:
        with patch.dict("os.environ", {"GA_CREW_ACP_BACKEND": "codex"}):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_crew_acp_backend, "codex")

    def test_codex_backend_valid_with_api_key(self) -> None:
        env = {
            "GA_CREW_ACP_BACKEND": "codex",
            "GA_CREW_OPENAI_API_KEY": "sk-openai-test123",
        }
        with patch.dict("os.environ", env):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_crew_acp_backend, "codex")
        self.assertEqual(cfg.ga_crew_openai_api_key, "sk-openai-test123")

    def test_unknown_value_still_errors_at_startup(self) -> None:
        """An unrecognised backend value still raises ConfigError at from_env()."""
        with patch.dict("os.environ", {"GA_CREW_ACP_BACKEND": "gemini"}):
            with self.assertRaises(ConfigError) as ctx:
                Config.from_env()
        self.assertIn("GA_CREW_ACP_BACKEND", str(ctx.exception))
        self.assertIn("gemini", str(ctx.exception))

    def test_codex_without_credential_does_not_error_at_startup(self) -> None:
        """GA_CREW_ACP_BACKEND=codex + no credential must NOT raise at validate().

        Credential enforcement is lazy (launch-time), matching the TRN-170 model.
        """
        env = {
            "GA_CREW_ACP_BACKEND": "codex",
            "GA_CREW_OPENAI_API_KEY": "",
        }
        with patch.dict("os.environ", env):
            cfg = Config.from_env()
        cfg.validate()  # must not raise

    def test_openai_base_url_stripped(self) -> None:
        with patch.dict("os.environ", {"GA_CREW_OPENAI_BASE_URL": "  https://proxy.local/v1  "}):
            cfg = Config.from_env()
        self.assertEqual(cfg.ga_crew_openai_base_url, "https://proxy.local/v1")

    def test_ga_include_codex_agent_bool_default_off(self) -> None:
        clean = {k: v for k, v in __import__("os").environ.items()
                 if k not in ("GA_INCLUDE_CODEX_AGENT",)}
        with patch.dict("os.environ", clean, clear=True):
            cfg = Config.from_env()
        self.assertFalse(cfg.ga_include_codex_agent)

    def test_ga_include_codex_agent_true(self) -> None:
        with patch.dict("os.environ", {"GA_INCLUDE_CODEX_AGENT": "true"}):
            cfg = Config.from_env()
        self.assertTrue(cfg.ga_include_codex_agent)


# ── 7.2 _patch_crew_config writes acp_backend: "codex" ────────────────────────


class TestPatchCrewConfigCodexBackend(unittest.TestCase):

    def _run_patch(self, backend: str) -> dict:
        podman = Mock()
        captured: list[str] = []

        def capture_exec(container, cmd, **kwargs):
            if len(cmd) >= 4 and "patch_crew_config.py" in cmd[1]:
                captured.append(cmd[3])
            return "patched config.local.json"

        podman.container_exec.side_effect = capture_exec

        original = _lifecycle.GA_CREW_ACP_BACKEND
        try:
            _lifecycle.GA_CREW_ACP_BACKEND = backend
            _lifecycle._patch_crew_config(podman, "gs-test")
        finally:
            _lifecycle.GA_CREW_ACP_BACKEND = original

        self.assertEqual(len(captured), 1)
        return json.loads(base64.b64decode(captured[0]).decode())

    def test_acp_backend_codex_written_to_agent_config(self) -> None:
        overrides = self._run_patch("codex")
        self.assertEqual(overrides.get("agent", {}).get("acp_backend"), "codex")

    def test_acp_backend_not_written_for_kiro(self) -> None:
        overrides = self._run_patch("kiro")
        self.assertNotIn("acp_backend", overrides.get("agent", {}))


# ── 7.3 / 7.4 / 7.5 Auth injection branching for Codex backend ────────────────


class TestFinishCrewSetupCodexBranch(unittest.TestCase):
    """kiro auth injection skipped; OAuth path injects ~/.codex/; WARNING emitted."""

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
            patch.object(_lifecycle, "GA_PREWARM_ENABLED", False),
        ):
            return _lifecycle._finish_crew_setup(
                podman, crew_id, container,
                f"gs-vol-{crew_id}", f"gs-home-{crew_id}",
                auth_b64=None,
                admiral_secret="aabbccdd" * 8,
            )

    def test_codex_path_skips_inject_auth(self) -> None:
        """On codex backend, _inject_auth (kiro path) is never called."""
        podman = self._make_podman()
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(_lifecycle, "GA_CREW_OPENAI_API_KEY", "sk-openai-key"),
            patch.object(_lifecycle, "_inject_auth") as mock_inject_auth,
            patch.object(_lifecycle, "_inject_codex_auth"),
            patch.object(_lifecycle, "KIRO_API_KEY", ""),
        ):
            result = self._run_finish(podman)
        mock_inject_auth.assert_not_called()
        self.assertEqual(result.get("status"), "ready")

    def test_api_key_path_does_not_inject_codex_auth(self) -> None:
        """When GA_CREW_OPENAI_API_KEY is set, _inject_codex_auth is NOT called."""
        podman = self._make_podman()
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(_lifecycle, "GA_CREW_OPENAI_API_KEY", "sk-openai-key"),
            patch.object(_lifecycle, "_inject_codex_auth") as mock_inject,
            patch.object(_lifecycle, "_inject_auth"),
            patch.object(_lifecycle, "KIRO_API_KEY", ""),
        ):
            result = self._run_finish(podman)
        mock_inject.assert_not_called()
        self.assertEqual(result.get("status"), "ready")

    def test_oauth_path_calls_inject_codex_auth(self) -> None:
        """No API key but ga-codex-auth present → _inject_codex_auth called (7.4)."""
        podman = self._make_podman()
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(_lifecycle, "GA_CREW_OPENAI_API_KEY", ""),
            patch.object(_lifecycle, "_codex_auth_exists", return_value=True),
            patch.object(_lifecycle, "_inject_codex_auth") as mock_inject,
            patch.object(_lifecycle, "_inject_auth"),
            patch.object(_lifecycle, "KIRO_API_KEY", ""),
        ):
            result = self._run_finish(podman)
        mock_inject.assert_called_once()
        self.assertEqual(result.get("status"), "ready")

    def test_codex_path_emits_warning_default_endpoint(self) -> None:
        """WARNING names api.openai.com when no base URL override is set (7.5)."""
        podman = self._make_podman()
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(_lifecycle, "GA_CREW_OPENAI_API_KEY", "sk-openai-key"),
            patch.object(_lifecycle, "GA_CREW_OPENAI_BASE_URL", ""),
            patch.object(_lifecycle, "_inject_auth"),
            patch.object(_lifecycle, "KIRO_API_KEY", ""),
        ):
            with self.assertLogs("transport.lifecycle", level="WARNING") as log_ctx:
                self._run_finish(podman)
        self.assertTrue(
            any("api.openai.com" in msg for msg in log_ctx.output),
            f"Expected WARNING naming api.openai.com, got: {log_ctx.output}",
        )

    def test_codex_path_emits_warning_override_endpoint(self) -> None:
        """WARNING names the configured GA_CREW_OPENAI_BASE_URL when set (7.5)."""
        podman = self._make_podman()
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(_lifecycle, "GA_CREW_OPENAI_API_KEY", "sk-openai-key"),
            patch.object(_lifecycle, "GA_CREW_OPENAI_BASE_URL", "https://proxy.local/v1"),
            patch.object(_lifecycle, "_inject_auth"),
            patch.object(_lifecycle, "KIRO_API_KEY", ""),
        ):
            with self.assertLogs("transport.lifecycle", level="WARNING") as log_ctx:
                self._run_finish(podman)
        self.assertTrue(
            any("https://proxy.local/v1" in msg for msg in log_ctx.output),
            f"Expected WARNING naming the override endpoint, got: {log_ctx.output}",
        )


# ── 7.3 / 7.5 launch() env injection ──────────────────────────────────────────


class TestLaunchCodexEnvInjection(unittest.TestCase):
    """OPENAI_API_KEY/OPENAI_BASE_URL injected only for codex crews (7.3, 7.5).

    The launch() flow is exercised only up to the container-create call; we
    capture the container_env dict from the podman.container_create mock.
    """

    def _launch_capture_env(self, backend: str, api_key: str, base_url: str,
                             anthropic_key: str = "", anthropic_base: str = "") -> dict | None:
        """Run server.launch far enough to capture container_env, then abort."""
        podman = Mock()
        captured_env: dict[str, dict] = {}

        def fake_container_create(*args, **kwargs):
            # container_create is called with env in kwargs; capture and then
            # raise to short-circuit the rest of launch (we only need the env).
            captured_env["env"] = kwargs.get("env") or (args[2] if len(args) > 2 else {})
            raise RuntimeError("stop-after-env-capture")

        podman.network_create = Mock()
        podman.volume_create = Mock()
        podman.container_create = Mock(side_effect=fake_container_create)

        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", backend),
            patch.object(server, "_GA_CREW_OPENAI_API_KEY", api_key),
            patch.object(server, "_GA_CREW_OPENAI_BASE_URL", base_url),
            patch.object(server, "_GA_CREW_ANTHROPIC_API_KEY", anthropic_key),
            patch.object(server, "_GA_CREW_ANTHROPIC_BASE_URL", anthropic_base),
            patch.object(server, "KIRO_API_KEY", ""),
            patch.object(server, "_codex_auth_exists", return_value=True),
            patch.object(server, "_claude_auth_exists", return_value=True),
            patch.object(server, "_read_auth_file", return_value="x"),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
            patch.object(server, "_cleanup_crew"),
        ):
            server.launch("test-crew")
        return captured_env.get("env")

    def test_codex_injects_openai_api_key_and_base_url(self) -> None:
        env = self._launch_capture_env("codex", "sk-openai-key", "https://proxy.local/v1")
        self.assertIsNotNone(env)
        self.assertEqual(env.get("OPENAI_API_KEY"), "sk-openai-key")
        self.assertEqual(env.get("OPENAI_BASE_URL"), "https://proxy.local/v1")

    def test_codex_base_url_injected_without_api_key(self) -> None:
        """OPENAI_BASE_URL is injected on the OAuth path too (no API key) (7.5)."""
        env = self._launch_capture_env("codex", "", "https://proxy.local/v1")
        self.assertIsNotNone(env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertEqual(env.get("OPENAI_BASE_URL"), "https://proxy.local/v1")

    def test_kiro_backend_does_not_inject_openai(self) -> None:
        """kiro crews never get OPENAI_* env vars even if the values are set (7.5)."""
        env = self._launch_capture_env("kiro", "sk-openai-key", "https://proxy.local/v1")
        self.assertIsNotNone(env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("OPENAI_BASE_URL", env)

    def test_claude_backend_does_not_inject_openai(self) -> None:
        """claude crews never get OPENAI_* env vars (7.5)."""
        env = self._launch_capture_env(
            "claude", "sk-openai-key", "https://proxy.local/v1",
            anthropic_key="sk-ant-real",
        )
        self.assertIsNotNone(env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("OPENAI_BASE_URL", env)


# ── 7.4 launch() with Codex backend and no credentials ────────────────────────


class TestLaunchCodexBackendNoCredentials(unittest.TestCase):

    def _call_launch(self, crew_id: str = "test-crew") -> dict:
        return server.launch(crew_id)

    def test_no_credentials_calls_initiate_codex_login(self) -> None:
        podman = Mock()
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(server, "_GA_CREW_OPENAI_API_KEY", ""),
            patch.object(server, "_codex_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(
                server, "_initiate_codex_login",
                return_value={"login_url": "https://auth.openai.com/x", "code": None},
            ) as mock_initiate,
        ):
            result = self._call_launch()
        mock_initiate.assert_called_once()
        self.assertEqual(result.get("error"), "not_authenticated")
        self.assertIn("login_url", result)

    def test_login_pending_response(self) -> None:
        podman = Mock()
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(server, "_GA_CREW_OPENAI_API_KEY", ""),
            patch.object(server, "_codex_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_initiate_codex_login", return_value={"login_pending": True}),
        ):
            result = self._call_launch()
        self.assertEqual(result.get("error"), "not_authenticated")
        self.assertTrue(result.get("login_pending"))

    def test_with_api_key_does_not_call_initiate(self) -> None:
        podman = Mock()
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(server, "_GA_CREW_OPENAI_API_KEY", "sk-openai-real"),
            patch.object(server, "_codex_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_initiate_codex_login") as mock_initiate,
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value={
                "crews": {"test-crew": {"status": "launching", "container": "gs-test-crew"}}
            }),
        ):
            result = self._call_launch()
        mock_initiate.assert_not_called()
        self.assertNotEqual(result.get("error"), "not_authenticated")

    def test_with_oauth_creds_does_not_call_initiate(self) -> None:
        podman = Mock()
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(server, "_GA_CREW_OPENAI_API_KEY", ""),
            patch.object(server, "_codex_auth_exists", return_value=True),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_initiate_codex_login") as mock_initiate,
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value={
                "crews": {"test-crew": {"status": "launching", "container": "gs-test-crew"}}
            }),
        ):
            result = self._call_launch()
        mock_initiate.assert_not_called()
        self.assertNotEqual(result.get("error"), "not_authenticated")


# ── 7.6 crews() response includes acp_backend: "codex" ────────────────────────


class TestCrewsResponseCodexBackend(unittest.TestCase):

    def _crews_result(self, crew_entry: dict) -> list[dict]:
        reg = {"crews": {"test-crew": crew_entry}}
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_get_podman", return_value=None),
        ):
            result = server.crews()
        return result.get("crews", [])

    def test_acp_backend_codex_surfaced(self) -> None:
        entry = {
            "container": "gs-test",
            "status": "stopped",
            "acp_backend": "codex",
            "composition": "spec-ops",
        }
        crews = self._crews_result(entry)
        self.assertEqual(len(crews), 1)
        self.assertEqual(crews[0]["acp_backend"], "codex")

    def test_legacy_entry_defaults_to_kiro(self) -> None:
        entry = {"container": "gs-legacy", "status": "stopped"}
        crews = self._crews_result(entry)
        self.assertEqual(crews[0]["acp_backend"], "kiro")


# ── 7.7 Codex login state machine ─────────────────────────────────────────────


class TestHandleCodexLoginPost(unittest.TestCase):
    def _run(self, request: Mock = None) -> object:
        return asyncio.run(server._handle_codex_login_post(request or Mock()))

    def setUp(self) -> None:
        with _lifecycle._codex_login_pending_lock:
            _lifecycle._codex_login_pending = None

    def tearDown(self) -> None:
        with _lifecycle._codex_login_pending_lock:
            _lifecycle._codex_login_pending = None

    def test_returns_200_with_login_url_when_unauthenticated(self) -> None:
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(server, "_codex_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(
                server, "_initiate_codex_login",
                return_value={"login_url": "https://auth.openai.com/x", "code": None},
            ),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["login_url"], "https://auth.openai.com/x")

    def test_returns_409_when_already_authenticated(self) -> None:
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(server, "_codex_auth_exists", return_value=True),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 409)
        self.assertIn("Already authenticated", response.body.decode())

    def test_returns_409_when_flow_in_progress(self) -> None:
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(server, "_codex_auth_exists", return_value=False),
        ):
            with _lifecycle._codex_login_pending_lock:
                _lifecycle._codex_login_pending = {
                    "container": "ga-codex-login-abc",
                    "state": "started",
                    "started_at": 0.0,
                }
            response = self._run()
        self.assertEqual(response.status_code, 409)
        self.assertIn("in progress", response.body.decode())

    def test_returns_400_when_not_codex_backend(self) -> None:
        with patch.object(server, "GA_CREW_ACP_BACKEND", "kiro"):
            response = self._run()
        self.assertEqual(response.status_code, 400)

    def test_returns_500_on_initiate_error(self) -> None:
        with (
            patch.object(server, "GA_CREW_ACP_BACKEND", "codex"),
            patch.object(server, "_codex_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_initiate_codex_login", return_value={"error": "image not found"}),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 500)
        self.assertIn("image not found", response.body.decode())


class TestHandleCodexLoginGet(unittest.TestCase):
    def _run(self, request: Mock = None) -> object:
        return asyncio.run(server._handle_codex_login_get(request or Mock()))

    def setUp(self) -> None:
        with _lifecycle._codex_login_pending_lock:
            _lifecycle._codex_login_pending = None

    def tearDown(self) -> None:
        with _lifecycle._codex_login_pending_lock:
            _lifecycle._codex_login_pending = None

    def test_returns_404_when_no_flow(self) -> None:
        response = self._run()
        self.assertEqual(response.status_code, 404)

    def test_returns_pending_while_waiting(self) -> None:
        with _lifecycle._codex_login_pending_lock:
            _lifecycle._codex_login_pending = {
                "container": "ga-codex-login-abc",
                "state": "started",
                "started_at": 0.0,
                "login_url": "https://auth.openai.com/x",
            }
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_poll_codex_login_container", return_value=None),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["status"], "pending")

    def test_returns_complete_and_writes_auth_on_success(self) -> None:
        with _lifecycle._codex_login_pending_lock:
            _lifecycle._codex_login_pending = {
                "container": "ga-codex-login-abc",
                "state": "started",
                "started_at": 0.0,
            }
        fake_tar = b"PK fake codex tar"
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_poll_codex_login_container", return_value=fake_tar),
            patch.object(server, "_write_codex_auth_file") as mock_write,
            patch.object(server, "_nuke_codex_login_container"),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            response = self._run()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["status"], "complete")
        mock_write.assert_called_once_with(fake_tar)

    def test_clears_pending_on_completion(self) -> None:
        with _lifecycle._codex_login_pending_lock:
            _lifecycle._codex_login_pending = {
                "container": "ga-codex-login-xyz",
                "state": "started",
                "started_at": 0.0,
            }
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_poll_codex_login_container", return_value=b"tar"),
            patch.object(server, "_write_codex_auth_file"),
            patch.object(server, "_nuke_codex_login_container"),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            self._run()
        with _lifecycle._codex_login_pending_lock:
            self.assertIsNone(_lifecycle._codex_login_pending)


class TestHandleCodexLogoutPost(unittest.TestCase):
    def _run(self, request: Mock = None) -> object:
        return asyncio.run(server._handle_codex_logout_post(request or Mock()))

    def test_returns_200_when_not_authenticated(self) -> None:
        """Logout is idempotent — returns 200 even when ga-codex-auth is absent."""
        with patch.object(server, "_codex_auth_exists", return_value=False):
            response = self._run()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["status"], "logged_out")

    def test_deletes_auth_file_and_wipes_codex_crews(self) -> None:
        podman = Mock()
        podman.container_exec = Mock(return_value="")
        mock_reg = {
            "crews": {
                "crew-1": {"status": "running", "container": "gs-crew-1", "acp_backend": "codex"},
                "crew-2": {"status": "running", "container": "gs-crew-2", "acp_backend": "kiro"},
                "crew-3": {"status": "stopped", "container": "gs-crew-3", "acp_backend": "codex"},
            }
        }
        mock_path = Mock()
        mock_path.unlink = Mock()
        with (
            patch.object(server, "_codex_auth_exists", return_value=True),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value=mock_reg),
            patch.object(server, "_codex_auth_file_path", return_value=mock_path),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            response = self._run()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["status"], "logged_out")
        wipe_calls = [c for c in podman.container_exec.call_args_list if "rm -rf" in str(c)]
        containers_wiped = {c[0][0] for c in wipe_calls}
        self.assertIn("gs-crew-1", containers_wiped)
        self.assertNotIn("gs-crew-2", containers_wiped)  # kiro crew
        self.assertNotIn("gs-crew-3", containers_wiped)  # stopped crew
        mock_path.unlink.assert_called_once()


if __name__ == "__main__":
    unittest.main()
