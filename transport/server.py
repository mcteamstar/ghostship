"""Transport MCP server — Ghost Academy crew orchestration endpoint.

Manages KiroCrew crew containers via the Podman socket. No permanently
running kirocrew container — all agent work happens in crew containers
created on demand via launch.

The client (on macOS) connects as "ghostship".

Post-modularisation scope (TRN-242)
------------------------------------
This file owns the thin integration layer:
  - MCP instance creation and ``register_tools`` wiring (tools live in
    ``transport.tools``; captain dispatch/steer lives in
    ``transport.captain_engine``; login HTTP handlers live in
    ``transport.login``).
  - Middleware stack: ``TransportSecretMiddleware``, ``RateLimitMiddleware``,
    ``SecurityHeadersMiddleware``, ``BearerAuthMiddleware`` (imported from
    ``transport.auth``).
  - Proxy HTTP handlers for the Caddy portal and the MCP session gate
    (``_proxy_*``).
  - Route assembly and the Starlette app object.
  - Health endpoint.
  - ``__main__`` entry point: config validation, TLS wiring, uvicorn startup,
    and Caddy/dashboard re-registration on restart.

MCP tools and resources (registered by ``transport.tools.register_tools``):
  crews      — list live crews
  launch     — summon a new crew container + workspace
  dispatch   — send a task to an agent in a named crew
  pickup     — check progress or collect result
  captain    — supervise standing orders inside one crew
  steer      — redirect a running task or continue a completed one
  nuke       — tear down a crew container + volumes
  schedule   — create a recurring task on a named crew
  evac       — extract files, diffs, or git bundles from a crew workspace
  supply     — get a presigned URL to deliver files into a crew workspace

  transport://agents       — available agents and their roles
  transport://compositions — available crew compositions for launch
  transport://orders       — built-in standing-order templates
  transport://version      — transport version and per-crew image versions
  transport://jobs         — scheduled jobs across all running crews

Auth flow:
  On first launch (no ga-kiro-auth file), the crew container initiates
  kiro-cli login and returns a device auth URL. After the user completes
  the flow, launch is called again to finish setup and save the auth
  rows to the ga-kiro-auth file for future launches.

  On subsequent launches, auth rows are read from the ga-kiro-auth file
  and injected into each crew's isolated kiro-cli SQLite DB.

Networking:
  All crew containers join ga-starboard. Transport reaches them by name:
  http://gs-<id>:5476. Container-name DNS confirmed working.

Naming:
  ga-* is Ghost Academy infrastructure (ga-transport, ga-portside, ga-starboard) — fixed,
  singleton names. gs-* is per-crew ghostship resources (gs-<crew_id>,
  gs-vol-<crew_id>, gs-home-<crew_id>) — the separate prefix means a
  crew_id can never collide with a ga-* infra name, since they're
  different strings regardless of Podman's own per-resource-kind
  namespacing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import functools
import posixpath
import select
import socket
import tarfile
import dataclasses
import json
import logging
import os
import re
import secrets
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

import httpx2 as httpx
from mcp.server.mcpserver.server import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse, PlainTextResponse, JSONResponse
from starlette.routing import Route, Mount
try:
    from starlette.websockets import WebSocket as _StarletteWebSocket, WebSocketDisconnect as _StarletteWebSocketDisconnect
except (ImportError, AttributeError):
    _StarletteWebSocket = None  # type: ignore[assignment,misc]
    _StarletteWebSocketDisconnect = Exception  # type: ignore[assignment,misc]
try:
    import websockets as _websockets
    import websockets.exceptions as _ws_exceptions
except ImportError:
    _websockets = None  # type: ignore[assignment]
    _ws_exceptions = None  # type: ignore[assignment]
import uvicorn
import asyncio

try:
    import security as _security  # container: both files flat in /app
except ModuleNotFoundError:
    from transport import security as _security  # local dev: transport/ is a package dir

try:
    import auth as _auth  # container: both files flat in /app
    from auth import (  # noqa: F401  re-exported for existing call-sites
        TransportSecretMiddleware,
        RateLimitMiddleware,
        BearerAuthMiddleware,
        SecurityHeadersMiddleware,
        _parse_bearer_token,
        _request_source,
        _parse_rate_limit_var,
        _build_rate_limiters,
        _RATE_LIMIT_DEFAULTS,
    )
except ModuleNotFoundError:
    from transport import auth as _auth  # local dev
    from transport.auth import (  # noqa: F401  re-exported for existing call-sites
        TransportSecretMiddleware,
        RateLimitMiddleware,
        BearerAuthMiddleware,
        SecurityHeadersMiddleware,
        _parse_bearer_token,
        _request_source,
        _parse_rate_limit_var,
        _build_rate_limiters,
        _RATE_LIMIT_DEFAULTS,
    )

try:
    import caddy as _caddy  # container: both files flat in /app
    from caddy import (  # noqa: F401  re-exported for existing call-sites
        CaddyPortal,
        _dashboard_ports_in_use,
        _allocate_dashboard_port,
        _release_dashboard_port,
        _caddy_admin_url,
        _caddy_register_crew,
        _caddy_deregister_crew,
    )
except ModuleNotFoundError:
    from transport import caddy as _caddy  # local dev
    from transport.caddy import (  # noqa: F401  re-exported for existing call-sites
        CaddyPortal,
        _dashboard_ports_in_use,
        _allocate_dashboard_port,
        _release_dashboard_port,
        _caddy_admin_url,
        _caddy_register_crew,
        _caddy_deregister_crew,
    )

try:
    import dashboard as _dashboard  # container: both files flat in /app
    from dashboard import (  # noqa: F401  re-exported for existing call-sites
        DashboardGate,
        _validate_next_url,
    )
except ModuleNotFoundError:
    from transport import dashboard as _dashboard  # local dev
    from transport.dashboard import (  # noqa: F401  re-exported for existing call-sites
        DashboardGate,
        _validate_next_url,
    )

try:
    from config import Config, api_key_exposure, inert_backend_settings, _parse_trusted_proxy_cidr, is_loopback as _is_loopback, _is_wildcard as _is_wildcard_bind  # container: both files flat in /app
except ImportError:
    # Local dev: transport/ is a package dir, and a bare `import config` can
    # resolve to the repo-root config/ namespace package (which has no Config),
    # raising ImportError rather than ModuleNotFoundError — fall back either way.
    from transport.config import Config, api_key_exposure, inert_backend_settings, _parse_trusted_proxy_cidr, is_loopback as _is_loopback, _is_wildcard as _is_wildcard_bind

try:
    from registry import (  # container: flat /app/
        REGISTRY_PATH,
        _NEVER_FIRE_AT,
        _registry_lock,
        _load_registry,
        _save_registry,
        _get_crew_schedules,
        _upsert_crew_schedule,
        _remove_crew_schedule,
        _advance_next_fire_at,
        _get_crew,
        _touch_crew,
        _delete_crew_secret,
        _write_crew_secret,
        _write_batch,
        _get_batch,
        _update_batch_status,
        _delete_batch,
        _find_batch_by_task_ids,
        registry,
    )
except ModuleNotFoundError:
    from transport.registry import (  # local dev
        REGISTRY_PATH,
        _NEVER_FIRE_AT,
        _registry_lock,
        _load_registry,
        _save_registry,
        _get_crew_schedules,
        _upsert_crew_schedule,
        _remove_crew_schedule,
        _advance_next_fire_at,
        _get_crew,
        _touch_crew,
        _delete_crew_secret,
        _write_crew_secret,
        _write_batch,
        _get_batch,
        _update_batch_status,
        _delete_batch,
        _find_batch_by_task_ids,
        registry,
    )

# Named exception raised by _load_registry() on a corrupt registry.
# Imported separately so both import branches above stay byte-identical to
# their prior form; the fallback keeps the module importable if an older
# registry.py without the class is somehow on the path.
try:
    from registry import RegistryCorruptError  # container: flat /app/
except (ModuleNotFoundError, ImportError):
    try:
        from transport.registry import RegistryCorruptError  # local dev
    except (ModuleNotFoundError, ImportError):
        class RegistryCorruptError(RuntimeError):  # pragma: no cover - fallback
            pass

try:
    from podman import (  # container: flat /app/
        ContainerRuntime,
        PodmanClient,
        _get_podman,
        _http,
        _async_http,
        _get_host_memory_gb,
        _get_host_memory_gb_cached,
        _wait_for_memory,
        KIRO_WORKSPACE_ROOT,
    )
except ModuleNotFoundError:
    from transport.podman import (  # local dev
        ContainerRuntime,
        PodmanClient,
        _get_podman,
        _http,
        _async_http,
        _get_host_memory_gb,
        _get_host_memory_gb_cached,
        _wait_for_memory,
        KIRO_WORKSPACE_ROOT,
    )

try:
    from files import (  # container: flat /app/
        CREW_ID_RE,
        _FILE_SECRET,
        _load_or_create_file_secret,
        _resolve_public_url_base,
        _sign_file_url,
        _sign_upload_url,
        _verify_file_token,
        _build_outer_transfer_tar,
        _cleanup_transfer_stage,
        _transfer_upload,
        _ResponseChunkReader,
        _TarMemberStream,
        _handle_file_get,
        _handle_file_put,
        file_routes,
    )
except ModuleNotFoundError:
    from transport.files import (  # local dev
        CREW_ID_RE,
        _FILE_SECRET,
        _load_or_create_file_secret,
        _resolve_public_url_base,
        _sign_file_url,
        _sign_upload_url,
        _verify_file_token,
        _build_outer_transfer_tar,
        _cleanup_transfer_stage,
        _transfer_upload,
        _ResponseChunkReader,
        _TarMemberStream,
        _handle_file_get,
        _handle_file_put,
        file_routes,
    )

try:
    from captain import (  # container: flat /app/
        _CAPTAIN_CHECKIN_JOB_NAME,
        _CAPTAIN_MAILBOX_PATH,
        _ADMIRAL_MAILBOX_PATH,
        _CAPTAIN_CHECKIN_TASK,
        _RAVEN_GATEWAY_ORIENTATION,
        _RAVEN_STORE_RESOLUTION,
        _RAVEN_SELF_CANCEL,
        _resolve_orders_dir,
        _list_order_templates,
        _load_order_template,
        _substitute_placeholders,
        _format_captain_mail,
        _resolve_order_template,
        _append_captain_mail,
        _mail_count,
        _read_all_mail_counts,
        _read_all_mail_subjects,
        _skim_all_mailboxes,
        _read_maildir_subjects_from_tar,
        _read_mail_subjects_archive,
        _captain_jobs,
        _captain_checkin_job,
        _captain_order_lock,
        _captain_order_locks,
        _captain_order_locks_lock,
        _captain_standing_view,
        _read_sentinel_file,
        _parse_sentinel_file,
        _delete_sentinel_file,
    )
except ModuleNotFoundError:
    from transport.captain import (  # local dev
        _CAPTAIN_CHECKIN_JOB_NAME,
        _CAPTAIN_MAILBOX_PATH,
        _ADMIRAL_MAILBOX_PATH,
        _CAPTAIN_CHECKIN_TASK,
        _RAVEN_GATEWAY_ORIENTATION,
        _RAVEN_STORE_RESOLUTION,
        _RAVEN_SELF_CANCEL,
        _resolve_orders_dir,
        _list_order_templates,
        _load_order_template,
        _substitute_placeholders,
        _format_captain_mail,
        _resolve_order_template,
        _append_captain_mail,
        _mail_count,
        _read_all_mail_counts,
        _read_all_mail_subjects,
        _skim_all_mailboxes,
        _read_maildir_subjects_from_tar,
        _read_mail_subjects_archive,
        _captain_jobs,
        _captain_checkin_job,
        _captain_order_lock,
        _captain_order_locks,
        _captain_order_locks_lock,
        _captain_standing_view,
        _read_sentinel_file,
        _parse_sentinel_file,
        _delete_sentinel_file,
    )

# ── Config ────────────────────────────────────────────────────────────────────
# All runtime configuration is read from the environment in exactly one place —
# Config.from_env() (see transport/config.py). The module-level names below are
# thin cfg.<field> reads kept for readability and backwards compatibility with
# the many call sites throughout this module; none of them read os.environ
# directly any more.
cfg = Config.from_env()

# The transport's own listen address inside its container (GA_TRANSPORT_BIND,
# fixed at 0.0.0.0 by compose.yml) so ga-portal can reach it as
# ga-transport:64057. It publishes no host port: exposure is decided solely by
# where ga-portal publishes (the operator's HOST, cfg.ga_portal_host).
HOST = cfg.ga_transport_bind
PORT = cfg.port

# DATA_DIR moved to lifecycle.py (owned there; not used in server.py post-TRN-242).
# REGISTRY_PATH is imported from transport.registry


# KiroCrew gateway port — fixed by upstream, not configurable from this transport.
# Canonical home is transport/constants.py.
try:
    from constants import (  # container: flat /app/
        ADMIRAL_PUBKEY_PATH,
        CREW_CONTAINER_PREFIX,
        CREW_GATEWAY_PORT,
        CREW_HOME_VOLUME_PREFIX,
        CREW_VOLUME_PREFIX,
        GA_PORTSIDE_NETWORK,
        GA_STARBOARD_NETWORK,
        PERSONA_NAMES,
    )
except ModuleNotFoundError:
    from transport.constants import (  # local dev
        ADMIRAL_PUBKEY_PATH,
        CREW_CONTAINER_PREFIX,
        CREW_GATEWAY_PORT,
        CREW_HOME_VOLUME_PREFIX,
        CREW_VOLUME_PREFIX,
        GA_PORTSIDE_NETWORK,
        GA_STARBOARD_NETWORK,
        PERSONA_NAMES,
    )

GA_IDLE_TIMEOUT_SECS = cfg.ga_idle_timeout_secs
# KiroCrew agent name written to config.local.json inside each crew.
# Hardcoded: not operator-configurable (always the built-in KiroCrew agent name).
_KC_AGENT_NAME = "kiro"
# Retained as GA_CREW_AGENT for existing call sites.
GA_CREW_AGENT = _KC_AGENT_NAME
KC_MODEL_DEFAULT = cfg.kc_model_default
GA_MIN_FREE_MEM_GB = cfg.ga_min_free_mem_gb
GA_SPAWN_MIN_MEMORY_GB = cfg.ga_spawn_min_memory_gb
GA_RESOURCE_PRESSURE_GB = cfg.ga_resource_pressure_gb
GA_RESOURCE_CRITICAL_GB = cfg.ga_resource_critical_gb
GA_SPAWN_PRESSURE_ESCALATE_CYCLES = cfg.ga_spawn_pressure_escalate_cycles
GA_SUBAGENT_TIMEOUT_SECS = cfg.ga_subagent_timeout_secs
# Hardcoded: subagent max turns is an internal constant.
_SUBAGENT_MAX_TURNS = 200
GA_SUBAGENT_MAX_TURNS = _SUBAGENT_MAX_TURNS

# ── Crew UI port allocation ───────────────────────────────
# GA_DASHBOARD_PORT_ENABLED was removed; dashboard access is exclusively
# provided by ga-portal (Caddy). Port range retained — Portal uses it.
GA_DASHBOARD_PORT_RANGE_START = cfg.ga_dashboard_port_range_start
GA_DASHBOARD_PORT_RANGE_SIZE = cfg.ga_dashboard_port_range_size

# ── Git author identity passthrough ─────────────────────────────────
# When both vars are set, all four git identity env vars are injected into
# each crew container at setup time so commits carry the operator's identity.
# When unset, per-persona identity (e.g. Ghost <ghost@localhost>) is preserved.
GA_GIT_AUTHOR_NAME = os.environ.get("GA_GIT_AUTHOR_NAME", "").strip()
GA_GIT_AUTHOR_EMAIL = os.environ.get("GA_GIT_AUTHOR_EMAIL", "").strip()

# ── ACP backend ───────────────────────────────────────────────────────────────
# Controls the ACP runtime used inside crew containers.
# "kiro" (default): kiro-cli auth injection (existing behaviour).
# "claude": skip kiro auth, inject ANTHROPIC_API_KEY (or CLAUDE_CODE_OAUTH_TOKEN).
# "codex": skip kiro auth, inject OPENAI_API_KEY.
GA_CREW_ACP_BACKEND = cfg.ga_crew_agent.split(",")[0].strip().lower()
# Credential globals removed (TRN-233 task 2.1) — tools.py resolves credentials
# per-launch via CredentialStore.get(backend). These stale module-level reads
# are no longer needed here.
_ANTHROPIC_BASE_URL = cfg.anthropic_base_url
_OPENAI_BASE_URL = cfg.openai_base_url

# ── Transport security ───────────────────────────────────────────────
# TLS is terminated at the edge (see design.md); the app still emits HSTS and
# security headers so protection does not depend solely on edge config.
#
# GA_TLS_CERTFILE / GA_TLS_KEYFILE: enable direct TLS termination when set.
# Security headers and TLS min version are hardcoded — not operator-configurable.
_TLS_MIN_VERSION = "1.2"
# Retained as GA_TLS_MIN_VERSION for existing call sites.
GA_TLS_MIN_VERSION = _TLS_MIN_VERSION
GA_TLS_CERTFILE = cfg.ga_tls_certfile
GA_TLS_KEYFILE = cfg.ga_tls_keyfile
# Security headers are always active — GA_ENABLE_SECURITY_HEADERS removed.
GA_ENABLE_SECURITY_HEADERS = True

# ── Caddy reverse proxy ───────────────────────────────────
# ga-portal (Caddy) is always present: a ga-portal container owns port bindings
# for the main HTTPS port AND the dashboard port range (64058–64107). The
# transport does NOT start per-port uvicorn listeners; instead it calls the
# Caddy admin API to register/deregister per-crew dashboard servers.

# ── Version ───────────────────────────────────────────────────────────────────

def _read_transport_version() -> str:
    """Resolve the transport version.

    Checks in order:
    1. TRANSPORT_VERSION env var (set via --build-arg at image build time)
    2. VERSION file at repo root (present in dev, absent in the container image)
    3. Fallback sentinel '0.0.0-dev'
    """
    env_version = os.environ.get("TRANSPORT_VERSION", "").strip()
    if env_version:
        return env_version
    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return version_path.read_text().strip()
    except (FileNotFoundError, OSError):
        return "0.0.0-dev"

TRANSPORT_VERSION: str = _read_transport_version()

# _load_or_create_file_secret, _FILE_SECRET, and its _security.register_secret
# registration now live in transport.files (imported above).


def _load_api_key() -> str:
    """Load GA_API_KEY from Podman secret file."""
    _logger = logging.getLogger(__name__)
    secret_path = Path("/run/secrets/ga-api-key")
    try:
        if secret_path.is_file():
            key = secret_path.read_text().strip()
            if key:
                _security.register_secret(key)
                return key
    except Exception:
        pass

    _logger.warning(
        "GA_API_KEY is not set — transport is running WITHOUT authentication. "
        "All MCP tools and file endpoints are publicly accessible. "
        "Set GA_API_KEY to require Bearer token auth."
    )
    return ""


def _enforce_api_key_requirement(api_key: str, config: Config | None = None) -> None:
    """Refuse to start unauthenticated when ga-portal is published beyond loopback.

    The check is on the portal's published address (``GA_PORTAL_HOST``, the
    operator's HOST), never on this process's own in-container listen address,
    which is always 0.0.0.0. A loopback portal needs no key. A non-loopback
    portal needs an API key, or the explicit opt-out ``network.api_key: false``
    (``GA_API_KEY_DISABLED``) — which starts with a WARNING instead.

    Called from the transport startup path, not at import time, so importing
    this module never terminates the process.
    """
    _logger = logging.getLogger(__name__)
    import sys as _sys

    verdict = api_key_exposure(api_key, config or cfg)
    if verdict is None:
        return
    level, message = verdict
    if level == "warning":
        _logger.warning("%s", message)
        return
    _logger.error("%s", message)
    _sys.exit(1)


GA_API_KEY = _load_api_key()

# Construct the CaddyPortal after secrets load, replacing the former
# `_caddy.PORT = PORT` / `_caddy.GA_API_KEY = ...` post-import mutation. PORT and
# the port-range come from cfg; GA_API_KEY is loaded from a mounted Podman secret
# here (a server concern). server.py's own call sites use this instance; the
# caddy module keeps thin wrappers over a module-default portal for isolated use.
_caddy_portal = CaddyPortal(
    port=PORT,
    api_key=GA_API_KEY,
    port_range_start=GA_DASHBOARD_PORT_RANGE_START,
    port_range_size=GA_DASHBOARD_PORT_RANGE_SIZE,
)


def _load_transport_secret() -> str:
    """Load GA_TRANSPORT_SECRET from Podman secret file.

    Reads /run/secrets/ga-transport-secret. Returns empty string when the file is
    absent (allows transport to start in dev/test environments without the
    secret). Registers the value with the log redaction filter when non-empty.

    When the secret is absent and the bind address is non-loopback, logs at
    CRITICAL level. If GA_REQUIRE_SECRET_ON_EXTERNAL_BIND is set, refuses to
    start instead (raises SystemExit).
    """
    _logger = logging.getLogger(__name__)
    secret_path = Path("/run/secrets/ga-transport-secret")
    try:
        if secret_path.is_file():
            secret = secret_path.read_text().strip()
            if secret:
                _security.register_secret(secret)
                return secret
    except Exception:
        pass

    # Check whether the bind address is non-loopback (I-6).
    bind = cfg.ga_transport_bind
    if not _is_loopback(bind) and not _is_wildcard_bind(bind):
        if cfg.ga_require_secret_on_external_bind:
            _logger.critical(
                "GA_TRANSPORT_SECRET is not set and transport is bound to %s "
                "(non-loopback). Refusing to start — set GA_TRANSPORT_SECRET or "
                "set GA_REQUIRE_SECRET_ON_EXTERNAL_BIND=false to allow warn-only.",
                bind,
            )
            raise SystemExit(1)
        _logger.critical(
            "GA_TRANSPORT_SECRET is not set — TransportSecretMiddleware will run "
            "in pass-through mode, but transport is bound to %s (non-loopback). "
            "Set up ga-transport-secret via install.sh for production.",
            bind,
        )
    else:
        _logger.warning(
            "GA_TRANSPORT_SECRET is not set — TransportSecretMiddleware will run in "
            "pass-through mode. Set up ga-transport-secret via install.sh for production."
        )
    return ""


GA_TRANSPORT_SECRET = _load_transport_secret()


# _auth_file_path, _read_auth_file, _write_auth_file moved to
# transport.lifecycle alongside _initiate_login; imported below.
# KIRO_IDENTITY_PROVIDER / KIRO_REGION also moved to lifecycle
# (they drive only the moved _initiate_login device flow).

# KIRO_API_KEY global removed (TRN-233 task 2.1) — credentials are now resolved
# per-launch via CredentialStore.get(backend) in tools.py.

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Scrub any registered secret value from every log record
# secrets-management: secrets excluded from logs and errors).
_security.install_redaction_filter()

try:
    from lifecycle import (  # container: flat /app/
        CREW_CONTAINER_PREFIX,
        CREW_GATEWAY_PORT,
        CREW_HOME_VOLUME_PREFIX,
        CREW_VOLUME_PREFIX,
        Crew,
        CrewUnresponsiveError,
        _NUKED_DURING_RESTART,
        GA_LOGIN_CONTAINER_PREFIX,
        GA_CLAUDE_LOGIN_CONTAINER_PREFIX,
        GA_CODEX_LOGIN_CONTAINER_PREFIX,
        GA_PORTSIDE_NETWORK,
        GA_STARBOARD_NETWORK,
        KIRO_AGENTS_DIR,
        KIRO_CLI_DB,
        KIRO_CREW_DIR,
        KIRO_MCP_JSON,
        KIRO_SKILLS_DIR,
        KIRO_STEERING_DIR,
        MCP_CATALOGUE_DIR,
        SCRIPTS_DIR,
        _SCHEDULE_MONITOR_INTERVAL,
        _cleanup_crew,
        _copy_agents,
        _copy_skills,
        _copy_steering,
        _crew_api,
        _crew_api_with_recovery,
        _crew_cookie,
        _crew_url,
        _cron_activity_since,
        _cron_has_enabled_job,
        _ensure_crew_running,
        _finish_crew_setup,
        _resolve_dispatch_slot,
        _get_recovery_lock,
        _idle_monitor,
        _captain_monitor,
        _inject_auth,
        _inject_claude_auth,
        _inject_codex_auth,
        _inject_policy,
        _mint_cookie,
        _mint_internal_cookie,
        _nuke_login_container,
        _nuke_claude_login_container,
        _nuke_codex_login_container,
        _auth_file_path,
        _read_auth_file,
        _write_auth_file,
        _claude_auth_file_path,
        _claude_auth_exists,
        _write_claude_auth_file,
        _codex_auth_file_path,
        _codex_auth_exists,
        _write_codex_auth_file,
        _initiate_login,
        _initiate_claude_login,
        _initiate_codex_login,
        _poll_claude_login_container,
        _poll_codex_login_container,
        _patch_crew_config,
        _patch_models,
        _pickup_batch,
        _pickup_list,
        _pickup_single,
        _dispatch_batch,
        _record_last_task_at,
        _task_timestamps,
        _task_timestamps_lock,
        _probe_gateway,
        _prewarm_crew,
        _read_auth_from_crew,
        _reconcile_registry,
        _recovery_locks,
        _recovery_locks_lock,
        _refresh_cookie,
        _require_crew,
        _reseed_crew_schedules,
        _schedule_monitor,
        _seed_openspec_store,
        _start_login_container,
        _start_claude_login_container,
        _startup_events,
        _startup_events_lock,
        _to_crew,
        _validate_agent,
        _wait_gateway,
        _write_dashboard_cookie,
    )
except ModuleNotFoundError:
    from transport.lifecycle import (  # local dev
        CREW_CONTAINER_PREFIX,
        CREW_GATEWAY_PORT,
        CREW_HOME_VOLUME_PREFIX,
        CREW_VOLUME_PREFIX,
        Crew,
        CrewUnresponsiveError,
        _NUKED_DURING_RESTART,
        GA_LOGIN_CONTAINER_PREFIX,
        GA_CLAUDE_LOGIN_CONTAINER_PREFIX,
        GA_CODEX_LOGIN_CONTAINER_PREFIX,
        GA_PORTSIDE_NETWORK,
        GA_STARBOARD_NETWORK,
        KIRO_AGENTS_DIR,
        KIRO_CLI_DB,
        KIRO_CREW_DIR,
        KIRO_MCP_JSON,
        KIRO_SKILLS_DIR,
        KIRO_STEERING_DIR,
        MCP_CATALOGUE_DIR,
        SCRIPTS_DIR,
        _SCHEDULE_MONITOR_INTERVAL,
        _cleanup_crew,
        _copy_agents,
        _copy_skills,
        _copy_steering,
        _crew_api,
        _crew_api_with_recovery,
        _crew_cookie,
        _crew_url,
        _cron_activity_since,
        _cron_has_enabled_job,
        _ensure_crew_running,
        _finish_crew_setup,
        _resolve_dispatch_slot,
        _get_recovery_lock,
        _idle_monitor,
        _captain_monitor,
        _inject_auth,
        _inject_claude_auth,
        _inject_codex_auth,
        _inject_policy,
        _mint_cookie,
        _mint_internal_cookie,
        _nuke_login_container,
        _nuke_claude_login_container,
        _nuke_codex_login_container,
        _auth_file_path,
        _read_auth_file,
        _write_auth_file,
        _claude_auth_file_path,
        _claude_auth_exists,
        _write_claude_auth_file,
        _codex_auth_file_path,
        _codex_auth_exists,
        _write_codex_auth_file,
        _initiate_login,
        _initiate_claude_login,
        _initiate_codex_login,
        _poll_claude_login_container,
        _poll_codex_login_container,
        _patch_crew_config,
        _patch_models,
        _pickup_batch,
        _pickup_list,
        _pickup_single,
        _dispatch_batch,
        _record_last_task_at,
        _task_timestamps,
        _task_timestamps_lock,
        _probe_gateway,
        _prewarm_crew,
        _read_auth_from_crew,
        _reconcile_registry,
        _recovery_locks,
        _recovery_locks_lock,
        _refresh_cookie,
        _require_crew,
        _reseed_crew_schedules,
        _schedule_monitor,
        _seed_openspec_store,
        _start_login_container,
        _start_claude_login_container,
        _startup_events,
        _startup_events_lock,
        _to_crew,
        _validate_agent,
        _wait_gateway,
        _write_dashboard_cookie,
    )

# Academy composition/manifest/validation surface — extracted from lifecycle
# to transport/academy.py. server reads COMPOSITION_REGISTRY (in
# resource_compositions), _AGENTS_DIR (in resource_agents), and the helper
# functions. It imports them from academy directly rather than re-through
# lifecycle. Note: tests still dual-patch these names on
# BOTH `lifecycle` and `server` (e.g. patch.object(lifecycle,
# "COMPOSITION_REGISTRY") + patch.object(server, ...)) and also patch
# transport.academy; that dual/triple-patch is intentional pending full
# test migration to patch transport.academy exclusively.
try:
    from academy import (  # container: flat /app/
        COMPOSITION_REGISTRY,
        _AGENTS_DIR,
        _CREW_REGISTRY_PATH,
        _load_composition_registry,
        _load_crew_manifest,
        _manifest_selects,
        _resolve_composition,
        _resolve_image,
        _resolve_manifest_path,
        _substitute_env_vars,
        _validate_academy,
    )
except ImportError:
    # See the ImportError note in lifecycle.py: the repo-root academy/ assets
    # directory shadows the flat-path module as a namespace package in local
    # dev, so `from academy import <name>` raises ImportError there.
    from transport.academy import (  # local dev
        COMPOSITION_REGISTRY,
        _AGENTS_DIR,
        _CREW_REGISTRY_PATH,
        _load_composition_registry,
        _load_crew_manifest,
        _manifest_selects,
        _resolve_composition,
        _resolve_image,
        _resolve_manifest_path,
        _substitute_env_vars,
        _validate_academy,
    )

# The login device-flow state (_login_pending / _login_pending_lock)
# lives in lifecycle and is reassigned by lifecycle._initiate_login. The login
# HTTP handlers below must read/clear that SAME object, so reference it through
# the module (lifecycle._login_pending) rather than importing the value — an
# imported name would fork into a stale server-local copy after reassignment.
try:
    import lifecycle as _lifecycle  # container: flat /app/
except ModuleNotFoundError:
    from transport import lifecycle as _lifecycle  # local dev

try:
    import login  # container: flat /app/
except ModuleNotFoundError:
    from transport import login  # local dev

try:
    import openapi as _openapi  # container: flat /app/
except ModuleNotFoundError:
    from transport import openapi as _openapi  # local dev

mcp = MCPServer(
    name="transport",
    description=(
        "Ghost Academy crew orchestration. Workflow: launch a crew → supply a repo "
        "→ dispatch tasks to agents → pickup results → steer if needed → evac output "
        "→ nuke when done."
    ),
)

# ── Task timestamps ──────────────────────────────────────────────────
# In-memory store for task lifecycle timestamps. Keyed by task_id.
# Lost on transport restart — acceptable per design decision D1.
# _task_timestamps and _task_timestamps_lock live in transport.lifecycle
# alongside the pickup/dispatch helpers; imported above. server's dispatch
# tools mutate the same shared objects.

# ── UI port pool + Caddy admin API ─────────────────────────
# _dashboard_ports_in_use, _allocate_dashboard_port, _release_dashboard_port,
# _caddy_admin_url, _caddy_register_crew, and _caddy_deregister_crew now live in
# transport/caddy.py and are imported at the top of this file. The
# port-pool helpers must still be called while holding _registry_lock.

# ── Dashboard session store ───────────────────────────────
# ── DashboardGate ───────────────────────────────────────────────────
# The dashboard auth/session state cluster (throttle, session store, CSRF token,
# and the port→crew map) and its four HTTP handlers now live in a single
# DashboardGate instance in transport/dashboard.py. Constructed here after
# config/secrets load so its dependencies (session TTL, API key, TLS mode) are
# explicit constructor arguments rather than implicit module globals.
_dashboard_gate = DashboardGate(
    session_ttl_secs=cfg.ga_portal_session_ttl_secs,
    api_key=GA_API_KEY,
    external_url=cfg.public_base_url(),
)

# Per-crew asyncio lock registry serialising concurrent _ensure_crew_running
# call sites in the async proxy handlers, so that concurrent coroutines for
# the same crew do not each dispatch a redundant
# probe-then-start thread. The registry dict itself is populated lazily under a
# threading.Lock because it is also touched from non-async startup paths.
_ensure_running_locks: dict[str, asyncio.Lock] = {}
_ensure_running_locks_lock = threading.Lock()


def _get_ensure_running_lock(crew_id: str) -> asyncio.Lock:
    """Return the per-crew asyncio.Lock for crew_id, creating it lazily.

    Guarded by _ensure_running_locks_lock so concurrent first-time callers do
    not each create a separate lock object for the same crew.
    """
    with _ensure_running_locks_lock:
        lock = _ensure_running_locks.get(crew_id)
        if lock is None:
            lock = asyncio.Lock()
            _ensure_running_locks[crew_id] = lock
        return lock


# _http and _async_http are imported from transport.podman (they are owned by
# that module; proxy handlers below use _async_http).


# ── API-key authentication middleware ─────────────────────────────────────────

# Hop-by-hop headers that must be stripped from forwarded responses per
# standard reverse-proxy practice (RFC 2616 §13.5.1).
_HOP_BY_HOP_HEADERS: frozenset[str] = frozenset({
    "transfer-encoding",
    "connection",
    "keep-alive",
    "te",
    "trailers",
    "upgrade",
    # httpx decompresses gzip/br/zstd transparently when using aread(); strip
    # content-encoding so the browser doesn't try to decompress already-decoded
    # bytes. content-length is also wrong after decompression so strip it too.
    "content-encoding",
    "content-length",
})

# Headers stripped when proxying a request down to a crew's own gateway
# (gs-{crew_id}:5476). Authorization and X-Transport-Token authenticate the
# caller to ga-transport itself — the crew gateway neither needs nor checks
# them, and forwarding them would hand a crew (which shares ga-starboard with
# ga-transport) a credential it could replay directly against the transport's
# own control-plane API. host/cookie are replaced with the crew's own
# mc_token_5476 session cookie immediately after this filter is applied.
_STRIPPED_CREW_PROXY_HEADERS: frozenset[str] = frozenset({
    "host",
    "cookie",
    "authorization",
    "x-transport-token",
})


def _extract_crew_proxy_parts(path: str) -> tuple[str, str, str] | None:
    """Parse /crews/{crew_id}/{segment}/{sub_path} into (crew_id, segment, sub_path).

    Returns None if the path does not match the expected structure.

    Examples:
        /crews/demo/ui           → ("demo", "ui", "")
        /crews/demo/ui/          → ("demo", "ui", "")
        /crews/demo/ui/app/page  → ("demo", "ui", "app/page")
        /crews/demo/api/spawn    → ("demo", "api", "spawn")
    """
    # Expect at least /crews/<id>/<segment>
    parts = path.lstrip("/").split("/")
    if len(parts) < 3 or parts[0] != "crews":
        return None
    crew_id = parts[1]
    segment = parts[2]
    sub_path = "/".join(parts[3:])
    return crew_id, segment, sub_path


_QS_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _sanitise_query_string(raw: bytes) -> str:
    """Decode query string and strip control characters.

    latin-1 is used to preserve non-ASCII bytes faithfully (percent-encoded
    values in a query string are ASCII anyway). Control characters (0x00-0x1F,
    0x7F) are stripped to prevent CRLF injection into the upstream request
    or a response header.
    """
    return _QS_CONTROL_CHARS.sub("", raw.decode("latin-1"))


def _parse_ttl_seconds(ttl: str) -> int:
    """Parse a KiroCrew TTL string (e.g. ``24h``, ``30m``, ``3600s``, ``2d``,
    or a bare integer meaning seconds) into a number of seconds.

    Falls back to 24h (86400 s) if the value cannot be parsed. Used to compute
    the near-expiry window for transparent cookie refresh.
    """
    if not ttl:
        return 86400
    m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", str(ttl).lower())
    if not m:
        return 86400
    value = int(m.group(1))
    unit = m.group(2) or "s"
    return value * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _jwt_exp(token: str) -> int | None:
    """Return the ``session_exp`` claim (epoch seconds) from a KiroCrew JWT
    without verifying its signature — we trust our own tokens (design.md).

    KiroCrew tokens have two expiry fields:
    - ``exp``: short-lived one-time-URL expiry (~5 min from issue)
    - ``session_exp``: the actual session duration (~24h)

    We use ``session_exp`` for the near-expiry check so we re-mint based on
    session lifetime, not on the token URL TTL.

    Returns None if the token is not a JWT or has no numeric ``session_exp`` claim.
    """
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        # KiroCrew tokens are payload.signature (2 parts), not header.payload.signature.
        # Standard 3-part JWTs use parts[1] as the payload; 2-part tokens use parts[0].
        payload_b64 = parts[0] if len(parts) == 2 else parts[1]
        # Restore base64 padding stripped by JWT's base64url encoding.
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode())
        # Use session_exp (session lifetime ~24h) not exp (one-time token URL ~5min).
        exp = payload.get("session_exp") or payload.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def _cookie_near_expiry(cookie: str) -> bool:
    """True if *cookie*'s JWT ``session_exp`` is within 20% of the configured TTL of
    expiring (i.e. > 80% of the TTL has elapsed). A cookie that is not a JWT,
    has no ``session_exp``, or is already expired is treated as near-expiry so the
    proxy re-mints it (design.md "Token refresh").
    """
    exp = _jwt_exp(cookie)
    if exp is None:
        return True
    ttl_secs = _parse_ttl_seconds("24h")
    remaining = exp - time.time()
    return remaining < 0.20 * ttl_secs


async def _resolve_crew_for_proxy(
    path: str, auto_wake: bool = True
) -> tuple[str, str, dict] | Response:
    """Resolve the crew targeted by a proxy request path.

    Encapsulates the parse + require (+ optional auto-wake) preamble shared by
    the crew proxy handlers. On success returns ``(crew_id, sub_path, crew)``.
    On failure returns a ``Response``:

    - 404 if the path does not parse as a crew proxy path
    - 404 if the crew is unknown
    - 502 if ``auto_wake`` is set and ensuring the crew is running fails

    ``auto_wake`` defaults to True (UI/API/WS handlers proxy to a live crew and
    must wake it first). The dashboard handler passes ``auto_wake=False`` — it
    only needs the parse + require portion.
    """
    parsed = _extract_crew_proxy_parts(path)
    if parsed is None:
        return PlainTextResponse("Not found", status_code=404)
    crew_id, _segment, sub_path = parsed

    try:
        crew = _require_crew(crew_id)
    except (KeyError, ValueError) as e:
        return PlainTextResponse(str(e), status_code=404)

    if auto_wake:
        try:
            async with _get_ensure_running_lock(crew_id):
                crew = await asyncio.to_thread(_ensure_crew_running, crew, crew_id)
        except RuntimeError as e:
            return PlainTextResponse(str(e), status_code=502)
        # TRN-238 QA-2: _ensure_crew_running returns _NUKED_DURING_RESTART when a
        # concurrent nuke() removed the crew's registry entry between container_start
        # and post-start setup. The crew no longer exists — return 410 Gone so
        # callers (UI, WS, API proxy handlers) never receive the sentinel as a dict.
        if crew is _NUKED_DURING_RESTART:
            return PlainTextResponse(
                f"Crew '{crew_id}' was removed while being started",
                status_code=410,
            )

    return crew_id, sub_path, crew


async def _handle_crew_ui_proxy(request: Request) -> Response:
    """Reverse-proxy GET/POST to the crew gateway UI at http://gs-{crew_id}:5476/.

    Route: /crews/{crew_id}/ui  →  http://gs-{crew_id}:5476/
           /crews/{crew_id}/ui/{path}  →  http://gs-{crew_id}:5476/{path}

    - Auto-wakes the crew before proxying.
    - Passes request headers through (minus host, any inbound cookie, and the
      Authorization / X-Transport-Token credentials used to reach ga-transport
      itself — never forwarded to the crew gateway).
    - Injects the crew's ``mc_token_5476`` session cookie on every forwarded
      request so the KiroCrew SPA is pre-authenticated. The cookie is minted
      from ga-transport's IP, satisfying the gateway's IP binding.
    - Transparently re-mints the cookie when it is near expiry (> 80% of TTL
      elapsed) before forwarding, so sessions never interrupt.
    - Streams the upstream response body without buffering.
    - Returns 404 for unknown crew_id.
    """
    resolved = await _resolve_crew_for_proxy(request.scope["path"])
    if isinstance(resolved, Response):
        return resolved
    crew_id, sub_path, crew = resolved

    # Transparently re-mint the session cookie when it is near expiry so the
    # browser session never sees a "Session expired" prompt. Best-effort: a
    # failed refresh falls through to the existing (possibly stale) cookie,
    # and the 401/403 retry below still recovers.
    c = _to_crew(crew_id, crew)
    if _cookie_near_expiry(c.cookie):
        logger.info("UI proxy: cookie near expiry for crew %s — refreshing", crew_id)
        _refresh_cookie(crew, crew_id)

    # Build upstream URL
    upstream_base = f"http://{CREW_CONTAINER_PREFIX}{crew_id}:{CREW_GATEWAY_PORT}"
    upstream_path = f"/{sub_path}" if sub_path else "/"
    query = request.scope.get("query_string", b"")
    upstream_url = upstream_path
    if query:
        upstream_url = f"{upstream_path}?{_sanitise_query_string(query)}"
    upstream_full = f"{upstream_base}{upstream_url}"

    # Forward headers minus _STRIPPED_CREW_PROXY_HEADERS, then inject the
    # crew's session cookie. The cookie is minted from ga-transport's IP so
    # the gateway's IP binding is satisfied — Caddy (ga-portal) proxies here
    # rather than to the crew gateway directly.
    forward_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _STRIPPED_CREW_PROXY_HEADERS
    }
    forward_headers["Cookie"] = _crew_cookie(crew)

    # Proxy and stream, retrying once with a fresh cookie on 401/403 (stale token).
    body = await request.body()
    try:
        async with _async_http.stream(
            request.method,
            upstream_full,
            headers=forward_headers,
            content=body,
        ) as upstream_resp:
            if upstream_resp.status_code in (401, 403):
                await upstream_resp.aread()  # drain so the context can close
                logger.info(
                    "UI proxy: upstream %d for crew %s — refreshing cookie",
                    upstream_resp.status_code, crew_id,
                )
                if _refresh_cookie(crew, crew_id):
                    forward_headers["Cookie"] = _crew_cookie(crew)
                    async with _async_http.stream(
                        request.method,
                        upstream_full,
                        headers=forward_headers,
                        content=body,
                    ) as retry_resp:
                        response_headers = {
                            k: v
                            for k, v in retry_resp.headers.items()
                            if k.lower() not in _HOP_BY_HOP_HEADERS
                        }
                        retry_body = await retry_resp.aread()
                    return Response(
                        content=retry_body,
                        status_code=retry_resp.status_code,
                        headers=response_headers,
                    )
            # Strip hop-by-hop headers from forwarded response
            response_headers = {
                k: v
                for k, v in upstream_resp.headers.items()
                if k.lower() not in _HOP_BY_HOP_HEADERS
            }
            # Read body fully so we can close the upstream context; for large
            # responses this is acceptable given the 60 s timeout constraint.
            body_out = await upstream_resp.aread()
        return Response(
            content=body_out,
            status_code=upstream_resp.status_code,
            headers=response_headers,
        )
    except Exception as e:
        logger.warning("UI proxy error for crew %s: %s", crew_id, e)
        return PlainTextResponse(f"Proxy error: {e}", status_code=502)


async def _handle_crew_ui_ws_proxy(scope: dict, receive, send) -> None:
    """Reverse-proxy a WebSocket upgrade for /crews/{crew_id}/ui/{path} to the
    crew gateway at ws://gs-{crew_id}:5476/{path}.

    Bidirectionally relays text and binary frames between the browser-side
    Starlette WebSocket and the upstream connection opened with
    ``websockets.connect``. The crew's ``mc_token_5476`` session cookie is
    injected on the upstream handshake so the gateway accepts the connection
    from ga-transport's IP. A disconnect on either side tears down the other.
    """
    if _StarletteWebSocket is None or _websockets is None:
        # No WS support available (dependency-free test env) — reject cleanly.
        await send({"type": "websocket.close", "code": 1011})
        return

    ws = _StarletteWebSocket(scope, receive=receive, send=send)

    resolved = await _resolve_crew_for_proxy(scope["path"])
    if isinstance(resolved, Response):
        # Translate the HTTP failure status to a WS close code:
        # 404 (parse error / unknown crew) -> 1008 policy violation;
        # 502 (ensure-running failure) -> 1011 internal error.
        await ws.close(code=1008 if resolved.status_code == 404 else 1011)
        return
    crew_id, sub_path, crew = resolved

    c_ws = _to_crew(crew_id, crew)
    if _cookie_near_expiry(c_ws.cookie):
        _refresh_cookie(crew, crew_id)

    upstream_path = f"/{sub_path}" if sub_path else "/"
    query = scope.get("query_string", b"")
    if query:
        upstream_path = f"{upstream_path}?{_sanitise_query_string(query)}"
    upstream_ws_url = (
        f"ws://{CREW_CONTAINER_PREFIX}{crew_id}:{CREW_GATEWAY_PORT}{upstream_path}"
    )

    # Forward the client's requested subprotocols and inject the session cookie
    # and the internal crew origin (required by KiroCrew's WS origin check).
    # TRN-191: send "http://localhost:{port}" rather than the container hostname
    # (http://gs-{crew_id}:5476). KiroCrew's build_allowed_origins() always
    # includes http://localhost:{port} and http://127.0.0.1:{port} regardless
    # of config, but only adds dashboard.url when token auth middleware is
    # active — which Ghostship's gateway does not use. The Origin header is
    # only checked for WS CSRF; the actual IP-binding uses the TCP connection
    # peer, not the Origin value, so sending localhost is safe.
    subprotocols = ws.scope.get("subprotocols") or []
    crew_origin = f"http://localhost:{CREW_GATEWAY_PORT}"
    handshake_headers = {
        "Cookie": _crew_cookie(crew),
        "Origin": crew_origin,
    }

    # C-2: Accept the client connection ONLY after the upstream connection
    # succeeds. If upstream fails before accept, close with code 1011.
    try:
        async with _websockets.connect(
            upstream_ws_url,
            additional_headers=handshake_headers,
            subprotocols=subprotocols or None,
        ) as upstream:
            await ws.accept(subprotocol=upstream.subprotocol)

            async def _client_to_upstream() -> None:
                while True:
                    msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        await upstream.close()
                        return
                    if msg.get("text") is not None:
                        await upstream.send(msg["text"])
                    elif msg.get("bytes") is not None:
                        await upstream.send(msg["bytes"])

            async def _upstream_to_client() -> None:
                async for message in upstream:
                    if isinstance(message, str):
                        await ws.send_text(message)
                    else:
                        await ws.send_bytes(message)

            done, pending = await asyncio.wait(
                {asyncio.create_task(_client_to_upstream()),
                 asyncio.create_task(_upstream_to_client())},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            # Retrieve and log exceptions from the completed task so Python
            # doesn't emit "Task exception was never retrieved" to stderr.
            # ConnectionClosedError (abnormal upstream close) is expected and
            # logged at DEBUG; other exceptions are logged at WARNING.
            for task in done:
                exc = task.exception()
                if exc is not None:
                    if _ws_exceptions is not None and isinstance(
                        exc, _ws_exceptions.ConnectionClosedError
                    ):
                        logger.debug(
                            "UI WS proxy upstream closed abnormally for crew %s: %s",
                            crew_id, exc,
                        )
                    elif not isinstance(exc, (asyncio.CancelledError,)):
                        logger.debug(
                            "UI WS proxy task finished with error for crew %s: %s",
                            crew_id, exc,
                        )
    except _StarletteWebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("UI WS proxy error for crew %s: %s", crew_id, e)
        # C-2: The upstream connection failed before we accepted the client
        # (ws.accept is now inside the try block, after _websockets.connect succeeds).
        # Send a close frame with code 1011 (internal error) so the client is
        # not left hanging with an unaccepted connection.
        try:
            await send({"type": "websocket.close", "code": 1011})
        except Exception:
            pass
        return
    finally:
        try:
            await ws.close()
        except Exception:
            pass


async def _handle_crew_api_proxy(request: Request) -> Response:
    """Reverse-proxy to the crew gateway REST API at http://gs-{crew_id}:5476/api/{path}.

    Route: /crews/{crew_id}/api/{path}  →  http://gs-{crew_id}:5476/api/{path}

    - Auto-wakes the crew before proxying.
    - Injects the internal session cookie mc_token_5476.
    - On upstream 401/403, refreshes the cookie and retries once (D4).
    - Returns 404 for unknown crew_id.
    """
    resolved = await _resolve_crew_for_proxy(request.scope["path"])
    if isinstance(resolved, Response):
        return resolved
    crew_id, sub_path, crew = resolved

    # Build upstream URL
    upstream_base = f"http://{CREW_CONTAINER_PREFIX}{crew_id}:{CREW_GATEWAY_PORT}"
    api_path = f"/api/{sub_path}" if sub_path else "/api/"
    query = request.scope.get("query_string", b"")
    if query:
        api_path = f"{api_path}?{_sanitise_query_string(query)}"
    upstream_full = f"{upstream_base}{api_path}"

    # Forward headers minus _STRIPPED_CREW_PROXY_HEADERS, then inject session cookie
    forward_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _STRIPPED_CREW_PROXY_HEADERS
    }
    forward_headers["Cookie"] = _crew_cookie(crew)

    body = await request.body()

    async def _do_request(headers: dict) -> httpx.Response:
        return await _async_http.request(
            request.method,
            upstream_full,
            headers=headers,
            content=body,
        )

    try:
        upstream_resp = await _do_request(forward_headers)

        # Single-retry on 401/403 (stale cookie)
        if upstream_resp.status_code in (401, 403):
            logger.info(
                "API proxy: upstream %d for crew %s — refreshing cookie",
                upstream_resp.status_code, crew_id,
            )
            if _refresh_cookie(crew, crew_id):
                # crew dict was mutated by _refresh_cookie
                forward_headers["Cookie"] = _crew_cookie(crew)
                upstream_resp = await _do_request(forward_headers)

        response_headers = {
            k: v
            for k, v in upstream_resp.headers.items()
            if k.lower() not in _HOP_BY_HOP_HEADERS
        }
        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=response_headers,
        )
    except Exception as e:
        logger.warning("API proxy error for crew %s: %s", crew_id, e)
        return PlainTextResponse(f"Proxy error: {e}", status_code=502)





async def _handle_crew_dashboard_post(request: Request) -> Response:
    """POST /crews/{crew_id}/dashboard — allocate a UI port and register with Portal.

    Allocates a port from the configured range, registers it with Portal (Caddy),
    and stores dashboard_port in the registry. Returns {"dashboard_url": "..."}.
    No-op if the crew already has a dashboard — returns the existing dashboard_url.

    Returns 404 for unknown crew. Returns 409 if port pool is exhausted.
    """
    resolved = await _resolve_crew_for_proxy(request.scope["path"], auto_wake=False)
    if isinstance(resolved, Response):
        return resolved
    crew_id, _sub, _crew = resolved

    # H-2: Consolidate the no-op check and port allocation into a single lock
    # section, reading the registry under the lock (not the pre-lock crew dict)
    # to prevent a TOCTOU race that could duplicate port allocation.
    _crew_cookie_val = ""
    dashboard_port: int | None = None
    with registry:
        crew_entry = registry._reg["crews"].get(crew_id)
        if crew_entry is None:
            return PlainTextResponse(f"Crew '{crew_id}' not found", status_code=404)

        # No-op: crew already has a dashboard (checked under the lock).
        existing_port = crew_entry.get("dashboard_port")
        if existing_port is not None:
            _caddy_scheme = "http" if cfg.ga_portal_tls_mode == "off" else "https"
            if cfg.ga_host_url:
                from urllib.parse import urlparse as _urlparse_d
                _ph = _urlparse_d(cfg.ga_host_url)
                dashboard_url = f"{_caddy_scheme}://{_ph.hostname}:{existing_port}/"
            else:
                dashboard_url = f"{_caddy_scheme}://localhost:{existing_port}/"
            return JSONResponse({"dashboard_url": dashboard_url})

        # Allocate a new port under the same lock so allocation and registry
        # write are atomic (prevents duplicate port allocation from concurrent
        # POSTs).
        try:
            dashboard_port = _caddy_portal.allocate_port()
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=409)

        registry._reg["crews"][crew_id]["dashboard_port"] = dashboard_port
        # Extract cookie value now, while still holding the lock.
        _crew_cookie_val = registry._reg["crews"][crew_id].get("cookie", "")

    # C-1: Call _caddy_register_crew AFTER releasing _registry_lock.
    # This avoids holding the lock across up to 7 s of blocking I/O.
    # Portal (Caddy) is the sole dashboard proxy.
    # GA_PORTAL_TLS_MODE=off means plain HTTP; all other modes use HTTPS.
    _caddy_scheme = "http" if cfg.ga_portal_tls_mode == "off" else "https"
    if cfg.ga_host_url:
        from urllib.parse import urlparse as _urlparse_d2
        _ph = _urlparse_d2(cfg.ga_host_url)
        dashboard_url = f"{_caddy_scheme}://{_ph.hostname}:{dashboard_port}/"
    else:
        dashboard_url = f"{_caddy_scheme}://localhost:{dashboard_port}/"

    _caddy_portal.register_crew(crew_id, dashboard_port, crew_cookie=_crew_cookie_val)
    # Store port→crew mapping for forward_auth lookups.
    _dashboard_gate.register_port(crew_id, dashboard_port)

    logger.info(
        "POST /crews/%s/dashboard — UI port %d, dashboard_url=%s",
        crew_id, dashboard_port, dashboard_url,
    )
    return JSONResponse({"dashboard_url": dashboard_url})


async def _handle_crew_dashboard_delete(request: Request) -> Response:
    """DELETE /crews/{crew_id}/dashboard — stop the UI listener and release the port.

    Stops the per-port uvicorn server, releases the port back to the pool, and
    clears dashboard_port from the registry. Returns {"dashboard_url": null}.
    No-op if the crew has no dashboard — returns {"dashboard_url": null} without error.

    Returns 404 for unknown crew.
    """
    parsed = _extract_crew_proxy_parts(request.scope["path"])
    if parsed is None:
        return PlainTextResponse("Not found", status_code=404)
    crew_id, _segment, _sub = parsed

    try:
        crew = _require_crew(crew_id)
    except (KeyError, ValueError) as e:
        return PlainTextResponse(str(e), status_code=404)

    # No-op: crew has no dashboard
    existing_port = crew.get("dashboard_port")
    if existing_port is None:
        return JSONResponse({"dashboard_url": None})

    with registry:
        # Re-check under the lock to prevent double-stop from concurrent DELETEs.
        existing_port = registry._reg["crews"].get(crew_id, {}).get("dashboard_port")
        if existing_port is None:
            return JSONResponse({"dashboard_url": None})
        # C-1: Extract all needed values and mutate registry under the lock,
        # then call _caddy_deregister_crew AFTER releasing it to avoid holding
        # the lock across blocking I/O.
        _dashboard_gate.release_port(int(existing_port))
        _caddy_portal.release_port(int(existing_port))
        registry._reg["crews"][crew_id].pop("dashboard_port", None)
        registry._reg["crews"][crew_id]["dashboard_url"] = None

    # C-1: Deregister from Caddy after releasing _registry_lock.
    _caddy_portal.deregister_crew(crew_id)

    logger.info(
        "DELETE /crews/%s/dashboard — released UI port %d",
        crew_id, existing_port,
    )
    return JSONResponse({"dashboard_url": None})





async def _handle_version_get(request: Request) -> Response:
    """GET /version — unauthenticated endpoint returning transport version."""
    return JSONResponse({"transport": TRANSPORT_VERSION})


# ── OpenAPI schema ──────────────────────────────────────────────────
# Generated once at startup (after all routes are defined) and cached here.
# task 2.2: handler that returns the cached schema.

_openapi_schema = None  # dict | None — populated by startup in __main__ block


async def _handle_openapi_get(request: Request) -> Response:
    """GET /openapi.json — return the cached OpenAPI 3.1.0 schema (public)."""
    import json as _json
    if _openapi_schema is None:
        return Response("schema not yet generated", status_code=503)
    return Response(
        _json.dumps(_openapi_schema, indent=2),
        media_type="application/json",
    )


# ── Auth / security middleware ──────────────────────────────────────
# TransportSecretMiddleware, RateLimitMiddleware, BearerAuthMiddleware,
# SecurityHeadersMiddleware, _parse_bearer_token, _request_source,
# _parse_rate_limit_var, _build_rate_limiters, and _RATE_LIMIT_DEFAULTS now live
# in transport/auth.py and are imported at the top of this file.


# ── Rate-limit configuration ──────────────────────────────────────────────────
# _RATE_LIMIT_DEFAULTS, _parse_rate_limit_var, _build_rate_limiters now live in
# transport/auth.py and are imported at the top of this file.


# ── Podman client + memory helpers ───────────────────────────────────────────
# PodmanClient, ContainerRuntime, _get_podman, the _podman singleton, and the
# host-memory helpers now live in transport.podman and are imported above.

# _startup_events, _startup_events_lock, _start_login_container,
# _nuke_login_container, and all lifecycle functions now live in
# transport.lifecycle and are imported above.


# ── Academy login state and _initiate_login ────────────────────────────────────
# _login_pending / _login_pending_lock and the device-flow driver live in
# transport.lifecycle. The HTTP handlers below import them from lifecycle.

# _request_source lives in transport/auth.py and is imported at the top of this file.


# ── Login/logout HTTP handlers (extracted to login.py, TRN-242) ──────────────
# The Starlette login/logout route handlers and the three backend helpers
# (_warn_inert_backend_settings, _backend_enabled, _backend_not_enabled_message)
# now live in transport.login alongside the LoginFlow singletons they delegate
# to. Re-exported here so BearerAuthMiddleware wiring in __main__ and existing
# patch('server.X') test sites keep resolving.
# TRN-233: new /login/{backend}/{method} and /logout/{backend} handlers added.
try:
    from login import (  # noqa: F401  re-exported for existing call-sites
        _warn_inert_backend_settings, _backend_enabled, _backend_not_enabled_message,
        _handle_login_post, _handle_login_get,
        _handle_claude_login_post, _handle_claude_login_get,
        _handle_claude_login_code_post,
        _handle_codex_login_post, _handle_codex_login_get,
        # TRN-233 new routes
        _handle_login_kiro_get, _handle_login_claude_get_new, _handle_login_codex_get_new,
        _handle_login_kiro_api_key_post, _handle_login_kiro_builder_id_post,
        _handle_login_kiro_identity_center_post, _handle_logout_kiro_post,
        _handle_login_claude_api_key_post, _handle_login_claude_setup_token_post,
        _handle_login_claude_oauth_post, _handle_login_claude_oauth_code_post,
        _handle_logout_claude_post_new,
        _handle_login_codex_api_key_post, _handle_login_codex_chatgpt_post,
        _handle_logout_codex_post_new,
    )
except ModuleNotFoundError:
    from transport.login import (  # noqa: F401  local dev
        _warn_inert_backend_settings, _backend_enabled, _backend_not_enabled_message,
        _handle_login_post, _handle_login_get,
        _handle_claude_login_post, _handle_claude_login_get,
        _handle_claude_login_code_post,
        _handle_codex_login_post, _handle_codex_login_get,
        # TRN-233 new routes
        _handle_login_kiro_get, _handle_login_claude_get_new, _handle_login_codex_get_new,
        _handle_login_kiro_api_key_post, _handle_login_kiro_builder_id_post,
        _handle_login_kiro_identity_center_post, _handle_logout_kiro_post,
        _handle_login_claude_api_key_post, _handle_login_claude_setup_token_post,
        _handle_login_claude_oauth_post, _handle_login_claude_oauth_code_post,
        _handle_logout_claude_post_new,
        _handle_login_codex_api_key_post, _handle_login_codex_chatgpt_post,
        _handle_logout_codex_post_new,
    )


# ── MCP tools + resources (extracted to tools.py, TRN-242) ───────────────────
# All tool functions, resources, and tool-only helpers now live in
# transport.tools; the captain dispatch/steer engine lives in
# transport.captain_engine. server.py no longer re-exports those names: no
# test patches `server.<name>` for any of them, and server's own code does not
# reference them directly. Register them against the mcp instance before
# __main__ calls mcp.streamable_http_app(...).
try:
    from tools import register_tools as _register_tools  # noqa: F401
except ModuleNotFoundError:
    from transport.tools import register_tools as _register_tools  # local dev
_register_tools(mcp, _caddy_portal, _dashboard_gate)


# ── Health endpoint ───────────────────────────────────────────────────────────

async def _handle_health(request: Request) -> Response:
    """Minimal health probe — returns 200 OK when the transport is alive."""
    return PlainTextResponse("ok")


health_routes = [
    Route("/health", _handle_health, methods=["GET"]),
]

# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Validate cross-field config constraints before doing anything else.
    # No-op — credential validation is lazy (deferred to launch())
    try:
        cfg.validate()
    except Exception as _cfg_err:
        logger.error("Transport startup aborted — config error: %s", _cfg_err)
        raise SystemExit(1) from _cfg_err

    # Refuse to start unauthenticated when ga-portal is published beyond loopback.
    _enforce_api_key_requirement(GA_API_KEY)

    logger.info("Starting transport MCP server on %s:%d", HOST, PORT)
    logger.info("Idle timeout: %ds", GA_IDLE_TIMEOUT_SECS)
    logger.info("Agent backend: %s (runtime default: %s)",
                cfg.ga_crew_agent, GA_CREW_ACP_BACKEND)
    _warn_inert_backend_settings()
    _reconcile_registry()
    # Restore UI port allocations from persisted registry so restarts
    # don't re-allocate ports already claimed by existing crews.
    with registry:
        for _cid, _info in registry._reg["crews"].items():
            _p = _info.get("dashboard_port")
            if _p is not None:
                _dashboard_ports_in_use.add(int(_p))
    if _dashboard_ports_in_use:
        logger.info("Restored %d UI port(s) from registry: %s",
                    len(_dashboard_ports_in_use), sorted(_dashboard_ports_in_use))
    for _warning in _validate_academy():
        logger.warning("Academy validation: %s", _warning)
    threading.Thread(target=_idle_monitor, daemon=True, name="idle-monitor").start()
    threading.Thread(target=_schedule_monitor, daemon=True, name="schedule-monitor").start()
    threading.Thread(target=_captain_monitor, daemon=True, name="captain-monitor").start()

    # Build the MCP ASGI app, wrap with API-key middleware, serve with Uvicorn.
    # Login/logout routes are handled inside BearerAuthMiddleware directly so
    # mcp_app is never wrapped in a Starlette router — that would break the
    # MCP lifespan (Task group is not initialized).
    # File routes are mounted on the same port via BearerAuthMiddleware's
    # file_app pass-through (presigned-URL auth, no API key needed).
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        host=HOST,
    )
    _file_starlette = Starlette(routes=file_routes)

    # Generate the OpenAPI schema once, after all routes/tools are defined,
    # before constructing BearerAuthMiddleware. Cached globally so
    # _handle_openapi_get can serve it without re-generating on every request.
    # TRN-233: old bare /login, /logout, /login/claude, /login/codex paths
    # removed; new /login/{backend}/{method} and /logout/{backend} registered.
    _openapi_schema_routes = {
        ("GET",  "/login/kiro"): _handle_login_kiro_get,
        ("POST", "/login/kiro/api-key"): _handle_login_kiro_api_key_post,
        ("POST", "/login/kiro/builder-id"): _handle_login_kiro_builder_id_post,
        ("POST", "/login/kiro/identity-center"): _handle_login_kiro_identity_center_post,
        ("POST", "/logout/kiro"): _handle_logout_kiro_post,
        ("GET",  "/login/claude"): _handle_login_claude_get_new,
        ("POST", "/login/claude/api-key"): _handle_login_claude_api_key_post,
        ("POST", "/login/claude/setup-token"): _handle_login_claude_setup_token_post,
        ("POST", "/login/claude/oauth"): _handle_login_claude_oauth_post,
        ("POST", "/login/claude/oauth/code"): _handle_login_claude_oauth_code_post,
        ("POST", "/logout/claude"): _handle_logout_claude_post_new,
        ("GET",  "/login/codex"): _handle_login_codex_get_new,
        ("POST", "/login/codex/api-key"): _handle_login_codex_api_key_post,
        ("POST", "/login/codex/chatgpt"): _handle_login_codex_chatgpt_post,
        ("POST", "/logout/codex"): _handle_logout_codex_post_new,
        ("GET",  "/health"): _handle_health,
        ("GET",  "/crews/*/ui"): _handle_crew_ui_proxy,
        ("GET",  "/crews/*/api"): _handle_crew_api_proxy,
        ("POST", "/crews/*/dashboard"): _handle_crew_dashboard_post,
        ("DELETE", "/crews/*/dashboard"): _handle_crew_dashboard_delete,
        ("WS",   "/crews/*/ui"): _handle_crew_ui_ws_proxy,
    }
    _openapi_schema_public_routes = {
        ("GET",  "/version"): _handle_version_get,
        ("POST", "/dashboard/login"): _dashboard_gate.handle_login_post,
        ("POST", "/dashboard/logout"): _dashboard_gate.handle_logout_post,
        ("GET",  "/dashboard/auth"): _dashboard_gate.handle_auth,
        ("GET",  "/dashboard/login"): _dashboard_gate.handle_login_get,
        ("GET",  "/openapi.json"): _handle_openapi_get,
    }
    _openapi_schema = _openapi.generate_schema(
        routes=_openapi_schema_routes,
        public_routes=_openapi_schema_public_routes,
        file_routes=file_routes,
        mcp_tools=_openapi.get_mcp_tools(mcp),
        version=TRANSPORT_VERSION,
    )
    logger.info("OpenAPI schema generated (%d paths)", len(_openapi_schema.get("paths", {})))

    app = BearerAuthMiddleware(mcp_app,
        api_key=GA_API_KEY,
        file_app=_file_starlette,
        routes={
            ("GET",  "/login/kiro"): _handle_login_kiro_get,
            ("POST", "/login/kiro/api-key"): _handle_login_kiro_api_key_post,
            ("POST", "/login/kiro/builder-id"): _handle_login_kiro_builder_id_post,
            ("POST", "/login/kiro/identity-center"): _handle_login_kiro_identity_center_post,
            ("POST", "/logout/kiro"): _handle_logout_kiro_post,
            ("GET",  "/login/claude"): _handle_login_claude_get_new,
            ("POST", "/login/claude/api-key"): _handle_login_claude_api_key_post,
            ("POST", "/login/claude/setup-token"): _handle_login_claude_setup_token_post,
            ("POST", "/login/claude/oauth"): _handle_login_claude_oauth_post,
            ("POST", "/login/claude/oauth/code"): _handle_login_claude_oauth_code_post,
            ("POST", "/logout/claude"): _handle_logout_claude_post_new,
            ("GET",  "/login/codex"): _handle_login_codex_get_new,
            ("POST", "/login/codex/api-key"): _handle_login_codex_api_key_post,
            ("POST", "/login/codex/chatgpt"): _handle_login_codex_chatgpt_post,
            ("POST", "/logout/codex"): _handle_logout_codex_post_new,
            ("GET",  "/health"): _handle_health,
            # Crew proxy routes — pattern keys used by BearerAuthMiddleware dispatch
            ("GET",  "/crews/*/api"): _handle_crew_api_proxy,
            ("POST", "/crews/*/dashboard"): _handle_crew_dashboard_post,
            ("DELETE", "/crews/*/dashboard"): _handle_crew_dashboard_delete,
        },
        public_routes={
            ("GET",  "/version"): _handle_version_get,
            ("POST", "/dashboard/login"): _dashboard_gate.handle_login_post,
            ("POST", "/dashboard/logout"): _dashboard_gate.handle_logout_post,
            ("GET",  "/dashboard/auth"): _dashboard_gate.handle_auth,
            ("GET",  "/dashboard/login"): _dashboard_gate.handle_login_get,
            ("GET",  "/openapi.json"): _handle_openapi_get,  # public, no auth
            # Crew UI paths — protected by Caddy's gs_session forward-auth,
            # not by bearer token. The transport never sees these requests
            # without Caddy's forward-auth check having passed first.
            ("GET",  "/crews/*/ui"): _handle_crew_ui_proxy,
            ("WS",   "/crews/*/ui"): _handle_crew_ui_ws_proxy,
        },
    )
    # Rate-limit wrapper: sits OUTSIDE BearerAuthMiddleware so all
    # callers — including unauthenticated /login — are subject to limits, and
    # INSIDE SecurityHeadersMiddleware. Skipped entirely when the master switch
    # GA_RATE_LIMIT_ENABLED=false.
    _rate_limiters = _build_rate_limiters()
    if _rate_limiters is not None:
        _trusted_proxy_networks = _parse_trusted_proxy_cidr(cfg.ga_trusted_proxy_cidr)
        app = RateLimitMiddleware(
            app,
            limiters=_rate_limiters,
            api_key=GA_API_KEY,
            trusted_proxy_networks=_trusted_proxy_networks,
        )
        logger.info(
            "HTTP rate limiting: enabled (%s)",
            ", ".join(
                f"{k}={lim.max_requests}/{int(lim.window_secs)}s"
                for k, lim in _rate_limiters.items()
            ),
        )
    else:
        logger.info("HTTP rate limiting: disabled (GA_RATE_LIMIT_ENABLED=false)")
    # Transport-security wrapper: security headers, HSTS, and CSP enforcement.
    # HTTPS redirect is disabled — Caddy owns redirects. CSP is unconditionally
    # enforced.
    app = SecurityHeadersMiddleware(
        app,
        enable_headers=GA_ENABLE_SECURITY_HEADERS,
        enforce_redirect=False,
        csp_enforce=True,
    )
    # TransportSecretMiddleware is the absolute outermost gate — it rejects any
    # request not from ga-portal (missing or wrong X-Transport-Token) before any
    # other middleware sees it. When GA_TRANSPORT_SECRET is empty (dev/test) this
    # is a transparent pass-through.
    app = TransportSecretMiddleware(app, transport_secret=GA_TRANSPORT_SECRET)
    if GA_TRANSPORT_SECRET:
        logger.info("Portal secret authentication: enabled (X-Transport-Token required)")
    else:
        logger.info("Portal secret authentication: disabled (GA_TRANSPORT_SECRET unset)")
    if GA_API_KEY:
        logger.info("MCP API-key authentication: enabled")
    else:
        logger.info("MCP API-key authentication: disabled (GA_API_KEY unset)")
    logger.info(
        "Transport security: headers=%s https_redirect=disabled csp=enforce",
        "on" if GA_ENABLE_SECURITY_HEADERS else "off",
    )

    # Enforce a minimum TLS version when the app terminates TLS directly.
    # (In production TLS is terminated at the edge; these apply for non-edge
    # deployments that set GA_TLS_CERTFILE / GA_TLS_KEYFILE.)
    _uvicorn_kwargs: dict[str, Any] = {}
    if GA_TLS_CERTFILE and GA_TLS_KEYFILE:
        import ssl as _ssl

        _tls_certfile = GA_TLS_CERTFILE
        _tls_keyfile = GA_TLS_KEYFILE
        _tls_min_version = GA_TLS_MIN_VERSION

        def _ssl_context_factory(_cfg, _default_factory):  # type: ignore[return]
            """Build an SSLContext with an explicit minimum TLS version floor.

            Using ssl_context_factory rather than ssl_version + ssl_ciphers
            lets us call ctx.minimum_version directly, which is the only
            reliable way to enforce a TLS floor across OpenSSL versions.
            """
            ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(_tls_certfile, _tls_keyfile)
            if _tls_min_version == "1.3":
                ctx.minimum_version = _ssl.TLSVersion.TLSv1_3
            else:
                # Enforce TLS 1.2 explicitly — do not rely on the OpenSSL default.
                ctx.minimum_version = _ssl.TLSVersion.TLSv1_2
            return ctx

        _uvicorn_kwargs["ssl_context_factory"] = _ssl_context_factory
        logger.info("Direct TLS termination enabled (min TLS %s)", GA_TLS_MIN_VERSION)

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info", **_uvicorn_kwargs)
    server = uvicorn.Server(config)

    async def _main() -> None:
        # Portal (Caddy) is the sole dashboard proxy and is always present.
        # On restart, re-register all existing crew servers with Caddy (idempotent
        # — Caddy's --resume may have already loaded them, but we call again so a
        # fresh data-volume wipe is handled gracefully).
        with registry:
            _restored_crews = dict(registry._reg.get("crews", {}))
        for _cid, _info in _restored_crews.items():
            _p = _info.get("dashboard_port")
            if _p is not None:
                _dashboard_gate.register_port(_cid, int(_p))
                _crew_cookie_val = _info.get("cookie", "")
                _caddy_portal.register_crew(_cid, int(_p), crew_cookie=_crew_cookie_val)
        logger.info("Portal (Caddy) is the sole dashboard proxy")
        await server.serve()

    asyncio.run(_main())
