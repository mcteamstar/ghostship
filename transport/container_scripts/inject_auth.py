#!/usr/bin/env python3
"""Inject kiro-cli auth rows into a crew container's SQLite DB.

Runs inside a crew container via ``python3 /scripts/inject_auth.py <db_path> <b64_rows>``.

The DB schema and migrations are pre-seeded in the crew image, so kiro-cli
finds them already applied — direct INSERT, no migration wait needed.

Args (argv):
    1. db_path  — path to the kiro-cli SQLite DB
    2. b64_rows — base64-encoded JSON list of [key, value] pairs

Prints ``injected <N> auth rows`` on success.
"""
from __future__ import annotations

import base64
import json
import sqlite3
import sys


def inject_auth(db_path: str, b64_rows: str) -> int:
    """Insert (key, value) auth rows into ``auth_kv``. Returns the row count."""
    rows = json.loads(base64.b64decode(b64_rows).decode())
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO auth_kv (key, value) VALUES (?, ?)", rows
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: inject_auth.py <db_path> <b64_rows>", file=sys.stderr)
        return 2
    count = inject_auth(argv[1], argv[2])
    print(f"injected {count} auth rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
