# Design

## Context

`_idle_monitor` in `transport/monitors.py` decides whether to stop an idle crew by checking two sources of activity:
1. `/api/spawn` — active dispatched tasks
2. `/api/crons` — gateway cron jobs (running or enabled)

Captain check-ins (0.6.0+) are transport-side: they live as `type: "captain"` entries in the transport registry and are driven by `_captain_monitor`, with no corresponding gateway cron. The idle monitor has no visibility into them and stops crews between check-ins.

## Goals / Non-Goals

**Goals:**
- Hold crews alive when a captain schedule entry is enabled and has a real `next_fire_at`
- Minimal diff — no new functions, no new data structures

**Non-Goals:**
- Fixing the `_captain_monitor` restart→steer failure path (separate issue)
- Changing how captain entries are stored or advanced

## Decisions

**Check registry directly, before the `/api/crons` HTTP call**

Registry captain entries are already in memory (loaded from disk at the top of the idle monitor loop). The check is a single `any()` over `info.get("schedules", [])` — no I/O, no new lock acquisitions. It goes right before the `/api/crons` block, mirroring the symmetry of the gateway cron check.

```python
# Captain entries are transport-side — check registry, not /api/crons
if any(
    s.get("type") == "captain"
    and s.get("enabled", True)
    and s.get("next_fire_at", _NEVER_FIRE_AT) < _NEVER_FIRE_AT
    for s in info.get("schedules", [])
):
    _note_idle_skip(crew_id, "captain check-in scheduled")
    _touch_crew(crew_id)
    continue
```

`_touch_crew` is called to keep `last_used` fresh, consistent with how the gateway cron path handles it.

**`_NEVER_FIRE_AT` as the sentinel for "no pending fire"**

A captain entry that has been stopped (`captain stop`) or completed (one-shot fired) has `next_fire_at == _NEVER_FIRE_AT`. Using this sentinel is consistent with how `_advance_next_fire_at` marks completed one-shot jobs and is already tested elsewhere in the monitors suite.

## Risks / Trade-offs

**Crew stays up indefinitely if captain is never stopped** — intentional. A captain schedule is a standing commitment; the crew should stay up. The operator calls `captain stop` to remove it.

**`_touch_crew` call advances `last_used`** — this is correct: the crew is being kept alive for an explicit reason, so its activity timestamp should reflect that.
