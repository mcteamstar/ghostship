#!/usr/bin/env python3
"""Patch the ``model`` field of every agent JSON to a fixed value.

Runs inside a crew container via
``python3 /scripts/patch_models.py <agents_dir> <model>``.

Args (argv):
    1. agents_dir — directory holding the agent ``*.json`` files
    2. model      — the model value to write

Skips ``._`` AppleDouble files and any agent already set to the target
model, ``auto``, or with no explicit model. Prints ``patched: [names]``.
"""
from __future__ import annotations

import json
import pathlib
import sys


def patch_models(agents_dir: str, model: str) -> list[str]:
    """Set ``model`` on eligible agent JSONs. Returns the patched names."""
    d = pathlib.Path(agents_dir)
    patched: list[str] = []
    for p in d.glob("*.json"):
        if not p.exists() or p.name.startswith("._"):
            continue
        data = json.loads(p.read_text())
        if data.get("model") in (model, "auto", None):
            continue
        p.write_text(json.dumps({**data, "model": model}, indent=2))
        patched.append(p.name)
    return patched


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: patch_models.py <agents_dir> <model>", file=sys.stderr)
        return 2
    patched = patch_models(argv[1], argv[2])
    print("patched:", patched)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
