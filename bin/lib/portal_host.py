#!/usr/bin/env python3
"""portal_host.py — Python port of bin/lib/portal_host.sh.

Implements the same functions as the shell file; loopback detection
delegates to yaml_config.py (same logic transport/config.py uses) so
install-time and runtime behaviour agree.

Functions:
    is_loopback(host)               — True when host is a loopback address
    is_wildcard(host)               — True when host binds every interface
    addr(host)                      — IPv6 literals bracketed
    public_base(host, port)         — default public base URL
    probe_base(host, port, scheme)  — readiness-probe base URL
    resolve_api_key(data_dir, ...)  — resolve/persist the endpoint API key
    check_exposure(host, port, ...)  — refuse unauthenticated non-loopback
    legacy_bind_notice(compose_path, host, port) — warn on bind change
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_YAML_CONFIG = _THIS_DIR / "yaml_config.py"
_VENDOR = _THIS_DIR / "vendor"


# ---------------------------------------------------------------------------
# is_loopback
# ---------------------------------------------------------------------------

def is_loopback(host: str) -> bool:
    """True when host is a loopback address (empty, localhost, ::1, 127.x)."""
    result = subprocess.run(
        [sys.executable, str(_YAML_CONFIG), "is-loopback", host or ""],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(_VENDOR)},
    )
    return result.stdout.strip() == "true"


# ---------------------------------------------------------------------------
# is_wildcard
# ---------------------------------------------------------------------------

def is_wildcard(host: str) -> bool:
    """True when host binds every interface (0.0.0.0, ::, [::])."""
    return (host or "") in ("0.0.0.0", "::", "[::]")


# ---------------------------------------------------------------------------
# addr
# ---------------------------------------------------------------------------

def addr(host: str) -> str:
    """Return host in URL/port-mapping form; IPv6 literals are bracketed."""
    h = host or "127.0.0.1"
    if ":" in h and not h.startswith("["):
        return f"[{h}]"
    return h


# ---------------------------------------------------------------------------
# public_base
# ---------------------------------------------------------------------------

def public_base(host: str, port: str) -> str:
    """Return the default public base URL.

    Loopback and wildcard → localhost. Otherwise the host itself.
    """
    if not host or is_wildcard(host) or is_loopback(host):
        return f"http://localhost:{port}"
    return f"http://{addr(host)}:{port}"


# ---------------------------------------------------------------------------
# probe_base
# ---------------------------------------------------------------------------

def probe_base(host: str, port: str, scheme: str = "http") -> str:
    """Return the base URL readiness probes use to reach the portal.

    Wildcard or empty → 127.0.0.1 (probed from the same host, not in-VM).
    """
    h = host or ""
    if not h or is_wildcard(h):
        h = "127.0.0.1"
    return f"{scheme}://{addr(h)}:{port}"


# ---------------------------------------------------------------------------
# resolve_api_key
# ---------------------------------------------------------------------------

def resolve_api_key(
    data_dir: str,
    *,
    api_key_flag_passed: bool = False,
    flag_api_key: str = "",
    ga_api_key: str = "",
    ga_api_key_disabled: str = "",
    ga_api_key_source: str = "",
    ga_api_key_deprecated_off: str = "",
) -> dict:
    """Resolve and persist the endpoint API key.

    Returns a dict with keys: ga_api_key, ga_api_key_disabled.
    Side effects: writes/removes DATA_DIR/ga-api-key and ga-api-key.flag.

    Resolution order mirrors portal_resolve_api_key() in portal_host.sh:
    1. --api-key flag (api_key_flag_passed + flag_api_key)
    2. network.api_key in YAML  (ga_api_key_source == "yaml")
    3. saved flag key           (DATA_DIR/ga-api-key.flag)
    """
    data = Path(data_dir)
    flag_file = data / "ga-api-key.flag"
    effective_file = data / "ga-api-key"

    # One-time migration: before portal-only-host, ga-api-key was written only
    # by --api-key. The .flag file always exists afterwards.
    if not flag_file.exists():
        if effective_file.is_file() and effective_file.stat().st_size > 0:
            _write_secret(flag_file, effective_file.read_text(encoding="utf-8"))
        else:
            _write_secret(flag_file, "")

    # Apply --api-key flag
    if api_key_flag_passed:
        _write_secret(flag_file, flag_api_key)
        if flag_api_key:
            print(f"✓ API key from --api-key saved to {flag_file} (reused on future installs)")
        else:
            print("✓ Saved --api-key cleared")

    # Resolve effective key
    result_key = ""
    result_disabled = ""

    if api_key_flag_passed and flag_api_key:
        result_key = flag_api_key
    elif ga_api_key_source == "yaml":
        result_key = ga_api_key
        result_disabled = ga_api_key_disabled
    elif flag_file.is_file() and flag_file.stat().st_size > 0:
        result_key = flag_file.read_text(encoding="utf-8")
        print(f"✓ API key restored from {flag_file}")
    else:
        result_key = ""

    # Deprecated network.require_api_key: off
    if not result_key and ga_api_key_deprecated_off == "true":
        result_disabled = "true"

    # Write or remove effective key file
    if result_key:
        _write_secret(effective_file, result_key)
    else:
        effective_file.unlink(missing_ok=True)

    return {"ga_api_key": result_key, "ga_api_key_disabled": result_disabled}


def _write_secret(path: Path, content: str) -> None:
    """Write content to path with mode 0o600, atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


# ---------------------------------------------------------------------------
# check_exposure
# ---------------------------------------------------------------------------

def check_exposure(
    host: str,
    port: str,
    ga_api_key: str = "",
    ga_api_key_disabled: str = "",
) -> None:
    """Refuse to publish an unauthenticated portal beyond loopback.

    Exits 1 unless:
    - host is loopback
    - ga_api_key is set
    - ga_api_key_disabled == "true" (explicit opt-out, warns instead)
    """
    if is_loopback(host):
        return
    if ga_api_key:
        return

    where = f"{addr(host)}:{port}"
    if ga_api_key_disabled == "true":
        print(
            f"WARNING: ga-portal is published on {where} with authentication"
            " explicitly disabled (network.api_key: false) — anyone who can"
            " reach that address can use every MCP tool.",
            file=sys.stderr,
        )
        return

    print(
        f"WARNING: ga-portal would be published on {where} with no API key"
        " — anyone who can reach that address could use every MCP tool.\n"
        "Aborting. Fix one of:\n"
        f"  - set an API key: --api-key <key>, or network.api_key in config/ghostship.yaml\n"
        f"  - keep it local: network.host: 127.0.0.1\n"
        f"  - accept unauthenticated access (e.g. behind your own auth proxy):"
        f" network.api_key: false",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# legacy_bind_notice
# ---------------------------------------------------------------------------

def legacy_bind_notice(compose_path: str, host: str, port: str) -> None:
    """Warn when an existing compose.yml published ga-portal on all interfaces
    but HOST now keeps it on loopback (the HOST default changed)."""
    p = Path(compose_path)
    if not p.is_file():
        return
    if not is_loopback(host):
        return
    content = p.read_text(encoding="utf-8")
    if f'"0.0.0.0:{port}:' not in content:
        return
    print(
        f"ℹ ga-portal was published on all interfaces (0.0.0.0:{port});"
        f" it is now loopback-only ({host or '127.0.0.1'}).",
        file=sys.stderr,
    )
    print(
        "  HOST now defaults to 127.0.0.1. For remote access set network.host"
        " in config/ghostship.yaml",
        file=sys.stderr,
    )
    print(
        "  (plus network.api_key, or network.api_key: false to opt out of"
        " authentication).",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(f"Usage: {sys.argv[0]} <command> [args...]", file=sys.stderr)
        sys.exit(1)

    cmd = args[0]

    if cmd == "is_loopback":
        host = args[1] if len(args) > 1 else ""
        print("true" if is_loopback(host) else "false")

    elif cmd == "is_wildcard":
        host = args[1] if len(args) > 1 else ""
        print("true" if is_wildcard(host) else "false")

    elif cmd == "addr":
        host = args[1] if len(args) > 1 else ""
        sys.stdout.write(addr(host))

    elif cmd == "public_base":
        host = args[1] if len(args) > 1 else ""
        port = args[2] if len(args) > 2 else "64057"
        sys.stdout.write(public_base(host, port))

    elif cmd == "probe_base":
        host = args[1] if len(args) > 1 else ""
        port = args[2] if len(args) > 2 else "64057"
        scheme = args[3] if len(args) > 3 else "http"
        sys.stdout.write(probe_base(host, port, scheme))

    elif cmd == "check_exposure":
        host = args[1] if len(args) > 1 else ""
        port = args[2] if len(args) > 2 else "64057"
        ga_api_key = os.environ.get("GA_API_KEY", "")
        ga_api_key_disabled = os.environ.get("GA_API_KEY_DISABLED", "")
        check_exposure(host, port, ga_api_key, ga_api_key_disabled)

    elif cmd == "legacy_bind_notice":
        compose_path = args[1] if len(args) > 1 else ""
        host = args[2] if len(args) > 2 else ""
        port = args[3] if len(args) > 3 else "64057"
        legacy_bind_notice(compose_path, host, port)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
