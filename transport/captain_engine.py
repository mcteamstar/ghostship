"""Captain dispatch/steer engine — extracted from server.py (TRN-242).

Owns the Captain check-in lifecycle: the memory-pressure probe and
classification helpers, the Admiral escalation mail path, and the
dispatch/steer/order/status/stop engine that the ``captain()`` MCP tool
and ``monitors.py::_captain_monitor`` delegate to.

Key exports:
  _dispatch_captain_checkin   — dispatch a new captain check-in task
  _steer_captain_checkin      — steer a running captain check-in task
  _captain_do_order           — implement the ``order`` sub-command
  _captain_do_status          — implement the ``status`` sub-command
  _captain_do_stop            — implement the ``stop`` sub-command
  _check_in_memory_pressure   — probe for memory pressure before check-in
  _mail_admiral               — send an escalation mail to admiral@localhost
  _record_memory_pressure_cycle — persist a memory-pressure skip cycle

Dependency boundary: this module is a leaf below ``server``/``tools`` — it
imports only from ``config``, ``registry``, ``captain``, ``lifecycle`` and
``podman``. It must NOT import from ``server`` or ``tools``. Extracting it
here breaks the former ``monitors.py -> server`` deferred call-time import:
``monitors.py`` now imports ``_dispatch_captain_checkin`` /
``_steer_captain_checkin`` from this leaf directly.
"""

from __future__ import annotations

import logging
import time
from typing import Any

try:
    import httpx2 as httpx  # container: flat /app/
except ModuleNotFoundError:
    import httpx  # local dev / test stub

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config  # local dev

try:
    from registry import registry  # container: flat /app/
except ModuleNotFoundError:
    from transport.registry import registry  # local dev

try:
    from captain import (  # container: flat /app/
        _CAPTAIN_CHECKIN_JOB_NAME,
        _CAPTAIN_CHECKIN_TASK,
        _append_captain_mail,
        _captain_order_lock,
        _captain_standing_view,
        _delete_sentinel_file,
        _parse_sentinel_file,
        _read_sentinel_file,
        _resolve_order_template,
        _skim_all_mailboxes,
    )
except ModuleNotFoundError:
    from transport.captain import (  # local dev
        _CAPTAIN_CHECKIN_JOB_NAME,
        _CAPTAIN_CHECKIN_TASK,
        _append_captain_mail,
        _captain_order_lock,
        _captain_standing_view,
        _delete_sentinel_file,
        _parse_sentinel_file,
        _read_sentinel_file,
        _resolve_order_template,
        _skim_all_mailboxes,
    )

# ── lifecycle functions (resolved LAZILY via _lc() — see cycle note) ──────────
# captain_engine needs _require_crew, _ensure_crew_running, _crew_api_with_recovery,
# _to_crew and _write_dashboard_cookie from lifecycle. Importing lifecycle at
# module-load time would reintroduce a load cycle: lifecycle imports monitors at
# its tail (eager `_monitors._schedule_monitor`), and monitors now imports this
# module at top level. If captain_engine is loaded via `import transport.monitors`
# first, a top-level `from lifecycle import ...` here would drive lifecycle to
# load and re-enter the still-initialising monitors module, raising AttributeError.
# So the lifecycle module is resolved on first use through _lc() and cached, by
# which point lifecycle is fully loaded. This mirrors the deferred-import
# discipline the monitors<->lifecycle boundary already uses via bind_lifecycle().
_lifecycle_mod = None


def _lc():
    """Return the fully-loaded lifecycle module, importing it on first use."""
    global _lifecycle_mod
    if _lifecycle_mod is None:
        try:
            import lifecycle as _lc_mod  # container: flat /app/
        except ModuleNotFoundError:
            from transport import lifecycle as _lc_mod  # local dev
        _lifecycle_mod = _lc_mod
    return _lifecycle_mod

try:
    from podman import _get_podman, _get_host_memory_gb_cached  # container: flat /app/
except ModuleNotFoundError:
    from transport.podman import _get_podman, _get_host_memory_gb_cached  # local dev

logger = logging.getLogger(__name__)

# Module-level config singleton — the captain engine reads the two spawn/memory
# pressure thresholds it needs from here rather than from server globals.
cfg = Config.from_env()
GA_RESOURCE_CRITICAL_GB = cfg.ga_resource_critical_gb
GA_SPAWN_PRESSURE_ESCALATE_CYCLES = cfg.ga_spawn_pressure_escalate_cycles


_MEMORY_PRESSURE_MARKER = "memory_pressure:"


class _MemoryPressureSkip(RuntimeError):
    """Raised when a Captain check-in dispatch is skipped (or refused) because
    the host is under critical memory pressure. A thin RuntimeError subclass so
    the fire path can catch it separately from any other dispatch error without
    string-sniffing."""


def _check_in_memory_pressure() -> float | None:
    """Return host available memory (GB) when BELOW the critical threshold,
    else None.

    None also means "probe unavailable → fail open": when the podman client or
    the memory reading is not available we return None so the caller dispatches
    anyway, letting the gateway's own refusal (D4) be the backstop rather than
    freezing the crew on a missing probe.
    """
    try:
        podman = _get_podman()
        free_gb = _get_host_memory_gb_cached(podman)
    except Exception:
        return None
    if free_gb is None:
        return None  # fail open: no probe, do not block the crew
    return free_gb if free_gb < GA_RESOURCE_CRITICAL_GB else None


def _is_memory_pressure_refusal(resp) -> bool:
    """True when ``resp`` is a gateway spawn refusal caused by host memory
    pressure (HTTP 429/503 whose body names memory pressure or insufficient
    memory). A 503-still-spawning body (no "memory" token) is NOT a match, so it
    stays on the normal _crew_api_with_recovery retry path."""
    try:
        if resp.status_code not in (429, 503):
            return False
        body = (resp.text or "").lower()
    except Exception:
        return False
    return "memory" in body and ("pressure" in body or "insufficient" in body)


def _mail_admiral(crew_id: str, subject: str, body: str) -> None:
    """Deliver one message to admiral@localhost from inside the crew container
    via /usr/local/bin/maildeliver (the atomic Maildir delivery path documented
    in STANDING_ORDERS.md). Best-effort: a delivery failure is logged, never
    raised, so an escalation attempt cannot break the fire path."""
    try:
        crew = _lc()._require_crew(crew_id)
        container = _lc()._to_crew(crew_id, crew).container
        if not container:
            logger.warning("Admiral escalation for crew %s: no container to deliver mail", crew_id)
            return
        from datetime import datetime as _dt, timezone as _tz
        import uuid as _uuid

        header_ts = _dt.now(_tz.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        message = (
            f"From: transport@localhost\r\n"
            f"To: admiral@localhost\r\n"
            f"Subject: {subject}\r\n"
            f"Message-ID: <{_uuid.uuid4()}@localhost>\r\n"
            f"Date: {header_ts}\r\n"
            f"\r\n"
            f"{body}\r\n"
        ).encode("utf-8")
        podman = _get_podman()
        podman.container_exec_stdin(
            container,
            ["/usr/local/bin/maildeliver", "admiral@localhost"],
            message,
        )
    except Exception as exc:
        logger.warning("Admiral escalation mail for crew %s failed: %s", crew_id, exc)


def _record_memory_pressure_cycle(crew_id: str) -> None:
    """Increment the captain schedule's consecutive_memory_pressure_skips counter
    (treating a missing field as 0), persist it under _registry_lock, and fire a
    single edge-triggered Admiral escalation when the post-increment value EQUALS
    GA_SPAWN_PRESSURE_ESCALATE_CYCLES (so it mails exactly once on the crossing,
    not on every subsequent cycle while the counter stays at/above the bound)."""
    n = 0
    with registry:
        for s in registry.get_schedules(crew_id):
            if s.get("type") == "captain":
                n = int(s.get("consecutive_memory_pressure_skips", 0) or 0) + 1
                s["consecutive_memory_pressure_skips"] = n
                break
    if n == GA_SPAWN_PRESSURE_ESCALATE_CYCLES:
        _mail_admiral(
            crew_id,
            subject=f"captain check-in deferred — sustained memory pressure {crew_id}",
            body=(
                f"{n} consecutive check-in cycles for crew {crew_id} were "
                f"deferred because host available memory stayed below "
                f"{GA_RESOURCE_CRITICAL_GB}GB. SDD progress is paused until "
                f"memory pressure drops."
            ),
        )


def _dispatch_captain_checkin(
    crew,
    crew_id: str,
    model: str | None = None,
) -> str:
    """Dispatch Raven into its member-raven slot for a Captain check-in.

    Calls POST /api/spawn with keep=True and parent_session=dashboard:member-raven
    so the session is attested and can make downstream spawns.  Returns the
    new task_id.  Raises on failure — callers are responsible for error
    handling.

    Must be called after _enroll_crew_members has run (member-raven slot must
    exist).  Verifies enrollment before dispatching; raises ValueError if
    raven is not enrolled.
    """
    c = _lc()._to_crew(crew_id, crew)
    enrolled: frozenset[str] = frozenset(c.enrolled_agents or [])
    if "raven" not in enrolled:
        # Fallback: read enrolled_agents from registry (crew may be a stale
        # minimal copy from _require_crew before _ensure_crew_running enriched it)
        try:
            with registry:
                crew_info = registry._reg.get("crews", {}).get(crew_id, {})
                enrolled = frozenset(crew_info.get("enrolled_agents") or [])
        except Exception:
            pass
    if "raven" not in enrolled:
        raise ValueError(
            f"Crew {crew_id}: raven is not enrolled — cannot dispatch Captain check-in. "
            "Re-launch the crew to enroll members."
        )
    # Refresh .dashboard_cookie so Raven (and any sub-agents she spawns) can use
    # cookie auth for all REST calls. Read internal_cookie from registry — it is
    # loopback-bound and safe to use from inside the container. If absent (old
    # registry row), skip silently — _refresh_cookie will populate it next cycle.
    try:
        with registry:
            internal_cookie = registry._reg.get("crews", {}).get(crew_id, {}).get("internal_cookie", "")
        if internal_cookie:
            podman = _get_podman()
            _lc()._write_dashboard_cookie(podman, c.container, internal_cookie)
    except Exception as exc:
        logger.warning("Captain dispatch: could not refresh .dashboard_cookie for crew %s: %s", crew_id, exc)
    spawn_body: dict[str, Any] = {
        "task": _CAPTAIN_CHECKIN_TASK,
        "agent": "raven",
        "keep": True,
        "parent_session": "dashboard:member-raven",
    }
    # Deterministic model selection for Claude-backend crews (TRN-210 D3).
    # raven.json carries a GPT-specific model, so on a Claude-backend crew a
    # dispatch with model=None would otherwise rely on raven.json's model (wrong
    # runtime) or a silent gateway fallback. When the crew is on the Claude
    # backend (acp_backend == "claude", or its configured model is a Claude model
    # string) and the caller supplied no model, pass the crew's configured model
    # explicitly so Raven is always dispatched on a compatible model.
    if model is None:
        crew_backend = c.acp_backend or None
        # model is not a standard Crew field — read from the dict if available,
        # otherwise fall through to the registry fallback.
        crew_model: str | None = crew.get("model") if isinstance(crew, dict) else None
        if not crew_backend or crew_model is None:
            # read authoritative values from the registry
            try:
                with registry:
                    crew_info = registry._reg.get("crews", {}).get(crew_id, {})
                if not crew_backend:
                    crew_backend = crew_info.get("acp_backend")
                if crew_model is None:
                    crew_model = crew_info.get("model")
            except Exception:
                pass
        is_claude_crew = crew_backend == "claude" or (
            isinstance(crew_model, str) and crew_model.startswith("claude")
        )
        if is_claude_crew and crew_model:
            model = crew_model
    if model is not None:
        spawn_body["model"] = model
    # Pre-dispatch host-memory probe (TRN-225): skip the spawn WITHOUT calling
    # /api/spawn when the host is under critical memory pressure. Fail-open when
    # the probe is unavailable (helper returns None).
    low_gb = _check_in_memory_pressure()
    if low_gb is not None:
        logger.warning(
            "Captain check-in for crew %s deferred: host at %sGB free "
            "(< %sGB critical) — memory pressure",
            crew_id, low_gb, GA_RESOURCE_CRITICAL_GB,
        )
        raise _MemoryPressureSkip(
            f"{_MEMORY_PRESSURE_MARKER} host at {low_gb}GB free "
            f"(< {GA_RESOURCE_CRITICAL_GB}GB critical) — check-in deferred"
        )
    # A gateway-side memory-pressure refusal (one that slipped past the probe
    # because the gateway threshold is stricter) is re-raised as the same typed
    # skip and NOT routed through _crew_api_with_recovery's in-cycle retries.
    #
    # Note: _crew_api_with_recovery's _phase0_transient_503 retries all 503
    # responses up to 4× before re-raising. When the gateway returns a
    # memory-pressure 503, phase0 will retry it 4× (~4 s) before the error
    # propagates here for classification. The probe (D3) prevents this in the
    # common case (same threshold on both sides); the retry overhead only occurs
    # in the narrow window where the gateway's threshold is stricter than
    # GA_RESOURCE_CRITICAL_GB. Fixing this properly requires a body-check inside
    # _phase0_transient_503 (lifecycle.py), which is outside this change's
    # declared footprint; tracked as a follow-on for lifecycle.py.
    try:
        result = _lc()._crew_api_with_recovery(crew, crew_id, "POST", "/api/spawn", json=spawn_body)
    except httpx.HTTPStatusError as exc:
        if _is_memory_pressure_refusal(exc.response):
            logger.warning(
                "Captain check-in for crew %s refused by gateway under memory pressure",
                crew_id,
            )
            raise _MemoryPressureSkip(
                f"{_MEMORY_PRESSURE_MARKER} gateway refused spawn under memory pressure"
            ) from exc
        raise
    task_id = result.get("id") if isinstance(result, dict) else None
    if not task_id:
        raise RuntimeError(
            f"Crew {crew_id}: POST /api/spawn returned no task id: {result!r}"
        )
    return task_id


def _steer_captain_checkin(
    crew,
    crew_id: str,
    model: str | None = None,
) -> str:
    """Continue or re-dispatch the Captain check-in for crew_id.

    Reads current_task_id from the registry and calls POST /api/spawn/{id}/continue.
    Updates current_task_id in the registry on success.

    Recovery paths:
    - conversation_gone (404): falls back to _dispatch_captain_checkin()
    - conversation_busy (409): logs warning, returns existing task_id unchanged
    - Other errors: re-raises after logging

    Returns the (possibly new) task_id.
    """
    with registry:
        schedules = registry.get_schedules(crew_id)
    captain_sched = next(
        (s for s in schedules if s.get("type") == "captain"),
        None,
    )
    current_task_id = captain_sched.get("current_task_id") if captain_sched else None
    saved_model = captain_sched.get("model") if captain_sched else None
    effective_model = model or saved_model

    if not current_task_id:
        # No task yet — fresh dispatch
        return _dispatch_captain_checkin(crew, crew_id, model=effective_model)

    # Refresh .dashboard_cookie so Raven's cookie auth stays current before continuing.
    # Use internal_cookie (loopback-bound) — skip if absent, _refresh_cookie will populate.
    try:
        with registry:
            internal_cookie = registry._reg.get("crews", {}).get(crew_id, {}).get("internal_cookie", "")
        if internal_cookie:
            podman = _get_podman()
            _lc()._write_dashboard_cookie(podman, _lc()._to_crew(crew_id, crew).container, internal_cookie)
    except Exception as exc:
        logger.warning("Captain steer: could not refresh .dashboard_cookie for crew %s: %s", crew_id, exc)

    # Try to continue the existing session
    continue_body: dict[str, Any] = {"task": _CAPTAIN_CHECKIN_TASK}
    if effective_model:
        continue_body["model"] = effective_model
    try:
        result = _lc()._crew_api_with_recovery(
            crew, crew_id, "POST", f"/api/spawn/{current_task_id}/continue",
            json=continue_body,
        )
    except Exception as exc:
        err_str = str(exc)
        # /continue returns 404 with code "conversation_gone" when the session
        # is no longer available (container restart, etc.).
        # TRN-230: /continue also returns 400 Bad Request when the Raven task
        # has completed and its session is gone — _crew_api_with_recovery now
        # re-raises this as a raw HTTPStatusError rather than routing to
        # phase-1 stale-cookie recovery.  Treat it the same as 404: fall back
        # to a fresh dispatch and clear the stale current_task_id.
        if "conversation_gone" in err_str or "404" in err_str or ("400 Bad Request" in err_str and "/continue" in err_str):
            logger.info(
                "Captain check-in: session %s gone for crew %s (400/404) — re-dispatching",
                current_task_id, crew_id,
            )
            # Clear the stale current_task_id so the next monitor tick doesn't
            # retry this dead session.
            try:
                with registry:
                    for s in registry.get_schedules(crew_id):
                        if s.get("type") == "captain":
                            s["current_task_id"] = None
                            break
            except Exception as clear_exc:
                logger.warning(
                    "Captain check-in: could not clear current_task_id for crew %s: %s",
                    crew_id, clear_exc,
                )
            return _dispatch_captain_checkin(crew, crew_id, model=effective_model)
        # /continue returns 409 with code "conversation_busy" when mid-turn
        if "conversation_busy" in err_str or "409" in err_str:
            logger.warning(
                "Captain check-in: session %s busy for crew %s — skipping this tick",
                current_task_id, crew_id,
            )
            return current_task_id
        raise

    # /continue returns a new id for the continuation run
    new_task_id = result.get("id") if isinstance(result, dict) else None
    if not new_task_id:
        logger.warning(
            "Captain check-in: /continue for crew %s returned no id — keeping %s",
            crew_id, current_task_id,
        )
        return current_task_id

    # Persist the new task_id
    try:
        with registry:
            for s in registry.get_schedules(crew_id):
                if s.get("type") == "captain":
                    s["current_task_id"] = new_task_id
                    from datetime import datetime as _dt, timezone as _tz
                    s["last_checkin_at"] = _dt.now(_tz.utc).isoformat()
                    break
    except Exception as exc:
        logger.warning(
            "Captain check-in: could not persist new task_id %s for crew %s: %s",
            new_task_id, crew_id, exc,
        )
    return new_task_id


def _captain_do_order(
    crew_id: str,
    message: str | None,
    template: str | None,
    change_name: str | None,
    cron: str | None,
    interval: int | None,
    timezone: str,
    fire_immediately: bool | None,
    model: str | None,
) -> dict:
    """Handle ``captain(action="order")``.

    Validates the order arguments, resolves a template when given, wakes the
    crew, provisions/resumes the Captain dispatch+steer loop, persists the
    schedule entry, and appends the standing order to ``captain@localhost``.
    ``action`` and ``model`` are already validated by the ``captain()``
    dispatcher.

    The Captain no longer uses a gateway cron job.  Instead, Raven is dispatched
    into its member-raven slot (which carries a captured execution_context that
    allows downstream spawning).  Subsequent check-ins are driven by
    ``_captain_monitor`` in monitors.py, which calls ``_steer_captain_checkin``
    at each ``next_fire_at`` interval.
    """
    has_message = message is not None
    has_template = template is not None
    if has_message == has_template:
        return {"error": "order requires exactly one of message or template"}
    if cron is not None and interval is not None:
        return {"error": "Provide cron or interval, not both"}
    if has_template:
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

    try:
        crew = _lc()._require_crew(crew_id)
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}

    try:
        crew = _lc()._ensure_crew_running(crew, crew_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        return {"error": str(exc)}

    with _captain_order_lock(crew_id):
        # Check registry for an existing captain entry
        with registry:
            existing_schedules = registry.get_schedules(crew_id)
        existing_entry = next(
            (s for s in existing_schedules if s.get("type") == "captain"),
            None,
        )

        is_new_entry = existing_entry is None
        if is_new_entry and not cron and not interval:
            return {
                "error": "A new Captain check-in requires either cron or interval",
            }

        # Resolve effective interval/cron — new entries require a schedule;
        # resuming an existing entry reuses the stored one when not overridden.
        effective_interval = interval
        effective_cron = cron
        effective_model = model
        if not is_new_entry and existing_entry is not None:
            if effective_interval is None and effective_cron is None:
                effective_interval = existing_entry.get("interval_secs")
                effective_cron = existing_entry.get("cron_expr")
            if effective_model is None:
                effective_model = existing_entry.get("model")

        # Build the new schedule entry
        now = time.time()
        if effective_interval:
            next_fire = now + effective_interval
        else:
            # cron schedule: fire in at most 60s for first fire, then the
            # monitor will respect the cron expression via next_fire_at.
            # Exact cron scheduling is future work; for now treat cron as
            # interval=60 for the first fire and store cron_expr for display.
            next_fire = now + 60

        schedule_entry: dict[str, Any] = {
            "type": "captain",
            "name": _CAPTAIN_CHECKIN_JOB_NAME,
            "interval_secs": effective_interval,
            "cron_expr": effective_cron,
            "next_fire_at": next_fire,
            "agent": "raven",
            "message": _CAPTAIN_CHECKIN_TASK,
            "enabled": True,
            "model": effective_model,
            "current_task_id": existing_entry.get("current_task_id") if existing_entry else None,
        }

        try:
            with registry:
                registry.upsert_schedule(crew_id, schedule_entry)
        except Exception as exc:
            logger.warning("Could not persist captain schedule entry: %s", exc)

        # Clear any stale sentinel file so the new order runs fresh (TRN-243).
        # Best-effort — a failure here does not block the order.
        try:
            _delete_sentinel_file(_get_podman(), _lc()._to_crew(crew_id, crew).container)
        except Exception as _sentinel_exc:
            logger.warning("Captain order: could not clear sentinel for crew %s: %s", crew_id, _sentinel_exc)

        # Only append an order after the schedule entry exists.  A
        # failed provisioning call must not leave mail that no Raven can read.
        try:
            podman = _get_podman()
            _append_captain_mail(podman, _lc()._to_crew(crew_id, crew).container, order_message, crew_id=crew_id)
        except Exception as exc:
            return {"error": f"Could not write Captain order: {exc}"}

        result: dict[str, Any] = {
            "crew_id": crew_id,
            "action": "order",
            "status": "ordered",
            "mode": "standing-orders",
            "job_id": None,  # no gateway cron — kept for API compatibility
            "mailbox": "captain@localhost",
            "schedule": effective_cron or (
                f"every {effective_interval}s" if effective_interval else None
            ),
        }

        # Determine whether to fire immediately
        if is_new_entry:
            should_fire = fire_immediately if fire_immediately is not None else (effective_interval is not None)
        else:
            # Resume: fire immediately only if explicitly requested
            should_fire = fire_immediately is True

        if should_fire:
            try:
                new_task_id = _dispatch_captain_checkin(crew, crew_id, model=effective_model)
                # Persist the task_id and updated next_fire_at
                if effective_interval:
                    fired_next = time.time() + effective_interval
                else:
                    fired_next = time.time() + 60
                with registry:
                    for s in registry.get_schedules(crew_id):
                        if s.get("type") == "captain":
                            s["current_task_id"] = new_task_id
                            s["next_fire_at"] = fired_next
                            # Successful dispatch clears any accumulated
                            # memory-pressure skips so a later sustained-pressure
                            # run re-arms the Admiral escalation. (TRN-225)
                            s["consecutive_memory_pressure_skips"] = 0
                            from datetime import datetime as _dt, timezone as _tz
                            s["last_checkin_at"] = _dt.now(_tz.utc).isoformat()
                            break
                result["current_task_id"] = new_task_id
            except _MemoryPressureSkip as exc:
                # Memory-pressure skip/refusal: do NOT advance current_task_id
                # (so the dispatch is retried on a later cycle), count the cycle,
                # and let _record_memory_pressure_cycle handle edge-triggered
                # Admiral escalation. (TRN-225)
                result["immediate_dispatch_error"] = str(exc)
                _record_memory_pressure_cycle(crew_id)
            except Exception as exc:
                result["immediate_dispatch_error"] = str(exc)
        elif not is_new_entry and existing_entry is not None:
            # Resume path: existing enabled captain, steer on next timer tick.
            # Ensure the entry is enabled in the registry (it may have been stopped).
            result["current_task_id"] = existing_entry.get("current_task_id")

        return result


def _captain_do_status(crew_id: str) -> dict:
    """Handle ``captain(action="status")``.

    Skims all mailboxes (works on running and stopped containers) and reports
    the durable standing-orders state without waking a dormant crew.

    Reads captain state from the transport registry rather than the gateway
    cron API — no need to wake the crew for a status check.
    """
    try:
        crew = _lc()._require_crew(crew_id)
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}

    c_status = _lc()._to_crew(crew_id, crew)
    action = "status"
    podman = _get_podman()
    # Single call — covers all 8 mailboxes; falls back to archive API on
    # stopped containers.
    agent_mail = _skim_all_mailboxes(podman, c_status.container)
    captain_subjects = agent_mail.get("captain", [])
    admiral_subjects = agent_mail.get("admiral", [])
    captain_mail = len(captain_subjects)
    admiral_mail = len(admiral_subjects)

    # Read captain state from registry — no need to wake the crew
    with registry:
        schedules = registry.get_schedules(crew_id)
    captain_entry = next(
        (s for s in schedules if s.get("type") == "captain"),
        None,
    )

    if captain_entry is None:
        return {
            "crew_id": crew_id,
            "action": action,
            "status": "dormant",
            "mode": "standing-orders",
            "job_id": None,
            "enabled": False,
            "unread_mail": captain_mail,
            "mailbox": "captain@localhost",
            "captain_subjects": captain_subjects,
            "captain_mail": captain_mail,
            "unread_admiral_mail": admiral_mail,
            "admiral_mailbox": "admiral@localhost",
            "admiral_subjects": admiral_subjects,
            "admiral_mail": admiral_mail,
            "agent_mail": agent_mail,
        }

    # Build a synthetic "job" dict from the registry entry for _captain_standing_view
    synthetic_job: dict[str, Any] = {
        "id": None,  # no gateway cron id
        "enabled": captain_entry.get("enabled", True),
        "last_run_ts": None,
        "last_status": None,
        "last_result": None,
    }
    # If the crew is running, check if the current task is still alive
    try:
        is_running = podman.container_is_running(c_status.container)
    except Exception:
        is_running = False

    current_task_id = captain_entry.get("current_task_id")
    if is_running and current_task_id:
        try:
            running_crew = _lc()._ensure_crew_running(crew, crew_id)
            task_info = _lc()._crew_api_with_recovery(
                running_crew, crew_id, "GET", f"/api/spawn/{current_task_id}"
            )
            if isinstance(task_info, dict):
                synthetic_job["last_status"] = "running" if not task_info.get("done") else "ok"
        except Exception:
            pass  # best-effort — status still works without task liveness

    status_result = _captain_standing_view(
        crew_id,
        action,
        synthetic_job,
        podman,
        c_status.container,
    )
    status_result["captain_subjects"] = captain_subjects
    status_result["admiral_subjects"] = admiral_subjects
    status_result["captain_mail"] = captain_mail
    status_result["admiral_mail"] = admiral_mail
    status_result["agent_mail"] = agent_mail
    status_result["current_task_id"] = current_task_id

    # Report sentinel file presence (TRN-243) — best-effort, no error on failure.
    try:
        sentinel_content = _read_sentinel_file(podman, c_status.container)
        if sentinel_content is not None:
            status_result["sentinel"] = _parse_sentinel_file(sentinel_content)
        else:
            status_result["sentinel"] = None
    except Exception:
        status_result["sentinel"] = None

    return status_result


def _captain_do_stop(crew_id: str) -> dict:
    """Handle ``captain(action="stop")``.

    Marks the captain schedule entry disabled in the transport registry.
    No gateway cron to disable — the Captain no longer uses a cron job.
    The crew does not need to be running to stop the Captain.
    """
    try:
        crew = _lc()._require_crew(crew_id)
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}

    c_stop = _lc()._to_crew(crew_id, crew)
    podman = _get_podman()

    # Read captain entry from registry — no need to wake the crew
    with registry:
        schedules = registry.get_schedules(crew_id)
    captain_entry = next(
        (s for s in schedules if s.get("type") == "captain"),
        None,
    )

    if captain_entry is None:
        return {
            "crew_id": crew_id,
            "action": "stop",
            "status": "dormant",
            "mode": "standing-orders",
            "job_id": None,
            "enabled": False,
            "mailbox": "captain@localhost",
        }

    # Mark disabled in registry — this is the only action needed.
    # The _captain_monitor will skip disabled entries on its next tick.
    try:
        with registry:
            matched = False
            for sched in registry.get_schedules(crew_id):
                if sched.get("type") == "captain":
                    sched["enabled"] = False
                    matched = True
                    break
            if not matched:
                logger.warning(
                    "captain stop: no captain registry entry found for crew %s",
                    crew_id,
                )
    except Exception as exc:
        logger.warning("captain stop: could not update registry for crew %s: %s", crew_id, exc)

    stopped_entry = dict(captain_entry)
    stopped_entry["enabled"] = False

    result = _captain_standing_view(
        crew_id,
        "stop",
        stopped_entry,
        podman,
        c_stop.container,
    )
    result["status"] = "stopped"
    return result
