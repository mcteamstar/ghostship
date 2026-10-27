"""MCP tool registry — extracted from server.py (TRN-242).

Home of the MCP tool functions (``crews``, ``launch``, ``supply``, ``evac``,
``nuke``, ``captain``, ``schedule``, ``dispatch``, ``steer``, ``pickup``) and
the ``transport://`` resources, plus the helpers used only by them
(``_registry_guard``, ``_validate_model``, ``_bg_prewarm``, ``_schedule_cancel``,
``_schedule_list``).

The ``mcp`` instance itself stays in ``server.py``; this module exposes
``register_tools(mcp_instance, caddy_portal, dashboard_gate)`` which applies the
``@mcp.tool()`` / ``@mcp.resource(...)`` decorators programmatically against the
instance ``server.py`` owns, and stashes the two injected objects into this
module's globals so the module-level ``launch`` / ``nuke`` functions (which need
the portal and the dashboard gate) can read them.

Dependency boundary: a pure leaf imported by ``server.py``. It imports from
``config``, ``registry``, ``captain``, ``captain_engine``, ``lifecycle``,
``files``, ``podman``, ``constants``, ``academy``, ``security`` and ``login`` —
never from ``server``.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

try:
    import httpx2 as httpx  # container: flat /app/
except ModuleNotFoundError:
    import httpx  # local dev / test stub

try:
    import security as _security  # container: flat /app/
except ModuleNotFoundError:
    from transport import security as _security  # local dev

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config  # local dev

try:
    from credentials import CredentialStore  # container: flat /app/
except ImportError:
    from transport.credentials import CredentialStore  # local dev

try:
    from constants import (  # container: flat /app/
        ADMIRAL_PUBKEY_PATH,
        CREW_CONTAINER_PREFIX,
        CREW_GATEWAY_PORT,
        CREW_HOME_VOLUME_PREFIX,
        CREW_VOLUME_PREFIX,
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
        GA_STARBOARD_NETWORK,
        PERSONA_NAMES,
    )

try:
    from registry import (  # container: flat /app/
        registry,
        _get_crew,
        _delete_crew_secret,
        _read_crew_secret,
        _write_crew_secret,
        _find_batch_by_task_ids,
        _update_batch_status,
    )
except ModuleNotFoundError:
    from transport.registry import (  # local dev
        registry,
        _get_crew,
        _delete_crew_secret,
        _read_crew_secret,
        _write_crew_secret,
        _find_batch_by_task_ids,
        _update_batch_status,
    )

# RegistryCorruptError drives the _registry_guard decorator. Imported with the
# same resilient fallback server.py uses.
try:
    from registry import RegistryCorruptError  # container: flat /app/
except (ModuleNotFoundError, ImportError):
    try:
        from transport.registry import RegistryCorruptError  # local dev
    except (ModuleNotFoundError, ImportError):
        class RegistryCorruptError(RuntimeError):  # pragma: no cover - fallback
            pass

try:
    from podman import _get_podman, _get_host_memory_gb_cached  # container: flat /app/
except ModuleNotFoundError:
    from transport.podman import _get_podman, _get_host_memory_gb_cached  # local dev

try:
    from files import _sign_file_url, _sign_upload_url  # container: flat /app/
except ModuleNotFoundError:
    from transport.files import _sign_file_url, _sign_upload_url  # local dev

try:
    from captain import (  # container: flat /app/
        _CAPTAIN_CHECKIN_JOB_NAME,
        _captain_jobs,
        _captain_order_locks,
        _captain_order_locks_lock,
        _list_order_templates,
        _load_order_template,
        _substitute_placeholders,
        _skim_all_mailboxes,
        _read_all_mail_counts,
    )
except ModuleNotFoundError:
    from transport.captain import (  # local dev
        _CAPTAIN_CHECKIN_JOB_NAME,
        _captain_jobs,
        _captain_order_locks,
        _captain_order_locks_lock,
        _list_order_templates,
        _load_order_template,
        _substitute_placeholders,
        _skim_all_mailboxes,
        _read_all_mail_counts,
    )

try:
    from captain_engine import (  # container: flat /app/
        _MEMORY_PRESSURE_MARKER,
        _MemoryPressureSkip,
        _is_memory_pressure_refusal,
        _captain_do_order,
        _captain_do_status,
        _captain_do_stop,
    )
except ModuleNotFoundError:
    from transport.captain_engine import (  # local dev
        _MEMORY_PRESSURE_MARKER,
        _MemoryPressureSkip,
        _is_memory_pressure_refusal,
        _captain_do_order,
        _captain_do_status,
        _captain_do_stop,
    )

try:
    from academy import (  # container: flat /app/
        COMPOSITION_REGISTRY,
        _AGENTS_DIR,
        _resolve_composition,
        _resolve_image,
    )
except ImportError:
    from transport.academy import (  # local dev
        COMPOSITION_REGISTRY,
        _AGENTS_DIR,
        _resolve_composition,
        _resolve_image,
    )

# lifecycle: tools is imported by server AFTER lifecycle is fully loaded, and a
# standalone `import transport.tools` loads lifecycle (which imports monitors,
# which imports captain_engine with a lazy lifecycle hook) without re-entering
# lifecycle — so an eager top-level import here is cycle-safe.
try:
    from lifecycle import (  # container: flat /app/
        CrewUnresponsiveError,
        _NUKED_DURING_RESTART,
        _cleanup_crew,
        _crew_api,
        _crew_api_with_recovery,
        _crew_url,
        _dispatch_batch,
        _ensure_crew_running,
        _finish_crew_setup,
        _initiate_claude_login,
        _initiate_codex_login,
        _initiate_login,
        _nuke_login_container,
        _pickup_batch,
        _pickup_list,
        _pickup_single,
        _prewarm_crew,
        _probe_gateway,
        _read_auth_from_crew,
        _record_last_task_at,
        _require_crew,
        _resolve_dispatch_slot,
        _to_crew,
        _validate_agent,
        _wait_gateway,
    )
    import lifecycle as _lifecycle  # for the shared task-timestamp objects
except ModuleNotFoundError:
    from transport.lifecycle import (  # local dev
        CrewUnresponsiveError,
        _NUKED_DURING_RESTART,
        _cleanup_crew,
        _crew_api,
        _crew_api_with_recovery,
        _crew_url,
        _dispatch_batch,
        _ensure_crew_running,
        _finish_crew_setup,
        _initiate_claude_login,
        _initiate_codex_login,
        _initiate_login,
        _nuke_login_container,
        _pickup_batch,
        _pickup_list,
        _pickup_single,
        _prewarm_crew,
        _probe_gateway,
        _read_auth_from_crew,
        _record_last_task_at,
        _require_crew,
        _resolve_dispatch_slot,
        _to_crew,
        _validate_agent,
        _wait_gateway,
    )
    from transport import lifecycle as _lifecycle  # local dev

# dispatch() mutates the shared in-memory task-timestamp store that lives in
# lifecycle (same objects server used). Reference lifecycle's live objects.
_task_timestamps = _lifecycle._task_timestamps
_task_timestamps_lock = _lifecycle._task_timestamps_lock


# login module: launch() reads login.KIRO_FLOW on the kiro device-flow path.
try:
    import login  # container: flat /app/
except ModuleNotFoundError:
    from transport import login  # local dev

logger = logging.getLogger(__name__)

# ── Config singleton (D4) ─────────────────────────────────────────────────────
# tools.py reads its config-derived constants from its own Config.from_env()
# singleton rather than importing them from server. Mirrors lifecycle.py and
# keeps tools a pure leaf. Credential-bearing values go through
# _security.get_secret (same resolution order as server/lifecycle).
cfg = Config.from_env()

PORT = cfg.port
GA_MAX_CREWS = cfg.ga_max_crews
GA_MAX_ACTIVE_CREWS = cfg.ga_max_active_crews
GA_CREW_ACP_BACKEND = cfg.ga_crew_agent.split(",")[0].strip().lower()

GA_GIT_AUTHOR_NAME = os.environ.get("GA_GIT_AUTHOR_NAME", "").strip()
GA_GIT_AUTHOR_EMAIL = os.environ.get("GA_GIT_AUTHOR_EMAIL", "").strip()

# Credential store — resolved per-launch via store.get(backend) rather than
# module-level globals (TRN-233 task 2.1).
_cred_store = CredentialStore()

_ANTHROPIC_BASE_URL = cfg.anthropic_base_url
_OPENAI_BASE_URL = cfg.openai_base_url

_MODEL_MAX_LENGTH = 500
_MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")

PERSONA_ALLOWLIST = frozenset(PERSONA_NAMES)


# ── Transport version (resource_version) ──────────────────────────────────────
# lifecycle does not re-export TRANSPORT_VERSION, so resource_version resolves it
# here with the same precedence server.py uses (env var -> VERSION file ->
# sentinel). This is the fresh-definition fallback described in TRN-242 D-step 2.8.
def _read_transport_version() -> str:
    env_version = os.environ.get("TRANSPORT_VERSION", "").strip()
    if env_version:
        return env_version
    from pathlib import Path as _Path
    version_path = _Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return version_path.read_text().strip()
    except (FileNotFoundError, OSError):
        return "0.0.0-dev"


TRANSPORT_VERSION: str = _read_transport_version()

# ── Injected server-owned objects (set by register_tools) ────────────────────
# launch() and nuke() need the CaddyPortal and DashboardGate instances created
# in server.py. register_tools() stashes them here so the module-level tool
# functions can read them (R4 — injection, not a server import).
_caddy_portal = None
_dashboard_gate = None


def _validate_model(model: str | None) -> str | None:
    """Validate and normalize an optional KiroCrew model override."""
    if model is None:
        return None
    if not isinstance(model, str):
        raise ValueError("Invalid model: expected a string")
    if not model:
        return None
    if len(model) > _MODEL_MAX_LENGTH:
        raise ValueError(
            f"Invalid model: maximum length is {_MODEL_MAX_LENGTH} characters"
        )
    if _MODEL_NAME_RE.fullmatch(model) is None:
        raise ValueError(
            "Invalid model: must start with a letter or digit and contain only "
            "letters, digits, '.', '_' or '-'"
        )
    return model


# ──────────────────────────────────────────────────────────────────────────────
# MOVED FUNCTIONS (helpers + tool bodies) — appended below. Tool functions are
# plain module-level defs here; register_tools() applies the mcp decorators.
# ──────────────────────────────────────────────────────────────────────────────


def _registry_guard(fn):
    """Wrap an MCP tool so a corrupt registry becomes a structured
    error response instead of an unhandled exception crashing the in-flight
    request. Any ``RegistryCorruptError`` raised out of ``_load_registry()``
    (directly or via a registry helper) is caught at the tool boundary and
    turned into ``{"error": "..."}``. ``functools.wraps`` preserves the
    original signature and docstring so MCP tool introspection is unchanged.
    """

    @functools.wraps(fn)
    def _wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except RegistryCorruptError:
            return {
                "error": "registry corrupt — crews.json.corrupt preserved for inspection"
            }

    return _wrapped


@_registry_guard
def crews() -> dict:
    """Situational awareness — list all crews and what's running before deciding what to do next.

    Shows crew_id, container, status, created_at, and last_task_at for each,
    plus uptime_secs (seconds since the container started; present only for
    running crews, null otherwise).
    Also includes active agents (tasks) running inside each crew — each with
    task_id, agent, done, and elapsed_secs. For live per-task detail (current
    tool, latest output) use `pickup`, not this overview.
    Also: list crews, show workspaces, what's running, sitrep.
    """
    with registry:
        _crews_data = dict(registry._reg.get("crews", {}))

    # Host memory visibility
    podman = None
    try:
        podman = _get_podman()
        host_mem = _get_host_memory_gb_cached(podman)
    except Exception:
        host_mem = None

    result = []
    corrections: list[str] = []  # crew_ids registered running but not actually running
    for cid, info in _crews_data.items():
        # Determine gateway health: stopped containers are unhealthy without
        # probing; running containers get a liveness probe — but only after
        # confirming with Podman that the container is actually running. A
        # registry entry marked "running" whose container was stopped
        # externally is corrected to "stopped" here (self-heal), and must not
        # trigger a gateway probe or an uptime inspect.
        status = info.get("status", "unknown")
        if status == "running" and podman is not None:
            if not podman.container_is_running(info["container"]):
                # Stale running entry — container is not actually running.
                status = "stopped"
                gateway_healthy = False
                corrections.append(cid)
            else:
                crew_url = _crew_url(info)
                gateway_healthy = _probe_gateway(crew_url)
        elif status != "running":
            gateway_healthy = False
        else:
            # status == "running" but no Podman client — fall back to a probe
            # (cannot confirm container state without Podman).
            crew_url = _crew_url(info)
            gateway_healthy = _probe_gateway(crew_url)

        entry = {
            "crew_id": cid,
            "container": info["container"],
            "status": status,
            "composition": info.get("composition", "kirocrew"),
            "created_at": info.get("created_at"),
            "last_task_at": info.get("last_task_at"),
            "gateway_healthy": gateway_healthy,
            "crew_image_version": info.get("crew_image_version", "unknown"),
            # acp_backend: "kiro" (default), "claude", or "codex". Defaults to "kiro" for
            # pre-TRN-167 registry entries that do not have the field.
            "acp_backend": info.get("acp_backend", "kiro"),
            "agents": [],
        }
        # Derive dashboard_url from stored dashboard_port (None if no port assigned).
        # ga-portal is always present — always use the Caddy scheme.
        _ui_p = info.get("dashboard_port")
        if _ui_p is not None:
            _caddy_scheme = "http" if cfg.ga_portal_tls_mode == "off" else "https"
            if cfg.ga_host_url:
                from urllib.parse import urlparse as _urlparse3
                _ph = _urlparse3(cfg.ga_host_url)
                entry["dashboard_url"] = f"{_caddy_scheme}://{_ph.hostname}:{_ui_p}/"
            else:
                entry["dashboard_url"] = f"{_caddy_scheme}://localhost:{_ui_p}/"
        else:
            entry["dashboard_url"] = None
        if "policy_version" in info:
            entry["policy_version"] = info["policy_version"]
        # uptime_secs for running crews, derived from the container's
        # State.StartedAt via Podman inspect. Omitted (None) for stopped crews
        # or on any inspect/parse failure.
        entry["uptime_secs"] = None
        if status == "running" and podman is not None:
            try:
                inspect = podman.container_inspect(info["container"])
                started_raw = inspect.get("State", {}).get("StartedAt")
                if started_raw:
                    started_at = datetime.fromisoformat(
                        started_raw.replace("Z", "+00:00")
                    )
                    if started_at.tzinfo is None:
                        started_at = started_at.replace(tzinfo=timezone.utc)
                    entry["uptime_secs"] = int(
                        (datetime.now(timezone.utc) - started_at).total_seconds()
                    )
            except Exception:
                entry["uptime_secs"] = None  # inspect failed — omit uptime
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
                    }
                    for a in tasks.get("agents", [])
                ]
        except Exception:
            pass  # crew may be idle/stopped — agents list stays empty
        result.append(entry)

    # Write back any stale running→stopped corrections discovered above, in a
    # single save under the registry lock (second acquisition, following the
    # established reconcile pattern). Only flip entries that are still marked
    # "running" in the registry to avoid clobbering a concurrent legitimate
    # state change.
    if corrections:
        with registry:
            for cid in corrections:
                entry2 = registry._reg["crews"].get(cid)
                if entry2 is not None and entry2.get("status") == "running":
                    entry2["status"] = "stopped"

    # active_crews reflects containers actually confirmed running by Podman:
    # each result entry's status has already been corrected to "stopped" for
    # stale registry-running entries above.
    active_crews = sum(1 for e in result if e.get("status") == "running")
    return {
        "crews": result,
        "host_memory_available_gb": host_mem,
        "active_crews": active_crews,
        "max_active_crews": GA_MAX_ACTIVE_CREWS,
    }


def resource_compositions() -> str:
    """Return available crew compositions from the registry."""
    if not COMPOSITION_REGISTRY:
        return "No compositions registered. Defaulting to 'kirocrew'."
    lines = []
    for entry in COMPOSITION_REGISTRY.values():
        image_note = f" (image: {entry['image']})" if entry.get("image") else ""
        lines.append(f"## {entry['name']}\n{entry['description']}{image_note}")
    return "\n\n".join(lines)


@_registry_guard
def launch(
    crew_id: str,
    composition: str = "spec-ops",
    dashboard: bool | None = None,
    backend: str | None = None,
) -> dict:
    """Step 1: create a crew workspace — summon a new crew container into existence, with its own workspace volume.

    Creates an isolated crew: a full KiroCrew instance (gateway + agent pool)
    with a dedicated workspace. Repository seeding is a separate supply step —
    dispatching into an empty crew without calling supply first is a real
    failure mode.
    Also: calldown, create workspace, launch crew, init environment, load the ghostship.

    Requires prior authentication. If not authenticated, launch automatically
    initiates the device auth flow and returns login_url and code so the caller
    can complete auth and retry launch — no separate POST /login call needed.

    Args:
        crew_id: Name for this crew (e.g. 'general', 'srv-refactor'). Must be
                 unique. Use lowercase letters, numbers, hyphens.
        composition: Crew composition to launch (default: "spec-ops"). See the
                     transport://compositions resource for available compositions.
        dashboard: When True, allocates a dedicated port from the UI port range
                   and registers it with Portal (ga-portal) so the crew's
                   dashboard SPA is accessible via HTTPS. The SPA owns its
                   entire origin so assets, client-side navigation, and hard
                   reloads all work. Returns dashboard_url in the response.
                   None (default) uses the site default from GA_DASHBOARD_DEFAULT
                   (false unless configured). Pass False to force headless even
                   when GA_DASHBOARD_DEFAULT=true.

                   MEMORY COST: when dashboard=True, dispatching enrolled persona
                   agents with the default slot (slot=None) routes them into
                   their member DM slot, which spawns a kiro-cli-chat process
                   per task (~300-400 MB each). For autonomous/unattended work
                   (SDD, batch jobs, background tasks) where you don't need
                   browser visibility, pass dashboard=False (or dispatch with
                   slot=False) to avoid this overhead. Use dashboard=True only
                   when you actually intend to watch the crew in a browser.
        backend: Agent runtime for this crew: "kiro", "claude" or "codex".
                 None (default) uses the transport default (the first entry of
                 backends.default). Must be an enabled backend — kiro always is;
                 claude/codex only when listed in backends.default — otherwise
                 launch returns backend_not_enabled with the enabled list. The
                 crew keeps this backend for its whole life, including restarts;
                 authentication uses that backend's stored credential.

    Returns crew_id and status once the gateway is ready (~60s).
    """
    # Resolve effective dashboard: explicit arg wins; None falls back to site default.
    effective_dashboard = dashboard if dashboard is not None else cfg.ga_dashboard_default

    if not re.match(r'^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$|^[a-z0-9]$', crew_id):
        return {"error": "crew_id must be lowercase alphanumeric/hyphens, 1-50 chars"}

    # TRN-259: resolve the crew's backend — the caller's choice, else the
    # transport default — and require it to be enabled (its toolchain is only
    # in the crew image when it is). Everything below keys on this value.
    backend = (backend or "").strip().lower() or GA_CREW_ACP_BACKEND
    if not login._backend_enabled(backend):
        return {
            "error": "backend_not_enabled",
            "backend": backend,
            "enabled": list(login._enabled_backends()),
            "instructions": login._backend_not_enabled_message(backend),
        }

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
    # Credentials are resolved per-launch from the credential store (TRN-233
    # task 2.1). No module-level credential globals remain; store.get(backend)
    # is called here and the result is used for gating and env injection below.
    auth_b64: str | None = None

    # Resolve the crew backend's credential once per launch.
    _cred = _cred_store.get(backend)

    if backend == "claude":
        # Claude backend — require a stored credential (any method).
        # If no credential is present, initiate the Claude login flow and return
        # not_authenticated with the login URL.
        if not _cred:
            result = _initiate_claude_login(podman)
            if result.get("login_pending"):
                return {
                    "error": "not_authenticated",
                    "login_pending": True,
                    "instructions": "Claude login already in progress. Poll GET /login/claude, then call launch again.",
                }
            if "error" in result:
                return {"error": result["error"]}
            return {
                "error": "not_authenticated",
                "login_url": result.get("login_url"),
                "code": result.get("code"),
                "instructions": "Open login_url, approve, then POST the pasted code to /login/claude/code, poll GET /login/claude until complete, then call launch again.",
            }
    elif backend == "codex":
        # Codex backend — require a stored credential (any method).
        # If no credential is present, initiate the Codex login flow and return
        # not_authenticated with the login URL.
        if not _cred:
            result = _initiate_codex_login(podman)
            if result.get("login_pending"):
                return {
                    "error": "not_authenticated",
                    "login_pending": True,
                    "instructions": "Codex login already in progress. Poll GET /login/codex, then call launch again.",
                }
            if "error" in result:
                return {"error": result["error"]}
            return {
                "error": "not_authenticated",
                "login_url": result.get("login_url"),
                "code": result.get("code"),
                "instructions": "Open login_url to authenticate with Codex, then call launch again.",
            }
    else:
        # kiro path — api-key credential skips device flow entirely.
        # TRN-233: the credential store is the sole source of truth.
        # Legacy ga-kiro-auth file is no longer read.
        _kiro_api_key = ""
        if _cred and _cred["method"] == "api-key":
            _kiro_api_key = _cred["payload"].decode("utf-8") if isinstance(_cred["payload"], bytes) else _cred["payload"]
        # For device-flow methods (builder-id, identity-center), auth_b64 comes
        # from the credential store or from polling a running login container.
        if _cred and _cred["method"] in ("builder-id", "identity-center"):
            _payload = _cred["payload"]
            auth_b64 = _payload.decode("utf-8") if isinstance(_payload, bytes) else _payload
        if not _kiro_api_key and not auth_b64:
            # If a login is already in progress, poll the DB before giving up —
            # the user may have just completed the device flow but GET /login
            # hasn't been called yet to store the credential.
            pending = login.KIRO_FLOW.state
            if pending is not None:
                _poll_consumed = False
                _cancelled = False
                try:
                    auth_b64 = _read_auth_from_crew(podman, pending["container"]) or None
                    if auth_b64:
                        # Store via credential store (TRN-233 hard break — no legacy file write).
                        _provider = pending.get("provider")
                        _method = "identity-center" if _provider else "builder-id"
                        # Commit only if the flow was not cancelled by logout while we polled.
                        _committed = login.KIRO_FLOW.commit_if_current(
                            pending,
                            lambda: _cred_store.put("kiro", _method, auth_b64, provider=_provider),
                        )
                        if _committed:
                            _nuke_login_container(podman, pending["container"])
                            _poll_consumed = True
                            logger.info("Auth completed via launch poll — login container cleaned up")
                        else:
                            _cancelled = True
                            auth_b64 = None
                            logger.info("Launch poll found a login cancelled by logout; credential discarded")
                except Exception as e:
                    logger.warning("Auth poll in launch failed: %s", e)
                finally:
                    # D7a: if the poll did not complete the login (read raised or
                    # returned no auth) we fall through to _initiate_login below,
                    # which starts a NEW login container. The stale one from the
                    # prior flow would then leak. Nuke it and clear the sentinel
                    # here so the retry starts clean. A cancelled flow is already
                    # cleared, so skip the abort: it could cancel a newer flow.
                    if not _poll_consumed:
                        try:
                            _nuke_login_container(podman, pending["container"])
                        except Exception:
                            pass
                        if not _cancelled:
                            login.KIRO_FLOW.abort(podman)
                if _cancelled:
                    return {
                        "error": "not_authenticated",
                        "instructions": "Login was cancelled by logout. Start a kiro login, then call launch again.",
                    }
            if not auth_b64:
                result = _initiate_login(podman)
                if result.get("login_pending"):
                    return {
                        "error": "not_authenticated",
                        "login_pending": True,
                        "instructions": "Login already in progress. Poll GET /login/kiro, then call launch again.",
                    }
                if "error" in result:
                    return {"error": result["error"]}
                return {
                    "error": "not_authenticated",
                    "login_url": result.get("login_url"),
                    "code": result.get("code"),
                    "instructions": "Open login_url to authenticate, then call launch again.",
                }

    with registry:
        existing = registry._reg["crews"].get(crew_id)
        if existing:
            return {"error": f"Crew '{crew_id}' already exists. Nuke it first to recreate."}
        if len(registry._reg["crews"]) >= GA_MAX_CREWS:
            return {"error": f"Registered crew limit ({GA_MAX_CREWS}) reached. Nuke one first."}
        # Pre-insert a placeholder to prevent concurrent launches with the same id
        registry._reg["crews"][crew_id] = {"status": "launching", "container": container}

    # Initialised before the try so the except block can reference it.
    dashboard_port: int | None = None
    try:
        podman.network_create(GA_STARBOARD_NETWORK)
        podman.volume_create(volume)
        podman.volume_create(home_volume)
        logger.info("Created volumes %s, %s", volume, home_volume)

        # Build container env — always include CORS and sandbox flag.
        # all four git identity vars so they are part of the container's process
        # environment from startup and inherited by the gateway and every kiro-cli
        # child it spawns.  /etc/environment is NOT used because it is only read
        # by PAM login sessions, not by non-login processes like the gateway.
        #
        # Derive the transport's public origin for CORS injection.
        # The crew gateway needs to accept API calls from the browser when it is
        # served from the per-crew UI port (a different origin). We append the
        # transport's public origin to KIROCREW_CORS_ORIGINS so those calls are
        # not CORS-rejected. The public base is GA_HOST_URL (path stripped) or,
        # when unset, derived from ga-portal's published address (HOST).
        from urllib.parse import urlparse as _urlparse
        _parsed = _urlparse(cfg.public_base_url())
        _transport_public_origin = f"{_parsed.scheme}://{_parsed.netloc}"

        _crew_internal_origin = f"http://{container}:{CREW_GATEWAY_PORT}"
        _cors_origins = f"{_crew_internal_origin},{_transport_public_origin}"

        container_env: dict[str, str] = {
            "KIROCREW_CORS_ORIGINS": _cors_origins,
            # Injected so crew-internal scripts (e.g. Raven self-cancel) can
            # address the transport at /crews/{crew_id}/... without parsing
            # KIROCREW_CORS_ORIGINS (TRN-241).
            "KIROCREW_CREW_ID": crew_id,
            # Sandbox mode is controlled via the crew's sandbox: config key;
            # KIROCREW_ALLOW_UNSANDBOXED was removed (replaced by sandbox: off).
        }
        # Credential-based env injection — resolved per-launch from the store
        # (TRN-233 task 2.1).  _cred was resolved above in the auth-gating block;
        # method drives which env var to set.
        if backend == "kiro":
            if _cred and _cred["method"] == "api-key":
                container_env["KIRO_API_KEY"] = _cred["payload"].decode("utf-8") if isinstance(_cred["payload"], bytes) else _cred["payload"]
        elif backend == "claude":
            if _cred:
                if _cred["method"] == "api-key":
                    container_env["ANTHROPIC_API_KEY"] = _cred["payload"].decode("utf-8") if isinstance(_cred["payload"], bytes) else _cred["payload"]
                    if _ANTHROPIC_BASE_URL:
                        container_env["ANTHROPIC_BASE_URL"] = _ANTHROPIC_BASE_URL
                elif _cred["method"] == "setup-token":
                    container_env["CLAUDE_CODE_OAUTH_TOKEN"] = _cred["payload"].decode("utf-8") if isinstance(_cred["payload"], bytes) else _cred["payload"]
                # oauth method: ~/.claude/ is injected in _finish_crew_setup via _inject_claude_auth
        elif backend == "codex":
            if _cred and _cred["method"] == "api-key":
                container_env["OPENAI_API_KEY"] = _cred["payload"].decode("utf-8") if isinstance(_cred["payload"], bytes) else _cred["payload"]
            # chatgpt method: ~/.codex/ is injected in _finish_crew_setup via _inject_codex_auth
            if _OPENAI_BASE_URL:
                container_env["OPENAI_BASE_URL"] = _OPENAI_BASE_URL
        if GA_GIT_AUTHOR_NAME and GA_GIT_AUTHOR_EMAIL:
            container_env["GIT_AUTHOR_NAME"] = GA_GIT_AUTHOR_NAME
            container_env["GIT_AUTHOR_EMAIL"] = GA_GIT_AUTHOR_EMAIL
            container_env["GIT_COMMITTER_NAME"] = GA_GIT_AUTHOR_NAME
            container_env["GIT_COMMITTER_EMAIL"] = GA_GIT_AUTHOR_EMAIL

        # Allocate a transport-side UI port for the crew's SPA. The crew container
        # itself stays on the internal ghost-academy network only. ga-portal (Caddy)
        # is always present and is the sole dashboard proxy; port allocation is
        # gated only on the per-launch dashboard flag.
        dashboard_url: str | None = None
        if effective_dashboard:
            with registry:
                try:
                    dashboard_port = _caddy_portal.allocate_port()
                except RuntimeError as _err:
                    _cleanup_crew(podman, container, volume, home_volume)
                    registry._reg["crews"].pop(crew_id, None)
                    return {"error": str(_err)}
            # Portal (Caddy) is the sole dashboard proxy. Scheme depends on TLS mode.
            _caddy_scheme = "http" if cfg.ga_portal_tls_mode == "off" else "https"
            if cfg.ga_host_url:
                from urllib.parse import urlparse as _urlparse2
                _p = _urlparse2(cfg.ga_host_url)
                _ui_host = f"{_caddy_scheme}://{_p.hostname}:{dashboard_port}"
            else:
                _ui_host = f"{_caddy_scheme}://localhost:{dashboard_port}"
            dashboard_url = f"{_ui_host}/"
            # Add the UI port origin to CORS so the SPA's API calls are accepted.
            container_env["KIROCREW_CORS_ORIGINS"] = (
                f"{container_env['KIROCREW_CORS_ORIGINS']},{_ui_host}"
            )

        # Generate the Admiral Ed25519 keypair BEFORE creating the container.
        # The private key is persisted host-side and never enters the container;
        # the public key is registered as a Podman secret and attached to the
        # container spec so it mounts read-only (immutable from inside the container
        # — CAP_SYS_ADMIN, needed to remount rw, is dropped). This must happen
        # before container_create because a Podman secret can only be attached at
        # creation time.
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PrivateFormat,
            PublicFormat,
            NoEncryption,
        )

        _admiral_private_key = Ed25519PrivateKey.generate()
        _admiral_private_seed = _admiral_private_key.private_bytes(
            Encoding.Raw, PrivateFormat.Raw, NoEncryption()
        )
        _admiral_public_bytes = _admiral_private_key.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )
        _admiral_secret_hex = _admiral_private_seed.hex()
        _admiral_secret_name = f"admiral-pubkey-{crew_id}"

        # Register the public key as a Podman secret for read-only delivery. This
        # MUST happen before container_create — a Podman secret can only be
        # attached to a container at creation time.
        podman.secret_create(_admiral_secret_name, _admiral_public_bytes)

        podman.container_create(
            name=container,
            image=image,
            env=container_env,
            network=GA_STARBOARD_NETWORK,
            workspace_volume=volume,
            home_volume=home_volume,
            # Mount the Admiral public key read-only, root-owned, 0444.
            # ADMIRAL_PUBKEY_PATH deliberately sits outside the home volume; see
            # the constant's definition for why a volume-backed target breaks
            # crew startup.
            secrets=[{
                "source": _admiral_secret_name,
                "target": ADMIRAL_PUBKEY_PATH,
                "uid": 0,
                "gid": 0,
                "mode": 0o444,
            }],
        )
        # Persist the private seed host-side so captain.py can sign standing
        # orders (same path/format as before — hex of the raw 32-byte seed).
        # Done right after create (before start) — standing orders only flow far
        # later, in _finish_crew_setup, so the private key is always on disk
        # before the crew can be signed to.
        _write_crew_secret(crew_id, _admiral_secret_hex)
        podman.container_start(container)
        logger.info("Started %s", container)

        crew_url = f"http://{container}:{CREW_GATEWAY_PORT}"
        if not _wait_gateway(crew_url, timeout=60):
            if dashboard_port is not None:
                _caddy_portal.release_port(dashboard_port)
            _cleanup_crew(podman, container, volume, home_volume)
            # D7c: the admiral secret file was written just above (before
            # container_start); remove it on this early-return failure path.
            try:
                _delete_crew_secret(crew_id)
            except Exception:
                pass
            with registry:
                registry._reg["crews"].pop(crew_id, None)
            return {"error": f"Gateway not ready within 60s for crew {crew_id}"}

        result = _finish_crew_setup(podman, crew_id, container, volume, home_volume, auth_b64, composition, composition_entry, admiral_secret=_admiral_secret_hex, dashboard=effective_dashboard, backend=backend)
        # _finish_crew_setup error-dict paths have already called _cleanup_crew
        # (removing the admiral secret and Podman resources). The registry placeholder
        # entry written before the try block still exists and must be removed here.
        if "error" in result:
            with registry:
                registry._reg["crews"].pop(crew_id, None)
            # D7c: _finish_crew_setup's error paths call _cleanup_crew (which
            # removes the Podman public-key secret) but not the host-side
            # admiral seed file written here before setup. Remove it too.
            try:
                _delete_crew_secret(crew_id)
            except Exception:
                pass
            if dashboard_port is not None:
                try:
                    _caddy_portal.release_port(dashboard_port)
                except Exception:
                    pass
            return result
        # Persist dashboard_port in registry and register with Caddy.
        # Portal is the sole dashboard proxy.
        if dashboard_port is not None and "error" not in result:
            _crew_cookie_for_caddy = ""
            with registry:
                if crew_id in registry._reg["crews"]:
                    registry._reg["crews"][crew_id]["dashboard_port"] = dashboard_port
                # Extract cookie value under the lock; register AFTER releasing it.
                _crew_cookie_for_caddy = registry._reg["crews"].get(crew_id, {}).get("cookie", "")
            # C-1: Call _caddy_register_crew AFTER releasing _registry_lock to
            # avoid holding the lock across up to 7 s of blocking I/O.
            _caddy_portal.register_crew(crew_id, dashboard_port, crew_cookie=_crew_cookie_for_caddy)
            # Record port→crew mapping for forward_auth lookups.
            _dashboard_gate.register_port(crew_id, dashboard_port)
            result["dashboard_url"] = dashboard_url
        elif "error" not in result:
            result["dashboard_url"] = None
        return result

    except Exception as e:
        logger.error("Launch failed for %s: %s", crew_id, e)
        try:
            _cleanup_crew(podman, container, volume, home_volume)
        except Exception:
            pass
        # D7c: remove the host-side admiral signing-secret file. _cleanup_crew
        # removes the Podman public-key secret but NOT the plaintext seed file
        # written by _write_crew_secret inside the try block. Without this the
        # file leaks on every failed launch (secret for a crew that no longer
        # exists). Best-effort — a failure before _write_crew_secret just no-ops.
        try:
            _delete_crew_secret(crew_id)
        except Exception:
            pass
        # Free any port allocated before the failure
        try:
            if dashboard_port is not None:
                _caddy_portal.release_port(dashboard_port)
        except Exception:
            pass
        with registry:
            registry._reg["crews"].pop(crew_id, None)
        return {"error": f"Launch failed: {e}"}


def _bg_prewarm(crew: dict, crew_id: str) -> None:
    """Fire-and-forget background prewarm. Non-fatal.

    Starts a daemon thread that calls _prewarm_crew; any exception is caught
    and logged at WARNING so that the calling tool is never blocked or failed
    by a prewarm error.  _prewarm_crew owns the GA_PREWARM_ENABLED gate and
    returns early when disabled, so no guard is needed here.
    """
    def _run() -> None:
        try:
            _prewarm_crew(crew, crew_id)
        except Exception as exc:
            logger.warning(
                "Background prewarm for %s failed (non-fatal): %s", crew_id, exc
            )
    threading.Thread(target=_run, daemon=True).start()


@_registry_guard
def supply(
    path: str,
    crew_id: str | None = None,
    unpack: bool = False,
    bundle: bool = False,
    force: bool = False,
) -> dict:
    """Step 2: seed the workspace — deliver a file, archive, or git bundle into a crew's workspace via a presigned upload URL.

    Always call supply before dispatching any task that touches the repo.
    Dispatching into an empty crew workspace is a real failure mode — the agent
    has no codebase to work with and will hallucinate or fail silently.

    Returns a URL to POST raw file bytes to. Use curl or any HTTP client
    to upload from your local machine — no credentials required beyond
    network access to the transport host.

    For directory trees, set unpack=True and POST a .tar or .tar.gz —
    it will be extracted at the given path in the workspace. For a real
    git checkout, set bundle=True and POST the output of ``git bundle create``;
    the bundle is cloned into the destination inside the crew.

    When bundle=True and force=True, any existing directory at the destination
    is removed before the bundle is cloned. Default force=False preserves the
    existing "reject occupied destination" behaviour.

    Pairs with evac, which extracts files, diffs, or git bundles out. Together
    they are the complete file exchange protocol for crew workspaces.
    Also: deliver, inject, upload, seed workspace, push file.

    Examples:
        # Single file
        curl -X POST <url> --data-binary @./myfile.py

        # Directory tree (tar)
        tar -czf - ./myrepo | curl -X POST "<url>&unpack=1" --data-binary @-

        # Git history (bundle)
        # IMPORTANT: always build a fresh bundle immediately before this call.
        # Never reuse a bundle built for a previous crew or at an earlier point
        # in time — a stale bundle silently seeds the crew with an outdated
        # repo snapshot, missing any commits made since the bundle was built.
        git bundle create /tmp/<crew_id>.bundle --all
        curl -X POST "<url>&bundle=1" --data-binary @/tmp/<crew_id>.bundle

        # Re-seed (force=True removes existing destination first)
        git bundle create /tmp/<crew_id>.bundle --all
        curl -X POST "<url>&bundle=1&force=1" --data-binary @/tmp/<crew_id>.bundle

    Args:
        path: Destination path in the workspace (e.g. "repo/config.json",
              "repo" when unpacking a tar, or "repo" for a bundle clone).
        crew_id: Which crew workspace to deliver into. Required.
        unpack: If True, the upload URL will unpack a tar/tar.gz at path.
        bundle: If True, the upload URL will clone a git bundle into path.
        force: When True with bundle=True, removes an existing destination
               before cloning. Default False preserves the existing "reject
               occupied destination" behaviour.
    """
    if unpack and bundle:
        return {"error": "unpack and bundle cannot both be True"}

    clean = path.lstrip("/")
    if ".." in clean.split("/"):
        return {"error": "Invalid path — no traversal allowed"}

    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}
    # TRN-238 QA-2: crew was nuked during restart — it no longer exists.
    if crew is _NUKED_DURING_RESTART:
        return {"error": f"Crew '{crew_id}' was removed while being started"}

    url = _sign_upload_url(crew_id, clean, unpack=unpack, bundle=bundle, force=force)
    if unpack:
        url += "&unpack=1"
    if bundle:
        url += "&bundle=1"
    if force:
        url += "&force=1"

    if bundle:
        curl_example = f'curl -X POST "{url}" --data-binary @./your-repo.bundle'
    elif unpack:
        curl_example = f'tar -czf - ./your-dir | curl -X POST "{url}" --data-binary @-'
    else:
        curl_example = f'curl -X POST "{url}" --data-binary @./your-file'

    _security.audit_auth_event(action="presign_supply", outcome="issued", source=None)
    _bg_prewarm(crew, crew_id)
    return {
        "crew_id": crew_id,
        "path": clean,
        "delivery_url": url,
        "method": "POST",
        "unpack": unpack,
        "bundle": bundle,
        "force": force,
        "expires_secs": 300,
        "example": curl_example,
    }


@_registry_guard
def evac(
    path: str,
    ref: str | None = None,
    crew_id: str | None = None,
    bundle: bool = False,
    pack: bool = False,
) -> dict:
    """Step 5: extract results, diffs, a git bundle, or a directory tar — extract files, diffs, git bundles, or directory trees from a crew workspace.

    Always evac before nuking — nuke is irreversible and the workspace is gone.
    Pairs with supply as the complete file exchange protocol for crew workspaces.

    Returns a direct download URL to the file on the transport server.
    Fetch the URL from any client that can reach the transport host —
    no LLM in the content path, works for binary and large files.
    Also: extract, exfil, pull, get file, show diff.

    Args:
        path: File path relative to the workspace root, or a directory
              containing a git repository when bundle=True, or a directory
              to extract as a tar archive when pack=True.
        ref: Optional git ref/range to diff against, or to bundle. With
             bundle=True and no ref, all reachable refs are bundled.
        crew_id: Which crew workspace to read from. Required.
        bundle: If True, return a git bundle instead of a file or diff.
        pack: If True, return a tar archive of the named directory instead
                of a single file. The response Content-Type is application/x-tar.
                Useful for evacuating multi-file output (generated reports,
                build artefact trees, subagent working directories, etc.).
                Example: curl -s "<url>" -o ./output.tar
                Note: prefer a specific subdirectory (e.g. subagent_<id>/) over
                the workspace root — large tars stream for the full URL TTL
                (300 s) and callers should scope the path accordingly.

    Note: pack and bundle cannot both be True.
    """
    if pack and bundle:
        return {"error": "pack and bundle cannot both be True"}

    clean = path.lstrip("/")
    if not clean:
        return {"error": "path must not be empty"}
    if ".." in clean.split("/"):
        return {"error": "Invalid path — no traversal allowed"}

    try:
        _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}

    url = _sign_file_url(crew_id, clean, ref, bundle, pack)
    _security.audit_auth_event(action="presign_evac", outcome="issued", source=None)
    result = {
        "crew_id": crew_id,
        "path": path,
        "bundle": bundle,
        "pack": pack,
        "expires_secs": 300,
    }
    if ref:
        result["ref"] = ref
    result["url"] = url
    return result


@_registry_guard
def nuke(crew_id: str, confirm: bool = False) -> dict:
    """Step 6: destroy the crew and both volumes when work is done — tear down its container and both volumes completely.

    Always evac first — nuke is irreversible. There is no undo.

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

    c_nuke = _to_crew(crew_id, crew)

    if not confirm:
        active: list = []
        try:
            tasks = _crew_api(crew, "GET", "/api/spawn")
            active = [a for a in tasks.get("agents", []) if not a.get("done")]
        except Exception:
            pass
        with registry:
            schedules = registry.get_schedules(crew_id)
        return {
            "warning": f"Pass confirm=True to tear down crew '{crew_id}'",
            "container": c_nuke.container or f"{CREW_CONTAINER_PREFIX}{crew_id}",
            "volumes": [c_nuke.volume or f"{CREW_VOLUME_PREFIX}{crew_id}", c_nuke.home_volume or f"{CREW_HOME_VOLUME_PREFIX}{crew_id}"],
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
    container = c_nuke.container or f"{CREW_CONTAINER_PREFIX}{crew_id}"
    vol = c_nuke.volume or f"{CREW_VOLUME_PREFIX}{crew_id}"
    home_vol = c_nuke.home_volume or f"{CREW_HOME_VOLUME_PREFIX}{crew_id}"
    try:
        if not container.startswith(CREW_CONTAINER_PREFIX):
            raise RuntimeError(f"Refusing to nuke non-crew container: {container!r}")
        if not vol.startswith(CREW_VOLUME_PREFIX):
            raise RuntimeError(f"Refusing to nuke non-crew volume: {vol!r}")
    except RuntimeError as e:
        return {"error": str(e)}

    # Cancel gateway cron jobs before teardown (best-effort). Use bare _crew_api
    # (not _crew_api_with_recovery) to avoid restarting a container we are about
    # to destroy.
    with registry:
        schedules = registry.get_schedules(crew_id)
    for sched in schedules:
        job_id = sched.get("job_id", "")
        if not job_id:
            # Captain entries (type=="captain") have no gateway cron job to cancel
            continue
        try:
            _crew_api(crew, "DELETE", f"/api/crons/{job_id}")
        except Exception as e:
            logger.warning("nuke: failed to cancel cron %s for crew %s: %s", job_id, crew_id, e)

    _cleanup_crew(podman, container, vol, home_vol)

    with registry:
        # Deregister from Caddy and release the port before removing the registry
        # entry. Portal is the sole dashboard proxy.
        _ui_p = registry._reg["crews"].get(crew_id, {}).get("dashboard_port")
        if _ui_p is not None:
            _caddy_portal.deregister_crew(crew_id)
            _dashboard_gate.release_port(int(_ui_p))
            _caddy_portal.release_port(int(_ui_p))
        # Explicitly drop any batch records so no orphan batch entry
        # survives a nuke. Popping the crew entry below already removes them,
        # but clearing here keeps the intent explicit and in the same atomic
        # write that removes the crew.
        _crew_entry = registry._reg["crews"].get(crew_id)
        if _crew_entry is not None:
            _crew_entry.pop("batches", None)
        registry._reg["crews"].pop(crew_id, None)

    with _captain_order_locks_lock:
        _captain_order_locks.pop(crew_id, None)

    # Remove the per-crew signing-secret file (best-effort).
    # Deregister the secret value first so it is no longer redacted from future
    # log output (I-4: prune _REGISTERED_SECRETS on nuke to avoid unbounded growth).
    _crew_signing_secret = _read_crew_secret(crew_id)
    if _crew_signing_secret:
        _security.deregister_secret(_crew_signing_secret)
    _delete_crew_secret(crew_id)

    # Evict per-crew in-memory state so nuked crew_ids do not accumulate
    # indefinitely in long-running transport processes.
    #
    # _recovery_locks / _startup_generation / _crew_restart_outcomes live in
    # lifecycle module-level dicts (and are mirrored in _launcher for the
    # restart path). _idle_skip_reasons lives in monitors.
    # These are all small objects (Lock, int, str, tuple) but grow without
    # bound across many launch+nuke cycles if not pruned here.
    try:
        from lifecycle import (  # container: flat /app/
            _recovery_locks, _recovery_locks_lock,
            _startup_events_lock, _startup_generation, _crew_restart_outcomes,
        )
    except ModuleNotFoundError:
        from transport.lifecycle import (  # local dev
            _recovery_locks, _recovery_locks_lock,
            _startup_events_lock, _startup_generation, _crew_restart_outcomes,
        )
    with _recovery_locks_lock:
        _recovery_locks.pop(crew_id, None)
    with _startup_events_lock:
        _startup_generation.pop(crew_id, None)
        _crew_restart_outcomes.pop(crew_id, None)
    try:
        try:
            from monitors import _idle_skip_reasons  # container: flat /app/
        except ModuleNotFoundError:
            from transport.monitors import _idle_skip_reasons  # local dev
        _idle_skip_reasons.pop(crew_id, None)
    except Exception:
        pass  # monitors may not be loaded yet (e.g. tests); skip silently

    logger.info("Crew %s nuked", crew_id)
    return {"crew_id": crew_id, "status": "nuked", "container": container}


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
    model: str | None = None,
) -> dict:
    """Autopilot: hand the full SDD lifecycle to a recurring Raven check-in — manage the single Raven-backed standing-orders Captain for a crew.

    Two paths: manual relay (you dispatch/pickup/steer each persona yourself),
    or Captain autopilot (a recurring Raven check-in drives the full cycle
    unattended). Captain is the autopilot path.

    ``order`` requires exactly one of ``message`` or ``template``. A named
    template is resolved before it is written to ``captain@localhost``;
    ``spec-driven-development`` (aliases: ``sdd``, ``specky``) is the built-in
    template and uses ``change_name`` to name the OpenSpec change it should
    drive — pass a comma-separated list for parallel multi-change execution
    with automatic worktree isolation.
    ``independent-review`` (alias: ``indy``) is the built-in review template;
    ``change_name`` is optional — when provided it scopes the review to that
    change; when omitted it reviews the entire codebase. The resolved order
    shares the same recurring Raven check-in as a hand-written message.
    ``stop`` pauses that check-in without deleting it, and ``status`` reports
    its durable state.

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
        template: Name of a built-in standing-order template. Available
            templates: ``spec-driven-development`` / ``sdd`` / ``specky``
            (single or multi-change lifecycle), ``independent-review`` /
            ``indy`` (scoped or whole-codebase review).
        change_name: Substitution value for a template. For ``sdd``, accepts
            a single change name or a comma-separated list for multi-change
            mode. For ``independent-review``, optional — omit to review the
            entire codebase.
        cron: Cron expression for a new standing-orders check-in.
        interval: Fixed interval in seconds for a new standing-orders check-in.
        timezone: IANA timezone for cron interpretation, matching schedule().
        fire_immediately: Whether to dispatch Raven once immediately when a
            new check-in is created. Defaults to True when interval is set,
            False when cron is set. Ignored on resume of a paused job.
        model: Optional model override for a newly created check-in job. Its
            format is validated on every call regardless of action; a
            syntactically valid value has no effect when resuming an existing
            job, since no new job is created, but an invalid value still
            returns an error.
    """
    if action not in {"order", "stop", "status"}:
        return {"error": "action must be one of: order, stop, status"}

    try:
        model = _validate_model(model)
    except ValueError as exc:
        return {"error": str(exc)}

    if action == "order":
        return _captain_do_order(
            crew_id,
            message,
            template,
            change_name,
            cron,
            interval,
            timezone,
            fire_immediately,
            model,
        )

    # Non-order actions accept only crew_id (and action). Reject any order-only
    # argument, including a non-default timezone.
    if any(
        value is not None
        for value in (message, template, change_name, cron, interval, fire_immediately, model)
    ) or timezone != "UTC":
        return {
            "error": f"{action} does not accept message, template, change_name, cron, interval, fire_immediately, model, or timezone"
        }

    if action == "status":
        return _captain_do_status(crew_id)
    return _captain_do_stop(crew_id)


@_registry_guard
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
    model: str | None = None,
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
        model: Optional model override for a newly created job. It is fixed at
            job creation and does not affect steer/continue operations.
    """
    if action not in ("create", "cancel", "list"):
        return {"error": "action must be one of: create, cancel, list"}

    try:
        model = _validate_model(model)
    except ValueError as exc:
        return {"error": str(exc)}

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

    # Delay creates a one-shot job
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
        if model is not None:
            body["model"] = model
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
            "model": model,
            "one_shot": True,
        }
        try:
            with registry:
                registry.upsert_schedule(crew_id, schedule_entry)
        except Exception as exc:
            logger.warning("Could not persist one-shot schedule entry: %s", exc)

        _bg_prewarm(crew, crew_id)
        return {
            "job_id": r.get("id"),
            "crew_id": crew_id,
            "name": name,
            "status": "scheduled",
            "delay": delay,
        }
    body: dict = {"name": name, "message": message, "agent": agent}
    if model is not None:
        body["model"] = model
    if cron:
        body["cron"] = cron
        body["timezone"] = timezone
    else:
        body["every"] = interval
    try:
        r = _crew_api_with_recovery(crew, crew_id, "POST", "/api/crons", json=body)
    except (CrewUnresponsiveError, RuntimeError) as e:
        return {"error": str(e)}

    # Write schedule entry to transport registry
    schedule_entry = {
        "job_id": r.get("id"),
        "name": name,
        "interval_secs": interval,
        "cron_expr": cron,
        "next_fire_at": time.time() + (interval or 60),
        "agent": agent,
        "message": message,
        "enabled": True,
        "model": model,
    }
    try:
        with registry:
            registry.upsert_schedule(crew_id, schedule_entry)
    except Exception as exc:
        logger.warning("Could not persist schedule entry: %s", exc)

    _bg_prewarm(crew, crew_id)

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
            immediate_body: dict[str, Any] = {
                "task": message,
                "agent": agent,
                "keep": True,
            }
            if model is not None:
                immediate_body["model"] = model
            try:
                _crew_api_with_recovery(
                    crew, crew_id, "POST", "/api/spawn", json=immediate_body,
                )
            except httpx.HTTPStatusError as exc:
                # Classify a gateway memory-pressure refusal consistently with the
                # captain path: tag it with the stable marker so callers/Raven can
                # recognise it. No counter here — generic scheduled jobs have no
                # captain escalation. (TRN-225)
                if _is_memory_pressure_refusal(exc.response):
                    raise _MemoryPressureSkip(
                        f"{_MEMORY_PRESSURE_MARKER} gateway refused spawn under memory pressure"
                    ) from exc
                raise
        except Exception as exc:
            result["immediate_dispatch_error"] = str(exc)

    return result


def _schedule_cancel(job_id: str | None, crew_id: str | None) -> dict:
    """Cancel (delete) a scheduled job by ID — removes from registry AND gateway."""
    if not job_id:
        return {"error": "job_id is required for action='cancel'"}
    if not crew_id:
        return {"error": "crew_id is required for action='cancel'"}

    # Check registry for captain guard before touching gateway
    try:
        with registry:
            schedules = registry.get_schedules(crew_id)
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

    # Remove from registry
    try:
        with registry:
            registry.remove_schedule(crew_id, job_id)
    except Exception as exc:
        logger.warning("Could not remove schedule entry from registry: %s", exc)

    return {"status": "cancelled", "job_id": job_id}


def _schedule_list(crew_id: str | None) -> dict:
    """List all scheduled jobs for a crew.

    Reads from the transport registry as the authoritative source.
    Falls back to the gateway if no registry entries exist (backward compat).
    """
    if not crew_id:
        return {"error": "crew_id is required"}

    # Read from registry first
    with registry:
        schedules = registry.get_schedules(crew_id)

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


@_registry_guard
def dispatch(
    task: str | None = None,
    agent: str = "ghost",
    crew_id: str | None = None,
    model: str | None = None,
    tasks: list[str] | None = None,
    slot: bool | None = None,
) -> dict:
    """Step 3: send a task to an agent persona — spawn a task (or a batch of tasks) on a KiroCrew agent for autonomous execution.

    The agent has zero context beyond the ``task`` string — be specific and
    self-contained. Use pickup as the next step to check progress or collect
    the result.

    Use this to send work to a ghost, spectre, banshee, wraith, reaper, or raven —
    research, coding, shell commands, file edits, anything that can run
    unattended. Always immediate — returns a task_id. For delayed execution,
    use schedule(delay=N) instead.
    Also: dropoff, send, assign.

    Single task: pass ``task=`` and get back one ``task_id``.

    Batch: pass ``tasks=[...]`` (a list of task strings) to dispatch N tasks
    atomically against the same crew. All tasks in a batch share the same
    ``agent``, ``model``, ``slot``, and ``crew_id``. The batch is dispatched
    sequentially against ``/api/spawn`` and recorded in the transport registry
    under a single ``batch_id``; the response includes ``batch_id`` and
    per-task ``task_ids``. The batch size must be between 2 and
    ``GA_BATCH_MAX_TASKS`` (default 20, read from the ``GA_BATCH_MAX_TASKS``
    env var). Collect batch results in one call with
    ``pickup(task_ids=[...], timeout_secs=N)``.

    ``task`` and ``tasks`` are mutually exclusive — supply exactly one. Existing
    single-task callers are unaffected.

    Returns:
        Single: ``{"task_id", "crew_id", "status": "dispatched", "task",
        "agent", "slot", "created_at"}``. ``slot`` echoes the resolved slot
        name, or ``None`` when headless.
        Batch (all started): ``{"batch_id", "task_ids", "crew_id",
        "status": "dispatched", "agent", "slot", "created_at"}``.
        Batch (crew died mid-dispatch): the same shape with ``status: "partial"``,
        the ``task_ids`` assigned so far, and an ``error`` field naming the
        failure. Tasks that never received a ``task_id`` are the lost members.

    Args:
        task: What to do (single dispatch). Be specific — the agent has no
            other context. Mutually exclusive with ``tasks``.
        agent: Which agent to use. Default is 'ghost' (general-purpose).
        crew_id: Which crew to dispatch to. Required — use launch first.
        model: Optional model override for this call only. It is the highest
            precedence level — it outranks the per-backend override
            (backends.<b>.model.override) and per-agent config. It has no effect
            on later steer/continue operations.
        tasks: A list of 2..GA_BATCH_MAX_TASKS task strings for atomic batch
            dispatch. Mutually exclusive with ``task``.
        slot: Dashboard session routing for this dispatch. One of:
            ``None`` (default) — let the system decide. For enrolled agents,
            routes into the agent's member DM slot
            (``parent_session="dashboard:member-<slug>"``), which is attested
            and visible in the dashboard as a named thread; the echoed slot
            name is the agent name (e.g. ``"ghost"``). For unenrolled agents,
            dispatches headless (no session created, echoed slot ``None``).
            ``False`` — explicit headless, regardless of enrollment: no session
            is created and the echoed slot is ``None``.
            ``True`` and arbitrary string slot names are no longer accepted —
            member slots cover all legitimate slotted-dispatch use cases. A
            member DM slot is pre-created at enrollment time, so no dispatch-time
            slot pre-creation is performed.

            MEMORY COST: a member-slot attachment spawns a kiro-cli-chat process
            inside the crew container (~300-400 MB RSS). For autonomous or
            unattended tasks (SDD, batch jobs, Raven check-ins) where dashboard
            visibility is not needed, pass ``slot=False`` to dispatch headless
            and avoid this overhead.
    """
    # Mutual-exclusion + presence guard (task 2.2).
    if task is not None and tasks is not None:
        return {"error": "Provide either task or tasks, not both"}
    if task is None and tasks is None:
        return {"error": "Provide task or tasks"}

    try:
        model = _validate_model(model)
    except ValueError as e:
        return {"error": str(e)}
    try:
        _validate_agent(agent)
    except ValueError as e:
        return {"error": str(e)}

    if tasks is not None:
        return _dispatch_batch(tasks, agent, crew_id, model, slot=slot)

    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}

    effective_slot, parent_session = _resolve_dispatch_slot(agent, slot, crew)

    body: dict[str, Any] = {"task": task, "agent": agent, "keep": True}
    if model is not None:
        body["model"] = model

    resolved_slot_name: str | None = None
    if parent_session:
        # Member DM auto-route (effective_slot is the agent name). The member
        # slot is pre-created at enrollment time, so no dispatch-time
        # slot pre-creation is needed. Headless dispatch leaves parent_session
        # unset (effective_slot is None).
        resolved_slot_name = effective_slot
        body["parent_session"] = parent_session

    try:
        result = _crew_api_with_recovery(
            crew, crew_id, "POST", "/api/spawn",
            json=body,
        )
    except CrewUnresponsiveError as e:
        return {"error": str(e)}

    task_id = result.get("id")
    if not task_id:
        return {"error": "spawn returned no task id"}
    now = datetime.now(timezone.utc)
    created_at = now.isoformat()

    # Record task timestamps in-memory
    with _task_timestamps_lock:
        _task_timestamps[task_id] = {
            "created_at": created_at,
            "started_at": None,
            "completed_at": None,
        }

    # Write last_task_at to crew's registry entry
    _record_last_task_at(crew_id, created_at)

    response: dict[str, Any] = {
        "task_id": task_id,
        "crew_id": crew_id,
        "status": "dispatched",
        "task": task,
        "agent": agent,
        "slot": resolved_slot_name,
        "created_at": created_at,
    }
    return response


@_registry_guard
def steer(
    task_id: str,
    message: str,
    crew_id: str | None = None,
    force: bool = False,
) -> dict:
    """Step 4b: redirect a running task or continue a completed session — guide a running task mid-flight, or continue a completed one.

    Running vs completed matters: a running task receives a /steer redirect;
    a completed task resumes via /continue with full prior context intact.
    Use force=True to hard-stop a running task before resuming its session.

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


@_registry_guard
def pickup(
    task_id: str | None = None,
    crew_id: str | None = None,
    timeout_secs: int = 0,
    agent: str | None = None,
    task_ids: list[str] | None = None,
) -> dict | list:
    """Step 4: check progress or collect the result — check a task's progress, retrieve its completed result, or list all tasks.

    With a task_id: returns current state including mail counts. Sessions are
    preserved after completion — use steer to continue or redirect the session,
    or nuke to destroy the crew when work is done. Also: collect, get result, check progress.

    With a task_ids list (batch pickup): polls every listed task and returns a
    dict keyed by task_id, each value the full single-task pickup shape, plus
    top-level ``done`` (True only when every member is done), ``completed_tasks``,
    and ``total_tasks``. When ``timeout_secs > 0`` the call blocks until all
    tasks are done, the timeout fires, or new Admiral mail arrives; each polling
    round is capped at ``GA_PICKUP_MAX_POLL_SECS`` (default 30 s), and a capped
    return carries ``"reason": "timeout"`` — re-call to keep waiting. With
    ``timeout_secs == 0`` it returns a one-shot snapshot of each task. Admiral
    mail arriving mid-poll returns early with ``"reason": "admiral_mail"``. A
    task the gateway does not know about (404) is reported as
    ``{"task_id", "done": false, "lost": true, "error": "task not found in gateway"}``
    rather than failing the whole batch; the batch ``done`` is then ``false``.
    ``task_id`` and ``task_ids`` are mutually exclusive.

    Without a task_id: returns all tasks currently running or recently finished
    in the crew, plus a per-agent mail summary. Also: list, overview,
    what's happening.

    Without a task_id and with agent set to a persona name (ghost, spectre,
    banshee, wraith, reaper, raven): returns only that agent's mailbox subjects
    and count — no task list, no other mailbox data. agent is ignored when
    task_id is set.

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
        agent: Optional persona name filter (ghost, spectre, banshee, wraith,
            reaper, raven). When set and task_id is None, returns only that
            agent's mailbox subjects and count. Ignored when task_id is set.
        task_ids: A list of task IDs for blocking batch pickup. Mutually
            exclusive with task_id. Must be non-empty.
    """
    # Batch mutual-exclusion + empty guards (tasks 4.2, 4.3).
    if task_id is not None and task_ids is not None:
        return {"error": "Provide either task_id or task_ids, not both"}
    if task_ids is not None and len(task_ids) == 0:
        return {"error": "task_ids must not be empty"}

    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return {"error": str(e)}

    try:
        podman = _get_podman()
    except Exception as e:
        return {"error": str(e)}

    container = _to_crew(crew_id, crew).container
    effective_timeout = min(max(0, timeout_secs), 30) if timeout_secs > 0 else 0

    if task_ids is not None:
        # Route to the batch pickup orchestrator in lifecycle.py, injecting the
        # single-task pickup and mail-count helpers to avoid a lifecycle->server
        # import cycle. effective_timeout already applies the standard cap.
        # Look up the batch_id so _pickup_batch can mark the batch complete
        # when all members finish (spec: "batch status SHALL be updated to
        # complete when all tasks complete"). Best-effort — if the batch record
        # is not found (e.g. caller assembled task_ids manually, or registry was
        # reset) pickup still works; the status just won't be updated.
        batch_record = _find_batch_by_task_ids(crew_id, task_ids)
        found_batch_id = batch_record["batch_id"] if batch_record else None
        return _pickup_batch(
            crew, crew_id, task_ids, podman, container, effective_timeout,
            _pickup_single, _read_all_mail_counts,
            batch_id=found_batch_id,
            update_batch_status=_update_batch_status,
        )

    if task_id:
        return _pickup_single(crew, crew_id, task_id, podman, container, effective_timeout)
    elif agent is not None:
        # Agent filter: validate and return single-inbox subjects only
        if agent not in PERSONA_ALLOWLIST:
            return {
                "error": (
                    f"Invalid agent {agent!r}. Must be one of: "
                    + ", ".join(sorted(PERSONA_ALLOWLIST))
                )
            }
        all_subjects = _skim_all_mailboxes(podman, container)
        subjects = all_subjects.get(agent, [])
        return {
            "agent": agent,
            "subjects": subjects,
            "mail": len(subjects),
        }
    else:
        return _pickup_list(crew, crew_id, podman, container, effective_timeout)


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


def resource_orders() -> str:
    """Return a summary index of available order templates (name + description only)."""
    templates = _list_order_templates()
    if not templates:
        return "No standing-order templates are available."
    lines = [f"{name}: {description}" for name, description in templates]
    return "\n".join(lines)


def resource_orders_by_name(name: str) -> str:
    """Return the full resolved body of a single order template by name."""
    try:
        _description, body = _load_order_template(name)
    except ValueError:
        return f"Not found: no standing-order template named {name!r}. Use transport://orders to list available templates."
    return _substitute_placeholders(body)


def resource_version() -> str:
    """Return transport version and per-crew image versions from registry."""
    with registry:
        _crews_snapshot = dict(registry._reg.get("crews", {}))
    crews_versions = {}
    for cid, info in _crews_snapshot.items():
        crews_versions[cid] = {
            "crew_image_version": info.get("crew_image_version", "unknown")
        }
    return json.dumps({
        "transport": TRANSPORT_VERSION,
        "crews": crews_versions,
    })


def resource_jobs() -> str:
    """Return a plain-text listing of all scheduled jobs across all crews.

    Includes delay-type (one-shot) jobs from the transport registry alongside
    recurring jobs from the gateway.
    """
    with registry:
        _crews_snapshot = dict(registry._reg.get("crews", {}))

    if not _crews_snapshot:
        return "No running crews found."

    sections = []
    for crew_id, info in _crews_snapshot.items():
        lines = [f"## {crew_id}"]
        gateway_jobs_shown = set()

        # Include registry jobs (delay-type and all tracked)
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



# ──────────────────────────────────────────────────────────────────────────────
# Tool/resource registration
# ──────────────────────────────────────────────────────────────────────────────

def register_tools(mcp_instance, caddy_portal, dashboard_gate) -> None:
    """Register every MCP tool and resource against ``mcp_instance``.

    ``server.py`` owns the ``mcp`` instance and the ``CaddyPortal`` /
    ``DashboardGate`` objects; it calls this once after constructing them and
    before ``mcp.streamable_http_app(...)`` / ``get_mcp_tools(mcp)`` in
    ``__main__``. The two objects are stashed into module globals so the
    module-level ``launch`` / ``nuke`` functions can read them.

    The decorators are applied programmatically here — equivalent to the
    ``@mcp.tool()`` / ``@mcp.resource(...)`` decorators that previously sat
    above each function in ``server.py``. ``functools.wraps`` was already
    applied where needed (``_registry_guard``), so tool introspection (name,
    signature, docstring) is unchanged.
    """
    global _caddy_portal, _dashboard_gate
    _caddy_portal = caddy_portal
    _dashboard_gate = dashboard_gate

    # Tools (plain @mcp.tool()).
    mcp_instance.tool()(crews)
    mcp_instance.tool()(launch)
    mcp_instance.tool()(supply)
    mcp_instance.tool()(evac)
    mcp_instance.tool()(nuke)
    mcp_instance.tool()(captain)
    mcp_instance.tool()(schedule)
    mcp_instance.tool()(dispatch)
    mcp_instance.tool()(steer)
    mcp_instance.tool()(pickup)

    # Resources (@mcp.resource(...) with explicit metadata).
    mcp_instance.resource(
        "transport://compositions",
        name="compositions",
        title="Available Crew Compositions",
        description="Lists the crew compositions available for launch — name, description, and optional image override for each.",
        mime_type="text/plain",
    )(resource_compositions)
    mcp_instance.resource(
        "transport://agents",
        name="agents",
        title="Available Crew Agents",
        description="Describes the agents available for dispatch to a crew — name, role, and when to use each.",
        mime_type="text/plain",
    )(resource_agents)
    mcp_instance.resource(
        "transport://orders",
        name="orders",
        title="Standing-Order Templates",
        description="Summary index of available standing-order templates — name and description only. Use transport://orders/{name} to fetch a template's full resolved body.",
        mime_type="text/plain",
    )(resource_orders)
    mcp_instance.resource(
        "transport://orders/{name}",
        name="orders_by_name",
        title="Standing-Order Template",
        description="Returns the full resolved body of the named standing-order template, with all placeholders substituted and front-matter stripped. Use transport://orders to list available templates.",
        mime_type="text/plain",
    )(resource_orders_by_name)
    mcp_instance.resource(
        "transport://version",
        name="version",
        title="Transport and Crew Image Versions",
        description="Returns the transport process version and, for each running crew, its crew image version.",
        mime_type="application/json",
    )(resource_version)
    mcp_instance.resource(
        "transport://jobs",
        name="jobs",
        title="Scheduled Jobs",
        description="Lists all scheduled jobs across all running crews — job_id, name, schedule, agent, enabled, last_run, last_status.",
        mime_type="text/plain",
    )(resource_jobs)
