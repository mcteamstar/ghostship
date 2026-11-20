#!/usr/bin/env python3
"""Remove a staged upload without following paths outside its workspace."""
from __future__ import annotations

import os

from transfer_paths import open_workspace, remove_tree


def cleanup(stage: str, workspace: str) -> None:
    root_fd = open_workspace(workspace)
    try:
        remove_tree(root_fd, workspace, stage)
    finally:
        os.close(root_fd)


def main() -> int:
    cleanup(os.environ["GA_TRANSFER_STAGE"], os.environ["GA_TRANSFER_WORKSPACE"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
