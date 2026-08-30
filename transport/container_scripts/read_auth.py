#!/usr/bin/env python3
"""Read auth_kv rows from a crew container's kiro-cli DB as base64 JSON.

Runs inside a crew container via ``python3 /scripts/read_auth.py <db_path>``.

Args (argv):
    1. db_path — path to the kiro-cli SQLite DB

Prints a base64-encoded JSON list of [key, value] pairs. Prints an empty
line when there are no rows so the caller can treat it as "no auth".
"""
from __future__ import annotations

import base64
import json
import sqlite3
import sys


def read_auth(db_path: str) -> str:
    """Return auth_kv rows as base64-encoded JSON, or "" when empty."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT key, value FROM auth_kv").fetchall()
    finally:
        conn.close()
    if not rows:
        return ""
    return base64.b64encode(json.dumps(rows).encode()).decode()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: read_auth.py <db_path>", file=sys.stderr)
        return 2
    print(read_auth(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
