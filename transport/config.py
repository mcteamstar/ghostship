"""Single source of truth for transport runtime configuration.

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
from dataclasses import dataclass


class ConfigError(ValueError):
    """Raised when an environment variable cannot be parsed into its expected type."""


def _env_bool_default_on(name: str) -> bool:
    """Truthy unless explicitly disabled (default: on)."""
    return os.environ.get(name, "1").strip() not in ("0", "false", "")


def _env_bool_default_off(name: str) -> bool:
    """Truthy only when explicitly enabled (default: off)."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: str) -> int:
    """Read an integer env var, raising ConfigError with a clear message on failure."""
    raw = os.environ.get(name, default)
    try:
        return int(raw)
    except (ValueError, TypeError):
        raise ConfigError(
            f"Environment variable {name}={raw!r} cannot be parsed as an integer"
        ) from None


def _env_float(name: str, default: str) -> float:
    """Read a float env var, raising ConfigError with a clear message on failure."""
    raw = os.environ.get(name, default)
    try:
        return float(raw)
    except (ValueError, TypeError):
        raise ConfigError(
            f"Environment variable {name}={raw!r} cannot be parsed as a float"
        ) from None


_config_logger = logging.getLogger(__name__)


_CADDY_TLS_MODES: frozenset[str] = frozenset({"internal", "tailscale", "acme", "off"})
_ACP_BACKEND_VALUES: frozenset[str] = frozenset({"kiro", "claude"})


def _validate_acp_backend(value: str) -> str:
    """Validate GA_CREW_ACP_BACKEND against the two allowed values.

    On an unrecognised value, raises ConfigError immediately (startup failure).
    """
    if value in _ACP_BACKEND_VALUES:
        return value
    raise ConfigError(
        f"GA_CREW_ACP_BACKEND={value!r} is not one of {sorted(_ACP_BACKEND_VALUES)}; "
        "must be 'kiro' or 'claude'"
    )


def _validate_claude_api_key(backend: str, key: str) -> None:
    """Raise ConfigError if Claude backend is selected but no API key is set."""
    if backend == "claude" and not key:
        raise ConfigError(
            "GA_CREW_ACP_BACKEND=claude requires GA_CREW_ANTHROPIC_API_KEY to be set"
        )


def _validate_caddy_tls_mode(value: str, default: str = "off") -> str:
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

    # ── Crew lifecycle ───────────────────────────────────────────────────────
    ga_max_crews: int = 20
    ga_max_active_crews: int = 3
    ga_idle_timeout_secs: int = 300
    ga_crew_agent: str = "kiro"

    # ── Model ────────────────────────────────────────────────────────────────
    kc_model_override: str = ""
    kc_model_default: str = ""

    # ── Memory gate / thresholds ─────────────────────────────────────────────
    ga_min_free_mem_gb: float = 2.0
    ga_spawn_min_memory_gb: float = 1.5
    ga_resource_pressure_gb: float = 2.0
    ga_resource_critical_gb: float = 1.0

    # ── Subagent timeouts ────────────────────────────────────────────────────
    ga_subagent_timeout_secs: int = 3600
    ga_subagent_max_turns: int = 200

    # ── ACP prewarm ──────────────────────────────────────────────────────────
    # Opt-in warm-up of a crew's ACP session ahead of an expected dispatch.
    # ga_prewarm_enabled defaults to False so no behaviour changes on existing
    # installs: the prewarm MCP tool + REST endpoint report ``disabled`` and
    # perform no container start or session fork. ga_prewarm_ttl_secs is the
    # warm-lifetime hint used for the idempotency freshness check; it is capped
    # at the effective session.timeout_secs (currently 300) inside _prewarm_crew
    # so a warm marker can never outlive the idle reaper.
    ga_prewarm_enabled: bool = False
    ga_prewarm_ttl_secs: int = 300

    # ── Crew UI port allocation ───────────────────────────────────────────────
    # Dashboard access is provided exclusively by ga-portal (Caddy). The port
    # range config is retained because Portal still uses it via the transport's
    # port pool.
    ga_dashboard_port_range_start: int = 64058
    ga_dashboard_port_range_size: int = 1024
    ga_dashboard_default: bool = False

    # ── Transport security ────────────────────────────────────────────────────
    ga_tls_min_version: str = "1.2"
    ga_tls_certfile: str = ""
    ga_tls_keyfile: str = ""
    ga_enable_security_headers: bool = True

    # ── Caddy reverse proxy ───────────────────────────────────────────────────
    # ga-portal (Caddy) is a required architectural component: it owns the main
    # HTTPS port and the dashboard port range, and provides the portal →
    # transport → crew proxy path. It is always started by install.sh.
    # TLS mode: internal | tailscale | acme | off
    # - internal (default): Caddy built-in CA; requires a one-time `caddy trust`
    # - tailscale: real certs from Tailscale ACME for .ts.net hostnames
    # - acme: public Let's Encrypt; requires GA_PORTAL_DOMAIN and port 80/443
    # - off: plain HTTP, no TLS
    ga_portal_tls_mode: str = "off"
    # Domain name used for ACME (Let's Encrypt) certificate requests.
    ga_portal_domain: str = ""
    # Session TTL for gs_session cookies (dashboard login); default 24 h.
    ga_portal_session_ttl_secs: int = 86400

    # ── User-defined orders directory ────────────────────────────────────────
    # When set, templates from this directory are merged with the built-in
    # academy/orders/ templates. User-defined templates take precedence on
    # name collision. Unset (default) means only built-in templates are used.
    ga_orders_dir: str = ""

    # ── ACP backend selection ─────────────────────────────────────────────────
    # GA_CREW_ACP_BACKEND: which ACP runtime to use inside crew containers.
    # Valid values: "kiro" (default), "claude".
    # "kiro" uses the KiroCrew-native kiro-cli agent (existing behaviour).
    # "claude" uses the Claude Code ACP backend (requires INCLUDE_CLAUDE_AGENT
    # image and GA_CREW_ANTHROPIC_API_KEY; bypasses per-call kiro approval gate).
    ga_crew_acp_backend: str = "kiro"

    # GA_CREW_ANTHROPIC_API_KEY: Anthropic API key injected into crew containers
    # when GA_CREW_ACP_BACKEND=claude. Required when backend is "claude".
    # Validated at startup — transport exits with ConfigError if
    # GA_CREW_ACP_BACKEND=claude but this is unset.
    ga_crew_anthropic_api_key: str = ""

    # GA_CREW_ANTHROPIC_BASE_URL: optional Anthropic-compatible endpoint URL
    # injected as ANTHROPIC_BASE_URL into Claude-backend crew containers.
    # When set, allows operators to redirect crew traffic to a local LLM
    # proxy (litellm, OpenRouter, LM Studio, etc.) without image changes.
    # Has no effect when GA_CREW_ACP_BACKEND != "claude". Default: unset.
    ga_crew_anthropic_base_url: str = ""

    # GA_INCLUDE_CLAUDE_AGENT: whether the spec-ops image was built with
    # INCLUDE_CLAUDE_AGENT=true. Boolean (default false). Used by install.sh to
    # pass --build-arg INCLUDE_CLAUDE_AGENT=true at image build time.
    ga_include_claude_agent: bool = False

    # ── kiro-cli identity ────────────────────────────────────────────────────
    kiro_license: str = ""
    kiro_identity_provider: str = ""
    kiro_region: str = ""
    # When set, kiro-cli authenticates via this API key (Pro+, headless) and the
    # device-code auth flow is skipped entirely. Injected as an env var into crew
    # containers at creation. Unset (default) => device-code flow is used.
    kiro_api_key: str = ""

    # ── Portal secret ─────────────────────────────────────────────────────────
    # The transport secret is loaded directly via _load_transport_secret() in
    # server.py from the Podman secrets file (/run/secrets/ga-transport-secret).
    # It is NOT part of the Config dataclass — keeping it out of Config avoids
    # accidental logging or serialisation of the plaintext secret value.

    @classmethod
    def from_env(cls) -> "Config":
        """Read every configured env var and construct a Config instance.

        This is the ONLY place the transport reads runtime config from the
        environment. Defaults here MUST match the field defaults above.
        """
        return cls(
            host=os.environ.get("HOST", "0.0.0.0"),
            port=_env_int("PORT", "64057"),
            ga_host_url=os.environ.get("GA_HOST_URL", ""),
            transport_data_dir=os.environ.get("TRANSPORT_DATA_DIR", "/data"),
            podman_socket=os.environ.get(
                "PODMAN_SOCKET", "/run/user/1000/podman/podman.sock"
            ),
            kc_image=os.environ.get("KC_IMAGE", "localhost/spec-ops:latest"),
            ga_max_crews=_env_int("GA_MAX_CREWS", "20"),
            ga_max_active_crews=_env_int("GA_MAX_ACTIVE_CREWS", "3"),
            ga_idle_timeout_secs=_env_int("GA_IDLE_TIMEOUT_SECS", "300"),
            ga_crew_agent=os.environ.get("GA_CREW_AGENT", "kiro"),
            kc_model_override=os.environ.get("KC_MODEL_OVERRIDE", ""),
            kc_model_default=os.environ.get("KC_MODEL_DEFAULT", ""),
            ga_min_free_mem_gb=_env_float("GA_MIN_FREE_MEM_GB", "2.0"),
            ga_spawn_min_memory_gb=_env_float("GA_SPAWN_MIN_MEMORY_GB", "1.5"),
            ga_resource_pressure_gb=_env_float("GA_RESOURCE_PRESSURE_GB", "2.0"),
            ga_resource_critical_gb=_env_float("GA_RESOURCE_CRITICAL_GB", "1.0"),
            ga_subagent_timeout_secs=_env_int("GA_SUBAGENT_TIMEOUT_SECS", "3600"),
            ga_subagent_max_turns=_env_int("GA_SUBAGENT_MAX_TURNS", "200"),
            ga_prewarm_enabled=_env_bool_default_off("GA_PREWARM_ENABLED"),
            ga_prewarm_ttl_secs=_env_int("GA_PREWARM_TTL_SECS", "300"),
            ga_dashboard_port_range_start=_env_int("GA_DASHBOARD_PORT_RANGE_START", "64058"),
            ga_dashboard_port_range_size=1024,
            ga_dashboard_default=os.environ.get("GA_DASHBOARD_DEFAULT", "").lower() in ("1", "true", "yes"),
            ga_tls_min_version=os.environ.get("GA_TLS_MIN_VERSION", "1.2").strip(),
            ga_tls_certfile=os.environ.get("GA_TLS_CERTFILE", "").strip(),
            ga_tls_keyfile=os.environ.get("GA_TLS_KEYFILE", "").strip(),
            ga_enable_security_headers=_env_bool_default_on(
                "GA_ENABLE_SECURITY_HEADERS"
            ),
            ga_portal_tls_mode=_validate_caddy_tls_mode(
                os.environ.get("GA_PORTAL_TLS_MODE", "off").strip()
            ),
            ga_portal_domain=os.environ.get("GA_PORTAL_DOMAIN", "").strip(),
            ga_portal_session_ttl_secs=_env_int("GA_PORTAL_SESSION_TTL_SECS", "86400"),
            kiro_license=os.environ.get("KIRO_LICENSE", ""),
            kiro_identity_provider=os.environ.get("KIRO_IDENTITY_PROVIDER", ""),
            kiro_region=os.environ.get("KIRO_REGION", ""),
            kiro_api_key=os.environ.get("KIRO_API_KEY", ""),
            ga_orders_dir=os.environ.get("GA_ORDERS_DIR", ""),
            ga_crew_acp_backend=_validate_acp_backend(
                os.environ.get("GA_CREW_ACP_BACKEND", "kiro").strip().lower()
            ),
            ga_crew_anthropic_api_key=os.environ.get("GA_CREW_ANTHROPIC_API_KEY", ""),
            ga_crew_anthropic_base_url=os.environ.get("GA_CREW_ANTHROPIC_BASE_URL", "").strip(),
            ga_include_claude_agent=_env_bool_default_off("GA_INCLUDE_CLAUDE_AGENT"),
        )

    def validate(self) -> None:
        """Run cross-field validation that cannot be expressed as a per-field default.

        Called once after from_env() during transport startup. Raises ConfigError
        if GA_CREW_ACP_BACKEND=claude but GA_CREW_ANTHROPIC_API_KEY is unset.
        """
        _validate_claude_api_key(self.ga_crew_acp_backend, self.ga_crew_anthropic_api_key)
