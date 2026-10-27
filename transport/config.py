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

import ipaddress
import logging
import math
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
        value = float(raw)
    except (ValueError, TypeError):
        raise ConfigError(
            f"Environment variable {name}={raw!r} cannot be parsed as a float"
        ) from None
    # float() accepts "nan" and "inf"; a NaN threshold never compares true, so
    # a gate set to it would silently never trip.
    if not math.isfinite(value):
        raise ConfigError(f"Environment variable {name}={raw!r} must be a finite number")
    return value


_config_logger = logging.getLogger(__name__)


def _parse_trusted_proxy_cidr(raw: str) -> list:
    """Parse a comma-separated list of CIDR strings into ``ip_network`` objects.

    Returns an empty list when ``raw`` is blank (default — no trusted proxies).
    Raises ``ConfigError`` if any entry is not a valid CIDR.
    """
    if not raw or not raw.strip():
        return []
    networks = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            raise ConfigError(
                f"GA_TRUSTED_PROXY_CIDR contains invalid CIDR {entry!r}"
            ) from None
    return networks


_CADDY_TLS_MODES: frozenset[str] = frozenset({"internal", "tailscale", "acme", "off"})
_ACP_BACKEND_VALUES: frozenset[str] = frozenset({"kiro", "claude", "codex"})
_ALWAYS_ENABLED_BACKEND = "kiro"
_RETIRED_BACKEND_FLAGS: tuple[str, ...] = ("GA_INCLUDE_CLAUDE_AGENT", "GA_INCLUDE_CODEX_AGENT")
_REINSTALL_HINT = "Re-run `ghostship install` after changing these settings."


def _parse_ga_crew_agent(raw: str) -> tuple[str, ...]:
    """Normalise GA_CREW_AGENT (comma-separated) into an ordered tuple of backends.

    Splits on commas, strips, lowercases, and drops empty entries and duplicates.
    Kiro is always included (appended if not listed). The first listed entry
    is the runtime default backend.

    Raises ConfigError for a name outside _ACP_BACKEND_VALUES.
    """
    seen: list[str] = []
    for entry in raw.split(","):
        name = entry.strip().lower()
        if not name or name in seen:
            continue
        if name not in _ACP_BACKEND_VALUES:
            raise ConfigError(
                f"GA_CREW_AGENT contains unknown backend {name!r}; "
                f"valid names are {sorted(_ACP_BACKEND_VALUES)}"
            )
        seen.append(name)
    if not seen:
        seen = [_ALWAYS_ENABLED_BACKEND]
    elif _ALWAYS_ENABLED_BACKEND not in seen:
        # Kiro is always enabled — append at end so the first entry remains the default
        seen.append(_ALWAYS_ENABLED_BACKEND)
    return tuple(seen)


def parse_agent_backends(raw: str) -> tuple[str, ...]:
    """Normalise GA_AGENT_BACKENDS into the optional backends it enables.

    Deprecated alias for _parse_ga_crew_agent for the parity test (TRN-202).
    Splits on commas, trims, lowercases, and drops empty entries, duplicates
    and kiro (always enabled). Returns the remaining names in first-listed
    order. bin/lib/agent_backends.sh applies the same rules on the
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
    """Fail on GA_INCLUDE_*_AGENT, replaced by GA_CREW_AGENT (TRN-202, consolidated TRN-213).

    Present with any non-empty value counts, including "false": a stale flag
    must never look like it enabled something.
    """
    for name in _RETIRED_BACKEND_FLAGS:
        if os.environ.get(name, "").strip():
            raise ConfigError(
                f"{name} is retired. Enable backends with GA_CREW_AGENT "
                f"(for example GA_CREW_AGENT=claude) instead. {_REINSTALL_HINT}"
            )


def _read_ga_crew_agent() -> str:
    """Read the GA_CREW_AGENT value with deprecation fallback to GA_CREW_ACP_BACKEND.

    Resolution order:
    1. GA_CREW_AGENT — new consolidated var (ACP backend to build/run)
    2. GA_CREW_ACP_BACKEND — deprecated alias, logs a warning, maps to GA_CREW_AGENT
    3. Default: "kiro"
    """
    value = os.environ.get("GA_CREW_AGENT", "").strip()
    if value:
        return value
    legacy = os.environ.get("GA_CREW_ACP_BACKEND", "").strip()
    if legacy:
        _config_logger.warning(
            "GA_CREW_ACP_BACKEND is deprecated — use GA_CREW_AGENT instead. "
            "Mapping GA_CREW_ACP_BACKEND=%r → GA_CREW_AGENT for this run. %s",
            legacy,
            _REINSTALL_HINT,
        )
        return legacy
    return "kiro"


# Settings that only apply to one optional backend, for the inert-setting
# warnings. Kiro's settings are never inert because kiro is always enabled.
_BACKEND_SETTINGS: dict[str, tuple[str, ...]] = {
    "claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN"),
    "codex": ("OPENAI_API_KEY", "OPENAI_BASE_URL"),
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
    # Derive the enabled set from ga_crew_agent (comma-separated).
    enabled_backends = frozenset(
        name.strip().lower()
        for name in cfg.ga_crew_agent.split(",")
        if name.strip()
    )
    inert: list[str] = []
    for backend, settings in _BACKEND_SETTINGS.items():
        if backend in enabled_backends:
            continue
        # Config field names mirror env var names lowercased (see module docstring).
        inert.extend(name for name in settings if getattr(cfg, name.lower(), ""))
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


def is_loopback(host: str) -> bool:
    """True for an unset host, ``localhost``, ``::1`` and ``127.0.0.0/8``.

    Mirrors ``is_loopback`` in bin/lib/yaml_config.py, which install.sh uses
    for the same check, so install time and transport startup agree.
    """
    host = (host or "").strip()
    if not host or host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _is_wildcard(host: str) -> bool:
    return host.strip("[]") in ("0.0.0.0", "::")


def api_key_exposure(api_key: str, config: "Config") -> tuple[str, str] | None:
    """Decide whether the transport may start without an API key.

    The check is on ga-portal's published address (``ga_portal_host``, the
    operator's HOST), never on the transport's own in-container listen address.
    Returns None when there is nothing to report, ``("warning", msg)`` for the
    explicit opt-out (``network.api_key: false``) on a non-loopback portal, and
    ``("error", msg)`` when a non-loopback portal has no key and no opt-out.
    """
    if api_key or is_loopback(config.ga_portal_host):
        return None
    if config.ga_api_key_disabled:
        return (
            "warning",
            "No API key is configured (network.api_key: false) and ga-portal is "
            f"published on {config.ga_portal_host} — MCP endpoints are accessible "
            "without authentication to anyone who can reach that address.",
        )
    return (
        "error",
        f"Refusing to start: ga-portal is published on {config.ga_portal_host} with "
        "no API key. Set network.api_key (or --api-key), set network.host: "
        "127.0.0.1, or set network.api_key: false to accept unauthenticated access.",
    )


@dataclass
class Config:
    """Transport runtime configuration.

    Defaults mirror the literal defaults previously inlined in
    `server.py`'s `os.environ.get(...)` calls. No behaviour change.
    """

    # ── Network ──────────────────────────────────────────────────────────────
    # The transport's own in-container listen address. Fixed by compose.yml —
    # NOT the operator's HOST, which is where ga-portal publishes (portal-only-host).
    ga_transport_bind: str = "0.0.0.0"
    # The operator's HOST: the address ga-portal publishes on. Used only for the
    # API-key exposure check and the public URL fallback, never as a bind address.
    ga_portal_host: str = "127.0.0.1"
    port: int = 64057
    ga_host_url: str = ""
    # network.api_key: false — authentication explicitly disabled by the operator.
    ga_api_key_disabled: bool = False

    # ── Storage / runtime ────────────────────────────────────────────────────
    podman_socket: str = "/run/user/1000/podman/podman.sock"

    # ── Images ───────────────────────────────────────────────────────────────
    kc_image: str = "localhost/spec-ops:latest"
    # Upstream base image used for ephemeral containers that only need kiro-cli
    # (e.g. login containers). Must match the FROM pin in
    # crews/_base/admission/Containerfile.
    # 2026-10-26: bumped v0.9.0 → v0.10.0 stable (TRN-271). Multi-arch index
    # digest — resolves correctly on amd64 (starport/Linux) and arm64 (corsair/Mac).
    kc_base_image: str = "ghcr.io/kirodotdev/kirocrew@sha256:b6d0b9a3a666df30d99fcadc6a71ab83cbf4ed1c6521e1b81f0333c5553f3e90"

    # ── Crew lifecycle ───────────────────────────────────────────────────────
    ga_max_crews: int = 20
    ga_max_active_crews: int = 3
    ga_idle_timeout_secs: int = 300

    # ── Model ────────────────────────────────────────────────────────────────
    # Global override removed in TRN-257 (a global model is a footgun across
    # backends with different namespaces). `kc_model_default` is the sole global
    # knob — the lowest-precedence fallback. Per-backend control lives in the
    # kc_model_<backend>_override / _default fields below.
    kc_model_default: str = ""

    # ── Per-backend model control (TRN-257) ──────────────────────────────────
    # Resolved at spawn time into the precedence chain:
    #   dispatch > backend_override > per-agent > backend_default > model.default > built-in
    # `override` forces every agent on that backend to the named model; `default`
    # is that backend's fallback when no per-agent model is set. Empty = unset.
    kc_model_kiro_override: str = ""
    kc_model_kiro_default: str = ""
    kc_model_claude_override: str = ""
    kc_model_claude_default: str = ""
    kc_model_codex_override: str = ""
    kc_model_codex_default: str = ""

    # ── Memory gate / thresholds ─────────────────────────────────────────────
    ga_min_free_mem_gb: float = 2.0
    ga_spawn_min_memory_gb: float = 1.5
    ga_resource_pressure_gb: float = 2.0
    ga_resource_critical_gb: float = 1.0
    # Consecutive memory-pressure check-in cycles before the transport mails
    # the Admiral (edge-triggered escalation; see TRN-225).
    ga_spawn_pressure_escalate_cycles: int = 3

    # ── Subagent timeouts ────────────────────────────────────────────────────
    ga_subagent_timeout_secs: int = 3600

    # ── Crew UI port allocation ───────────────────────────────────────────────
    # Dashboard access is provided exclusively by ga-portal (Caddy). The port
    # range config is retained because Portal still uses it via the transport's
    # port pool.
    ga_dashboard_port_range_start: int = 64058
    ga_dashboard_port_range_size: int = 64
    ga_dashboard_default: bool = False

    # ── Transport security ────────────────────────────────────────────────────
    ga_tls_certfile: str = ""
    ga_tls_keyfile: str = ""
    # Comma-separated list of CIDR blocks whose connections are trusted to
    # supply an accurate X-Forwarded-For header (H-2 / TRN-272). When empty
    # (default) XFF is never trusted — safe for loopback-only and direct
    # deployments. Set to e.g. "10.0.0.0/8,172.16.0.0/12" when operating
    # behind a load balancer or Caddy on a different host.
    ga_trusted_proxy_cidr: str = ""
    # When True (default False), refuse to start when GA_TRANSPORT_SECRET is absent
    # and the transport bind address is non-loopback. When False, emit a CRITICAL
    # log but continue (warn-only). Set GA_REQUIRE_SECRET_ON_EXTERNAL_BIND=true
    # to harden production deployments.
    ga_require_secret_on_external_bind: bool = False

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
    # GA_CREW_AGENT: the ACP backend(s) to build and run. Comma-separated list;
    # first entry is the runtime default. Values: "kiro" (default), "claude",
    # "codex", "opencode". Kiro is always in the set (prepended if absent).
    # Deprecated aliases: GA_CREW_ACP_BACKEND → read with warning in from_env().
    # GA_AGENT_BACKENDS is install-time only (handled in install.sh).
    ga_crew_agent: str = "kiro"

    # ANTHROPIC_API_KEY: Anthropic API key injected into crew containers
    # when GA_CREW_ACP_BACKEND=claude. Optional when using Claude OAuth login
    # (ga-claude-auth). When set, takes precedence over OAuth credentials.
    # When neither API key nor OAuth credentials are present at launch time,
    # launch() returns not_authenticated with a login URL (TRN-170).
    anthropic_api_key: str = ""

    # ANTHROPIC_BASE_URL: optional Anthropic-compatible endpoint URL
    # injected as ANTHROPIC_BASE_URL into Claude-backend crew containers.
    # When set, allows operators to redirect crew traffic to a local LLM
    # proxy (litellm, OpenRouter, LM Studio, etc.) without image changes.
    # Has no effect when GA_CREW_ACP_BACKEND != "claude". Default: unset.
    anthropic_base_url: str = ""

    # CLAUDE_CODE_OAUTH_TOKEN: long-lived token from `claude setup-token`,
    # delivered as the ga-claude-code-oauth-token Podman secret and injected into
    # Claude-backend crews when ANTHROPIC_API_KEY is unset. Takes
    # precedence over ga-claude-auth (TRN-226). "" in production; the transport
    # reads the secret file. Kept here for the inert-setting warning.
    claude_code_oauth_token: str = ""

    # OPENAI_API_KEY: OpenAI API key injected under the same name into crew
    # containers when GA_CREW_ACP_BACKEND=codex. Optional when using Codex OAuth
    # login (ga-codex-auth). When set, takes precedence over OAuth credentials.
    # When neither API key nor OAuth credentials are present at launch time,
    # launch() returns not_authenticated with a login URL (TRN-172, mirrors
    # the TRN-170 Claude model).
    openai_api_key: str = ""

    # OPENAI_BASE_URL: optional OpenAI-compatible endpoint URL injected
    # as OPENAI_BASE_URL into Codex-backend crew containers. When set, redirects
    # crew traffic to an OpenAI-compatible endpoint without image changes.
    # Has no effect when GA_CREW_ACP_BACKEND != "codex". Default: unset.
    openai_base_url: str = ""

    # ── kiro-cli identity ────────────────────────────────────────────────────
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

    # ── Fields whose values must never appear in logs or repr ────────────────
    # SEC-3: non-empty values of these fields are masked by __repr__ so that any
    # log call including repr(cfg)/str(cfg) emits "***" instead of a live
    # credential. Backend credentials are now managed by CredentialStore, not
    # Config, so only the transport bearer key field remains here (TRN-233).
    _SECRET_FIELDS = (
        "kiro_api_key",
    )

    def __repr__(self) -> str:
        import dataclasses as _dc

        parts = []
        for f in _dc.fields(self):
            value = getattr(self, f.name)
            if f.name in self._SECRET_FIELDS and value:
                value = "***"
            parts.append(f"{f.name}={value!r}")
        return f"{type(self).__name__}({', '.join(parts)})"

    def public_base_url(self) -> str:
        """The transport's public base URL, without a trailing slash.

        ``GA_HOST_URL`` when set (install.sh always sets it). Otherwise derived
        from the portal's published address: ``http://localhost:{PORT}`` for a
        loopback or wildcard HOST, ``http://{HOST}:{PORT}`` for a specific one.
        """
        if self.ga_host_url:
            return self.ga_host_url.rstrip("/")
        host = (self.ga_portal_host or "").strip()
        if is_loopback(host) or _is_wildcard(host):
            return f"http://localhost:{self.port}"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.port}"

    @classmethod
    def from_env(cls) -> "Config":
        """Read every configured env var and construct a Config instance.

        This is the ONLY place the transport reads runtime config from the
        environment. Defaults here MUST match the field defaults above.
        """
        # Backend checks run first: retired flags get their own message.
        _reject_retired_backend_flags()
        _raw_ga_crew_agent = _read_ga_crew_agent()
        # Normalise: parse, validate, and reconstruct as comma-joined canonical string
        # (always includes kiro).
        _normalized = _parse_ga_crew_agent(_raw_ga_crew_agent)
        ga_crew_agent = ",".join(_normalized)
        return cls(
            ga_transport_bind=os.environ.get("GA_TRANSPORT_BIND", "0.0.0.0"),
            ga_portal_host=os.environ.get("GA_PORTAL_HOST", "127.0.0.1"),
            port=_env_int("PORT", "64057"),
            ga_host_url=os.environ.get("GA_HOST_URL", ""),
            ga_api_key_disabled=_env_bool_default_off("GA_API_KEY_DISABLED"),
            podman_socket=os.environ.get(
                "PODMAN_SOCKET", "/run/user/1000/podman/podman.sock"
            ),
            kc_image=os.environ.get("KC_IMAGE", "localhost/spec-ops:latest"),
            kc_base_image=os.environ.get("KC_BASE_IMAGE", "ghcr.io/kirodotdev/kirocrew@sha256:b6d0b9a3a666df30d99fcadc6a71ab83cbf4ed1c6521e1b81f0333c5553f3e90"),
            ga_max_crews=_env_int("GA_MAX_CREWS", "20"),
            ga_max_active_crews=_env_int("GA_MAX_ACTIVE_CREWS", "3"),
            ga_idle_timeout_secs=_env_int("GA_IDLE_TIMEOUT_SECS", "300"),
            kc_model_default=os.environ.get("KC_MODEL_DEFAULT", ""),
            kc_model_kiro_override=os.environ.get("KC_MODEL_KIRO_OVERRIDE", ""),
            kc_model_kiro_default=os.environ.get("KC_MODEL_KIRO_DEFAULT", ""),
            kc_model_claude_override=os.environ.get("KC_MODEL_CLAUDE_OVERRIDE", ""),
            kc_model_claude_default=os.environ.get("KC_MODEL_CLAUDE_DEFAULT", ""),
            kc_model_codex_override=os.environ.get("KC_MODEL_CODEX_OVERRIDE", ""),
            kc_model_codex_default=os.environ.get("KC_MODEL_CODEX_DEFAULT", ""),
            ga_min_free_mem_gb=_env_float("GA_MIN_FREE_MEM_GB", "2.0"),
            ga_spawn_min_memory_gb=_env_float("GA_SPAWN_MIN_MEMORY_GB", "1.5"),
            ga_resource_pressure_gb=_env_float("GA_RESOURCE_PRESSURE_GB", "2.0"),
            ga_resource_critical_gb=_env_float("GA_RESOURCE_CRITICAL_GB", "1.0"),
            ga_spawn_pressure_escalate_cycles=_env_int("GA_SPAWN_PRESSURE_ESCALATE_CYCLES", "3"),
            ga_subagent_timeout_secs=_env_int("GA_SUBAGENT_TIMEOUT_SECS", "3600"),
            ga_dashboard_port_range_start=_env_int("GA_DASHBOARD_PORT_RANGE_START", "64058"),
            ga_dashboard_port_range_size=_env_int("GA_DASHBOARD_PORT_RANGE_SIZE", "64"),
            ga_dashboard_default=os.environ.get("GA_DASHBOARD_DEFAULT", "").lower() in ("1", "true", "yes"),
            ga_tls_certfile=os.environ.get("GA_TLS_CERTFILE", "").strip(),
            ga_tls_keyfile=os.environ.get("GA_TLS_KEYFILE", "").strip(),
            ga_trusted_proxy_cidr=os.environ.get("GA_TRUSTED_PROXY_CIDR", "").strip(),
            ga_require_secret_on_external_bind=os.environ.get("GA_REQUIRE_SECRET_ON_EXTERNAL_BIND", "").lower() in ("1", "true", "yes"),
            ga_portal_tls_mode=_validate_caddy_tls_mode(
                os.environ.get("GA_PORTAL_TLS_MODE", "off").strip()
            ),
            ga_portal_domain=os.environ.get("GA_PORTAL_DOMAIN", "").strip(),
            ga_portal_session_ttl_secs=_env_int("GA_PORTAL_SESSION_TTL_SECS", "86400"),
            kiro_identity_provider=os.environ.get("KIRO_IDENTITY_PROVIDER", ""),
            kiro_region=os.environ.get("KIRO_REGION", ""),
            kiro_api_key=os.environ.get("KIRO_API_KEY", ""),
            ga_orders_dir=os.environ.get("GA_ORDERS_DIR", ""),
            ga_crew_agent=ga_crew_agent,
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            anthropic_base_url=os.environ.get("ANTHROPIC_BASE_URL", "").strip(),
            claude_code_oauth_token=os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", "").strip(),
        )

    def validate(self) -> None:
        """No-op. Retained for call-site compatibility. Credential validation is lazy — deferred to launch() time."""
        pass

    @property
    def ga_crew_acp_backend(self) -> str:
        """Compatibility alias: the runtime default ACP backend (first entry of ga_crew_agent)."""
        return self.ga_crew_agent.split(",")[0].strip().lower()

    @property
    def ga_agent_backends(self) -> frozenset:
        """Compatibility alias: frozenset of all enabled backends derived from ga_crew_agent."""
        return frozenset(
            name.strip().lower()
            for name in self.ga_crew_agent.split(",")
            if name.strip()
        )
