#!/usr/bin/env python3
"""wizard.py — Interactive setup wizard for Ghost Academy.

Replaces _interactive_setup() and the post-install auth block in
bin/install.sh. All terminal I/O is dependency-injected so tests can
supply canned answers without patching builtins.

Functions:
    interactive_setup(env, input_fn, print_fn) -> dict
    post_install_auth(env, ghostship_bin, input_fn, print_fn)

CLI usage:
    python3 bin/lib/wizard.py --mode setup --ghostship-dir <dir>
    python3 bin/lib/wizard.py --mode post-auth --ghostship-dir <dir>
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

_KNOWN_BACKENDS = ("kiro", "claude", "codex")


# ---------------------------------------------------------------------------
# interactive_setup
# ---------------------------------------------------------------------------

def interactive_setup(
    env: dict,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[..., None] = print,
) -> dict:
    """Walk the operator through backend selection and non-secret config.

    Returns a dict with the resolved values:
        ga_crew_agent, kiro_identity_provider, kiro_region,
        openai_base_url, wrote_config (bool).
    """
    print_fn("=== Ghostship Interactive Setup ===")

    ghostship_dir = env.get("GHOSTSHIP_DIR", "")

    # 1. Default backend — validate, re-prompt on unknown.
    while True:
        raw = _prompt(
            "Default agent backend (kiro/claude/codex)", "kiro",
            input_fn=input_fn, print_fn=print_fn,
        )
        if raw in _KNOWN_BACKENDS:
            ga_crew_agent = raw
            break
        print_fn(f"  Unknown backend '{raw}'. Choose one of: kiro, claude, codex.")

    # 2. Additional backends — comma-separated, validate each.
    while True:
        extra_raw = _prompt(
            "Additional backends to enable, comma-separated (blank = none)", "",
            input_fn=input_fn, print_fn=print_fn,
        )
        if not extra_raw:
            break
        parts = [b.strip() for b in extra_raw.split(",")]
        bad = [b for b in parts if b and b not in _KNOWN_BACKENDS]
        if bad:
            print_fn(f"  Unknown backend(s): {', '.join(bad)}. Choose from: kiro, claude, codex.")
            continue
        ga_crew_agent = f"{ga_crew_agent},{extra_raw}"
        break

    # 3. Non-secret config per backend.
    kiro_identity_provider = ""
    kiro_region = ""
    openai_base_url = ""

    if "kiro" in ga_crew_agent:
        kiro_identity_provider = _prompt(
            "kiro-cli identity provider URL (blank = Builder ID)", "",
            input_fn=input_fn, print_fn=print_fn,
        )
        if kiro_identity_provider:
            kiro_region = _prompt(
                "AWS region for that identity provider", "",
                input_fn=input_fn, print_fn=print_fn,
            )

    if "claude" in ga_crew_agent:
        print_fn(
            "  Claude: no config needed here — you'll be offered a login"
            " after the transport starts."
        )

    if "codex" in ga_crew_agent:
        openai_base_url = _prompt(
            "OpenAI-compatible base URL"
            " (blank = https://api.openai.com/v1;"
            " can point at a local proxy like litellm)",
            "",
            input_fn=input_fn,
            print_fn=print_fn,
        )
        print_fn("  Codex: you'll be offered a login after the transport starts.")

    # 4. Write config/ghostship.yaml.
    wrote_config = _write_config(
        ghostship_dir=ghostship_dir,
        ga_crew_agent=ga_crew_agent,
        kiro_identity_provider=kiro_identity_provider,
        kiro_region=kiro_region,
        openai_base_url=openai_base_url,
        input_fn=input_fn,
        print_fn=print_fn,
    )

    return {
        "ga_crew_agent": ga_crew_agent,
        "kiro_identity_provider": kiro_identity_provider,
        "kiro_region": kiro_region,
        "openai_base_url": openai_base_url,
        "wrote_config": wrote_config,
    }


def _write_config(
    *,
    ghostship_dir: str,
    ga_crew_agent: str,
    kiro_identity_provider: str,
    kiro_region: str,
    openai_base_url: str,
    input_fn: Callable,
    print_fn: Callable,
) -> bool:
    """Write config/ghostship.yaml. Returns True when a file was written."""
    if not ghostship_dir:
        return False

    config_dir = Path(ghostship_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = config_dir / "ghostship.yaml"

    if yaml_path.exists():
        overwrite = _prompt(
            "config/ghostship.yaml already exists — overwrite? (y/N)", "n",
            input_fn=input_fn, print_fn=print_fn,
        )
        if overwrite.lower() != "y":
            print_fn("✓ Keeping existing config/ghostship.yaml (wizard values discarded).")
            return False

    def _emit(indent: str, key: str, value: str, default: str) -> str:
        if value:
            return f'{indent}{key}: "{value}"\n'
        return f'{indent}# {key}: "{default}"\n'

    import datetime
    content = (
        f"# Generated by ./install.sh --wizard on"
        f" {datetime.datetime.now(datetime.timezone.utc).strftime('%c')}\n"
        "# Every unset key below is commented out at its built-in default.\n"
        "# Full reference: config/ghostship.yaml.example and docs/configuration.md\n"
        "\n"
        "backends:\n"
        f'  agent: "{ga_crew_agent}"\n'
        "  kiro:\n"
        + _emit("    ", "identity_provider", kiro_identity_provider, "")
        + _emit("    ", "region", kiro_region, "")
        + "  codex:\n"
        + _emit("    ", "base_url", openai_base_url, "")
    )

    yaml_path.write_text(content, encoding="utf-8")
    yaml_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print_fn(f"✓ Config written to {yaml_path}")
    return True


# ---------------------------------------------------------------------------
# post_install_auth
# ---------------------------------------------------------------------------

def post_install_auth(
    env: dict,
    ghostship_bin: str,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[..., None] = print,
    run: Callable = subprocess.run,
) -> None:
    """Offer ghostship auth login for each enabled, unconfigured backend.

    Args:
        env:          Environment dict (must contain GA_CREW_AGENT).
        ghostship_bin: Absolute path to the ghostship CLI binary.
        input_fn:     Input callable (injectable for testing).
        print_fn:     Print callable (injectable for testing).
        run:          subprocess.run-compatible callable.
    """
    print_fn("")
    print_fn("=== Authentication ===")

    ga_crew_agent = env.get("GA_CREW_AGENT", "kiro")
    enabled_backends = [b.strip() for b in ga_crew_agent.split(",") if b.strip()]

    # Query configured status from the transport.
    auth_status: dict = {}
    try:
        result = run(
            [ghostship_bin, "auth", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            auth_status = json.loads(result.stdout)
    except Exception:
        pass  # Fall through: offer login for all enabled backends.

    for backend in enabled_backends:
        is_configured = "unknown"
        info = auth_status.get(backend, {})
        if info:
            is_configured = "yes" if info.get("configured") else "no"

        if is_configured == "yes":
            print_fn(f"  {backend}: already configured — skipping login.")
        else:
            print_fn(
                f"  {backend}: starting login"
                f" (run 'ghostship auth logout {backend}' to undo)."
            )
            try:
                run(
                    [ghostship_bin, "auth", "login", backend],
                    check=False,
                )
            except Exception:
                print_fn(
                    f"  {backend}: login not completed —"
                    f" run 'ghostship auth login {backend}' later.",
                    file=sys.stderr,
                )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prompt(
    prompt: str,
    default: str,
    *,
    input_fn: Callable[[str], str],
    print_fn: Callable[..., None],
) -> str:
    """Read a value with a default; returns default on EOF."""
    try:
        value = input_fn(f"{prompt} [{default}]: ")
    except EOFError:
        value = ""
    return value if value else default


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ghost Academy interactive setup wizard"
    )
    parser.add_argument(
        "--mode",
        choices=["setup", "post-auth"],
        required=True,
        help="Wizard mode: 'setup' (interactive config) or 'post-auth' (auth offers)",
    )
    parser.add_argument(
        "--ghostship-dir",
        default=os.environ.get("GHOSTSHIP_DIR", ""),
        help="Path to the ghostship repo root",
    )
    args = parser.parse_args()

    env = {**os.environ, "GHOSTSHIP_DIR": args.ghostship_dir}

    if args.mode == "setup":
        result = interactive_setup(env)
        # Emit resolved values as shell-safe KEY=value for eval in install.sh
        for key, val in result.items():
            if key != "wrote_config":
                print(f"{key.upper()}={val}")

    elif args.mode == "post-auth":
        ghostship_bin = str(Path(args.ghostship_dir) / "ghostship")
        post_install_auth(env, ghostship_bin)


if __name__ == "__main__":
    main()
