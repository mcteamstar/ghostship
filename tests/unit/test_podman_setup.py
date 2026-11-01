"""Unit tests for bin/lib/podman_setup.py.

All subprocess calls are mocked — no live Podman required.

Coverage:
(a) Missing socket after max retries raises RuntimeError with a diagnostic message.
(b) Linux socket path computed correctly from XDG_RUNTIME_DIR.
(c) Dedicated-instance systemd unit content contains correct --root and --runroot paths.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from bin.lib.podman_setup import (
    PodmanConfig,
    _wait_for_socket,
    resolve_socket_path,
    setup_podman_linux,
    write_systemd_unit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(
    machine_name: str = "ghost-academy",
    dedicated: bool = True,
    xdg_runtime_dir: str = "/run/user/1000",
    home_dir: str = "/home/user",
    socket_max_retries: int = 3,
    socket_retry_delay: float = 0.0,
) -> PodmanConfig:
    c = PodmanConfig(
        machine_name=machine_name,
        dedicated=dedicated,
        xdg_runtime_dir=xdg_runtime_dir,
        home_dir=home_dir,
        socket_max_retries=socket_max_retries,
        socket_retry_delay=socket_retry_delay,
    )
    # Bypass default initialisation that reads real env
    c.xdg_runtime_dir = xdg_runtime_dir
    c.home_dir = home_dir
    return c


def _run_noop(*args, **kwargs):
    """Default mock run: returns a success CompletedProcess."""
    return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")


# ---------------------------------------------------------------------------
# (a) Missing socket → RuntimeError
# ---------------------------------------------------------------------------

class TestSocketWait:
    def test_missing_socket_raises_runtime_error(self, tmp_path: Path) -> None:
        config = _config(
            socket_max_retries=3,
            socket_retry_delay=0.0,
            xdg_runtime_dir=str(tmp_path),
        )
        fake_path = str(tmp_path / "podman.sock")  # never created

        with pytest.raises(RuntimeError, match=fake_path):
            _wait_for_socket(
                fake_path,
                config,
                sleep_fn=lambda _: None,
            )

    def test_socket_error_message_includes_debug_hint(self, tmp_path: Path) -> None:
        config = _config(
            machine_name="ghost-academy",
            socket_max_retries=1,
            socket_retry_delay=0.0,
            xdg_runtime_dir=str(tmp_path),
        )
        with pytest.raises(RuntimeError, match="podman-ghost-academy"):
            _wait_for_socket(
                str(tmp_path / "missing.sock"),
                config,
                sleep_fn=lambda _: None,
            )

    def test_socket_found_immediately_does_not_raise(self, tmp_path: Path) -> None:
        sock = tmp_path / "podman.sock"
        sock.touch()
        # Pretend it IS a socket: patch is_socket()
        config = _config(socket_max_retries=3, xdg_runtime_dir=str(tmp_path))
        with patch.object(Path, "is_socket", return_value=True):
            _wait_for_socket(str(sock), config, sleep_fn=lambda _: None)

    def test_bounded_retry_count(self, tmp_path: Path) -> None:
        """_wait_for_socket sleeps exactly max_retries times before raising."""
        config = _config(
            socket_max_retries=4,
            socket_retry_delay=0.0,
            xdg_runtime_dir=str(tmp_path),
        )
        sleep_calls = []
        with pytest.raises(RuntimeError):
            _wait_for_socket(
                str(tmp_path / "nope.sock"),
                config,
                sleep_fn=lambda d: sleep_calls.append(d),
            )
        assert len(sleep_calls) == 4


# ---------------------------------------------------------------------------
# (b) Linux socket path from XDG_RUNTIME_DIR
# ---------------------------------------------------------------------------

class TestResolveSocketPath:
    def test_uses_xdg_runtime_dir(self) -> None:
        config = _config(xdg_runtime_dir="/run/user/1234")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PODMAN_SOCK", None)
            path = resolve_socket_path(config)
        assert path == "/run/user/1234/ghost-academy/podman.sock"

    def test_non_dedicated_uses_default_socket_name(self) -> None:
        config = _config(xdg_runtime_dir="/run/user/1234", dedicated=False)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PODMAN_SOCK", None)
            path = resolve_socket_path(config)
        assert path == "/run/user/1234/podman/podman.sock"

    def test_env_override_wins(self) -> None:
        config = _config(xdg_runtime_dir="/run/user/1234")
        with patch.dict(os.environ, {"PODMAN_SOCK": "/custom/podman.sock"}):
            path = resolve_socket_path(config)
        assert path == "/custom/podman.sock"


# ---------------------------------------------------------------------------
# (c) Dedicated-instance systemd unit content
# ---------------------------------------------------------------------------

class TestWriteSystemdUnit:
    def test_unit_contains_storage_root(self) -> None:
        config = _config(
            machine_name="ghost-academy",
            home_dir="/home/user",
            xdg_runtime_dir="/run/user/1000",
        )
        unit = write_systemd_unit(config)
        assert "--root=/home/user/.local/share/ghost-academy/containers/storage" in unit

    def test_unit_contains_runroot(self) -> None:
        config = _config(
            machine_name="ghost-academy",
            home_dir="/home/user",
            xdg_runtime_dir="/run/user/1000",
        )
        unit = write_systemd_unit(config)
        assert "--runroot=/run/user/1000/ghost-academy-containers" in unit

    def test_unit_uses_simple_service_type(self) -> None:
        config = _config()
        unit = write_systemd_unit(config)
        assert "Type=simple" in unit

    def test_unit_socket_path_in_exec_start(self) -> None:
        config = _config(
            machine_name="ga",
            xdg_runtime_dir="/run/user/500",
        )
        unit = write_systemd_unit(config)
        assert "unix:///run/user/500/ga/podman.sock" in unit

    def test_unit_description_contains_machine_name(self) -> None:
        config = _config(machine_name="my-academy")
        unit = write_systemd_unit(config)
        assert "my-academy" in unit


# ---------------------------------------------------------------------------
# setup_podman_linux: dedicated instance
# ---------------------------------------------------------------------------

class TestSetupPodmanLinux:
    def test_dedicated_creates_unit_file(self, tmp_path: Path) -> None:
        config = _config(
            dedicated=True,
            xdg_runtime_dir=str(tmp_path / "run"),
            home_dir=str(tmp_path / "home"),
        )
        Path(config.home_dir).mkdir(parents=True, exist_ok=True)

        sock_path = tmp_path / "run" / "ghost-academy" / "podman.sock"

        calls_log: list = []

        def mock_run(cmd, check=False, **kwargs):
            calls_log.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.object(Path, "is_socket", return_value=True):
            result = setup_podman_linux(config, run=mock_run)

        unit_file = (
            Path(config.home_dir)
            / ".config" / "systemd" / "user"
            / "podman-ghost-academy.service"
        )
        assert unit_file.exists()

    def test_dedicated_calls_systemctl_enable(self, tmp_path: Path) -> None:
        config = _config(
            dedicated=True,
            xdg_runtime_dir=str(tmp_path / "run"),
            home_dir=str(tmp_path / "home"),
        )
        Path(config.home_dir).mkdir(parents=True, exist_ok=True)

        calls_log: list = []

        def mock_run(cmd, check=False, **kwargs):
            calls_log.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.object(Path, "is_socket", return_value=True):
            setup_podman_linux(config, run=mock_run)

        flat = [" ".join(c) for c in calls_log]
        assert any("enable" in c and "podman-ghost-academy.service" in c for c in flat)

    def test_socket_not_found_raises_runtime_error(self, tmp_path: Path) -> None:
        config = _config(
            dedicated=True,
            socket_max_retries=2,
            socket_retry_delay=0.0,
            xdg_runtime_dir=str(tmp_path / "run"),
            home_dir=str(tmp_path / "home"),
        )
        Path(config.home_dir).mkdir(parents=True, exist_ok=True)

        def mock_run(cmd, check=False, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.object(Path, "is_socket", return_value=False):
            with pytest.raises(RuntimeError, match="Podman socket not reachable"):
                setup_podman_linux(config, run=mock_run)
