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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx2 as httpx

try:
    from crew_gateway import (
        CrewGatewayClient, CrewUnresponsiveError, _GATEWAY_DETAIL_LIMIT,
        _crew_cookie, _crew_url, _gateway_error_detail, _spawn_backend,
        _unresponsive_error,
    )
except ModuleNotFoundError:
    from .crew_gateway import (
        CrewGatewayClient, CrewUnresponsiveError, _GATEWAY_DETAIL_LIMIT,
        _crew_cookie, _crew_url, _gateway_error_detail, _spawn_backend,
        _unresponsive_error,
    )


try:
    from task_service import TaskService, _resolve_dispatch_slot
except ModuleNotFoundError:
    from .task_service import TaskService, _resolve_dispatch_slot


try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config

try:
    import security as _security  # container: flat /app/
except ModuleNotFoundError:
    from transport import security as _security

try:
    from credentials import CredentialStore  # container: flat /app/
except ImportError:
    from transport.credentials import CredentialStore  # local dev

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
    )
except ModuleNotFoundError:
    from transport.captain import (  # local dev
        _resolve_orders_dir,
    )

try:
    from academy import (  # container: flat /app/
        AcademyLoader,
        COMP_REGISTRY,
        _AGENTS_DIR,
        _CREW_REGISTRY_PATH,
        _load_comp_registry,
        _load_crew_manifest,
        _manifest_selects,
        _resolve_comp,
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
        COMP_REGISTRY,
        _AGENTS_DIR,
        _CREW_REGISTRY_PATH,
        _load_comp_registry,
        _load_crew_manifest,
        _manifest_selects,
        _resolve_comp,
        _resolve_image,
        _resolve_manifest_path,
        _substitute_env_vars,
        _validate_academy,
    )

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
cfg = Config.from_env()

# Credential store — resolved per-launch via store.get(backend) in launcher.py
# (TRN-233 task 2.1). KIRO_API_KEY and the anthropic/openai globals removed.
_cred_store = CredentialStore()

# The reusable kiro-cli auth blob lives under the transport data mount; the
# KIRO_* values drive the interactive `kiro-cli login` device flow in _initiate_login.
DATA_DIR = Path("/data")
GA_AUTH_FILE = "ga-kiro-auth"
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
KC_MODEL_DEFAULT = cfg.kc_model_default
# Per-backend model knobs (TRN-257). Keyed by backend name so the precedence
# chain can be resolved for whichever backend a crew runs on.
_KC_MODEL_BACKEND_OVERRIDE: dict[str, str] = {
    "kiro": cfg.kc_model_kiro_override,
    "claude": cfg.kc_model_claude_override,
    "codex": cfg.kc_model_codex_override,
}
_KC_MODEL_BACKEND_DEFAULT: dict[str, str] = {
    "kiro": cfg.kc_model_kiro_default,
    "claude": cfg.kc_model_claude_default,
    "codex": cfg.kc_model_codex_default,
}


def _resolve_backend_model_override(backend: str) -> str:
    """Per-backend hard override (``backends.<b>.model.override``), or ''.

    Highest operator-controlled precedence level: when set, every agent on this
    backend is forced to the named model regardless of per-agent persona config.
    """
    return _KC_MODEL_BACKEND_OVERRIDE.get(backend, "")


def _resolve_backend_default_model(backend: str) -> str:
    """Resolve the fallback model for a backend when no per-agent model is set.

    Applies the lower half of the TRN-257 precedence chain:
      backends.<b>.model.default > model.default > "" (KiroCrew built-in)
    The caller writes the result as ``agent.model``, or ``auto`` when empty,
    leaving model selection to KiroCrew/the harness when nothing is pinned.
    A persona model still wins over this fallback, as does a per-backend
    override resolved separately.
    """
    return _KC_MODEL_BACKEND_DEFAULT.get(backend, "") or KC_MODEL_DEFAULT
GA_MIN_FREE_MEM_GB = cfg.ga_min_free_mem_gb
GA_START_MEM_ESTIMATE_GB = cfg.ga_start_mem_estimate_gb
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
# Credential globals removed (TRN-233 task 2.1) — launcher.py now calls
# _cred_store.get(backend) at launch time instead of using module-level reads.
ANTHROPIC_BASE_URL = cfg.anthropic_base_url
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

# Per-crew ACP warm markers. Maps crew_id → warmed_at (monotonic seconds)
# recording the last successful prewarm. Guarded by its own lock, mirroring the
# _startup_events_lock / _task_timestamps_lock patterns. The marker is advisory:
# a missed or stale marker at worst causes one extra idempotent warm-up request,
# never real work.
_warm_markers: dict[str, float] = {}
_warm_markers_lock = threading.Lock()

# Warm markers expire after the TTL, which has a one-hour floor.


def _warm_marker_ttl_secs() -> float:
    """Warm-marker TTL: twice the prewarm TTL, with a one-hour floor."""
    return float(max(GA_PREWARM_TTL_SECS * 2 if GA_PREWARM_TTL_SECS > 0 else 3600, 3600))


_SCHEDULE_MONITOR_INTERVAL = 30  # seconds


# ── Comp registry ────────────────────────────────────────────────────────────
# COMP_REGISTRY, _load_comp_registry, _resolve_comp,
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
    except (FileNotFoundError, RuntimeError, OSError):
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
        # H-1 fix: update the in-memory crew dict inside the lock so the
        # registry write and the local reference are both updated atomically.
        # This eliminates the stale-cookie window where the registry is already
        # updated but the caller's local dict still holds the old cookie.
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


# The shared client also serves flat container entry points and local callers
# which import lifecycle without assembling the HTTP application.
_gateway_client = CrewGatewayClient(
    _http,
    refresh_cookie=lambda crew, crew_id: _refresh_cookie(crew, crew_id),
    restore_crew=lambda crew, crew_id: _ensure_crew_running(crew, crew_id),
    removed_crew=_NUKED_DURING_RESTART,
)


def _crew_api(crew: dict, method: str, path: str, **kw: Any) -> Any:
    return _gateway_client.request(crew, method, path, **kw)


def _crew_api_with_recovery(crew: dict, crew_id: str, method: str, path: str, **kw: Any) -> Any:
    return _gateway_client.request_with_recovery(crew, crew_id, method, path, **kw)


def _probe_gateway(crew_url: str) -> bool:
    return _gateway_client.probe(crew_url)


def _get_recovery_lock(crew_id: str) -> threading.Lock:
    return _gateway_client.recovery_lock(crew_id)


def _forget_gateway_crew(crew_id: str) -> None:
    _gateway_client.forget_crew(crew_id)


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
    # best-effort: podman availability is optional here; if unavailable, assume not running
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

    The auth payload is delivered via stdin (not argv) so ``auth_b64`` never
    appears in ``/proc/<pid>/cmdline`` (secret-delivery-hardening spec, TRN-269).
    Returns True if successful.
    """
    podman.container_exec_stdin(
        container,
        ["python3", f"{SCRIPTS_DIR}/inject_auth.py", KIRO_CLI_DB],
        auth_b64.encode("utf-8"),
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
        # best-effort: connection errors during gateway startup are expected; retry until timeout
        except Exception:
            pass
        time.sleep(1.0)
    return False


# _load_crew_manifest, _manifest_selects and _substitute_env_vars live in
# transport/academy.py and are imported at the top of this module.
# _copy_agents/_copy_skills/_copy_steering below call them via the imported names.


def _copy_agents(podman: PodmanClient, container: str, comp_entry: dict | None = None) -> list[str]:
    """Wrapper delegating to AcademyLoader.copy('agents').

    Kept as a one-line wrapper so existing call sites and test patches on
    ``lifecycle._copy_agents`` continue to resolve (TRN-240 task 4.1).
    """
    return AcademyLoader(podman, container, comp_entry).copy("agents")


def _copy_skills(podman: PodmanClient, container: str, comp_entry: dict | None = None) -> list[str]:
    """Wrapper delegating to AcademyLoader.copy('skills')."""
    return AcademyLoader(podman, container, comp_entry).copy("skills")


def _copy_steering(podman: PodmanClient, container: str, comp_entry: dict | None = None) -> list[str]:
    """Wrapper delegating to AcademyLoader.copy('steering')."""
    return AcademyLoader(podman, container, comp_entry).copy("steering")


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


def _patch_models(podman: PodmanClient, container: str, *, backend: str) -> None:
    """Hard-patch all *.json agent files to the per-backend model override.

    TRN-257: the override is now per-backend (``backends.<b>.model.override``),
    resolved for the crew's own ``backend`` (TRN-259).
    When set, it forces every agent on that backend to the named model — the
    highest operator-controlled precedence level (``backend_override``), beaten
    only by a dispatch-time ``model=`` argument. No override set -> no patch.
    """
    model = _resolve_backend_model_override(backend)
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


def _kiro_signin():
    """The kiro sign-in checks module (imported lazily; it imports lifecycle)."""
    try:
        import kiro_signin as m  # container: flat /app/
    except ModuleNotFoundError:
        from transport import kiro_signin as m  # local dev
    return m


def _auth_payload_has_profile(auth_b64: str | bytes) -> bool:
    """True when a captured kiro auth payload carries ``api.codewhisperer.profile``."""
    try:
        payload = json.loads(base64.b64decode(auth_b64).decode())
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    return any(
        len(r) > 1 and r[0] == "api.codewhisperer.profile" and r[1]
        for r in payload.get("state", [])
    )


def _read_auth_from_crew(
    podman: PodmanClient, container: str, profile_wait_retries: int | None = None,
) -> str | None:
    """Read auth rows from a crew container's kiro-cli DB, return as b64 JSON.

    Returns a v2 payload (base64-encoded JSON dict with ``auth_kv`` and
    ``state`` keys) so that kiro-cli 2.37.0's profile-selection requirement is
    satisfied — ``api.codewhisperer.profile`` lives in the ``state`` table and
    must be injected alongside the token rows in ``auth_kv``.

    Uses an inline python one-liner so this works in both crew containers
    (base-admission image, which has /scripts/) and ephemeral login containers
    (bare kirocrew image, which does not).

    Returns None while only the device-flow registration precursor row is
    present — that row exists from the moment the flow *starts*, so it is not
    evidence the user has actually completed the grant.

    Retries up to _PROFILE_WAIT_RETRIES times (1s apart) waiting for
    ``api.codewhisperer.profile`` to be set after the OIDC token lands. For an
    Identity Center login kiro-cli writes it once its profile step completes:
    it picks the default itself or shows "Select an IAM Identity Center
    profile", which the login flow's post-URL prompt answers with Enter.
    If it is still absent after the wait, the v2 payload is returned without
    the state row so the caller is not blocked indefinitely; inject_auth.py
    handles a missing state list gracefully.
    """
    # kiro-cli 2.37.0 requires api.codewhisperer.profile in the state table for
    # ACP token refresh.  Capture it alongside the auth_kv rows so inject_auth.py
    # can write both tables (v2 payload format).
    _PROFILE_WAIT_RETRIES = 30 if profile_wait_retries is None else max(0, profile_wait_retries)
    extract = (
        "import sqlite3, json, base64; "
        f"conn = sqlite3.connect('{KIRO_CLI_DB}'); "
        "auth_kv = conn.execute('SELECT key, value FROM auth_kv').fetchall(); "
        "state = conn.execute(\"SELECT key, value FROM state WHERE key='api.codewhisperer.profile'\").fetchall(); "
        "conn.close(); "
        "payload = {'v': 2, 'auth_kv': auth_kv, 'state': state}; "
        "print(base64.b64encode(json.dumps(payload).encode()).decode())"
    )
    try:
        for attempt in range(_PROFILE_WAIT_RETRIES + 1):
            b64 = podman.container_exec(container, ["python3", "-c", extract]).strip()
            if not b64:
                break
            payload = json.loads(base64.b64decode(b64).decode())
            auth_kv_rows = payload.get("auth_kv", []) if isinstance(payload, dict) else payload
            if not (auth_kv_rows and any(
                r[1] for r in auth_kv_rows if len(r) > 1 and r[0] not in _LOGIN_PRECURSOR_KEYS
            )):
                break  # no token yet — caller will retry
            # Token is present. Wait for the profile to be set too.
            state_rows = payload.get("state", []) if isinstance(payload, dict) else []
            if state_rows or attempt == _PROFILE_WAIT_RETRIES:
                if not state_rows and _PROFILE_WAIT_RETRIES:
                    logger.warning(
                        "Auth capture: api.codewhisperer.profile not set after %ds; "
                        "proceeding without it — re-login may be needed after kiro-cli 2.37+ upgrade",
                        _PROFILE_WAIT_RETRIES,
                    )
                return b64
            logger.debug("Auth capture: profile not yet set, waiting 1s (attempt %d/%d)", attempt + 1, _PROFILE_WAIT_RETRIES)
            time.sleep(1.0)
    except Exception as e:
        logger.warning("Auth read failed: %s", e)
    return None


def _cleanup_crew(podman: PodmanClient, container: str, volume: str, home_volume: str) -> None:
    # Each step is best-effort — a failed launch may mean the container or
    # volumes were never created, so not-found errors are silently ignored.
    # best-effort: container may not exist if launch failed before container creation
    try:
        podman.container_stop(container)
    except Exception:
        pass
    # best-effort: container may not exist if launch failed before container creation
    try:
        podman.container_remove(container)
    except Exception:
        pass
    # best-effort: volume may not exist if launch failed before volume creation
    try:
        podman.volume_remove(volume)
    except Exception:
        pass
    # best-effort: volume may not exist if launch failed before volume creation
    try:
        podman.volume_remove(home_volume)
    except Exception:
        pass
    # Remove the Admiral public-key Podman secret. Podman secrets live in a global
    # namespace and must be explicitly removed or they leak across crew lifecycles.
    # Derive the crew_id from the container name (gs-<crew_id>) so every
    # launch-failure path and the nuke path clean it up. Best-effort — a launch
    # that failed before secret_create just no-ops.
    # best-effort: secret may not exist if launch failed before secret creation
    try:
        if container.startswith(CREW_CONTAINER_PREFIX):
            crew_id = container[len(CREW_CONTAINER_PREFIX):]
            podman.secret_remove(f"admiral-pubkey-{crew_id}")
    except Exception:
        pass


def _cleanup_crew_for_nuke(
    podman: PodmanClient, container: str, volume: str, home_volume: str
) -> list[dict[str, str]]:
    """Remove crew resources for confirmed nuke and return failed removals.

    Stopping is best-effort: force-removal below can still succeed after a stop
    error. PodmanClient treats 404 removal responses as already removed, but
    also recognize them here so callers and test doubles preserve that contract.
    """
    try:
        podman.container_stop(container)
    except Exception:
        pass

    failures: list[dict[str, str]] = []
    removals = (
        (container, "container_remove", podman.container_remove),
        (volume, "volume_remove", podman.volume_remove),
        (home_volume, "volume_remove", podman.volume_remove),
    )
    for resource, operation, remove in removals:
        try:
            remove(resource)
        except Exception as exc:
            response = getattr(exc, "response", None)
            if getattr(response, "status_code", None) == 404:
                continue
            failures.append({
                "resource": resource,
                "operation": operation,
                "error": str(exc) or type(exc).__name__,
            })

    # Keep secret cleanup best-effort just as it is for launch rollback.
    try:
        if container.startswith(CREW_CONTAINER_PREFIX):
            crew_id = container[len(CREW_CONTAINER_PREFIX):]
            podman.secret_remove(f"admiral-pubkey-{crew_id}")
    except Exception:
        pass

    return failures


def _reseed_crew_schedules(crew: dict, crew_id: str, crew_info: dict) -> None:
    """Reconcile tracked jobs with gateway state after a crew becomes available.

    Runs in two passes:

    1. **Reconcile pass** — reads the gateway's current cron state and updates
       the registry to match.  The gateway is the source of truth; the registry
       is a reseed bootstrap cache only.  Any job paused, resumed, or deleted
       inside the container is reflected back into the registry here so that
       subsequent idle-stop checks see the correct enabled state.

    2. **Reseed pass** — for each enabled registry entry that has no matching
       job in the gateway (the true bootstrap case: fresh container, empty
       gateway), re-register it.

    The gateway listing is also fetched when the transport has no tracked
    entries, so gateway-only schedules are observed on the first explicit wake
    after downtime. They remain gateway-owned and keep their existing delivery
    semantics; the transport does not synthesize registry schedules for job
    types it cannot represent.
    """
    try:
        from captain import _captain_jobs  # container: flat /app/
    except ModuleNotFoundError:
        from transport.captain import _captain_jobs  # local dev  # type: ignore[no-redef]

    with registry:
        schedules = registry.get_schedules(crew_id)

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

        # Captain entries are transport-side schedules. The captain monitor
        # wakes and dispatches only when next_fire_at is due; an unrelated wake
        # must not start a future Captain check-in.
        if sched.get("type") == "captain":
            continue

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
    """On startup, reconcile registered crews with Podman without waking them.

    Existing stopped containers remain registered with their schedules,
    workspace volumes, dashboard allocations, and other metadata intact.
    Containers confirmed absent are removed under the existing re-registration
    guard. The login-container sweep is independent of crew recovery.
    """
    # best-effort: podman may be unavailable on startup; reconciliation is skipped, not fatal
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

    try:
        from launcher import _launcher  # container: flat /app/
    except ModuleNotFoundError:
        from transport.launcher import _launcher  # local dev

    # Capture registry state and per-crew startup generations under the same
    # lock order used by the write-back. A wake that starts after this snapshot
    # increments its generation before it can start the container, so stale
    # Podman observations cannot overwrite that newer lifecycle state.
    with _launcher._startup_events_lock:
        startup_in_progress = set(_launcher._startup_events)
        with registry:
            snapshot = dict(registry._reg["crews"])
            snapshot_created_at: dict[str, str | None] = {
                cid: entry.get("created_at") for cid, entry in snapshot.items()
            }
            snapshot_containers: dict[str, str | None] = {
                cid: entry.get("container") for cid, entry in snapshot.items()
            }
            snapshot_generation: dict[str, int] = {
                cid: _launcher._startup_generation.get(cid, 0)
                for cid in snapshot
            }

    to_remove = []
    updates: dict[str, dict] = {}  # cid -> fields to merge back

    for cid, info in snapshot.items():
        if cid in startup_in_progress:
            logger.info("Reconcile: crew %s already has a wake in progress — skipping", cid)
            continue
        container = snapshot_containers[cid]
        if not container:
            logger.warning("Reconcile: crew %s has no container name — skipping", cid)
            continue
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
            desired_status = "running" if running else "stopped"
            if info.get("status") != desired_status:
                logger.info(
                    "Reconcile: correcting crew %s registry status from %r to %s",
                    cid, info.get("status"), desired_status,
                )
            updates[cid] = {"status": desired_status}

    # Apply statuses and guarded removals together. The launcher generation
    # lock closes the observation/write race with _ensure_crew_running; no
    # Podman or gateway operation is performed while either lock is held.
    try:
        with _launcher._startup_events_lock:
            with registry:
                live_crews = registry._reg["crews"]

                def _snapshot_is_current(cid: str, live_entry: dict) -> bool:
                    return (
                        cid not in _launcher._startup_events
                        and _launcher._startup_generation.get(cid, 0)
                        == snapshot_generation.get(cid, 0)
                        and live_entry.get("container") == snapshot_containers.get(cid)
                        and live_entry.get("created_at") == snapshot_created_at.get(cid)
                    )

                for cid in to_remove:
                    # H-2 fix: re-read the live entry and skip deletion if its
                    # created_at differs from the snapshot value. A differing
                    # created_at means the crew was re-registered concurrently
                    # (e.g. a new launch() ran between the snapshot and here).
                    live_entry = live_crews.get(cid)
                    if live_entry is None:
                        continue  # already removed — nothing to do
                    if not _snapshot_is_current(cid, live_entry):
                        logger.info(
                            "Reconcile: skipping deletion of crew %s — "
                            "entry or lifecycle generation changed during inspection", cid,
                        )
                        continue
                    del live_crews[cid]
                for cid, fields in updates.items():
                    live_entry = live_crews.get(cid)
                    if live_entry is None:
                        continue
                    if not _snapshot_is_current(cid, live_entry):
                        logger.info(
                            "Reconcile: skipping status update for crew %s — "
                            "lifecycle state changed during inspection", cid,
                        )
                        continue
                    live_entry.update(fields)
    except Exception as e:
        logger.error(
            "Registry I/O error during reconcile write-back — skipping write to avoid data loss: %s", e
        )
        return
    logger.info("Registry reconciled. Live crews: %s", list(snapshot.keys()))


def _patch_crew_config(
    podman: PodmanClient,
    container: str,
    comp_entry: dict | None = None,
    *,
    backend: str,
) -> None:
    """Patch KiroCrew config while the container is running.

    ``backend`` is the crew's own backend (TRN-259): the launch-time choice, or
    the registry-recorded ``acp_backend`` on restart. It is required so no call
    site silently falls back to the transport default.

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
    # For a claude crew, write acp_backend into the crew config so the gateway
    # routes agent spawns through the Claude Code ACP runtime rather than the
    # kiro-cli runtime.
    if backend == "claude":
        agent_overrides["acp_backend"] = "claude"
    # Codex's enforced permission route relies on KiroCrew's OS credential
    # mask. It cannot run with the legacy unsandboxed defaults above.
    # Require a working backend and refuse an unsandboxed fallback.
    elif backend == "codex":
        agent_overrides["acp_backend"] = "codex"
        agent_overrides["sandbox"] = "auto"
        agent_overrides["sandbox_allow_unsandboxed_exec"] = False
    # KiroCrew consumes agent.model as its global fallback, below persona pins.
    # Always write auto when unset so reapplying config clears an earlier pin.
    agent_overrides["model"] = _resolve_backend_default_model(backend) or "auto"

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
    # Resolve which agents this comp deploys so config.agents entries
    # are generated dynamically rather than hardcoded.
    manifest_agents = _load_crew_manifest(comp_entry).get("agents", "*")

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
        # by the comp manifest — same source _copy_agents uses — so any
        # comp's agents are enrolled, not just a hardcoded list.
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
    comp: str,
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
    # 1. Load template — comp-specific or fallback to default
    policy_template_path = Path(f"/policies/{comp}.json")
    if not policy_template_path.exists():
        policy_template_path = Path("/policies/default.json")
    policy = json.loads(policy_template_path.read_text())
    policy_version = policy.get("version", "1")

    # 2. Add identity block (without signature yet) and pass everything into
    # the container to sign.  Signing runs inside the container so the
    # canonicalization is always the same version as the verifier.
    # The policy + policy_signing_key are sent via stdin (not argv) so the
    # signing key never appears in /proc/<pid>/cmdline (TRN-260/H-1).
    policy["identity"] = {"issuer": "ghostship"}
    payload_b64 = base64.b64encode(
        json.dumps({"policy": policy, "policy_signing_key": policy_signing_key}).encode("utf-8")
    ).decode()

    # Signing runs inside the container (see inject_policy.py).
    result = podman.container_exec_stdin(
        container,
        ["python3", f"{SCRIPTS_DIR}/inject_policy.py", KIRO_CREW_DIR],
        payload_b64.encode("utf-8"),
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
    comp: str = "spec-ops",
    comp_entry: dict | None = None,
    *,
    admiral_secret: str,
    dashboard: bool = False,
    backend: str,
    acp_profile: str = "default",
    credential: dict | None = None,
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
        comp,
        comp_entry,
        admiral_secret=admiral_secret,
        dashboard=dashboard,
        backend=backend,
        acp_profile=acp_profile,
        credential=credential,
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


def _inject_claude_auth(podman: "PodmanClient", container: str, tar_bytes: bytes | None = None) -> None:
    """Inject the ga-claude-auth tar archive into container's ~/.claude/.

    Inject the selected profile archive when supplied. The legacy host-side
    archive is retained only for callers using the implicit default profile.

    Injection strategy (SEC-1): the host-side ga-claude-auth file is already a
    tar of ``~/.claude/``, so its bytes are streamed straight into the container
    via a single ``container_archive_put`` call whose target path untars the
    archive in place.  No base64 encoding, no chunking, no temp file, and no
    ``sh -c`` exec — the credential bytes never pass through a shell, so no
    future non-base64 payload can open a shell-injection surface.
    """
    auth_path = _claude_auth_file_path()
    if tar_bytes is None and not auth_path.is_file():
        raise RuntimeError("ga-claude-auth not found — Claude login required first")

    # Ensure the target directory exists in the container
    podman.container_exec(container, ["mkdir", "-p", "/home/kirocrew/.claude"])

    # The auth file is a tar of ~/.claude/ — hand the raw tar bytes to the
    # archive-put endpoint, which untars them directly at the target path.
    if tar_bytes is None:
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


_LOGIN_OUTPUT_REDACTIONS = (
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4,}\b"), "<code>"),
    (re.compile(r"\b\d{12}\b"), "<acct>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
)


def _redact_login_output(text: str) -> str:
    """Strip URLs, device codes, account ids and emails from login CLI output
    before it is logged for diagnosis."""
    for pattern, repl in _LOGIN_OUTPUT_REDACTIONS:
        text = pattern.sub(repl, text)
    return text


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
    require_code: bool = False,
    post_url_prompts: "list[tuple[re.Pattern, bytes]] | None" = None,
) -> "tuple[str | None, str | None]":
    """Run a PTY select-loop and extract a login URL and optional code.

    When require_code is true, wait for both URL and code before handing
    off to the background drain; an incomplete handoff fails on timeout.

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
    post_url_prompts:
        ``(compiled_pattern, answer_bytes)`` pairs for prompts the CLI shows
        after the URL is handed back (e.g. kiro-cli's Identity Center profile
        selector, shown once the person approves the grant).  The background
        drain answers each at most once, matching against a bounded tail of
        the output so far.
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
                # best-effort: PTY may have closed before the prompt was answered
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
                return not require_code or login_code is not None
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

    if require_code and not login_code:
        login_url = None

    if not login_url:
        # Surface what the CLI printed so a stalled prompt is diagnosable from
        # the transport log alone.
        tail = _strip_terminal_sequences(
            collected.decode("utf-8", errors="replace")
        ).strip()[-500:]
        logger.warning("Login CLI produced no URL; last output: %r", tail)

    if login_url:
        # Hand remaining PTY output to a background daemon thread so the
        # socket drains to EOF without blocking the event loop.
        pty_sock.setblocking(True)
        late_prompts = list(post_url_prompts or [])

        def _drain() -> None:
            # best-effort: PTY drain runs in background; socket errors on EOF are expected and non-fatal
            late_answered: set[int] = set()
            tail = bytearray()
            try:
                while True:
                    chunk = pty_sock.recv(4096)
                    if not chunk:
                        break
                    # Bounded tail: a prompt split across chunks still matches,
                    # the end of the CLI's output can be logged for diagnosis,
                    # and a long-running CLI never grows memory unbounded.
                    tail.extend(chunk)
                    del tail[:-8192]
                    if len(late_answered) == len(late_prompts):
                        continue
                    text = _strip_terminal_sequences(tail.decode("utf-8", errors="replace"))
                    for idx, (pattern, answer) in enumerate(late_prompts):
                        if idx not in late_answered and pattern.search(text):
                            pty_sock.sendall(answer)
                            late_answered.add(idx)
                            logger.info("Login CLI: answered post-URL prompt %r", pattern.pattern)
            except Exception:
                pass
            finally:
                if tail:
                    logger.info(
                        "Login CLI post-URL output (redacted tail): %r",
                        _redact_login_output(
                            _strip_terminal_sequences(tail.decode("utf-8", errors="replace"))
                        )[-600:],
                    )
                try:
                    pty_sock.close()
                # best-effort: socket close in finally; ignore errors if already closed
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


def _initiate_login(
    podman: "PodmanClient", method: str | None = None, provider: dict | None = None,
    profile: str = "default",
) -> dict:
    """Start a device auth flow and return login URL and code.

    *method*/*provider* select builder-id or identity-center; see
    ``KiroLoginFlow.initiate`` for the defaults when they are omitted.

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
    result = KIRO_FLOW.initiate(podman, method=method, provider=provider, profile=profile)
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


def _initiate_claude_login(podman: "PodmanClient", profile: str = "default") -> dict:
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
    result = CLAUDE_FLOW.initiate(podman, profile=profile)
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
        # best-effort: socket may already be closed if the PTY drain thread finished
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


def _inject_codex_auth(podman: "PodmanClient", container: str, tar_bytes: bytes | None = None) -> None:
    """Inject the ga-codex-auth tar archive into container's ~/.codex/.

    Inject the selected profile archive when supplied. The legacy host-side
    archive is retained only for callers using the implicit default profile.

    Injection strategy mirrors _inject_claude_auth (SEC-1): the host-side
    ga-codex-auth file is already a tar of ``~/.codex/``, so its bytes stream
    straight into the container via a single ``container_archive_put`` call that
    untars the archive at the target path.  No base64 encoding, no chunking, no
    temp file, and no ``sh -c`` exec — the credential bytes never pass through a
    shell.
    """
    auth_path = _codex_auth_file_path()
    if tar_bytes is None and not auth_path.is_file():
        raise RuntimeError("ga-codex-auth not found — Codex login required first")

    # Ensure the target directory exists in the container
    podman.container_exec(container, ["mkdir", "-p", "/home/kirocrew/.codex"])

    if tar_bytes is None:
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


def _initiate_codex_login(podman: "PodmanClient", profile: str = "default") -> dict:
    """Start a Codex OAuth/device login flow and return the login URL.

    Mirrors _initiate_claude_login: acquires _codex_login_pending_lock, applies
    TOCTOU-safe guards, starts the ephemeral ga-codex-login-* container from
    KC_IMAGE (spec-ops with the codex toolchain), runs
    ``codex login --device-auth`` via container_exec_pty_stdin, reads the
    45-second PTY stream, extracts the verification URL and optional code,
    and drains the PTY in the background while authentication completes.
    The CLI is the compatible dependency shipped with codex-acp, exposed on
    PATH by the image toolchain; codex-acp itself is an ACP stdio server.

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
    result = CODEX_FLOW.initiate(podman, profile=profile)
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


def _record_last_task_at(crew_id: str | None, created_at: str) -> None:
    """Write last_task_at to the crew's registry entry (best-effort)."""
    try:
        with registry:
            if crew_id in registry._reg["crews"]:
                registry._reg["crews"][crew_id]["last_task_at"] = created_at
    except Exception as exc:
        logger.warning("Could not update last_task_at for crew %s: %s", crew_id, exc)


_task_service = TaskService(
    config=cfg,
    require_crew=_require_crew,
    ensure_running=_ensure_crew_running,
    to_crew=_to_crew,
    validate_agent=_validate_agent,
    call_gateway=_crew_api_with_recovery,
    get_podman=_get_podman,
    sign_in=_kiro_signin,
    record_last_task_at=_record_last_task_at,
)

# Compatibility exports for existing Python callers.
_dispatch_batch = _task_service._dispatch_batch
_pickup_batch = _task_service._pickup_batch
_pickup_single = _task_service._pickup_single
_pickup_list = _task_service._pickup_list
_task_timestamps = _task_service._task_timestamps
_task_timestamps_lock = _task_service._task_timestamps_lock


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
