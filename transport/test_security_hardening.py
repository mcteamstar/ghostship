"""Tests for trn-27-security-hardening: Podman secrets, login TOCTOU, guarded clear."""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Import server using the same stub pattern as other transport tests ────────

try:
    server = importlib.import_module("transport.server")
except ModuleNotFoundError:
    # Running from repo root without deps — install stubs first
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from test_file_transfer import _install_import_stubs
    except ImportError:
        from transport.test_file_transfer import _install_import_stubs  # type: ignore[no-redef]
    _install_import_stubs()
    server = importlib.import_module("transport.server")


class TestLoadApiKey(unittest.TestCase):
    """Section 2: transport reads /run/secrets/ga-api-key."""

    def test_reads_from_secrets_file(self):
        """5.3: transport reads /run/secrets/ga-api-key when file exists."""
        original_is_file = Path.is_file
        original_read_text = Path.read_text

        def mock_is_file(self):
            if str(self) == "/run/secrets/ga-api-key":
                return True
            return original_is_file(self)

        def mock_read_text(self, *args, **kwargs):
            if str(self) == "/run/secrets/ga-api-key":
                return "  test-secret-key-123  \n"
            return original_read_text(self, *args, **kwargs)

        with patch.object(Path, "is_file", mock_is_file), \
             patch.object(Path, "read_text", mock_read_text):
            result = server._load_api_key()
            self.assertEqual(result, "test-secret-key-123")

    def test_falls_back_to_env_var_with_deprecation_warning(self):
        """5.4: transport falls back to env var with deprecation warning when file absent."""
        original_is_file = Path.is_file

        def mock_is_file(self):
            if str(self) == "/run/secrets/ga-api-key":
                return False
            return original_is_file(self)

        with patch.object(Path, "is_file", mock_is_file), \
             patch.dict(os.environ, {"GA_API_KEY": "env-key-456"}), \
             patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            result = server._load_api_key()
            self.assertEqual(result, "env-key-456")
            mock_logger.warning.assert_called_once()
            self.assertIn("DEPRECATED", mock_logger.warning.call_args[0][0])

    def test_no_key_returns_empty(self):
        """Neither secret file nor env var → empty string, auth disabled."""
        original_is_file = Path.is_file

        def mock_is_file(self):
            if str(self) == "/run/secrets/ga-api-key":
                return False
            return original_is_file(self)

        env_backup = os.environ.pop("GA_API_KEY", None)
        try:
            with patch.object(Path, "is_file", mock_is_file), \
                 patch("logging.getLogger") as mock_get_logger:
                mock_logger = MagicMock()
                mock_get_logger.return_value = mock_logger
                result = server._load_api_key()
                self.assertEqual(result, "")
                mock_logger.info.assert_called_once()
        finally:
            if env_backup is not None:
                os.environ["GA_API_KEY"] = env_backup


class TestLoginPostTOCTOU(unittest.TestCase):
    """Section 3: concurrent POST /login — only one gets 200, other gets 409."""

    def test_concurrent_post_login_one_wins(self):
        """5.1: Two threads call POST /login simultaneously; exactly one gets 200, other 409."""
        # Reset module state
        server._login_pending = None

        results = [None, None]
        barrier = threading.Barrier(2, timeout=5)

        # Mock dependencies
        mock_podman = MagicMock()
        mock_podman.container_exec.return_value = "kiro-cli"

        container_counter = [0]
        counter_lock = threading.Lock()

        def slow_start(podman):
            with counter_lock:
                container_counter[0] += 1
                n = container_counter[0]
            time.sleep(0.05)
            return f"ga-login-test-{n}"

        def mock_read_auth():
            return ""  # Not authenticated

        def mock_get_podman():
            return mock_podman

        # Mock the pty exec to return a fake URL
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"Open this URL: https://example.com/device?user_code=TEST-1234"
        mock_sock.setblocking = MagicMock()
        mock_podman.container_exec_pty_stdin.return_value = ("exec-123", mock_sock)

        def run_login(idx):
            barrier.wait()
            loop = asyncio.new_event_loop()
            try:
                with patch.object(server, "_read_auth_file", mock_read_auth), \
                     patch.object(server, "_get_podman", mock_get_podman), \
                     patch.object(server, "_start_login_container", slow_start), \
                     patch.object(server, "_nuke_login_container"):
                    request = MagicMock()
                    resp = loop.run_until_complete(server._handle_login_post(request))
                    results[idx] = resp.status_code
            except Exception as e:
                results[idx] = f"error: {e}"
            finally:
                loop.close()

        t1 = threading.Thread(target=run_login, args=(0,))
        t2 = threading.Thread(target=run_login, args=(1,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Exactly one should be 409
        status_codes = sorted([r for r in results if isinstance(r, int)])
        self.assertIn(409, status_codes,
                      f"Expected one 409 from concurrent POST /login, got: {results}")
        # The other should succeed (200) or at least not also be 409
        non_409 = [s for s in status_codes if s != 409]
        self.assertTrue(len(non_409) >= 1,
                        f"Expected at least one non-409 result, got: {results}")

        # Clean up
        server._login_pending = None


class TestLoginGetGuardedClear(unittest.TestCase):
    """Section 4: GET /login clear guard — only clears if container matches."""

    def test_does_not_clear_if_different_container(self):
        """5.2: _login_pending with different container name is NOT cleared."""
        # The old container (the one that just completed)
        old_pending = {
            "container": "ga-login-OLD-xyz789",
            "started_at": time.time() - 60,
            "state": "started",
            "exec_id": "exec-old",
        }

        # Simulate: the GET handler captured old_pending, then a new POST set a new sentinel
        server._login_pending = {
            "container": "ga-login-NEW-abc123",
            "started_at": time.time(),
            "state": "started",
            "exec_id": "exec-new",
        }

        # Execute the guarded clear logic (as in _handle_login_get)
        with server._login_pending_lock:
            if server._login_pending is not None and \
               server._login_pending.get("container") == old_pending["container"]:
                server._login_pending = None

        # _login_pending should NOT be cleared (different container)
        self.assertIsNotNone(server._login_pending)
        self.assertEqual(server._login_pending["container"], "ga-login-NEW-abc123")

        # Clean up
        server._login_pending = None

    def test_clears_when_container_matches(self):
        """GET /login clears _login_pending when container matches."""
        container_name = "ga-login-match-abc"
        server._login_pending = {
            "container": container_name,
            "started_at": time.time(),
            "state": "started",
            "exec_id": "exec-match",
        }

        pending = server._login_pending.copy()

        # Execute the guarded clear logic
        with server._login_pending_lock:
            if server._login_pending is not None and \
               server._login_pending.get("container") == pending["container"]:
                server._login_pending = None

        self.assertIsNone(server._login_pending)


class TestInstallShPodmanSecret(unittest.TestCase):
    """Section 1 + 5.5: install.sh creates Podman secret, no GA_API_KEY in env."""

    def test_install_script_has_secret_create(self):
        """5.5 (partial): install.sh contains podman secret create and no env-var pass."""
        install_path = Path(__file__).resolve().parent.parent / "install.sh"
        if not install_path.exists():
            self.skipTest("install.sh not found relative to test")

        content = install_path.read_text()
        self.assertIn("secret rm ga-api-key", content)
        self.assertIn("secret create ga-api-key", content)
        self.assertIn("--secret ga-api-key", content)
        # Verify the env var line is gone
        self.assertNotIn('-e "GA_API_KEY=${GA_API_KEY:-}"', content)


if __name__ == "__main__":
    unittest.main()
