#!/usr/bin/env python3
"""uninstall_ops.py — Python helper for bin/uninstall.sh.

Resolves config via yaml_config (no eval), then emits shell-safe
KEY=value lines for the two vars uninstall.sh needs:
    GA_MACHINE_NAME, GA_DEDICATED_MACHINE

Usage:
    python3 bin/lib/uninstall_ops.py [--config <path>]
"""
from __future__ import annotations

import argparse
import os
import platform
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_VENDOR = _THIS_DIR / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import yaml_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="", help="Explicit config file path")
    parser.add_argument("--ghostship-dir", default="", dest="ghostship_dir")
    args = parser.parse_args()

    ghostship_dir = args.ghostship_dir or str(_THIS_DIR.parent.parent)
    os_name = platform.system()

    if os_name == "Darwin":
        xdg_yaml = str(Path.home() / "Library" / "Application Support" / "ghost-academy" / "ghostship.yaml")
    else:
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        xdg_yaml = str(xdg_config / "ghost-academy" / "ghostship.yaml")

    repo_yaml = str(Path(ghostship_dir) / "config" / "ghostship.yaml")

    if args.config:
        merged = yaml_config.resolve_config(
            repo_path="", xdg_path="", explicit_path=args.config
        )
    else:
        merged = yaml_config.resolve_config(
            repo_path=repo_yaml, xdg_path=xdg_yaml, explicit_path=None
        )

    cfg = yaml_config.flatten_to_env(merged)
    machine_name = cfg.get("GA_MACHINE_NAME", "ghost-academy")
    dedicated = cfg.get("GA_DEDICATED_MACHINE", "true")

    print(f"GA_MACHINE_NAME={machine_name}")
    print(f"GA_DEDICATED_MACHINE={dedicated}")


if __name__ == "__main__":
    main()
