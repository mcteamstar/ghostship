"""Transport MCP server — Ghost Academy crew orchestration endpoint.

Manages KiroCrew crew containers via the Podman socket. No permanently
running kirocrew container — all agent work happens in crew containers
created on demand via launch.

The client (on macOS) connects as "ghostship".

Tools:
  crews      — list live crews
  launch     — summon a new crew container + workspace
  dispatch  — send a task to an agent in a named crew (C)
  pickup    — check progress or collect result (R)
  captain   — supervise standing orders inside one crew
  steer     — redirect a running task or continue a completed one (U)
  nuke      — tear down a crew container + volumes (D)
  schedule  — create a recurring task on a named crew
  evac      — extract files, diffs, or git bundles from a crew workspace
  supply    — get a presigned URL to deliver files, tar archives, or git bundles into a crew workspace

Resources:
  transport://agents — available agents and their roles (read before dispatching)
  transport://orders — built-in standing-order templates (read before ordering)
  transport://jobs — scheduled jobs across all running crews

Auth flow:
  On first launch (no ga-kiro-auth file), the crew container initiates
  kiro-cli login and returns a device auth URL. After the user completes
  the flow, launch is called again to finish setup and save the auth
  rows to the ga-kiro-auth file for future launches.

  On subsequent launches, auth rows are read from the ga-kiro-auth file
  and injected into each crew's isolated kiro-cli SQLite DB.

Networking:
  All crew containers join ga-net. Transport reaches them by name:
  http://gs-<id>:5476. Container-name DNS confirmed working.

Naming:
  ga-* is Ghost Academy infrastructure (ga-transport, ga-net) — fixed,
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
import posixpath
import select
import socket
import tarfile
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

import httpx
from mcp.server.mcpserver.server import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse, PlainTextResponse, JSONResponse
from starlette.routing import Route, Mount
import uvicorn
import asyncio

try:
    import security as _security  # container: both files flat in /app
except ModuleNotFoundError:
    from transport import security as _security  # local dev: transport/ is a package dir

try:
    from config import Config  # container: both files flat in /app
except ImportError:
    # Local dev: transport/ is a package dir, and a bare `import config` can
    # resolve to the repo-root config/ namespace package (which has no Config),
    # raising ImportError rather than ModuleNotFoundError — fall back either way.
    from transport.config import Config

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
    )

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
        _load_order_template,
        _substitute_placeholders,
        _format_captain_mail,
        _resolve_order_template,
        _append_captain_mail,
        _mail_count,
        _read_all_mail_counts,
        _read_all_mail_subjects,
        _captain_jobs,
        _captain_checkin_job,
        _captain_order_lock,
        _captain_order_locks,
        _captain_order_locks_lock,
        _captain_standing_view,
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
        _load_order_template,
        _substitute_placeholders,
        _format_captain_mail,
        _resolve_order_template,
        _append_captain_mail,
        _mail_count,
        _read_all_mail_counts,
        _read_all_mail_subjects,
        _captain_jobs,
        _captain_checkin_job,
        _captain_order_lock,
        _captain_order_locks,
        _captain_order_locks_lock,
        _captain_standing_view,
    )

# ── Config ────────────────────────────────────────────────────────────────────
# All runtime configuration is read from the environment in exactly one place —
# Config.from_env() (see transport/config.py). The module-level names below are
# thin cfg.<field> reads kept for readability and backwards compatibility with
# the many call sites throughout this module; none of them read os.environ
# directly any more.
cfg = Config.from_env()

HOST = cfg.host  # Binds all interfaces inside the container.
# The host-side protection is in install.sh: -p "127.0.0.1:PORT:PORT" ensures
# the published port is only reachable from localhost on the host, regardless
# of what the container binds internally. Set HOST=127.0.0.1 only for
# non-containerised installs where you want loopback-only binding.
PORT = cfg.port

DATA_DIR = Path(cfg.transport_data_dir)
# REGISTRY_PATH is imported from transport.registry


# KiroCrew gateway port — fixed by upstream, not configurable from this transport.
CREW_GATEWAY_PORT = 5476
CREW_CONTAINER_PREFIX = "gs-"
CREW_VOLUME_PREFIX = "gs-vol-"
CREW_HOME_VOLUME_PREFIX = "gs-home-"

PODMAN_SOCK = cfg.podman_socket

KC_IMAGE = cfg.kc_image
# Upstream image used for ephemeral containers that only need kiro-cli (e.g.
# ga-login). Using the base image here avoids any risk from a tainted crew image.
KC_BASE_IMAGE = cfg.kc_base_image
GA_NETWORK = "ga-net"
GA_MAX_CREWS = cfg.ga_max_crews
GA_MAX_ACTIVE_CREWS = cfg.ga_max_active_crews
GA_AUTH_FILE = "ga-kiro-auth"
PERSONA_NAMES = ("ghost", "spectre", "banshee", "wraith", "reaper", "raven")
PERSONA_ALLOWLIST = frozenset(PERSONA_NAMES)
GA_IDLE_TIMEOUT_SECS = cfg.ga_idle_timeout_secs
# KiroCrew 0.4.0 requires a non-empty `agent` field in config.local.json; crew
# creation fails at the gateway with a 4xx if it is absent. Default "kiro" is
# KiroCrew's built-in agent name; operators override for a differently-named agent.
GA_CREW_AGENT = cfg.ga_crew_agent
KC_MODEL_OVERRIDE = cfg.kc_model_override
KC_MODEL_DEFAULT = cfg.kc_model_default
GA_FILE_TTL_SECS = cfg.ga_file_ttl_secs  # 5 min default
GA_MIN_FREE_MEM_GB = cfg.ga_min_free_mem_gb
GA_MEMORY_WAIT_SECS = cfg.ga_memory_wait_secs
GA_SPAWN_MIN_MEMORY_GB = cfg.ga_spawn_min_memory_gb
GA_RESOURCE_PRESSURE_GB = cfg.ga_resource_pressure_gb
GA_RESOURCE_CRITICAL_GB = cfg.ga_resource_critical_gb
GA_SUBAGENT_TIMEOUT_SECS = cfg.ga_subagent_timeout_secs
GA_SUBAGENT_MAX_TURNS = cfg.ga_subagent_max_turns
GA_PICKUP_MAX_POLL_SECS = cfg.ga_pickup_max_poll_secs
KC_GATEWAY_TOKEN_TTL = cfg.kc_gateway_token_ttl

# ── Git author identity passthrough (TRN-77) ─────────────────────────────────
# When both vars are set, all four git identity env vars are injected into
# each crew container at setup time so commits carry the operator's identity.
# When unset, per-persona identity (e.g. Ghost <ghost@localhost>) is preserved.
GA_GIT_AUTHOR_NAME = os.environ.get("GA_GIT_AUTHOR_NAME", "").strip()
GA_GIT_AUTHOR_EMAIL = os.environ.get("GA_GIT_AUTHOR_EMAIL", "").strip()

# ── Transport security (TRN-70) ───────────────────────────────────────────────
# TLS is terminated at the edge (see design.md); the app still emits HSTS and
# security headers so protection does not depend solely on edge config. These
# flags let each protection be toggled via config for a staged rollout and
# config-only rollback.
#
# GA_TLS_MIN_VERSION: minimum TLS version enforced when the app terminates TLS
#   directly (ssl_version passed to uvicorn). Values: "1.2" or "1.3".
# GA_TLS_CERTFILE / GA_TLS_KEYFILE: enable direct TLS termination when set.
# GA_ENABLE_SECURITY_HEADERS: emit baseline security headers (default on).
# GA_ENFORCE_HTTPS_REDIRECT: 301-redirect plaintext HTTP to HTTPS (staged;
#   default off until the monitored plaintext window + client notice is done).
# GA_CSP_ENFORCE: send CSP as enforcing rather than report-only (staged;
#   default off until report-only violations are triaged).
GA_TLS_MIN_VERSION = cfg.ga_tls_min_version
GA_TLS_CERTFILE = cfg.ga_tls_certfile
GA_TLS_KEYFILE = cfg.ga_tls_keyfile
GA_ENABLE_SECURITY_HEADERS = cfg.ga_enable_security_headers
GA_ENFORCE_HTTPS_REDIRECT = cfg.ga_enforce_https_redirect
GA_CSP_ENFORCE = cfg.ga_csp_enforce

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

    _logger.warning("GA_API_KEY is not set — transport is running WITHOUT authentication. "
                    "All MCP tools and file endpoints are publicly accessible. "
                    "Set GA_API_KEY to require Bearer token auth.")
    return ""


GA_API_KEY = _load_api_key()


def _auth_file_path() -> Path:
    """Return the reusable kiro-cli auth file under the data mount."""
    return DATA_DIR / GA_AUTH_FILE


def _read_auth_file(_path: Path | None = None) -> str:
    """Read the persisted auth value, or "" if it doesn't exist yet.

    _path: override the default path (for testing only).
    """
    path = _path if _path is not None else _auth_file_path()
    if not path.is_file():
        return ""
    try:
        return path.read_text()
    except Exception as e:
        logger.warning("Failed to read %s: %s", path, e)
        return ""


def _write_auth_file(value: str, _path: Path | None = None) -> None:
    """Persist the reusable auth value for future launches.

    _path: override the default path (for testing only).
    """
    path = _path if _path is not None else _auth_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            fd = -1
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
    finally:
        if fd != -1:
            os.close(fd)
    os.chmod(path, 0o600)

# kiro-cli identity provider for crew logins. Left unset, `kiro-cli login`
# falls back to Builder ID (free tier) — a different identity system than an
# org's IAM Identity Center Pro tenant. Set these to match whatever identity
# an org's own kiro-cli install already authenticates against (see
# `kiro-cli whoami`).
KIRO_LICENSE = cfg.kiro_license
KIRO_IDENTITY_PROVIDER = cfg.kiro_identity_provider
KIRO_REGION = cfg.kiro_region

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Scrub any registered secret value from every log record (TRN-70
# secrets-management: secrets excluded from logs and errors).
_security.install_redaction_filter()

try:
    from lifecycle import (  # container: flat /app/
        CREW_CONTAINER_PREFIX,
        CREW_GATEWAY_PORT,
        CREW_HOME_VOLUME_PREFIX,
        CREW_VOLUME_PREFIX,
        CrewUnresponsiveError,
        GA_LOGIN_CONTAINER_PREFIX,
        GA_NETWORK,
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
        _get_recovery_lock,
        _idle_monitor,
        _inject_auth,
        _inject_git_identity,
        _inject_policy,
        _mint_cookie,
        _nuke_login_container,
        _patch_crew_config,
        _patch_models,
        _probe_gateway,
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
        _startup_events,
        _startup_events_lock,
        _validate_agent,
        _wait_gateway,
    )
except ModuleNotFoundError:
    from transport.lifecycle import (  # local dev
        CREW_CONTAINER_PREFIX,
        CREW_GATEWAY_PORT,
        CREW_HOME_VOLUME_PREFIX,
        CREW_VOLUME_PREFIX,
        CrewUnresponsiveError,
        GA_LOGIN_CONTAINER_PREFIX,
        GA_NETWORK,
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
        _get_recovery_lock,
        _idle_monitor,
        _inject_auth,
        _inject_git_identity,
        _inject_policy,
        _mint_cookie,
        _nuke_login_container,
        _patch_crew_config,
        _patch_models,
        _probe_gateway,
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
        _startup_events,
        _startup_events_lock,
        _validate_agent,
        _wait_gateway,
    )

# Academy composition/manifest/validation surface — extracted from lifecycle
# to transport/academy.py (TRN-86). server reads COMPOSITION_REGISTRY (in
# resource_compositions), _AGENTS_DIR (in resource_agents), and the helper
# functions. It imports them from academy directly rather than re-through
# lifecycle. Note (pending TRN-85): tests still dual-patch these names on
# BOTH `lifecycle` and `server` (e.g. patch.object(lifecycle,
# "COMPOSITION_REGISTRY") + patch.object(server, ...)) and also patch
# transport.academy; that dual/triple-patch is intentional until TRN-85
# migrates the academy tests to patch transport.academy exclusively.
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

mcp = MCPServer(
    name="transport",
    description=(
        "Ghost Academy crew orchestration: launch workspaces, dispatch agents, "
        "evac results, nuke crews"
    ),
)

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


async def _handle_crew_ui_proxy(request: Request) -> Response:
    """Reverse-proxy GET/POST to the crew gateway UI at http://gs-{crew_id}:5476/.

    Route: /crews/{crew_id}/ui  →  http://gs-{crew_id}:5476/
           /crews/{crew_id}/ui/{path}  →  http://gs-{crew_id}:5476/{path}

    - Auto-wakes the crew before proxying.
    - Passes request headers through (minus host).
    - Does NOT inject any session cookie (browser goes through the normal
      gateway login UI — see design.md decision D3).
    - Streams the upstream response body without buffering.
    - Returns 404 for unknown crew_id.
    """
    parsed = _extract_crew_proxy_parts(request.scope["path"])
    if parsed is None:
        return PlainTextResponse("Not found", status_code=404)
    crew_id, _segment, sub_path = parsed

    # Crew lookup
    try:
        crew = _require_crew(crew_id)
    except (KeyError, ValueError) as e:
        return PlainTextResponse(str(e), status_code=404)

    # Auto-wake if stopped
    try:
        crew = _ensure_crew_running(crew, crew_id)
    except RuntimeError as e:
        return PlainTextResponse(str(e), status_code=502)

    # Build upstream URL
    upstream_base = f"http://{CREW_CONTAINER_PREFIX}{crew_id}:{CREW_GATEWAY_PORT}"
    upstream_path = f"/{sub_path}" if sub_path else "/"
    query = request.scope.get("query_string", b"")
    upstream_url = upstream_path
    if query:
        upstream_url = f"{upstream_path}?{_sanitise_query_string(query)}"
    upstream_full = f"{upstream_base}{upstream_url}"

    # Forward headers minus host
    forward_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() != "host"
    }

    # Proxy and stream
    try:
        async with _async_http.stream(
            request.method,
            upstream_full,
            headers=forward_headers,
            content=await request.body(),
        ) as upstream_resp:
            # Strip hop-by-hop headers from forwarded response
            response_headers = {
                k: v
                for k, v in upstream_resp.headers.items()
                if k.lower() not in _HOP_BY_HOP_HEADERS
            }
            # Read body fully so we can close the upstream context; for large
            # responses this is acceptable given the 60 s timeout constraint.
            body = await upstream_resp.aread()
        return Response(
            content=body,
            status_code=upstream_resp.status_code,
            headers=response_headers,
        )
    except Exception as e:
        logger.warning("UI proxy error for crew %s: %s", crew_id, e)
        return PlainTextResponse(f"Proxy error: {e}", status_code=502)


async def _handle_crew_api_proxy(request: Request) -> Response:
    """Reverse-proxy to the crew gateway REST API at http://gs-{crew_id}:5476/api/{path}.

    Route: /crews/{crew_id}/api/{path}  →  http://gs-{crew_id}:5476/api/{path}

    - Auto-wakes the crew before proxying.
    - Injects the internal session cookie mc_token_5476.
    - On upstream 401/403, refreshes the cookie and retries once (D4).
    - Returns 404 for unknown crew_id.
    """
    parsed = _extract_crew_proxy_parts(request.scope["path"])
    if parsed is None:
        return PlainTextResponse("Not found", status_code=404)
    crew_id, _segment, sub_path = parsed

    # Crew lookup
    try:
        crew = _require_crew(crew_id)
    except (KeyError, ValueError) as e:
        return PlainTextResponse(str(e), status_code=404)

    # Auto-wake if stopped
    try:
        crew = _ensure_crew_running(crew, crew_id)
    except RuntimeError as e:
        return PlainTextResponse(str(e), status_code=502)

    # Build upstream URL
    upstream_base = f"http://{CREW_CONTAINER_PREFIX}{crew_id}:{CREW_GATEWAY_PORT}"
    api_path = f"/api/{sub_path}" if sub_path else "/api/"
    query = request.scope.get("query_string", b"")
    if query:
        api_path = f"{api_path}?{_sanitise_query_string(query)}"
    upstream_full = f"{upstream_base}{api_path}"

    # Forward headers minus host and cookie, then inject session cookie
    forward_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() != "host" and k.lower() != "cookie"
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





async def _handle_version_get(request: Request) -> Response:
    """GET /version — unauthenticated endpoint returning transport version."""
    return JSONResponse({"transport": TRANSPORT_VERSION})


class BearerAuthMiddleware:
    """Pure ASGI middleware enforcing a static bearer API key.

    When ``api_key`` is empty the middleware is a transparent pass-through.
    Otherwise every HTTP request must carry exactly one ``Authorization: Bearer <key>``
    header matching the configured value (constant-time comparison). Rejected
    requests receive 401 with ``WWW-Authenticate: Bearer`` and never reach the
    downstream app. Non-HTTP ASGI scopes pass through unchanged.

    Login/logout routes are also handled here so the inner app (mcp_app) is
    never wrapped in a Starlette router — that would break the MCP lifespan.
    """

    def __init__(self, app, api_key: str = "", file_app=None) -> None:
        self.app = app
        self._key = api_key
        self._file_app = file_app
        # Map (method, path) → handler for routes that live outside the MCP app
        self._routes: dict[tuple[str, str], Any] = {
            ("POST", "/login"): _handle_login_post,
            ("GET",  "/login"): _handle_login_get,
            ("POST", "/logout"): _handle_logout_post,
            ("GET",  "/health"): _handle_health,
        }
        # Routes exempt from authentication (served before auth check)
        self._public_routes: dict[tuple[str, str], Any] = {
            ("GET", "/version"): _handle_version_get,
        }

    # Paths that bypass API-key auth (readiness probes, etc.)
    _PUBLIC_PATHS: set[str] = {"/health"}

    async def __call__(self, scope, receive, send) -> None:
        # Public routes — served without any authentication check
        if scope["type"] == "http":
            public_handler = self._public_routes.get(
                (scope["method"], scope["path"])
            )
            if public_handler is not None:
                request = Request(scope, receive)
                response = await public_handler(request)
                await response(scope, receive, send)
                return

            # File routes — use presigned-URL auth, bypass API key
            if self._file_app and scope["path"].startswith("/files/"):
                await self._file_app(scope, receive, send)
                return

        if not self._key or scope["type"] != "http":
            # No API key — still need to check login/logout routes
            if scope["type"] == "http":
                handler = self._routes.get(
                    (scope["method"], scope["path"])
                )
                if handler is not None:
                    request = Request(scope, receive)
                    response = await handler(request)
                    await response(scope, receive, send)
                    return
                # Crew proxy routes (no auth required when GA_API_KEY unset)
                _path = scope["path"]
                _parts = _path.lstrip("/").split("/")
                if len(_parts) >= 3 and _parts[0] == "crews" and _parts[2] == "ui":
                    request = Request(scope, receive)
                    response = await _handle_crew_ui_proxy(request)
                    await response(scope, receive, send)
                    return
                if len(_parts) >= 4 and _parts[0] == "crews" and _parts[2] == "api":
                    request = Request(scope, receive)
                    response = await _handle_crew_api_proxy(request)
                    await response(scope, receive, send)
                    return
            await self.app(scope, receive, send)
            return

        # Allow public paths through without auth (health probes, etc.)
        if scope["path"] in self._PUBLIC_PATHS:
            handler = self._routes.get((scope["method"], scope["path"]))
            if handler is not None:
                request = Request(scope, receive)
                response = await handler(request)
                await response(scope, receive, send)
                return

        # Extract Authorization headers from the ASGI scope
        auth_values = [
            v.decode("latin-1")
            for k, v in scope.get("headers", [])
            if k == b"authorization"
        ]

        # Reject: missing, duplicated, or malformed
        if len(auth_values) != 1:
            await self._reject(send, scope)
            return

        value = auth_values[0]
        # Must be "Bearer <token>" (case-insensitive scheme)
        if not value[:7].lower() == "bearer " or " " in value[7:].strip():
            await self._reject(send, scope)
            return

        token = value[7:].strip()
        if not token or not hmac.compare_digest(token, self._key):
            await self._reject(send, scope)
            return

        # Auth passed — check login/logout routes before falling through to MCP
        handler = self._routes.get((scope["method"], scope["path"]))
        if handler is not None:
            request = Request(scope, receive)
            response = await handler(request)
            await response(scope, receive, send)
            return

        # Crew UI proxy — /crews/<id>/ui and /crews/<id>/ui/<path>
        # Dispatch after auth passes so GA_API_KEY enforcement applies.
        path = scope["path"]
        path_parts = path.lstrip("/").split("/")
        if (
            len(path_parts) >= 3
            and path_parts[0] == "crews"
            and path_parts[2] == "ui"
        ):
            request = Request(scope, receive)
            response = await _handle_crew_ui_proxy(request)
            await response(scope, receive, send)
            return

        # Crew API proxy — /crews/<id>/api/<path>
        if (
            len(path_parts) >= 4
            and path_parts[0] == "crews"
            and path_parts[2] == "api"
        ):
            request = Request(scope, receive)
            response = await _handle_crew_api_proxy(request)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send, scope=None) -> None:
        # Audit the authorization denial (TRN-70 audit logging). No token value
        # is ever included — only outcome, source, and timestamp.
        try:
            source = None
            if scope is not None:
                for k, v in scope.get("headers", []):
                    if k == b"x-forwarded-for":
                        source = v.decode("latin-1").split(",")[0].strip()
                        break
                if source is None:
                    client = scope.get("client")
                    if client:
                        source = client[0]
            _security.audit_auth_event(
                action="api_request", outcome="denied", account=None,
                source=source, emit=logger.info,
            )
        except Exception:
            pass
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                [b"www-authenticate", b"Bearer"],
                [b"content-type", b"text/plain; charset=utf-8"],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b"Unauthorized",
        })


# ── Transport security middleware (TRN-70) ────────────────────────────────────

class SecurityHeadersMiddleware:
    """ASGI middleware enforcing transport-security guarantees.

    - Redirects plaintext HTTP to HTTPS with a 301 when the redirect is enabled
      (staged rollout: off until the monitored plaintext window + client notice
      is complete).
    - Emits the baseline security headers on every response
      (``X-Content-Type-Options: nosniff``, clickjacking protection, and a
      Content-Security-Policy) and, on HTTPS responses, an HSTS header with a
      non-zero max-age.

    HTTPS is detected from the ASGI scheme or the ``x-forwarded-proto`` header,
    since TLS is terminated at the edge and the app sees forwarded requests.
    """

    def __init__(
        self,
        app,
        *,
        enable_headers: bool = True,
        enforce_redirect: bool = False,
        csp_enforce: bool = False,
    ) -> None:
        self.app = app
        self._enable_headers = enable_headers
        self._enforce_redirect = enforce_redirect
        self._csp_enforce = csp_enforce

    @staticmethod
    def _is_https(scope) -> bool:
        if scope.get("scheme") == "https":
            return True
        for k, v in scope.get("headers", []):
            if k == b"x-forwarded-proto" and v.split(b",")[0].strip().lower() == b"https":
                return True
        return False

    @staticmethod
    def _host(scope) -> str:
        for k, v in scope.get("headers", []):
            if k == b"host":
                return v.decode("latin-1")
        server = scope.get("server") or ("localhost", None)
        return server[0]

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        https = self._is_https(scope)

        # Log plaintext HTTP traffic during the monitoring window (TRN-70 task 3.4).
        # When enforce_redirect is off, we are in the monitored window phase — log
        # every non-health plaintext hit so operators can identify affected clients
        # before flipping GA_ENFORCE_HTTPS_REDIRECT. Once enforce_redirect is on,
        # the redirect itself is the record of the hit.
        if not https and scope.get("path") != "/health":
            source = None
            for k, v in scope.get("headers", []):
                if k == b"x-forwarded-for":
                    source = v.decode("latin-1").split(",")[0].strip()
                    break
            if source is None:
                client = scope.get("client")
                if client:
                    source = client[0]
            logger.info(
                "plaintext HTTP hit: method=%s path=%s source=%s "
                "(enforce_redirect=%s)",
                scope.get("method", "?"),
                scope.get("path", "/"),
                source or "-",
                "on" if self._enforce_redirect else "off",
            )

        # Plaintext → HTTPS 301 redirect (staged; skip health probes).
        if self._enforce_redirect and not https and scope.get("path") != "/health":
            host = self._host(scope)
            path = scope.get("path", "/")
            qs = scope.get("query_string", b"")
            target = f"https://{host}{path}"
            if qs:
                target += "?" + _sanitise_query_string(qs)
            await send({
                "type": "http.response.start",
                "status": 301,
                "headers": [
                    (b"location", target.encode("latin-1")),
                    (b"content-length", b"0"),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        if not self._enable_headers:
            await self.app(scope, receive, send)
            return

        extra = _security.security_headers(
            https=https,
            csp_report_only=not self._csp_enforce,
        )

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                for name, value in extra:
                    if name not in present:
                        headers.append((name, value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ── Podman client + memory helpers ───────────────────────────────────────────
# PodmanClient, ContainerRuntime, _get_podman, the _podman singleton, and the
# host-memory helpers now live in transport.podman and are imported above.

# _startup_events, _startup_events_lock, _start_login_container,
# _nuke_login_container, and all lifecycle functions now live in
# transport.lifecycle and are imported above.


# ── Academy login state ───────────────────────────────────────────────────────

# Single-slot for the active login flow. Keyed fields:
#   container: str   — name of the ephemeral ga-login-<token> container
#   exec_id:   str   — Podman exec session id (informational)
#   started_at: float — time.time() when the flow started
_login_pending: dict | None = None
_login_pending_lock = threading.Lock()


# ── Academy login / logout HTTP routes ───────────────────────────────────────

def _initiate_login(podman: "PodmanClient") -> dict:
    """Start a device auth flow and return login URL and code.

    Acquires _login_pending_lock, applies TOCTOU-safe guards, starts the
    ephemeral login container, runs kiro-cli login via PTY, answers interactive
    prompts, extracts the device URL and code, and hands the stream to a
    background drain thread.

    Returns one of:
      {"login_url": str, "code": str | None}     — flow started successfully
      {"login_pending": True}                     — a flow is already in progress
      {"error": str}                              — hard failure (container / PTY)

    Callers must NOT hold _login_pending_lock when calling this.
    """
    global _login_pending
    with _login_pending_lock:
        if _login_pending is not None:
            return {"login_pending": True}
        # Set lightweight sentinel immediately to prevent concurrent starts
        _login_pending = {
            "container": None,
            "started_at": time.time(),
            "state": "starting",
        }

    # ── Start ephemeral container ─────────────────────────────────────────────
    try:
        container = _start_login_container(podman)
    except Exception as e:
        logger.error("Failed to start login container: %s", e)
        with _login_pending_lock:
            _login_pending = None
        return {"error": f"Failed to start login container: {e}"}

    # Update sentinel with real container name
    with _login_pending_lock:
        _login_pending = {
            "container": container,
            "started_at": _login_pending["started_at"] if _login_pending else time.time(),
            "state": "started",
        }

    # ── Wait for kiro-cli to be available in the container ────────────────────
    for _ in range(10):
        try:
            check = podman.container_exec(container, ["which", "kiro-cli"])
            if "kiro-cli" in check:
                break
        except Exception:
            pass
        time.sleep(0.5)

    # ── Start PTY+stdin exec ──────────────────────────────────────────────────
    # kiro-cli ignores --identity-provider / --region flags in interactive/PTY
    # mode (upstream bug kiro#6120). Use a raw-socket exec so we can write
    # stdin answers to the interactive prompts automatically.
    cmd = ["kiro-cli", "login", "--use-device-flow"] + (
        ["--license", KIRO_LICENSE] if KIRO_LICENSE else []
    )
    try:
        exec_id, pty_sock = podman.container_exec_pty_stdin(container, cmd)
    except Exception as e:
        _nuke_login_container(podman, container)
        with _login_pending_lock:
            _login_pending = None
        return {"error": f"Failed to start kiro-cli login: {e}"}

    pty_sock.setblocking(False)

    # ── Read output, answer prompts, wait for device URL (max 15s) ───────────
    deadline = time.time() + 15.0
    collected = bytearray()
    login_url: str | None = None
    login_code: str | None = None
    prompt_rules: list[tuple[str, bytes]] = [
        ("Select login method", b"\n"),
        ("Start URL", (KIRO_IDENTITY_PROVIDER.rstrip("/") + "/\n").encode()),
        ("Region", (KIRO_REGION + "\n").encode()),
    ]
    answered_prompts: set[str] = set()
    answered_url = False
    start_url_seen = False

    try:
        while time.time() < deadline:
            ready, _, _ = select.select([pty_sock], [], [], 0.1)
            if ready:
                try:
                    chunk = pty_sock.recv(4096)
                except BlockingIOError:
                    continue
                if not chunk:
                    break
                collected.extend(chunk)
                text = collected.decode("utf-8", errors="replace")

                for matcher, answer in prompt_rules:
                    if matcher not in text or matcher in answered_prompts:
                        continue
                    if matcher == "Select login method":
                        menu_position = text.find(matcher)
                        start_url_position = text.find("Start URL")
                        if start_url_seen or (
                            start_url_position >= 0
                            and start_url_position < menu_position
                        ):
                            continue
                    elif matcher == "Region" and not answered_url:
                        continue

                    pty_sock.sendall(answer)
                    answered_prompts.add(matcher)
                    if matcher == "Select login method":
                        logger.debug("Answered login method menu with Builder ID default")
                    elif matcher == "Start URL":
                        answered_url = True
                        start_url_seen = True
                        logger.debug("Answered Start URL prompt")
                    else:
                        logger.debug("Answered Region prompt")

                url_match = re.search(r'Open this URL[:\s]+(https?://\S+)', text)
                if not url_match:
                    url_match = re.search(r'(https?://\S+user_code=\S+)', text)
                code_match = re.search(r'[Cc]ode[:\s]+([A-Z0-9-]{4,})', text)
                if url_match:
                    login_url = url_match.group(1).rstrip(").,")
                    uc_match = re.search(r'user_code=([A-Z0-9-]{4,})', login_url)
                    if uc_match:
                        login_code = uc_match.group(1)
                    elif code_match:
                        login_code = code_match.group(1)
                    break
    except Exception as e:
        logger.warning("PTY read error during login: %s", e)

    if not login_url:
        raw_output = collected.decode("utf-8", errors="replace")
        try:
            pty_sock.close()
        except Exception:
            pass
        _nuke_login_container(podman, container)
        with _login_pending_lock:
            _login_pending = None
        return {"error": f"kiro-cli did not produce a login URL within 15s.\nOutput:\n{raw_output}"}

    # ── Hand off remaining stream to background thread ────────────────────────
    pty_sock.setblocking(True)

    def _drain_pty() -> None:
        try:
            while True:
                chunk = pty_sock.recv(4096)
                if not chunk:
                    break
        except Exception:
            pass
        finally:
            try:
                pty_sock.close()
            except Exception:
                pass

    drain_thread = threading.Thread(target=_drain_pty, daemon=True, name=f"pty-drain-{container}")
    drain_thread.start()

    with _login_pending_lock:
        if _login_pending is not None:
            _login_pending["exec_id"] = exec_id

    logger.info("Login flow started in %s, URL extracted", container)
    return {"login_url": login_url, "code": login_code}


def _request_source(request: Request) -> str | None:
    """Best-effort client source (IP) for audit events; None if unavailable."""
    try:
        client = getattr(request, "client", None)
        if client is not None:
            return getattr(client, "host", None) or (client[0] if isinstance(client, (tuple, list)) else None)
    except Exception:
        pass
    return None


async def _handle_login_post(request: Request) -> Response:
    """POST /login — initiate kiro-cli device auth via an ephemeral temp container.

    State machine guard:
      - 409 if ga-kiro-auth already exists and is non-empty (already authenticated)
      - 409 if a login flow is already pending

    Delegates to _initiate_login() for the actual container start and PTY flow.
    Returns the URL and code immediately so the operator can open the browser.
    """
    global _login_pending
    with _login_pending_lock:
        if _read_auth_file():
            return PlainTextResponse(
                "Already authenticated. POST /logout first.",
                status_code=409,
            )
        if _login_pending is not None:
            return PlainTextResponse(
                "Login already in progress. Poll GET /login for status.",
                status_code=409,
            )

    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

    result = _initiate_login(podman)

    if result.get("login_pending"):
        return PlainTextResponse(
            "Login already in progress. Poll GET /login for status.",
            status_code=409,
        )
    if "error" in result:
        return PlainTextResponse(result["error"], status_code=500)

    return JSONResponse({
        "status": "pending",
        "login_url": result.get("login_url"),
        "code": result.get("code"),
    })


async def _handle_login_get(request: Request) -> Response:
    """GET /login — poll whether the kiro-cli device auth flow has completed.

    Returns {status: "pending"} while the browser flow is in progress.
    On completion: writes ga-kiro-auth, injects auth into all running crews,
    nukes the temp container, clears _login_pending, returns {status: "complete"}.
    Returns 404 if no login flow is in progress.
    """
    global _login_pending
    with _login_pending_lock:
        pending = _login_pending

    if pending is None:
        return PlainTextResponse("No login in progress.", status_code=404)

    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

    auth_b64 = _read_auth_from_crew(podman, pending["container"])
    if not auth_b64:
        return JSONResponse({"status": "pending"})

    # ── Auth complete ─────────────────────────────────────────────────────────
    try:
        _write_auth_file(auth_b64)
        logger.info("ga-kiro-auth written after login completion")
    except Exception as e:
        logger.warning("Could not write auth file: %s", e)

    # Inject all currently running crews
    with _registry_lock:
        reg = _load_registry()
    for cid, info in reg["crews"].items():
        if info.get("status") == "running":
            try:
                _inject_auth(podman, info["container"], auth_b64)
                logger.info("Injected fresh auth into running crew %s", cid)
            except Exception as e:
                logger.warning("Could not inject auth into crew %s: %s", cid, e)

    # Nuke temp container and clear pending state (guarded)
    _nuke_login_container(podman, pending["container"])
    with _login_pending_lock:
        # Only clear if the pending login is the one we just completed;
        # a new concurrent login may have started between nuke and here.
        if _login_pending is not None and _login_pending.get("container") == pending["container"]:
            _login_pending = None

    _security.audit_auth_event(
        action="login", outcome="success", account="academy",
        source=_request_source(request),
        emit=logger.info,
    )
    return JSONResponse({"status": "complete"})


async def _handle_logout_post(request: Request) -> Response:
    """POST /logout — de-authenticate the Ghost Academy.

    Deletes ga-kiro-auth and wipes auth_kv rows from every running crew's
    kiro-cli DB. Returns 404 if the academy is not currently authenticated.
    """
    if not _read_auth_file():
        return PlainTextResponse("Not authenticated.", status_code=404)

    _security.audit_auth_event(
        action="logout", outcome="success", account="academy",
        source=_request_source(request), emit=logger.info,
    )

    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

    # Clear the shared auth file
    auth_path = _auth_file_path()
    try:
        auth_path.unlink(missing_ok=True)
        logger.info("Deleted ga-kiro-auth")
    except Exception as e:
        logger.warning("Could not delete ga-kiro-auth: %s", e)

    # Wipe auth rows from all running crews
    with _registry_lock:
        reg = _load_registry()
    for cid, info in reg["crews"].items():
        if info.get("status") == "running":
            try:
                podman.container_exec(
                    info["container"],
                    ["python3", f"{SCRIPTS_DIR}/wipe_auth.py", KIRO_CLI_DB],
                )
                logger.info("Cleared auth_kv from crew %s", cid)
            except Exception as e:
                logger.warning("Could not clear auth from crew %s: %s", cid, e)

    return JSONResponse({"status": "logged_out"})


# ── MCP tools: workspace ─────────────────────────────────────────────────────

@mcp.tool()
def crews() -> dict:
    """List all live crews in the registry.

    Shows crew_id, container, status, and created_at for each.
    Also includes active agents (tasks) running inside each crew.
    Also: list crews, show workspaces, what's running, sitrep.
    """
    with _registry_lock:
        reg = _load_registry()

    # Host memory visibility
    try:
        podman = _get_podman()
        host_mem = _get_host_memory_gb_cached(podman)
    except Exception:
        host_mem = None

    result = []
    for cid, info in reg["crews"].items():
        # Determine gateway health: stopped containers are unhealthy without
        # probing; running containers get a liveness probe.
        status = info.get("status", "unknown")
        if status != "running":
            gateway_healthy = False
        else:
            crew_url = _crew_url(info)
            gateway_healthy = _probe_gateway(crew_url)

        entry = {
            "crew_id": cid,
            "container": info["container"],
            "status": status,
            "composition": info.get("composition", "kirocrew"),
            "created_at": info.get("created_at"),
            "gateway_healthy": gateway_healthy,
            "crew_image_version": info.get("crew_image_version", "unknown"),
            "agents": [],
        }
        if "policy_version" in info:
            entry["policy_version"] = info["policy_version"]
        # Try to fetch active tasks from the gateway
        try:
            tasks = _crew_api(info, "GET", "/api/spawn")
            if isinstance(tasks, list):
                entry["agents"] = [
                    {
                        "task_id": a.get("id"),
                        "agent": a.get("agent", ""),
                        "done": a.get("done", False),
                        "elapsed_secs": int(a.get("elapsed", 0)),
                        "last_tool": a.get("last_tool", ""),
                    }
                    for a in tasks
                ]
            elif isinstance(tasks, dict):
                entry["agents"] = [
                    {
                        "task_id": a.get("id"),
                        "agent": a.get("agent", ""),
                        "done": a.get("done", False),
                        "elapsed_secs": int(a.get("elapsed", 0)),
                        "last_tool": a.get("last_tool", ""),
                    }
                    for a in tasks.get("agents", [])
                ]
        except Exception:
            pass  # crew may be idle/stopped — agents list stays empty
        result.append(entry)
    active_crews = sum(1 for e in result if e.get("status") == "running")
    return {
        "crews": result,
        "host_memory_available_gb": host_mem,
        "active_crews": active_crews,
        "max_active_crews": GA_MAX_ACTIVE_CREWS,
    }


@mcp.resource(
    "transport://compositions",
    name="compositions",
    title="Available Crew Compositions",
    description="Lists the crew compositions available for launch — name, description, and optional image override for each.",
    mime_type="text/plain",
)
def resource_compositions() -> str:
    """Return available crew compositions from the registry."""
    if not COMPOSITION_REGISTRY:
        return "No compositions registered. Defaulting to 'kirocrew'."
    lines = []
    for entry in COMPOSITION_REGISTRY.values():
        image_note = f" (image: {entry['image']})" if entry.get("image") else ""
        lines.append(f"## {entry['name']}\n{entry['description']}{image_note}")
    return "\n\n".join(lines)


@mcp.tool()
def launch(crew_id: str, composition: str = "spec-ops") -> dict:
    """Summon a new crew container into existence, with its own workspace volume.

    Creates an isolated crew: a full KiroCrew instance (gateway + agent pool)
    with a dedicated workspace. Repository seeding is a separate supply step.
    Also: calldown, create workspace, launch crew, init environment, load the ghostship.

    Requires prior authentication. If not authenticated, launch automatically
    initiates the device auth flow and returns login_url and code so the caller
    can complete auth and retry launch — no separate POST /login call needed.

    Args:
        crew_id: Name for this crew (e.g. 'general', 'srv-refactor'). Must be
                 unique. Use lowercase letters, numbers, hyphens.
        composition: Crew composition to launch (default: "spec-ops"). See the
                     transport://compositions resource for available compositions.

    Returns crew_id and status once the gateway is ready (~30s).
    """
    if not re.match(r'^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$|^[a-z0-9]$', crew_id):
        return {"error": "crew_id must be lowercase alphanumeric/hyphens, 1-50 chars"}

    # Resolve crew type from registry
    composition_entry = _resolve_composition(composition)
    if composition_entry is None:
        available = list(COMPOSITION_REGISTRY.keys())
        return {"error": f"Unknown composition '{composition}'. Available: {available}"}

    image = _resolve_image(composition_entry)
    container = f"{CREW_CONTAINER_PREFIX}{crew_id}"
    volume = f"{CREW_VOLUME_PREFIX}{crew_id}"
    home_volume = f"{CREW_HOME_VOLUME_PREFIX}{crew_id}"

    try:
        podman = _get_podman()
    except Exception as e:
        return {"error": str(e)}

    # ── Auth check — before registry write to avoid orphaned entries ──────────
    auth_b64: str | None = _read_auth_file() or None
    if not auth_b64:
        result = _initiate_login(podman)
        if result.get("login_pending"):
            return {
                "error": "not_authenticated",
                "login_pending": True,
                "instructions": "Login already in progress. Poll GET /login, then call launch again.",
            }
        if "error" in result:
            return {"error": result["error"]}
        return {
            "error": "not_authenticated",
            "login_url": result.get("login_url"),
            "code": result.get("code"),
            "instructions": "Open login_url to authenticate, then call launch again.",
        }

    with _registry_lock:
        reg = _load_registry()
        existing = reg["crews"].get(crew_id)
        if existing:
            return {"error": f"Crew '{crew_id}' already exists. Nuke it first to recreate."}
        if len(reg["crews"]) >= GA_MAX_CREWS:
            return {"error": f"Registered crew limit ({GA_MAX_CREWS}) reached. Nuke one first."}
        # Pre-insert a placeholder to prevent concurrent launches with the same id
        reg["crews"][crew_id] = {"status": "launching", "container": container}
        _save_registry(reg)

    try:
        podman.network_create(GA_NETWORK)
        podman.volume_create(volume)
        podman.volume_create(home_volume)
        logger.info("Created volumes %s, %s", volume, home_volume)

        # Build container env — always include CORS and sandbox flag.
        # When GA_GIT_AUTHOR_NAME and GA_GIT_AUTHOR_EMAIL are both set, inject
        # all four git identity vars so they are part of the container's process
        # environment from startup and inherited by the gateway and every kiro-cli
        # child it spawns.  /etc/environment is NOT used because it is only read
        # by PAM login sessions, not by non-login processes like the gateway.
        container_env: dict[str, str] = {
            "KIROCREW_CORS_ORIGINS": f"http://{container}:{CREW_GATEWAY_PORT}",
            "KIROCREW_ALLOW_UNSANDBOXED": "1",
        }
        if GA_GIT_AUTHOR_NAME and GA_GIT_AUTHOR_EMAIL:
            container_env["GIT_AUTHOR_NAME"] = GA_GIT_AUTHOR_NAME
            container_env["GIT_AUTHOR_EMAIL"] = GA_GIT_AUTHOR_EMAIL
            container_env["GIT_COMMITTER_NAME"] = GA_GIT_AUTHOR_NAME
            container_env["GIT_COMMITTER_EMAIL"] = GA_GIT_AUTHOR_EMAIL
        podman.container_create(
            name=container,
            image=image,
            env=container_env,
            network=GA_NETWORK,
            workspace_volume=volume,
            home_volume=home_volume,
        )
        podman.container_start(container)
        logger.info("Started %s", container)

        crew_url = f"http://{container}:{CREW_GATEWAY_PORT}"
        if not _wait_gateway(crew_url, timeout=30):
            _cleanup_crew(podman, container, volume, home_volume)
            with _registry_lock:
                reg = _load_registry()
                reg["crews"].pop(crew_id, None)
                _save_registry(reg)
            return {"error": f"Gateway not ready within 30s for crew {crew_id}"}

        return _finish_crew_setup(podman, crew_id, container, volume, home_volume, auth_b64, composition, composition_entry)

    except Exception as e:
        logger.error("Launch failed for %s: %s", crew_id, e)
        try:
            _cleanup_crew(podman, container, volume, home_volume)
        except Exception:
            pass
        with _registry_lock:
            reg = _load_registry()
            reg["crews"].pop(crew_id, None)
            _save_registry(reg)
        return {"error": f"Launch failed: {e}"}


@mcp.tool()
def supply(
    path: str,
    crew_id: str | None = None,
    unpack: bool = False,
    bundle: bool = False,
) -> dict:
    """Deliver a file, archive, or git bundle into a crew's workspace via a presigned upload URL.

    Returns a URL to POST raw file bytes to. Use curl or any HTTP client
    to upload from your local machine — no credentials required beyond
    network access to the transport host.

    For directory trees, set unpack=True and POST a .tar or .tar.gz —
    it will be extracted at the given path in the workspace. For a real
    git checkout, set bundle=True and POST the output of ``git bundle create``;
    the bundle is cloned into the destination inside the crew.

    Pairs with evac, which extracts files, diffs, or git bundles out. Together
    they are the complete file exchange protocol for crew workspaces.
    Also: deliver, inject, upload, seed workspace, push file.

    Examples:
        # Single file
        curl -X POST <url> --data-binary @./myfile.py

        # Directory tree (tar)
        tar -czf - ./myrepo | curl -X POST "<url>&unpack=1" --data-binary @-

        # Git history (bundle)
        git bundle create ./myrepo.bundle --all
        curl -X POST "<url>&bundle=1" --data-binary @./myrepo.bundle

    Args:
        path: Destination path in the workspace (e.g. "repo/config.json",
              "repo" when unpacking a tar, or "repo" for a bundle clone).
        crew_id: Which crew workspace to deliver into. Required.
        unpack: If True, the upload URL will unpack a tar/tar.gz at path.
        bundle: If True, the upload URL will clone a git bundle into path.
    """
    if unpack and bundle:
        return {"error": "unpack and bundle cannot both be True"}

    clean = path.lstrip("/")
    if ".." in clean.split("/"):
        return {"error": "Invalid path — no traversal allowed"}

    try:
        _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}

    url = _sign_upload_url(crew_id, clean, unpack=unpack, bundle=bundle)
    if unpack:
        url += "&unpack=1"
    if bundle:
        url += "&bundle=1"

    if bundle:
        curl_example = f'curl -X POST "{url}" --data-binary @./your-repo.bundle'
    elif unpack:
        curl_example = f'tar -czf - ./your-dir | curl -X POST "{url}" --data-binary @-'
    else:
        curl_example = f'curl -X POST "{url}" --data-binary @./your-file'

    return {
        "crew_id": crew_id,
        "path": clean,
        "delivery_url": url,
        "method": "POST",
        "unpack": unpack,
        "bundle": bundle,
        "expires_secs": GA_FILE_TTL_SECS,
        "example": curl_example,
    }


@mcp.tool()
def evac(
    path: str,
    ref: str | None = None,
    crew_id: str | None = None,
    bundle: bool = False,
) -> dict:
    """Extract files, diffs, or git bundles from a crew workspace.

    Returns a direct download URL to the file on the transport server.
    Fetch the URL from any client that can reach the transport host —
    no LLM in the content path, works for binary and large files.
    Also: extract, exfil, pull, get file, show diff.

    Args:
        path: File path relative to the workspace root, or a directory
              containing a git repository when bundle=True.
        ref: Optional git ref/range to diff against, or to bundle. With
             bundle=True and no ref, all reachable refs are bundled.
        crew_id: Which crew workspace to read from. Required.
        bundle: If True, return a git bundle instead of a file or diff.
    """
    clean = path.lstrip("/")
    if not clean:
        return {"error": "path must not be empty"}
    if ".." in clean.split("/"):
        return {"error": "Invalid path — no traversal allowed"}

    try:
        _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}

    url = _sign_file_url(crew_id, clean, ref, bundle)
    result = {
        "crew_id": crew_id,
        "path": path,
        "bundle": bundle,
        "expires_secs": GA_FILE_TTL_SECS,
    }
    if ref:
        result["ref"] = ref
    result["url"] = url
    return result


@mcp.tool()
def nuke(crew_id: str, confirm: bool = False) -> dict:
    """Destroy a crew completely — tear down its container and both volumes.

    With confirm=True: stops and removes the container and both volumes.
    Total teardown — no residue.
    Without confirm: shows what would be nuked.
    Also: destroy, teardown, kill.

    Idle crews stop and restart automatically — use nuke only when you want to
    discard the workspace entirely.

    Args:
        crew_id: The crew to nuke.
        confirm: Must be True to proceed. Safety guard.
    """
    try:
        crew = _get_crew(crew_id)
    except KeyError as e:
        return {"error": str(e)}

    if not confirm:
        active: list = []
        try:
            tasks = _crew_api(crew, "GET", "/api/spawn")
            active = [a for a in tasks.get("agents", []) if not a.get("done")]
        except Exception:
            pass
        with _registry_lock:
            reg = _load_registry()
        schedules = _get_crew_schedules(reg, crew_id)
        return {
            "warning": f"Pass confirm=True to tear down crew '{crew_id}'",
            "container": crew.get("container", f"{CREW_CONTAINER_PREFIX}{crew_id}"),
            "volumes": [crew.get("volume", f"{CREW_VOLUME_PREFIX}{crew_id}"), crew.get("home_volume", f"{CREW_HOME_VOLUME_PREFIX}{crew_id}")],
            "active_tasks": len(active),
            "scheduled_jobs": len(schedules),
            "scheduled_job_names": [s.get("name", "") for s in schedules],
        }

    try:
        podman = _get_podman()
    except Exception as e:
        return {"error": str(e)}

    # A failed launch may leave a partial registry entry with only 'container'
    # and 'status: launching' — fall back to conventional names for anything missing.
    container = crew.get("container", f"{CREW_CONTAINER_PREFIX}{crew_id}")
    vol = crew.get("volume", f"{CREW_VOLUME_PREFIX}{crew_id}")
    home_vol = crew.get("home_volume", f"{CREW_HOME_VOLUME_PREFIX}{crew_id}")
    try:
        if not container.startswith(CREW_CONTAINER_PREFIX):
            raise RuntimeError(f"Refusing to nuke non-crew container: {container!r}")
        if not vol.startswith(CREW_VOLUME_PREFIX):
            raise RuntimeError(f"Refusing to nuke non-crew volume: {vol!r}")
    except RuntimeError as e:
        return {"error": str(e)}

    # TRN-59: cancel gateway cron jobs before teardown (best-effort).
    # Use bare _crew_api (not _crew_api_with_recovery) to avoid restarting a
    # container we are about to destroy.
    with _registry_lock:
        reg = _load_registry()
    schedules = _get_crew_schedules(reg, crew_id)
    for sched in schedules:
        job_id = sched.get("job_id", "")
        try:
            _crew_api(crew, "DELETE", f"/api/crons/{job_id}")
        except Exception as e:
            logger.warning("nuke: failed to cancel cron %s for crew %s: %s", job_id, crew_id, e)

    _cleanup_crew(podman, container, vol, home_vol)

    with _registry_lock:
        reg = _load_registry()
        reg["crews"].pop(crew_id, None)
        _save_registry(reg)

    with _captain_order_locks_lock:
        _captain_order_locks.pop(crew_id, None)

    logger.info("Crew %s nuked", crew_id)
    return {"crew_id": crew_id, "status": "nuked", "container": container}



@mcp.tool()
def captain(
    crew_id: str,
    action: str = "order",
    message: str | None = None,
    template: str | None = None,
    change_name: str | None = None,
    cron: str | None = None,
    interval: int | None = None,
    timezone: str = "UTC",
    fire_immediately: bool | None = None,
) -> dict:
    """Manage the single Raven-backed standing-orders Captain for a crew.

    ``order`` requires exactly one of ``message`` or ``template``. A named
    template is resolved before it is written to ``captain@localhost``;
    ``sdd`` is the built-in template and uses ``change_name`` to name the
    OpenSpec change it should drive. The resolved order shares the same
    recurring Raven check-in as a hand-written message. ``stop`` pauses that
    check-in without deleting it, and ``status`` reports its durable state.

    When fire_immediately is True (the default for interval-based check-ins),
    Raven is dispatched once immediately after a newly created check-in job,
    before the first scheduled interval or cron tick fires. Resuming a
    previously paused check-in never fires immediately regardless of this
    parameter.
    Also: supervise, oversee, autopilot, govern, sitrep, status.

    Args:
        crew_id: Which crew's Captain to manage. Required.
        action: One of ``order``, ``stop``, or ``status``.
        message: Free-form standing order text.
        template: Name of a built-in standing-order template, currently
            ``sdd``.
        change_name: Substitution value for a template that names an OpenSpec
            change.
        cron: Cron expression for a new standing-orders check-in.
        interval: Fixed interval in seconds for a new standing-orders check-in.
        timezone: IANA timezone for cron interpretation, matching schedule().
        fire_immediately: Whether to dispatch Raven once immediately when a
            new check-in is created. Defaults to True when interval is set,
            False when cron is set. Ignored on resume of a paused job.
    """
    if action not in {"order", "stop", "status"}:
        return {"error": "action must be one of: order, stop, status"}

    if action == "order":
        has_message = message is not None
        has_template = template is not None
        if has_message == has_template:
            return {"error": "order requires exactly one of message or template"}
        if cron is not None and interval is not None:
            return {"error": "Provide cron or interval, not both"}
        if has_template:
            if change_name is None and template == "sdd":
                return {"error": "template 'sdd' requires change_name"}
            try:
                order_message = _resolve_order_template(template, change_name)
            except ValueError as exc:
                return {"error": str(exc)}
        else:
            if not message:
                return {"error": "message is required for order"}
            if change_name is not None:
                return {"error": "change_name requires template"}
            order_message = message
    elif any(
        value is not None
        for value in (message, template, change_name, cron, interval, fire_immediately)
    ) or timezone != "UTC":
        return {
            "error": f"{action} does not accept message, template, change_name, cron, interval, fire_immediately, or timezone"
        }

    try:
        crew = _require_crew(crew_id)
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}

    if action == "order":
        try:
            crew = _ensure_crew_running(crew, crew_id)
        except (ValueError, KeyError, RuntimeError) as exc:
            return {"error": str(exc)}

        with _captain_order_lock(crew_id):
            try:
                cron_listing = _crew_api_with_recovery(crew, crew_id, "GET", "/api/crons")
            except (ValueError, KeyError, RuntimeError, CrewUnresponsiveError) as exc:
                return {"error": str(exc)}
            except Exception as exc:
                return {"error": f"Could not inspect Captain check-in jobs: {exc}"}

            existing_job = _captain_checkin_job(cron_listing)
            enabled_job = _captain_checkin_job(cron_listing, enabled_only=True)
            if existing_job is None and not cron and not interval:
                return {
                    "error": "A new Captain check-in requires either cron or interval",
                }

            job = existing_job
            is_new_job = False
            if job is None:
                body: dict[str, Any] = {
                    "name": _CAPTAIN_CHECKIN_JOB_NAME,
                    "message": _CAPTAIN_CHECKIN_TASK,
                    "agent": "raven",
                }
                if cron:
                    body["cron"] = cron
                    body["timezone"] = timezone
                else:
                    body["every"] = interval
                try:
                    job = _crew_api_with_recovery(crew, crew_id, "POST", "/api/crons", json=body)
                except Exception as exc:
                    return {"error": f"Could not create Captain check-in: {exc}"}
                job = dict(job)
                is_new_job = True
            elif enabled_job is None:
                try:
                    toggle = _crew_api_with_recovery(
                        crew,
                        crew_id,
                        "POST",
                        f"/api/crons/{job.get('id')}/enable",
                        json={"enabled": True},
                    )
                    if isinstance(toggle, dict) and toggle.get("ok") is False:
                        return {"error": "Could not resume Captain check-in: job not found"}
                except Exception as exc:
                    return {"error": f"Could not resume Captain check-in: {exc}"}
                job = dict(job)
                job["enabled"] = True

            # TRN-29: Write schedule entry to transport registry
            schedule_entry = {
                "job_id": job.get("id"),
                "name": _CAPTAIN_CHECKIN_JOB_NAME,
                "interval_secs": interval,
                "cron_expr": cron,
                "next_fire_at": time.time() + (interval or 60),
                "agent": "raven",
                "message": _CAPTAIN_CHECKIN_TASK,
                "enabled": True,
            }
            try:
                with _registry_lock:
                    reg = _load_registry()
                    _upsert_crew_schedule(reg, crew_id, schedule_entry)
                    _save_registry(reg)
            except Exception as exc:
                logger.warning("TRN-29: Could not persist schedule entry: %s", exc)

            # Only append an order after the check-in exists and is enabled.  A
            # failed provisioning call must not leave mail that no Raven can read.
            try:
                podman = _get_podman()
                _append_captain_mail(podman, crew["container"], order_message, crew_id=crew_id)
            except Exception as exc:
                return {"error": f"Could not write Captain order: {exc}"}

            result: dict[str, Any] = {
                "crew_id": crew_id,
                "action": "order",
                "status": "ordered",
                "mode": "standing-orders",
                "job_id": job.get("id"),
                "mailbox": "captain@localhost",
                "schedule": job.get("schedule") or cron or (
                    f"every {interval}s" if interval else None
                ),
            }

            # Immediate dispatch: only for newly created jobs (not resumes)
            if is_new_job:
                should_fire = fire_immediately if fire_immediately is not None else (interval is not None)
                if should_fire:
                    try:
                        _crew_api_with_recovery(
                            crew, crew_id, "POST", "/api/spawn",
                            json={"task": _CAPTAIN_CHECKIN_TASK, "agent": "raven", "keep": True},
                        )
                    except Exception as exc:
                        result["immediate_dispatch_error"] = str(exc)

            return result

    try:
        crew = _ensure_crew_running(crew, crew_id)
        podman = _get_podman()
    except (ValueError, KeyError, RuntimeError) as exc:
        return {"error": str(exc)}

    try:
        cron_listing = _crew_api_with_recovery(crew, crew_id, "GET", "/api/crons")
        standing_job = _captain_checkin_job(cron_listing)
    except Exception as exc:
        return {"error": f"Could not inspect Captain check-in jobs: {exc}"}

    if standing_job is None:
        if action == "status":
            try:
                unread_mail = _mail_count(
                    podman, crew["container"], _CAPTAIN_MAILBOX_PATH
                )
                unread_admiral_mail = _mail_count(
                    podman, crew["container"], _ADMIRAL_MAILBOX_PATH
                )
            except Exception as exc:
                return {"error": f"Could not read Captain or Admiral mailbox: {exc}"}
            return {
                "crew_id": crew_id,
                "action": action,
                "status": "dormant",
                "mode": "standing-orders",
                "job_id": None,
                "enabled": False,
                "unread_mail": unread_mail,
                "mailbox": "captain@localhost",
                "unread_admiral_mail": unread_admiral_mail,
                "admiral_mailbox": "admiral@localhost",
            }
        return {
            "crew_id": crew_id,
            "action": "stop",
            "status": "dormant",
            "mode": "standing-orders",
            "job_id": None,
            "enabled": False,
            "mailbox": "captain@localhost",
        }

    if action == "stop" and standing_job.get("enabled", False):
        try:
            toggle = _crew_api_with_recovery(
                crew,
                crew_id,
                "POST",
                f"/api/crons/{standing_job.get('id')}/enable",
                json={"enabled": False},
            )
            if isinstance(toggle, dict) and toggle.get("ok") is False:
                return {"error": "Could not stop Captain check-in: job not found"}
        except Exception as exc:
            return {"error": f"Could not stop Captain check-in: {exc}"}
        standing_job = dict(standing_job)
        standing_job["enabled"] = False

        # TRN-29: Set enabled=False in registry entry (do not remove)
        try:
            with _registry_lock:
                reg = _load_registry()
                schedules = _get_crew_schedules(reg, crew_id)
                for sched in schedules:
                    if sched.get("job_id") == standing_job.get("id"):
                        sched["enabled"] = False
                        break
                _save_registry(reg)
        except Exception as exc:
            logger.warning("TRN-29: Could not update schedule entry on stop: %s", exc)

    result = _captain_standing_view(
        crew_id,
        action,
        standing_job,
        podman,
        crew["container"],
    )
    if action == "stop":
        result["status"] = "stopped"
    return result


@mcp.tool()
def schedule(
    name: str = "",
    message: str = "",
    crew_id: str | None = None,
    cron: str | None = None,
    interval: int | None = None,
    delay: int | None = None,
    agent: str = "ghost",
    timezone: str = "UTC",
    fire_immediately: bool | None = None,
    action: str = "create",
    job_id: str | None = None,
) -> dict:
    """Book, cancel, or list recurring tasks on KiroCrew.

    Use for anything that should run on a timer — daily reports, periodic
    checks, background maintenance — without manual dispatching each time.
    Provide either a cron expression, an interval in seconds, or a delay for
    one-shot execution. Both recurring work and one-off dispatches default to
    Ghost; pass an explicit persona when another worker, including Raven for a
    Captain check-in, is intended.

    When fire_immediately is True (the default for interval jobs), the job's
    task is dispatched once immediately after creation, before the first
    scheduled interval or cron tick fires. The immediate dispatch uses the
    same dispatch() mechanism as a normal scheduled run. The schedule itself
    is unaffected — the next fire still occurs at created_at + interval.
    Also: book, recur, cron, timer, automate.

    Args:
        action: One of "create" (default), "cancel", or "list".
        name: A short name for the job (required for create).
        message: The task instruction to run on each trigger (required for create).
        crew_id: Which crew to schedule on. Required.
        cron: 5-field cron expression (e.g. '0 9 * * 1' for Monday 9am).
        interval: Run every N seconds (minimum 60).
        delay: Fire once after N seconds (one-shot). Creates a job that fires
            once and returns a job_id. Minimum 1 second.
        agent: Agent to use. Defaults to ghost, matching dispatch().
        timezone: IANA timezone for cron interpretation.
        fire_immediately: Whether to dispatch the task once immediately on
            creation. Defaults to True when interval is set, False when cron
            is set. Explicit values override the default.
        job_id: Job ID to cancel (required for action="cancel").
    """
    if action not in ("create", "cancel", "list"):
        return {"error": "action must be one of: create, cancel, list"}

    if action == "cancel":
        return _schedule_cancel(job_id, crew_id)
    if action == "list":
        return _schedule_list(crew_id)

    # action == "create"
    if not name:
        return {"error": "name is required for action='create'"}
    if not message:
        return {"error": "message is required for action='create'"}
    try:
        _validate_agent(agent)
    except ValueError as e:
        return {"error": str(e)}
    if name == _CAPTAIN_CHECKIN_JOB_NAME:
        return {
            "error": f"Job name {_CAPTAIN_CHECKIN_JOB_NAME!r} is reserved for the "
            "Captain check-in — use captain(action=\"order\", ...) instead"
        }
    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}

    # Validate: exactly one of cron, interval, or delay
    schedule_params = sum(1 for p in (cron, interval, delay) if p is not None)
    if schedule_params == 0:
        return {"error": "Provide one of: cron, interval, or delay"}
    if schedule_params > 1:
        return {"error": "Provide only one of: cron, interval, or delay"}

    # TRN-29: delay creates a one-shot job
    if delay is not None:
        if delay < 1:
            return {"error": "delay must be >= 1"}
        import datetime as _dt
        fire_at = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=delay)
        cron_expr = f"{fire_at.minute} {fire_at.hour} {fire_at.day} {fire_at.month} *"
        body: dict = {
            "name": name,
            "message": message,
            "agent": agent,
            "cron": cron_expr,
        }
        try:
            r = _crew_api_with_recovery(crew, crew_id, "POST", "/api/crons", json=body)
        except (CrewUnresponsiveError, RuntimeError) as e:
            return {"error": str(e)}

        # Write one-shot entry to registry
        schedule_entry = {
            "job_id": r.get("id"),
            "name": name,
            "interval_secs": None,
            "cron_expr": cron_expr,
            "next_fire_at": time.time() + delay,
            "agent": agent,
            "message": message,
            "enabled": True,
            "one_shot": True,
        }
        try:
            with _registry_lock:
                reg = _load_registry()
                _upsert_crew_schedule(reg, crew_id, schedule_entry)
                _save_registry(reg)
        except Exception as exc:
            logger.warning("TRN-29: Could not persist one-shot schedule entry: %s", exc)

        return {
            "job_id": r.get("id"),
            "crew_id": crew_id,
            "name": name,
            "status": "scheduled",
            "delay": delay,
        }
    body: dict = {"name": name, "message": message, "agent": agent}
    if cron:
        body["cron"] = cron
        body["timezone"] = timezone
    else:
        body["every"] = interval
    try:
        r = _crew_api_with_recovery(crew, crew_id, "POST", "/api/crons", json=body)
    except (CrewUnresponsiveError, RuntimeError) as e:
        return {"error": str(e)}

    # TRN-29: Write schedule entry to transport registry
    schedule_entry = {
        "job_id": r.get("id"),
        "name": name,
        "interval_secs": interval,
        "cron_expr": cron,
        "next_fire_at": time.time() + (interval or 60),
        "agent": agent,
        "message": message,
        "enabled": True,
    }
    try:
        with _registry_lock:
            reg = _load_registry()
            _upsert_crew_schedule(reg, crew_id, schedule_entry)
            _save_registry(reg)
    except Exception as exc:
        logger.warning("TRN-29: Could not persist schedule entry: %s", exc)

    # Resolve fire_immediately default: True for interval, False for cron
    should_fire = fire_immediately if fire_immediately is not None else (interval is not None)

    result: dict[str, Any] = {
        "job_id": r.get("id"),
        "crew_id": crew_id,
        "name": name,
        "schedule": cron or f"every {interval}s",
        "status": "scheduled",
    }

    if should_fire:
        try:
            _crew_api_with_recovery(
                crew, crew_id, "POST", "/api/spawn",
                json={"task": message, "agent": agent, "keep": True},
            )
        except Exception as exc:
            result["immediate_dispatch_error"] = str(exc)

    return result


def _schedule_cancel(job_id: str | None, crew_id: str | None) -> dict:
    """Cancel (delete) a scheduled job by ID — removes from registry AND gateway."""
    if not job_id:
        return {"error": "job_id is required for action='cancel'"}
    if not crew_id:
        return {"error": "crew_id is required for action='cancel'"}

    # TRN-29: Check registry for captain guard before touching gateway
    try:
        with _registry_lock:
            reg = _load_registry()
            schedules = _get_crew_schedules(reg, crew_id)
            for sched in schedules:
                if sched.get("job_id") == job_id:
                    if (
                        sched.get("name") == _CAPTAIN_CHECKIN_JOB_NAME
                        and sched.get("agent") == "raven"
                    ):
                        return {
                            "error": f"Cannot cancel the Captain check-in job — "
                            "use captain(action=\"stop\", ...) instead"
                        }
                    break
    except Exception:
        pass  # Registry unavailable — proceed with gateway check

    # Try to cancel in gateway (if crew is running)
    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
        # Guard against cancelling the captain check-in job (gateway check)
        try:
            cron_listing = _crew_api_with_recovery(crew, crew_id, "GET", "/api/crons")
            jobs = _captain_jobs(cron_listing)
            for job in jobs:
                if job.get("id") == job_id:
                    if (
                        job.get("name") == _CAPTAIN_CHECKIN_JOB_NAME
                        and job.get("agent") == "raven"
                    ):
                        return {
                            "error": f"Cannot cancel the Captain check-in job — "
                            "use captain(action=\"stop\", ...) instead"
                        }
                    break
        except (CrewUnresponsiveError, RuntimeError):
            pass  # Gateway unavailable — still cancel from registry

        try:
            _crew_api_with_recovery(crew, crew_id, "DELETE", f"/api/crons/{job_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                pass  # Not in gateway, but may still be in registry
            else:
                return {"error": str(e)}
        except (CrewUnresponsiveError, RuntimeError):
            pass  # Gateway unavailable — still cancel from registry
    except (ValueError, KeyError, RuntimeError):
        pass  # Crew not running — still remove from registry

    # TRN-29: Remove from registry
    try:
        with _registry_lock:
            reg = _load_registry()
            _remove_crew_schedule(reg, crew_id, job_id)
            _save_registry(reg)
    except Exception as exc:
        logger.warning("TRN-29: Could not remove schedule entry from registry: %s", exc)

    return {"status": "cancelled", "job_id": job_id}


def _schedule_list(crew_id: str | None) -> dict:
    """List all scheduled jobs for a crew.

    Reads from the transport registry as the authoritative source.
    Falls back to the gateway if no registry entries exist (backward compat).
    """
    if not crew_id:
        return {"error": "crew_id is required"}

    # TRN-29: Read from registry first
    with _registry_lock:
        reg = _load_registry()
        schedules = _get_crew_schedules(reg, crew_id)

    if schedules:
        result_jobs = []
        for sched in schedules:
            result_jobs.append({
                "job_id": sched.get("job_id"),
                "name": sched.get("name"),
                "schedule": sched.get("cron_expr") or (
                    f"every {sched['interval_secs']}s" if sched.get("interval_secs") else None
                ),
                "agent": sched.get("agent"),
                "enabled": sched.get("enabled", True),
                "last_run": None,
            })
        return {"jobs": result_jobs}

    # Backward compat: fall back to gateway if no registry entries
    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}

    try:
        cron_listing = _crew_api_with_recovery(crew, crew_id, "GET", "/api/crons")
    except (CrewUnresponsiveError, RuntimeError) as e:
        return {"error": str(e)}

    jobs = _captain_jobs(cron_listing)
    result_jobs = []
    for job in jobs:
        result_jobs.append({
            "job_id": job.get("id"),
            "name": job.get("name"),
            "schedule": job.get("schedule"),
            "agent": job.get("agent"),
            "enabled": job.get("enabled", False),
            "last_run": job.get("last_run_ts"),
        })
    return {"jobs": result_jobs}


@mcp.tool()
def dispatch(task: str, agent: str = "ghost", crew_id: str | None = None) -> dict:
    """Spawn a task on a KiroCrew agent, dispatched for autonomous execution.

    Use this to send work to a ghost, spectre, banshee, wraith, reaper, or raven —
    research, coding, shell commands, file edits, anything that can run
    unattended. Always immediate — returns a task_id. For delayed execution,
    use schedule(delay=N) instead.
    Also: dropoff, send, assign.

    Returns a task_id to use with status/pickup/update.

    Args:
        task: What to do. Be specific — the agent has no other context.
        agent: Which agent to use. Default is 'ghost' (general-purpose).
        crew_id: Which crew to dispatch to. Required — use launch first.
    """
    try:
        _validate_agent(agent)
    except ValueError as e:
        return {"error": str(e)}
    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}

    try:
        result = _crew_api_with_recovery(
            crew, crew_id, "POST", "/api/spawn",
            json={"task": task, "agent": agent, "keep": True},
        )
    except CrewUnresponsiveError as e:
        return {"error": str(e)}
    return {
        "task_id": result.get("id"),
        "crew_id": crew_id,
        "status": "dispatched",
        "task": task,
        "agent": agent,
    }


@mcp.tool()
def steer(
    task_id: str,
    message: str,
    crew_id: str | None = None,
    force: bool = False,
) -> dict:
    """Guide a running task mid-flight, or continue a completed one.

    For running tasks: redirects the agent — add constraints, correct
    direction, provide new information. With ``force=True``, hard-stops the
    underlying process before resuming the same session with the message.
    For completed tasks: resumes the existing session via /continue —
    the agent picks up where it left off with full prior context intact.
    Sessions persist until the crew is nuked.
    Also: redirect, update, continue, follow up, add context.

    Args:
        task_id: The task to steer or continue.
        message: The instruction or follow-up to send.
        crew_id: Which crew the task belongs to. Required.
        force: Hard-stop a running task before continuing its session.
    """
    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}
    try:
        s = _crew_api_with_recovery(crew, crew_id, "GET", f"/api/spawn/{task_id}")
    except CrewUnresponsiveError as e:
        return {"error": str(e)}
    if s.get("done", False):
        try:
            r = _crew_api_with_recovery(crew, crew_id, "POST", f"/api/spawn/{task_id}/continue",
                          json={"task": message})
        except CrewUnresponsiveError as e:
            return {"error": str(e)}
        return {"task_id": r.get("id", task_id), "crew_id": crew_id,
                "action": "redeployed", "message": message}
    if force:
        try:
            _crew_api_with_recovery(crew, crew_id, "DELETE", f"/api/spawn/{task_id}")
            r = _crew_api_with_recovery(crew, crew_id, "POST", f"/api/spawn/{task_id}/continue",
                          json={"task": message})
        except CrewUnresponsiveError as e:
            return {"error": str(e)}
        return {"task_id": r.get("id", task_id), "crew_id": crew_id,
                "action": "force_redeployed", "message": message}
    try:
        _crew_api_with_recovery(crew, crew_id, "POST", f"/api/spawn/{task_id}/steer", json={"message": message})
    except CrewUnresponsiveError as e:
        return {"error": str(e)}
    return {"task_id": task_id, "crew_id": crew_id, "action": "steered", "message": message}


@mcp.tool()
def pickup(
    task_id: str | None = None,
    crew_id: str | None = None,
    timeout_secs: int = 0,
) -> dict | list:
    """Check a task's progress, retrieve its completed result, or list all tasks.

    With a task_id: returns current state including mail counts. Sessions are
    preserved after completion — use steer to continue the session, or nuke to
    destroy it. Also: collect, get result, check progress.

    Without a task_id: returns all tasks currently running or recently finished
    in the crew, plus a per-agent mail summary. Also: list, overview,
    what's happening.

    When timeout_secs > 0, polls every 3s until a task completes or the timeout
    elapses. Returns early with reason="admiral_mail" if new Admiral mail
    arrives during polling. With timeout_secs=0 (the default), checks once and
    returns immediately — equivalent to legacy behavior.
    Also (with timeout_secs > 0): bridge, watch, monitor, patrol, poll.

    Args:
        task_id: Specific task to check/collect. Omit to list all tasks.
        crew_id: Which crew the task belongs to. Required.
        timeout_secs: Maximum seconds to poll before returning. 0 means
            check once and return immediately (default).
    """
    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}

    try:
        podman = _get_podman()
    except Exception as e:
        return {"error": str(e)}

    container = crew["container"]
    effective_timeout = min(max(0, timeout_secs), GA_PICKUP_MAX_POLL_SECS) if timeout_secs > 0 else 0

    if task_id:
        return _pickup_single(crew, crew_id, task_id, podman, container, effective_timeout)
    else:
        return _pickup_list(crew, crew_id, podman, container, effective_timeout)


def _pickup_single(
    crew: dict,
    crew_id: str,
    task_id: str,
    podman: PodmanClient,
    container: str,
    timeout_secs: int,
) -> dict:
    """Single-task pickup with optional polling and mail state."""
    # Capture initial admiral mail count for early-return detection using a
    # single batched exec rather than a dedicated _mail_count call.
    if timeout_secs > 0:
        initial_counts = _read_all_mail_counts(podman, container)
        initial_admiral_mail = initial_counts.get("admiral", 0)
    else:
        initial_admiral_mail = 0
    deadline = time.monotonic() + timeout_secs

    while True:
        try:
            r = _crew_api_with_recovery(crew, crew_id, "GET", f"/api/spawn/{task_id}")
        except CrewUnresponsiveError as e:
            return {"error": str(e), "task_id": task_id, "crew_id": crew_id}
        done = r.get("done", False)

        # Single exec reads all mailboxes at once.
        mail_counts = _read_all_mail_counts(podman, container)
        mail_subjects = _read_all_mail_subjects(podman, container)
        agent_persona = r.get("agent", "")
        agent_mail = mail_counts.get(agent_persona, 0) if agent_persona else 0
        admiral_mail = mail_counts.get("admiral", 0)
        captain_mail = mail_counts.get("captain", 0)

        out: dict[str, Any] = {
            "task_id": r.get("id"),
            "crew_id": crew_id,
            "done": done,
            "turns": r.get("turns", 0),
            "last_tool": r.get("last_tool", ""),
            "elapsed_secs": int(r.get("elapsed", 0)),
            "result": r.get("result", ""),
            "error": r.get("error", ""),
            "outcome": r.get("outcome", ""),
            "agent_mail": agent_mail,
            "admiral_mail": admiral_mail,
            "captain_mail": captain_mail,
        }

        # Include subject lines for the agent, captain, and admiral mailboxes.
        if agent_persona:
            out[f"{agent_persona}_subjects"] = mail_subjects.get(agent_persona, [])
        out["captain_subjects"] = mail_subjects.get("captain", [])
        out["admiral_subjects"] = mail_subjects.get("admiral", [])

        if done or timeout_secs == 0:
            return out

        # Check for admiral mail early-return
        if admiral_mail > initial_admiral_mail:
            out["reason"] = "admiral_mail"
            return out

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if not done:
                out["reason"] = "timeout"
            return out

        # F-03 audit: @mcp.tool() handlers are dispatched via run_in_executor
        # (confirmed: MCPServer.streamable_http_app wraps sync handlers in the
        # default thread-pool executor). time.sleep blocks the worker thread,
        # not the event loop — safe, no conversion to asyncio.sleep needed.
        time.sleep(min(3, remaining))


def _pickup_list(
    crew: dict,
    crew_id: str,
    podman: PodmanClient,
    container: str,
    timeout_secs: int,
) -> dict:
    """List-all pickup with optional polling and mail state."""
    # Capture initial admiral mail count for early-return detection using a
    # single batched exec rather than a dedicated _mail_count call.
    if timeout_secs > 0:
        initial_counts = _read_all_mail_counts(podman, container)
        initial_admiral_mail = initial_counts.get("admiral", 0)
    else:
        initial_admiral_mail = 0
    deadline = time.monotonic() + timeout_secs

    while True:
        try:
            r = _crew_api_with_recovery(crew, crew_id, "GET", "/api/spawn")
        except CrewUnresponsiveError as e:
            return {"error": str(e), "crew_id": crew_id}
        agents = r.get("agents", [])

        # Check if any task is done
        any_done = any(a.get("done", False) for a in agents)

        # Single exec reads all mailboxes at once; split into persona summary
        # and admiral count for the response surface.
        mail_counts = _read_all_mail_counts(podman, container)
        mail_subjects = _read_all_mail_subjects(podman, container)
        mail_summary: dict[str, int] = {
            name: mail_counts[name]
            for name in PERSONA_NAMES
            if mail_counts.get(name, 0) > 0
        }
        admiral_mail = mail_counts.get("admiral", 0)
        captain_mail = mail_counts.get("captain", 0)

        task_list = [
            {
                "task_id": a.get("id"),
                "crew_id": crew_id,
                "task": a.get("task", "")[:80],
                "agent": a.get("agent", ""),
                "done": a.get("done", False),
                "elapsed_secs": int(a.get("elapsed", 0)),
                "last_tool": a.get("last_tool", ""),
                "outcome": a.get("outcome", ""),
                "error": a.get("error", ""),
            }
            for a in agents
        ]

        # Build subject summaries for all persona mailboxes + captain + admiral.
        subjects_summary: dict[str, list[str]] = {}
        for name in PERSONA_NAMES:
            subs = mail_subjects.get(name, [])
            if subs:
                subjects_summary[f"{name}_subjects"] = subs
        subjects_summary["captain_subjects"] = mail_subjects.get("captain", [])
        subjects_summary["admiral_subjects"] = mail_subjects.get("admiral", [])

        out: dict[str, Any] = {
            "crew_id": crew_id,
            "tasks": task_list,
            "mail_summary": mail_summary,
            "admiral_mail": admiral_mail,
            "captain_mail": captain_mail,
            **subjects_summary,
        }

        if any_done or timeout_secs == 0:
            return out

        # Check for admiral mail early-return
        if admiral_mail > initial_admiral_mail:
            out["reason"] = "admiral_mail"
            return out

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            out["reason"] = "timeout"
            return out

        # F-03: same as _pickup_single — time.sleep is safe in executor thread.
        time.sleep(min(3, remaining))


# ── MCP resources ────────────────────────────────────────────────────────────

# _AGENTS_DIR is imported from transport.lifecycle above.

@mcp.resource(
    "transport://agents",
    name="agents",
    title="Available Crew Agents",
    description="Describes the agents available for dispatch to a crew — name, role, and when to use each.",
    mime_type="text/plain",
)
def resource_agents() -> str:
    """Read agent JSON files from /agents and return a plain-text roster."""
    if not _AGENTS_DIR.exists():
        return "No agents directory found. Agents are read from the /agents bind-mount."
    agents = []
    for path in sorted(_AGENTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            name = data.get("name", path.stem)
            description = data.get("description", "No description.")
            agents.append(f"## {name}\n{description}")
        except Exception:
            agents.append(f"## {path.stem}\n(Could not read agent definition.)")
    if not agents:
        return "No agent JSON files found in /agents."
    return "\n\n".join(agents)





@mcp.resource(
    "transport://orders",
    name="orders",
    title="Standing-Order Templates",
    description="Lists the built-in standing-order templates available to captain(order).",
    mime_type="text/plain",
)
def resource_orders() -> str:
    """Return every standing-order template from academy/orders/ and its full body."""
    orders_dir = _resolve_orders_dir()
    if not orders_dir.is_dir():
        return "No standing-order templates are available."
    templates = sorted(p for p in orders_dir.glob("*.md") if not p.name.startswith("."))
    if not templates:
        return "No standing-order templates are available."
    sections = []
    for template_path in templates:
        name = template_path.stem
        description, body = _load_order_template(name)
        resolved_body = _substitute_placeholders(body)
        sections.append(f"## {name}\n{description}\n\n{resolved_body}")
    return "\n\n".join(sections)


@mcp.resource(
    "transport://version",
    name="version",
    title="Transport and Crew Image Versions",
    description="Returns the transport process version and, for each running crew, its crew image version.",
    mime_type="application/json",
)
def resource_version() -> str:
    """Return transport version and per-crew image versions from registry."""
    with _registry_lock:
        reg = _load_registry()
    crews_versions = {}
    for cid, info in reg["crews"].items():
        crews_versions[cid] = {
            "crew_image_version": info.get("crew_image_version", "unknown")
        }
    return json.dumps({
        "transport": TRANSPORT_VERSION,
        "crews": crews_versions,
    })


@mcp.resource(
    "transport://jobs",
    name="jobs",
    title="Scheduled Jobs",
    description="Lists all scheduled jobs across all running crews — job_id, name, schedule, agent, enabled, last_run, last_status.",
    mime_type="text/plain",
)
def resource_jobs() -> str:
    """Return a plain-text listing of all scheduled jobs across all crews.

    Includes delay-type (one-shot) jobs from the transport registry alongside
    recurring jobs from the gateway.
    """
    with _registry_lock:
        reg = _load_registry()

    if not reg["crews"]:
        return "No running crews found."

    sections = []
    for crew_id, info in reg["crews"].items():
        lines = [f"## {crew_id}"]
        gateway_jobs_shown = set()

        # TRN-29: Include registry jobs (delay-type and all tracked)
        schedules = info.get("schedules", [])
        for sched in schedules:
            sched_display = sched.get("cron_expr") or (
                f"every {sched['interval_secs']}s" if sched.get("interval_secs") else "one-shot"
            )
            job_type = "delay" if sched.get("one_shot") else "recurring"
            lines.append(
                f"- {sched.get('name', '?')} "
                f"[{sched.get('job_id', '?')}] "
                f"schedule={sched_display} "
                f"agent={sched.get('agent', '?')} "
                f"enabled={sched.get('enabled', True)} "
                f"type={job_type} "
                f"next_fire_at={sched.get('next_fire_at', 'unknown')}"
            )
            gateway_jobs_shown.add(sched.get("job_id"))

        # Also show gateway jobs not yet in registry (backward compat)
        if info.get("status") == "running":
            try:
                crew = info
                cron_listing = _crew_api(crew, "GET", "/api/crons")
                jobs = _captain_jobs(cron_listing)
                for job in jobs:
                    if job.get("id") in gateway_jobs_shown:
                        continue
                    lines.append(
                        f"- {job.get('name', '?')} "
                        f"[{job.get('id', '?')}] "
                        f"schedule={job.get('schedule', '?')} "
                        f"agent={job.get('agent', '?')} "
                        f"enabled={job.get('enabled', False)} "
                        f"last_run={job.get('last_run_ts', 'never')} "
                        f"last_status={job.get('last_status', 'none')}"
                    )
            except Exception as e:
                lines.append(f"(gateway query error: {e})")

        if len(lines) == 1:
            lines.append("No scheduled jobs.")
        sections.append("\n".join(lines))

    if not sections:
        return "No running crews found."
    return "\n\n".join(sections)


# _schedule_monitor, _idle_monitor, _cron_activity_since, _cron_has_enabled_job,
# _validate_academy, and _SCHEDULE_MONITOR_INTERVAL now live in transport.lifecycle
# and are imported above.

# ── Health endpoint ───────────────────────────────────────────────────────────

async def _handle_health(request: Request) -> Response:
    """Minimal health probe — returns 200 OK when the transport is alive."""
    return PlainTextResponse("ok")


health_routes = [
    Route("/health", _handle_health, methods=["GET"]),
]

# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting transport MCP server on %s:%d", HOST, PORT)
    logger.info("Idle timeout: %ds", GA_IDLE_TIMEOUT_SECS)
    _reconcile_registry()
    for _warning in _validate_academy():
        logger.warning("Academy validation: %s", _warning)
    threading.Thread(target=_idle_monitor, daemon=True, name="idle-monitor").start()
    threading.Thread(target=_schedule_monitor, daemon=True, name="schedule-monitor").start()

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
    app = BearerAuthMiddleware(mcp_app, api_key=GA_API_KEY, file_app=_file_starlette)
    # Transport-security wrapper: security headers, HSTS, and the staged
    # HTTP→HTTPS redirect (TRN-70). Outermost so headers land on every response
    # and the redirect precedes auth.
    app = SecurityHeadersMiddleware(
        app,
        enable_headers=GA_ENABLE_SECURITY_HEADERS,
        enforce_redirect=GA_ENFORCE_HTTPS_REDIRECT,
        csp_enforce=GA_CSP_ENFORCE,
    )
    if GA_API_KEY:
        logger.info("MCP API-key authentication: enabled")
    else:
        logger.info("MCP API-key authentication: disabled (GA_API_KEY unset)")
    logger.info(
        "Transport security: headers=%s https_redirect=%s csp=%s",
        "on" if GA_ENABLE_SECURITY_HEADERS else "off",
        "enforced" if GA_ENFORCE_HTTPS_REDIRECT else "staged-off",
        "enforce" if GA_CSP_ENFORCE else "report-only",
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
    asyncio.run(server.serve())
