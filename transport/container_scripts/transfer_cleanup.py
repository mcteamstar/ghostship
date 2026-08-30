#!/usr/bin/env python3
"""Remove a transfer staging directory.

Runs inside a crew container via ``python3 /scripts/transfer_cleanup.py``,
reading the staging path from the environment (as the inline
``_CLEANUP_TRANSFER_SCRIPT`` did):

    GA_TRANSFER_STAGE — the staging directory to remove

Best-effort: a missing directory is not an error.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys


def cleanup(stage: str) -> None:
    """Recursively remove ``stage``, ignoring errors."""
    shutil.rmtree(pathlib.Path(stage), ignore_errors=True)


def main() -> int:
    cleanup(os.environ["GA_TRANSFER_STAGE"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
