"""Single source of truth for transport runtime configuration (TRN-75).

All environment-driven runtime configuration the transport reads at startup is
declared here as a `Config` dataclass. `server.py` builds one instance via
`Config.from_env()` at import time and reads `cfg.<field>` everywhere it used to
call `os.environ.get(...)`.

Keeping the dataclass pure (plain typed fields with defaults) makes config
testable without touching the environment — construct `Config(field=value)`
directly in a test. The only place that reads `os.environ` is `from_env()`.

Field names mirror the env var names lowercased (e.g. `GA_MAX_CREWS` ->
`ga_max_crews`) so the mapping is mechanical and grep-able.

Note on scope: secret loading (`GA_FILE_SECRET`, `GA_API_KEY`), the transport
version resolver (`TRANSPORT_VERSION`), the academy order path (`ACADEMY_PATH`),
`dict(os.environ)` passthrough, and the env reads embedded inside generated
crew-side transfer scripts all have bespoke handling in `server.py` and are
intentionally NOT part of `Config`.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field


def _env_bool_default_on(name: str) -> bool:
    """Truthy unless explicitly disabled (default: on)."""
    return os.environ.get(name, "1").strip() not in ("0", "false", "")


def _env_bool_default_off(name: str) -> bool:
    """Falsy unless explicitly enabled (default: off)."""
    return os.environ.get(name, "0").strip() in ("1", "true")


_TTL_RE = re.compile(r"^([1-9]\d*)[smhd]$")
_config_logger = logging.getLogger(__name__)


_CADDY_TLS_MODES: frozenset[str] = frozenset({"internal", "tailscale", "acme", "off"})


def _validate_caddy_tls_mode(value: str, default: str = "internal") -> str:
    """Validate GA_PORTAL_TLS_MODE against the four allowed values.

    On an unrecognised value, logs a WARNING and falls back to ``default``.
    """
    if value in _CADDY_TLS_MODES:
        return value
    _config_logger.warning(
        "GA_PORTAL_TLS_MODE=%r is not one of %s; falling back to %r",
        value,
        sorted(_CADDY_TLS_MODES),
        default,
    )
    return default


def _validate_token_ttl(value: str, default: str = "24h") -> str:
    """Validate a KC_GATEWAY_TOKEN_TTL value.

    Accepts values matching ``^\\d+[smhd]$`` with the numeric part > 0.
    On mismatch, logs a WARNING and returns ``default``.
    """
    if _TTL_RE.match(value):
        return value
    _config_logger.warning(
        "KC_GATEWAY_TOKEN_TTL=%r is invalid; falling back to %r", value, default
    )
    return default


@dataclass
class Config:
    """Transport runtime configuration.

    Defaults mirror the literal defaults previously inlined in
    `server.py`'s `os.environ.get(...)` calls. No behaviour change.
    """

    # ── Network ──────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 64057
    ga_host_url: str = ""

    # ── Storage / runtime ────────────────────────────────────────────────────
    transport_data_dir: str = "/data"
    podman_socket: str = "/run/user/1000/podman/podman.sock"

    # ── Images ───────────────────────────────────────────────────────────────
    kc_image: str = "localhost/spec-ops:latest"
    kc_base_image: str = "ghcr.io/kirodotdev/kirocrew:0.5.0"

    # ── Crew lifecycle ───────────────────────────────────────────────────────
    ga_max_crews: int = 20
    ga_max_active_crews: int = 3
    ga_idle_timeout_secs: int = 300
    ga_crew_agent: str = "kiro"
    ga_file_ttl_secs: int = 300
    ga_pickup_max_poll_secs: int = 30

    # ── Model ────────────────────────────────────────────────────────────────
    kc_model_override: str = ""
    kc_model_default: str = ""

    # ── Memory gate / thresholds ─────────────────────────────────────────────
    ga_min_free_mem_gb: float = 2.0
    ga_memory_wait_secs: int = 60
    ga_spawn_min_memory_gb: float = 1.5
    ga_resource_pressure_gb: float = 2.0
    ga_resource_critical_gb: float = 1.0

    # ── Subagent timeouts ────────────────────────────────────────────────────
    ga_subagent_timeout_secs: int = 3600
    ga_subagent_max_turns: int = 200

    # ── Gateway ──────────────────────────────────────────────────────────────
    kc_gateway_token_ttl: str = "24h"

    # ── Crew UI port allocation (TRN-80 / TRN-101) ───────────────────────────
    # TRN-101: GA_DASHBOARD_PORT_ENABLED removed — dashboard access is now
    # exclusively provided by ga-portal (Caddy). The port range config is
    # retained because Portal still uses it via the transport's port pool.
    ga_dashboard_port_range_start: int = 64058
    ga_dashboard_port_range_size: int = 50

    # ── Transport security (TRN-70) ──────────────────────────────────────────
    ga_tls_min_version: str = "1.2"
    ga_tls_certfile: str = ""
    ga_tls_keyfile: str = ""
    ga_enable_security_headers: bool = True
    ga_enforce_https_redirect: bool = False
    ga_csp_enforce: bool = False

    # ── Caddy reverse proxy (TRN-92) ─────────────────────────────────────────
    # ga-portal (Caddy) is a required architectural component (TRN-103): it owns
    # the main HTTPS port and the dashboard port range, and provides the
    # portal → transport → crew proxy path. It is always started by install.sh.
    # URL of the Caddy admin API, reachable from inside the transport container.
    ga_portal_admin_url: str = "http://ga-portal:2019"
    # TLS mode: internal | tailscale | acme | off
    # - internal (default): Caddy built-in CA; requires a one-time `caddy trust`
    # - tailscale: real certs from Tailscale ACME for .ts.net hostnames
    # - acme: public Let's Encrypt; requires GA_PORTAL_DOMAIN and port 80/443
    # - off: plain HTTP, no TLS
    ga_portal_tls_mode: str = "internal"
    # Domain name used for ACME (Let's Encrypt) certificate requests.
    ga_portal_domain: str = ""
    # HTTPS port Caddy listens on (main port).
    ga_portal_port: int = 64057    # HTTP port Caddy listens on (redirects, ACME challenges).
    # Session TTL for gs_session cookies (dashboard login); default 24 h.
    ga_portal_session_ttl_secs: int = 86400

    # ── kiro-cli identity ────────────────────────────────────────────────────
    kiro_license: str = ""
    kiro_identity_provider: str = ""
    kiro_region: str = ""
    # When set, kiro-cli authenticates via this API key (Pro+, headless) and the
    # device-code auth flow is skipped entirely. Injected as an env var into crew
    # containers at creation. Unset (default) => device-code flow is used.
    kiro_api_key: str = ""

    # ── Portal secret (TRN-107) ──────────────────────────────────────────────
    # Shared secret between ga-portal (Caddy) and ga-transport. Caddy injects
    # X-Transport-Token on every upstream request; transport rejects any request
    # that is missing or has a wrong X-Transport-Token value.
    # Loaded at startup from /run/secrets/ga-transport-secret via _load_transport_secret().
    ga_transport_secret: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        """Read every configured env var and construct a Config instance.

        This is the ONLY place the transport reads runtime config from the
        environment. Defaults here MUST match the field defaults above.
        """
        return cls(
            host=os.environ.get("HOST", "0.0.0.0"),
            port=int(os.environ.get("PORT", "64057")),
            ga_host_url=os.environ.get("GA_HOST_URL", ""),
            transport_data_dir=os.environ.get("TRANSPORT_DATA_DIR", "/data"),
            podman_socket=os.environ.get(
                "PODMAN_SOCKET", "/run/user/1000/podman/podman.sock"
            ),
            kc_image=os.environ.get("KC_IMAGE", "localhost/spec-ops:latest"),
            kc_base_image=os.environ.get(
                "KC_BASE_IMAGE", "ghcr.io/kirodotdev/kirocrew:0.5.0"
            ),
            ga_max_crews=int(os.environ.get("GA_MAX_CREWS", "20")),
            ga_max_active_crews=int(os.environ.get("GA_MAX_ACTIVE_CREWS", "3")),
            ga_idle_timeout_secs=int(os.environ.get("GA_IDLE_TIMEOUT_SECS", "300")),
            ga_crew_agent=os.environ.get("GA_CREW_AGENT", "kiro"),
            ga_file_ttl_secs=int(os.environ.get("GA_FILE_TTL_SECS", "300")),
            ga_pickup_max_poll_secs=int(
                os.environ.get("GA_PICKUP_MAX_POLL_SECS", "30")
            ),
            kc_model_override=os.environ.get("KC_MODEL_OVERRIDE", ""),
            kc_model_default=os.environ.get("KC_MODEL_DEFAULT", ""),
            ga_min_free_mem_gb=float(os.environ.get("GA_MIN_FREE_MEM_GB", "2.0")),
            ga_memory_wait_secs=int(os.environ.get("GA_MEMORY_WAIT_SECS", "60")),
            ga_spawn_min_memory_gb=float(
                os.environ.get("GA_SPAWN_MIN_MEMORY_GB", "1.5")
            ),
            ga_resource_pressure_gb=float(
                os.environ.get("GA_RESOURCE_PRESSURE_GB", "2.0")
            ),
            ga_resource_critical_gb=float(
                os.environ.get("GA_RESOURCE_CRITICAL_GB", "1.0")
            ),
            ga_subagent_timeout_secs=int(
                os.environ.get("GA_SUBAGENT_TIMEOUT_SECS", "3600")
            ),
            ga_subagent_max_turns=int(
                os.environ.get("GA_SUBAGENT_MAX_TURNS", "200")
            ),
            kc_gateway_token_ttl=_validate_token_ttl(os.environ.get("KC_GATEWAY_TOKEN_TTL", "24h")),
            ga_dashboard_port_range_start=int(os.environ.get("GA_DASHBOARD_PORT_RANGE_START", "64058")),
            ga_dashboard_port_range_size=int(os.environ.get("GA_DASHBOARD_PORT_RANGE_SIZE", "50")),
            ga_tls_min_version=os.environ.get("GA_TLS_MIN_VERSION", "1.2").strip(),
            ga_tls_certfile=os.environ.get("GA_TLS_CERTFILE", "").strip(),
            ga_tls_keyfile=os.environ.get("GA_TLS_KEYFILE", "").strip(),
            ga_enable_security_headers=_env_bool_default_on(
                "GA_ENABLE_SECURITY_HEADERS"
            ),
            ga_enforce_https_redirect=_env_bool_default_off(
                "GA_ENFORCE_HTTPS_REDIRECT"
            ),
            ga_csp_enforce=_env_bool_default_off("GA_CSP_ENFORCE"),
            ga_portal_admin_url=os.environ.get("GA_PORTAL_ADMIN_URL", "http://ga-portal:2019").strip(),
            ga_portal_tls_mode=_validate_caddy_tls_mode(
                os.environ.get("GA_PORTAL_TLS_MODE", "internal").strip()
            ),
            ga_portal_domain=os.environ.get("GA_PORTAL_DOMAIN", "").strip(),
            ga_portal_port=int(os.environ.get("GA_PORTAL_PORT", "64057")),
            ga_portal_session_ttl_secs=int(os.environ.get("GA_PORTAL_SESSION_TTL_SECS", "86400")),
            kiro_license=os.environ.get("KIRO_LICENSE", ""),
            kiro_identity_provider=os.environ.get("KIRO_IDENTITY_PROVIDER", ""),
            kiro_region=os.environ.get("KIRO_REGION", ""),
            kiro_api_key=os.environ.get("KIRO_API_KEY", ""),
        )
