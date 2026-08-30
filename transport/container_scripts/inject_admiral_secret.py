#!/usr/bin/env python3
"""Write the admiral signing secret to a file with fsync.

Runs inside a crew container via
``python3 /scripts/inject_admiral_secret.py <path> <secret>``.

The secret must be on the home volume before the post-restart gateway
starts, so the write is fsync'd before returning.

Args (argv):
    1. path   — destination file (e.g. /home/kirocrew/.kiro/crew/.admiral_secret)
    2. secret — the secret string to write

The file is created with mode 0600. Prints ``admiral secret injected``.
"""
from __future__ import annotations

import os
import pathlib
import sys


def inject_secret(path: str, secret: str) -> None:
    """Write ``secret`` to ``path`` (mode 0600) and fsync it to disk."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, secret.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: inject_admiral_secret.py <path> <secret>", file=sys.stderr)
        return 2
    inject_secret(argv[1], argv[2])
    print("admiral secret injected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
