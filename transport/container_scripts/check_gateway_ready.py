#!/usr/bin/env python3
"""Check whether the gateway has seeded its built-in agent files.

Runs inside a crew container via
``python3 /scripts/check_gateway_ready.py <agents_dir>``.

Args (argv):
    1. agents_dir — directory the gateway seeds kirocrew*.json into

Prints ``ready`` and exits 0 when at least one ``kirocrew*.json`` file is
present; prints ``wait`` and exits 1 otherwise. The caller polls this.
"""
from __future__ import annotations

import pathlib
import sys


def is_ready(agents_dir: str) -> bool:
    """True if any ``kirocrew*.json`` file exists in ``agents_dir``."""
    return any(pathlib.Path(agents_dir).glob("kirocrew*.json"))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_gateway_ready.py <agents_dir>", file=sys.stderr)
        return 2
    if is_ready(argv[1]):
        print("ready")
        return 0
    print("wait")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
