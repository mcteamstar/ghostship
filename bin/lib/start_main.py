#!/usr/bin/env python3
"""start_main.py — Python entry point for `ghostship start`.

Called by the thin bin/start.sh prereq-check shim via:
    exec python3 "${GHOSTSHIP_DIR}/bin/lib/start_main.py" "$@"

This module:
1. Parses --config and --machine-name flags.
2. Resolves config via start_ops / yaml_config (no eval).
3. Delegates Podman machine/socket start to podman_setup.
4. Brings up the compose stack via subprocess (no eval, env as explicit dict).
5. Verifies readiness via urllib.request poll on /health.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup: make bin/lib and vendor importable.
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent  # bin/lib/start_main.py → repo root
_VENDOR = _THIS_DIR / "vendor"

if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

# ---------------------------------------------------------------------------
# Imports from sibling modules.
# ---------------------------------------------------------------------------
import yaml_config as _yaml_config
import podman_setup as _podman_setup
from portal_host import probe_base as _probe_base

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_OS = platform.system()
_HEALTH_MAX_RETRIES = 30
_HEALTH_RETRY_INTERVAL = 1  # seconds


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Start Ghost Academy containers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--config", default="", help="YAML config file path")
    p.add_argument("--machine-name", dest="machine_name", default="",
                   help="Override GA_MACHINE_NAME")
    return p


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def _resolve_config(args: argparse.Namespace) -> dict:
    """Resolve the merged config dict via yaml_config.resolve_config.

    Returns a flat dict of environment variable names → string values.
    No subprocess eval.
    """
    ghostship_dir = str(_REPO_ROOT)

    if _OS == "Darwin":
        xdg_yaml = (
            Path.home() / "Library" / "Application Support"
            / "ghost-academy" / "ghostship.yaml"
        )
    else:
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        xdg_yaml = xdg_config / "ghost-academy" / "ghostship.yaml"

    repo_yaml = Path(ghostship_dir) / "config" / "ghostship.yaml"

    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            _die(f"Config file does not exist: {args.config}")
        merged = _yaml_config.resolve_config(
            repo_path="",
            xdg_path="",
            explicit_path=str(config_path),
        )
    else:
        merged = _yaml_config.resolve_config(
            repo_path=str(repo_yaml),
            xdg_path=str(xdg_yaml),
            explicit_path=None,
        )

    return _yaml_config.flatten_to_env(merged)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # ── Resolve config ────────────────────────────────────────────────────────
    try:
        cfg = _resolve_config(args)
    except SystemExit:
        raise
    except Exception as exc:
        _die(f"Failed to resolve config: {exc}")

    # ── Apply CLI overrides ───────────────────────────────────────────────────
    machine_name = args.machine_name or cfg.get("GA_MACHINE_NAME", "ghost-academy")
    dedicated = cfg.get("GA_DEDICATED_MACHINE", "true") == "true"
    port = cfg.get("PORT", "64057")
    host = cfg.get("HOST", "127.0.0.1")
    tls_mode = cfg.get("GA_PORTAL_TLS_MODE", "off")

    # ── 1. Start Podman runtime via podman_setup ──────────────────────────────
    podman_cfg = _podman_setup.PodmanConfig(
        machine_name=machine_name,
        dedicated=dedicated,
        xdg_runtime_dir=os.environ.get("XDG_RUNTIME_DIR", ""),
        home_dir=str(Path.home()),
    )

    try:
        if _OS == "Darwin":
            podman_sock = _podman_setup.setup_podman_macos(podman_cfg)
        else:
            podman_sock = _podman_setup.setup_podman_linux(podman_cfg)
    except Exception as exc:
        _die(f"Podman setup failed: {exc}")

    # ── 2. Locate compose file ────────────────────────────────────────────────
    if _OS == "Darwin":
        data_dir = (
            Path.home() / "Library" / "Application Support" / machine_name / "data"
        )
    else:
        xdg_data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        data_dir = xdg_data / machine_name / "data"

    compose_file = data_dir / "compose.yml"
    if not compose_file.is_file():
        _die(
            f"compose.yml not found at {compose_file}\n"
            "  Run ./install.sh first to generate it."
        )

    # ── 3. Compose up (no eval — env passed as explicit dict) ─────────────────
    compose_env = _build_compose_env(dedicated, machine_name, podman_sock)
    _compose_up(compose_file, compose_env)

    # ── 4. Health check ───────────────────────────────────────────────────────
    scheme = "https" if tls_mode and tls_mode != "off" else "http"
    probe_url = _probe_base(host, port, scheme) + "/health"
    _health_check(probe_url)


# ---------------------------------------------------------------------------
# Helper: build compose environment dict
# ---------------------------------------------------------------------------

def _build_compose_env(dedicated: bool, machine_name: str, podman_sock: str) -> dict:
    """Return an explicit env dict for the compose subprocess.

    No string interpolation with shell eval. Every variable is a key in a
    plain Python dict passed to subprocess.run(env=...).
    """
    compose_env = dict(os.environ)

    if dedicated and _OS == "Linux":
        compose_env["CONTAINER_HOST"] = f"unix://{podman_sock}"
    elif dedicated and _OS == "Darwin":
        compose_env["CONTAINER_CONNECTION"] = machine_name

    podman_compose_bin = shutil.which("podman-compose") or "podman-compose"
    compose_env["PODMAN_COMPOSE_PROVIDER"] = podman_compose_bin

    return compose_env


# ---------------------------------------------------------------------------
# Helper: compose up
# ---------------------------------------------------------------------------

def _compose_up(compose_file: Path, compose_env: dict) -> None:
    """Bring the compose stack up.  No eval — subprocess list form only."""
    print("Starting ga-transport via compose...")
    result = subprocess.run(
        [
            "podman", "compose",
            "--project-name", "ga",
            "-f", str(compose_file),
            "up", "-d",
        ],
        env=compose_env,
    )
    if result.returncode != 0:
        _die(
            f"podman compose up failed (exit {result.returncode}).\n"
            "  Run: podman logs ga-transport --tail 20"
        )
    print("✓ ga-transport container started")


# ---------------------------------------------------------------------------
# Helper: health check
# ---------------------------------------------------------------------------

def _health_check(
    probe_url: str,
    *,
    max_retries: int = _HEALTH_MAX_RETRIES,
    interval: float = _HEALTH_RETRY_INTERVAL,
    urlopen=urllib.request.urlopen,
    sleep_fn=time.sleep,
) -> None:
    """Poll the portal /health endpoint until ready or timeout.

    Uses urllib.request — no curl, no fixed sleep before polling.
    The urlopen and sleep_fn parameters are injectable for unit testing.
    """
    ready = False
    for _ in range(max_retries):
        try:
            urlopen(probe_url, timeout=5)
            ready = True
            break
        except Exception:
            sleep_fn(interval)

    if ready:
        print(f"✓ ga-transport is ready ({probe_url})")
    else:
        _die(
            f"ga-transport did not become ready through ga-portal within "
            f"{max_retries * interval:.0f}s ({probe_url})\n"
            "  Run: podman logs ga-transport --tail 10\n"
            "  Run: podman logs ga-portal --tail 10"
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
