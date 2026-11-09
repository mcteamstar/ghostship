#!/usr/bin/env python3
"""install_main.py — Python entry point for Ghost Academy installer.

Called by the thin bin/install.sh prereq-check shim via:
    exec python3 "$(dirname "$0")/lib/install_main.py" "$@"

This module:
1. Parses all install.sh flags via argparse.
2. Imports yaml_config directly (no subprocess eval).
3. Delegates to podman_setup, compose, caddy, wizard Python modules.
4. Handles image builds, secrets, compose-up, health check via subprocess.
5. Removes the eval "$_RESOLVED" injection surface entirely.

All install.sh logic that was bash is replicated here in Python, so
install.sh can be a ~50-line prereq-check + exec shim.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup: make bin/lib importable and vendor available.
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent  # bin/lib/install_main.py → repo root
_VENDOR = _THIS_DIR / "vendor"

if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

# ---------------------------------------------------------------------------
# Imports from sibling modules.
# ---------------------------------------------------------------------------
import yaml_config as _yaml_config
from agent_backends import normalise as _normalise, validate as _validate, reject_retired as _reject_retired
from portal_host import (
    addr as _addr,
    check_exposure as _check_exposure,
    is_loopback as _is_loopback,
    legacy_bind_notice as _legacy_bind_notice,
    probe_base as _probe_base,
    public_base as _public_base,
    resolve_api_key as _resolve_api_key,
)
from compose import ComposeConfig, generate_compose
from caddy_install import CaddyConfig, generate_caddy_config
import podman_setup as _podman_setup
import wizard as _wizard

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_OS = platform.system()
_COMPOSE_RETRY_ATTEMPTS = 3
_COMPOSE_RETRY_DELAY_SECS = 2


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Install Ghost Academy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--config", default="", help="YAML config file path")
    p.add_argument("--identity-provider", dest="identity_provider", default="",
                   help="kiro-cli identity provider URL")
    p.add_argument("--region", default="", help="AWS region for the identity provider")
    p.add_argument("--port", default="", help="MCP/portal port (default 64057)")
    p.add_argument("--model", default="", dest="model", help="kiro model override")
    p.add_argument("--model-default", default="", dest="model_default",
                   help="Default model across all backends")
    p.add_argument("--public-url", default="", dest="public_url", help="Public base URL")
    p.add_argument("--api-key", default=None, dest="api_key",
                   help="MCP bearer-token API key")
    p.add_argument("--caddy-domain", default="", dest="caddy_domain",
                   help="Caddy ACME domain")
    p.add_argument("--caddy-tls-mode", default="", dest="caddy_tls_mode",
                   help="TLS mode: off|internal|tailscale|acme")
    p.add_argument("--client-only", action="store_true", dest="client_only",
                   help="Wire CLI without container infrastructure")
    p.add_argument("--url", default="http://localhost:64057/mcp", dest="url",
                   help="Transport URL for --client-only")
    p.add_argument("--wizard", action="store_true", dest="wizard",
                   help="Force interactive guided setup")
    return p


# ---------------------------------------------------------------------------
# Config resolution (replaces eval "$_RESOLVED")
# ---------------------------------------------------------------------------

def _resolve_config(args: argparse.Namespace) -> dict:
    """Resolve the merged config dict via yaml_config.resolve_config.

    Returns a flat dict of environment variable names → values.
    No subprocess, no eval.
    """
    ghostship_dir = str(_REPO_ROOT)

    if _OS == "Darwin":
        xdg_yaml = Path.home() / "Library" / "Application Support" / "ghost-academy" / "ghostship.yaml"
    else:
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        xdg_yaml = xdg_config / "ghost-academy" / "ghostship.yaml"

    repo_yaml = Path(ghostship_dir) / "config" / "ghostship.yaml"
    repo_conf = Path(ghostship_dir) / "config" / "ghostship.conf"

    # Auto-migration: ghostship.conf → ghostship.yaml
    if args.config == "" and repo_conf.exists() and not repo_yaml.exists():
        _migrate_conf(repo_conf, repo_yaml)

    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            _die(f"config file does not exist: {args.config}")
        if not config_path.is_file():
            _die(f"Config file is not readable: {args.config}")
        print(f"Loaded config file: {args.config}")
        merged = _yaml_config.resolve_config(
            repo_path="",
            xdg_path="",
            explicit_path=str(config_path),
        )
    else:
        merged = _yaml_config.resolve_config(
            repo_path=str(repo_yaml),
            xdg_path=str(xdg_yaml),
            explicit_path=None,
        )

    return _yaml_config.flatten_to_env(merged)


def _migrate_conf(conf_path: Path, yaml_path: Path) -> None:
    """Migrate legacy ghostship.conf to ghostship.yaml."""
    print("⚠ Legacy config/ghostship.conf found — migrating to config/ghostship.yaml",
          file=sys.stderr)
    result = subprocess.run(
        [sys.executable, str(_THIS_DIR / "yaml_config.py"),
         "migrate", "--conf", str(conf_path), "--out", str(yaml_path)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(_VENDOR)},
    )
    if result.returncode != 0:
        _die("Config migration failed.")
    if result.stdout:
        print("  WARNING: unmapped keys in ghostship.conf:", file=sys.stderr)
        for line in result.stdout.splitlines():
            if line:
                print(f"             {line.removeprefix('UNKNOWN: ')}", file=sys.stderr)
    conf_path.rename(conf_path.with_suffix(".conf.bak"))
    print("✓ Config migrated to config/ghostship.yaml.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args, unknown = parser.parse_known_args()
    if unknown:
        for u in unknown:
            print(f"Unknown argument: {u}", file=sys.stderr)
        sys.exit(1)

    ghostship_dir = str(_REPO_ROOT)

    # ── Resolve merged config (no eval) ──────────────────────────────────────
    cfg = _resolve_config(args)

    # Populate env from resolved config.
    for k, v in cfg.items():
        os.environ.setdefault(k, v)
        os.environ[k] = v

    # ── Apply CLI flag overrides ──────────────────────────────────────────────
    api_key_flag_passed = args.api_key is not None
    flag_api_key = args.api_key or ""
    if args.identity_provider:
        os.environ["KIRO_IDENTITY_PROVIDER"] = args.identity_provider
    if args.region:
        os.environ["KIRO_REGION"] = args.region
    if args.port:
        os.environ["PORT"] = args.port
    if args.model:
        os.environ["KC_MODEL_KIRO_OVERRIDE"] = args.model
    if args.model_default:
        os.environ["KC_MODEL_DEFAULT"] = args.model_default
    if args.public_url:
        os.environ["GA_HOST_URL"] = args.public_url
    if args.caddy_domain:
        os.environ["GA_PORTAL_DOMAIN"] = args.caddy_domain
    if args.caddy_tls_mode:
        os.environ["GA_PORTAL_TLS_MODE"] = args.caddy_tls_mode

    # ── Read resolved config values ───────────────────────────────────────────
    def _g(key: str, default: str = "") -> str:
        return os.environ.get(key, default)

    port = _g("PORT", "64057")
    host = _g("HOST", "127.0.0.1")
    ga_portal_tls_mode = _g("GA_PORTAL_TLS_MODE", "off")
    ga_machine_name = _g("GA_MACHINE_NAME", "ghost-academy")
    ga_dedicated_machine = _g("GA_DEDICATED_MACHINE", "true") == "true"
    ga_crew_agent = _g("GA_CREW_AGENT", "kiro")
    ga_api_key = _g("GA_API_KEY", "")
    ga_api_key_disabled = _g("GA_API_KEY_DISABLED", "")
    client_only = args.client_only

    # ── Warn about ignored deprecated credential vars ─────────────────────────
    _ignored = [
        "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "OPENAI_API_KEY",
        "KIRO_API_KEY", "GA_CREW_ANTHROPIC_API_KEY", "GA_CREW_OPENAI_API_KEY",
    ]
    for var in _ignored:
        if os.environ.get(var):
            print(f"  WARNING: {var} is no longer used by the installer and is ignored.",
                  file=sys.stderr)
            print("           Backend credentials are managed with 'ghostship auth login <backend>'.",
                  file=sys.stderr)
            del os.environ[var]

    # ── Base-URL alias mapping ────────────────────────────────────────────────
    for new in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL"):
        old = f"GA_CREW_{new}"
        if os.environ.get(old):
            print(f"  WARNING: {old} is deprecated — rename it to {new}.", file=sys.stderr)
            if not os.environ.get(new):
                os.environ[new] = os.environ[old]
            else:
                print(f"  {new} is also set; ignoring {old}.", file=sys.stderr)

    # ── GA_AGENT_BACKENDS / GA_CREW_ACP_BACKEND deprecation mapping ───────────
    if os.environ.get("GA_AGENT_BACKENDS"):
        print("  WARNING: GA_AGENT_BACKENDS is deprecated — use GA_CREW_AGENT instead.",
              file=sys.stderr)
        if not ga_crew_agent or ga_crew_agent == "kiro":
            ga_crew_agent = os.environ["GA_AGENT_BACKENDS"]
            os.environ["GA_CREW_AGENT"] = ga_crew_agent
    if os.environ.get("GA_CREW_ACP_BACKEND", "kiro") != "kiro":
        acp = os.environ["GA_CREW_ACP_BACKEND"]
        print(f"  WARNING: GA_CREW_ACP_BACKEND is deprecated — use GA_CREW_AGENT instead.",
              file=sys.stderr)
        if not ga_crew_agent or ga_crew_agent == "kiro":
            ga_crew_agent = acp
            os.environ["GA_CREW_AGENT"] = ga_crew_agent

    # ── Reject retired flags ──────────────────────────────────────────────────
    _reject_retired(dict(os.environ))

    # ── TLS mode validation (before client-only exit so --client-only rejects bad TLS too) ──
    if ga_portal_tls_mode and ga_portal_tls_mode not in ("off", "internal", "tailscale", "acme"):
        _die(f"GA_PORTAL_TLS_MODE='{ga_portal_tls_mode}' is not one of: off, internal, tailscale, acme")

    # ── Client-only early exit ────────────────────────────────────────────────
    if client_only:
        _client_only_install(
            ghostship_dir=ghostship_dir,
            client_url=args.url,
            api_key=flag_api_key or ga_api_key,
        )
        return

    # ── Interactive mode detection ────────────────────────────────────────────
    found_config = (
        (Path(ghostship_dir) / "config" / "ghostship.yaml").exists()
        or (_OS != "Darwin" and Path(
            os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        ) / "ghost-academy" / "ghostship.yaml").exists()
    )
    interactive_mode = (not found_config and sys.stdin.isatty()) or args.wizard

    if interactive_mode:
        wizard_env = {**os.environ, "GHOSTSHIP_DIR": ghostship_dir}
        result = _wizard.interactive_setup(wizard_env)
        ga_crew_agent = result.get("ga_crew_agent", ga_crew_agent)
        os.environ["GA_CREW_AGENT"] = ga_crew_agent
        if result.get("kiro_identity_provider"):
            os.environ["KIRO_IDENTITY_PROVIDER"] = result["kiro_identity_provider"]
        if result.get("kiro_region"):
            os.environ["KIRO_REGION"] = result["kiro_region"]
        if result.get("openai_base_url"):
            os.environ["OPENAI_BASE_URL"] = result["openai_base_url"]

    if not interactive_mode:
        kiro_idp = _g("KIRO_IDENTITY_PROVIDER", "")
        if not kiro_idp and sys.stdin.isatty():
            kiro_idp = input(
                "kiro-cli identity provider URL (blank = default Builder ID login): "
            ).strip()
            if kiro_idp:
                os.environ["KIRO_IDENTITY_PROVIDER"] = kiro_idp
        if kiro_idp and not _g("KIRO_REGION") and sys.stdin.isatty():
            region = input("AWS region for that identity provider: ").strip()
            if region:
                os.environ["KIRO_REGION"] = region

    # ── Agent backend normalise and validate ──────────────────────────────────
    agent_toolchains = _normalise(ga_crew_agent)
    _validate(agent_toolchains, str(Path(ghostship_dir) / "crews" / "spec-ops" / "toolchains"))
    print(f"✓ Agent backend: {ga_crew_agent} (runtime default: {ga_crew_agent.split(',')[0]})")

    # ── Podman provisioning ───────────────────────────────────────────────────
    # PODMAN_SOCK and DATA_DIR are set by the shim for non-client-only installs.
    # If not set (e.g. called directly without the shim), run setup here.
    podman_sock = os.environ.get("PODMAN_SOCK", "")
    data_dir = os.environ.get("DATA_DIR", "")
    if not podman_sock or not data_dir:
        podman_config = _podman_setup.PodmanConfig(
            machine_name=ga_machine_name,
            dedicated=ga_dedicated_machine,
            machine_cpus=int(_g("GA_MACHINE_CPUS", "8")),
            machine_memory=int(_g("GA_MACHINE_MEMORY", "8192")),
            machine_disk=int(_g("GA_MACHINE_DISK", "100")),
            xdg_runtime_dir=os.environ.get("XDG_RUNTIME_DIR", ""),
        )
        if _OS == "Darwin":
            podman_sock = _podman_setup.setup_podman_macos(podman_config)
        else:
            podman_sock = _podman_setup.setup_podman_linux(podman_config)
        if _OS == "Darwin":
            data_dir = str(Path.home() / "Library" / "Application Support" / ga_machine_name / "data")
        else:
            xdg_data = os.environ.get("XDG_DATA_HOME", "") or str(Path.home() / ".local" / "share")
            data_dir = str(Path(xdg_data) / ga_machine_name / "data")
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        os.environ["PODMAN_SOCK"] = podman_sock
        os.environ["DATA_DIR"] = data_dir

    # ── API key resolution ────────────────────────────────────────────────────
    resolved = _resolve_api_key(
        data_dir,
        api_key_flag_passed=api_key_flag_passed,
        flag_api_key=flag_api_key,
        ga_api_key=ga_api_key,
        ga_api_key_disabled=ga_api_key_disabled,
        ga_api_key_source=_g("GA_API_KEY_SOURCE"),
        ga_api_key_deprecated_off=_g("GA_API_KEY_DEPRECATED_OFF"),
    )
    ga_api_key = resolved["ga_api_key"]
    ga_api_key_disabled = resolved["ga_api_key_disabled"]
    os.environ["GA_API_KEY"] = ga_api_key
    os.environ["GA_API_KEY_DISABLED"] = ga_api_key_disabled

    # ── Exposure check ────────────────────────────────────────────────────────
    _check_exposure(host, port, ga_api_key, ga_api_key_disabled)

    # ── Resolve podman command prefix ─────────────────────────────────────────
    _podman_cmd = _build_podman_cmd(ghostship_dir, _OS, ga_dedicated_machine, ga_machine_name)

    # ── Network setup ─────────────────────────────────────────────────────────
    _ensure_networks(_podman_cmd, ga_dedicated_machine, ga_machine_name)

    # ── WSL2 containers.conf (moved from podman_setup to here for non-dedicated) ─
    if _OS == "Linux":
        _write_containers_conf(ga_machine_name)

    # ── Pre-warm + build images ───────────────────────────────────────────────
    _build_images(ghostship_dir, _podman_cmd, agent_toolchains, _g("AGENTS_REF"),
                  _g("KC_BASE_IMAGE"), _g("VERSION", _read_version(ghostship_dir)))

    # ── Podman secrets ────────────────────────────────────────────────────────
    _manage_secrets(_podman_cmd, ga_api_key)

    # ── Copy academy/crews ────────────────────────────────────────────────────
    _copy_academy(ghostship_dir, data_dir)

    # ── Validate GA_ORDERS_DIR / TLS cert/key ────────────────────────────────
    _validate_orders_dir(_g("GA_ORDERS_DIR"))
    _validate_tls_paths(_g("GA_TLS_CERTFILE"), _g("GA_TLS_KEYFILE"))

    # ── Generate compose.yml ──────────────────────────────────────────────────
    _legacy_bind_notice(str(Path(data_dir) / "compose.yml"), host, port)
    portal_bind = _addr(host)
    ga_host_url = _g("GA_HOST_URL") or _public_base(host, port)
    os.environ["GA_HOST_URL"] = ga_host_url

    dashboard_start = _g("GA_DASHBOARD_PORT_RANGE_START", "64058")
    dashboard_size = _g("GA_DASHBOARD_PORT_RANGE_SIZE", "64")
    try:
        dashboard_end = str(int(dashboard_start) + int(dashboard_size) - 1)
    except ValueError:
        dashboard_end = "64121"

    compose_cfg = ComposeConfig(
        data_dir=data_dir,
        podman_sock=podman_sock,
        port=port,
        host=host,
        portal_bind=portal_bind,
        ga_host_url=ga_host_url,
        ga_max_crews=_g("GA_MAX_CREWS", "20"),
        ga_max_active_crews=_g("GA_MAX_ACTIVE_CREWS", "3"),
        ga_idle_timeout_secs=_g("GA_IDLE_TIMEOUT_SECS", "300"),
        ga_subagent_timeout_secs=_g("GA_SUBAGENT_TIMEOUT_SECS", "3600"),
        ga_batch_max_tasks=_g("GA_BATCH_MAX_TASKS", "20"),
        ga_pickup_max_poll_secs=_g("GA_PICKUP_MAX_POLL_SECS", "30"),
        ga_crew_agent=ga_crew_agent,
        anthropic_base_url=_g("ANTHROPIC_BASE_URL"),
        openai_base_url=_g("OPENAI_BASE_URL"),
        kiro_identity_provider=_g("KIRO_IDENTITY_PROVIDER"),
        kiro_region=_g("KIRO_REGION"),
        kc_model_default=_g("KC_MODEL_DEFAULT"),
        kc_model_kiro_override=_g("KC_MODEL_KIRO_OVERRIDE"),
        kc_model_kiro_default=_g("KC_MODEL_KIRO_DEFAULT"),
        kc_model_claude_override=_g("KC_MODEL_CLAUDE_OVERRIDE"),
        kc_model_claude_default=_g("KC_MODEL_CLAUDE_DEFAULT"),
        kc_model_codex_override=_g("KC_MODEL_CODEX_OVERRIDE"),
        kc_model_codex_default=_g("KC_MODEL_CODEX_DEFAULT"),
        ga_min_free_mem_gb=_g("GA_MIN_FREE_MEM_GB", "2.0"),
        ga_start_mem_estimate_gb=_g("GA_START_MEM_ESTIMATE_GB", "1.0"),
        ga_spawn_min_memory_gb=_g("GA_SPAWN_MIN_MEMORY_GB", "1.5"),
        ga_resource_pressure_gb=_g("GA_RESOURCE_PRESSURE_GB", "2.0"),
        ga_resource_critical_gb=_g("GA_RESOURCE_CRITICAL_GB", "1.0"),
        ga_spawn_pressure_escalate_cycles=_g("GA_SPAWN_PRESSURE_ESCALATE_CYCLES", "3"),
        ga_git_author_name=_g("GA_GIT_AUTHOR_NAME"),
        ga_git_author_email=_g("GA_GIT_AUTHOR_EMAIL"),
        ga_rate_limit_enabled=_g("GA_RATE_LIMIT_ENABLED", "true"),
        ga_rate_limit_login_get=_g("GA_RATE_LIMIT_LOGIN_GET", "30:60"),
        ga_rate_limit_login_post=_g("GA_RATE_LIMIT_LOGIN_POST", "5:300"),
        ga_rate_limit_mcp=_g("GA_RATE_LIMIT_MCP", "300:60"),
        ga_rate_limit_files=_g("GA_RATE_LIMIT_FILES", "60:60"),
        ga_rate_limit_crew_api=_g("GA_RATE_LIMIT_CREW_API", "120:60"),
        ga_rate_limit_dashboard_auth=_g("GA_RATE_LIMIT_DASHBOARD_AUTH", "600:60"),
        ga_dashboard_port_range_start=dashboard_start,
        ga_dashboard_default=_g("GA_DASHBOARD_DEFAULT", "false"),
        ga_dashboard_port_range_size=dashboard_size,
        ga_portal_tls_mode=ga_portal_tls_mode,
        ga_portal_domain=_g("GA_PORTAL_DOMAIN"),
        ga_portal_session_ttl_secs=_g("GA_PORTAL_SESSION_TTL_SECS", "86400"),
        ga_api_key_disabled=ga_api_key_disabled,
        kc_image=_g("KC_IMAGE", "localhost/spec-ops:latest"),
        ga_api_key=ga_api_key,
        ga_orders_dir=_g("GA_ORDERS_DIR"),
        ga_tls_certfile=_g("GA_TLS_CERTFILE"),
        ga_tls_keyfile=_g("GA_TLS_KEYFILE"),
        dashboard_port_range_start=dashboard_start,
        dashboard_port_range_end=dashboard_end,
    )
    import stat as _stat
    compose_path = Path(data_dir) / "compose.yml"
    compose_path.write_text(generate_compose(compose_cfg), encoding="utf-8")
    compose_path.chmod(_stat.S_IRUSR | _stat.S_IWUSR)
    print(f"✓ compose.yml written to {compose_path}")

    # ── Generate Caddy initial-config.json ────────────────────────────────────
    import json as _json
    caddy_cfg = CaddyConfig(
        port=port,
        tls_mode=ga_portal_tls_mode,
        acme_domain=_g("GA_PORTAL_DOMAIN"),
        ga_api_key=ga_api_key,
    )
    caddy_dir = Path(data_dir) / "caddy"
    caddy_dir.mkdir(parents=True, exist_ok=True)
    caddy_path = caddy_dir / "initial-config.json"
    caddy_path.write_text(_json.dumps(generate_caddy_config(caddy_cfg), indent=2),
                          encoding="utf-8")
    print(f"✓ Caddy initial-config.json written to {caddy_path}")

    # Internal CA hint
    if ga_portal_tls_mode == "internal":
        _print_internal_ca_hint(_podman_cmd, ga_machine_name, _OS)

    # ── Run transport ─────────────────────────────────────────────────────────
    _compose_up(_podman_cmd, data_dir, ga_dedicated_machine, ga_machine_name,
                _OS, podman_sock, port)

    if ga_api_key:
        print("✓ MCP API-key authentication: enabled (see docs/auth.md)")
    elif ga_api_key_disabled == "true":
        print("  MCP API-key authentication: disabled (explicit opt-out: network.api_key: false)")
    else:
        print("  MCP API-key authentication: disabled (loopback-only; pass --api-key <key>)")

    # ── Health check ──────────────────────────────────────────────────────────
    caddy_scheme = "https" if ga_portal_tls_mode != "off" else "http"
    probe_url = _probe_base(host, port, caddy_scheme) + "/health"
    _health_check(_podman_cmd, probe_url, max_wait=90, interval=3)

    # ── ga-net cleanup ────────────────────────────────────────────────────────
    _cleanup_ga_net(_podman_cmd)

    # ── Interactive-mode harness registration ─────────────────────────────────
    if interactive_mode:
        print("\nRegistering MCP server with detected agent clients...")
        ghostship = str(Path(ghostship_dir) / "ghostship")
        subprocess.run([ghostship, "setup"], check=False)

    # ── Interactive-mode authentication ───────────────────────────────────────
    if interactive_mode:
        ghostship = str(Path(ghostship_dir) / "ghostship")
        _wizard.post_install_auth({**os.environ, "GA_CREW_AGENT": ga_crew_agent}, ghostship)

    # ── Post-install instructions ─────────────────────────────────────────────
    print("\n=== Post-install ===")
    _post_install(ghostship_dir, ga_host_url, interactive_mode)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


def _read_version(ghostship_dir: str) -> str:
    try:
        return (Path(ghostship_dir) / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "unknown"


def _build_podman_cmd(
    ghostship_dir: str, os_name: str, dedicated: bool, machine_name: str
) -> list[str]:
    """Return the podman command prefix list."""
    if dedicated and os_name == "Linux":
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        home = str(Path.home())
        storage_root = f"{home}/.local/share/{machine_name}/containers/storage"
        ga_containers_conf = f"{home}/.config/{machine_name}/containers.conf"
        return [
            "env",
            f"CONTAINERS_CONF={ga_containers_conf}",
            "podman",
            f"--root={storage_root}",
            f"--runroot={runtime_dir}/{machine_name}-containers",
        ]
    elif dedicated and os_name == "Darwin":
        return ["podman", f"--connection={machine_name}"]
    return ["podman"]


def _write_containers_conf(machine_name: str) -> None:
    """Write ghostship-scoped containers.conf for WSL2 iptables workaround."""
    home = str(Path.home())
    conf_path = Path(home) / ".config" / machine_name / "containers.conf"
    conf_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if we're in WSL2
    try:
        proc_version = Path("/proc/version").read_text(encoding="utf-8", errors="replace")
        is_wsl2 = "microsoft" in proc_version.lower()
    except Exception:
        is_wsl2 = False

    if is_wsl2:
        # Ensure iptables is available
        if not shutil.which("iptables"):
            if shutil.which("apt-get"):
                subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "iptables"],
                                check=False)
            elif shutil.which("dnf"):
                subprocess.run(["sudo", "dnf", "install", "-y", "-q", "iptables"],
                                check=False)
        conf_path.write_text(
            f"# ghostship-scoped containers.conf\n"
            f"# WSL2: use iptables instead of nftables.\n"
            "[network]\n"
            'firewall_driver = "iptables"\n',
            encoding="utf-8",
        )
        print(f"✓ WSL2 detected — scoped iptables workaround written to {conf_path}")
    else:
        conf_path.write_text(
            f"# ghostship-scoped containers.conf\n"
            f"# Scoped to the dedicated '{machine_name}' Podman instance only.\n",
            encoding="utf-8",
        )


def _ensure_networks(podman_cmd: list[str], dedicated: bool, machine_name: str) -> None:
    """Ensure ga-portside and ga-starboard networks exist."""
    for net in ("ga-portside", "ga-starboard"):
        result = subprocess.run(
            [*podman_cmd, "network", "exists", net],
            capture_output=True,
        )
        if result.returncode != 0:
            subprocess.run([*podman_cmd, "network", "create", net], check=True)
    if dedicated:
        print(f"✓ ga-portside and ga-starboard networks ready on dedicated instance '{machine_name}'")
    else:
        print("✓ ga-portside and ga-starboard networks ready")


def _build_images(
    ghostship_dir: str,
    podman_cmd: list[str],
    agent_toolchains: str,
    agents_ref: str,
    kc_base_image: str,
    version: str,
) -> None:
    """Build all container images."""
    # Stale-image detection for transport
    transport_build_flags: list[str] = []
    source_hash = _compute_transport_hash(ghostship_dir)
    result = subprocess.run(
        [*podman_cmd, "image", "exists", "localhost/transport:latest"],
        capture_output=True,
    )
    if result.returncode == 0:
        baked_ver = subprocess.run(
            [*podman_cmd, "run", "--rm", "localhost/transport:latest",
             "sh", "-c", "echo $TRANSPORT_VERSION"],
            capture_output=True, text=True,
        ).stdout.strip()
        if baked_ver and baked_ver != version:
            print(f"  Detected stale localhost/transport:latest version ('{baked_ver}' != '{version}') -- forcing clean rebuild.")
            transport_build_flags = ["--no-cache"]

    # crew image stale-detection
    crew_build_flags: list[str] = []
    result = subprocess.run(
        [*podman_cmd, "image", "exists", "localhost/spec-ops:latest"],
        capture_output=True,
    )
    if result.returncode == 0:
        baked_agents = subprocess.run(
            [*podman_cmd, "inspect", "localhost/spec-ops:latest",
             "--format", "{{ index .Labels \"org.ghostship.agent-toolchains\" }}"],
            capture_output=True, text=True,
        ).stdout.strip()
        if baked_agents and baked_agents != agent_toolchains:
            print(f"  Detected stale crew image (toolchains changed) -- forcing clean rebuild.")
            crew_build_flags = ["--no-cache"]

    images = [
        ("base-admission", "Building localhost/base-admission:latest (admission) ..."),
        ("gs-worker", "Building localhost/gs-worker:latest (worker) ..."),
        ("spec-ops", "Building localhost/spec-ops:latest ..."),
        ("transport", "Building localhost/transport:latest ..."),
        ("ga-radar", "Building localhost/ga-radar:latest ..."),
    ]

    for name, msg in images:
        print(msg)
        if name == "base-admission":
            ctx = tempfile.mkdtemp()
            try:
                shutil.copytree(
                    str(Path(ghostship_dir) / "crews" / "_base" / "admission"),
                    ctx, dirs_exist_ok=True,
                )
                scripts_dst = Path(ctx) / "container_scripts"
                scripts_dst.mkdir(exist_ok=True)
                for py in (Path(ghostship_dir) / "transport" / "container_scripts").glob("*.py"):
                    shutil.copy2(py, scripts_dst)
                cmd = [*podman_cmd, "build", "-t", f"localhost/{name}:latest"]
                if kc_base_image:
                    cmd += ["--build-arg", f"KC_BASE_IMAGE={kc_base_image}"]
                cmd.append(ctx)
                subprocess.run(cmd, check=True)
            finally:
                shutil.rmtree(ctx, ignore_errors=True)
        elif name == "spec-ops":
            mid_cmd = [
                *podman_cmd, "build", "-t", "localhost/spec-ops-mid:latest",
                *crew_build_flags,
                "--build-arg", f"VERSION={version}-spec-ops",
                "--build-arg", f"AGENT_TOOLCHAINS={agent_toolchains}",
            ]
            if agents_ref:
                mid_cmd += ["--build-arg", f"AGENTS_REF={agents_ref}"]
            mid_cmd.append(str(Path(ghostship_dir) / "crews" / "spec-ops"))
            subprocess.run(mid_cmd, check=True)
            subprocess.run([
                *podman_cmd, "build", "-t", "localhost/spec-ops:latest",
                *crew_build_flags,
                "--build-arg", "MID_IMAGE=localhost/spec-ops-mid:latest",
                str(Path(ghostship_dir) / "crews" / "_base" / "graduation"),
            ], check=True)
        elif name == "transport":
            cmd = [
                *podman_cmd, "build", "-t", "localhost/transport:latest",
                *transport_build_flags,
                "--build-arg", f"VERSION={version}",
                "--build-arg", f"SOURCE_HASH={source_hash}",
                str(Path(ghostship_dir) / "transport"),
            ]
            subprocess.run(cmd, check=True)
        elif name == "gs-worker":
            subprocess.run([
                *podman_cmd, "build", "-t", f"localhost/{name}:latest",
                "--build-arg", f"VERSION={version}",
                str(Path(ghostship_dir) / "crews" / "_worker"),
            ], check=True)
        else:  # ga-radar
            subprocess.run([
                *podman_cmd, "build", "-t", f"localhost/{name}:latest",
                str(Path(ghostship_dir) / "radar"),
            ], check=True)
        print(f"✓ {name} image built")


def _compute_transport_hash(ghostship_dir: str) -> str:
    """Compute a hash of the transport source tree."""
    try:
        result = subprocess.run(
            "find " + str(Path(ghostship_dir) / "transport") + " -type f | sort | xargs sha256sum 2>/dev/null | sha256sum | awk '{print $1}'",
            shell=True, capture_output=True, text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _manage_secrets(podman_cmd: list[str], ga_api_key: str) -> None:
    """Create/remove ga-api-key and ga-transport-secret Podman secrets."""
    subprocess.run([*podman_cmd, "secret", "rm", "ga-api-key"],
                   capture_output=True)  # ignore errors
    if ga_api_key:
        result = subprocess.run(
            [*podman_cmd, "secret", "create", "ga-api-key", "-"],
            input=ga_api_key.encode(),
            capture_output=True,
        )
        if result.returncode != 0:
            _die("Failed to create ga-api-key Podman secret")
        print("✓ Podman secret 'ga-api-key' created")

    result = subprocess.run(
        [*podman_cmd, "secret", "inspect", "ga-transport-secret"],
        capture_output=True,
    )
    if result.returncode != 0:
        openssl = subprocess.run(
            ["openssl", "rand", "-hex", "32"],
            capture_output=True, text=True, check=True,
        )
        subprocess.run(
            [*podman_cmd, "secret", "create", "ga-transport-secret", "-"],
            input=openssl.stdout.strip().encode(),
            check=True,
        )
        print("✓ Podman secret 'ga-transport-secret' created (new)")
    else:
        print("✓ Podman secret 'ga-transport-secret' already exists (keeping existing)")


def _copy_academy(ghostship_dir: str, data_dir: str) -> None:
    """Copy academy/ and crews/ into DATA_DIR."""
    data = Path(data_dir)
    (data / "academy").mkdir(parents=True, exist_ok=True)
    dirs = ["agents", "skills", "steering", "policies", "orders", "mcp"]
    if shutil.which("rsync"):
        for d in dirs:
            subprocess.run(
                ["rsync", "-a", "--delete",
                 str(Path(ghostship_dir) / "academy" / d) + "/",
                 str(data / "academy" / d) + "/"],
                check=True,
            )
        subprocess.run(
            ["rsync", "-a", "--delete",
             str(Path(ghostship_dir) / "crews") + "/",
             str(data / "crews") + "/"],
            check=True,
        )
    else:
        print("  rsync not found — falling back to cp")
        for d in dirs:
            dst = data / "academy" / d
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(str(Path(ghostship_dir) / "academy" / d), str(dst))
        crews_dst = data / "crews"
        if crews_dst.exists():
            shutil.rmtree(crews_dst)
        shutil.copytree(str(Path(ghostship_dir) / "crews"), str(crews_dst))
    print(f"✓ academy/ and crews/ copied to {data_dir}")


def _validate_orders_dir(ga_orders_dir: str) -> None:
    if not ga_orders_dir:
        return
    if not ga_orders_dir.startswith("/"):
        _die(f"GA_ORDERS_DIR={ga_orders_dir} is not an absolute path.")
    if not Path(ga_orders_dir).exists():
        print(f"  WARNING: GA_ORDERS_DIR={ga_orders_dir} does not exist.")


def _validate_tls_paths(certfile: str, keyfile: str) -> None:
    if not certfile and not keyfile:
        return
    if not certfile or not keyfile:
        _die("GA_TLS_CERTFILE and GA_TLS_KEYFILE must both be set or both be unset.")
    if Path(certfile).parent != Path(keyfile).parent:
        _die(
            "GA_TLS_CERTFILE and GA_TLS_KEYFILE must be in the same parent directory.\n"
            f"  Cert: {certfile}\n  Key:  {keyfile}"
        )


def _compose_up(
    podman_cmd: list[str],
    data_dir: str,
    dedicated: bool,
    machine_name: str,
    os_name: str,
    podman_sock: str,
    port: str,
) -> None:
    """Start the compose stack."""
    # Kill stale rootlessport
    try:
        pids = subprocess.run(
            ["pgrep", "-x", "rootlessport"], capture_output=True, text=True
        ).stdout.split()
        for pid in pids:
            ss = subprocess.run(
                ["ss", "-tlnp"], capture_output=True, text=True
            ).stdout
            if f"0.0.0.0:{port}" in ss and f"pid={pid}" in ss:
                subprocess.run(["kill", pid], check=False)
                time.sleep(0.5)
    except Exception:
        pass

    # Compose env
    compose_env = dict(os.environ)
    if dedicated and os_name == "Linux":
        compose_env["CONTAINER_HOST"] = f"unix://{podman_sock}"
    elif dedicated and os_name == "Darwin":
        compose_env["CONTAINER_CONNECTION"] = machine_name

    podman_compose_bin = shutil.which("podman-compose") or "podman-compose"
    compose_env["PODMAN_COMPOSE_PROVIDER"] = podman_compose_bin

    compose_file = str(Path(data_dir) / "compose.yml")

    # Remove old containers
    subprocess.run([*podman_cmd, "rm", "-f", "ga-transport"],
                   capture_output=True, env=compose_env)
    subprocess.run([*podman_cmd, "rm", "-f", "ga-portal"],
                   capture_output=True, env=compose_env)

    # Compose up with retry
    for attempt in range(1, _COMPOSE_RETRY_ATTEMPTS + 1):
        result = subprocess.run(
            ["podman-compose", "--project-name", "ga", "-f", compose_file,
             "up", "-d", "--force-recreate", "--remove-orphans"],
            env=compose_env,
        )
        if result.returncode == 0:
            break
        if attempt < _COMPOSE_RETRY_ATTEMPTS:
            print(f"  compose up failed (attempt {attempt}/{_COMPOSE_RETRY_ATTEMPTS}), retrying...",
                  file=sys.stderr)
            time.sleep(_COMPOSE_RETRY_DELAY_SECS)
    else:
        _die(f"compose up failed after {_COMPOSE_RETRY_ATTEMPTS} attempt(s)")

    print("✓ ga-transport container started")


def _health_check(podman_cmd: list[str], probe_url: str, max_wait: int, interval: int) -> None:
    """Wait for the transport health check to pass through ga-portal."""
    time.sleep(1)
    print("\n=== Health check ===")
    ready = False
    for _ in range(0, max_wait, interval):
        try:
            req = urllib.request.Request(probe_url)
            urllib.request.urlopen(req, timeout=5)
            ready = True
            break
        except Exception:
            time.sleep(interval)

    if ready:
        print(f"✓ Transport is ready ({probe_url})")
    else:
        print(f"✗ Transport did not become ready within {max_wait}s ({probe_url})",
              file=sys.stderr)
        print("  Run: podman logs ga-portal --tail 20", file=sys.stderr)
        sys.exit(1)


def _cleanup_ga_net(podman_cmd: list[str]) -> None:
    """Remove ga-net if empty (migration cleanup)."""
    result = subprocess.run(
        [*podman_cmd, "network", "exists", "ga-net"],
        capture_output=True,
    )
    if result.returncode == 0:
        containers = subprocess.run(
            [*podman_cmd, "network", "inspect", "ga-net",
             "--format", "{{len .Containers}}"],
            capture_output=True, text=True,
        ).stdout.strip()
        if containers == "0":
            subprocess.run([*podman_cmd, "network", "rm", "ga-net"],
                           capture_output=True)
            print("✓ ga-net removed (empty, migration complete)")


def _print_internal_ca_hint(
    podman_cmd: list[str], machine_name: str, os_name: str
) -> None:
    """Print the internal CA cert path hint."""
    mountpoint = ""
    for vol in ("ga_ga-portal-data", "ga-portal-data"):
        result = subprocess.run(
            [*podman_cmd, "volume", "inspect", vol, "--format", "{{.Mountpoint}}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            mountpoint = result.stdout.strip()
            break

    cert_path = f"{mountpoint or '(ga-portal-data not yet created)'}/caddy/pki/authorities/local/root.crt"
    print("\n── Caddy internal CA ─────────────────────────────────────────────────")
    print("TLS mode: internal (Caddy built-in CA)")
    print(f"Root CA cert: {cert_path}")
    if os_name == "Darwin" and mountpoint:
        print(f"  (VM path — to extract: podman machine ssh {machine_name} cat {cert_path} > ~/ghost-academy-root.crt)")
    print("\nAfter ga-portal starts, run this once to trust the CA:")
    print("  podman exec ga-portal caddy trust")
    print("──────────────────────────────────────────────────────────────────────\n")


def _client_only_install(ghostship_dir: str, client_url: str, api_key: str) -> None:
    """Wire the ghostship CLI + agent harnesses to a remote transport."""
    local_bin = str(Path.home() / ".local" / "bin")
    Path(local_bin).mkdir(parents=True, exist_ok=True)
    ghostship = str(Path(ghostship_dir) / "ghostship")
    (Path(local_bin) / "ghostship").unlink(missing_ok=True)
    os.symlink(ghostship, str(Path(local_bin) / "ghostship"))
    print(f"✓ ghostship CLI linked to {local_bin}/ghostship")

    cmd = [ghostship, "setup", "--url", client_url]
    if api_key:
        cmd += ["--api-key", api_key]
    subprocess.run(cmd, check=True)

    path = os.environ.get("PATH", "")
    if local_bin not in path:
        print(f'  Add ~/.local/bin to your PATH: export PATH="$HOME/.local/bin:$PATH"')


def _post_install(ghostship_dir: str, ga_host_url: str, interactive_mode: bool) -> None:
    """Print or execute post-install steps."""
    # Best-effort ghostship setup (always run after wizard)
    if interactive_mode:
        ghostship = str(Path(ghostship_dir) / "ghostship")
        print("\nRegistering MCP server with detected agent clients (kiro-cli, claude, opencode)...")
        subprocess.run([ghostship, "setup"], check=False)

    if not interactive_mode:
        print(f"Register the MCP server (one-time):")
        mcp_url = ga_host_url.rstrip("/") + "/mcp"
        print(f"  kiro-cli mcp add --name ghostship --url {mcp_url} --scope global")
        print("")
        print("Then from Kiro CLI, create the first crew:")
        print('  ghostship__launch(crew_id="general")')
        print("")

    # ghostship CLI link
    local_bin = str(Path.home() / ".local" / "bin")
    Path(local_bin).mkdir(parents=True, exist_ok=True)
    ghostship_src = str(Path(ghostship_dir) / "ghostship")
    link = Path(local_bin) / "ghostship"
    link.unlink(missing_ok=True)
    link.symlink_to(ghostship_src)
    print(f"\n✓ ghostship CLI linked to {local_bin}/ghostship")
    path = os.environ.get("PATH", "")
    if local_bin not in path:
        print(f'  Add ~/.local/bin to your PATH: export PATH="$HOME/.local/bin:$PATH"')


if __name__ == "__main__":
    main()
