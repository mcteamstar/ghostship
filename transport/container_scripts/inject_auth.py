#!/usr/bin/env python3
"""Inject kiro-cli auth rows into a crew container's SQLite DB.

Runs inside a crew container via
``python3 /scripts/inject_auth.py <db_path>``, where the payload
(a base64-encoded JSON list of ``[key, value]`` pairs) is written to the
process's stdin by the caller.

Reading the payload via stdin rather than argv ensures the auth credential
never appears in ``/proc/<pid>/cmdline`` (secret-delivery-hardening spec,
TRN-269).

The DB schema and migrations are pre-seeded in the crew image, so kiro-cli
finds them already applied — direct INSERT, no migration wait needed.

Args (argv):
    1. db_path — path to the kiro-cli SQLite DB

Stdin:
    base64-encoded JSON list of [key, value] pairs

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
    if len(argv) != 2:
        print("usage: inject_auth.py <db_path>  (payload on stdin)", file=sys.stderr)
        return 2
    b64_rows = sys.stdin.read().strip()
    count = inject_auth(argv[1], b64_rows)
    print(f"injected {count} auth rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
