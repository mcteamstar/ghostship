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
    )

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
KIRO_API_KEY = cfg.kiro_api_key

# The reusable kiro-cli auth blob lives under the transport data mount; the
# KIRO_* values drive the interactive `kiro-cli login` device flow in _initiate_login.
DATA_DIR = Path(cfg.transport_data_dir)
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
GA_CREW_AGENT = cfg.ga_crew_agent
KC_MODEL_OVERRIDE = cfg.kc_model_override
KC_MODEL_DEFAULT = cfg.kc_model_default
GA_MIN_FREE_MEM_GB = cfg.ga_min_free_mem_gb
GA_SPAWN_MIN_MEMORY_GB = cfg.ga_spawn_min_memory_gb
GA_RESOURCE_PRESSURE_GB = cfg.ga_resource_pressure_gb
GA_RESOURCE_CRITICAL_GB = cfg.ga_resource_critical_gb
GA_SUBAGENT_TIMEOUT_SECS = cfg.ga_subagent_timeout_secs
GA_SUBAGENT_MAX_TURNS = cfg.ga_subagent_max_turns
GA_PREWARM_ENABLED = cfg.ga_prewarm_enabled
GA_PREWARM_TTL_SECS = cfg.ga_prewarm_ttl_secs

# ACP backend selection — controls whether kiro, Claude Code, or Codex runs inside crew containers.
# "kiro" (default): kiro-cli auth injection path (existing behaviour).
# "claude": skip kiro auth, inject ANTHROPIC_API_KEY + CLAUDE_CODE_HEADLESS=1.
# "codex": skip kiro auth, inject OPENAI_API_KEY (or the ga-codex-auth archive).
GA_CREW_ACP_BACKEND = cfg.ga_crew_acp_backend
GA_CREW_ANTHROPIC_API_KEY = cfg.ga_crew_anthropic_api_key
GA_CREW_ANTHROPIC_BASE_URL = cfg.ga_crew_anthropic_base_url
GA_INCLUDE_CLAUDE_AGENT = cfg.ga_include_claude_agent
GA_CREW_OPENAI_API_KEY = cfg.ga_crew_openai_api_key
GA_CREW_OPENAI_BASE_URL = cfg.ga_crew_openai_base_url
GA_INCLUDE_CODEX_AGENT = cfg.ga_include_codex_agent

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
# Both TTLs floor at one hour.
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

def _crew_url(crew: dict) -> str:
    return f"http://{crew['container']}:{CREW_GATEWAY_PORT}"


def _crew_cookie(crew: dict) -> str:
    return f"mc_token_{CREW_GATEWAY_PORT}={crew['cookie']}"


def _crew_api(crew: dict, method: str, path: str, **kw: Any) -> Any:
    url = _crew_url(crew)
    r = _http.request(
        method, f"{url}{path}",
        headers={"Cookie": _crew_cookie(crew), "Origin": url},
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


def _refresh_cookie(crew: dict, crew_id: str) -> bool:
    """Re-mint the session cookie and update the registry.

    Returns True on success, False on failure. On success the registry is
    updated with the new cookie value so subsequent calls use it.
    """
    try:
        podman = _get_podman()
    except Exception:
        return False

    crew_url = _crew_url(crew)
    new_cookie = _mint_cookie(podman, crew["container"], crew_url)
    if not new_cookie:
        return False

    with _registry_lock:
        reg = _load_registry()
        if crew_id in reg["crews"]:
            reg["crews"][crew_id]["cookie"] = new_cookie
            _save_registry(reg)

    # Update the in-memory crew dict so the caller can use it immediately
    crew["cookie"] = new_cookie
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
    """
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
    """
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
            # ── Phase 1: stale cookie ─────────────────────────────────────────
            return _phase1_stale_cookie(crew, crew_id, method, path, **kw)

        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError, OSError):
            # ── Phase 2: connection error / dead gateway ──────────────────────
            return _phase2_dead_gateway(crew, crew_id, method, path, **kw)


def _require_crew(crew_id: str | None) -> dict:
    """Return the crew dict or raise a clear error."""
    if not crew_id:
        with _registry_lock:
            reg = _load_registry()
        names = list(reg["crews"].keys())
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
    crew: dict,
    crew_id: str,
    *,
    touch: bool = True,
) -> dict:
    """Ensure a crew container is running, starting it if stopped.

    Uses a per-crew Event to serialise concurrent restart attempts — the
    first caller does the work, subsequent callers wait for it to finish
    then read the refreshed crew dict from the registry.

    The ``touch`` flag controls whether a successful call refreshes the
    crew activity timestamp.

    Returns an updated crew dict (cookie may be refreshed).
    """
    try:
        podman = _get_podman()
    except Exception as e:
        raise RuntimeError(str(e))

    if podman.container_is_running(crew["container"]):
        # Gateway liveness probe: a running container may have a dead gateway
        crew_url = _crew_url(crew)
        if _probe_gateway(crew_url):
            if touch:
                _touch_crew(crew_id)
            return crew
        # Gateway is dead inside a running container — fall through to restart
        logger.info(
            "Crew %s container running but gateway probe failed — restarting",
            crew_id,
        )
        podman.container_stop(crew["container"])

    # Serialise concurrent restarts for this crew
    with _startup_events_lock:
        if crew_id in _startup_events:
            event = _startup_events[crew_id]
            is_leader = False
            # Capture generation before releasing lock
            _waiter_gen = _startup_generation.get(crew_id, 0)
        else:
            event = threading.Event()
            _startup_events[crew_id] = event
            is_leader = True
            # Drop any outcome left by a PRIOR leader for this crew. The outcome
            # map is never popped on completion (its read happens after event.set(),
            # so it cannot be cleared in the leader's finally without racing the
            # waiter), so a stale entry survives between cycles. If we did not clear
            # it, a waiter whose event.wait() times out would read the previous
            # cycle's failure and raise an unrelated exception. Clearing at election
            # makes the map hold at most one entry per crew AND guarantees a
            # timed-out waiter sees None (→ explicit timeout error) rather than a
            # stale outcome.
            _crew_restart_outcomes.pop(crew_id, None)
            # Increment generation for this new restart cycle
            _startup_generation[crew_id] = _startup_generation.get(crew_id, 0) + 1
            _waiter_gen = _startup_generation[crew_id]  # leader also captures (unused but symmetric)

    if not is_leader:
        # Another caller is already restarting — wait for it then return
        # the refreshed crew dict
        logger.info("Crew %s restart already in progress — waiting", crew_id)
        event.wait(timeout=45)
        # Read the outcome the leader recorded before firing the Event. If the
        # leader's restart failed (memory gate, crew limit, gateway timeout, ...),
        # propagate that exact exception instead of reading a stale "running" status
        # and proceeding against a crew that never started. A missing entry means the
        # leader timed out without recording — treat that as a failure too.
        # Check generation under lock before reading outcome.
        with _startup_events_lock:
            outcome = _crew_restart_outcomes.get(crew_id)
            _current_gen = _startup_generation.get(crew_id, 0)
        if _current_gen != _waiter_gen:
            raise RuntimeError(
                f"Crew {crew_id} restart (concurrent) failed -- restart cycle changed "
                f"during wait (waited on gen {_waiter_gen}, current gen {_current_gen}); "
                f"a new restart cycle started before outcome was read"
            )
        if outcome is None:
            raise RuntimeError(
                f"Crew {crew_id} restart (concurrent) failed -- leader did not "
                f"record an outcome within the wait window"
            )
        success, exc = outcome
        if not success:
            raise exc if exc is not None else RuntimeError(
                f"Crew {crew_id} restart (concurrent) failed"
            )
        crew_after = _get_crew(crew_id)
        if crew_after.get("status") in ("stopped", "launching", None):
            raise RuntimeError(
                f"Crew {crew_id} restart (concurrent) failed -- status is still "
                f"{crew_after.get('status')!r}"
            )
        return crew_after

    # We are the leader — do the restart
    # Record a success/failure outcome for waiters before firing the Event.
    # Default to failure so any exit path that is not an explicit success
    # (an exception below) leaves waiters with a failure to propagate.
    _outcome: tuple[bool, Exception | None] = (
        False,
        RuntimeError(f"Crew {crew_id} restart (leader) failed"),
    )
    try:
        logger.info("Crew %s is stopped — restarting", crew_id)

        # Active crew limit: count crews whose container is actually running
        # per Podman, not merely those the registry marks "running".  A stale
        # "running" entry (container stopped externally) must not count toward
        # the limit or block a legitimate restart.  GA_MAX_ACTIVE_CREWS=0
        # disables the check.
        #
        # Pattern (mirrors _reconcile_registry): acquire lock → snapshot →
        # release → probe Podman outside the lock → re-acquire → write back
        # any stale "running"→"stopped" corrections → release, then decide.
        if GA_MAX_ACTIVE_CREWS > 0:
            with _registry_lock:
                reg = _load_registry()
                running_snapshot = [
                    (cid, c.get("container"))
                    for cid, c in reg["crews"].items()
                    if c.get("status") == "running"
                ]

            active = 0
            corrections: list[str] = []
            for cid, container in running_snapshot:
                if container and podman.container_is_running(container):
                    active += 1
                else:
                    # Registered running but not actually running — stale.
                    corrections.append(cid)

            if corrections:
                with _registry_lock:
                    reg = _load_registry()
                    changed = False
                    for cid in corrections:
                        entry = reg["crews"].get(cid)
                        if entry is not None and entry.get("status") == "running":
                            entry["status"] = "stopped"
                            changed = True
                    if changed:
                        _save_registry(reg)
                logger.info(
                    "Active-limit check corrected %d stale running entr%s to stopped: %s",
                    len(corrections),
                    "y" if len(corrections) == 1 else "ies",
                    ", ".join(corrections),
                )

            if active >= GA_MAX_ACTIVE_CREWS:
                raise RuntimeError(
                    f"Active crew limit ({GA_MAX_ACTIVE_CREWS}) reached — "
                    "wait for a running crew to idle out or nuke one first"
                )

        # Pre-launch memory gate: wait for balloon to deflate before starting
        if GA_MIN_FREE_MEM_GB > 0:
            free_gb = _wait_for_memory(podman, GA_MIN_FREE_MEM_GB, 60)
            if free_gb < GA_MIN_FREE_MEM_GB:
                raise RuntimeError(
                    f"Insufficient available memory to start crew {crew_id}: "
                    f"{free_gb}GB free, {GA_MIN_FREE_MEM_GB}GB required. "
                    f"Retry in a moment."
                )

        podman.container_start(crew["container"])
        crew_url = _crew_url(crew)

        # Apply config overrides on every stopped-crew restart, then a single
        # restart cycle so the gateway loads them. KiroCrew 0.4.0 requires a
        # non-empty `agent` field in config.local.json; crew creation fails at
        # the gateway with a 4xx if it is absent. Default "kiro" is KiroCrew's
        # built-in agent name; operators override for a differently-named agent.
        # Note: only _patch_crew_config (a config file write) runs here — no
        # agent JSON files are written on restart, so the 0.4.0 runtime
        # write-protection of the agents directory is not a concern on this path.
        _patch_crew_config(podman, crew["container"])
        podman.container_stop(crew["container"])
        podman.container_start(crew["container"])
        if not _wait_gateway(crew_url, timeout=60):
            raise RuntimeError(f"Gateway did not recover after config re-patch for crew {crew_id}")

        # Refresh cookie (old one may have expired)
        new_cookie = _mint_cookie(podman, crew["container"], crew_url)
        if new_cookie:
            with _registry_lock:
                reg = _load_registry()
                if crew_id in reg["crews"]:
                    reg["crews"][crew_id]["cookie"] = new_cookie
                    reg["crews"][crew_id]["status"] = "running"
                    reg["crews"][crew_id]["last_used"] = time.time()
                    _save_registry(reg)
            crew = {**crew, "cookie": new_cookie}
            logger.info("Crew %s restarted and cookie refreshed", crew_id)
        else:
            logger.warning("Crew %s restarted but cookie refresh failed", crew_id)
            _touch_crew(crew_id)
        _outcome = (True, None)
        return crew
    except Exception as exc:
        # Record the failure so waiters re-raise it instead of proceeding on
        # stale "running" status, then re-raise for our own caller.
        _outcome = (False, exc)
        raise
    finally:
        # Always unblock waiters and clean up, even on error. Publish the
        # outcome BEFORE firing the Event so a waiter that wakes immediately
        # sees it. The outcome entry's lifetime is tied to the event's: both
        # are cleared here once the leader is done (a subsequent leader
        # re-populates them).
        with _startup_events_lock:
            _crew_restart_outcomes[crew_id] = _outcome
            _startup_events.pop(crew_id, None)
        event.set()


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


def _prewarm_crew(crew: dict, crew_id: str) -> dict:
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
    # 2.2: opt-in gate — return early when disabled, before any start/fork.
    if not GA_PREWARM_ENABLED:
        return {"crew_id": crew_id, "status": "disabled"}

    ttl = _effective_prewarm_ttl()

    # 2.3: idempotency — a fresh warm marker on a running container is a no-op.
    try:
        podman = _get_podman()
        container_running = podman.container_is_running(crew["container"])
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


def prewarm(crew_id: str | None) -> dict:
    """Public prewarm entry point shared by the MCP tool and REST endpoint.

    Resolves the crew (2.7: an unknown crew_id returns an error and performs no
    start or fork) then delegates to _prewarm_crew.
    """
    try:
        crew = _require_crew(crew_id)
    except (ValueError, KeyError) as e:
        return {"error": str(e)}
    return _prewarm_crew(crew, crew_id)


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
    """Copy the agent JSONs selected by the crew type's manifest from the
    Academy agents pool (academy/agents/, bind-mounted from the host) into
    the crew container.

    Also writes ~/.kiro/mcp.json from the manifest's mcpServers array, if
    present, by resolving each name against the /mcp catalogue, substituting
    ${VAR} references from the transport environment, and setting
    poolable: false on entries that contain a headers field.
    """
    agents_src = Path("/agents")
    if not agents_src.exists():
        logger.warning("No /agents dir in transport container — skipping agent copy")
        return []
    manifest = _load_crew_manifest(composition_entry)
    selection = manifest["agents"]
    copied = []
    for af in agents_src.glob("*.json"):
        if not _manifest_selects(selection, af.name):
            continue
        try:
            data = af.read_bytes()
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                info = tarfile.TarInfo(name=af.name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            buf.seek(0)
            podman.container_archive_put(container, KIRO_AGENTS_DIR, buf.read())
            copied.append(af.name)
        except Exception as e:
            logger.warning("Failed to copy agent %s: %s", af.name, e)
    logger.info("Copied agents to %s: %s", container, copied)

    # ── Write mcp.json from manifest.mcpServers ───────────────────────────────
    mcp_servers_list = manifest.get("mcpServers")
    if not mcp_servers_list:
        # No mcpServers declared — skip mcp.json creation
        return copied

    env = dict(os.environ)
    resolved_entries: dict[str, Any] = {}

    for server_name in mcp_servers_list:
        catalogue_path = MCP_CATALOGUE_DIR / f"{server_name}.json"
        if not catalogue_path.is_file():
            logger.warning(
                "mcp.json: server %r not found in catalogue at %s — skipping",
                server_name, catalogue_path,
            )
            continue
        try:
            entry = json.loads(catalogue_path.read_text())
        except Exception as e:
            logger.warning(
                "mcp.json: failed to parse catalogue entry %s: %s — skipping",
                catalogue_path, e,
            )
            continue

        # Substitute ${VAR} references from transport environment
        entry = _substitute_env_vars(entry, env)

        # Auto-set poolable: false for entries with a headers field
        if "headers" in entry:
            entry["poolable"] = False

        resolved_entries[server_name] = entry

    if not resolved_entries:
        logger.info("mcp.json: no valid server entries resolved — skipping write")
        return copied

    # Write ~/.kiro/mcp.json into the crew container
    mcp_json_data = json.dumps({"mcpServers": resolved_entries}, indent=2).encode()
    try:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name="mcp.json")
            info.size = len(mcp_json_data)
            tar.addfile(info, io.BytesIO(mcp_json_data))
        buf.seek(0)
        mcp_dest_dir = str(Path(KIRO_MCP_JSON).parent)
        podman.container_archive_put(container, mcp_dest_dir, buf.read())
        logger.info(
            "Wrote mcp.json to %s with servers: %s",
            container, list(resolved_entries.keys()),
        )
    except Exception as e:
        logger.warning("Failed to write mcp.json to %s: %s", container, e)

    return copied


def _copy_skills(podman: PodmanClient, container: str, composition_entry: dict | None = None) -> list[str]:
    """Copy the skill directories selected by the crew type's manifest from
    the Academy skills pool (academy/skills/, bind-mounted from the host)
    into the crew container at ~/.kiro/crew/skills/."""
    skills_src = Path("/skills")
    if not skills_src.exists():
        logger.warning("No /skills dir in transport container — skipping skill copy")
        return []
    selection = _load_crew_manifest(composition_entry)["skills"]
    copied = []
    for skill_dir in skills_src.iterdir():
        if not _manifest_selects(selection, skill_dir.name):
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            data = skill_md.read_bytes()
            dest_dir = f"{KIRO_SKILLS_DIR}/{skill_dir.name}"
            # Ensure the skill subdirectory exists before writing into it.
            podman.container_exec(container, ["mkdir", "-p", dest_dir])
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                info = tarfile.TarInfo(name="SKILL.md")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            buf.seek(0)
            podman.container_archive_put(container, dest_dir, buf.read())
            copied.append(skill_dir.name)
        except Exception as e:
            logger.warning("Failed to copy skill %s: %s", skill_dir.name, e)
    logger.info("Copied skills to %s: %s", container, copied)
    return copied


def _copy_steering(podman: PodmanClient, container: str, composition_entry: dict | None = None) -> list[str]:
    """Copy the steering docs selected by the crew type's manifest from the
    Academy steering pool (academy/steering/, bind-mounted from the host)
    into the crew container at ~/.kiro/steering/ — kiro-cli loads every .md
    file there for every session, regardless of working directory, which is
    what makes this the right place for crew-wide facts every dispatched
    task needs (see academy/steering/STANDING_ORDERS.md for what that
    covers)."""
    steering_src = Path("/steering")
    if not steering_src.exists():
        logger.warning("No /steering dir in transport container — skipping steering copy")
        return []
    selection = _load_crew_manifest(composition_entry)["steering"]
    copied = []
    for doc in steering_src.glob("*.md"):
        if not _manifest_selects(selection, doc.name):
            continue
        try:
            b64 = base64.b64encode(doc.read_bytes()).decode()
            podman.container_exec(container, [
                "python3", f"{SCRIPTS_DIR}/copy_steering.py",
                KIRO_STEERING_DIR, doc.name, b64,
            ])
            copied.append(doc.name)
        except Exception as e:
            logger.warning("Failed to copy steering doc %s: %s", doc.name, e)
    logger.info("Copied steering docs to %s: %s", container, copied)
    return copied


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
            logger.error("Could not parse token from: %s", raw[:200])
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

    with _registry_lock:
        reg = _load_registry()
        schedules = _get_crew_schedules(reg, crew_id)

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
    with _registry_lock:
        reg = _load_registry()
        crew_scheds = _get_crew_schedules(reg, crew_id)
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
            _save_registry(reg)
        # Reload schedules for the reseed pass (may have been mutated above).
        schedules = _get_crew_schedules(reg, crew_id)

    # ── Reseed pass: registry → gateway (bootstrap only) ──────────────────────
    for sched in schedules:
        if not sched.get("enabled", True):
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
                with _registry_lock:
                    reg = _load_registry()
                    crew_scheds = _get_crew_schedules(reg, crew_id)
                    for s in crew_scheds:
                        if s.get("job_id") == job_id:
                            s["job_id"] = new_id
                            break
                    _save_registry(reg)
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
    # Snapshot the registry under the lock, then release it before the
    # per-crew restart loop so the lock is not held across gateway waits
    # (up to 30s each).  Per-crew write-backs re-acquire the lock individually.
    with _registry_lock:
        reg = _load_registry()
        snapshot = dict(reg["crews"])

    to_remove = []
    updates: dict[str, dict] = {}  # cid -> fields to merge back

    for cid, info in snapshot.items():
        container = info["container"]
        if not podman.container_exists(container):
            logger.info("Removing gone crew from registry: %s", cid)
            to_remove.append(cid)
        else:
            if not podman.container_is_running(container):
                # Container exists but stopped (e.g. VM reboot) — restart it
                logger.info("Restarting stopped crew on startup: %s", cid)
                try:
                    podman.container_start(container)
                    crew_url = f"http://{container}:{CREW_GATEWAY_PORT}"
                    # D-07: Apply config overrides before the gateway reads them,
                    # then restart so the gateway loads the patched values.
                    # Must mirror the _ensure_crew_running pattern:
                    #   patch → stop → start → wait
                    # Writing config after _wait_gateway means the gateway has
                    # already loaded config.local.json and will not see the patch
                    # until the next restart.
                    _patch_crew_config(podman, container)
                    podman.container_stop(container)
                    podman.container_start(container)
                    if _wait_gateway(crew_url, timeout=60):
                        new_cookie = _mint_cookie(podman, container, crew_url)
                        updates[cid] = {
                            "status": "running",
                            "last_used": time.time(),
                            **({} if not new_cookie else {"cookie": new_cookie}),
                        }
                        logger.info("Crew %s restored", cid)
                        # Re-seed gateway schedules from registry
                        restored_crew = dict(info)
                        if new_cookie:
                            restored_crew["cookie"] = new_cookie
                        try:
                            _reseed_crew_schedules(restored_crew, cid, info)
                        except Exception as e:
                            logger.warning("Schedule re-seed failed for crew %s: %s", cid, e)
                    else:
                        logger.warning("Crew %s gateway not ready after restart — leaving stopped", cid)
                        updates[cid] = {"status": "stopped"}
                except Exception as e:
                    logger.warning("Could not restart crew %s: %s", cid, e)
                    updates[cid] = {"status": "stopped"}

    # Write all changes back under the lock in one pass
    with _registry_lock:
        reg = _load_registry()
        for cid in to_remove:
            reg["crews"].pop(cid, None)
        for cid, fields in updates.items():
            if cid in reg["crews"]:
                reg["crews"][cid].update(fields)
        _save_registry(reg)
    logger.info("Registry reconciled. Live crews: %s", list(reg["crews"].keys()))


def _patch_crew_config(podman: PodmanClient, container: str) -> None:
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
        # ``sandbox="off"`` disables the kiro-cli inner namespace sandbox.
        # The config key and value are not new — "off" has been valid since
        # before 0.5.0. sandbox="auto" (the default since 0.6.0, and present
        # in fail-closed form since 0.5.0) issues a MS_REMOUNT|MS_BIND|MS_RDONLY
        # mount to seal credential directories read-only; kiro-cli calls
        # sys.exit(rc=1) if that mount fails (fail-closed). Under Podman rootless
        # the kernel denies the remount (errno EPERM — no seccomp allowance for
        # MS_REMOUNT inside a user namespace), so every agent spawn fails with
        # AcpRuntimeDead rc=1 unless this is set to "off".
        # Setting "off" short-circuits detect_backend() to return "none", so the
        # namespace sandbox setup (and the failing mount) are never attempted.
        # The Podman container itself remains the OS-level isolation boundary.
        "sandbox": "off",
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
    """Complete crew setup after auth is confirmed: copy agents, patch, mint cookie."""
    crew_url = f"http://{container}:{CREW_GATEWAY_PORT}"

    # depends on: container running (pre-restart)
    if not _wait_gateway(crew_url, timeout=10):
        podman.container_stop(container)
        podman.container_start(container)
        if not _wait_gateway(crew_url, timeout=60):
            _cleanup_crew(podman, container, volume, home_volume)
            return {"error": f"Gateway did not recover for crew {crew_id}"}

    # depends on: gateway (pre-restart)
    # Backend branch: kiro (default) vs claude.
    #
    # kiro path: inject kiro-cli auth rows into the crew's SQLite DB, unless
    # KIRO_API_KEY is set (API-key path skips the DB injection entirely).
    #
    # claude path: skip all kiro-cli auth injection; ANTHROPIC_API_KEY was
    # already injected as a container env var at container_create time (see
    # launch() in server.py).
    #
    # Headless tool-approval suppression (claude path): KiroCrew's AcpClient
    # writes <work_dir>/.claude/settings.local.json with
    # permissions.defaultMode="bypassPermissions" at session spawn time
    # (_write_claude_local_settings), driven by dangerously_skip_permissions=True
    # already set in _patch_crew_config. No ghostship-side env var injection is
    # needed — the suppression is owned by KiroCrew.
    if GA_CREW_ACP_BACKEND == "claude":
        # Task 3.4: warn at launch time that outbound access is required.
        # Use the override endpoint when set, otherwise api.anthropic.com.
        _effective_endpoint = GA_CREW_ANTHROPIC_BASE_URL or "api.anthropic.com"
        logger.warning(
            "GA_CREW_ACP_BACKEND=claude: crew %s requires outbound access to "
            "%s to function",
            crew_id,
            _effective_endpoint,
        )
        # Task 3.2: API key path (env var injected at container_create) takes
        # precedence over OAuth path. If no API key, inject OAuth credentials
        # from ga-claude-auth into the crew container's ~/.claude/ directory.
        if not GA_CREW_ANTHROPIC_API_KEY and _claude_auth_exists():
            try:
                _inject_claude_auth(podman, container)
            except Exception as e:
                logger.warning(
                    "Claude OAuth auth injection failed for crew %s: %s — crew may be "
                    "unable to authenticate against api.anthropic.com",
                    crew_id, e,
                )
        # If GA_CREW_ANTHROPIC_API_KEY is set, the env var was already injected
        # at container_create time (server.py launch()); nothing more to do here.
        # If neither API key nor ga-claude-auth is present, this path is
        # unreachable: launch() blocks before reaching _finish_crew_setup
        # when no Claude credential is available (task 3.3).
    elif GA_CREW_ACP_BACKEND == "codex":
        # codex path: skip all kiro-cli auth injection. OPENAI_API_KEY and
        # OPENAI_BASE_URL were already injected as container env vars at
        # container_create time (see launch() in server.py). codex-acp
        # advertises a verified read-only mode, so no ghostship-side
        # approval-suppression env var is needed (see crew-governance).
        #
        # Task 3.5: warn at launch time that outbound access to the effective
        # OpenAI endpoint is required. Use GA_CREW_OPENAI_BASE_URL when set,
        # otherwise api.openai.com.
        _effective_endpoint = GA_CREW_OPENAI_BASE_URL or "api.openai.com"
        logger.warning(
            "GA_CREW_ACP_BACKEND=codex: crew %s requires outbound access to "
            "%s to function",
            crew_id,
            _effective_endpoint,
        )
        # Task 3.3: API key path (OPENAI_API_KEY env var injected at
        # container_create) takes precedence over OAuth path. If no API key,
        # inject OAuth credentials from ga-codex-auth into the crew container's
        # ~/.codex/ directory (the path codex-acp reads).
        if not GA_CREW_OPENAI_API_KEY and _codex_auth_exists():
            try:
                _inject_codex_auth(podman, container)
            except Exception as e:
                logger.warning(
                    "Codex OAuth auth injection failed for crew %s: %s — crew may be "
                    "unable to authenticate against api.openai.com",
                    crew_id, e,
                )
        # If GA_CREW_OPENAI_API_KEY is set, the env var was already injected
        # at container_create time (server.py launch()); nothing more to do here.
        # If neither API key nor ga-codex-auth is present, this path is
        # unreachable: launch() blocks before reaching _finish_crew_setup
        # when no Codex credential is available (task 3.3).
    else:
        # kiro path: inject auth rows (or skip when KIRO_API_KEY is set).
        if not KIRO_API_KEY:
            _inject_auth(podman, container, auth_b64)

    # depends on: container running (pre-restart); must be written before restart
    # so the secret is on the home volume before the post-restart gateway starts
    #
    # The Admiral keypair is generated in server.py before container_create —
    # the private seed (``admiral_secret``, hex-encoded) has
    # already been persisted host-side via _write_crew_secret, and the public
    # key is mounted read-only as a Podman secret at .admiral_public_key. There
    # is no longer a container-exec injection step for the Admiral key; only the
    # policy signing key is generated and injected here.
    policy_signing_key = secrets.token_hex(32)

    # depends on: gateway (pre-restart); gateway seeds config on first start
    _patch_crew_config(podman, container)

    # depends on: auth + admiral_secret + config all committed before workers start
    podman.container_stop(container)
    podman.container_start(container)
    if not _wait_gateway(crew_url, timeout=60):
        _cleanup_crew(podman, container, volume, home_volume)
        return {"error": f"Gateway did not recover after auth restart for crew {crew_id}"}

    # depends on: gateway (post-restart)
    _copy_agents(podman, container, composition_entry)
    # depends on: gateway (post-restart)
    _copy_skills(podman, container, composition_entry)
    # depends on: gateway (post-restart)
    _copy_steering(podman, container, composition_entry)
    # depends on: gateway (post-restart)
    _seed_openspec_store(podman, container)

    # depends on: policy_signing_key (already generated above), filesystem
    policy_version = None
    policy_warning: str | None = None
    try:
        policy_version = _inject_policy(podman, container, composition, policy_signing_key)
    except Exception as e:
        policy_warning = str(e)
        logger.error("Policy injection failed for %s: %s — continuing without policy", container, e)

    # depends on: gateway (post-restart); poll until gateway writes built-in kirocrew*.json files before patching
    for _ in range(20):
        check = podman.container_exec(container, [
            "python3", f"{SCRIPTS_DIR}/check_gateway_ready.py", KIRO_AGENTS_DIR,
        ])
        if "ready" in check:
            break
        time.sleep(0.5)

    # depends on: gateway (post-restart), agent files present
    _patch_models(podman, container)

    # depends on: gateway (post-restart), fully configured
    cookie = _mint_cookie(podman, container, crew_url)
    if not cookie:
        _cleanup_crew(podman, container, volume, home_volume)
        return {"error": f"Failed to mint session cookie for crew {crew_id}"}

    # Read crew image version from OCI label
    crew_image_version = "unknown"
    try:
        inspect_data = podman.container_inspect(container)
        labels = inspect_data.get("Config", {}).get("Labels", {})
        crew_image_version = labels.get("org.ghostship.version", "unknown")
    except Exception as e:
        logger.warning("Could not read version label from %s: %s", container, e)

    with _registry_lock:
        reg = _load_registry()
        crew_entry = {
            "container": container,
            "volume": volume,
            "home_volume": home_volume,
            "port": 5476,
            "cookie": cookie,
            "status": "running",
            "composition": composition,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used": time.time(),
            # Store non-reversible identifiers only — plaintext secrets are not
            # needed after injection and must not persist in crews.json.
            "admiral_secret_id": _secret_identifier(admiral_secret),
            "crew_image_version": crew_image_version,
            # ACP backend used for this crew — "kiro" (default) or "claude".
            # Persisted so crews() can surface it per crew without re-reading config.
            "acp_backend": GA_CREW_ACP_BACKEND,
        }
        if policy_version is not None:
            crew_entry["policy_version"] = policy_version
            crew_entry["policy_signing_key_id"] = _secret_identifier(policy_signing_key)
        reg["crews"][crew_id] = crew_entry
        _save_registry(reg)

    logger.info("Crew %s ready", crew_id)
    result = {
        "crew_id": crew_id,
        "container": container,
        "gateway_url": crew_url,
        "status": "ready",
    }
    if policy_version is not None:
        result["policy_version"] = policy_version
    if policy_warning is not None:
        result["policy_warning"] = f"Policy injection failed — crew is ungoverned: {policy_warning}"

    # ── ACP prewarm ─────────────────────────────────────────────────
    # Fire-and-report: non-fatal. AcpProcessDied on the prewarm is acceptable —
    # it still expands the balloon. Errors are logged but never bubble up to the
    # caller so launch always succeeds even if prewarm fails.
    if GA_PREWARM_ENABLED:
        try:
            pw = _prewarm_crew(crew_entry, crew_id)
            if pw.get("pre_warm_task_id"):
                result["pre_warm_task_id"] = pw["pre_warm_task_id"]
            result["pre_warm_status"] = pw.get("status", "unknown")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Crew %s prewarm failed (non-fatal): %s", crew_id, exc)
            result["pre_warm_status"] = "error"

    return result


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
    token = secrets.token_hex(8)
    name = f"{GA_LOGIN_CONTAINER_PREFIX}{token}"
    podman.network_create(GA_STARBOARD_NETWORK)
    podman._req("POST", "/libpod/containers/create", json={
        "name": name,
        "image": cfg.kc_base_image,
        "netns": {"nsmode": "bridge"},
        "Networks": {GA_STARBOARD_NETWORK: {}},
        # Use the default gateway command — kirocrew-entrypoint seeds
        # ~/.kiro/crew/config.json which kiro-cli requires. The gateway will
        # stall on AcpAuthRequired (no auth yet) and the loop watchdog will
        # recycle it after a timeout, but GET /login polls the auth DB
        # continuously and will catch a completed auth before that window.
        # No volumes — ephemeral writable layer only
    })
    podman.container_start(name)
    logger.info("Started ephemeral login container %s", name)
    return name


def _nuke_login_container(podman: PodmanClient, name: str) -> None:
    """Best-effort stop and remove a ga-login-* container."""
    if not name.startswith(GA_LOGIN_CONTAINER_PREFIX):
        raise RuntimeError(f"Refusing to nuke non-login container: {name!r}")
    try:
        podman.container_stop(name)
    except Exception:
        pass
    try:
        podman.container_remove(name)
    except Exception:
        pass
    logger.info("Nuked login container %s", name)


# ── Claude login container helpers ────────────────────────────────────────────


def _start_claude_login_container(podman: PodmanClient) -> str:
    """Create and start an ephemeral ga-claude-login-<token> container.

    Uses KC_IMAGE (the local spec-ops image built with INCLUDE_CLAUDE_AGENT=true)
    because the ``claude`` CLI is only present in that image.  Fails with a clear
    error if the image is not found or does not have ``claude`` installed.
    Returns the container name.
    """
    # Verify the spec-ops image has `claude` available before starting.
    # We do a quick inspection check; the actual binary check happens after
    # container start in _initiate_claude_login.
    token = secrets.token_hex(8)
    name = f"{GA_CLAUDE_LOGIN_CONTAINER_PREFIX}{token}"
    podman.network_create(GA_STARBOARD_NETWORK)
    try:
        podman._req("POST", "/libpod/containers/create", json={
            "name": name,
            "image": KC_IMAGE,
            "netns": {"nsmode": "bridge"},
            "Networks": {GA_STARBOARD_NETWORK: {}},
            # No volumes — ephemeral writable layer only.
            # The container runs the gateway entrypoint like the kiro login
            # container, which seeds ~/.kiro/crew/config.json. The gateway
            # will stall on AcpAuthRequired but that's fine — we only need
            # the container running long enough to exec `claude auth login`.
        })
    except Exception as e:
        raise RuntimeError(
            f"Failed to create Claude login container from image {KC_IMAGE!r}: {e}. "
            "Ensure the spec-ops image was built with GA_INCLUDE_CLAUDE_AGENT=true."
        ) from e
    podman.container_start(name)
    logger.info("Started ephemeral Claude login container %s", name)
    return name


def _nuke_claude_login_container(podman: PodmanClient, name: str) -> None:
    """Best-effort stop and remove a ga-claude-login-* container."""
    if not name.startswith(GA_CLAUDE_LOGIN_CONTAINER_PREFIX):
        raise RuntimeError(f"Refusing to nuke non-Claude-login container: {name!r}")
    try:
        podman.container_stop(name)
    except Exception:
        pass
    try:
        podman.container_remove(name)
    except Exception:
        pass
    logger.info("Nuked Claude login container %s", name)


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
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        f = os.fdopen(fd, "w")
        fd = -1
        with f:
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
    finally:
        if fd != -1:
            os.close(fd)
    os.chmod(path, 0o600)


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
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        f = os.fdopen(fd, "wb")
        fd = -1
        with f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    finally:
        if fd != -1:
            os.close(fd)
    os.chmod(path, 0o600)


def _inject_claude_auth(podman: "PodmanClient", container: str) -> None:
    """Inject the ga-claude-auth tar archive into container's ~/.claude/.

    Reads the host-side ga-claude-auth file (a tar of ~/.claude/) and untars it
    into /home/kirocrew/.claude/ inside the crew container, matching the path
    that the claude-agent-acp server reads for OAuth credentials.

    Injection strategy: split the base64-encoded archive into fixed-width lines
    and write each line via a separate container_exec echo, then pipe the
    assembled file through ``base64 -d | tar -xf -``.  This avoids both the
    ARG_MAX ceiling (Linux typically ~2 MB per argv entry) and any shell quoting
    issues that arise from embedding the raw base64 string in an f-string passed
    to ``sh -c``.
    """
    import base64 as _b64
    auth_path = _claude_auth_file_path()
    if not auth_path.is_file():
        raise RuntimeError("ga-claude-auth not found — Claude login required first")

    # Ensure the target directory exists in the container
    podman.container_exec(container, ["mkdir", "-p", "/home/kirocrew/.claude"])

    # Encode the archive and write it in chunks to a temp file inside the
    # container, then decode and untar.  Each chunk is a small, safe exec.
    tar_bytes = auth_path.read_bytes()
    tar_b64 = _b64.b64encode(tar_bytes).decode()

    # Write base64 in 4 KB chunks using echo >> to a temp file.
    # 4 KB is well under any reasonable ARG_MAX.
    CHUNK = 4096
    tmp = "/tmp/_ga_claude_auth.b64"
    # Start fresh (truncate)
    podman.container_exec(container, ["sh", "-c", f"> {tmp}"])
    for i in range(0, len(tar_b64), CHUNK):
        chunk = tar_b64[i : i + CHUNK]
        # printf is used here to avoid echo interpreting backslashes; the chunk
        # contains only base64 alphabet characters [A-Za-z0-9+/=] so no quoting
        # or shell-injection is possible.
        podman.container_exec(container, ["sh", "-c", f"printf '%s' '{chunk}' >> {tmp}"])

    # Decode and untar, then remove the temp file
    podman.container_exec(
        container,
        ["sh", "-c", f"base64 -d < {tmp} | tar -xf - -C /home/kirocrew/.claude/ && rm -f {tmp}"],
    )
    logger.info("Injected Claude OAuth credentials into crew container %s", container)


# ── Shared PTY login helper ──────────────────────────────────────────────────


def _run_pty_login_flow(
    pty_sock: "socket.socket",
    prompt_patterns: "list[tuple[re.Pattern, bytes]]",
    url_patterns: "list[re.Pattern]",
    code_pattern: "re.Pattern | None",
    deadline_secs: float = 45.0,
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
    """
    deadline = time.time() + deadline_secs
    collected = bytearray()
    login_url: str | None = None
    login_code: str | None = None
    answered: set[int] = set()  # indices into prompt_patterns already sent

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

                for idx, (pattern, answer) in enumerate(prompt_patterns):
                    if idx in answered:
                        continue
                    if pattern.search(text):
                        try:
                            pty_sock.sendall(answer)
                        except Exception:
                            pass
                        answered.add(idx)

                for pat in url_patterns:
                    m = pat.search(text)
                    if m:
                        login_url = (m.group(1) if m.lastindex else m.group(0)).rstrip(").,")
                        if code_pattern:
                            cm = code_pattern.search(login_url) or code_pattern.search(text)
                            if cm:
                                login_code = cm.group(1)
                        break
                if login_url:
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
    global _login_pending
    # ── Phase: acquire lock / TOCTOU guard ───────────────────────────────────
    # _login_pending_lock serialises concurrent callers: the first one through
    # sets the sentinel immediately before releasing the lock, so any race
    # between "is flow pending?" and "start a flow" is eliminated.
    with _login_pending_lock:
        if _login_pending is not None:
            return {"login_pending": True}
        # Set lightweight sentinel immediately to prevent concurrent starts
        _login_pending = {
            "container": None,
            "started_at": time.time(),
            "state": "starting",
        }

    # ── Phase: start login container ──────────────────────────────────────────
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

    # ── Phase: wait for kiro-cli ───────────────────────────────────────────────
    for _ in range(10):
        try:
            check = podman.container_exec(container, ["which", "kiro-cli"])
            if "kiro-cli" in check:
                break
        except Exception:
            pass
        time.sleep(0.5)

    # ── Phase: PTY exec + prompt loop ─────────────────────────────────────────
    # kiro-cli ignores --identity-provider / --region flags in interactive/PTY
    # mode (upstream bug kiro#6120). Use a raw-socket exec so we can write
    # stdin answers to the interactive prompts automatically.
    # With --license pro the provider-selection menu is skipped; kiro-cli goes
    # straight to Start URL → Region, then makes a network round-trip to AWS
    # to register the device (which takes a few seconds) before printing the
    # URL.
    #
    # Deadline is 45 seconds to accommodate the AWS IAM Identity Center
    # round-trip that happens after the user answers the Region prompt.  The
    # device-registration call can take several seconds on a warm network; 45s
    # gives comfortable headroom without leaving users waiting indefinitely on
    # a failed flow.
    #
    # The read loop uses select() rather than a blocking recv() so it can poll
    # for the URL without blocking the event loop thread.  PTY sockets are set
    # non-blocking; select() with a 0.1s timeout yields control between chunks
    # so the outer deadline check and prompt-matching logic run frequently.
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

    # ── Phase: PTY read loop ───────────────────────────────────────────────────
    # Prompt patterns for the kiro-cli interactive device flow.
    # Each tuple is (compiled_regex, answer_bytes); patterns are answered in
    # order and at most once.  The Select-login-method menu is answered with a
    # bare newline to accept the highlighted Builder-ID default; Start URL and
    # Region answers come from the KIRO_* env vars.
    # NOTE: the Select-login-method guard (skip if Start URL already seen) that
    # the old inline loop used is intentionally omitted here — in practice the
    # menu always appears before the Start URL prompt, and the helper answers
    # each pattern at most once, so double-answering cannot happen.
    kiro_prompt_patterns = [
        (re.compile(r"Select login method"), b"\n"),
        (re.compile(r"Start URL"), (KIRO_IDENTITY_PROVIDER.rstrip("/") + "/\n").encode()),
        (re.compile(r"Region"), (KIRO_REGION + "\n").encode()),
    ]
    kiro_url_patterns = [
        re.compile(r"Open this URL[:\s]+(https?://\S+)"),
        re.compile(r"(https?://\S+user_code=\S+)"),
    ]
    # Primary code extraction: user_code= query param in the URL.
    # Fallback: a "Code: XXXX" line that appears before the URL in the output.
    _kiro_code_re = re.compile(r"user_code=([A-Z0-9-]{4,})")
    _kiro_code_re2 = re.compile(r"[Cc]ode[:\s]+([A-Z0-9-]{4,})")

    login_url, login_code = _run_pty_login_flow(
        pty_sock=pty_sock,
        prompt_patterns=kiro_prompt_patterns,
        url_patterns=kiro_url_patterns,
        code_pattern=_kiro_code_re,
        deadline_secs=45.0,
    )
    # Fallback: if user_code= wasn't in the URL, try the "Code: NNN" pattern
    # against the URL string itself (rare, but matches the original behaviour).
    if login_url and not login_code:
        cm2 = _kiro_code_re2.search(login_url)
        if cm2:
            login_code = cm2.group(1)

    if not login_url:
        try:
            pty_sock.close()
        except Exception:
            pass
        _nuke_login_container(podman, container)
        with _login_pending_lock:
            _login_pending = None
        return {"error": "kiro-cli did not produce a login URL within 45s."}

    # ── Phase: finalise ────────────────────────────────────────────────────────
    # Drain thread already started by _run_pty_login_flow.
    with _login_pending_lock:
        if _login_pending is not None:
            _login_pending["exec_id"] = exec_id

    logger.info("Login flow started in %s, URL extracted", container)
    return {"login_url": login_url, "code": login_code}



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
    KC_IMAGE (spec-ops with INCLUDE_CLAUDE_AGENT=true), runs ``claude auth login``
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
    global _claude_login_pending
    # ── Phase: acquire lock / TOCTOU guard ───────────────────────────────────
    with _claude_login_pending_lock:
        if _claude_login_pending is not None:
            return {"login_pending": True}
        # Lightweight sentinel to prevent concurrent starts
        _claude_login_pending = {
            "container": None,
            "started_at": time.time(),
            "state": "starting",
        }

    # ── Phase: start Claude login container ──────────────────────────────────
    try:
        container = _start_claude_login_container(podman)
    except Exception as e:
        logger.error("Failed to start Claude login container: %s", e)
        with _claude_login_pending_lock:
            _claude_login_pending = None
        return {"error": str(e)}

    # Update sentinel with real container name
    with _claude_login_pending_lock:
        _claude_login_pending = {
            "container": container,
            "started_at": _claude_login_pending["started_at"] if _claude_login_pending else time.time(),
            "state": "started",
        }

    # ── Phase: wait for claude CLI ────────────────────────────────────────────
    # Poll briefly for the claude binary to be accessible in the container.
    for _ in range(10):
        try:
            check = podman.container_exec(container, ["which", "claude"])
            if "claude" in check:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        _nuke_claude_login_container(podman, container)
        with _claude_login_pending_lock:
            _claude_login_pending = None
        return {
            "error": (
                f"'claude' CLI not found in image {KC_IMAGE!r}. "
                "Ensure the spec-ops image was built with GA_INCLUDE_CLAUDE_AGENT=true."
            )
        }

    # ── Phase: PTY exec ───────────────────────────────────────────────────────
    # claude auth login opens a browser-based device-code flow and prints a URL.
    # PTY URL extraction note (task 1.2): the URL pattern for claude auth login
    # is one of:
    #   "Open the following URL in your browser: https://..."
    #   "https://claude.ai/..." or "https://console.anthropic.com/..."
    # We match with re.search(r'https?://\S+', text) and accept the first URL
    # that looks like an Anthropic/Claude auth URL. A generic fallback accepts
    # any https:// URL if no more specific match is found within 45 seconds.
    cmd = ["claude", "auth", "login"]
    try:
        exec_id, pty_sock = podman.container_exec_pty_stdin(container, cmd)
    except Exception as e:
        _nuke_claude_login_container(podman, container)
        with _claude_login_pending_lock:
            _claude_login_pending = None
        return {"error": f"Failed to start claude auth login: {e}"}

    pty_sock.setblocking(False)

    # ── Phase: PTY read loop ──────────────────────────────────────────────────
    # Prompt patterns: answer a "Continue?" / "Yes/No" / bare "?" prompt with
    # a newline.  URL patterns: Anthropic/Claude auth URLs first, then generic.
    claude_prompt_patterns = [
        (re.compile(r"\?\s*$", re.MULTILINE), b"\n"),
    ]
    claude_url_patterns = [
        re.compile(
            r"https?://(?:claude\.ai|console\.anthropic\.com|auth\.anthropic\.com)\S*"
        ),
        re.compile(r"(?:URL|browser)[:\s]+(https?://\S+)", re.IGNORECASE),
        re.compile(r"(https?://\S{20,})"),
    ]
    claude_code_pattern = re.compile(r"[?&]code=([A-Za-z0-9_-]+)")

    login_url, login_code = _run_pty_login_flow(
        pty_sock=pty_sock,
        prompt_patterns=claude_prompt_patterns,
        url_patterns=claude_url_patterns,
        code_pattern=claude_code_pattern,
        deadline_secs=45.0,
    )

    if not login_url:
        try:
            pty_sock.close()
        except Exception:
            pass
        _nuke_claude_login_container(podman, container)
        with _claude_login_pending_lock:
            _claude_login_pending = None
        return {
            "error": "claude auth login did not produce a login URL within 45s."
        }

    # ── Phase: finalise ────────────────────────────────────────────────────────
    # Drain thread already started by _run_pty_login_flow.
    with _claude_login_pending_lock:
        if _claude_login_pending is not None:
            _claude_login_pending["exec_id"] = exec_id

    logger.info("Claude login flow started in %s, URL extracted", container)
    return {"login_url": login_url, "code": login_code}



def _poll_claude_login_container(podman: "PodmanClient", container: str) -> bytes | None:
    """Poll container for completed ~/.claude/ credentials.

    Checks whether ~/.claude/ inside the container contains a non-empty
    credentials file. If present, tars the entire ~/.claude/ directory and
    returns the raw tar bytes. Returns None if credentials are not yet present.

    On completion (task 1.5): the caller writes the tar to ga-claude-auth
    (mode 0600) and nukes the login container.
    """
    try:
        # Check for any file in ~/.claude/ with content
        result = podman.container_exec(
            container,
            ["sh", "-c", "find /home/kirocrew/.claude/ -type f -size +0 2>/dev/null | head -1"],
        )
        if not result or not result.strip():
            return None
        # Tar ~/.claude/ inside the container and retrieve the archive via base64.
        # container_exec returns stdout as a string, so base64 is the transport.
        # Note: the dead _req("POST", ".../export") call that was here before was
        # removed (TRN-170 Banshee fix F1) — it was never consumed and would
        # silently fail on large archives; the exec+base64 path is the only path.
        import base64 as _b64
        tar_b64_result = podman.container_exec(
            container,
            ["sh", "-c", "tar -cf - -C /home/kirocrew/.claude/ . 2>/dev/null | base64"],
        )
        if tar_b64_result and tar_b64_result.strip():
            return _b64.b64decode(tar_b64_result.strip())
    except Exception as e:
        logger.warning("Error polling Claude login container: %s", e)
    return None


# ── Codex login container helpers ─────────────────────────────────────────────


def _start_codex_login_container(podman: PodmanClient) -> str:
    """Create and start an ephemeral ga-codex-login-<token> container.

    Uses KC_IMAGE (the local spec-ops image built with INCLUDE_CODEX_AGENT=true)
    because the ``codex-acp`` adapter is only present in that image. Fails with a
    clear error naming GA_INCLUDE_CODEX_AGENT=true if the image cannot start.
    The actual adapter-binary check happens after start in _initiate_codex_login.
    Returns the container name.
    """
    token = secrets.token_hex(8)
    name = f"{GA_CODEX_LOGIN_CONTAINER_PREFIX}{token}"
    podman.network_create(GA_STARBOARD_NETWORK)
    try:
        podman._req("POST", "/libpod/containers/create", json={
            "name": name,
            "image": KC_IMAGE,
            "netns": {"nsmode": "bridge"},
            "Networks": {GA_STARBOARD_NETWORK: {}},
            # No volumes — ephemeral writable layer only. The container runs the
            # gateway entrypoint like the kiro/claude login containers; the
            # gateway stalls on AcpAuthRequired but that's fine — we only need
            # the container running long enough to exec the codex login flow.
        })
    except Exception as e:
        raise RuntimeError(
            f"Failed to create Codex login container from image {KC_IMAGE!r}: {e}. "
            "Ensure the spec-ops image was built with GA_INCLUDE_CODEX_AGENT=true."
        ) from e
    podman.container_start(name)
    logger.info("Started ephemeral Codex login container %s", name)
    return name


def _nuke_codex_login_container(podman: PodmanClient, name: str) -> None:
    """Best-effort stop and remove a ga-codex-login-* container."""
    if not name.startswith(GA_CODEX_LOGIN_CONTAINER_PREFIX):
        raise RuntimeError(f"Refusing to nuke non-Codex-login container: {name!r}")
    try:
        podman.container_stop(name)
    except Exception:
        pass
    try:
        podman.container_remove(name)
    except Exception:
        pass
    logger.info("Nuked Codex login container %s", name)


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
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        f = os.fdopen(fd, "wb")
        fd = -1
        with f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    finally:
        if fd != -1:
            os.close(fd)
    os.chmod(path, 0o600)


def _inject_codex_auth(podman: "PodmanClient", container: str) -> None:
    """Inject the ga-codex-auth tar archive into container's ~/.codex/.

    Reads the host-side ga-codex-auth file (a tar of ~/.codex/, holding
    auth.json) and untars it into /home/kirocrew/.codex/ inside the crew
    container, matching the path that codex-acp reads for OAuth credentials
    (relocatable via CODEX_HOME, but ghostship uses the default location).

    Injection strategy mirrors _inject_claude_auth: split the base64-encoded
    archive into fixed-width lines written via separate container_exec calls to
    stay under ARG_MAX, then pipe the assembled file through
    ``base64 -d | tar -xf -``. The chunk alphabet is base64 [A-Za-z0-9+/=] only,
    so no shell quoting/injection is possible.
    """
    import base64 as _b64
    auth_path = _codex_auth_file_path()
    if not auth_path.is_file():
        raise RuntimeError("ga-codex-auth not found — Codex login required first")

    # Ensure the target directory exists in the container
    podman.container_exec(container, ["mkdir", "-p", "/home/kirocrew/.codex"])

    tar_bytes = auth_path.read_bytes()
    tar_b64 = _b64.b64encode(tar_bytes).decode()

    CHUNK = 4096
    tmp = "/tmp/_ga_codex_auth.b64"
    podman.container_exec(container, ["sh", "-c", f"> {tmp}"])
    for i in range(0, len(tar_b64), CHUNK):
        chunk = tar_b64[i : i + CHUNK]
        podman.container_exec(container, ["sh", "-c", f"printf '%s' '{chunk}' >> {tmp}"])

    podman.container_exec(
        container,
        ["sh", "-c", f"base64 -d < {tmp} | tar -xf - -C /home/kirocrew/.codex/ && rm -f {tmp}"],
    )
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
    KC_IMAGE (spec-ops with INCLUDE_CODEX_AGENT=true), runs the codex-acp login
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
    global _codex_login_pending
    # ── Phase: acquire lock / TOCTOU guard ───────────────────────────────────
    with _codex_login_pending_lock:
        if _codex_login_pending is not None:
            return {"login_pending": True}
        _codex_login_pending = {
            "container": None,
            "started_at": time.time(),
            "state": "starting",
        }

    # ── Phase: start Codex login container ────────────────────────────────────
    try:
        container = _start_codex_login_container(podman)
    except Exception as e:
        logger.error("Failed to start Codex login container: %s", e)
        with _codex_login_pending_lock:
            _codex_login_pending = None
        return {"error": str(e)}

    with _codex_login_pending_lock:
        _codex_login_pending = {
            "container": container,
            "started_at": _codex_login_pending["started_at"] if _codex_login_pending else time.time(),
            "state": "started",
        }

    # ── Phase: wait for codex-acp adapter (task 3.6) ──────────────────────────
    # Poll briefly for the codex-acp binary. Its absence means the image was
    # not built with INCLUDE_CODEX_AGENT=true — fail with an actionable error.
    for _ in range(10):
        try:
            check = podman.container_exec(container, ["which", "codex-acp"])
            if "codex-acp" in check:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        _nuke_codex_login_container(podman, container)
        with _codex_login_pending_lock:
            _codex_login_pending = None
        return {
            "error": (
                f"'codex-acp' adapter not found in image {KC_IMAGE!r}. "
                "Ensure the spec-ops image was built with GA_INCLUDE_CODEX_AGENT=true."
            )
        }

    # ── Phase: PTY exec ───────────────────────────────────────────────────────
    cmd = ["codex-acp", "login"]
    try:
        exec_id, pty_sock = podman.container_exec_pty_stdin(container, cmd)
    except Exception as e:
        _nuke_codex_login_container(podman, container)
        with _codex_login_pending_lock:
            _codex_login_pending = None
        return {"error": f"Failed to start codex-acp login: {e}"}

    pty_sock.setblocking(False)

    # ── Phase: PTY read loop ──────────────────────────────────────────────────
    # Prompt patterns: answer a generic yes/no or "Continue?" prompt with a
    # newline.  URL patterns: OpenAI/ChatGPT auth URLs first, then generic.
    codex_prompt_patterns = [
        (re.compile(r"\?\s*$", re.MULTILINE), b"\n"),
    ]
    codex_url_patterns = [
        re.compile(
            r"https?://(?:auth\.openai\.com|platform\.openai\.com|chatgpt\.com|chat\.openai\.com)\S*"
        ),
        re.compile(r"(?:URL|browser)[:\s]+(https?://\S+)", re.IGNORECASE),
        re.compile(r"(https?://\S{20,})"),
    ]
    # Code is optional for Codex — spec permits a code-less login_url.
    # Use two separate single-group patterns: the helper tries code_pattern
    # against the URL, so pass the user_code= URL param pattern here; the
    # Code: text fallback is run manually after the helper returns if needed.
    codex_code_pattern = re.compile(r"[?&]user_code=([A-Za-z0-9_-]+)")

    login_url, login_code = _run_pty_login_flow(
        pty_sock=pty_sock,
        prompt_patterns=codex_prompt_patterns,
        url_patterns=codex_url_patterns,
        code_pattern=codex_code_pattern,
        deadline_secs=45.0,
    )

    if not login_url:
        try:
            pty_sock.close()
        except Exception:
            pass
        _nuke_codex_login_container(podman, container)
        with _codex_login_pending_lock:
            _codex_login_pending = None
        return {
            "error": "codex-acp login did not produce a login URL within 45s."
        }

    # ── Phase: finalise ────────────────────────────────────────────────────────
    # Drain thread already started by _run_pty_login_flow.
    with _codex_login_pending_lock:
        if _codex_login_pending is not None:
            _codex_login_pending["exec_id"] = exec_id

    logger.info("Codex login flow started in %s, URL extracted", container)
    return {"login_url": login_url, "code": login_code}



def _poll_codex_login_container(podman: "PodmanClient", container: str) -> bytes | None:
    """Poll container for completed ~/.codex/ credentials.

    Checks whether ~/.codex/ inside the container contains a non-empty file
    (auth.json). If present, tars the entire ~/.codex/ directory and returns the
    raw tar bytes. Returns None if credentials are not yet present.

    On completion: the caller writes the tar to ga-codex-auth (mode 0600) and
    nukes the login container.
    """
    try:
        result = podman.container_exec(
            container,
            ["sh", "-c", "find /home/kirocrew/.codex/ -type f -size +0 2>/dev/null | head -1"],
        )
        if not result or not result.strip():
            return None
        import base64 as _b64
        tar_b64_result = podman.container_exec(
            container,
            ["sh", "-c", "tar -cf - -C /home/kirocrew/.codex/ . 2>/dev/null | base64"],
        )
        if tar_b64_result and tar_b64_result.strip():
            return _b64.b64decode(tar_b64_result.strip())
    except Exception as e:
        logger.warning("Error polling Codex login container: %s", e)
    return None


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
        with _registry_lock:
            reg = _load_registry()
            if crew_id in reg["crews"]:
                reg["crews"][crew_id]["last_task_at"] = created_at
                _save_registry(reg)
    except Exception as exc:
        logger.warning("Could not update last_task_at for crew %s: %s", crew_id, exc)


def _dispatch_batch(
    tasks: list[str],
    agent: str,
    crew_id: str | None,
    model: str | None,
    slot: str | bool | None = None,
) -> dict:
    """Sequentially dispatch a batch of tasks; record a batch entry.

    Validation (size, agent, model) has already run in ``dispatch``. On the
    first CrewUnresponsiveError or unexpected failure the loop breaks and a
    ``partial`` batch is recorded with the task_ids assigned so far.

    ``slot`` follows the same semantics as single-task dispatch: explicit arg
    (``True`` / ``"<name>"``) > default resolution (``"bridge"`` if the crew
    has an active dashboard, else ``None`` for headless). For a string slot all
    tasks in the batch share one ``parent_session``. For ``slot=True`` each
    task gets a distinct UUID-suffixed slot.
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

    # Resolve effective slot: explicit arg > live dashboard check.
    if slot is None:
        effective_slot: str | bool | None = "bridge" if crew.get("dashboard_port") else None
    else:
        effective_slot = slot

    # For a string slot, all tasks share the same parent_session; pre-create
    # the dashboard session slot once before the loop (409 = already exists,
    # treat as success). Non-fatal.
    shared_parent_session: str | None = None
    if isinstance(effective_slot, str):
        shared_parent_session = f"dashboard:{effective_slot}"
        try:
            _crew_api(crew, "POST", "/api/chat/slots", json={"name": effective_slot})
        except Exception:
            pass

    batch_id = str(uuid.uuid4())
    task_ids: list[str] = []
    task_slots: dict[str, str] = {}  # task_id -> slot name (for slot=True)
    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    dispatch_error: str | None = None

    for t in tasks:
        body: dict[str, Any] = {"task": t, "agent": agent, "keep": True}
        if model is not None:
            body["model"] = model
        # Inject parent_session per task based on the effective slot.
        task_slot_name: str | None = None
        if effective_slot is True:
            task_slot_name = uuid.uuid4().hex[:8]
            body["parent_session"] = f"dashboard:{task_slot_name}"
            # Pre-create the per-task session slot. Non-fatal.
            try:
                _crew_api(crew, "POST", "/api/chat/slots", json={"name": task_slot_name})
            except Exception:
                pass
        elif shared_parent_session is not None:
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
        # Record per-task slot name for slot=True
        if effective_slot is True and task_slot_name is not None:
            task_slots[tid] = task_slot_name
        # Per-task timestamp + last_task_at, using this task's response time.
        task_created = datetime.now(timezone.utc).isoformat()
        with _task_timestamps_lock:
            _task_timestamps[tid] = {
                "created_at": task_created,
                "started_at": None,
                "completed_at": None,
            }
        _record_last_task_at(crew_id, task_created)

    # Echo the effective slot: the string name, True (auto-per-task), or None.
    response_slot: str | bool | None = effective_slot

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
        # For slot=True, include per-task slot names.
        if effective_slot is True and task_slots:
            response["task_slots"] = task_slots
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
    if effective_slot is True and task_slots:
        response["task_slots"] = task_slots
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
