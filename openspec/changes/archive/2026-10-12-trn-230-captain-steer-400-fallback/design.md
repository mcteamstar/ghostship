# Design

## Context

See Wraith investigation report (carrier task `b87079e565bc33d2`, evac'd to `/tmp/trn-230-report.md`).

Three functions involved:
- `lifecycle.py:_crew_api_with_recovery` — routes 400 to stale-cookie recovery indiscriminately
- `server.py:_steer_captain_checkin` — catches exceptions but only handles "404"/"conversation_gone", not "400 Bad Request" wrapped in CrewUnresponsiveError
- `monitors.py:_captain_monitor` — advances schedule but never clears `current_task_id`

## Goals / Non-Goals

**Goals:**
- Fix the 400-on-/continue misroute in `_crew_api_with_recovery`
- Fix the fallback condition in `_steer_captain_checkin`
- Clear `current_task_id` on fallback so subsequent ticks don't retry the dead task

**Non-Goals:**
- Changing the phase-1 stale-cookie logic for other routes
- Introducing a new exception type (the string-match approach is sufficient)

## Decisions

**Fix in `_crew_api_with_recovery`** — add a guard before the phase-1 branch:

```python
# Before routing 400 to phase-1, check if this is a /continue call.
# A 400 on /continue means the session is gone (not a stale cookie).
if status == 400 and "/continue" in path:
    raise  # re-raise HTTPStatusError; caller handles "session gone"
return _phase1_stale_cookie(crew, crew_id, method, path, **kw)
```

This is the minimal change: a single `if` before the existing `_phase1_stale_cookie` call. It only affects the `/continue` route for 400 — all other 400s still go through phase-1 unchanged.

**Fix in `_steer_captain_checkin`** — extend the conversation-gone check and clear `current_task_id`:

```python
# Current:
if "conversation_gone" in err_str or "404" in err_str:
    return _dispatch_captain_checkin(...)

# After:
if "conversation_gone" in err_str or "404" in err_str or "400 Bad Request" in err_str:
    # Clear stale task ID before re-dispatching so next tick doesn't retry it
    _clear_captain_task_id(crew_id)  # or inline registry update
    logger.info("Captain: session %s gone (400/404) — re-dispatching for crew %s",
                current_task_id, crew_id)
    return _dispatch_captain_checkin(crew, crew_id, model=effective_model)
```

`_clear_captain_task_id` can be an inline registry update:
```python
with _registry_lock:
    reg = _load_registry()
    for s in _get_crew_schedules(reg, crew_id):
        if s.get("type") == "captain":
            s["current_task_id"] = None
            break
    _save_registry(reg)
```

**Why "400 Bad Request" not just "400"?** The string `"400"` is too broad (could match port numbers, task IDs, etc.). `"400 Bad Request"` is the exact httpx error message format and is specific enough.

## Risks / Trade-offs

**False positive on "400 Bad Request"** — very low risk. The string only appears in httpx `HTTPStatusError` messages for actual HTTP 400 responses, and only surfaces here via `CrewUnresponsiveError` when phase-1 exhausts its retries. No other normal error path produces this string.

**Registry clear race** — the registry update to clear `current_task_id` happens outside the monitor's main lock. This is fine: `current_task_id` is advisory state used to route the next tick; a brief race where two ticks both try to dispatch is safe because the second one will also hit a completed-or-missing task and re-dispatch or succeed normally.
