#!/usr/bin/env python3
"""Write one base64-encoded steering doc into the crew's steering dir.

Runs inside a crew container via
``python3 /scripts/copy_steering.py <steering_dir> <dest_name> <b64_content>``.

Args (argv):
    1. steering_dir — the ~/.kiro/steering directory (created if absent)
    2. dest_name    — the file name to write within steering_dir
    3. b64_content  — base64-encoded file bytes

Passing the content base64-encoded via argv (rather than interpolating a
path/blob into an inline ``-c`` string) removes the shell-quoting hazard
the inline version worked around. Prints ``wrote <dest_name>``.
"""
from __future__ import annotations

import base64
import pathlib
import sys


def copy_steering(steering_dir: str, dest_name: str, b64_content: str) -> None:
    """Write decoded ``b64_content`` to ``steering_dir/dest_name``."""
    d = pathlib.Path(steering_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / dest_name).write_bytes(base64.b64decode(b64_content))


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(
            "usage: copy_steering.py <steering_dir> <dest_name> <b64_content>",
            file=sys.stderr,
        )
        return 2
    copy_steering(argv[1], argv[2], argv[3])
    print(f"wrote {argv[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
