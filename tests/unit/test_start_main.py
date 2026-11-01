"""Unit tests for bin/lib/start_main.py (TRN-297).

All external I/O is mocked:
- podman_setup.setup_podman_linux / setup_podman_macos
- subprocess.run (compose up)
- urllib.request.urlopen (health check)
- time.sleep (health check loop)

No running Podman daemon required.
"""
from __future__ import annotations

import importlib
import platform
import sys
import types
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — make bin/lib importable
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BIN_LIB = _REPO_ROOT / "bin" / "lib"

if str(_BIN_LIB) not in sys.path:
    sys.path.insert(0, str(_BIN_LIB))
if str(_BIN_LIB / "vendor") not in sys.path:
    sys.path.insert(0, str(_BIN_LIB / "vendor"))

import start_main  # noqa: E402  (must come after sys.path setup)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_module(monkeypatch, tmp_path):
    """Provide a fake data_dir with a compose.yml for each test."""
    # Write a dummy compose.yml so _compose_up path check passes
    data_dir = tmp_path / "ghost-academy" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "compose.yml").write_text("version: '3'\n", encoding="utf-8")
    yield data_dir


@pytest.fixture
def compose_yml(tmp_path):
    data_dir = tmp_path / "ghost-academy" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    p = data_dir / "compose.yml"
    p.write_text("version: '3'\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_args(config="", machine_name=""):
    """Return a minimal argparse.Namespace matching _build_parser output."""
    import argparse
    return argparse.Namespace(config=config, machine_name=machine_name)


def _fake_cfg():
    return {
        "GA_MACHINE_NAME": "ghost-academy",
        "GA_DEDICATED_MACHINE": "true",
        "PORT": "64057",
        "HOST": "127.0.0.1",
        "GA_PORTAL_TLS_MODE": "off",
    }


# ---------------------------------------------------------------------------
# T3 Test 1: Successful start
# ---------------------------------------------------------------------------

class TestSuccessfulStart:
    """Full happy-path: config resolves, podman starts, compose up succeeds,
    health check passes."""

    def test_main_successful_start(self, compose_yml):
        """main() exits 0 when all steps succeed (end-to-end integration test)."""
        fake_proc = MagicMock()
        fake_proc.returncode = 0

        health_check_calls = []

        def fake_health_check(url, **kwargs):
            health_check_calls.append(url)

        with (
            patch.object(start_main, "_resolve_config", return_value=_fake_cfg()),
            patch("start_main._podman_setup.PodmanConfig") as mock_podman_cfg_cls,
            patch("start_main._podman_setup.setup_podman_linux",
                  return_value="/run/user/1000/ghost-academy/podman.sock") as mock_setup_linux,
            patch("start_main._podman_setup.setup_podman_macos",
                  return_value="/run/user/1000/podman/podman.sock"),
            patch("start_main._OS", "Linux"),
            patch("shutil.which", return_value="/usr/bin/podman-compose"),
            patch("subprocess.run", return_value=fake_proc),
            patch.object(start_main, "_health_check", side_effect=fake_health_check),
            patch("start_main.Path") as mock_path_cls,
        ):
            # Make Path(...) / "compose.yml" appear to be a real file
            mock_compose_file = MagicMock()
            mock_compose_file.is_file.return_value = True
            mock_compose_file.__str__ = lambda self: str(compose_yml)
            mock_path_cls.home.return_value = MagicMock()
            # Build the chain: Path.home() / ".local" / "share" → xdg_data
            xdg_mock = MagicMock()
            xdg_mock.__truediv__ = lambda self, other: xdg_mock
            xdg_mock.is_file.return_value = True
            mock_path_cls.return_value.__truediv__.return_value = mock_compose_file
            mock_path_cls.home.return_value.__truediv__.return_value = xdg_mock
            xdg_mock.__truediv__ = lambda s, o: mock_compose_file

            import argparse
            with patch("argparse.ArgumentParser.parse_args",
                       return_value=argparse.Namespace(config="", machine_name="")):
                # Should not raise — happy path exits 0
                start_main.main()

            # Verify setup_podman_linux was invoked (podman runtime was started)
            mock_setup_linux.assert_called_once()
            # Verify _health_check was called with the correct probe URL
            assert health_check_calls, "_health_check was not called"
            assert "health" in health_check_calls[0]

    def test_compose_env_no_eval(self, compose_yml):
        """_compose_up passes env as explicit dict, never uses shell=True."""
        compose_file = compose_yml
        fake_proc = MagicMock()
        fake_proc.returncode = 0

        captured_calls = []

        def capturing_run(cmd, **kwargs):
            captured_calls.append((cmd, kwargs))
            return fake_proc

        with patch("subprocess.run", side_effect=capturing_run):
            start_main._compose_up(compose_file, {"MY_VAR": "value"})

        assert captured_calls, "subprocess.run was never called"
        _cmd, kwargs = captured_calls[0]
        # env must be passed as a dict, not via shell=True
        assert "env" in kwargs, "compose env not passed via env= kwarg"
        assert isinstance(kwargs["env"], dict), "env must be a dict"
        assert kwargs.get("shell") is not True, "shell=True must never be used"

    def test_podman_already_running_continues(self, compose_yml):
        """When podman_setup returns a socket path (podman already running),
        compose up proceeds using that socket."""
        fake_proc = MagicMock()
        fake_proc.returncode = 0

        # Simulate setup_podman_linux succeeding (podman was already running;
        # setup_podman returns the socket path without starting a new instance).
        with (
            patch.object(start_main, "_resolve_config", return_value=_fake_cfg()),
            patch("start_main._podman_setup.PodmanConfig"),
            patch("start_main._podman_setup.setup_podman_linux",
                  return_value="/run/user/1000/ghost-academy/podman.sock") as mock_setup,
            patch("start_main._OS", "Linux"),
            patch("shutil.which", return_value="/usr/bin/podman-compose"),
            patch("subprocess.run", return_value=fake_proc) as mock_run,
            patch.object(start_main, "_health_check"),
            patch("start_main.Path") as mock_path_cls,
        ):
            mock_compose_file = MagicMock()
            mock_compose_file.is_file.return_value = True
            mock_compose_file.__str__ = lambda self: str(compose_yml)
            xdg_mock = MagicMock()
            xdg_mock.__truediv__ = lambda s, o: mock_compose_file
            mock_path_cls.home.return_value.__truediv__.return_value = xdg_mock

            import argparse
            with patch("argparse.ArgumentParser.parse_args",
                       return_value=argparse.Namespace(config="", machine_name="")):
                start_main.main()

        # setup_podman_linux was called — it returned the existing socket path
        mock_setup.assert_called_once()
        # compose up was subsequently invoked
        assert mock_run.called, "subprocess.run (compose up) was never called"
        # The compose env should contain CONTAINER_HOST set from the returned socket
        call_kwargs = mock_run.call_args[1]
        assert "env" in call_kwargs
        assert call_kwargs["env"].get("CONTAINER_HOST") == "unix:///run/user/1000/ghost-academy/podman.sock"


# ---------------------------------------------------------------------------
# T3 Test 2: Compose up failure exits non-zero
# ---------------------------------------------------------------------------

class TestComposeUpFailure:
    """Compose up failing causes _die (SystemExit with code 1)."""

    def test_compose_up_failure_raises(self, compose_yml):
        """_compose_up raises SystemExit when compose returns non-zero."""
        compose_file = compose_yml
        fake_proc = MagicMock()
        fake_proc.returncode = 1

        with patch("subprocess.run", return_value=fake_proc):
            with pytest.raises(SystemExit) as exc_info:
                start_main._compose_up(compose_file, {})
        assert exc_info.value.code != 0

    def test_compose_up_failure_message(self, compose_yml, capsys):
        """_compose_up prints a diagnostic when compose fails."""
        compose_file = compose_yml
        fake_proc = MagicMock()
        fake_proc.returncode = 2

        with patch("subprocess.run", return_value=fake_proc):
            with pytest.raises(SystemExit):
                start_main._compose_up(compose_file, {})

        captured = capsys.readouterr()
        assert "compose" in captured.err.lower() or "failed" in captured.err.lower()


# ---------------------------------------------------------------------------
# T3 Test 3: Health check timeout
# ---------------------------------------------------------------------------

class TestHealthCheckTimeout:
    """Health check timing out causes SystemExit with non-zero code."""

    def test_health_check_timeout_exits(self):
        """_health_check exits non-zero after all retries fail."""
        def always_fail(url, timeout=5):
            raise urllib.error.URLError("connection refused")

        with pytest.raises(SystemExit) as exc_info:
            start_main._health_check(
                "http://127.0.0.1:64057/health",
                max_retries=3,
                interval=0.0,
                urlopen=always_fail,
                sleep_fn=lambda _: None,
            )
        assert exc_info.value.code != 0

    def test_health_check_timeout_message(self, capsys):
        """_health_check prints a timeout diagnostic."""
        def always_fail(url, timeout=5):
            raise urllib.error.URLError("connection refused")

        with pytest.raises(SystemExit):
            start_main._health_check(
                "http://127.0.0.1:64057/health",
                max_retries=2,
                interval=0.0,
                urlopen=always_fail,
                sleep_fn=lambda _: None,
            )
        captured = capsys.readouterr()
        assert "did not become ready" in captured.err or "timeout" in captured.err.lower()

    def test_health_check_wildcard_host_uses_loopback(self):
        """When host is 0.0.0.0, probe_base targets 127.0.0.1."""
        from portal_host import probe_base
        url = probe_base("0.0.0.0", "64057", "http") + "/health"
        assert "127.0.0.1" in url, f"expected 127.0.0.1 in probe URL, got: {url}"

    def test_health_check_success_on_first_attempt(self):
        """_health_check returns without error when urlopen succeeds."""
        call_count = {"n": 0}

        def succeed_once(url, timeout=5):
            call_count["n"] += 1
            return MagicMock()

        # Should not raise
        start_main._health_check(
            "http://127.0.0.1:64057/health",
            max_retries=5,
            interval=0.0,
            urlopen=succeed_once,
            sleep_fn=lambda _: None,
        )
        assert call_count["n"] == 1, "urlopen should have been called exactly once"

    def test_health_check_retries_before_success(self):
        """_health_check retries until the endpoint responds."""
        attempts = {"n": 0}

        def fail_twice_then_succeed(url, timeout=5):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise urllib.error.URLError("not yet")
            return MagicMock()

        start_main._health_check(
            "http://127.0.0.1:64057/health",
            max_retries=5,
            interval=0.0,
            urlopen=fail_twice_then_succeed,
            sleep_fn=lambda _: None,
        )
        assert attempts["n"] == 3

    def test_health_check_sleeps_between_retries(self):
        """_health_check calls sleep_fn between failed attempts."""
        sleep_calls = []

        def always_fail(url, timeout=5):
            raise urllib.error.URLError("connection refused")

        with pytest.raises(SystemExit):
            start_main._health_check(
                "http://127.0.0.1:64057/health",
                max_retries=3,
                interval=1.5,
                urlopen=always_fail,
                sleep_fn=lambda s: sleep_calls.append(s),
            )

        assert len(sleep_calls) == 3
        assert all(s == 1.5 for s in sleep_calls)


# ---------------------------------------------------------------------------
# T3 Test 4: Build compose env dict (no eval)
# ---------------------------------------------------------------------------

class TestBuildComposeEnv:
    """_build_compose_env always returns a dict with no shell interpolation."""

    def test_linux_dedicated_sets_container_host(self):
        with patch("start_main._OS", "Linux"):
            env = start_main._build_compose_env(
                dedicated=True,
                machine_name="ghost-academy",
                podman_sock="/run/user/1000/ghost-academy/podman.sock",
            )
        assert env["CONTAINER_HOST"] == "unix:///run/user/1000/ghost-academy/podman.sock"
        assert "CONTAINER_CONNECTION" not in env

    def test_macos_dedicated_sets_container_connection(self):
        with patch("start_main._OS", "Darwin"):
            env = start_main._build_compose_env(
                dedicated=True,
                machine_name="ghost-academy",
                podman_sock="/run/user/1000/podman/podman.sock",
            )
        assert env["CONTAINER_CONNECTION"] == "ghost-academy"
        assert "CONTAINER_HOST" not in env

    def test_non_dedicated_no_special_vars(self):
        with patch("start_main._OS", "Linux"):
            env = start_main._build_compose_env(
                dedicated=False,
                machine_name="ghost-academy",
                podman_sock="/run/user/1000/podman/podman.sock",
            )
        assert "CONTAINER_HOST" not in env
        assert "CONTAINER_CONNECTION" not in env

    def test_env_is_dict(self):
        with patch("start_main._OS", "Linux"):
            env = start_main._build_compose_env(
                dedicated=True,
                machine_name="ghost-academy",
                podman_sock="/tmp/test.sock",
            )
        assert isinstance(env, dict)

    def test_podman_compose_provider_set(self):
        with (
            patch("start_main._OS", "Linux"),
            patch("shutil.which", return_value="/usr/local/bin/podman-compose"),
        ):
            env = start_main._build_compose_env(
                dedicated=True,
                machine_name="ghost-academy",
                podman_sock="/tmp/test.sock",
            )
        assert env["PODMAN_COMPOSE_PROVIDER"] == "/usr/local/bin/podman-compose"
