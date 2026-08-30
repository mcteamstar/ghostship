#!/usr/bin/env python3
"""Delete all auth_kv rows from a crew container's kiro-cli DB.

Runs inside a crew container via ``python3 /scripts/wipe_auth.py <db_path>``.

Args (argv):
    1. db_path — path to the kiro-cli SQLite DB

Prints ``auth_kv cleared`` on success.
"""
from __future__ import annotations

import sqlite3
import sys


def wipe_auth(db_path: str) -> None:
    """Delete every row from ``auth_kv``."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM auth_kv")
        conn.commit()
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: wipe_auth.py <db_path>", file=sys.stderr)
        return 2
    wipe_auth(argv[1])
    print("auth_kv cleared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
