#!/usr/bin/env python3
"""ghostship setup — register the MCP server and install skill symlinks for agent clients.

Supports: kiro-cli, Claude Code, opencode.
Idempotent: safe to re-run.

Usage:
    ghostship setup [--agent kiro|claude|opencode|all] [--url <url>] [--api-key <key>]
    ./scripts/setup.py [same flags]
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ghostship_dir() -> pathlib.Path:
    """Repo root — one level up from this script (scripts/)."""
    return pathlib.Path(__file__).resolve().parent.parent


_DEFAULT_URL = "http://localhost:64057/mcp"
_SKILLS = ["ghostship-command", "ghostship-admin", "ghostship-capability"]


def _skills_source_dir() -> pathlib.Path:
    return _ghostship_dir() / ".claude-plugin" / "skills"


def _wire_skills(client_skills_dir: pathlib.Path, label: str) -> None:
    """Create symlinks in client_skills_dir for the three ghostship skills."""
    source = _skills_source_dir()
    client_skills_dir.mkdir(parents=True, exist_ok=True)
    for skill in _SKILLS:
        target = source / skill
        link = client_skills_dir / skill
        if link.is_symlink():
            if link.resolve() == target.resolve():
                continue  # already correct
            print(f"  [{label}] note: {skill} symlink target changed — updating")
            link.unlink()
        elif link.exists():
            print(f"  [{label}] skip: {skill} already exists at {link} (not a symlink)")
            continue
        link.symlink_to(target)
        print(f"  [{label}] ✓ skill symlink: {link} → {target}")


def _write_json_atomic(cfg_path: pathlib.Path, config: dict, label: str) -> bool:
    """Write config to cfg_path atomically. Returns True on success."""
    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=cfg_path.parent, prefix=".ghostship-setup-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(config, fh, indent=2)
                fh.write("\n")
            os.replace(tmp_path, cfg_path)
            return True
        except Exception:
            os.unlink(tmp_path)
            raise
    except OSError as exc:
        print(f"  [{label}] error: could not write {cfg_path}: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# kiro-cli
# ---------------------------------------------------------------------------

def _setup_kiro(url: str, api_key: str) -> bool:
    if not shutil.which("kiro-cli"):
        return False

    print("[kiro] kiro-cli detected")

    add_cmd = [
        "kiro-cli", "mcp", "add",
        "--name", "ghostship",
        "--url", url,
        "--scope", "global",
        "--force",
    ]
    result = subprocess.run(add_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[kiro]   error: {result.stderr.strip()}", file=sys.stderr)
        return True

    print(f"[kiro] ✓ MCP server registered: {url}")

    if api_key:
        cfg_path = pathlib.Path.home() / ".kiro" / "settings" / "mcp.json"
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
            config.setdefault("mcpServers", {}).setdefault("ghostship", {})
            config["mcpServers"]["ghostship"]["headers"] = {
                "Authorization": f"Bearer {api_key}"
            }
            _write_json_atomic(cfg_path, config, "kiro")
            print(f"[kiro]   ✓ Authorization header written")
        except OSError as exc:
            print(f"[kiro]   warning: could not write api-key header: {exc}")

    _wire_skills(pathlib.Path.home() / ".kiro" / "skills", "kiro")
    return True


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------

def _find_claude_config() -> pathlib.Path:
    for p in [
        pathlib.Path.home() / ".claude.json",
        pathlib.Path.home() / ".config" / "claude" / "claude.json",
    ]:
        if p.exists():
            return p
    return pathlib.Path.home() / ".claude.json"


def _setup_claude(url: str, api_key: str, force: bool = False) -> bool:
    if not force and not shutil.which("claude"):
        return False

    cfg_path = _find_claude_config()
    if not force and not cfg_path.exists():
        return False

    print("[claude] Claude Code detected")

    config: dict = {}
    if cfg_path.exists():
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[claude]   error: could not read {cfg_path}: {exc}", file=sys.stderr)
            return True

    entry: dict = {"type": "http", "url": url}
    if api_key:
        entry["headers"] = {"Authorization": f"Bearer {api_key}"}

    config.setdefault("mcpServers", {})["ghostship"] = entry

    if _write_json_atomic(cfg_path, config, "claude"):
        print(f"[claude] ✓ MCP server registered in {cfg_path}: {url}")

    _wire_skills(pathlib.Path.home() / ".claude" / "skills", "claude")
    return True


# ---------------------------------------------------------------------------
# opencode
# ---------------------------------------------------------------------------

def _setup_opencode(url: str, api_key: str, force: bool = False) -> bool:
    if not force and not shutil.which("opencode"):
        return False

    cfg_path = pathlib.Path.home() / ".config" / "opencode" / "opencode.json"
    print("[opencode] opencode detected")

    config: dict = {}
    if cfg_path.exists():
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[opencode]   error: could not read {cfg_path}: {exc}", file=sys.stderr)
            return True

    entry: dict = {"type": "http", "url": url}
    if api_key:
        entry["headers"] = {"Authorization": f"Bearer {api_key}"}

    config.setdefault("mcp", {})["ghostship"] = entry

    if _write_json_atomic(cfg_path, config, "opencode"):
        print(f"[opencode] ✓ MCP server registered in {cfg_path}: {url}")

    # opencode has no skills directory — uses instructions globs in config
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    agent = None
    url = _DEFAULT_URL
    api_key = ""

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--help", "-h"):
            print(
                "Usage: ghostship setup [--agent kiro|claude|opencode|all] "
                "[--url <url>] [--api-key <key>]\n"
                "\n"
                "  --agent   Target agent: kiro, claude, opencode, or all.\n"
                "            Default: auto-detect installed agents.\n"
                "  --url     MCP server URL (default: http://localhost:64057/mcp)\n"
                "  --api-key Bearer token for the MCP endpoint (optional)\n"
            )
            return 0
        elif a == "--agent":
            if i + 1 >= len(args):
                print("error: --agent requires a value (kiro, claude, opencode, all)",
                      file=sys.stderr)
                return 1
            agent = args[i + 1]
            if agent not in ("kiro", "claude", "opencode", "all"):
                print(f"error: unknown --agent '{agent}' (use kiro, claude, opencode, or all)",
                      file=sys.stderr)
                return 1
            i += 2
        elif a == "--url":
            if i + 1 >= len(args):
                print("error: --url requires a value", file=sys.stderr)
                return 1
            url = args[i + 1]
            i += 2
        elif a == "--api-key":
            if i + 1 >= len(args):
                print("error: --api-key requires a value", file=sys.stderr)
                return 1
            api_key = args[i + 1]
            i += 2
        else:
            print(f"error: unknown flag '{a}'", file=sys.stderr)
            return 1

    print(f"ghostship setup — url: {url}")
    if api_key:
        print("  api-key: (set)")

    wired_any = False

    if agent is None:
        # Auto-detect all installed agents
        wired_any = _setup_kiro(url, api_key) or wired_any
        wired_any = _setup_claude(url, api_key) or wired_any
        wired_any = _setup_opencode(url, api_key) or wired_any
    elif agent == "all":
        for fn, label in [
            (_setup_kiro, "kiro-cli"),
            (lambda u, k: _setup_claude(u, k, force=True), "claude"),
            (lambda u, k: _setup_opencode(u, k, force=True), "opencode"),
        ]:
            if not fn(url, api_key):
                print(f"[{label}]   not found on PATH — skipping")
        wired_any = True
    elif agent == "kiro":
        wired_any = _setup_kiro(url, api_key)
        if not wired_any:
            print("[kiro]   kiro-cli not found on PATH")
    elif agent == "claude":
        wired_any = _setup_claude(url, api_key, force=True)
    elif agent == "opencode":
        wired_any = _setup_opencode(url, api_key, force=True)
        if not wired_any:
            print("[opencode]   opencode not found on PATH")

    if not wired_any and agent is None:
        print("No supported agent client found (kiro-cli, Claude Code, or opencode).")
        print("Re-run with --agent kiro, --agent claude, or --agent opencode to force.")
        return 0

    if wired_any:
        print("\nghostship setup complete.")
        print("  If symlinks break after moving the repo, re-run 'ghostship setup'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
