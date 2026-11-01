#!/usr/bin/env python3
"""compose.py — Generate compose.yml for Ghost Academy.

Replaces the compose.yml heredoc in bin/install.sh. Produces a PyYAML-
serialised YAML string from a structured config dataclass; no string
interpolation, so quoting edge cases cannot occur.

Usage (CLI):
    python3 bin/lib/compose.py --output <path>

All config is read from environment variables when running as a CLI entry
point (mirroring install.sh's resolved environment).
"""
from __future__ import annotations

import argparse
import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# PyYAML is vendored at bin/lib/vendor/yaml — no pip, no network.
_THIS_DIR = Path(__file__).resolve().parent
_VENDOR = _THIS_DIR / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

import yaml  # noqa: E402  (vendored)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ComposeConfig:
    """All fields needed to render compose.yml.

    Required fields raise ValueError when empty.  Optional fields default to
    empty string / False.
    """

    # Required
    data_dir: str
    podman_sock: str
    port: str = "64057"
    host: str = "127.0.0.1"
    portal_bind: str = "127.0.0.1"
    ga_host_url: str = ""

    # Transport env vars
    ga_max_crews: str = "20"
    ga_max_active_crews: str = "3"
    ga_idle_timeout_secs: str = "300"
    ga_subagent_timeout_secs: str = "3600"
    ga_batch_max_tasks: str = "20"
    ga_pickup_max_poll_secs: str = "30"
    ga_crew_agent: str = "kiro"
    anthropic_base_url: str = ""
    openai_base_url: str = ""
    kiro_identity_provider: str = ""
    kiro_region: str = ""
    kc_model_default: str = ""
    kc_model_kiro_override: str = ""
    kc_model_kiro_default: str = ""
    kc_model_claude_override: str = ""
    kc_model_claude_default: str = ""
    kc_model_codex_override: str = ""
    kc_model_codex_default: str = ""
    ga_min_free_mem_gb: str = "2.0"
    ga_spawn_min_memory_gb: str = "1.5"
    ga_resource_pressure_gb: str = "2.0"
    ga_resource_critical_gb: str = "1.0"
    ga_spawn_pressure_escalate_cycles: str = "3"
    ga_git_author_name: str = ""
    ga_git_author_email: str = ""
    ga_rate_limit_enabled: str = "true"
    ga_rate_limit_login_get: str = "30:60"
    ga_rate_limit_login_post: str = "5:300"
    ga_rate_limit_mcp: str = "300:60"
    ga_rate_limit_files: str = "60:60"
    ga_rate_limit_crew_api: str = "120:60"
    ga_rate_limit_dashboard_auth: str = "600:60"
    ga_dashboard_port_range_start: str = "64058"
    ga_dashboard_default: str = "false"
    ga_dashboard_port_range_size: str = "64"
    ga_portal_tls_mode: str = "off"
    ga_portal_domain: str = ""
    ga_portal_session_ttl_secs: str = "86400"
    ga_api_key_disabled: str = ""
    kc_image: str = "localhost/spec-ops:latest"

    # Optional conditional features
    ga_api_key: str = ""           # non-empty → secret mount
    ga_orders_dir: str = ""        # non-empty → bind mount
    ga_tls_certfile: str = ""      # non-empty → TLS cert bind mount
    ga_tls_keyfile: str = ""       # non-empty → TLS key bind mount

    # Dashboard port range (computed by caller)
    dashboard_port_range_start: str = "64058"
    dashboard_port_range_end: str = "64121"

    def __post_init__(self) -> None:
        for required in ("data_dir", "podman_sock"):
            val = getattr(self, required)
            if not val:
                raise ValueError(
                    f"ComposeConfig: required field '{required}' is empty"
                )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate_compose(config: ComposeConfig) -> str:
    """Return a PyYAML-serialised compose.yml string for the given config."""

    # --- Transport volumes ---
    transport_volumes = [
        f"{config.data_dir}:/data",
        f"{config.data_dir}/academy/agents:/agents:ro",
        f"{config.data_dir}/academy/skills:/skills:ro",
        f"{config.data_dir}/academy/steering:/steering:ro",
        f"{config.data_dir}/academy/policies:/policies:ro",
        f"{config.data_dir}/academy/orders:/orders:ro",
        f"{config.data_dir}/academy/mcp:/mcp:ro",
        f"{config.data_dir}/crews:/crews:ro",
        f"{config.podman_sock}:{config.podman_sock}",
    ]
    if config.ga_orders_dir:
        transport_volumes.append(f"{config.ga_orders_dir}:/mnt/orders:ro")
    if config.ga_tls_certfile:
        tls_dir = str(Path(config.ga_tls_certfile).parent)
        transport_volumes.append(f"{tls_dir}:/mnt/tls:ro")

    # --- Transport environment ---
    tls_certfile_container = ""
    tls_keyfile_container = ""
    if config.ga_tls_certfile:
        tls_certfile_container = f"/mnt/tls/{Path(config.ga_tls_certfile).name}"
    if config.ga_tls_keyfile:
        tls_keyfile_container = f"/mnt/tls/{Path(config.ga_tls_keyfile).name}"

    orders_dir_container = "/mnt/orders" if config.ga_orders_dir else ""

    transport_environment = {
        "PODMAN_SOCKET": config.podman_sock,
        "GA_TRANSPORT_BIND": "0.0.0.0",
        "GA_PORTAL_HOST": config.host,
        "GA_API_KEY_DISABLED": config.ga_api_key_disabled,
        "PORT": "64057",
        "GA_HOST_URL": config.ga_host_url,
        "GA_MAX_CREWS": config.ga_max_crews,
        "GA_MAX_ACTIVE_CREWS": config.ga_max_active_crews,
        "GA_IDLE_TIMEOUT_SECS": config.ga_idle_timeout_secs,
        "GA_SUBAGENT_TIMEOUT_SECS": config.ga_subagent_timeout_secs,
        "GA_BATCH_MAX_TASKS": config.ga_batch_max_tasks,
        "GA_PICKUP_MAX_POLL_SECS": config.ga_pickup_max_poll_secs,
        "GA_CREW_AGENT": config.ga_crew_agent,
        "ANTHROPIC_BASE_URL": config.anthropic_base_url,
        "OPENAI_BASE_URL": config.openai_base_url,
        "KIRO_IDENTITY_PROVIDER": config.kiro_identity_provider,
        "KIRO_REGION": config.kiro_region,
        "KC_MODEL_DEFAULT": config.kc_model_default,
        "KC_MODEL_KIRO_OVERRIDE": config.kc_model_kiro_override,
        "KC_MODEL_KIRO_DEFAULT": config.kc_model_kiro_default,
        "KC_MODEL_CLAUDE_OVERRIDE": config.kc_model_claude_override,
        "KC_MODEL_CLAUDE_DEFAULT": config.kc_model_claude_default,
        "KC_MODEL_CODEX_OVERRIDE": config.kc_model_codex_override,
        "KC_MODEL_CODEX_DEFAULT": config.kc_model_codex_default,
        "GA_MIN_FREE_MEM_GB": config.ga_min_free_mem_gb,
        "GA_SPAWN_MIN_MEMORY_GB": config.ga_spawn_min_memory_gb,
        "GA_RESOURCE_PRESSURE_GB": config.ga_resource_pressure_gb,
        "GA_RESOURCE_CRITICAL_GB": config.ga_resource_critical_gb,
        "GA_SPAWN_PRESSURE_ESCALATE_CYCLES": config.ga_spawn_pressure_escalate_cycles,
        "GA_GIT_AUTHOR_NAME": config.ga_git_author_name,
        "GA_GIT_AUTHOR_EMAIL": config.ga_git_author_email,
        "GA_TLS_CERTFILE": tls_certfile_container,
        "GA_TLS_KEYFILE": tls_keyfile_container,
        "GA_RATE_LIMIT_ENABLED": config.ga_rate_limit_enabled,
        "GA_RATE_LIMIT_LOGIN_GET": config.ga_rate_limit_login_get,
        "GA_RATE_LIMIT_LOGIN_POST": config.ga_rate_limit_login_post,
        "GA_RATE_LIMIT_MCP": config.ga_rate_limit_mcp,
        "GA_RATE_LIMIT_FILES": config.ga_rate_limit_files,
        "GA_RATE_LIMIT_CREW_API": config.ga_rate_limit_crew_api,
        "GA_RATE_LIMIT_DASHBOARD_AUTH": config.ga_rate_limit_dashboard_auth,
        "GA_DASHBOARD_PORT_RANGE_START": config.ga_dashboard_port_range_start,
        "GA_DASHBOARD_DEFAULT": config.ga_dashboard_default,
        "GA_DASHBOARD_PORT_RANGE_SIZE": config.ga_dashboard_port_range_size,
        "GA_PORTAL_TLS_MODE": config.ga_portal_tls_mode,
        "GA_PORTAL_DOMAIN": config.ga_portal_domain,
        "GA_PORTAL_SESSION_TTL_SECS": config.ga_portal_session_ttl_secs,
        "GA_ORDERS_DIR": orders_dir_container,
        "KC_IMAGE": config.kc_image,
    }

    # --- Transport secrets ---
    transport_secrets: list[str] = ["ga-transport-secret"]
    if config.ga_api_key:
        transport_secrets.append("ga-api-key")

    # --- Portal secrets ---
    portal_secrets: list[str] = ["ga-transport-secret"]
    if config.ga_api_key:
        portal_secrets.append("ga-api-key")

    # --- Portal ports ---
    portal_ports = [
        (
            f"{config.portal_bind}:{config.port}:{config.port}"
        ),
        (
            f"{config.portal_bind}:{config.dashboard_port_range_start}-"
            f"{config.dashboard_port_range_end}:{config.dashboard_port_range_start}-"
            f"{config.dashboard_port_range_end}"
        ),
    ]

    # --- Top-level secrets ---
    top_secrets: dict = {
        "ga-transport-secret": {"external": True},
    }
    if config.ga_api_key:
        top_secrets["ga-api-key"] = {"external": True}

    # --- Build the document ---
    doc: dict = {
        "services": {
            "ga-transport": {
                "image": "localhost/transport:latest",
                "container_name": "ga-transport",
                "restart": "always",
                "security_opt": ["label=disable"],
                "networks": ["ga-portside", "ga-starboard"],
                "volumes": transport_volumes,
                "environment": transport_environment,
                "secrets": transport_secrets,
            },
            "ga-radar": {
                "image": "localhost/ga-radar:latest",
                "container_name": "ga-radar",
                "restart": "unless-stopped",
                "networks": ["ga-portside"],
                "environment": {
                    "TRANSPORT_URL": "http://ga-transport:64057",
                },
                "secrets": ["ga-transport-secret"],
                "depends_on": ["ga-transport"],
            },
            "ga-portal": {
                "image": "docker.io/caddy:2",
                "container_name": "ga-portal",
                "restart": "always",
                "ports": portal_ports,
                "networks": ["ga-portside"],
                "secrets": portal_secrets,
                "volumes": [
                    f"{config.data_dir}/caddy/initial-config.json:/config/initial-config.json:ro",
                    "ga-portal-data:/data",
                ],
                "command": [
                    "caddy",
                    "run",
                    "--config",
                    "/config/initial-config.json",
                    "--resume",
                ],
            },
        },
        "networks": {
            "ga-portside": {"external": True},
            "ga-starboard": {"external": True},
        },
        "secrets": top_secrets,
        "volumes": {
            "ga-portal-data": None,
        },
    }

    return yaml.dump(doc, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _config_from_env() -> ComposeConfig:
    """Build a ComposeConfig from the current environment."""
    env = os.environ

    data_dir = env.get("DATA_DIR", "")
    if not data_dir:
        print("Error: DATA_DIR is not set", file=sys.stderr)
        sys.exit(1)

    podman_sock = env.get("PODMAN_SOCK", "")
    if not podman_sock:
        print("Error: PODMAN_SOCK is not set", file=sys.stderr)
        sys.exit(1)

    port = env.get("PORT", "64057")
    host = env.get("HOST", "127.0.0.1")

    # Compute portal_bind and dashboard range end the same way install.sh does.
    # portal_addr: IPv6 literals get bracketed.
    raw_host = host or "127.0.0.1"
    if ":" in raw_host and not raw_host.startswith("["):
        portal_bind = f"[{raw_host}]"
    else:
        portal_bind = raw_host

    dashboard_start = env.get("GA_DASHBOARD_PORT_RANGE_START", "64058")
    dashboard_size = env.get("GA_DASHBOARD_PORT_RANGE_SIZE", "64")
    try:
        dashboard_end = str(int(dashboard_start) + int(dashboard_size) - 1)
    except ValueError:
        dashboard_end = "64121"

    ga_host_url = env.get("GA_HOST_URL", "")

    return ComposeConfig(
        data_dir=data_dir,
        podman_sock=podman_sock,
        port=port,
        host=host,
        portal_bind=portal_bind,
        ga_host_url=ga_host_url,
        ga_max_crews=env.get("GA_MAX_CREWS", "20"),
        ga_max_active_crews=env.get("GA_MAX_ACTIVE_CREWS", "3"),
        ga_idle_timeout_secs=env.get("GA_IDLE_TIMEOUT_SECS", "300"),
        ga_subagent_timeout_secs=env.get("GA_SUBAGENT_TIMEOUT_SECS", "3600"),
        ga_batch_max_tasks=env.get("GA_BATCH_MAX_TASKS", "20"),
        ga_pickup_max_poll_secs=env.get("GA_PICKUP_MAX_POLL_SECS", "30"),
        ga_crew_agent=env.get("GA_CREW_AGENT", "kiro"),
        anthropic_base_url=env.get("ANTHROPIC_BASE_URL", ""),
        openai_base_url=env.get("OPENAI_BASE_URL", ""),
        kiro_identity_provider=env.get("KIRO_IDENTITY_PROVIDER", ""),
        kiro_region=env.get("KIRO_REGION", ""),
        kc_model_default=env.get("KC_MODEL_DEFAULT", ""),
        kc_model_kiro_override=env.get("KC_MODEL_KIRO_OVERRIDE", ""),
        kc_model_kiro_default=env.get("KC_MODEL_KIRO_DEFAULT", ""),
        kc_model_claude_override=env.get("KC_MODEL_CLAUDE_OVERRIDE", ""),
        kc_model_claude_default=env.get("KC_MODEL_CLAUDE_DEFAULT", ""),
        kc_model_codex_override=env.get("KC_MODEL_CODEX_OVERRIDE", ""),
        kc_model_codex_default=env.get("KC_MODEL_CODEX_DEFAULT", ""),
        ga_min_free_mem_gb=env.get("GA_MIN_FREE_MEM_GB", "2.0"),
        ga_spawn_min_memory_gb=env.get("GA_SPAWN_MIN_MEMORY_GB", "1.5"),
        ga_resource_pressure_gb=env.get("GA_RESOURCE_PRESSURE_GB", "2.0"),
        ga_resource_critical_gb=env.get("GA_RESOURCE_CRITICAL_GB", "1.0"),
        ga_spawn_pressure_escalate_cycles=env.get("GA_SPAWN_PRESSURE_ESCALATE_CYCLES", "3"),
        ga_git_author_name=env.get("GA_GIT_AUTHOR_NAME", ""),
        ga_git_author_email=env.get("GA_GIT_AUTHOR_EMAIL", ""),
        ga_rate_limit_enabled=env.get("GA_RATE_LIMIT_ENABLED", "true"),
        ga_rate_limit_login_get=env.get("GA_RATE_LIMIT_LOGIN_GET", "30:60"),
        ga_rate_limit_login_post=env.get("GA_RATE_LIMIT_LOGIN_POST", "5:300"),
        ga_rate_limit_mcp=env.get("GA_RATE_LIMIT_MCP", "300:60"),
        ga_rate_limit_files=env.get("GA_RATE_LIMIT_FILES", "60:60"),
        ga_rate_limit_crew_api=env.get("GA_RATE_LIMIT_CREW_API", "120:60"),
        ga_rate_limit_dashboard_auth=env.get("GA_RATE_LIMIT_DASHBOARD_AUTH", "600:60"),
        ga_dashboard_port_range_start=dashboard_start,
        ga_dashboard_default=env.get("GA_DASHBOARD_DEFAULT", "false"),
        ga_dashboard_port_range_size=dashboard_size,
        ga_portal_tls_mode=env.get("GA_PORTAL_TLS_MODE", "off"),
        ga_portal_domain=env.get("GA_PORTAL_DOMAIN", ""),
        ga_portal_session_ttl_secs=env.get("GA_PORTAL_SESSION_TTL_SECS", "86400"),
        ga_api_key_disabled=env.get("GA_API_KEY_DISABLED", ""),
        kc_image=env.get("KC_IMAGE", "localhost/spec-ops:latest"),
        ga_api_key=env.get("GA_API_KEY", ""),
        ga_orders_dir=env.get("GA_ORDERS_DIR", ""),
        ga_tls_certfile=env.get("GA_TLS_CERTFILE", ""),
        ga_tls_keyfile=env.get("GA_TLS_KEYFILE", ""),
        dashboard_port_range_start=dashboard_start,
        dashboard_port_range_end=dashboard_end,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate compose.yml for Ghost Academy"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the generated compose.yml",
    )
    args = parser.parse_args()

    config = _config_from_env()
    content = generate_compose(config)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Write owner-only (matching the heredoc's umask 077 + chmod 600).
    out.write_text(content, encoding="utf-8")
    out.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"✓ compose.yml written to {out}")


if __name__ == "__main__":
    main()
