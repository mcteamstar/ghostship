#!/usr/bin/env python3
"""Merge agent-config overrides into a crew's ``config.local.json``.

Runs inside a crew container via
``python3 /scripts/patch_crew_config.py <config_path> <b64_overrides>``.

Writes to ``config.local.json`` (user overrides that survive gateway
upgrades and restarts) rather than ``config.json`` (re-seeded on every
start). The gateway deep-merges ``config.local.json`` over ``config.json``
on every load, so these overrides are permanent without re-patching.

Creating the parent directory here means the patch does not depend on the
gateway having seeded the config files already.

Args (argv):
    1. config_path   — path to config.local.json
    2. b64_overrides — base64-encoded JSON object merged into ``cfg['agent']``

The overrides are passed base64-encoded via argv because the transport's
exec API is stdout-only (no stdin) and to avoid any inline string
construction.

Prints ``patched config.local.json``.
"""
from __future__ import annotations

import base64
import json
import pathlib
import sys


def patch_config(config_path: str, agent_overrides: dict) -> None:
    """Deep-merge ``agent_overrides`` into ``config['agent']`` and write it."""
    p = pathlib.Path(config_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(p.read_text()) if p.exists() else {}
    agent = cfg.setdefault("agent", {})
    agent.update(agent_overrides)
    p.write_text(json.dumps(cfg, indent=2))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: patch_crew_config.py <config_path> <b64_overrides>",
            file=sys.stderr,
        )
        return 2
    overrides = json.loads(base64.b64decode(argv[2]).decode())
    patch_config(argv[1], overrides)
    print("patched config.local.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
