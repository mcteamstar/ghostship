"""transport/monitors.py — background schedule/idle monitor threads (TRN-116).

Extracted from lifecycle.py to improve navigability.  This module owns the two
daemon-thread loops that run for the life of the transport process:

  * ``_schedule_monitor`` — polls the registry for due scheduled jobs and fires
    them against each crew's gateway.
  * ``_idle_monitor`` — stops crew containers that have been idle past
    ``GA_IDLE_TIMEOUT_SECS`` and have no active tasks or crons.

plus their cron-activity helpers ``_cron_activity_since`` and
``_cron_has_enabled_job``.

Dependency direction (design.md D-1 exception): monitors needs a few runtime
functions from ``lifecycle`` (``_ensure_crew_running``, ``_crew_api``,
``_crew_api_with_recovery``, ``_mint_cookie`` and the loop constants) and is
imported only by ``server`` and re-exported by ``lifecycle``.  To keep the
import graph genuinely acyclic — so ``import transport.monitors`` and
``import transport.lifecycle`` both work as the FIRST transport module a fresh
interpreter loads — monitors does NOT import lifecycle at module load.  Instead
``lifecycle`` injects those objects via ``bind_lifecycle()`` at the end of its
own module body (see below).  The leaf-module helpers monitors needs
(``_http``/``_get_podman`` from podman, the registry helpers) are imported
directly from those leaf modules so a patch on ``monitors.*`` in tests targets
the same call-site name the loop actually resolves.

Dual-path import pattern (container flat layout vs. local dev package):
    try:
        import monitors as _monitors        # /app/monitors.py  (container)
    except ModuleNotFoundError:
        from transport import monitors as _monitors  # local dev
"""

from __future__ import annotations

import logging
import time
from typing import Any

try:
    from podman import _get_podman, _http  # container: flat /app/
except ModuleNotFoundError:
    from transport.podman import _get_podman, _http  # local dev

try:
    from registry import (  # container: flat /app/
        _NEVER_FIRE_AT,
        _registry_lock,
        _load_registry,
        _save_registry,
        _get_crew_schedules,
        _advance_next_fire_at,
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
        _touch_crew,
    )

# CREW_GATEWAY_PORT is a plain integer constant with no transport dependencies,
# so it is imported directly from the zero-dependency constants leaf rather than
# injected via bind_lifecycle() (TRN-142). It was never part of the
# monitors↔lifecycle load-time cycle that bind_lifecycle() exists to break.
try:
    from constants import CREW_GATEWAY_PORT  # container: flat /app/
except ModuleNotFoundError:
    from transport.constants import CREW_GATEWAY_PORT  # local dev

# ── lifecycle bindings (injected, NOT imported — see below) ───────────────────
# monitors needs a handful of runtime functions and constants from lifecycle
# (_ensure_crew_running, _crew_api, _crew_api_with_recovery, _mint_cookie and
# the loop constants). We deliberately do NOT import them at module load: doing
# so creates a load-time cycle, because lifecycle re-exports this module's loop
# functions (from monitors import _schedule_monitor …) so that server and the
# test suite can reach them via lifecycle.*. Importing lifecycle here while
# lifecycle is still mid-import (whenever monitors or lifecycle is the first
# transport module a fresh interpreter loads) raises
# "cannot import name … (most likely due to a circular import)".
#
# Instead lifecycle calls bind_lifecycle() at the end of its own module body —
# after every referenced name is defined — to inject the real objects into this
# module's globals. The loop functions reference these as bare module globals,
# so (a) after injection they resolve to lifecycle's live functions, and (b)
# tests can still patch them via patch.object(monitors, "_crew_api", …), the
# call-site-patching principle the suite relies on. The placeholders below make
# the names exist as module attributes before injection so tooling that imports
# monitors standalone does not see an AttributeError.
#
# CREW_GATEWAY_PORT is NOT injected — it is imported directly from constants
# (see above), because it is a plain constant, not part of the cycle (TRN-142).
GA_IDLE_TIMEOUT_SECS: float = 0.0
_SCHEDULE_MONITOR_INTERVAL: int = 30
_ensure_crew_running: Any = None
_crew_api: Any = None
_crew_api_with_recovery: Any = None
_mint_cookie: Any = None


def bind_lifecycle(
    *,
    ga_idle_timeout_secs: float,
    schedule_monitor_interval: int,
    ensure_crew_running: Any,
    crew_api: Any,
    crew_api_with_recovery: Any,
    mint_cookie: Any,
) -> None:
    """Inject lifecycle's runtime functions/constants into this module.

    Called once by ``lifecycle`` at the end of its module body. Breaks the
    monitors↔lifecycle load-time import cycle while keeping every name a
    real, patchable module attribute of ``monitors``.
    """
    global GA_IDLE_TIMEOUT_SECS, _SCHEDULE_MONITOR_INTERVAL
    global _ensure_crew_running, _crew_api, _crew_api_with_recovery, _mint_cookie
    GA_IDLE_TIMEOUT_SECS = ga_idle_timeout_secs
    _SCHEDULE_MONITOR_INTERVAL = schedule_monitor_interval
    _ensure_crew_running = ensure_crew_running
    _crew_api = crew_api
    _crew_api_with_recovery = crew_api_with_recovery
    _mint_cookie = mint_cookie


logger = logging.getLogger("transport.lifecycle")


# ── Schedule monitor ──────────────────────────────────────────────────────────

def _schedule_monitor() -> None:
    """Background thread: poll for due scheduled jobs and fire them.

    Runs as a daemon thread — exits automatically when the process exits.
    Loop interval: _SCHEDULE_MONITOR_INTERVAL (30 s).

    Per cycle, for each crew in the registry the monitor may take one of
    three actions:
      1. Skip disabled or not-yet-due jobs (next_fire_at > now).
      2. Wake the crew via _ensure_crew_running and fire a tick via POST
         /api/spawn (advancing next_fire_at on success, logging on failure).
      3. Advance next_fire_at and persist to the registry even when the crew
         cannot be woken (error path), so a broken crew never blocks others.
    """
    while True:
        # ── Interval sleep ───────────────────────────────────────────────────
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

                    # TRN-108: check gateway enabled state — gateway is source of truth.
                    # After waking the crew, fetch /api/crons and check whether this
                    # specific job is still enabled. The registry may lag behind a
                    # `kirocrew cron pause` issued inside the container (TRN-82 only
                    # syncs on restart). Fail-open: if the fetch raises, proceed.
                    job_id = sched.get("job_id")
                    try:
                        cron_payload = _crew_api(crew, "GET", "/api/crons")
                        gateway_jobs = (
                            cron_payload.get("jobs", [])
                            if isinstance(cron_payload, dict)
                            else []
                        )
                        gateway_job = next(
                            (
                                j
                                for j in gateway_jobs
                                if isinstance(j, dict) and j.get("id") == job_id
                            ),
                            None,
                        )
                        if gateway_job is not None and not gateway_job.get("enabled", True):
                            logger.info(
                                "Schedule monitor: job %s on crew %s is disabled in"
                                " gateway — skipping and syncing registry",
                                job_id,
                                crew_id,
                            )
                            with _registry_lock:
                                reg = _load_registry()
                                crew_scheds = _get_crew_schedules(reg, crew_id)
                                for s in crew_scheds:
                                    if s.get("job_id") == job_id:
                                        s["enabled"] = False
                                        break
                                _save_registry(reg)
                            continue
                    except Exception as e:
                        logger.warning(
                            "Schedule monitor: could not fetch gateway cron state"
                            " for job %s on crew %s: %s — proceeding",
                            job_id,
                            crew_id,
                            e,
                        )
                        # Fail-open: proceed to fire if gateway unreachable after wake.

                    # Fire the tick
                    fired = False
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
                        fired = True
                    except Exception as e:
                        logger.error(
                            "Schedule monitor: tick dropped — failed to fire job %s on crew %s: %s",
                            sched.get("job_id"), crew_id, e,
                        )

                    if fired:
                        # Advance next_fire_at in registry only on success
                        # TRN-89 task 4: write last_checkin_at for captain check-ins
                        _advance_next_fire_at(sched)
                        with _registry_lock:
                            reg = _load_registry()
                            crew_scheds = _get_crew_schedules(reg, crew_id)
                            for s in crew_scheds:
                                if s.get("job_id") == sched.get("job_id"):
                                    s["next_fire_at"] = sched["next_fire_at"]
                                    if (
                                        sched.get("name") == "captain"
                                        and sched.get("agent") == "raven"
                                    ):
                                        from datetime import datetime as _datetime, timezone as _tz
                                        s["last_checkin_at"] = _datetime.now(_tz.utc).isoformat()
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

    Runs as a daemon thread — exits automatically when the process exits.
    Loop interval: max(GA_IDLE_TIMEOUT_SECS, 10) seconds between cycles.
    Idle-stop threshold: GA_IDLE_TIMEOUT_SECS seconds since last_used.

    A crew is considered idle and eligible for stop when ALL hold:
      - Container is running (stopped crews are already handled).
      - No active dispatched tasks (checked via GET /api/spawn).
      - No in-flight or recently-completed cron jobs (checked via GET /api/crons).
      - No enabled cron jobs that have not yet fired (a standing commitment).
      - last_used is at least GA_IDLE_TIMEOUT_SECS seconds in the past.

    Stopped containers are restarted transparently on next use by
    _ensure_crew_running.  The monitor fails open on any check error — if
    activity cannot be verified, the crew is left running.
    """
    while True:
        # ── Interval sleep ───────────────────────────────────────────────────
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
