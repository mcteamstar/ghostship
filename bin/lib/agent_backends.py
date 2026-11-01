#!/usr/bin/env python3
"""agent_backends.py — Python port of bin/lib/agent_backends.sh.

Implements the same functions as the shell file; semantics are identical
so tests/unit/test_agent_backends_parity.py can drive both in parallel.

Functions:
    normalise(raw)        — normalise a comma-separated backend list
    available(dir)        — list available toolchain scripts
    validate(list_str, dir) — validate normalised list against toolchains
    check_default(default, list_str, dir) — ensure default is kiro or enabled
    reject_retired(env)   — fail on deprecated GA_INCLUDE_*_AGENT flags

CLI usage (matches shell wrapper for sourced callers):
    python3 bin/lib/agent_backends.py normalise <raw>
    python3 bin/lib/agent_backends.py available <dir>
    python3 bin/lib/agent_backends.py validate <list> <dir>
    python3 bin/lib/agent_backends.py check_default <default> <list> [<dir>]
    python3 bin/lib/agent_backends.py reject_retired
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# normalise
# ---------------------------------------------------------------------------

def normalise(raw: str) -> str:
    """Return a normalised comma-separated backend list.

    Rules (matching agent_backends_normalise in .sh):
    - Split on commas, trim, lowercase each entry.
    - Drop empty entries and 'kiro' (always enabled).
    - Drop duplicates (first occurrence wins).
    - Reject multi-line input (newline/carriage-return in raw).
    - Return empty string when nothing remains.
    """
    if "\n" in raw or "\r" in raw:
        print(
            "✗ GA_AGENT_BACKENDS must be a single line (found a line break).",
            file=sys.stderr,
        )
        sys.exit(1)

    parts = raw.split(",")
    seen: list[str] = []
    for part in parts:
        name = part.strip().lower()
        if not name or name == "kiro":
            continue
        if name not in seen:
            seen.append(name)
    return ",".join(seen)


# ---------------------------------------------------------------------------
# available
# ---------------------------------------------------------------------------

def available(toolchains_dir: str) -> str:
    """Return comma-separated basenames of .sh scripts in toolchains_dir."""
    d = Path(toolchains_dir)
    if not d.is_dir():
        return ""
    scripts = sorted(p.stem for p in d.glob("*.sh") if p.is_file())
    return ",".join(scripts)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def validate(list_str: str, toolchains_dir: str) -> None:
    """Validate a normalised backend list against toolchain scripts.

    Names must match ^[a-z][a-z0-9-]*$ and exist as a script in
    toolchains_dir. Exits 1 on first invalid name.
    """
    avail = available(toolchains_dir)
    avail_set = set(avail.split(",")) if avail else set()

    names = [n for n in list_str.split(",") if n]
    for name in names:
        if not re.match(r"^[a-z][a-z0-9-]*$", name) or name not in avail_set:
            avail_display = f"kiro{(',' + avail) if avail else ''}"
            print(
                f"✗ GA_AGENT_BACKENDS contains unknown backend '{name}'."
                f" Available: {avail_display}.",
                file=sys.stderr,
            )
            sys.exit(1)


# ---------------------------------------------------------------------------
# check_default
# ---------------------------------------------------------------------------

def check_default(
    default: str, list_str: str, toolchains_dir: str = ""
) -> None:
    """Ensure the default backend is 'kiro' or a member of list_str.

    Trims/lowercases default; empty default falls back to 'kiro'. Exits 1
    when the default is neither kiro nor in the enabled list.
    """
    d = default.strip().lower() if default else ""
    if not d:
        d = "kiro"

    if d == "kiro":
        return

    enabled = set(list_str.split(",")) if list_str else set()
    if d in enabled:
        return

    if toolchains_dir:
        avail = available(toolchains_dir)
        avail_set = set(avail.split(",")) if avail else set()
        if d not in avail_set:
            avail_display = f"kiro{(',' + avail) if avail else ''}"
            print(
                f"✗ GA_CREW_ACP_BACKEND='{d}' is not a known backend."
                f" Valid: {avail_display}.",
                file=sys.stderr,
            )
            sys.exit(1)

    enabled_display = f"kiro{(',' + list_str) if list_str else ''}"
    print(
        f"✗ GA_CREW_ACP_BACKEND='{d}' is not enabled."
        f" Add it to GA_AGENT_BACKENDS (enabled: {enabled_display}),"
        f" then re-run ghostship install.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# reject_retired
# ---------------------------------------------------------------------------

_RETIRED_VARS = ("GA_INCLUDE_CLAUDE_AGENT", "GA_INCLUDE_CODEX_AGENT")


def reject_retired(env: dict) -> None:
    """Fail on any non-empty GA_INCLUDE_*_AGENT flag in env."""
    for name in _RETIRED_VARS:
        if env.get(name):
            print(
                f"✗ {name} is retired."
                " Enable backends with GA_AGENT_BACKENDS"
                " (for example GA_AGENT_BACKENDS=claude) instead.",
                file=sys.stderr,
            )
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(f"Usage: {sys.argv[0]} <command> [args...]", file=sys.stderr)
        sys.exit(1)

    cmd = args[0]

    if cmd == "normalise":
        raw = args[1] if len(args) > 1 else ""
        sys.stdout.write(normalise(raw))

    elif cmd == "available":
        d = args[1] if len(args) > 1 else "."
        sys.stdout.write(available(d))

    elif cmd == "validate":
        lst = args[1] if len(args) > 1 else ""
        d = args[2] if len(args) > 2 else "."
        validate(lst, d)

    elif cmd == "check_default":
        default = args[1] if len(args) > 1 else "kiro"
        lst = args[2] if len(args) > 2 else ""
        d = args[3] if len(args) > 3 else ""
        check_default(default, lst, d)

    elif cmd == "reject_retired":
        reject_retired(dict(os.environ))

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
