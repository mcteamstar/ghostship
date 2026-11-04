#!/usr/bin/env python3
"""podman_setup.py — Podman machine/instance provisioning for Ghost Academy.

Replaces the Podman provisioning blocks in bin/install.sh.
All Podman calls use subprocess.run([...], check=True) — no eval.
Socket paths are captured as Python strings, never eval'd into shell.

Functions:
    setup_podman_linux(config) -> str   — provision Linux, return socket path
    setup_podman_macos(config) -> str   — provision macOS, return socket path
    resolve_socket_path(config) -> str  — derive default Linux socket path
    write_systemd_unit(config, ...)     — write the dedicated Linux service unit

The module is importable and unit-testable without a live Podman installation.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class PodmanConfig:
    """All fields the provisioning functions need."""

    # Machine name (macOS) / instance name (Linux)
    machine_name: str = "ghost-academy"
    dedicated: bool = True

    # macOS machine sizing
    machine_cpus: int = 8
    machine_memory: int = 8192
    machine_disk: int = 100

    # Linux paths (computed from env when empty)
    xdg_runtime_dir: str = ""
    home_dir: str = ""

    # Socket wait parameters
    socket_max_retries: int = 10
    socket_retry_delay: float = 1.0

    def __post_init__(self) -> None:
        if not self.xdg_runtime_dir:
            self.xdg_runtime_dir = os.environ.get(
                "XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"
            )
        if not self.home_dir:
            self.home_dir = str(Path.home())


# ---------------------------------------------------------------------------
# Linux provisioning
# ---------------------------------------------------------------------------

def setup_podman_linux(
    config: PodmanConfig,
    *,
    run: Callable = subprocess.run,
) -> str:
    """Provision Podman on Linux and return the socket path.

    For a dedicated instance: writes the systemd unit, reloads, enables,
    and returns the socket path. For the default instance: enables
    podman.socket via systemctl and returns the default socket path.

    Args:
        config: PodmanConfig instance.
        run:    subprocess.run-compatible callable (injectable for testing).

    Returns:
        Absolute path to the Podman socket file.
    """
    if config.dedicated:
        sock_path = _setup_linux_dedicated(config, run=run)
    else:
        sock_path = _setup_linux_default(config, run=run)

    _wait_for_socket(sock_path, config, run=run)
    return sock_path


def _setup_linux_dedicated(
    config: PodmanConfig,
    *,
    run: Callable = subprocess.run,
) -> str:
    machine = config.machine_name
    runtime_dir = config.xdg_runtime_dir
    home_dir = config.home_dir
    storage_root = f"{home_dir}/.local/share/{machine}/containers/storage"
    unit_dir = f"{home_dir}/.config/systemd/user"
    ga_containers_conf = f"{home_dir}/.config/{machine}/containers.conf"

    Path(unit_dir).mkdir(parents=True, exist_ok=True)

    # Remove stale socket-activation unit from previous installs.
    socket_unit = Path(unit_dir) / f"podman-{machine}.socket"
    socket_unit.unlink(missing_ok=True)

    unit_content = write_systemd_unit(
        config,
        storage_root=storage_root,
        runtime_dir=runtime_dir,
        ga_containers_conf=ga_containers_conf,
    )
    unit_path = Path(unit_dir) / f"podman-{machine}.service"
    unit_path.write_text(unit_content, encoding="utf-8")
    print(f"✓ Systemd service unit written to {unit_path}")

    run(["systemctl", "--user", "daemon-reload"], check=True)
    run(["systemctl", "--user", "enable", "--now", f"podman-{machine}.service"], check=True)

    # Enable lingering for reboot survival.
    try:
        run(
            ["loginctl", "enable-linger", os.environ.get("USER", "")],
            check=True,
        )
        print("✓ Linger enabled — dedicated instance survives logout/reboot")
    except Exception:
        pass  # loginctl failure is non-fatal

    sock_path = f"{runtime_dir}/{machine}/podman.sock"
    return sock_path


def _setup_linux_default(
    config: PodmanConfig,
    *,
    run: Callable = subprocess.run,
) -> str:
    run(
        ["systemctl", "--user", "enable", "--now", "podman.socket"],
        check=False,  # May already be active; non-fatal
    )
    run(
        ["systemctl", "--user", "enable", "podman-restart.service"],
        check=False,
    )
    print("✓ podman.socket + podman-restart.service enabled")

    try:
        run(
            ["loginctl", "enable-linger", os.environ.get("USER", "")],
            check=True,
        )
        print("✓ Linger enabled — transport survives logout/reboot")
    except Exception:
        pass

    return resolve_socket_path(config)


def write_systemd_unit(
    config: PodmanConfig,
    *,
    storage_root: str = "",
    runtime_dir: str = "",
    ga_containers_conf: str = "",
) -> str:
    """Return the content of the dedicated Podman systemd service unit."""
    machine = config.machine_name
    if not runtime_dir:
        runtime_dir = config.xdg_runtime_dir
    if not storage_root:
        storage_root = (
            f"{config.home_dir}/.local/share/{machine}/containers/storage"
        )
    if not ga_containers_conf:
        ga_containers_conf = f"{config.home_dir}/.config/{machine}/containers.conf"

    return (
        f"[Unit]\n"
        f"Description=Ghost Academy dedicated Podman API ({machine})\n"
        f"After=network.target\n"
        f"\n"
        f"[Service]\n"
        f"Type=simple\n"
        f"Environment=CONTAINERS_CONF={ga_containers_conf}\n"
        f"RuntimeDirectory={machine}\n"
        f"ExecStart=/usr/bin/podman \\\n"
        f"  --root={storage_root} \\\n"
        f"  --runroot={runtime_dir}/{machine}-containers \\\n"
        f"  system service --time=0 unix://{runtime_dir}/{machine}/podman.sock\n"
        f"Restart=on-failure\n"
        f"\n"
        f"[Install]\n"
        f"WantedBy=default.target\n"
    )


# ---------------------------------------------------------------------------
# macOS provisioning
# ---------------------------------------------------------------------------

def setup_podman_macos(
    config: PodmanConfig,
    *,
    run: Callable = subprocess.run,
) -> str:
    """Provision Podman on macOS and return the in-guest socket path.

    For a dedicated machine: init (if needed), start (if not running),
    enable podman-restart.service in the guest, resolve guest UID.
    For the default machine: same but without a named machine.

    Args:
        config: PodmanConfig instance.
        run:    subprocess.run-compatible callable (injectable for testing).

    Returns:
        In-guest socket path (e.g. /run/user/<uid>/podman/podman.sock).
    """
    if config.dedicated:
        return _setup_macos_dedicated(config, run=run)
    return _setup_macos_default(config, run=run)


def _setup_macos_dedicated(
    config: PodmanConfig,
    *,
    run: Callable = subprocess.run,
) -> str:
    machine = config.machine_name

    # Init the machine if it does not yet exist.
    list_result = run(
        ["podman", "machine", "list", "--format", "{{.Name}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    existing_machines = [n.rstrip("*") for n in list_result.stdout.split()]
    if machine not in existing_machines:
        print(f"Initialising dedicated podman machine '{machine}'...")
        run(
            [
                "podman", "machine", "init", machine,
                "--cpus", str(config.machine_cpus),
                "--memory", str(config.machine_memory),
                "--disk-size", str(config.machine_disk),
            ],
            check=True,
        )

    # Start if not already running.
    state_result = run(
        ["podman", "machine", "inspect", machine, "--format", "{{.State}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    if "running" not in state_result.stdout.lower():
        print(f"Starting dedicated podman machine '{machine}'...")
        run(["podman", "machine", "start", machine], check=True)

    # Enable podman-restart.service inside the guest.
    run(
        ["podman", "machine", "ssh", machine, "--",
         "systemctl", "--user", "enable", "podman-restart.service"],
        check=True,
    )
    print(f"✓ podman-restart.service enabled in dedicated machine '{machine}'")

    guest_uid = _get_guest_uid(machine=machine, run=run)
    sock_path = f"/run/user/{guest_uid}/podman/podman.sock"
    print(f"✓ Dedicated machine '{machine}' guest socket: {sock_path}")
    return sock_path


def _setup_macos_default(
    config: PodmanConfig,
    *,
    run: Callable = subprocess.run,
) -> str:
    # Init if no machine exists.
    list_result = run(
        ["podman", "machine", "list", "--format", "{{.Name}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    if not list_result.stdout.strip():
        print("Initialising podman machine...")
        run(
            ["podman", "machine", "init",
             "--cpus", "4", "--memory", "8192", "--disk-size", "60"],
            check=True,
        )

    # Start if not running.
    running_result = run(
        ["podman", "machine", "list", "--format", "{{.Running}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    if "true" not in running_result.stdout.lower():
        print("Starting podman machine...")
        run(["podman", "machine", "start"], check=True)

    run(
        ["podman", "machine", "ssh", "--",
         "systemctl", "--user", "enable", "podman-restart.service"],
        check=True,
    )
    print("✓ podman-restart.service enabled (transport survives machine restarts)")

    guest_uid = _get_guest_uid(machine=None, run=run)
    sock_path = f"/run/user/{guest_uid}/podman/podman.sock"
    print(f"✓ Guest podman socket: {sock_path}")
    return sock_path


def _get_guest_uid(
    machine: str | None,
    *,
    run: Callable = subprocess.run,
) -> str:
    """Retrieve the guest UID via podman machine ssh."""
    cmd = ["podman", "machine", "ssh"]
    if machine:
        cmd.append(machine)
    cmd += ["--", "id", "-u"]
    result = run(cmd, check=True, capture_output=True, text=True)
    uid = result.stdout.strip()
    if not uid:
        raise RuntimeError(
            f"Failed to retrieve guest UID from"
            f" {'machine ' + repr(machine) if machine else 'default machine'}"
        )
    return uid


# ---------------------------------------------------------------------------
# resolve_socket_path
# ---------------------------------------------------------------------------

def resolve_socket_path(config: PodmanConfig) -> str:
    """Derive the default Linux Podman socket path.

    Uses XDG_RUNTIME_DIR and id -u (via subprocess, no eval).
    Respects PODMAN_SOCK env var as an override.
    Only used on Linux — macOS uses the in-guest socket returned by
    setup_podman_macos(), not a host filesystem socket.
    """
    env_override = os.environ.get("PODMAN_SOCK", "")
    if env_override:
        return env_override

    uid = _get_local_uid()
    runtime_dir = config.xdg_runtime_dir or f"/run/user/{uid}"
    if config.dedicated and platform.system() == "Linux":
        return f"{runtime_dir}/{config.machine_name}/podman.sock"
    return f"{runtime_dir}/podman/podman.sock"


def _get_local_uid() -> str:
    """Return the current user's UID via id -u (no eval)."""
    result = subprocess.run(
        ["id", "-u"], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Socket wait helper
# ---------------------------------------------------------------------------

def _wait_for_socket(
    sock_path: str,
    config: PodmanConfig,
    *,
    run: Callable = subprocess.run,
    sleep_fn: Callable = time.sleep,
) -> None:
    """Wait for the socket file to appear, bounded by config.socket_max_retries."""
    for _ in range(config.socket_max_retries):
        if Path(sock_path).is_socket():
            return
        sleep_fn(config.socket_retry_delay)

    if not Path(sock_path).is_socket():
        raise RuntimeError(
            f"Podman socket not reachable at: {sock_path}\n"
            f"Check: systemctl --user status podman-{config.machine_name}.service\n"
            f"Journal: journalctl --user -u podman-{config.machine_name}.service"
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _config_from_env() -> PodmanConfig:
    env = os.environ
    return PodmanConfig(
        machine_name=env.get("GA_MACHINE_NAME", "ghost-academy"),
        dedicated=(env.get("GA_DEDICATED_MACHINE", "true") == "true"),
        machine_cpus=int(env.get("GA_MACHINE_CPUS", "8")),
        machine_memory=int(env.get("GA_MACHINE_MEMORY", "8192")),
        machine_disk=int(env.get("GA_MACHINE_DISK", "100")),
        xdg_runtime_dir=env.get("XDG_RUNTIME_DIR", ""),
        home_dir=str(Path.home()),
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Provision Podman for Ghost Academy"
    )
    parser.add_argument(
        "--print-socket",
        action="store_true",
        help="Print resolved socket path and exit (no provisioning)",
    )
    args = parser.parse_args()

    config = _config_from_env()

    if args.print_socket:
        print(resolve_socket_path(config))
        return

    os_name = platform.system()
    if os_name == "Darwin":
        sock = setup_podman_macos(config)
    else:
        sock = setup_podman_linux(config)

    print(f"PODMAN_SOCK={sock}")


if __name__ == "__main__":
    main()
