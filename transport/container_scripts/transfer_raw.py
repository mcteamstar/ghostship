#!/usr/bin/env python3
"""Write (or unpack) a staged upload into its destination, then clean up.

Runs inside a crew container via ``python3 /scripts/transfer_raw.py``, with
the source, destination, and staging paths supplied through the
environment (as the inline ``_RAW_TRANSFER_SCRIPT`` / ``_ARCHIVE_TRANSFER_SCRIPT``
did):

    GA_TRANSFER_SOURCE — the staged payload file
    GA_TRANSFER_DEST   — the final destination path
    GA_TRANSFER_STAGE  — the staging directory to remove afterwards

Pass ``--unpack`` (argv) to treat the source as a tar archive and extract
it into the destination directory; otherwise the source is streamed to the
destination as a regular file. The staging directory is always removed,
success or failure. Prints a short status line.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tarfile


def transfer(source: str, destination: str, stage: str, unpack: bool) -> str:
    """Copy/extract ``source`` to ``destination``, removing ``stage`` after."""
    src = pathlib.Path(source)
    dest = pathlib.Path(destination)
    stage_path = pathlib.Path(stage)
    try:
        if unpack:
            dest.mkdir(parents=True, exist_ok=True)
            with tarfile.open(src, mode="r|*") as archive:
                archive.extractall(dest, filter="data")
            return f"unpacked to {dest}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with src.open("rb") as sf, dest.open("wb") as df:
            while True:
                chunk = sf.read(1024 * 1024)
                if not chunk:
                    break
                df.write(chunk)
                count += len(chunk)
        return f"wrote {count} bytes to {dest}"
    finally:
        shutil.rmtree(stage_path, ignore_errors=True)


def main(argv: list[str]) -> int:
    unpack = "--unpack" in argv[1:]
    result = transfer(
        os.environ["GA_TRANSFER_SOURCE"],
        os.environ["GA_TRANSFER_DEST"],
        os.environ["GA_TRANSFER_STAGE"],
        unpack,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
