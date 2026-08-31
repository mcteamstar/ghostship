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
import io
import json
import logging
import os
import re
import secrets
import tarfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

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
    )

try:
    from captain import _resolve_orders_dir  # container: flat /app/
except ModuleNotFoundError:
    from transport.captain import _resolve_orders_dir  # local dev

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

# ── Hardcoded container-side paths ────────────────────────────────────────────
# These match the layout baked into the crew image by the Containerfile.
KIRO_CLI_DB = "/home/kirocrew/.local/share/kiro-cli/data.sqlite3"
KIRO_AGENTS_DIR = "/home/kirocrew/.kiro/agents"
KIRO_SKILLS_DIR = "/home/kirocrew/.kiro/crew/skills"
KIRO_STEERING_DIR = "/home/kirocrew/.kiro/steering"
# KIRO_WORKSPACE_ROOT is imported from transport.podman
KIRO_CREW_DIR = "/home/kirocrew/.kiro/crew"
KIRO_MCP_JSON = "/home/kirocrew/.kiro/mcp.json"

# Container-side helper scripts baked into the crew image at /scripts/ by the
# Containerfile (see transport/container_scripts/, TRN-74). lifecycle.py
# invokes them via `python3 <SCRIPTS_DIR>/<name>.py` inside crew containers.
SCRIPTS_DIR = "/scripts"

# ── Crew infrastructure constants ─────────────────────────────────────────────
CREW_GATEWAY_PORT = 5476
CREW_CONTAINER_PREFIX = "gs-"
CREW_VOLUME_PREFIX = "gs-vol-"
CREW_HOME_VOLUME_PREFIX = "gs-home-"

GA_NETWORK = "ga-net"
GA_LOGIN_CONTAINER_PREFIX = "ga-login-"

# ── Config-driven constants ───────────────────────────────────────────────────
KC_IMAGE = cfg.kc_image
KC_BASE_IMAGE = cfg.kc_base_image
GA_MAX_ACTIVE_CREWS = cfg.ga_max_active_crews
GA_IDLE_TIMEOUT_SECS = cfg.ga_idle_timeout_secs
GA_CREW_AGENT = cfg.ga_crew_agent
KC_MODEL_OVERRIDE = cfg.kc_model_override
KC_MODEL_DEFAULT = cfg.kc_model_default
GA_MIN_FREE_MEM_GB = cfg.ga_min_free_mem_gb
GA_MEMORY_WAIT_SECS = cfg.ga_memory_wait_secs
GA_SPAWN_MIN_MEMORY_GB = cfg.ga_spawn_min_memory_gb
GA_RESOURCE_PRESSURE_GB = cfg.ga_resource_pressure_gb
GA_RESOURCE_CRITICAL_GB = cfg.ga_resource_critical_gb
GA_SUBAGENT_TIMEOUT_SECS = cfg.ga_subagent_timeout_secs
GA_SUBAGENT_MAX_TURNS = cfg.ga_subagent_max_turns
KC_GATEWAY_TOKEN_TTL = cfg.kc_gateway_token_ttl

PERSONA_NAMES = ("ghost", "spectre", "banshee", "wraith", "reaper", "raven")
PERSONA_ALLOWLIST = frozenset(PERSONA_NAMES)

# /mcp catalogue dir for mcpServers resolution
MCP_CATALOGUE_DIR = Path("/mcp")

# ── Lifecycle globals ─────────────────────────────────────────────────────────

# Per-crew startup locks: prevent concurrent restarts racing each other.
# Maps crew_id → threading.Event that is set once the crew is running.
_startup_events: dict[str, threading.Event] = {}
_startup_events_lock = threading.Lock()

# Per-crew recovery locks: prevent concurrent recovery races within
# _crew_api_with_recovery.
_recovery_locks: dict[str, threading.Lock] = {}
_recovery_locks_lock = threading.Lock()

_SCHEDULE_MONITOR_INTERVAL = 30  # seconds


# ── Composition registry ──────────────────────────────────────────────────────
# COMPOSITION_REGISTRY, _load_composition_registry, _resolve_composition,
# _resolve_manifest_path and _resolve_image were extracted to
# transport/academy.py (TRN-86) and are imported at the top of this module.


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


def _crew_api_with_recovery(
    crew: dict,
    crew_id: str,
    method: str,
    path: str,
    **kw: Any,
) -> Any:
    """Wrap _crew_api with two-phase recovery logic.

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
            if status not in (400, 401, 403):
                raise
            # Phase 1: stale cookie — try refresh
            logger.info(
                "Crew %s returned %d — attempting cookie refresh",
                crew_id, status,
            )
            if _refresh_cookie(crew, crew_id):
                # Retry with refreshed cookie
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

            # Final retry after restart
            try:
                return _crew_api(crew, method, path, **kw)
            except Exception:
                raise CrewUnresponsiveError(
                    f"crew {crew_id} is unresponsive — transport attempted "
                    f"cookie refresh and container restart but the gateway "
                    f"did not recover. Suggestion: check crew status with "
                    f"crews() or try again in a moment."
                )

        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError, OSError):
            # Phase 2: connection error — probe then restart only if dead
            logger.info(
                "Crew %s connection error — probing gateway liveness",
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

            # Retry after restart
            try:
                return _crew_api(crew, method, path, **kw)
            except Exception:
                raise CrewUnresponsiveError(
                    f"crew {crew_id} is unresponsive — transport attempted "
                    f"container restart but the gateway did not recover. "
                    f"Suggestion: check crew status with crews() or try "
                    f"again in a moment."
                )


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
        else:
            event = threading.Event()
            _startup_events[crew_id] = event
            is_leader = True

    if not is_leader:
        # Another caller is already restarting — wait for it then return
        # the refreshed crew dict
        logger.info("Crew %s restart already in progress — waiting", crew_id)
        event.wait(timeout=45)
        return _get_crew(crew_id)

    # We are the leader — do the restart
    try:
        logger.info("Crew %s is stopped — restarting", crew_id)

        # Active crew limit: count running entries in the registry.
        # A stopped crew requesting restart must not push the running count
        # over GA_MAX_ACTIVE_CREWS.  GA_MAX_ACTIVE_CREWS=0 disables the check.
        if GA_MAX_ACTIVE_CREWS > 0:
            with _registry_lock:
                reg = _load_registry()
                active = sum(
                    1 for c in reg["crews"].values() if c.get("status") == "running"
                )
            if active >= GA_MAX_ACTIVE_CREWS:
                raise RuntimeError(
                    f"Active crew limit ({GA_MAX_ACTIVE_CREWS}) reached — "
                    "wait for a running crew to idle out or nuke one first"
                )

        # Pre-launch memory gate: wait for balloon to deflate before starting
        if GA_MIN_FREE_MEM_GB > 0:
            free_gb = _wait_for_memory(podman, GA_MIN_FREE_MEM_GB, GA_MEMORY_WAIT_SECS)
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
        if not _wait_gateway(crew_url, timeout=30):
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
        return crew
    finally:
        # Always unblock waiters and clean up, even on error
        with _startup_events_lock:
            _startup_events.pop(crew_id, None)
        event.set()


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


# _load_crew_manifest, _manifest_selects and _substitute_env_vars were
# extracted to transport/academy.py (TRN-86) and are imported at the top of
# this module. _copy_agents/_copy_skills/_copy_steering below call them via
# the imported names.


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
            ["kirocrew", "token", "--ttl", KC_GATEWAY_TOKEN_TTL],
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


def _read_auth_from_crew(podman: PodmanClient, container: str) -> str | None:
    """Read auth_kv rows from a crew container's kiro-cli DB, return as b64 JSON."""
    try:
        b64 = podman.container_exec(
            container, ["python3", f"{SCRIPTS_DIR}/read_auth.py", KIRO_CLI_DB]
        ).strip()
        if b64:
            rows = json.loads(base64.b64decode(b64).decode())
            if rows and any(r[1] for r in rows if len(r) > 1):
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
        elif not podman.container_is_running(container):
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
                if _wait_gateway(crew_url, timeout=30):
                    new_cookie = _mint_cookie(podman, container, crew_url)
                    updates[cid] = {
                        "status": "running",
                        "last_used": time.time(),
                        **({} if not new_cookie else {"cookie": new_cookie}),
                    }
                    logger.info("Crew %s restored", cid)
                    # TRN-29: Re-seed gateway schedules from registry
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
    #   subagent_timeout_secs: > 0. subagent_max_turns: >= 1 (UI cap 200).
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
    }
    # KC_MODEL_DEFAULT sets agent.default_model — a global fallback that applies
    # when no per-agent model field overrides it. Precedence (high→low):
    #   KC_MODEL_OVERRIDE > per-agent model > KC_MODEL_DEFAULT > KiroCrew built-in
    # Only write the field when the env var is set and non-empty; omitting it
    # leaves KiroCrew's built-in default intact for existing installs.
    if KC_MODEL_DEFAULT:
        agent_overrides["default_model"] = KC_MODEL_DEFAULT

    overrides_b64 = base64.b64encode(json.dumps(agent_overrides).encode()).decode()
    config_path = f"{KIRO_CREW_DIR}/config.local.json"
    try:
        result = podman.container_exec(
            container,
            ["python3", f"{SCRIPTS_DIR}/patch_crew_config.py", config_path, overrides_b64],
        )
        logger.info("Config patch for %s: %s", container, result.strip())
    except Exception as e:
        logger.warning("Config patch failed for %s: %s", container, e)


def _inject_git_identity(podman: PodmanClient, container: str) -> None:
    """No-op. Git identity is now injected at container_create time.

    The original implementation wrote GIT_AUTHOR_NAME/EMAIL/GIT_COMMITTER_NAME/
    GIT_COMMITTER_EMAIL to /etc/environment inside the container.  That approach
    does not work: /etc/environment is only read by PAM login sessions (pam_env),
    not by the non-login gateway process or the kiro-cli subprocesses it spawns.
    The gateway builds its child environment from ``{**os.environ}`` which was
    fixed at container-create time — writes to /etc/environment after that are
    invisible to any running or future subprocess.

    The vars are now passed in the container_create env= dict (see launch()),
    so they are in the gateway's process env from startup and inherited by every
    kiro-cli child through the ``{**os.environ}`` chain in AcpRuntime.spawn().
    Container stop/start cycles preserve the create-time env, so idle-stop
    recovery via _ensure_crew_running also works correctly.
    """


def _inject_policy(
    podman: PodmanClient,
    container: str,
    composition: str,
    admiral_secret: str,
) -> str:
    """Inject security_policy.json and admission_policy.json into the crew.

    Returns the policy version string for registry storage.
    Raises on failure — caller must catch and handle gracefully.

    Note: admission_policy.json contains trust_keys (the admiral_secret) which
    is required by KiroCrew's governance API to verify the policy signature.
    The file is written with mode 0600, but agents running as kirocrew can still
    read it. See docs/auth.md for the threat model — this is accepted for the
    current single-operator use case.
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
    # The policy + admiral_secret are passed as a single base64-encoded JSON
    # payload to avoid interpolating the secret as a Python literal.
    policy["identity"] = {"issuer": "ghostship"}
    payload_b64 = base64.b64encode(
        json.dumps({"policy": policy, "admiral_secret": admiral_secret}).encode("utf-8")
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
) -> dict:
    """Complete crew setup after auth is confirmed: copy agents, patch, mint cookie."""
    crew_url = f"http://{container}:{CREW_GATEWAY_PORT}"

    # depends on: container running (pre-restart)
    if not _wait_gateway(crew_url, timeout=10):
        podman.container_stop(container)
        podman.container_start(container)
        if not _wait_gateway(crew_url, timeout=30):
            _cleanup_crew(podman, container, volume, home_volume)
            return {"error": f"Gateway did not recover for crew {crew_id}"}

    # depends on: gateway (pre-restart)
    _inject_auth(podman, container, auth_b64)

    # depends on: container running (pre-restart); must be written before restart
    # so the secret is on the home volume before the post-restart gateway starts
    admiral_secret = secrets.token_hex(32)
    try:
        podman.container_exec_checked(
            container,
            [
                "python3", f"{SCRIPTS_DIR}/inject_admiral_secret.py",
                f"{KIRO_CREW_DIR}/.admiral_secret", admiral_secret,
            ],
        )
        logger.info("Injected admiral signing secret for %s", container)
    except Exception as e:
        logger.warning("Failed to inject admiral secret for %s: %s", container, e)

    # depends on: gateway (pre-restart); gateway seeds config on first start
    _patch_crew_config(podman, container)

    # depends on: auth + admiral_secret + config all committed before workers start
    podman.container_stop(container)
    podman.container_start(container)
    if not _wait_gateway(crew_url, timeout=30):
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

    # Git identity vars (GA_GIT_AUTHOR_NAME/EMAIL) are injected at container_create
    # time so they are part of the process env from startup.  _inject_git_identity
    # is a no-op kept for call-site symmetry; the real work is done in launch().
    _inject_git_identity(podman, container)

    # depends on: admiral_secret (already generated above), filesystem
    policy_version = None
    policy_warning: str | None = None
    try:
        policy_version = _inject_policy(podman, container, composition, admiral_secret)
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
            "admiral_secret": admiral_secret,
            "crew_image_version": crew_image_version,
        }
        if policy_version is not None:
            crew_entry["policy_version"] = policy_version
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
    return result


# ── Login container helpers ───────────────────────────────────────────────────
# These are called from server.py's login state machine; they live here because
# they touch crew container state (Podman operations on login containers).

def _start_login_container(podman: PodmanClient) -> str:
    """Create and start an ephemeral ga-login-<token> container.

    Uses KC_BASE_IMAGE (upstream kirocrew) rather than the local crew image —
    the login container only needs kiro-cli, and using the upstream image avoids
    any risk from a tainted local build. No volumes — kiro-cli DB lives in the
    container's ephemeral writable layer. The container is NOT registered in the
    crew registry and is invisible to MCP tools. Returns the container name.
    """
    token = secrets.token_hex(8)
    name = f"{GA_LOGIN_CONTAINER_PREFIX}{token}"
    podman.network_create(GA_NETWORK)
    podman._req("POST", "/libpod/containers/create", json={
        "name": name,
        "image": KC_BASE_IMAGE,
        "netns": {"nsmode": "bridge"},
        "Networks": {GA_NETWORK: {}},
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


# ── Schedule monitor ──────────────────────────────────────────────────────────

def _schedule_monitor() -> None:
    """Background thread: poll for due scheduled jobs and fire them.

    Checks every 30s. For each due job (next_fire_at <= now), ensures the
    crew is running and fires the tick via POST /api/spawn.
    """
    while True:
        time.sleep(_SCHEDULE_MONITOR_INTERVAL)
        try:
            with _registry_lock:
                reg = _load_registry()
                crew_items = list(reg["crews"].items())

            now = time.time()
            for crew_id, info in crew_items:
                schedules = info.get("schedules", [])
                for sched in schedules:
                    if not sched.get("enabled", True):
                        continue
                    next_fire = sched.get("next_fire_at", _NEVER_FIRE_AT)
                    if next_fire > now:
                        continue

                    # Job is due — wake the crew and fire
                    try:
                        crew = _ensure_crew_running(info, crew_id)
                    except Exception as e:
                        logger.warning(
                            "Schedule monitor: crew %s won't start for job %s: %s",
                            crew_id, sched.get("job_id"), e,
                        )
                        # Advance next_fire_at and persist
                        _advance_next_fire_at(sched)
                        with _registry_lock:
                            reg = _load_registry()
                            crew_scheds = _get_crew_schedules(reg, crew_id)
                            for s in crew_scheds:
                                if s.get("job_id") == sched.get("job_id"):
                                    s["next_fire_at"] = sched["next_fire_at"]
                                    break
                            _save_registry(reg)
                        continue

                    # Fire the tick
                    try:
                        tick_body: dict[str, Any] = {
                            "task": sched.get("message", ""),
                            "agent": sched.get("agent", "ghost"),
                            "keep": True,
                        }
                        if sched.get("model"):
                            tick_body["model"] = sched["model"]
                        _crew_api_with_recovery(
                            crew, crew_id, "POST", "/api/spawn", json=tick_body,
                        )
                    except Exception as e:
                        logger.warning(
                            "Schedule monitor: failed to fire job %s on crew %s: %s",
                            sched.get("job_id"), crew_id, e,
                        )

                    # Advance next_fire_at in registry after fire (success or failure)
                    _advance_next_fire_at(sched)
                    with _registry_lock:
                        reg = _load_registry()
                        crew_scheds = _get_crew_schedules(reg, crew_id)
                        for s in crew_scheds:
                            if s.get("job_id") == sched.get("job_id"):
                                s["next_fire_at"] = sched["next_fire_at"]
                                break
                        _save_registry(reg)

                    # H-2: For one-shot (delay) jobs, delete the cron from the
                    # gateway so its annual cron expression never fires again.
                    if sched.get("one_shot"):
                        job_id = sched.get("job_id")
                        if job_id:
                            try:
                                _crew_api_with_recovery(
                                    crew, crew_id, "DELETE", f"/api/crons/{job_id}"
                                )
                                logger.info(
                                    "Schedule monitor: deleted one-shot cron %s from gateway after fire",
                                    job_id,
                                )
                            except Exception as e:
                                logger.warning(
                                    "Schedule monitor: could not delete one-shot cron %s from gateway: %s",
                                    job_id, e,
                                )

        except Exception as e:
            logger.warning("Schedule monitor error: %s", e)


# ── Idle monitor ─────────────────────────────────────────────────────────────

def _cron_activity_since(payload: Any, last_used: float) -> bool:
    """Return whether a cron is running or completed since the last touch.

    Cron executions are tracked by the crew gateway's cron service rather than
    its dispatched-task list.  Treating both in-flight work and a recently
    completed run as activity keeps the idle monitor independent of any one
    caller such as Captain.
    """
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if not isinstance(jobs, list):
        return False
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if job.get("is_running"):
            return True
        for field in ("running_since", "last_run_ts"):
            stamp = job.get(field)
            if (
                isinstance(stamp, (int, float))
                and not isinstance(stamp, bool)
                and stamp > last_used
            ):
                return True
    return False


def _cron_has_enabled_job(payload: Any) -> bool:
    """Return whether any cron job for this crew is currently enabled.

    An enabled job may not have fired yet — its interval can exceed
    GA_IDLE_TIMEOUT_SECS, which is common for anything coarser than a
    minute — so "activity since last touch" alone cannot detect it: there
    is no activity to detect until the first fire. An enabled job is
    itself a standing commitment to run; stopping the crew before that
    commitment is ever honoured would silently orphan it before its first
    check-in.
    """
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if not isinstance(jobs, list):
        return False
    return any(isinstance(job, dict) and job.get("enabled") for job in jobs)


def _idle_monitor() -> None:
    """Background thread: stop crew containers that have been idle too long.

    Checks every GA_IDLE_TIMEOUT_SECS seconds. A crew is considered idle when:
    - It has no running tasks (done=false), AND
    - It hasn't been used in GA_IDLE_TIMEOUT_SECS seconds

    Stopped containers are restarted transparently on next use by _ensure_crew_running.
    """
    while True:
        time.sleep(max(GA_IDLE_TIMEOUT_SECS, 10))
        try:
            podman = _get_podman()
        except Exception:
            continue

        with _registry_lock:
            reg = _load_registry()
            crew_items = list(reg["crews"].items())

        now = time.time()
        for crew_id, info in crew_items:
            if info.get("status") == "auth_required":
                continue
            if not podman.container_is_running(info["container"]):
                continue

            last_used = info.get("last_used", 0)
            idle_secs = now - last_used
            if idle_secs < GA_IDLE_TIMEOUT_SECS:
                continue

            crew_url = f"http://{info['container']}:{CREW_GATEWAY_PORT}"
            cookie = f"mc_token_{CREW_GATEWAY_PORT}={info['cookie']}"

            # Check for active dispatched tasks before stopping.
            try:
                r = _http.get(
                    f"{crew_url}/api/spawn",
                    headers={"Cookie": cookie, "Origin": crew_url},
                    timeout=5.0,
                )
                if r.status_code in (401, 403):
                    # Cookie expired — attempt refresh and retry
                    new_cookie = _mint_cookie(podman, info["container"], crew_url)
                    if new_cookie:
                        cookie = f"mc_token_{CREW_GATEWAY_PORT}={new_cookie}"
                        with _registry_lock:
                            reg = _load_registry()
                            if crew_id in reg["crews"]:
                                reg["crews"][crew_id]["cookie"] = new_cookie
                                _save_registry(reg)
                        r = _http.get(
                            f"{crew_url}/api/spawn",
                            headers={"Cookie": cookie, "Origin": crew_url},
                            timeout=5.0,
                        )
                    else:
                        # Can't verify activity — skip this crew (fail-open)
                        continue
                if r.status_code != 200:
                    # Activity is unknown after any non-success response — fail open.
                    continue
                payload = r.json()
                if not isinstance(payload, dict):
                    # A successful response with an unusable shape is still unknown activity.
                    continue
                agents = payload.get("agents")
                if not isinstance(agents, list):
                    continue
                active = [
                    agent for agent in agents
                    if isinstance(agent, dict) and not agent.get("done")
                ]
                if active:
                    # Tasks still running — update last_used and skip.
                    _touch_crew(crew_id)
                    continue
            except Exception:
                continue

            # Cron executions do not appear in /api/spawn.  The gateway exposes
            # their running and last-completed timestamps through /api/crons —
            # and an enabled job that hasn't fired yet (its interval can
            # exceed GA_IDLE_TIMEOUT_SECS) must also keep the crew alive, not
            # just one that already has.
            try:
                r = _http.get(
                    f"{crew_url}/api/crons",
                    headers={"Cookie": cookie, "Origin": crew_url},
                    timeout=5.0,
                )
                if r.status_code in (401, 403):
                    # Cookie expired — attempt refresh and retry
                    new_cookie = _mint_cookie(podman, info["container"], crew_url)
                    if new_cookie:
                        cookie = f"mc_token_{CREW_GATEWAY_PORT}={new_cookie}"
                        with _registry_lock:
                            reg = _load_registry()
                            if crew_id in reg["crews"]:
                                reg["crews"][crew_id]["cookie"] = new_cookie
                                _save_registry(reg)
                        r = _http.get(
                            f"{crew_url}/api/crons",
                            headers={"Cookie": cookie, "Origin": crew_url},
                            timeout=5.0,
                        )
                    else:
                        # Can't verify activity — skip this crew (fail-open)
                        continue
                if r.status_code != 200:
                    # Activity is unknown after any non-success response — fail open.
                    continue
                cron_payload = r.json()
                if not isinstance(cron_payload, dict):
                    # A successful response with an unusable shape is still unknown activity.
                    continue
                if not isinstance(cron_payload.get("jobs"), list):
                    continue
                if _cron_activity_since(cron_payload, last_used) or _cron_has_enabled_job(
                    cron_payload
                ):
                    _touch_crew(crew_id)
                    continue
            except Exception:
                continue

            logger.info(
                "Crew %s idle for %.0fs — stopping container",
                crew_id, idle_secs,
            )
            podman.container_stop(info["container"])
            with _registry_lock:
                reg = _load_registry()
                if crew_id in reg["crews"]:
                    reg["crews"][crew_id]["status"] = "stopped"
                    _save_registry(reg)


# ── Academy validation ────────────────────────────────────────────────────────
# _AGENTS_DIR and _validate_academy() were extracted to transport/academy.py
# (TRN-86) and are imported at the top of this module.
