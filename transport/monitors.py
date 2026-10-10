"""transport/monitors.py — background schedule/idle monitor threads.

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
# injected via bind_lifecycle(). It was never part of the monitors↔lifecycle
# load-time cycle that bind_lifecycle() exists to break.
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
# (see above), because it is a plain constant, not part of the module cycle.
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
                    # Captain entries are driven by _captain_monitor, not here
                    if sched.get("type") == "captain":
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

                    # Check gateway enabled state — gateway is source of truth.
                    # After waking the crew, fetch /api/crons and check whether this
                    # specific job is still enabled. The registry may lag behind a
                    # `kirocrew cron pause` issued inside the container (syncs on
                    # restart). Fail-open: if the fetch raises, proceed.
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
                        # Write last_checkin_at for captain check-ins
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

                    # H-2: For one-shot (delay) jobs, disable the
                    # schedule in the registry FIRST (durable safety gate that
                    # prevents the annual cron expression from replaying if the
                    # gateway DELETE fails), then best-effort delete the cron
                    # from the gateway.
                    if sched.get("one_shot"):
                        job_id = sched.get("job_id")
                        if job_id:
                            # Step 1: mark disabled in registry (durable gate)
                            try:
                                with _registry_lock:
                                    _reg = _load_registry()
                                    for _s in _get_crew_schedules(_reg, crew_id):
                                        if _s.get("job_id") == job_id:
                                            _s["enabled"] = False
                                            _s["next_fire_at"] = _NEVER_FIRE_AT
                                            break
                                    _save_registry(_reg)
                            except Exception as e:
                                logger.warning(
                                    "Schedule monitor: could not disable one-shot cron %s in registry: %s",
                                    job_id, e,
                                )
                            # Step 2: best-effort DELETE from gateway
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


# Last reason each idle crew was kept running, so the reason is logged once
# when it changes rather than every interval.
_idle_skip_reasons: dict[str, str] = {}


def _note_idle_skip(crew_id: str, reason: str) -> None:
    """Record why an idle crew was not stopped; log only when the reason changes."""
    if _idle_skip_reasons.get(crew_id) != reason:
        _idle_skip_reasons[crew_id] = reason
        logger.info("Idle crew %s kept running: %s", crew_id, reason)


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
                try:
                    if not podman.container_is_running(info["container"]):
                        continue
                except Exception as e:
                    logger.warning(
                        "Idle monitor: transient Podman error for crew %s — skipping: %s",
                        crew_id, e,
                    )
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
                            _note_idle_skip(crew_id, "spawn check: cookie refresh failed")
                            continue
                    if r.status_code != 200:
                        # Activity is unknown after any non-success response — fail open.
                        _note_idle_skip(crew_id, f"spawn check: HTTP {r.status_code}")
                        continue
                    payload = r.json()
                    if not isinstance(payload, dict):
                        # A successful response with an unusable shape is still unknown activity.
                        _note_idle_skip(crew_id, "spawn check: unexpected response")
                        continue
                    agents = payload.get("agents")
                    if not isinstance(agents, list):
                        _note_idle_skip(crew_id, "spawn check: no agent list")
                        continue
                    active = [
                        agent for agent in agents
                        if isinstance(agent, dict) and not agent.get("done")
                    ]
                    if active:
                        # Tasks still running — update last_used and skip.
                        _note_idle_skip(crew_id, "tasks running")
                        _touch_crew(crew_id)
                        continue
                except Exception as e:
                    _note_idle_skip(crew_id, f"spawn check error: {type(e).__name__}")
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
                            _note_idle_skip(crew_id, "cron check: cookie refresh failed")
                            continue
                    if r.status_code != 200:
                        # Activity is unknown after any non-success response — fail open.
                        _note_idle_skip(crew_id, f"cron check: HTTP {r.status_code}")
                        continue
                    cron_payload = r.json()
                    if not isinstance(cron_payload, dict):
                        # A successful response with an unusable shape is still unknown activity.
                        _note_idle_skip(crew_id, "cron check: unexpected response")
                        continue
                    if not isinstance(cron_payload.get("jobs"), list):
                        _note_idle_skip(crew_id, "cron check: no job list")
                        continue
                    if _cron_activity_since(cron_payload, last_used) or _cron_has_enabled_job(
                        cron_payload
                    ):
                        _note_idle_skip(crew_id, "cron job enabled or recently ran")
                        _touch_crew(crew_id)
                        continue
                except Exception as e:
                    _note_idle_skip(crew_id, f"cron check error: {type(e).__name__}")
                    continue

                logger.info(
                    "Crew %s idle for %.0fs — stopping container",
                    crew_id, idle_secs,
                )
                # TOCTOU guard: re-read last_used from the live registry and
                # perform the stop while the lock is held, so a _touch_crew
                # call that lands between our HTTP checks and the stop cannot
                # race us.  The design (D3) requires the re-check AND the stop
                # to be atomic with respect to _touch_crew (which also acquires
                # _registry_lock).  Holding the lock across container_stop adds
                # latency bounded by Podman's stop timeout — acceptable per the
                # design risk analysis.
                stop_failed = False
                with _registry_lock:
                    live_reg = _load_registry()
                    live_last_used = live_reg.get("crews", {}).get(crew_id, {}).get("last_used", 0)
                    if now - live_last_used < GA_IDLE_TIMEOUT_SECS:
                        _note_idle_skip(crew_id, "last_used advanced during checks — skipping stop")
                        continue
                    try:
                        podman.container_stop(info["container"])
                    except Exception as e:
                        # One crew's stop failure must not end idle reaping for every crew.
                        logger.warning("Could not stop idle crew %s: %s", crew_id, e)
                        stop_failed = True
                    if not stop_failed:
                        _idle_skip_reasons.pop(crew_id, None)
                        reg = _load_registry()
                        if crew_id in reg["crews"]:
                            reg["crews"][crew_id]["status"] = "stopped"
                            _save_registry(reg)
                if stop_failed:
                    continue
        except Exception:
            # Never let one bad iteration end idle reaping for the process.
            logger.exception("Idle monitor iteration failed; retrying next interval")



# ── Captain monitor ───────────────────────────────────────────────────────────

_CAPTAIN_MONITOR_INTERVAL: int = 30  # seconds between scans when no entry is due


def _captain_monitor() -> None:
    """Background thread: drive Captain dispatch+steer check-ins.

    Runs as a daemon thread — exits automatically when the process exits.
    Scans the registry every _CAPTAIN_MONITOR_INTERVAL seconds (or sooner
    when an entry is due) and fires ``_steer_captain_checkin`` for each
    enabled captain entry whose ``next_fire_at`` has passed.

    Captain entries (type == "captain") are managed entirely by the transport
    registry; there is no gateway cron job for Captain.  This loop is the
    replacement for the gateway cron timer.
    """
    # Import here to avoid circular import (same pattern as _schedule_monitor).
    # These are injected via bind_lifecycle() for _crew_api_with_recovery and
    # _ensure_crew_running.  For _steer_captain_checkin and
    # _dispatch_captain_checkin we import from server at call time (they are
    # defined there, not in lifecycle) to avoid a module-load cycle.
    while True:
        next_wakeup = time.time() + _CAPTAIN_MONITOR_INTERVAL  # initialised before try so sleep line is always defined
        try:
            with _registry_lock:
                reg = _load_registry()
                crew_items = list(reg["crews"].items())

            now = time.time()
            next_wakeup = now + _CAPTAIN_MONITOR_INTERVAL

            for crew_id, info in crew_items:
                schedules = info.get("schedules", [])
                for sched in schedules:
                    if sched.get("type") != "captain":
                        continue
                    if not sched.get("enabled", True):
                        continue
                    next_fire = sched.get("next_fire_at", _NEVER_FIRE_AT)
                    # Track earliest upcoming fire for sleep duration
                    if next_fire > now and next_fire < next_wakeup:
                        next_wakeup = next_fire
                    if next_fire > now:
                        continue

                    # Entry is due — wake the crew and steer/dispatch
                    try:
                        crew = _ensure_crew_running(info, crew_id)
                    except Exception as e:
                        logger.warning(
                            "Captain monitor: crew %s won't start for check-in: %s",
                            crew_id, e,
                        )
                        _advance_next_fire_at(sched)
                        with _registry_lock:
                            reg2 = _load_registry()
                            for s in _get_crew_schedules(reg2, crew_id):
                                if s.get("type") == "captain":
                                    s["next_fire_at"] = sched["next_fire_at"]
                                    break
                            _save_registry(reg2)
                        continue

                    # Import _steer_captain_checkin from server at call time
                    # to avoid a module-load cycle (server imports monitors).
                    try:
                        try:
                            from server import (  # container: flat /app/
                                _steer_captain_checkin,
                                _dispatch_captain_checkin,
                            )
                        except ModuleNotFoundError:
                            from transport.server import (  # local dev  # type: ignore[no-redef]
                                _steer_captain_checkin,
                                _dispatch_captain_checkin,
                            )
                        _steer_captain_checkin(crew, crew_id)
                    except Exception as e:
                        logger.error(
                            "Captain monitor: check-in failed for crew %s: %s",
                            crew_id, e,
                        )

                    # Advance next_fire_at in registry
                    _advance_next_fire_at(sched)
                    with _registry_lock:
                        reg3 = _load_registry()
                        for s in _get_crew_schedules(reg3, crew_id):
                            if s.get("type") == "captain":
                                s["next_fire_at"] = sched["next_fire_at"]
                                break
                        _save_registry(reg3)

        except Exception:
            logger.exception("Captain monitor iteration failed; retrying next interval")

        # Sleep until the next due entry, or _CAPTAIN_MONITOR_INTERVAL
        sleep_secs = max(1.0, next_wakeup - time.time())
        time.sleep(sleep_secs)
