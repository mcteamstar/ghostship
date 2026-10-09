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
_ACP_BACKEND_VALUES: frozenset[str] = frozenset({"kiro", "claude", "codex"})


def _validate_acp_backend(value: str) -> str:
    """Validate GA_CREW_ACP_BACKEND against the allowed values.

    On an unrecognised value, raises ConfigError immediately (startup failure).
    """
    if value in _ACP_BACKEND_VALUES:
        return value
    raise ConfigError(
        f"GA_CREW_ACP_BACKEND={value!r} is not one of {sorted(_ACP_BACKEND_VALUES)}; "
        "must be 'kiro', 'claude', or 'codex'"
    )


# Kiro is bundled in every KiroCrew image, so it is always enabled and never a
# build arg. The others are optional backends, enabled by GA_AGENT_BACKENDS.
_ALWAYS_ENABLED_BACKEND = "kiro"
_RETIRED_BACKEND_FLAGS: tuple[str, ...] = ("GA_INCLUDE_CLAUDE_AGENT", "GA_INCLUDE_CODEX_AGENT")
_REINSTALL_HINT = "Re-run `ghostship install` after changing these settings."


def parse_agent_backends(raw: str) -> tuple[str, ...]:
    """Normalise GA_AGENT_BACKENDS into the optional backends it enables.

    Splits on commas, trims, lowercases, and drops empty entries, duplicates
    and kiro (always enabled). Returns the remaining names in first-listed
    order. scripts/lib/agent_backends.sh applies the same rules on the
    install side; the parity test keeps them in step.

    Raises ConfigError for a name outside _ACP_BACKEND_VALUES.
    """
    optional: list[str] = []
    for entry in raw.split(","):
        name = entry.strip().lower()
        if not name or name == _ALWAYS_ENABLED_BACKEND or name in optional:
            continue
        if name not in _ACP_BACKEND_VALUES:
            raise ConfigError(
                f"GA_AGENT_BACKENDS contains unknown backend {name!r}; "
                f"valid names are {sorted(_ACP_BACKEND_VALUES)}"
            )
        optional.append(name)
    return tuple(optional)


def _reject_retired_backend_flags() -> None:
    """Fail on GA_INCLUDE_*_AGENT, replaced by GA_AGENT_BACKENDS (TRN-202).

    Present with any non-empty value counts, including "false": a stale flag
    must never look like it enabled something.
    """
    for name in _RETIRED_BACKEND_FLAGS:
        if os.environ.get(name, "").strip():
            raise ConfigError(
                f"{name} is retired. Enable backends with GA_AGENT_BACKENDS "
                f"(for example GA_AGENT_BACKENDS=claude) instead. {_REINSTALL_HINT}"
            )


def _validate_default_backend(default: str, enabled: frozenset[str]) -> str:
    """Require GA_CREW_ACP_BACKEND to be an enabled backend."""
    if default in enabled:
        return default
    raise ConfigError(
        f"GA_CREW_ACP_BACKEND={default!r} is not enabled: add it to GA_AGENT_BACKENDS "
        f"(enabled: {sorted(enabled)}). {_REINSTALL_HINT}"
    )


# Settings that only apply to one optional backend, for the inert-setting
# warnings. Kiro's settings are never inert because kiro is always enabled.
_BACKEND_SETTINGS: dict[str, tuple[str, ...]] = {
    "claude": ("GA_CREW_ANTHROPIC_API_KEY", "GA_CREW_ANTHROPIC_BASE_URL"),
    "codex": ("GA_CREW_OPENAI_API_KEY", "GA_CREW_OPENAI_BASE_URL"),
}
_BACKEND_CREDENTIAL_FILES: dict[str, str] = {
    "claude": "ga-claude-auth",
    "codex": "ga-codex-auth",
}


def inert_backend_settings(cfg: "Config", stored_credentials: frozenset[str]) -> list[str]:
    """Names of settings and stored credentials that belong to a disabled backend.

    Pure: the caller supplies which credential files exist. Returns names only,
    never values, so the result is safe to log.
    """
    values = {
        "GA_CREW_ANTHROPIC_API_KEY": cfg.ga_crew_anthropic_api_key,
        "GA_CREW_ANTHROPIC_BASE_URL": cfg.ga_crew_anthropic_base_url,
        "GA_CREW_OPENAI_API_KEY": cfg.ga_crew_openai_api_key,
        "GA_CREW_OPENAI_BASE_URL": cfg.ga_crew_openai_base_url,
    }
    inert: list[str] = []
    for backend, settings in _BACKEND_SETTINGS.items():
        if backend in cfg.ga_agent_backends:
            continue
        inert.extend(name for name in settings if values[name])
        if _BACKEND_CREDENTIAL_FILES[backend] in stored_credentials:
            inert.append(_BACKEND_CREDENTIAL_FILES[backend])
    return inert


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
    # Upstream base image used for ephemeral containers that only need kiro-cli
    # (e.g. login containers). Must match the FROM pin in
    # crews/_base/admission/Containerfile.
    kc_base_image: str = "ghcr.io/kirodotdev/kirocrew:0.8.0-insider.8"

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
    # GA_AGENT_BACKENDS: comma-separated optional backends to enable ("claude",
    # "codex"). Kiro is always enabled. Drives the image toolchains at install
    # time and which backends the transport accepts. Default: kiro only.
    ga_agent_backends: frozenset[str] = frozenset({"kiro"})

    # GA_CREW_ACP_BACKEND: the default ACP runtime for new crews. Must be an
    # enabled backend. Valid values: "kiro" (default), "claude", "codex".
    # "kiro" uses the KiroCrew-native kiro-cli agent (existing behaviour).
    # "claude" uses the Claude Code ACP backend (credential: GA_CREW_ANTHROPIC_API_KEY
    # or ga-claude-auth; bypasses the per-call kiro approval gate).
    # "codex" uses the Codex ACP backend (credential: GA_CREW_OPENAI_API_KEY or
    # ga-codex-auth; runs under codex-acp's verified read-only mode, bypassing
    # the approval gate).
    ga_crew_acp_backend: str = "kiro"

    # GA_CREW_ANTHROPIC_API_KEY: Anthropic API key injected into crew containers
    # when GA_CREW_ACP_BACKEND=claude. Optional when using Claude OAuth login
    # (ga-claude-auth). When set, takes precedence over OAuth credentials.
    # When neither API key nor OAuth credentials are present at launch time,
    # launch() returns not_authenticated with a login URL (TRN-170).
    ga_crew_anthropic_api_key: str = ""

    # GA_CREW_ANTHROPIC_BASE_URL: optional Anthropic-compatible endpoint URL
    # injected as ANTHROPIC_BASE_URL into Claude-backend crew containers.
    # When set, allows operators to redirect crew traffic to a local LLM
    # proxy (litellm, OpenRouter, LM Studio, etc.) without image changes.
    # Has no effect when GA_CREW_ACP_BACKEND != "claude". Default: unset.
    ga_crew_anthropic_base_url: str = ""

    # GA_CREW_OPENAI_API_KEY: OpenAI API key injected as OPENAI_API_KEY into crew
    # containers when GA_CREW_ACP_BACKEND=codex. Optional when using Codex OAuth
    # login (ga-codex-auth). When set, takes precedence over OAuth credentials.
    # When neither API key nor OAuth credentials are present at launch time,
    # launch() returns not_authenticated with a login URL (TRN-172, mirrors
    # the TRN-170 Claude model).
    ga_crew_openai_api_key: str = ""

    # GA_CREW_OPENAI_BASE_URL: optional OpenAI-compatible endpoint URL injected
    # as OPENAI_BASE_URL into Codex-backend crew containers. When set, redirects
    # crew traffic to an OpenAI-compatible endpoint without image changes.
    # Has no effect when GA_CREW_ACP_BACKEND != "codex". Default: unset.
    ga_crew_openai_base_url: str = ""

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
        # Backend checks run first and in this order: a retired flag gets its
        # own message rather than a downstream error, and the default backend
        # is checked against the parsed set.
        _reject_retired_backend_flags()
        agent_backends = frozenset(
            (_ALWAYS_ENABLED_BACKEND,) + parse_agent_backends(os.environ.get("GA_AGENT_BACKENDS", ""))
        )
        default_backend = _validate_default_backend(
            _validate_acp_backend(os.environ.get("GA_CREW_ACP_BACKEND", "kiro").strip().lower()),
            agent_backends,
        )
        return cls(
            host=os.environ.get("HOST", "0.0.0.0"),
            port=_env_int("PORT", "64057"),
            ga_host_url=os.environ.get("GA_HOST_URL", ""),
            transport_data_dir=os.environ.get("TRANSPORT_DATA_DIR", "/data"),
            podman_socket=os.environ.get(
                "PODMAN_SOCKET", "/run/user/1000/podman/podman.sock"
            ),
            kc_image=os.environ.get("KC_IMAGE", "localhost/spec-ops:latest"),
            kc_base_image=os.environ.get("KC_BASE_IMAGE", "ghcr.io/kirodotdev/kirocrew:0.8.0-insider.8"),
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
            ga_dashboard_port_range_size=_env_int("GA_DASHBOARD_PORT_RANGE_SIZE", "1024"),
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
            ga_agent_backends=agent_backends,
            ga_crew_acp_backend=default_backend,
            ga_crew_anthropic_api_key=os.environ.get("GA_CREW_ANTHROPIC_API_KEY", ""),
            ga_crew_anthropic_base_url=os.environ.get("GA_CREW_ANTHROPIC_BASE_URL", "").strip(),
            ga_crew_openai_api_key=os.environ.get("GA_CREW_OPENAI_API_KEY", ""),
            ga_crew_openai_base_url=os.environ.get("GA_CREW_OPENAI_BASE_URL", "").strip(),
        )

    def validate(self) -> None:
        """No-op. Retained for call-site compatibility. Credential validation is lazy — deferred to launch() time."""
        pass
