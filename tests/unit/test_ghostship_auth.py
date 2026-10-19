"""Unit tests for the ghostship CLI auth subcommand (TRN-233 tasks 4.1-4.4).

Covers:
- Task 4.1: URL and key discovery (flag → GHOSTSHIP_URL env → Podman → default)
- Task 4.1: Key from GHOSTSHIP_API_KEY env
- Task 4.1: Refusing secret over plain HTTP to remote host without --insecure
- Task 4.1: Local plain HTTP allowed
- Task 4.2: Dispatch with usage, backend required for login and logout
- Task 4.2: Unknown verb / backend errors
- Task 4.3: Method menu, --method, empty secret 400, no-tty-without-method
- Task 4.4: auth logout <backend>, auth status
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from unittest.mock import patch

# Add the repo root to sys.path so we can import from ghostship
import importlib
import importlib.util
import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_ghostship():
    """Import the ghostship CLI module dynamically."""
    import importlib.machinery
    gs_path = _REPO_ROOT / "ghostship"
    loader = importlib.machinery.SourceFileLoader("ghostship_cli", str(gs_path))
    spec = importlib.util.spec_from_loader("ghostship_cli", loader, origin=str(gs_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gs = _load_ghostship()


# ── portal-only-host: installed URL comes from ga-transport's GA_HOST_URL ─────

class TestInspectInstalledUrl(unittest.TestCase):
    """ga-transport publishes no port; the installed URL is its GA_HOST_URL."""

    def _inspect(self, env, returncode=0):
        import subprocess as _sp

        completed = _sp.CompletedProcess(
            args=[], returncode=returncode, stdout=json.dumps(env), stderr=""
        )
        with patch.object(gs, "_find_podman", return_value=["podman"]):
            with patch.object(gs.subprocess, "run", return_value=completed) as run:
                url = gs._inspect_installed_url()
        return url, run

    def test_loopback_install(self):
        url, run = self._inspect(["PORT=64057", "GA_HOST_URL=http://localhost:64057"])
        self.assertEqual(url, "http://localhost:64057")
        self.assertIn("ga-transport", run.call_args.args[0])
        self.assertIn("{{json .Config.Env}}", run.call_args.args[0])

    def test_specific_host_install(self):
        url, _ = self._inspect(["GA_HOST_URL=http://192.168.1.10:64057/"])
        self.assertEqual(url, "http://192.168.1.10:64057")

    def test_custom_port_install_is_discovered(self):
        url, _ = self._inspect(["GA_HOST_URL=http://localhost:9000"])
        self.assertEqual(url, "http://localhost:9000")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GHOSTSHIP_URL", None)
            with patch.object(gs, "_inspect_installed_url", return_value=url):
                resolved, _ = gs._discover_transport([])
        self.assertEqual(resolved, "http://localhost:9000")

    def test_missing_ga_host_url_falls_back(self):
        url, _ = self._inspect(["PORT=64057"])
        self.assertEqual(url, "")

    def test_inspect_failure_falls_back(self):
        url, _ = self._inspect([], returncode=125)
        self.assertEqual(url, "")


# ── Task 4.1: URL and key discovery ──────────────────────────────────────────

class TestDiscoverTransport(unittest.TestCase):
    """_discover_transport: flag → env → Podman → default."""

    def test_flag_takes_precedence_over_env(self):
        with patch.dict(os.environ, {"GHOSTSHIP_URL": "http://env.example.com"}):
            with patch.object(gs, "_inspect_installed_url", return_value=""):
                url, _ = gs._discover_transport(["--url", "http://flag.example.com"])
        self.assertEqual(url, "http://flag.example.com")

    def test_env_used_when_no_flag(self):
        with patch.dict(os.environ, {"GHOSTSHIP_URL": "http://env.example.com"}):
            with patch.object(gs, "_inspect_installed_url", return_value=""):
                url, _ = gs._discover_transport([])
        self.assertEqual(url, "http://env.example.com")

    def test_podman_inspect_used_when_no_flag_no_env(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("GHOSTSHIP_URL", "GHOSTSHIP_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(gs, "_inspect_installed_url",
                              return_value="http://podman.local:9000"):
                with patch.object(gs, "_inspect_installed_api_key", return_value=""):
                    url, _ = gs._discover_transport([])
        self.assertEqual(url, "http://podman.local:9000")

    def test_default_used_when_nothing_else(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("GHOSTSHIP_URL", "GHOSTSHIP_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(gs, "_inspect_installed_url", return_value=""):
                with patch.object(gs, "_inspect_installed_api_key", return_value=""):
                    url, _ = gs._discover_transport([])
        self.assertEqual(url, "http://localhost:64057")

    def test_api_key_from_flag(self):
        with patch.object(gs, "_inspect_installed_url", return_value=""):
            with patch.object(gs, "_inspect_installed_api_key", return_value=""):
                _, key = gs._discover_transport(["--api-key", "myflagkey"])
        self.assertEqual(key, "myflagkey")

    def test_api_key_from_env(self):
        with patch.dict(os.environ, {"GHOSTSHIP_API_KEY": "envkey123"}):
            with patch.object(gs, "_inspect_installed_url", return_value=""):
                with patch.object(gs, "_inspect_installed_api_key", return_value=""):
                    _, key = gs._discover_transport([])
        self.assertEqual(key, "envkey123")

    def test_api_key_from_podman_data(self):
        env = {k: v for k, v in os.environ.items() if k != "GHOSTSHIP_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(gs, "_inspect_installed_url", return_value=""):
                with patch.object(gs, "_inspect_installed_api_key",
                                  return_value="podmankey456"):
                    _, key = gs._discover_transport([])
        self.assertEqual(key, "podmankey456")

    def test_trailing_slash_stripped(self):
        with patch.dict(os.environ, {"GHOSTSHIP_URL": "http://example.com/"}):
            with patch.object(gs, "_inspect_installed_url", return_value=""):
                url, _ = gs._discover_transport([])
        self.assertEqual(url, "http://example.com")


class TestIsSafeUrl(unittest.TestCase):
    """_is_safe_url: HTTPS or loopback allowed; plain HTTP to remote rejected."""

    def test_https_allowed(self):
        self.assertTrue(gs._is_safe_url("https://remote.example.com"))

    def test_localhost_allowed(self):
        self.assertTrue(gs._is_safe_url("http://localhost:64057"))

    def test_127_0_0_1_allowed(self):
        self.assertTrue(gs._is_safe_url("http://127.0.0.1:64057"))

    def test_remote_http_rejected(self):
        self.assertFalse(gs._is_safe_url("http://10.0.0.5:64057"))

    def test_remote_http_no_port_rejected(self):
        self.assertFalse(gs._is_safe_url("http://remote.example.com"))

    def test_127_x_x_x_allowed(self):
        self.assertTrue(gs._is_safe_url("http://127.0.0.100:12345"))


# ── Task 4.2: Dispatch ────────────────────────────────────────────────────────

class TestAuthDispatch(unittest.TestCase):
    """cmd_auth: dispatch with usage, unknown verb or backend errors."""

    def test_no_args_prints_usage_exits_0(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            result = gs.cmd_auth([])
        self.assertEqual(result, 0)
        self.assertIn("ghostship auth", buf.getvalue())

    def test_help_flag_exits_0(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            result = gs.cmd_auth(["--help"])
        self.assertEqual(result, 0)

    def test_unknown_verb_exits_nonzero(self):
        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            result = gs.cmd_auth(["frobnicate"])
        self.assertNotEqual(result, 0)
        self.assertIn("unknown auth subcommand", err_buf.getvalue())

    def test_login_without_backend_exits_nonzero(self):
        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            result = gs.cmd_auth(["login"])
        self.assertNotEqual(result, 0)
        self.assertIn("backend", err_buf.getvalue().lower())

    def test_login_unknown_backend_exits_nonzero_no_network(self):
        """ghostship auth login anthropic exits non-zero without contacting the transport."""
        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            # anthropic is not a valid backend
            result = gs.auth_login(["anthropic"])
        self.assertNotEqual(result, 0)
        self.assertIn("anthropic", err_buf.getvalue())

    def test_logout_without_backend_exits_nonzero(self):
        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            result = gs.cmd_auth(["logout"])
        self.assertNotEqual(result, 0)

    def test_unknown_backend_for_logout(self):
        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            result = gs.auth_logout(["anthropic"])
        self.assertNotEqual(result, 0)


# ── Task 4.1: Refuse secret over plain HTTP to remote host ────────────────────

class TestSecretHttpsGuard(unittest.TestCase):
    """Secrets must not be sent over plain HTTP to remote hosts."""

    def _mock_discover(self):
        """Return a tuple patcher that sets url to http://10.0.0.5:64057."""
        return patch.object(
            gs, "_discover_transport",
            return_value=("http://10.0.0.5:64057", None),
        )

    def test_api_key_method_refused_on_remote_http(self):
        """auth login claude --method api-key --url http://10.0.0.5 exits non-zero."""
        err_buf = io.StringIO()
        with self._mock_discover():
            with patch("sys.stderr", err_buf):
                result = gs.auth_login(["claude", "--method", "api-key"])
        self.assertNotEqual(result, 0)
        self.assertIn("plain HTTP", err_buf.getvalue())

    def test_local_http_allowed(self):
        """auth login kiro --method api-key over localhost is allowed."""
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        # Mock discover to return localhost URL
        with patch.object(gs, "_discover_transport",
                          return_value=("http://localhost:64057", None)):
            # Mock _read_secret to return a test key
            with patch.object(gs, "_read_secret", return_value="test-api-key"):
                # Mock _http_json to succeed
                with patch.object(gs, "_http_json",
                                  return_value={"status": "stored", "method": "api-key",
                                                "stored_at": "2026-01-01T00:00:00Z"}):
                    # Mock the status check for existing credential
                    with patch.object(gs, "_http_json",
                                      side_effect=[
                                          {"identity_center": {}},  # GET /login/kiro IDC defaults
                                          {"configured": False},  # status check
                                          {"status": "stored", "method": "api-key",
                                           "stored_at": "2026-01-01T00:00:00Z"},  # POST
                                      ]):
                        with patch("sys.stdout", out_buf):
                            with patch("sys.stderr", err_buf):
                                result = gs.auth_login(
                                    ["kiro", "--method", "api-key"]
                                )
        self.assertEqual(result, 0, err_buf.getvalue())
        self.assertIn("Stored", out_buf.getvalue())


# ── Task 4.3: No-tty-without-method ──────────────────────────────────────────

class TestNoTtyWithoutMethod(unittest.TestCase):
    """auth login without --method and non-tty stdin exits non-zero."""

    def test_no_method_no_tty_exits_nonzero(self):
        err_buf = io.StringIO()
        with patch.object(gs, "_discover_transport",
                          return_value=("http://localhost:64057", None)):
            with patch("sys.stdin", io.StringIO("not a tty")):
                with patch("sys.stderr", err_buf):
                    result = gs.auth_login(["kiro"])
        self.assertNotEqual(result, 0)
        self.assertIn("--method", err_buf.getvalue())


# ── Task 4.3: Empty secret ────────────────────────────────────────────────────

class TestEmptySecret(unittest.TestCase):
    """Empty secret exits non-zero without contacting the transport."""

    def test_empty_secret_exits_nonzero(self):
        err_buf = io.StringIO()
        with patch.object(gs, "_discover_transport",
                          return_value=("http://localhost:64057", None)):
            with patch.object(gs, "_http_json", return_value={"configured": False}):
                with patch.object(gs, "_read_secret", return_value=""):
                    with patch("sys.stderr", err_buf):
                        result = gs.auth_login(["kiro", "--method", "api-key"])
        self.assertNotEqual(result, 0)
        self.assertIn("empty", err_buf.getvalue().lower())


# ── Task 4.4: auth logout and auth status ────────────────────────────────────

class TestAuthLogout(unittest.TestCase):
    """auth logout <backend>: success and nothing-stored cases."""

    def test_logout_success(self):
        out_buf = io.StringIO()
        with patch.object(gs, "_discover_transport",
                          return_value=("http://localhost:64057", None)):
            with patch.object(gs, "_http_json", return_value={"status": "logged_out"}):
                with patch("sys.stdout", out_buf):
                    result = gs.auth_logout(["claude"])
        self.assertEqual(result, 0)
        self.assertIn("claude", out_buf.getvalue())
        self.assertIn("Logged out", out_buf.getvalue())

    def test_logout_already_empty_returns_0(self):
        """Logout when nothing is stored should still succeed (idempotent)."""
        out_buf = io.StringIO()
        with patch.object(gs, "_discover_transport",
                          return_value=("http://localhost:64057", None)):
            # Transport returns 200 (idempotent logout)
            with patch.object(gs, "_http_json", return_value={"status": "logged_out"}):
                with patch("sys.stdout", out_buf):
                    result = gs.auth_logout(["codex"])
        self.assertEqual(result, 0)


class TestAuthStatus(unittest.TestCase):
    """auth status: table and --json, no values in output."""

    def _mock_status(self, configured: bool = False, method: str | None = None):
        """Return a side_effect list for three GET /login/{backend} calls."""
        def _resp(backend):
            return {
                "backend": backend,
                "configured": configured and backend == "claude",
                "method": method if (configured and backend == "claude") else None,
                "stored_at": "2026-10-17T05:00:00Z" if (configured and backend == "claude") else None,
                "pending_flow": None,
            }
        return [_resp("kiro"), _resp("claude"), _resp("codex")]

    def test_status_table_no_values(self):
        out_buf = io.StringIO()
        secret = "sk-ant-super-secret"
        with patch.object(gs, "_discover_transport",
                          return_value=("http://localhost:64057", None)):
            with patch.object(gs, "_http_json",
                              side_effect=self._mock_status(configured=True, method="api-key")):
                with patch("sys.stdout", out_buf):
                    result = gs.auth_status([])
        self.assertEqual(result, 0)
        output = out_buf.getvalue()
        # Table has all three backends
        self.assertIn("kiro", output)
        self.assertIn("claude", output)
        self.assertIn("codex", output)
        # Claude shows method
        self.assertIn("api-key", output)
        # No secret value
        self.assertNotIn(secret, output)

    def test_status_json_flag(self):
        out_buf = io.StringIO()
        with patch.object(gs, "_discover_transport",
                          return_value=("http://localhost:64057", None)):
            with patch.object(gs, "_http_json",
                              side_effect=self._mock_status()):
                with patch("sys.stdout", out_buf):
                    result = gs.auth_status(["--json"])
        self.assertEqual(result, 0)
        data = json.loads(out_buf.getvalue())
        self.assertIn("kiro", data)
        self.assertIn("claude", data)
        self.assertIn("codex", data)


if __name__ == "__main__":
    unittest.main()
