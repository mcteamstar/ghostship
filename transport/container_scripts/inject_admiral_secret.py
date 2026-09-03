#!/usr/bin/env python3
"""Write the admiral signing secret to a file with fsync.

Runs inside a crew container via
``python3 /scripts/inject_admiral_secret.py <path>``.

The secret is read from stdin (``sys.stdin.read().strip()``) so it never
appears in ``podman exec`` argument lists or ``/proc/<pid>/cmdline``.

The secret must be on the home volume before the post-restart gateway
starts, so the write is fsync'd before returning.

Args (argv):
    1. path — destination file (e.g. /home/kirocrew/.kiro/crew/.admiral_secret)

Stdin:
    The secret string to write (trailing whitespace is stripped).

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


def inject_admiral_secret(dest: str, stdin_secret: str) -> None:
    """Public API: write ``stdin_secret`` to ``dest`` (mode 0600) and fsync."""
    inject_secret(dest, stdin_secret)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: inject_admiral_secret.py <path>", file=sys.stderr)
        return 2
    secret = sys.stdin.read().strip()
    inject_admiral_secret(argv[1], secret)
    print("admiral secret injected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
