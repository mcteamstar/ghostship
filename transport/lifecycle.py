"""Crew lifecycle management — startup, recovery, setup, and monitoring.

Contains all functions that touch crew container state: bringing crews up,
tearing them down, injecting auth/config/policy, monitoring idle crews, and
firing scheduled jobs.

Depends on: registry, podman, captain, config, security.
Must NOT be imported by registry, podman, captain, or files at module load
time (files resolves these functions lazily via _crew_helpers() to avoid a
cycle — lifecycle can call files freely).
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
import secrets
import select
import tarfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx2 as httpx

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config

try:
    import security as _security  # container: flat /app/
except ModuleNotFoundError:
    from transport import security as _security

try:
    from podman import (  # container: flat /app/
        PodmanClient,
        _get_podman,
        _http,
        _wait_for_memory,
        KIRO_WORKSPACE_ROOT,
    )
except ModuleNotFoundError:
    from transport.podman import (  # local dev
        PodmanClient,
        _get_podman,
        _http,
        _wait_for_memory,
        KIRO_WORKSPACE_ROOT,
    )

try:
    from registry import (  # container: flat /app/
        _NEVER_FIRE_AT,
        _registry_lock,
        _load_registry,
        _save_registry,
        _get_crew_schedules,
        _advance_next_fire_at,
        _get_crew,
        _touch_crew,
        _write_batch,
        _write_secret_file,
        registry,
    )
except ModuleNotFoundError:
    from transport.registry import (  # local dev
        _NEVER_FIRE_AT,
        _registry_lock,
        _load_registry,
        _save_registry,
        _get_crew_schedules,
        _advance_next_fire_at,
        _get_crew,
        _touch_crew,
        _write_batch,
        _write_secret_file,
        registry,
    )

try:
    from crew import Crew  # container: flat /app/
except ModuleNotFoundError:
    from transport.crew import Crew  # local dev

try:
    from captain import (  # container: flat /app/
        _resolve_orders_dir,
        _read_all_mail_counts,
        _read_all_mail_subjects,
    )
except ModuleNotFoundError:
    from transport.captain import (  # local dev
        _resolve_orders_dir,
        _read_all_mail_counts,
        _read_all_mail_subjects,
    )

try:
    from academy import (  # container: flat /app/
        AcademyLoader,
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
    # ImportError (not just ModuleNotFoundError): in local dev the repo-root
    # academy/ assets directory shadows the flat-path module as a namespace
    # package, so `from academy import <name>` raises ImportError, not
    # ModuleNotFoundError. The container image is flat (/app/academy.py) and
    # has no such directory, so the try branch wins there.
    from transport.academy import (  # local dev
        AcademyLoader,
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

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
cfg = Config.from_env()

# When set, kiro-cli in the crew authenticates via this API key (injected
# as a container env var by server.launch) and the SQLite auth-row injection
# (_inject_auth) is skipped. Unset (default) => device-code auth is injected.
# Read from the Podman secret, as server.py does: cfg.kiro_api_key is "" in
# production because the compose file never carries the key (TRN-226).
KIRO_API_KEY = _security.get_secret("ga-kiro-api-key", env_var="KIRO_API_KEY")

# The reusable kiro-cli auth blob lives under the transport data mount; the
# KIRO_* values drive the interactive `kiro-cli login` device flow in _initiate_login.
DATA_DIR = Path("/data")
GA_AUTH_FILE = "ga-kiro-auth"
KIRO_LICENSE = cfg.kiro_license
KIRO_IDENTITY_PROVIDER = cfg.kiro_identity_provider
KIRO_REGION = cfg.kiro_region

# ── Hardcoded container-side paths ────────────────────────────────────────────
# These match the layout baked into the crew image by the Containerfile.
KIRO_CLI_DB = "/home/kirocrew/.local/share/kiro-cli/data.sqlite3"
KIRO_AGENTS_DIR = "/home/kirocrew/.kiro/agents"
KIRO_SKILLS_DIR = "/home/kirocrew/.kiro/crew/skills"
KIRO_STEERING_DIR = "/home/kirocrew/.kiro/steering"
# KIRO_WORKSPACE_ROOT is imported from transport.podman
KIRO_CREW_DIR = "/home/kirocrew/.kiro/crew"
KIRO_MCP_JSON = "/home/kirocrew/.kiro/mcp.json"

# ── Crew infrastructure constants ─────────────────────────────────────────────
# These constants are re-exported here (as pass-through imports) so existing
# callers of lifecycle.* — server.py and the test suite — remain unaffected.
# SCRIPTS_DIR is invoked via
# `python3 <SCRIPTS_DIR>/<name>.py` inside crew containers.
try:
    from constants import (  # container: flat /app/
        CREW_CONTAINER_PREFIX,
        CREW_GATEWAY_PORT,
        CREW_HOME_VOLUME_PREFIX,
        CREW_VOLUME_PREFIX,
        GA_PORTSIDE_NETWORK,
        GA_STARBOARD_NETWORK,
        PERSONA_NAMES,
        SCRIPTS_DIR,
    )
except ModuleNotFoundError:
    from transport.constants import (  # local dev
        CREW_CONTAINER_PREFIX,
        CREW_GATEWAY_PORT,
        CREW_HOME_VOLUME_PREFIX,
        CREW_VOLUME_PREFIX,
        GA_PORTSIDE_NETWORK,
        GA_STARBOARD_NETWORK,
        PERSONA_NAMES,
        SCRIPTS_DIR,
    )

GA_LOGIN_CONTAINER_PREFIX = "ga-login-"
GA_CLAUDE_LOGIN_CONTAINER_PREFIX = "ga-claude-login-"
GA_CLAUDE_AUTH_FILE = "ga-claude-auth"
GA_CODEX_LOGIN_CONTAINER_PREFIX = "ga-codex-login-"
GA_CODEX_AUTH_FILE = "ga-codex-auth"

# ── Config-driven constants ───────────────────────────────────────────────────
KC_IMAGE = cfg.kc_image
# Login containers use the upstream base image directly (not the locally-built
# crew image) to avoid any risk from a tainted local build. This must match the
# FROM pin in crews/_base/admission/Containerfile.
GA_MAX_ACTIVE_CREWS = cfg.ga_max_active_crews
GA_IDLE_TIMEOUT_SECS = cfg.ga_idle_timeout_secs
# KiroCrew agent name written to config.local.json inside each crew.
# Hardcoded: this is the KiroCrew built-in agent name and is not operator-configurable.
_KC_AGENT_NAME = "kiro"
# Retained as GA_CREW_AGENT for existing call sites in _patch_crew_config.
GA_CREW_AGENT = _KC_AGENT_NAME
KC_MODEL_OVERRIDE = cfg.kc_model_override
KC_MODEL_DEFAULT = cfg.kc_model_default
GA_MIN_FREE_MEM_GB = cfg.ga_min_free_mem_gb
GA_SPAWN_MIN_MEMORY_GB = cfg.ga_spawn_min_memory_gb
GA_RESOURCE_PRESSURE_GB = cfg.ga_resource_pressure_gb
GA_RESOURCE_CRITICAL_GB = cfg.ga_resource_critical_gb
GA_SUBAGENT_TIMEOUT_SECS = cfg.ga_subagent_timeout_secs
# Hardcoded: subagent max turns and prewarm TTL are internal constants.
_SUBAGENT_MAX_TURNS = 200
GA_SUBAGENT_MAX_TURNS = _SUBAGENT_MAX_TURNS
_PREWARM_TTL_SECS = 300
GA_PREWARM_TTL_SECS = _PREWARM_TTL_SECS
# GA_PREWARM_ENABLED: prewarm always fires when triggered (gate removed).
# Retained as a module-level name so tests can patch it for isolation.
GA_PREWARM_ENABLED = True

# ACP backend selection — controls whether kiro, Claude Code, or Codex runs inside crew containers.
# "kiro" (default): kiro-cli auth injection path (existing behaviour).
# "claude": skip kiro auth, inject ANTHROPIC_API_KEY + CLAUDE_CODE_HEADLESS=1.
# "codex": skip kiro auth, inject OPENAI_API_KEY (or the ga-codex-auth archive).
# GA_CREW_AGENT is the consolidated backend var (replaces GA_CREW_ACP_BACKEND + GA_AGENT_BACKENDS).
# The runtime default backend is the first entry.
GA_CREW_ACP_BACKEND = cfg.ga_crew_agent.split(",")[0].strip().lower()
# Credentials resolve from Podman secrets exactly as in server.py, so the
# OAuth-injection guards below see the same values the crew env was built from.
ANTHROPIC_API_KEY = _security.get_secret(
    "ga-crew-anthropic-api-key", env_var="ANTHROPIC_API_KEY")
CLAUDE_CODE_OAUTH_TOKEN = _security.get_secret(
    "ga-claude-code-oauth-token", env_var="CLAUDE_CODE_OAUTH_TOKEN")
ANTHROPIC_BASE_URL = cfg.anthropic_base_url
OPENAI_API_KEY = _security.get_secret(
    "ga-crew-openai-api-key", env_var="OPENAI_API_KEY")
OPENAI_BASE_URL = cfg.openai_base_url

# The effective crew session idle timeout. Spec-ops crews are patched with a
# fixed ``session.timeout_secs = 300`` override (see _patch_crew_config); a
# warm marker must never claim a session is warm past the point the idle reaper
# would have reclaimed it, so the prewarm TTL is capped at this value.
GA_SESSION_TIMEOUT_SECS = 300

PERSONA_ALLOWLIST = frozenset(PERSONA_NAMES)

# /mcp catalogue dir for mcpServers resolution
MCP_CATALOGUE_DIR = Path("/mcp")


def _secret_identifier(value: str) -> str:
    """Return a non-reversible opaque label for a secret value.

    Returns ``"sha256:" + hashlib.sha256(value.encode()).hexdigest()[:16]``.
    Useful for log correlation without storing the plaintext secret.
    """
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()[:16]

# ── Lifecycle globals ─────────────────────────────────────────────────────────

# TRN-238 QA-2: sentinel returned by _ensure_crew_running when a concurrent
# nuke() removes the crew's registry entry between container_start and
# post-start setup. Callers compare identity (``is _NUKED_DURING_RESTART``) and
# treat it as an expected, non-error outcome (the crew is gone — nothing more to
# do) rather than proceeding against a crew dict for a crew that no longer
# exists. It is a distinct sentinel object, never a crew dict, so a normal
# successful restart (which returns a dict) can never be mistaken for it.
_NUKED_DURING_RESTART: object = object()

# Per-crew startup locks: prevent concurrent restarts racing each other.
# Maps crew_id → threading.Event that is set once the crew is running.
_startup_events: dict[str, threading.Event] = {}
_startup_events_lock = threading.Lock()

# Maps crew_id → (success, exc) recorded by the leader before it fires
# the startup Event. Waiters read this after event.wait() and re-raise the
# stored exception when success is False, instead of proceeding against a crew
# that never started. Guarded by _startup_events_lock (same lifecycle as the
# event it accompanies).
_crew_restart_outcomes: dict[str, tuple[bool, Exception | None]] = {}

# Generation counter — tracks restart cycle identity per crew.
# Incremented when a new leader is elected; waiters capture the generation before
# event.wait() and verify it is unchanged after waking, so a third concurrent caller
# starting a new cycle cannot corrupt a prior waiter's outcome read.
# Guarded by _startup_events_lock (same lifecycle as _startup_events).
_startup_generation: dict[str, int] = {}

# Per-crew recovery locks: prevent concurrent recovery races within
# _crew_api_with_recovery.
_recovery_locks: dict[str, threading.Lock] = {}
_recovery_locks_lock = threading.Lock()

# Per-crew ACP warm markers. Maps crew_id → warmed_at (monotonic seconds)
# recording the last successful prewarm. Guarded by its own lock, mirroring the
# _startup_events_lock / _task_timestamps_lock patterns. The marker is advisory:
# a missed or stale marker at worst causes one extra idempotent warm-up request,
# never real work.
_warm_markers: dict[str, float] = {}
_warm_markers_lock = threading.Lock()

# Bounded in-process memory: _task_timestamps completed entries are evicted once
# their completed_at is older than _TASK_TIMESTAMP_TTL_SECS (env-overridable);
# _warm_markers entries are evicted once older than _WARM_MARKER_TTL_SECS.
# The warm-marker TTL is floored at one hour via `_warm_marker_ttl_secs()`;
# `_TASK_TIMESTAMP_TTL_SECS` has no floor.
_TASK_TIMESTAMP_TTL_SECS = float(os.environ.get("GA_TASK_TIMESTAMP_TTL_SECS", "3600"))


def _warm_marker_ttl_secs() -> float:
    """Warm-marker TTL: twice the prewarm TTL, with a one-hour floor."""
    return float(max(GA_PREWARM_TTL_SECS * 2 if GA_PREWARM_TTL_SECS > 0 else 3600, 3600))


_SCHEDULE_MONITOR_INTERVAL = 30  # seconds


# ── Composition registry ──────────────────────────────────────────────────────
# COMPOSITION_REGISTRY, _load_composition_registry, _resolve_composition,
# _resolve_manifest_path and _resolve_image live in transport/academy.py
# and are imported at the top of this module.


# ── Crew URL / cookie / API helpers ──────────────────────────────────────────

def _to_crew(crew_id: str, crew) -> Crew:
    """Return *crew* as a ``Crew`` instance.

    If *crew* is already a ``Crew`` the object is returned unchanged.
    If *crew* is a plain dict (legacy caller path — callers in server.py and
    test suites still pass raw dicts until tasks 2.3/2.4 migrate them) it is
    converted via ``Crew.from_dict``.  This lets lifecycle.py use attribute
    access internally while remaining compatible with dict-passing callers.
    """
    if isinstance(crew, Crew):
        return crew
    return Crew.from_dict(crew_id, crew)


def _crew_url(crew) -> str:
    if isinstance(crew, Crew):
        return crew.gateway_url()
    return f"http://{crew['container']}:{CREW_GATEWAY_PORT}"


def _crew_cookie(crew) -> str:
    if isinstance(crew, Crew):
        return crew.cookie_header()
    return f"mc_token_{CREW_GATEWAY_PORT}={crew['cookie']}"


_DASHBOARD_COOKIE_PATH = "/home/kirocrew/.kiro/crew/.dashboard_cookie"


def _write_dashboard_cookie(podman: "PodmanClient", container: str, cookie: str) -> bool:
    """Write the dashboard cookie value to .dashboard_cookie inside the container.

    Writes ``mc_token_<port>=<value>`` raw value (not the full header) to
    ``/home/kirocrew/.kiro/crew/.dashboard_cookie`` with mode 0600 so crew
    members can read it via ``$(cat .dashboard_cookie)`` and construct
    ``Cookie: mc_token_5476=$COOKIE`` for gateway REST calls.

    Non-fatal — returns True on success, False on failure (logged as WARNING).
    Parallel to ``.local_secret`` which the gateway writes itself at startup.
    """
    try:
        # SEC-2: build a minimal in-memory tar holding the cookie value as a
        # single member with mode 0600, and untar it into the target directory
        # via container_archive_put. The cookie value never passes through a
        # shell, so no interpolation/injection surface exists.
        dest_dir = os.path.dirname(_DASHBOARD_COOKIE_PATH)
        member_name = os.path.basename(_DASHBOARD_COOKIE_PATH)
        payload = cookie.encode("utf-8")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=member_name)
            info.size = len(payload)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(payload))
        buf.seek(0)
        podman.container_archive_put(container, dest_dir, buf.read())
        logger.debug("Dashboard cookie written to %s in %s", _DASHBOARD_COOKIE_PATH, container)
        return True
    except Exception as exc:
        logger.warning(
            "Failed to write dashboard cookie to %s in %s: %s",
            _DASHBOARD_COOKIE_PATH, container, exc,
        )
        return False


# TRN-220: headers the transport host must never send to a crew gateway.
# These select the gateway's INTERNAL auth path, which KiroCrew 0.9.0
# (PR #2424 / issue #302) now peer-cred-gates over the unix socket: a caller
# whose OS UID does not match the gateway's `kirocrew` process is rejected even
# with a valid shared secret. The transport host runs under a different UID, so
# any internal-secret call from here would be rejected. The transport always
# uses the external dashboard-cookie path instead.
_FORBIDDEN_INTERNAL_HEADERS = ("X-Internal-Secret", "X-Session-Key")


def _crew_api(crew: dict, method: str, path: str, **kw: Any) -> Any:
    url = _crew_url(crew)
    # TRN-220: authenticate on the external cookie path (Cookie + Origin) only.
    # Never attach the internal-secret headers — see _FORBIDDEN_INTERNAL_HEADERS.
    headers = {"Cookie": _crew_cookie(crew), "Origin": url}
    caller_headers = kw.pop("headers", None)
    if caller_headers:
        for h in _FORBIDDEN_INTERNAL_HEADERS:
            if h in caller_headers:
                raise ValueError(
                    f"TRN-220: {h} must not be sent on the transport cookie path"
                )
        headers.update(caller_headers)
    r = _http.request(
        method, f"{url}{path}",
        headers=headers,
        **kw,
    )
    r.raise_for_status()
    return r.json()


# ── Self-healing: liveness probe, cookie refresh, retry wrapper ───────────────

def _probe_gateway(crew_url: str) -> bool:
    """Perform a lightweight liveness probe against the gateway root.

    GET {crew_url}/ with a 5-second timeout. Returns True on any 2xx
    response, False on non-2xx, connection refused, timeout, or any error.
    """
    try:
        r = _http.get(f"{crew_url}/", timeout=5.0)
        return 200 <= r.status_code < 300
    except Exception:
        return False


def _refresh_cookie(crew, crew_id: str) -> bool:
    """Re-mint the session cookie and update the registry.

    Returns True on success, False on failure. On success the registry is
    updated with the new cookie value so subsequent calls use it.

    Also mints a new internal cookie (loopback-bound, for crew members) and
    updates ``.dashboard_cookie`` inside the container plus the registry's
    ``internal_cookie`` field.  Internal cookie failure is non-fatal — the
    external cookie refresh still returns True.
    """
    try:
        podman = _get_podman()
    except Exception:
        return False

    c = _to_crew(crew_id, crew)
    new_cookie = _mint_cookie(podman, c.container, c.gateway_url())
    if not new_cookie:
        return False

    # Also mint an internally-bound cookie for crew member spawn auth.
    new_internal = _mint_internal_cookie(podman, c.container)

    with registry:
        if crew_id in registry._reg["crews"]:
            registry._reg["crews"][crew_id]["cookie"] = new_cookie
            if new_internal:
                registry._reg["crews"][crew_id]["internal_cookie"] = new_internal

    # Update the in-memory crew so the caller can use it immediately.
    # Both the Crew view (c) and the original dict (if crew is a dict) are
    # updated for backward compatibility with callers that still pass plain dicts.
    c.cookie = new_cookie
    if isinstance(crew, dict):
        crew["cookie"] = new_cookie
    if new_internal:
        c.internal_cookie = new_internal
        if isinstance(crew, dict):
            crew["internal_cookie"] = new_internal
        _write_dashboard_cookie(podman, c.container, new_internal)
    else:
        logger.warning("Internal cookie refresh failed for crew %s", crew_id)

    logger.info("Cookie refreshed for crew %s", crew_id)
    return True


def _get_recovery_lock(crew_id: str) -> threading.Lock:
    """Return or create a per-crew lock for serialising recovery attempts."""
    with _recovery_locks_lock:
        return _recovery_locks.setdefault(crew_id, threading.Lock())


class CrewUnresponsiveError(RuntimeError):
    """Raised when all recovery attempts for a crew have been exhausted."""
    pass


def _phase0_transient_503(
    crew: dict,
    method: str,
    path: str,
    **kw: Any,
) -> Any:
    """Phase 0: task still spawning — short bounded retry on 503.

    On 503 from a per-task /api/spawn/* route, KiroCrew's own task record
    already reports elapsed > 0 before the agent process has finished
    forking/registering enough to serve the route.  Short bounded retry —
    this is transient and self-resolving within a couple of seconds.

    Re-raises the last 503 error if all retries are exhausted.
    Raises any non-503 HTTPStatusError immediately without retrying.

    Note (D6): a 503 here means the task process is still starting and has not
    served the route yet — the request was not acted upon, so retrying is safe
    for any method (including POST). The idempotency guard D6 adds is for a
    connection reset (_phase2_dead_gateway), not this transient-503 path.
    """
    last_exc: Exception | None = None
    for _attempt in range(4):
        time.sleep(1.0)
        try:
            return _crew_api(crew, method, path, **kw)
        except httpx.HTTPStatusError as retry_exc:
            if retry_exc.response.status_code != 503:
                raise
            last_exc = retry_exc
    raise last_exc


def _phase1_stale_cookie(
    crew: dict,
    crew_id: str,
    method: str,
    path: str,
    **kw: Any,
) -> Any:
    """Phase 1: stale cookie — attempt cookie refresh then retry once.

    On 400/401/403 from a running container, refreshes the session cookie
    and retries the request.  If the refresh fails or the retry fails,
    escalates to Phase 2 (full gateway restart).

    Returns the API result on success.
    Raises CrewUnresponsiveError if Phase 2 restart also fails.

    Note (D6): a stale-cookie failure is a 400/401/403 — the gateway REJECTED
    the request at auth and did not act on it, so retrying after a cookie
    refresh cannot duplicate a side effect even for a POST. The idempotency
    guard that D6 adds lives in _phase2_dead_gateway (a connection reset, where
    the request MAY have been accepted before the socket dropped), not here.
    """
    logger.info(
        "Crew %s stale-cookie phase — attempting cookie refresh",
        crew_id,
    )
    if _refresh_cookie(crew, crew_id):
        try:
            return _crew_api(crew, method, path, **kw)
        except Exception as _retry_exc:
            logger.warning(
                "Crew %s phase-1 retry failed after cookie refresh: %s — "
                "escalating to full restart",
                crew_id, _retry_exc,
            )

    # Phase 1 failed — escalate to full restart
    logger.info(
        "Crew %s cookie refresh failed or retry failed — "
        "escalating to full restart",
        crew_id,
    )
    try:
        crew = _ensure_crew_running(crew, crew_id)
    except RuntimeError:
        raise CrewUnresponsiveError(
            f"crew {crew_id} is unresponsive — transport attempted "
            f"cookie refresh and container restart but the gateway "
            f"did not recover. Suggestion: check crew status with "
            f"crews() or try again in a moment."
        )
    # TRN-238 QA-2: crew was nuked during the restart — the registry entry is
    # gone, so there is nothing to call the API against. Surface a clear error.
    if crew is _NUKED_DURING_RESTART:
        raise CrewUnresponsiveError(
            f"crew {crew_id} was removed (nuked) during restart — no longer exists."
        )
    try:
        return _crew_api(crew, method, path, **kw)
    except Exception:
        raise CrewUnresponsiveError(
            f"crew {crew_id} is unresponsive — transport attempted "
            f"cookie refresh and container restart but the gateway "
            f"did not recover. Suggestion: check crew status with "
            f"crews() or try again in a moment."
        )


def _phase2_dead_gateway(
    crew: dict,
    crew_id: str,
    method: str,
    path: str,
    **kw: Any,
) -> Any:
    """Phase 2: connection error — probe then restart only if dead.

    On a connection error from a running container, first probes liveness.
    If the gateway is alive (transient error), retries directly.
    If the gateway is dead, restarts via _ensure_crew_running and retries.

    Returns the API result on success.
    Raises CrewUnresponsiveError if the gateway cannot be recovered.

    Non-idempotent methods (POST, PATCH, DELETE) are NOT retried after a
    gateway restart — the request may have been accepted before the connection
    was cut, and a blind retry would duplicate the side-effect.  The caller
    receives a CrewUnresponsiveError and can choose to retry explicitly.
    """
    _IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "OPTIONS"})
    logger.info(
        "Crew %s connection-error phase — probing gateway liveness",
        crew_id,
    )
    crew_url = _crew_url(crew)
    if _probe_gateway(crew_url):
        # Gateway is actually alive — transient error, retry directly
        try:
            return _crew_api(crew, method, path, **kw)
        except Exception:
            raise CrewUnresponsiveError(
                f"crew {crew_id} is unresponsive — gateway responded to "
                f"liveness probe but API call failed twice. Suggestion: "
                f"check crew status with crews() or try again in a moment."
            )
    logger.info(
        "Crew %s gateway confirmed dead — restarting",
        crew_id,
    )
    try:
        crew = _ensure_crew_running(crew, crew_id)
    except RuntimeError:
        raise CrewUnresponsiveError(
            f"crew {crew_id} is unresponsive — transport attempted "
            f"container restart but the gateway did not recover. "
            f"Suggestion: check crew status with crews() or try "
            f"again in a moment."
        )
    # TRN-238 QA-2: crew was nuked during the restart — nothing to call against.
    if crew is _NUKED_DURING_RESTART:
        raise CrewUnresponsiveError(
            f"crew {crew_id} was removed (nuked) during restart — no longer exists."
        )
    if method.upper() not in _IDEMPOTENT_METHODS:
        raise CrewUnresponsiveError(
            f"crew {crew_id} gateway restarted after a connection reset on a "
            f"{method} request — not retrying a non-idempotent call to avoid "
            f"duplicating side-effects. Re-issue the request to proceed."
        )
    try:
        return _crew_api(crew, method, path, **kw)
    except Exception:
        raise CrewUnresponsiveError(
            f"crew {crew_id} is unresponsive — transport attempted "
            f"container restart but the gateway did not recover. "
            f"Suggestion: check crew status with crews() or try "
            f"again in a moment."
        )


def _crew_api_with_recovery(
    crew: dict,
    crew_id: str,
    method: str,
    path: str,
    **kw: Any,
) -> Any:
    """Wrap _crew_api with three-phase recovery logic.

    Phase 0 (task still spawning): On 503 from a per-task /api/spawn/*
    route, KiroCrew's own task record already reports elapsed > 0 before
    the agent process has finished forking/registering enough to serve
    the route. Short bounded retry — this is transient and self-resolving
    within a couple of seconds, not a dead gateway.

    Phase 1 (stale cookie): On 400/401/403 from a running container,
    attempt cookie refresh then retry once.

    Phase 2 (dead gateway): On connection error from a running container,
    confirm via liveness probe then restart via _ensure_crew_running and
    retry once.

    If phase 1 cookie refresh fails, escalates to phase 2.
    At most one retry per failure class — no infinite loops.

    NON-REENTRANT CONTRACT (D1 — do not reintroduce the deadlock):
    This function holds ``_get_recovery_lock(crew_id)`` for the entire call,
    INCLUDING any phase-1/phase-2 sub-call into ``_ensure_crew_running``. The
    per-crew recovery lock is a plain ``threading.Lock`` (non-reentrant), so a
    code path reached *while this lock is held* must NOT call
    ``_crew_api_with_recovery`` again for the same crew — doing so blocks
    forever trying to re-acquire the lock. Concretely: ``_ensure_crew_running``
    (reached via phase 2) calls ``_enroll_crew_members``, which therefore uses
    ``_crew_api`` DIRECTLY (best-effort, its own try/except) and never
    ``_crew_api_with_recovery``. Any new caller of ``_enroll_crew_members`` — or
    any new sub-call added under this lock — must preserve that: route
    gateway calls through ``_crew_api``, not through recovery, so the lock is
    never re-entered. See design.md D1.
    """
    lock = _get_recovery_lock(crew_id)
    with lock:
        # First attempt
        try:
            return _crew_api(crew, method, path, **kw)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 503:
                # ── Phase 0: transient 503 while task process is still starting ──
                return _phase0_transient_503(crew, method, path, **kw)
            if status not in (400, 401, 403):
                raise
            # ── TRN-230: 400 on /continue means session is gone, not a stale cookie.
            # Phase-1 cookie refresh cannot recover a finished session — re-raise so
            # the caller (_steer_captain_checkin) can handle it as "session gone".
            # TRN-238 QA-3: match only a path whose final segment is "continue"
            # (path.endswith("/continue")), not any path merely containing the
            # substring "continue". A route like /api/continue-session/abc or
            # /api/foo?note=continue must NOT trigger this session-gone bypass.
            if status == 400 and path.endswith("/continue"):
                raise
            # ── Phase 1: stale cookie ─────────────────────────────────────────
            return _phase1_stale_cookie(crew, crew_id, method, path, **kw)

        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError, OSError):
            # ── Phase 2: connection error / dead gateway ──────────────────────
            return _phase2_dead_gateway(crew, crew_id, method, path, **kw)


def _require_crew(crew_id: str | None) -> dict:
    """Return the crew dict or raise a clear error."""
    if not crew_id:
        with registry:
            names = list(registry._reg["crews"].keys())
        if names:
            raise ValueError(
                f"crew_id required. Live crews: {names}. "
                "Pass crew_id=<name> to target one."
            )
        raise ValueError(
            "crew_id required and no crews exist. "
            "Call launch first to create a crew."
        )
    return _get_crew(crew_id)


def _validate_agent(agent: str) -> None:
    if agent not in PERSONA_ALLOWLIST:
        accepted = ", ".join(PERSONA_NAMES)
        raise ValueError(
            f"Invalid agent {agent!r}; expected one of: {accepted}"
        )


def _ensure_crew_running(
    crew,
    crew_id: str,
    *,
    touch: bool = True,
) -> dict:
    """Ensure a crew container is running, starting it if stopped.

    Delegates to ``_launcher.ensure_running`` (transport/launcher.py).
    The concurrency state (startup events, leader/waiter pattern, generation
    counter, outcome recording) lives in the launcher singleton.

    Returns an updated crew dict (cookie may be refreshed), or the
    ``_NUKED_DURING_RESTART`` sentinel if the crew was concurrently nuked.
    """
    try:
        from launcher import _launcher  # container: flat /app/
    except ModuleNotFoundError:
        from transport.launcher import _launcher  # local dev
    return _launcher.ensure_running(crew, crew_id, touch=touch)


# ── ACP prewarm ─────────────────────────────────────────────────────

# D1: the gateway surface used to fork the kiro-cli-chat session and complete
# the ACP handshake WITHOUT enqueuing a real agent task. Pinned to a single
# constant so a future KiroCrew change is a one-function fix (design D1 / risk
# note). /api/ready is the gateway's readiness/session surface: it is
# auth-bypassed and returns 200 only once the session manager is wired, which
# is the request the transport drives to establish the session/ACP connection.
_PREWARM_WARMUP_PATH = "/api/ready"


def _effective_prewarm_ttl() -> int:
    """Return the warm-lifetime hint, capped at the session idle timeout.

    D3/D4: GA_PREWARM_TTL_SECS is an operator hint but a warm marker must never
    claim a session is warm past the point the idle reaper (session.timeout_secs)
    would have reclaimed it, so the effective TTL is capped at
    GA_SESSION_TIMEOUT_SECS.
    """
    ttl = GA_PREWARM_TTL_SECS if GA_PREWARM_TTL_SECS > 0 else 0
    return min(ttl, GA_SESSION_TIMEOUT_SECS)


def _issue_warmup(crew: dict, crew_id: str) -> None:
    """Drive the gateway warm-up request that forks the session (D1).

    Routed through _crew_api_with_recovery so the Phase-0 503 "still spawning"
    tolerance applies exactly as it does for a real dispatch. Raises on failure;
    the caller translates that into an ``error:`` status.
    """
    _crew_api_with_recovery(crew, crew_id, "GET", _PREWARM_WARMUP_PATH)


def _prewarm_crew(crew, crew_id: str) -> dict:
    """Pre-establish a crew's ACP session ahead of an expected dispatch.

    Returns ``{"crew_id": crew_id, "status": <status>}`` where status is one of:

    - ``disabled``      — GA_PREWARM_ENABLED is false; no start / no fork.
    - ``already_warm``  — running container with a fresh warm marker; no second
                          warm-up request and no restart.
    - ``blocked:<gate>``— the memory or active-crew gate refused the start; no
                          container start.
    - ``warmed``        — the session was (re)warmed successfully.
    - ``error:<msg>``   — the warm-up request failed; dispatch behaviour is
                          unchanged.

    Non-destructive: it dispatches no real task, sends no mail, and writes no
    spec/workspace state. The only bookkeeping is the in-memory warm marker and
    whatever _ensure_crew_running already performs for a normal auto-start.
    """
    ttl = _effective_prewarm_ttl()

    c = _to_crew(crew_id, crew)

    # 2.3: idempotency — a fresh warm marker on a running container is a no-op.
    try:
        podman = _get_podman()
        container_running = podman.container_is_running(c.container)
    except Exception:
        container_running = False

    if container_running and ttl > 0:
        with _warm_markers_lock:
            warmed_at = _warm_markers.get(crew_id)
        if warmed_at is not None and (time.monotonic() - warmed_at) < ttl:
            return {"crew_id": crew_id, "status": "already_warm"}

    # 2.4: enforce the memory + active-crew gates, per-crew start serialisation,
    # and gateway readiness via _ensure_crew_running. A gate RuntimeError is
    # translated into blocked:<gate>.
    try:
        crew = _ensure_crew_running(crew, crew_id)
    except RuntimeError as e:
        msg = str(e)
        if "Active crew limit" in msg:
            gate = "active-crew-limit"
        elif "memory" in msg.lower():
            gate = "insufficient-memory"
        else:
            gate = "start-failed"
        return {"crew_id": crew_id, "status": f"blocked:{gate}"}

    # TRN-238 QA-2: crew was nuked during restart — report a clean status and
    # do not attempt to warm a crew that no longer exists.
    if crew is _NUKED_DURING_RESTART:
        return {"crew_id": crew_id, "status": "nuked_during_restart"}

    # 2.5 / 2.6: issue the session warm-up (D1). On success record the marker
    # and report warmed; on failure report error and leave dispatch unchanged.
    try:
        _issue_warmup(crew, crew_id)
    except Exception as e:
        return {"crew_id": crew_id, "status": f"error:{e}"}

    with _warm_markers_lock:
        _warm_markers[crew_id] = time.monotonic()
        # Evict warm markers older than _WARM_MARKER_TTL_SECS (twice the prewarm
        # TTL, 1h min) so _warm_markers does not accumulate entries for crews long
        # gone.
        _wm_ttl = _warm_marker_ttl_secs()
        _wm_now = time.monotonic()
        _expired_wm = [k for k, v in _warm_markers.items() if (_wm_now - v) > _wm_ttl]
        for k in _expired_wm:
            _warm_markers.pop(k, None)
    logger.info("Crew %s prewarmed (ACP session warm)", crew_id)
    return {"crew_id": crew_id, "status": "warmed"}


# ── Launch helpers ────────────────────────────────────────────────────────────


def _inject_auth(podman: PodmanClient, container: str, auth_b64: str) -> bool:
    """Inject kiro-cli auth rows into a running crew container's DB.

    The DB schema and migrations are pre-seeded in the crew image, so kiro-cli
    finds them already applied — direct INSERT, no migration wait needed.
    Returns True if successful.
    """
    podman.container_exec_checked(
        container,
        ["python3", f"{SCRIPTS_DIR}/inject_auth.py", KIRO_CLI_DB, auth_b64],
    )
    logger.info("Auth injected for %s", container)
    return True


def _wait_gateway(url: str, timeout: int = 30) -> bool:
    """Poll /api/ready until KiroCrew reports startup_complete (200), or timeout.

    /api/ready is auth-bypassed and returns 503 until the session manager is
    wired and post-bind startup work finishes — unlike GET / which returns the
    SPA HTML the moment the HTTP server binds, before KiroCrew is ready to
    accept dispatches.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if _http.get(f"{url}/api/ready", timeout=2.0).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


# _load_crew_manifest, _manifest_selects and _substitute_env_vars live in
# transport/academy.py and are imported at the top of this module.
# _copy_agents/_copy_skills/_copy_steering below call them via the imported names.


def _copy_agents(podman: PodmanClient, container: str, composition_entry: dict | None = None) -> list[str]:
    """Wrapper delegating to AcademyLoader.copy('agents').

    Kept as a one-line wrapper so existing call sites and test patches on
    ``lifecycle._copy_agents`` continue to resolve (TRN-240 task 4.1).
    """
    return AcademyLoader(podman, container, composition_entry).copy("agents")


def _copy_skills(podman: PodmanClient, container: str, composition_entry: dict | None = None) -> list[str]:
    """Wrapper delegating to AcademyLoader.copy('skills')."""
    return AcademyLoader(podman, container, composition_entry).copy("skills")


def _copy_steering(podman: PodmanClient, container: str, composition_entry: dict | None = None) -> list[str]:
    """Wrapper delegating to AcademyLoader.copy('steering')."""
    return AcademyLoader(podman, container, composition_entry).copy("steering")


def _seed_openspec_store(podman: PodmanClient, container: str) -> None:
    """Init a shared OpenSpec store at the workspace root.

    Every dispatched task runs in its own subagent_<task_id>/ subdirectory
    (isolated from every other task, including earlier ones in the same
    crew), but OpenSpec resolves commands to the "nearest local openspec/
    root" by walking up the directory tree — so seeding one store here,
    one level above every subagent_* dir, is what lets independently
    dispatched agents (e.g. Spectre planning a change, Ghost implementing
    it later) share the same change/spec state without any explicit
    path-passing between them.

    Lives at the workspace root as a sibling to any delivered repo/,
    never inside it — this never touches a user's own repo.
    --force makes this idempotent: safe to call on every launch.
    """
    try:
        podman.container_exec(container, [
            "openspec", "init", "--tools", "none", "--no-animation", "--force",
            KIRO_WORKSPACE_ROOT,
        ])
        logger.info("Seeded shared openspec store for %s", container)
    except Exception as e:
        logger.warning("openspec init failed for %s: %s", container, e)


def _patch_models(podman: PodmanClient, container: str) -> None:
    """Patch all *.json agent files to KC_MODEL_OVERRIDE if set."""
    model = KC_MODEL_OVERRIDE
    if not model:
        return
    try:
        result = podman.container_exec(
            container,
            ["python3", f"{SCRIPTS_DIR}/patch_models.py", KIRO_AGENTS_DIR, model],
        )
        logger.info("Model override patch %s: %s", container, result.strip())
    except Exception as e:
        logger.warning("Model override patch failed for %s: %s", container, e)


def _mint_cookie(podman: PodmanClient, container: str, crew_url: str) -> str | None:
    """Mint a gateway token and exchange it for a session cookie."""
    try:
        raw = podman.container_exec(
            container,
            ["kirocrew", "token", "--ttl", "24h"],
        )
        m = re.search(r'token=([A-Za-z0-9._-]+)', raw)
        if not m:
            logger.error("Could not parse a token from `kirocrew token` output (%d bytes; output not logged)", len(raw))
            return None
        token = m.group(1)

        resp = _http.get(f"{crew_url}/", params={"token": token},
                         follow_redirects=False, timeout=15.0)
        cookie_val = ""
        for h_name, h_val in resp.headers.multi_items():
            if h_name.lower() == "set-cookie":
                if f"mc_token_{CREW_GATEWAY_PORT}=" in h_val and f'mc_token_{CREW_GATEWAY_PORT}=""' not in h_val:
                    cookie_val = h_val.split(f"mc_token_{CREW_GATEWAY_PORT}=")[1].split(";")[0]
        if not cookie_val:
            logger.error("Cookie exchange failed (status %d)", resp.status_code)
        return cookie_val or None
    except Exception as e:
        logger.error("Cookie mint failed: %s", e)
        return None


def _mint_internal_cookie(podman: PodmanClient, container: str) -> str | None:
    """Mint a dashboard cookie bound to 127.0.0.1 by doing the exchange from inside.

    Runs both the token mint and the token exchange inside the container so the
    resulting session cookie is bound to loopback (127.0.0.1) rather than the
    transport host's IP.  Crew members can then use this cookie for gateway REST
    calls (spawn, steer, continue) from inside the container without hitting the
    IP-mismatch check.

    Returns the raw cookie value (without the ``mc_token_<port>=`` prefix) or
    None on any failure.  Non-fatal — callers log a WARNING and continue.
    """
    try:
        # Step 1: mint a one-time URL token (runs inside container, unchanged)
        raw = podman.container_exec(
            container,
            ["kirocrew", "token", "--ttl", "24h"],
        )
        m = re.search(r'token=([A-Za-z0-9._-]+)', raw)
        if not m:
            logger.warning(
                "Internal cookie mint: could not parse token from `kirocrew token` output "
                "(%d bytes)", len(raw)
            )
            return None
        token = m.group(1)

        # Step 2: exchange from INSIDE the container so cookie binds to 127.0.0.1
        curl_out = podman.container_exec(
            container,
            ["curl", "-si", f"http://localhost:{CREW_GATEWAY_PORT}/?token={token}"],
        )
        cookie_val = ""
        prefix = f"mc_token_{CREW_GATEWAY_PORT}="
        empty_marker = f'mc_token_{CREW_GATEWAY_PORT}=""'
        for line in curl_out.splitlines():
            low = line.lower()
            if low.startswith("set-cookie:") and prefix in line and empty_marker not in line:
                cookie_val = line.split(prefix)[1].split(";")[0].strip()
                break
        if not cookie_val:
            logger.warning("Internal cookie mint: Set-Cookie not found in curl output")
            return None
        logger.debug("Internal cookie minted for %s", container)
        return cookie_val
    except Exception as exc:
        logger.warning("Internal cookie mint failed for %s: %s", container, exc)
        return None


# kiro-cli writes this row the instant it registers an OIDC device-flow
# client — before the user has even seen the approval screen, let alone
# granted it. It is present throughout the whole flow (pending or complete),
# so its mere existence must never be treated as evidence the login finished;
# only a *different*, non-empty auth_kv row (the actual granted credential,
# written after the user approves) proves that.
_LOGIN_PRECURSOR_KEYS = {"kirocli:odic:device-registration"}


def _read_auth_from_crew(podman: PodmanClient, container: str) -> str | None:
    """Read auth_kv rows from a crew container's kiro-cli DB, return as b64 JSON.

    Uses an inline python one-liner so this works in both crew containers
    (base-admission image, which has /scripts/) and ephemeral login containers
    (bare kirocrew image, which does not).

    Returns None while only the device-flow registration precursor row is
    present — that row exists from the moment the flow *starts*, so it is not
    evidence the user has actually completed the grant.
    """
    extract = (
        "import sqlite3, json, base64; "
        f"conn = sqlite3.connect('{KIRO_CLI_DB}'); "
        "rows = conn.execute('SELECT key, value FROM auth_kv').fetchall(); "
        "conn.close(); "
        "print(base64.b64encode(json.dumps(rows).encode()).decode())"
    )
    try:
        b64 = podman.container_exec(container, ["python3", "-c", extract]).strip()
        if b64:
            rows = json.loads(base64.b64decode(b64).decode())
            if rows and any(
                r[1] for r in rows if len(r) > 1 and r[0] not in _LOGIN_PRECURSOR_KEYS
            ):
                return b64
    except Exception as e:
        logger.warning("Auth read failed: %s", e)
    return None


def _cleanup_crew(podman: PodmanClient, container: str, volume: str, home_volume: str) -> None:
    # Each step is best-effort — a failed launch may mean the container or
    # volumes were never created, so not-found errors are silently ignored.
    try:
        podman.container_stop(container)
    except Exception:
        pass
    try:
        podman.container_remove(container)
    except Exception:
        pass
    try:
        podman.volume_remove(volume)
    except Exception:
        pass
    try:
        podman.volume_remove(home_volume)
    except Exception:
        pass
    # Remove the Admiral public-key Podman secret. Podman secrets live in a global
    # namespace and must be explicitly removed or they leak across crew lifecycles.
    # Derive the crew_id from the container name (gs-<crew_id>) so every
    # launch-failure path and the nuke path clean it up. Best-effort — a launch
    # that failed before secret_create just no-ops.
    try:
        if container.startswith(CREW_CONTAINER_PREFIX):
            crew_id = container[len(CREW_CONTAINER_PREFIX):]
            podman.secret_remove(f"admiral-pubkey-{crew_id}")
    except Exception:
        pass


def _reseed_crew_schedules(crew: dict, crew_id: str, crew_info: dict) -> None:
    """Re-register tracked jobs from the transport registry into the gateway.

    Runs in two passes:

    1. **Reconcile pass** — reads the gateway's current cron state and updates
       the registry to match.  The gateway is the source of truth; the registry
       is a reseed bootstrap cache only.  Any job paused, resumed, or deleted
       inside the container is reflected back into the registry here so that
       subsequent idle-stop checks see the correct enabled state.

    2. **Reseed pass** — for each enabled registry entry that has no matching
       job in the gateway (the true bootstrap case: fresh container, empty
       gateway), re-register it.
    """
    try:
        from captain import _captain_jobs  # container: flat /app/
    except ModuleNotFoundError:
        from transport.captain import _captain_jobs  # local dev  # type: ignore[no-redef]

    with registry:
        schedules = registry.get_schedules(crew_id)

    if not schedules:
        return

    # Get existing gateway jobs
    try:
        cron_listing = _crew_api(crew, "GET", "/api/crons")
        gateway_jobs = _captain_jobs(cron_listing)
        gateway_ids = {j.get("id") for j in gateway_jobs}
    except Exception as e:
        logger.warning("Could not list gateway crons for re-seed on crew %s: %s", crew_id, e)
        return

    # ── Reconcile pass: gateway → registry ────────────────────────────────────
    # Build a map of job_id → gateway_job for O(1) lookup.
    gateway_map = {j.get("id"): j for j in gateway_jobs if j.get("id")}

    registry_changed = False
    with registry:
        crew_scheds = registry.get_schedules(crew_id)
        for sched in crew_scheds:
            job_id = sched.get("job_id")
            if job_id not in gateway_map:
                # Job absent from gateway — either a fresh container (bootstrap
                # case, will be reseeded below) or deleted inside the container.
                # We cannot distinguish the two from a single snapshot, so leave
                # the registry entry intact; the reseed pass will re-register it
                # if enabled.  A future improvement could track explicit deletes.
                continue
            # Job exists in gateway — sync enabled state and schedule type.
            gw = gateway_map[job_id]
            new_enabled = bool(gw.get("enabled", True))
            new_interval = gw.get("every_secs") or gw.get("interval_secs")
            new_cron = gw.get("cron_expr")
            changed = False
            if sched.get("enabled", True) != new_enabled:
                sched["enabled"] = new_enabled
                changed = True
            if new_interval is not None and sched.get("interval_secs") != new_interval:
                sched["interval_secs"] = new_interval
                changed = True
            if new_cron is not None and sched.get("cron_expr") != new_cron:
                sched["cron_expr"] = new_cron
                changed = True
            if "model" in gw and sched.get("model") != gw.get("model"):
                sched["model"] = gw.get("model")
                changed = True
            if changed:
                registry_changed = True
                logger.info(
                    "Reconciled schedule %s on crew %s from gateway (enabled=%s)",
                    sched.get("name"), crew_id, new_enabled,
                )

        if registry_changed:
            pass  # registry auto-saves on clean exit via CrewRegistry.__exit__
        # Reload schedules for the reseed pass (may have been mutated above).
        schedules = registry.get_schedules(crew_id)

    # ── Reseed pass: registry → gateway (bootstrap only) ──────────────────────
    for sched in schedules:
        if not sched.get("enabled", True):
            continue

        # ── Captain entries use dispatch+steer, not gateway crons ─────────────
        if sched.get("type") == "captain":
            current_task_id = sched.get("current_task_id")
            if not current_task_id:
                # No task yet — dispatch immediately
                try:
                    try:
                        from captain_engine import _dispatch_captain_checkin  # container
                    except ModuleNotFoundError:
                        from transport.captain_engine import _dispatch_captain_checkin  # type: ignore[no-redef]
                    new_task_id = _dispatch_captain_checkin(
                        crew, crew_id, model=sched.get("model")
                    )
                    with registry:
                        for s in registry.get_schedules(crew_id):
                            if s.get("type") == "captain":
                                s["current_task_id"] = new_task_id
                                break
                    logger.info(
                        "Re-seeded captain check-in for crew %s (new task %s)",
                        crew_id, new_task_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to re-seed captain check-in for crew %s: %s",
                        crew_id, e,
                    )
            else:
                # Has a task_id — verify liveness
                try:
                    task_info = _crew_api(crew, "GET", f"/api/spawn/{current_task_id}")
                    # Task exists — leave it; the captain monitor will steer it
                    logger.debug(
                        "Captain check-in task %s still live for crew %s",
                        current_task_id, crew_id,
                    )
                except Exception as e:
                    err_str = str(e)
                    if "conversation_gone" in err_str or "404" in err_str or "not found" in err_str:
                        # Session gone after container restart — re-dispatch
                        logger.info(
                            "Captain check-in task %s gone for crew %s — re-dispatching",
                            current_task_id, crew_id,
                        )
                        try:
                            try:
                                from captain_engine import _dispatch_captain_checkin  # container
                            except ModuleNotFoundError:
                                from transport.captain_engine import _dispatch_captain_checkin  # type: ignore[no-redef]
                            new_task_id = _dispatch_captain_checkin(
                                crew, crew_id, model=sched.get("model")
                            )
                            with registry:
                                for s in registry.get_schedules(crew_id):
                                    if s.get("type") == "captain":
                                        s["current_task_id"] = new_task_id
                                        break
                            logger.info(
                                "Re-dispatched captain check-in for crew %s (new task %s)",
                                crew_id, new_task_id,
                            )
                        except Exception as e2:
                            logger.warning(
                                "Failed to re-dispatch captain check-in for crew %s: %s",
                                crew_id, e2,
                            )
                    else:
                        logger.warning(
                            "Could not check captain task liveness for crew %s: %s",
                            crew_id, e,
                        )
            continue  # Captain entries handled above — skip the cron reseed path

        job_id = sched.get("job_id")
        if job_id in gateway_ids:
            continue  # Already exists in gateway

        # Re-register in gateway
        body: dict[str, Any] = {
            "name": sched.get("name", "reseeded-job"),
            "message": sched.get("message", ""),
            "agent": sched.get("agent", "ghost"),
        }
        if sched.get("model"):
            body["model"] = sched["model"]
        if sched.get("cron_expr"):
            body["cron"] = sched["cron_expr"]
        elif sched.get("interval_secs"):
            body["every"] = sched["interval_secs"]
        else:
            continue  # Can't re-register without a schedule type

        try:
            r = _crew_api(crew, "POST", "/api/crons", json=body)
            # Update registry with new gateway job_id if it changed
            new_id = r.get("id") if isinstance(r, dict) else None
            if new_id and new_id != job_id:
                with registry:
                    for s in registry.get_schedules(crew_id):
                        if s.get("job_id") == job_id:
                            s["job_id"] = new_id
                            break
            logger.info("Re-seeded job %s on crew %s", sched.get("name"), crew_id)
        except Exception as e:
            logger.warning("Failed to re-seed job %s on crew %s: %s", sched.get("name"), crew_id, e)


def _reconcile_registry() -> None:
    """On startup: restart stopped crew containers, remove truly gone ones.
    Also sweeps any orphaned ga-login-* containers left over from a transport
    restart that occurred mid-login flow.
    """
    try:
        podman = _get_podman()
    except Exception:
        logger.info("Podman socket unavailable — skipping registry reconciliation")
        return

    # ── Sweep orphaned login containers ──────────────────────────────────────
    try:
        all_containers = podman._req("GET", "/libpod/containers/json", params={"all": "true"})
        for c in all_containers:
            cname = c.get("Names", [None])[0] or ""
            if cname.lstrip("/").startswith(GA_LOGIN_CONTAINER_PREFIX):
                logger.info("Sweeping orphaned login container on startup: %s", cname)
                _nuke_login_container(podman, cname.lstrip("/"))
            elif cname.lstrip("/").startswith(GA_CLAUDE_LOGIN_CONTAINER_PREFIX):
                logger.info("Sweeping orphaned Claude login container on startup: %s", cname)
                _nuke_claude_login_container(podman, cname.lstrip("/"))
            elif cname.lstrip("/").startswith(GA_CODEX_LOGIN_CONTAINER_PREFIX):
                logger.info("Sweeping orphaned Codex login container on startup: %s", cname)
                _nuke_codex_login_container(podman, cname.lstrip("/"))
    except Exception as e:
        logger.warning("Login container sweep failed: %s", e)

    # Sweep any pending login flows that have exceeded their TTL.  This runs
    # independently of polling so an abandoned flow does not keep its container
    # running until the next poll (or until a restart).
    try:
        _sweep_expired_logins(podman)
    except Exception as e:
        logger.warning("Login expiry sweep failed: %s", e)

    # Snapshot the registry under the lock, then release it before the
    # per-crew restart loop so the lock is not held across gateway waits
    # (up to 30s each).  Per-crew write-backs re-acquire the lock individually.
    with registry:
        snapshot = dict(registry._reg["crews"])

    to_remove = []
    updates: dict[str, dict] = {}  # cid -> fields to merge back

    for cid, info in snapshot.items():
        container = info["container"]
        try:
            exists = podman.container_exists(container)
        except Exception as e:
            logger.warning("Reconcile: transient Podman error checking crew %s — skipping: %s", cid, e)
            continue
        if not exists:
            logger.info("Removing gone crew from registry: %s", cid)
            to_remove.append(cid)
        else:
            try:
                running = podman.container_is_running(container)
            except Exception as e:
                logger.warning("Reconcile: transient Podman error checking running state for crew %s — skipping: %s", cid, e)
                continue
            if not running:
                # Container exists but stopped (e.g. VM reboot) — restart it.
                # Delegates to _launcher._run_restart_cycle for the
                # patch-config → stop → start → wait-gateway → mint-cookie cycle.
                logger.info("Restarting stopped crew on startup: %s", cid)
                try:
                    from launcher import _launcher  # container: flat /app/
                except ModuleNotFoundError:
                    from transport.launcher import _launcher  # local dev
                cycle_result = _launcher._run_restart_cycle(info, cid)
                updates[cid] = cycle_result
                if cycle_result.get("status") == "running":
                    logger.info("Crew %s restored", cid)
                    # Re-seed gateway schedules from registry
                    restored_crew = dict(info)
                    if cycle_result.get("cookie"):
                        restored_crew["cookie"] = cycle_result["cookie"]
                    deployed = _deployed_agent_names(podman, container)
                    _enroll_crew_members(restored_crew, cid, deployed)
                    updates[cid]["enrolled_agents"] = [
                        n.removesuffix(".json") for n in deployed
                    ]
                    try:
                        _reseed_crew_schedules(restored_crew, cid, info)
                    except Exception as e:
                        logger.warning("Schedule re-seed failed for crew %s: %s", cid, e)

    # Write all changes back under the lock in one pass
    try:
        with registry:
            for cid in to_remove:
                registry._reg["crews"].pop(cid, None)
            for cid, fields in updates.items():
                if cid in registry._reg["crews"]:
                    registry._reg["crews"][cid].update(fields)
    except Exception as e:
        logger.error(
            "Registry I/O error during reconcile write-back — skipping write to avoid data loss: %s", e
        )
        return
    logger.info("Registry reconciled. Live crews: %s", list(snapshot.keys()))


def _patch_crew_config(podman: PodmanClient, container: str, composition_entry: dict | None = None) -> None:
    """Patch KiroCrew config while the container is running.

    The stopped-crew recovery path calls this immediately after a provisional
    start, before waiting for gateway readiness. Create the destination
    directory in the exec script so the patch does not depend on the gateway
    having seeded the config files already.

    Writes to config.local.json (user overrides that survive gateway upgrades
    and restarts) rather than config.json (which the gateway re-seeds on every
    start). The gateway deep-merges config.local.json over config.json on every
    load, so these overrides are permanent without needing to re-patch.
    """
    # Build the agent-config overrides as a plain dict, then hand them to
    # patch_crew_config.py (which deep-merges them into config.local.json).
    #
    # KiroCrew 0.4.0 requires a non-empty `agent` field, sourced from
    # GA_CREW_AGENT (default "kiro"). Bounds enforced by the gateway with a 4xx
    # on out-of-range:
    #   spawn_min_memory_gb: >= 0 (0 disables the spawn memory gate); no upper cap.
    #   resource_pressure_gb: >= 0; must be >= resource_critical_gb.
    #   resource_critical_gb: >= 0, and <= resource_pressure_gb.
    #   subagent_timeout_secs: > 0. subagent_max_turns: >= 1 (UI cap 1000, raised in KiroCrew 0.6.0).
    #
    # Memory thresholds default to 0 (disabled). Inside a container, memory is
    # dynamically allocated by the host (balloon on Linux, Podman VM on macOS).
    # The container sees only allocated memory, not the full host headroom, so
    # any non-zero threshold causes premature throttling under real concurrent
    # workloads. Setting to 0 lets the OS manage memory pressure.
    #
    # dangerously_skip_permissions=True bypasses KiroCrew's per-operation
    # permission guard for the agent running inside this crew container. This is
    # intentional and safe: (a) the crew container is an isolated Podman sandbox
    # — normal permission enforcement would block config writes because the
    # transport and gateway run as different UIDs; (b) the flag is scoped to
    # this crew's config.local.json patch only and does not affect the transport
    # process itself.
    agent_overrides: dict[str, Any] = {
        "agent": GA_CREW_AGENT,
        "spawn_min_memory_gb": GA_SPAWN_MIN_MEMORY_GB,
        "resource_pressure_gb": GA_RESOURCE_PRESSURE_GB,
        "resource_critical_gb": GA_RESOURCE_CRITICAL_GB,
        "dangerously_skip_permissions": True,
        "default_agent": "ghost",
        "reasoning_effort": "max",
        "subagent_timeout_secs": GA_SUBAGENT_TIMEOUT_SECS,
        "subagent_max_turns": GA_SUBAGENT_MAX_TURNS,
        # KiroCrew 0.9.0 sandbox bypass for Podman rootless hosts.
        #
        # Podman rootless cannot perform user-namespace bind mounts inside the
        # container (the kernel refuses ``unshare(CLONE_NEWNS)`` or the mount
        # propagation step with errno EPERM/EACCES). Two complementary keys are
        # needed:
        #
        # ``sandbox: "off"`` — skip the sandbox launcher entirely. wrap_argv()
        #   returns the unmodified argv immediately when mode=="off", before
        #   probing or launching the namespace setup. The governance floor clamp
        #   runs first, but on a non-enterprise crew container (no IAM Identity
        #   Center governance profile) the floor is absent and "off" passes
        #   through. Equivalent to the old 0.6.x behaviour where ``sandbox: "off"``
        #   was the sole escape hatch.
        #
        # ``sandbox_allow_unsandboxed_exec: true`` — belt-and-suspenders for
        #   subsequent spawns when the ACP runtime re-reads config independently.
        #   In 0.9.0 the gateway's entrypoint pre-checks config.json (not the
        #   merged config.local.json) and emits a hint if the key is absent; the
        #   key in config.local.json satisfies the actual gate via
        #   KiroCrewConfig.load() deep-merge, but setting it alongside sandbox:off
        #   makes the intent unambiguous.
        #
        # The Podman container itself (and the workspace volume isolation) remain
        # the OS-level security boundary. This is equivalent to running KiroCrew
        # on any other unsandboxable host (e.g. macOS without SIP or inside a
        # Docker container with the default seccomp profile).
        "sandbox": "off",
        "sandbox_allow_unsandboxed_exec": True,
    }
    # When GA_CREW_ACP_BACKEND=claude, write acp_backend into the crew config so
    # the gateway routes agent spawns through the Claude Code ACP runtime rather
    # than the kiro-cli runtime.
    if GA_CREW_ACP_BACKEND == "claude":
        agent_overrides["acp_backend"] = "claude"
    # When GA_CREW_ACP_BACKEND=codex, route agent spawns through the Codex ACP
    # runtime. codex-acp advertises a verified read-only mode at session/new, so
    # ghostship's per-call kiro approval gate does not apply (see crew-governance).
    elif GA_CREW_ACP_BACKEND == "codex":
        agent_overrides["acp_backend"] = "codex"
    # KC_MODEL_DEFAULT sets agent.default_model — a global fallback that applies
    # when no per-agent model field overrides it. Precedence (high→low):
    #   KC_MODEL_OVERRIDE > per-agent model > KC_MODEL_DEFAULT > KiroCrew built-in
    # Only write the field when the env var is set and non-empty; omitting it
    # leaves KiroCrew's built-in default intact for existing installs.
    if KC_MODEL_DEFAULT:
        agent_overrides["default_model"] = KC_MODEL_DEFAULT

    # Build the full config override structure passed to patch_crew_config.py.
    # The script deep-merges every top-level key into config.local.json, so
    # non-agent sections are written directly at the right path.
    #
    # Headless-optimised overrides applied to every spec-ops crew (fixed values,
    # not operator-configurable — see design.md D1):
    #   stt.enabled = false        — no microphone in a headless server crew
    #   session.eager_spawn = false  — spawn session on first dispatch, not at
    #                                  startup; eliminates the ~340 MB pre-fork
    #   session.timeout_secs = 300   — reclaim session memory within 5 min of
    #                                  task completion (was 3600 s / 1 hour)
    #   session.watchdog_rss_max_mb = 2000 — hard RSS ceiling per session process;
    #                                  recycles session if exceeded (set above
    #                                  ~1.9 GB active task peak to avoid cycling
    #                                  healthy sessions)
    #   telemetry.beacon_enabled = false — suppress outbound beacon on server
    #   auto_update = false        — prevent version drift in a pinned container
    # Resolve which agents this composition deploys so config.agents entries
    # are generated dynamically rather than hardcoded.
    manifest_agents = _load_crew_manifest(composition_entry).get("agents", "*")

    full_overrides: dict[str, Any] = {
        "agent": agent_overrides,
        "stt": {"enabled": False},
        "session": {
            "eager_spawn": False,
            "timeout_secs": 300,
            "watchdog_rss_max_mb": 2000,
        },
        "telemetry": {"beacon_enabled": False},
        "auto_update": False,
        # Long SDD runs (Spectre → Ghost → Banshee → Reaper) can exceed the
        # default 2h (7200s) limit introduced in KiroCrew 0.7.0. Set to 4h so
        # multi-persona orchestration sessions are not cut off mid-flight.
        "orchestrator": {"max_plan_duration_seconds": 14400},
        # Register deployed agent files as named KiroCrew crew members so
        # their sessions are treated as member DM threads (token-stamped).
        # Derived from the Academy /agents directory (bind-mounted) filtered
        # by the composition manifest — same source _copy_agents uses — so any
        # composition's agents are enrolled, not just a hardcoded list.
        # Deep-merged over config.json — the "default" agent entry is preserved.
        "agents": {
            af.stem: {
                "kiro_agent": af.stem,
                "memory_store": "default",
                "session_control": True,
                "member_dispatch": True,
            }
            for af in Path("/agents").glob("*.json")
            if _manifest_selects(manifest_agents, af.name)
        },
    }

    overrides_b64 = base64.b64encode(json.dumps(full_overrides).encode()).decode()
    config_path = f"{KIRO_CREW_DIR}/config.local.json"
    try:
        result = podman.container_exec(
            container,
            ["python3", f"{SCRIPTS_DIR}/patch_crew_config.py", config_path, overrides_b64],
        )
        logger.info("Config patch for %s: %s", container, result.strip())
    except Exception as e:
        logger.warning("Config patch failed for %s: %s", container, e)


def _resolve_dispatch_slot(
    agent: str,
    slot: bool | None,
    crew,
) -> tuple[str | None, str | None]:
    """Resolve the effective slot and parent_session for a dispatch.

    Returns (effective_slot, parent_session).

    Two modes:

    - ``slot=None`` (default): let the system decide. An enrolled agent routes
      to its member DM slot (``parent_session="dashboard:member-<slug>"``),
      echoing ``"<slug>"`` as the slot name. An unenrolled agent routes headless
      (``(None, None)``) — no session is created.
    - ``slot=False``: explicit headless, regardless of enrollment —
      ``(None, None)``.

    ``True`` is not a valid value under the current type annotation; a caller
    passing it receives headless dispatch (``(None, None)``) — it does NOT
    fall through to the member-slot path, because the member-slot guard checks
    ``slot is None`` explicitly.
    """
    if isinstance(crew, Crew):
        enrolled: frozenset[str] = frozenset(crew.enrolled_agents or [])
    else:
        enrolled = frozenset(crew.get("enrolled_agents") or [])
    if slot is None and agent in enrolled:
        # Echo the agent name (clean) not "member-<agent>" (implementation detail).
        return agent, f"dashboard:member-{agent}"
    # slot=None for an unenrolled agent, or slot=False for anyone → headless.
    return None, None


def _deployed_agent_names(podman: PodmanClient, container: str) -> list[str]:
    """Return the list of agent JSON filenames deployed in this crew container."""
    try:
        out = podman.container_exec(container, ["ls", KIRO_AGENTS_DIR])
        return [n.strip() for n in out.splitlines() if n.strip().endswith(".json")]
    except Exception as e:
        logger.warning("Could not list deployed agents for %s: %s", container, e)
        return []


def _enroll_crew_members(crew: dict, crew_id: str, agent_names: list[str]) -> None:
    """Create member DM thread bindings for all agents deployed in this crew.

    Calls POST /api/members/{slug}/thread for each agent name (derived from
    the copied agent JSON filenames, e.g. ["ghost.json", "raven.json"] →
    slugs ["ghost", "raven"]). Idempotent get-or-create.

    Once the binding exists, sessions opened on that slot are treated as
    member DM threads. The gateway stamps KIROCREW_STUB_SESSION_TOKEN into
    the session's MCP server env AND the session's $KIRO_SESSION_ID becomes
    an attested key — allowing POST /api/spawn with X-Session-Key to pass
    session_key_is_attested().

    Must be called after _patch_crew_config and after gateway-ready.
    Failures are logged but non-fatal.
    """
    slugs = [n.removesuffix(".json") for n in agent_names if n.endswith(".json")]
    for slug in slugs:
        try:
            # Use _crew_api directly (not _crew_api_with_recovery) to avoid
            # re-entering the per-crew recovery lock — this function is called
            # from within _ensure_crew_running while that lock may already be
            # held.  The gateway is confirmed live before enrolment runs, so
            # the recovery wrapper's restart logic is not needed here.
            _crew_api(crew, "POST", f"/api/members/{slug}/thread")
            logger.info("Member DM thread enrolled for %s on crew %s", slug, crew_id)
        except Exception as e:
            logger.warning("Member enrollment failed for %s on crew %s: %s", slug, crew_id, e)


def _inject_policy(
    podman: PodmanClient,
    container: str,
    composition: str,
    policy_signing_key: str,
) -> str:
    """Inject security_policy.json and admission_policy.json into the crew.

    Returns the policy version string for registry storage.
    Raises on failure — caller must catch and handle gracefully.

    Note: admission_policy.json contains trust_keys (the policy_signing_key),
    which is required by KiroCrew's governance API to verify the policy
    signature. The file is written with mode 0600. policy_signing_key is a
    dedicated signing key, separate from admiral_secret, so agent-readable
    admission_policy.json no longer exposes the Admiral mail-signing secret.
    See docs/auth.md for the threat model.
    """
    # 1. Load template — composition-specific or fallback to default
    policy_template_path = Path(f"/policies/{composition}.json")
    if not policy_template_path.exists():
        policy_template_path = Path("/policies/default.json")
    policy = json.loads(policy_template_path.read_text())
    policy_version = policy.get("version", "1")

    # 2. Add identity block (without signature yet) and pass everything into
    # the container to sign.  Signing runs inside the container so the
    # canonicalization is always the same version as the verifier.
    # The policy + policy_signing_key are passed as a single base64-encoded
    # JSON payload to avoid interpolating the secret as a Python literal.
    policy["identity"] = {"issuer": "ghostship"}
    payload_b64 = base64.b64encode(
        json.dumps({"policy": policy, "policy_signing_key": policy_signing_key}).encode("utf-8")
    ).decode()

    # Signing runs inside the container (see inject_policy.py).
    result = podman.container_exec_checked(
        container,
        ["python3", f"{SCRIPTS_DIR}/inject_policy.py", KIRO_CREW_DIR, payload_b64],
    )
    logger.info("Injected security policy for %s: %s", container, result.strip())
    return policy_version


def _finish_crew_setup(
    podman: PodmanClient,
    crew_id: str,
    container: str,
    volume: str,
    home_volume: str,
    auth_b64: str,
    composition: str = "spec-ops",
    composition_entry: dict | None = None,
    *,
    admiral_secret: str,
    dashboard: bool = False,
) -> dict:
    """Complete crew setup after auth is confirmed.

    Delegates to ``_launcher.finish_setup`` (transport/launcher.py).
    Kept as a module-level wrapper so existing call sites and test patches
    on ``lifecycle._finish_crew_setup`` continue to resolve.
    """
    try:
        from launcher import _launcher  # container: flat /app/
    except ModuleNotFoundError:
        from transport.launcher import _launcher  # local dev
    return _launcher.finish_setup(
        podman,
        crew_id,
        container,
        volume,
        home_volume,
        auth_b64,
        composition,
        composition_entry,
        admiral_secret=admiral_secret,
        dashboard=dashboard,
    )


# ── Login container helpers ───────────────────────────────────────────────────
# These are called from server.py's login state machine; they live here because
# they touch crew container state (Podman operations on login containers).

def _start_login_container(podman: PodmanClient) -> str:
    """Create and start an ephemeral ga-login-<token> container.

    Uses cfg.kc_base_image (upstream kirocrew) rather than the local crew image —
    the login container only needs kiro-cli, and using the upstream image avoids
    any risk from a tainted local build. No volumes — kiro-cli DB lives in the
    container's ephemeral writable layer. The container is NOT registered in the
    crew registry and is invisible to MCP tools. Returns the container name.
    """
    try:
        from login import KIRO_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import KIRO_FLOW  # local dev
    return KIRO_FLOW.start_container(podman)


def _nuke_login_container(podman: PodmanClient, name: str) -> None:
    """Best-effort stop and remove a ga-login-* container."""
    try:
        from login import KIRO_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import KIRO_FLOW  # local dev
    KIRO_FLOW._nuke_container(podman, name)


# ── Claude login container helpers ────────────────────────────────────────────


def _start_claude_login_container(podman: PodmanClient) -> str:
    """Create and start an ephemeral ga-claude-login-<token> container.

    Uses KC_IMAGE (the local spec-ops image built with the claude toolchain)
    because the ``claude`` CLI is only present in that image.  Fails with a clear
    error if the image is not found or does not have ``claude`` installed.
    Returns the container name.
    """
    try:
        from login import CLAUDE_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import CLAUDE_FLOW  # local dev
    return CLAUDE_FLOW.start_container(podman)


def _nuke_claude_login_container(podman: PodmanClient, name: str) -> None:
    """Best-effort stop and remove a ga-claude-login-* container."""
    try:
        from login import CLAUDE_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import CLAUDE_FLOW  # local dev
    CLAUDE_FLOW._nuke_container(podman, name)


# ── kiro-cli auth file helpers ──────────────────────────────────────

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
    _write_secret_file(path, value)


# ── Claude OAuth auth file helpers ────────────────────────────────────────────


def _claude_auth_file_path() -> Path:
    """Return the Claude OAuth credential tar archive path under the data mount."""
    return DATA_DIR / GA_CLAUDE_AUTH_FILE


def _claude_auth_exists() -> bool:
    """Return True if the ga-claude-auth credential archive exists and is non-empty."""
    p = _claude_auth_file_path()
    return p.is_file() and p.stat().st_size > 0


def _write_claude_auth_file(data: bytes, _path: Path | None = None) -> None:
    """Persist the Claude OAuth tar archive (mode 0600).

    _path: override the default path (for testing only).
    """
    path = _path if _path is not None else _claude_auth_file_path()
    _write_secret_file(path, data)


def _inject_claude_auth(podman: "PodmanClient", container: str) -> None:
    """Inject the ga-claude-auth tar archive into container's ~/.claude/.

    Reads the host-side ga-claude-auth file (a tar of ~/.claude/) and untars it
    into /home/kirocrew/.claude/ inside the crew container, matching the path
    that the claude-agent-acp server reads for OAuth credentials.

    Injection strategy (SEC-1): the host-side ga-claude-auth file is already a
    tar of ``~/.claude/``, so its bytes are streamed straight into the container
    via a single ``container_archive_put`` call whose target path untars the
    archive in place.  No base64 encoding, no chunking, no temp file, and no
    ``sh -c`` exec — the credential bytes never pass through a shell, so no
    future non-base64 payload can open a shell-injection surface.
    """
    auth_path = _claude_auth_file_path()
    if not auth_path.is_file():
        raise RuntimeError("ga-claude-auth not found — Claude login required first")

    # Ensure the target directory exists in the container
    podman.container_exec(container, ["mkdir", "-p", "/home/kirocrew/.claude"])

    # The auth file is a tar of ~/.claude/ — hand the raw tar bytes to the
    # archive-put endpoint, which untars them directly at the target path.
    tar_bytes = auth_path.read_bytes()
    podman.container_archive_put(container, "/home/kirocrew/.claude/", tar_bytes)
    logger.info("Injected Claude OAuth credentials into crew container %s", container)


# ── Shared PTY login helper ──────────────────────────────────────────────────

# Terminal control sequences the CLI may wrap around printed text: CSI (colour,
# cursor), OSC (including OSC-8 hyperlinks, terminated by BEL or ESC \), and a
# bare BEL. Stripped before URL and code patterns run, so the returned URL is
# exactly the text the CLI printed.
_TERMINAL_SEQUENCE_RE = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b\[[0-9;?]*[ -/]*[@-~]"
    r"|\x07"
)
# An escape sequence still arriving at the end of the buffer. URL matching waits
# for its terminator, otherwise a URL inside an unterminated OSC-8 link could be
# returned truncated.
_OPEN_SEQUENCE_RE = re.compile(r"\x1b$|\x1b\[[0-9;?]*[ -/]*$|\x1b\][^\x07\x1b]*$")


def _strip_terminal_sequences(text: str) -> str:
    """Remove terminal control sequences and BEL from PTY output text."""
    return _TERMINAL_SEQUENCE_RE.sub("", text)


def _run_pty_login_flow(
    pty_sock: "socket.socket",
    prompt_patterns: "list[tuple[re.Pattern, bytes]]",
    url_patterns: "list[re.Pattern]",
    code_pattern: "re.Pattern | None",
    deadline_secs: float = 45.0,
    initial_bytes: bytes = b"",
) -> "tuple[str | None, str | None]":
    """Run a PTY select-loop and extract a login URL and optional code.

    Owns the select() loop, chunk accumulation, prompt-answer dispatch,
    URL/code extraction, and background PTY drain thread.  Returns
    ``(login_url, login_code)`` — both may be ``None`` on timeout.

    Parameters
    ----------
    pty_sock:
        Non-blocking PTY socket from ``container_exec_pty_stdin``.  The
        caller must call ``pty_sock.setblocking(False)`` before passing it.
        The helper sets it back to blocking before starting the drain thread.
    prompt_patterns:
        Ordered list of ``(compiled_pattern, answer_bytes)`` pairs.  When a
        pattern matches the accumulated text and has not yet been answered, the
        helper writes ``answer_bytes`` to the PTY socket.  Each pattern is
        answered at most once.
    url_patterns:
        Ordered list of compiled URL patterns tried in sequence.  The first
        match wins.  Patterns that capture group 1 use ``group(1)``; patterns
        with no groups use ``group(0)``.
    code_pattern:
        Optional compiled pattern for the short device code.  ``group(1)`` is
        used if the pattern matches the accumulated text or the extracted URL.
        Pass ``None`` when the backend does not surface a code.
    deadline_secs:
        Wall-clock budget for the loop.  Default 45 s.
    initial_bytes:
        PTY bytes already received (leftover from the HTTP upgrade read in
        ``container_exec_pty_stdin``).  Pre-populated into the accumulator so
        no early output is lost before the select-loop starts.
    """
    deadline = time.time() + deadline_secs
    # Pre-seed the accumulator with any bytes already received during the
    # HTTP-to-PTY upgrade handshake so they are not lost.
    collected = bytearray(initial_bytes)
    login_url: str | None = None
    login_code: str | None = None
    answered: set[int] = set()  # indices into prompt_patterns already sent

    def _process_collected() -> bool:
        """Process current contents of ``collected``; return True when a URL is found."""
        nonlocal login_url, login_code
        raw_text = collected.decode("utf-8", errors="replace")
        text = _strip_terminal_sequences(raw_text)
        url_ready = not _OPEN_SEQUENCE_RE.search(raw_text)

        for idx, (pattern, answer) in enumerate(prompt_patterns):
            if idx in answered:
                continue
            if pattern.search(text):
                try:
                    pty_sock.sendall(answer)
                except Exception:
                    pass
                answered.add(idx)

        for pat in url_patterns if url_ready else ():
            m = pat.search(text)
            if m:
                login_url = (m.group(1) if m.lastindex else m.group(0)).rstrip(").,")
                if code_pattern:
                    cm = code_pattern.search(login_url) or code_pattern.search(text)
                    if cm:
                        # Support two-branch patterns: group(1) is the URL-param
                        # branch; group(2) is the prose branch.  Use whichever
                        # branch matched (the other will be None).
                        login_code = cm.group(1) or (
                            cm.group(2) if cm.lastindex and cm.lastindex >= 2 else None
                        )
                return True
        return False

    try:
        # If initial_bytes already contain the URL, return without entering the
        # select loop.  This is the common case when PTY output arrives in the
        # same recv() chunk as the 101 Switching Protocols headers.
        if collected and _process_collected():
            pass  # login_url is set; the ``if login_url`` branch below handles drain.
        else:
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
                    if _process_collected():
                        break
    except Exception as e:
        logger.warning("PTY read error in _run_pty_login_flow: %s", e)

    if login_url:
        # Hand remaining PTY output to a background daemon thread so the
        # socket drains to EOF without blocking the event loop.
        pty_sock.setblocking(True)

        def _drain() -> None:
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

        threading.Thread(target=_drain, daemon=True, name="pty-drain").start()

    return login_url, login_code


# ── Login device-flow state ─────────────────────────────────────────
# _login_pending holds the in-progress login flow's state (or None when idle):
#   container: str   — ephemeral ga-login-* container name
#   state:     str   — "starting" | "started"
#   exec_id:   str   — Podman exec session id (informational)
#   started_at: float — time.time() when the flow started
_login_pending: dict | None = None
_login_pending_lock = threading.Lock()


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
    try:
        from login import KIRO_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import KIRO_FLOW  # local dev
    global _login_pending, _login_pending_lock
    result = KIRO_FLOW.initiate(podman)
    with _login_pending_lock:
        _login_pending = KIRO_FLOW._pending
    return result


def _abort_pending_login(podman: "PodmanClient") -> bool:
    """Abort an in-progress kiro login flow, if any.

    Acquires _login_pending_lock, nukes the login container (best-effort), and
    clears _login_pending so a fresh POST /login can be issued immediately.

    Returns True if a flow was in progress and was aborted, False if there was
    nothing to abort (no-op).

    Safe to call from the logout handler regardless of whether a flow is
    pending.
    """
    try:
        from login import KIRO_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import KIRO_FLOW  # local dev
    global _login_pending, _login_pending_lock
    result = KIRO_FLOW.abort(podman)
    with _login_pending_lock:
        _login_pending = KIRO_FLOW._pending
    return result


# ── Claude OAuth device-flow state ────────────────────────────────────────────
# _claude_login_pending mirrors _login_pending:
#   container:  str   — ephemeral ga-claude-login-* container name
#   state:      str   — "starting" | "started"
#   exec_id:    str   — Podman exec session id (informational)
#   started_at: float — time.time() when the flow started
_claude_login_pending: dict | None = None
_claude_login_pending_lock = threading.Lock()


def _initiate_claude_login(podman: "PodmanClient") -> dict:
    """Start a Claude OAuth device-code flow and return the login URL.

    Mirrors _initiate_login: acquires _claude_login_pending_lock, applies
    TOCTOU-safe guards, starts the ephemeral ga-claude-login-* container from
    KC_IMAGE (spec-ops with the claude toolchain), runs ``claude auth login``
    via container_exec_pty_stdin, reads the 45-second PTY stream with select(),
    extracts the verification URL, drains the PTY in background, stores pending
    state in _claude_login_pending.

    URL regex note (task 1.2): ``claude auth login`` prints a line of the form:
        Please open the following URL in your browser:
        https://claude.ai/auth/login?...
    or via Anthropic's device-code flow:
        https://console.anthropic.com/...?code=...
    We match both with a broad URL pattern and fall back to any https:// line
    containing 'anthropic' or 'claude.ai'. The regex is documented here so it
    is easy to update if the CLI changes its output format.

    Returns one of:
      {"login_url": str, "code": str | None}  — flow started successfully
      {"login_pending": True}                 — a flow is already in progress
      {"error": str}                          — hard failure
    """
    try:
        from login import CLAUDE_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import CLAUDE_FLOW  # local dev
    global _claude_login_pending, _claude_login_pending_lock
    result = CLAUDE_FLOW.initiate(podman)
    with _claude_login_pending_lock:
        _claude_login_pending = CLAUDE_FLOW._pending
    return result


# How long a submitted code may take to complete the exchange before the flow is
# abandoned. The exchange is a single network round-trip, so this is generous.
CLAUDE_LOGIN_CODE_DEADLINE_SECS = 120.0

# TTLs for kiro and Codex device flows.  Matches CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS —
# same device-flow window.  An abandoned flow exceeding this limit is expired by
# _sweep_expired_logins regardless of polling activity.
KIRO_LOGIN_TTL_SECS = 900.0
CODEX_LOGIN_TTL_SECS = 900.0


def _submit_claude_login_code(code: str) -> dict:
    """Write the user's pasted authorisation code to the pending login's PTY.

    Delegates to CLAUDE_FLOW.submit_code() and keeps the lifecycle-level
    _claude_login_pending mirror in sync so existing test assertions on
    ``lifecycle._claude_login_pending["state"]`` continue to work.

    Returns one of:
      {"ok": True}                 — code written; the exchange is in progress
      {"error": "no_pending"}      — no Claude login flow is awaiting a code
      {"error": "already_submitted"} — a code was already written for this flow
      {"error": "pty_write_failed"}  — the PTY closed before the code was written

    The code is never logged or returned.
    """
    try:
        from login import CLAUDE_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import CLAUDE_FLOW  # local dev
    result = CLAUDE_FLOW.submit_code(code)
    global _claude_login_pending, _claude_login_pending_lock
    with _claude_login_pending_lock:
        _claude_login_pending = CLAUDE_FLOW._pending
    return result


# How long a login may wait for the user to approve in the browser and paste the
# code. Without this, an abandoned flow keeps its login container running until
# the transport restarts.
CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS = 900.0


def _claude_login_code_expired(pending: dict) -> bool:
    """True when a Claude login has exceeded its deadline.

    Two windows: the user must submit a code within CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS
    of the flow starting, and a submitted code must complete the exchange within
    CLAUDE_LOGIN_CODE_DEADLINE_SECS.
    """
    now = time.time()
    state = pending.get("state")
    if state == "awaiting_code":
        started_at = pending.get("started_at")
        return started_at is not None and now - started_at > CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS
    if state == "code_submitted":
        submitted_at = pending.get("code_submitted_at")
        return submitted_at is not None and now - submitted_at > CLAUDE_LOGIN_CODE_DEADLINE_SECS
    return False


def _kiro_login_expired(pending: dict) -> bool:
    """True when a kiro device flow has exceeded KIRO_LOGIN_TTL_SECS."""
    started_at = pending.get("started_at")
    return started_at is not None and time.time() - started_at > KIRO_LOGIN_TTL_SECS


def _codex_login_expired(pending: dict) -> bool:
    """True when a Codex device flow has exceeded CODEX_LOGIN_TTL_SECS."""
    started_at = pending.get("started_at")
    return started_at is not None and time.time() - started_at > CODEX_LOGIN_TTL_SECS


def _sweep_expired_logins(podman: "PodmanClient") -> None:
    """Expire pending login flows that have exceeded their TTL.

    Inspects the pending-login dicts for all three backends (kiro, Claude,
    Codex) under their respective locks and expires any flow whose deadline has
    passed.  On expiry: nukes the login container (best-effort) and clears the
    pending dict so a fresh login can be started.

    Must be called from a context that already holds the ``podman`` client (e.g.
    the startup sweep in ``_reconcile_registry``).  The function is intentionally
    coarse-grained: each backend's check acquires and releases its own lock
    independently so a slow nuke does not hold an unrelated backend's lock.
    """
    try:
        from login import ALL_FLOWS  # container
    except ModuleNotFoundError:
        from transport.login import ALL_FLOWS  # local dev
    for flow in ALL_FLOWS:
        if flow.is_expired():
            flow.abort(podman)


CLAUDE_CREDENTIAL_FILE = ".credentials.json"
_CLAUDE_CONFIG_DIR_IN_CONTAINER = "/home/kirocrew/.claude"


def _archive_has_file(tar_bytes: bytes, filename: str) -> bool:
    """True when the archive contains a non-empty regular file named ``filename``."""
    try:
        with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
            for member in tf.getmembers():
                if (
                    member.isfile()
                    and os.path.basename(member.name) == filename
                    and member.size > 0
                ):
                    return True
    except tarfile.TarError:
        return False
    return False


def _archive_has_claude_credential(tar_bytes: bytes) -> bool:
    """True when the archive contains a non-empty CLAUDE_CREDENTIAL_FILE.

    Other members (such as backups/ or .claude.json) do not count as completion.
    """
    return _archive_has_file(tar_bytes, CLAUDE_CREDENTIAL_FILE)


def _poll_claude_login_container(podman: "PodmanClient", container: str) -> bytes | None:
    """Poll container for completed Claude credentials.

    Completion is the CLI's credential file (~/.claude/.credentials.json) being
    present and non-empty. Only then is ~/.claude/ tarred and returned, so the
    crews receive the same directory layout the CLI wrote. Returns None when the
    credential is not yet present, or when the archive would not contain it.

    The caller writes the tar to ga-claude-auth (mode 0600) and nukes the login
    container. Any other file under ~/.claude/ (such as backups/) is not evidence
    of login: the earlier any-file check matched a config backup and reported a
    login that never happened.
    """
    try:
        check = podman.container_exec(
            container,
            [
                "sh", "-c",
                f"test -s {_CLAUDE_CONFIG_DIR_IN_CONTAINER}/{CLAUDE_CREDENTIAL_FILE} && echo present",
            ],
        )
        if not check or "present" not in check:
            return None
        # container_exec returns stdout as a string, so base64 is the transport.
        tar_b64_result = podman.container_exec(
            container,
            [
                "sh", "-c",
                f"tar -cf - -C {_CLAUDE_CONFIG_DIR_IN_CONTAINER}/ . 2>/dev/null | base64",
            ],
        )
        if not tar_b64_result or not tar_b64_result.strip():
            return None
        tar_bytes = base64.b64decode(tar_b64_result.strip())
        if not _archive_has_claude_credential(tar_bytes):
            logger.warning("Claude login archive did not contain %s; not completing", CLAUDE_CREDENTIAL_FILE)
            return None
        return tar_bytes
    except Exception as e:
        logger.warning("Error polling Claude login container: %s", e)
    return None


def _abort_claude_pending_login(podman: "PodmanClient") -> bool:
    """Abort an in-progress Claude login flow, if any.

    Mirrors _abort_pending_login for the Claude OAuth device flow. Acquires
    _claude_login_pending_lock, closes the PTY socket if present, nukes the
    login container (best-effort), and clears _claude_login_pending.

    Returns True if a flow was aborted, False if nothing was pending.
    """
    try:
        from login import CLAUDE_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import CLAUDE_FLOW  # local dev
    global _claude_login_pending, _claude_login_pending_lock
    # Capture the pty_sock BEFORE abort() clears _pending
    with CLAUDE_FLOW._lock:
        pending = CLAUDE_FLOW._pending
        pty_sock = pending.get("pty_sock") if pending else None
    result = CLAUDE_FLOW.abort(podman)
    # Close the PTY socket if present (abort() does not close it)
    if pty_sock is not None:
        try:
            pty_sock.close()
        except Exception:
            pass
    with _claude_login_pending_lock:
        _claude_login_pending = CLAUDE_FLOW._pending
    return result


# ── Codex login container helpers ─────────────────────────────────────────────


def _nuke_codex_login_container(podman: PodmanClient, name: str) -> None:
    """Best-effort stop and remove a ga-codex-login-* container."""
    try:
        from login import CODEX_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import CODEX_FLOW  # local dev
    CODEX_FLOW._nuke_container(podman, name)


# ── Codex OAuth auth file helpers ─────────────────────────────────────────────


def _codex_auth_file_path() -> Path:
    """Return the Codex OAuth credential tar archive path under the data mount."""
    return DATA_DIR / GA_CODEX_AUTH_FILE


def _codex_auth_exists() -> bool:
    """Return True if the ga-codex-auth credential archive exists and is non-empty."""
    p = _codex_auth_file_path()
    return p.is_file() and p.stat().st_size > 0


def _write_codex_auth_file(data: bytes, _path: Path | None = None) -> None:
    """Persist the Codex OAuth tar archive (mode 0600).

    _path: override the default path (for testing only).
    """
    path = _path if _path is not None else _codex_auth_file_path()
    _write_secret_file(path, data)


def _inject_codex_auth(podman: "PodmanClient", container: str) -> None:
    """Inject the ga-codex-auth tar archive into container's ~/.codex/.

    Reads the host-side ga-codex-auth file (a tar of ~/.codex/, holding
    auth.json) and untars it into /home/kirocrew/.codex/ inside the crew
    container, matching the path that codex-acp reads for OAuth credentials
    (relocatable via CODEX_HOME, but ghostship uses the default location).

    Injection strategy mirrors _inject_claude_auth (SEC-1): the host-side
    ga-codex-auth file is already a tar of ``~/.codex/``, so its bytes stream
    straight into the container via a single ``container_archive_put`` call that
    untars the archive at the target path.  No base64 encoding, no chunking, no
    temp file, and no ``sh -c`` exec — the credential bytes never pass through a
    shell.
    """
    auth_path = _codex_auth_file_path()
    if not auth_path.is_file():
        raise RuntimeError("ga-codex-auth not found — Codex login required first")

    # Ensure the target directory exists in the container
    podman.container_exec(container, ["mkdir", "-p", "/home/kirocrew/.codex"])

    tar_bytes = auth_path.read_bytes()
    podman.container_archive_put(container, "/home/kirocrew/.codex/", tar_bytes)
    logger.info("Injected Codex OAuth credentials into crew container %s", container)


# ── Codex OAuth device-flow state ─────────────────────────────────────────────
# _codex_login_pending mirrors _claude_login_pending:
#   container:  str   — ephemeral ga-codex-login-* container name
#   state:      str   — "starting" | "started"
#   exec_id:    str   — Podman exec session id (informational)
#   started_at: float — time.time() when the flow started
_codex_login_pending: dict | None = None
_codex_login_pending_lock = threading.Lock()


def _initiate_codex_login(podman: "PodmanClient") -> dict:
    """Start a Codex OAuth/device login flow and return the login URL.

    Mirrors _initiate_claude_login: acquires _codex_login_pending_lock, applies
    TOCTOU-safe guards, starts the ephemeral ga-codex-login-* container from
    KC_IMAGE (spec-ops with the codex toolchain), runs the codex-acp login
    command via container_exec_pty_stdin, reads the 45-second PTY stream with
    select(), extracts the verification URL, drains the PTY in background, and
    stores pending state in _codex_login_pending.

    Login-flow shape note (design Open Questions / task 1.2): the exact codex-acp
    login UX (device-code vs browser sign-in, and whether a short code is
    surfaced alongside the login_url) is confirmed against the adapter at
    implementation time. The command is ``codex-acp login`` (headless), and the
    URL regex accepts an OpenAI/ChatGPT auth URL first, then any https URL after
    a "URL"/"browser" cue, then any long https URL as a last resort. The
    codex-auth spec explicitly permits a code-less login_url response, so a
    missing code is not an error.

    Returns one of:
      {"login_url": str, "code": str | None}  — flow started successfully
      {"login_pending": True}                 — a flow is already in progress
      {"error": str}                          — hard failure
    """
    try:
        from login import CODEX_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import CODEX_FLOW  # local dev
    global _codex_login_pending, _codex_login_pending_lock
    result = CODEX_FLOW.initiate(podman)
    with _codex_login_pending_lock:
        _codex_login_pending = CODEX_FLOW._pending
    return result



CODEX_CREDENTIAL_FILE = "auth.json"
_CODEX_CONFIG_DIR_IN_CONTAINER = "/home/kirocrew/.codex"


def _poll_codex_login_container(podman: "PodmanClient", container: str) -> bytes | None:
    """Poll container for completed Codex credentials.

    Completion is codex-acp's credential file (~/.codex/auth.json) being present
    and non-empty. Only then is ~/.codex/ tarred and returned. Any other file
    (such as config.toml) is not evidence of login: an any-file check would
    store an archive with no credential and then report "Already authenticated".
    Returns None when the credential is not yet present, or when the archive
    would not contain it.

    On completion: the caller writes the tar to ga-codex-auth (mode 0600) and
    nukes the login container.
    """
    try:
        check = podman.container_exec(
            container,
            [
                "sh", "-c",
                f"test -s {_CODEX_CONFIG_DIR_IN_CONTAINER}/{CODEX_CREDENTIAL_FILE} && echo present",
            ],
        )
        if not check or "present" not in check:
            return None
        tar_b64_result = podman.container_exec(
            container,
            ["sh", "-c", f"tar -cf - -C {_CODEX_CONFIG_DIR_IN_CONTAINER}/ . 2>/dev/null | base64"],
        )
        if not tar_b64_result or not tar_b64_result.strip():
            return None
        tar_bytes = base64.b64decode(tar_b64_result.strip())
        if not _archive_has_file(tar_bytes, CODEX_CREDENTIAL_FILE):
            logger.warning("Codex login archive did not contain %s; not completing", CODEX_CREDENTIAL_FILE)
            return None
        return tar_bytes
    except Exception as e:
        logger.warning("Error polling Codex login container: %s", e)
    return None


def _abort_codex_pending_login(podman: "PodmanClient") -> bool:
    """Abort an in-progress Codex login flow, if any.

    Mirrors _abort_pending_login for the Codex OAuth device flow. Acquires
    _codex_login_pending_lock, nukes the login container (best-effort), and
    clears _codex_login_pending.

    Returns True if a flow was aborted, False if nothing was pending.
    """
    try:
        from login import CODEX_FLOW  # container
    except ModuleNotFoundError:
        from transport.login import CODEX_FLOW  # local dev
    global _codex_login_pending, _codex_login_pending_lock
    result = CODEX_FLOW.abort(podman)
    with _codex_login_pending_lock:
        _codex_login_pending = CODEX_FLOW._pending
    return result


# ── Schedule / idle monitors ───────────────────────────────────────
# _schedule_monitor, _idle_monitor, _cron_activity_since and _cron_has_enabled_job
# were extracted to transport/monitors.py and are imported below so existing
# call-sites (server starts the threads; tests patch lifecycle.*) keep resolving.
try:
    import monitors as _monitors  # container: flat /app/
except ModuleNotFoundError:
    from transport import monitors as _monitors  # local dev

_schedule_monitor = _monitors._schedule_monitor
_idle_monitor = _monitors._idle_monitor
_captain_monitor = _monitors._captain_monitor
# ── Batch pickup ────────────────────────────────────────────────────
# GA_PICKUP_MAX_POLL_SECS caps the wall time of one _pickup_batch call, mirroring
# the single-task pickup internal cap (default 30 s). Read from env so operators
# can tune it without a config-dataclass change.
GA_PICKUP_MAX_POLL_SECS = int(os.environ.get("GA_PICKUP_MAX_POLL_SECS", "30"))

_BATCH_POLL_INTERVAL_SECS = 3


def _pickup_batch(
    crew: dict,
    crew_id: str,
    task_ids: list[str],
    podman: "PodmanClient",
    container: str,
    timeout_secs: int,
    pickup_single,
    read_all_mail_counts,
    batch_id: str | None = None,
    update_batch_status=None,
) -> dict:
    """Blocking multi-task pickup: collect results for every id in *task_ids*.

    Orchestrates per-round sequential calls to ``pickup_single(timeout_secs=0)``
    for each task id, aggregating into a dict keyed by task_id. The whole call
    is capped at ``GA_PICKUP_MAX_POLL_SECS`` of wall time (each round polls all
    members once, then sleeps 3 s). A task the gateway does not know about (404
    / missing) is marked ``{"done": false, "lost": true, ...}`` rather than
    raising, so the other members' results survive.

    ``pickup_single`` and ``read_all_mail_counts`` are injected by the caller
    (server.py) to avoid a lifecycle->server import cycle. ``update_batch_status``
    (optional) is called with (crew_id, batch_id, "complete") when every task is
    done and a ``batch_id`` is known.

    Response shape::

        {
          "<task_id>": {<single-task pickup shape> | lost-marker},
          ...,
          "done": bool,          # True only when every member is done
          "completed_tasks": int,
          "total_tasks": int,
          "reason": "timeout" | "admiral_mail",   # only when it applies
        }
    """
    total = len(task_ids)

    # Cap the batch wall time at GA_PICKUP_MAX_POLL_SECS regardless of the
    # requested timeout — identical to the single-task internal cap contract.
    capped_timeout = min(max(0, timeout_secs), GA_PICKUP_MAX_POLL_SECS)

    # Admiral-mail early-return baseline read before the first round.
    if capped_timeout > 0:
        initial_counts = read_all_mail_counts(podman, container)
        initial_admiral_mail = initial_counts.get("admiral", 0)
    else:
        initial_admiral_mail = 0

    deadline = time.monotonic() + capped_timeout

    def _poll_round() -> tuple[dict, int]:
        """Poll every task once; return (results, done_count)."""
        results: dict[str, Any] = {}
        done_count = 0
        for tid in task_ids:
            res = pickup_single(crew, crew_id, tid, podman, container, 0)
            # Lost member: gateway returns 404 for an unknown task id. The
            # single-task path surfaces that as an error string; normalise it
            # to an explicit lost marker so the batch survives.
            err = res.get("error", "") if isinstance(res, dict) else ""
            if err and ("404" in str(err) or "not found" in str(err).lower()):
                res = {
                    "task_id": tid,
                    "done": False,
                    "lost": True,
                    "error": "task not found in gateway",
                }
            results[tid] = res
            if res.get("done"):
                done_count += 1
        return results, done_count

    while True:
        results, done_count = _poll_round()
        all_done = done_count == total and total > 0

        out: dict[str, Any] = dict(results)
        out["done"] = all_done
        out["completed_tasks"] = done_count
        out["total_tasks"] = total

        if all_done:
            if batch_id is not None and update_batch_status is not None:
                try:
                    update_batch_status(crew_id, batch_id, "complete")
                except Exception as exc:  # best-effort; do not fail the pickup
                    logger.warning(
                        "Could not mark batch %s complete: %s",
                        batch_id, exc,
                    )
            return out

        # Snapshot mode (timeout_secs == 0): one query per task, no blocking.
        if capped_timeout == 0:
            return out

        # Admiral-mail early-return: re-read the count and bail if it grew.
        admiral_mail = read_all_mail_counts(podman, container).get("admiral", 0)
        if admiral_mail > initial_admiral_mail:
            out["reason"] = "admiral_mail"
            return out

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            out["reason"] = "timeout"
            return out

        time.sleep(min(_BATCH_POLL_INTERVAL_SECS, remaining))


# ── Task timestamp tracking ──────────────────────────────────────────
# In-memory per-task created/started/completed timestamps. Written by the
# dispatch tools (worker threads) and read-modified-written by the pickup
# handlers (worker threads). Lives here alongside pickup/dispatch; server.py
# imports these names so its dispatch tools share the same objects.
_task_timestamps: dict[str, dict] = {}
# Guards all read-modify-write access to _task_timestamps. The dict is written
# by dispatch (worker thread) and read-modified-written by pickup handlers
# (worker threads); without this lock those accesses race.
_task_timestamps_lock = threading.Lock()


def _record_last_task_at(crew_id: str | None, created_at: str) -> None:
    """Write last_task_at to the crew's registry entry (best-effort)."""
    try:
        with registry:
            if crew_id in registry._reg["crews"]:
                registry._reg["crews"][crew_id]["last_task_at"] = created_at
    except Exception as exc:
        logger.warning("Could not update last_task_at for crew %s: %s", crew_id, exc)


def _dispatch_batch(
    tasks: list[str],
    agent: str,
    crew_id: str | None,
    model: str | None,
    slot: bool | None = None,
) -> dict:
    """Sequentially dispatch a batch of tasks; record a batch entry.

    Validation (size, agent, model) has already run in ``dispatch``. On the
    first CrewUnresponsiveError or unexpected failure the loop breaks and a
    ``partial`` batch is recorded with the task_ids assigned so far.

    ``slot`` follows the same two-mode semantics as single-task dispatch:
    ``None`` (default) routes an enrolled agent to its shared member DM slot and
    an unenrolled agent headless; ``False`` is explicit headless for everyone.
    All tasks in the batch share the one resolved slot (member or headless);
    per-task slot names are not generated.
    """
    # Size validation (task 2.3).
    max_tasks = int(os.environ.get("GA_BATCH_MAX_TASKS", "20"))
    if len(tasks) == 0 or len(tasks) == 1:
        return {"error": "tasks must contain at least 2 items; use task= for a single dispatch"}
    if len(tasks) > max_tasks:
        return {"error": f"tasks exceeds maximum batch size of {max_tasks}"}

    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}

    # Resolve effective slot and shared parent_session using the unified helper.
    # effective_slot is either the agent name (member slot) or None (headless);
    # all tasks in the batch share the one resolved parent_session.
    effective_slot, shared_parent_session = _resolve_dispatch_slot(agent, slot, crew)

    batch_id = str(uuid.uuid4())
    task_ids: list[str] = []
    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    dispatch_error: str | None = None

    for t in tasks:
        body: dict[str, Any] = {"task": t, "agent": agent, "keep": True}
        if model is not None:
            body["model"] = model
        if shared_parent_session is not None:
            body["parent_session"] = shared_parent_session

        try:
            result = _crew_api_with_recovery(
                crew, crew_id, "POST", "/api/spawn", json=body,
            )
        except (CrewUnresponsiveError, RuntimeError, ValueError) as e:
            dispatch_error = str(e)
            break
        tid = result.get("id")
        if not tid:
            dispatch_error = "spawn returned no task id"
            break
        task_ids.append(tid)
        # Per-task timestamp + last_task_at, using this task's response time.
        task_created = datetime.now(timezone.utc).isoformat()
        with _task_timestamps_lock:
            _task_timestamps[tid] = {
                "created_at": task_created,
                "started_at": None,
                "completed_at": None,
            }
        _record_last_task_at(crew_id, task_created)

    # Echo the effective slot: the agent name (member slot) or None (headless).
    response_slot: str | None = effective_slot

    if dispatch_error is None:
        # Task 2.5: full success.
        _write_batch(crew_id, batch_id, task_ids, status="pending", created_at=created_at)
        response: dict[str, Any] = {
            "batch_id": batch_id,
            "task_ids": task_ids,
            "crew_id": crew_id,
            "status": "dispatched",
            "agent": agent,
            "slot": response_slot,
            "created_at": created_at,
        }
        return response

    # Task 2.6: partial failure. Record what was started; surface the error.
    _write_batch(crew_id, batch_id, task_ids, status="partial", created_at=created_at)
    response = {
        "batch_id": batch_id,
        "task_ids": task_ids,
        "crew_id": crew_id,
        "status": "partial",
        "agent": agent,
        "slot": response_slot,
        "created_at": created_at,
        "error": dispatch_error,
    }
    return response


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

        # Populate task timestamps
        now = datetime.now(timezone.utc)
        with _task_timestamps_lock:
            ts = _task_timestamps.get(task_id, {})
            elapsed = r.get("elapsed", 0)
            if ts and elapsed and elapsed > 0 and ts.get("started_at") is None:
                ts["started_at"] = now.isoformat()
            if ts and done and ts.get("completed_at") is None:
                ts["completed_at"] = now.isoformat()
            # Snapshot ts under the lock so the post-lock reads below see a stable
            # copy rather than a live reference that a concurrent _pickup_single
            # or _dispatch_batch could mutate after release.
            ts = dict(ts)

            # Evict completed-task timestamp entries older than TTL so
            # _task_timestamps does not grow without bound over the process life.
            _evict_cutoff = (
                now - timedelta(seconds=_TASK_TIMESTAMP_TTL_SECS)
            ).isoformat()
            _to_evict = [
                k
                for k, v in _task_timestamps.items()
                if v.get("completed_at") is not None and v["completed_at"] < _evict_cutoff
            ]
            for k in _to_evict:
                _task_timestamps.pop(k, None)

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
            "created_at": ts.get("created_at") if ts else None,
            "started_at": ts.get("started_at") if ts else None,
            "completed_at": ts.get("completed_at") if ts else None,
        }

        # Include subject lines for the agent persona, raven, captain, and admiral.
        # captain/admiral come from the single _read_all_mail_subjects exec above
        # (same shape: [{subject, received_at}]). The admiral_mail count above is
        # still used for the reason="admiral_mail" early-return signal.
        if agent_persona:
            out[f"{agent_persona}_subjects"] = mail_subjects.get(agent_persona, [])
        raven_subjects = mail_subjects.get("raven", [])
        if raven_subjects:
            out["raven_subjects"] = raven_subjects
        captain_subjects = mail_subjects.get("captain", [])
        admiral_subjects = mail_subjects.get("admiral", [])
        out["captain_subjects"] = captain_subjects
        out["captain_mail"] = len(captain_subjects)
        out["admiral_subjects"] = admiral_subjects
        out["admiral_mail"] = len(admiral_subjects)

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

        # Snapshot the timestamp entries for the listed agents under the lock,
        # then build the response list from the snapshot so the comprehension
        # does not read _task_timestamps concurrently with writes.
        with _task_timestamps_lock:
            # Evict completed-task timestamp entries older than TTL first
            # (reading _task_timestamps), then snapshot the survivors.
            _evict_cutoff = (
                datetime.now(timezone.utc)
                - timedelta(seconds=_TASK_TIMESTAMP_TTL_SECS)
            ).isoformat()
            _to_evict = [
                k
                for k, v in _task_timestamps.items()
                if v.get("completed_at") is not None and v["completed_at"] < _evict_cutoff
            ]
            for k in _to_evict:
                _task_timestamps.pop(k, None)
            _ts_snapshot = {
                a.get("id", ""): dict(_task_timestamps.get(a.get("id", ""), {}))
                for a in agents
            }

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
                # Include per-task timestamps (null if missing)
                "created_at": _ts_snapshot.get(a.get("id", ""), {}).get("created_at"),
                "started_at": _ts_snapshot.get(a.get("id", ""), {}).get("started_at"),
                "completed_at": _ts_snapshot.get(a.get("id", ""), {}).get("completed_at"),
            }
            for a in agents
        ]

        # Build subject summaries for all persona mailboxes + captain + admiral.
        # captain/admiral come from the single _read_all_mail_subjects exec above.
        subjects_summary: dict[str, list[str]] = {}
        for name in PERSONA_NAMES:
            subs = mail_subjects.get(name, [])
            if subs:
                subjects_summary[f"{name}_subjects"] = subs
        captain_subjects = mail_subjects.get("captain", [])
        admiral_subjects = mail_subjects.get("admiral", [])
        subjects_summary["captain_subjects"] = captain_subjects
        subjects_summary["captain_mail"] = len(captain_subjects)
        subjects_summary["admiral_subjects"] = admiral_subjects
        subjects_summary["admiral_mail"] = len(admiral_subjects)

        out: dict[str, Any] = {
            "crew_id": crew_id,
            "tasks": task_list,
            "mail_summary": mail_summary,
            "agent_subjects": mail_subjects,
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


_cron_activity_since = _monitors._cron_activity_since
_cron_has_enabled_job = _monitors._cron_has_enabled_job

# Inject the runtime functions/constants monitors needs. monitors deliberately
# does not import lifecycle at load time (that would re-create the cycle broken
# here); it declares placeholders and relies on this call. Runs at lifecycle
# import time — before server starts the monitor threads and before any test
# touches monitors.* — so the loops resolve lifecycle's live functions and the
# suite can still patch them via patch.object(monitors, "…").
_monitors.bind_lifecycle(
    ga_idle_timeout_secs=GA_IDLE_TIMEOUT_SECS,
    schedule_monitor_interval=_SCHEDULE_MONITOR_INTERVAL,
    ensure_crew_running=_ensure_crew_running,
    crew_api=_crew_api,
    crew_api_with_recovery=_crew_api_with_recovery,
    mint_cookie=_mint_cookie,
)


# ── Academy validation ────────────────────────────────────────────────────────
# _AGENTS_DIR and _validate_academy() live in transport/academy.py
# and are imported at the top of this module.
