# Design — TRN-225 Cron spawn refused under memory pressure

All line numbers are against the current ghostship checkout read while writing
this proposal; treat them as anchors, re-confirm at implementation time.

## Current state (source-grounded)

### `transport/server.py`

- `_dispatch_captain_checkin(crew, crew_id, model=None)` begins at **line 3131**.
  It verifies raven enrollment, refreshes `.dashboard_cookie`, builds
  `spawn_body` (`task`, `agent="raven"`, `keep=True`,
  `parent_session="dashboard:member-raven"`), optionally picks a Claude model,
  then at **line 3212** calls:
  ```python
  result = _crew_api_with_recovery(crew, crew_id, "POST", "/api/spawn", json=spawn_body)
  task_id = result.get("id") if isinstance(result, dict) else None
  if not task_id:
      raise RuntimeError(... "returned no task id" ...)
  return task_id
  ```
  There is **no host-memory probe** here — it dispatches unconditionally.

- The captain fire path (around **line 3460–3484**) wraps the dispatch:
  ```python
  if should_fire:
      try:
          new_task_id = _dispatch_captain_checkin(crew, crew_id, model=effective_model)
          ...  # persist current_task_id, next_fire_at, last_checkin_at
          result["current_task_id"] = new_task_id
      except Exception as exc:
          result["immediate_dispatch_error"] = str(exc)
  ```
  Every failure — including a memory-pressure refusal — lands in the same
  generic `except` and is stringified. The schedule's `next_fire_at` is only
  advanced on success, so a failed cycle is simply retried on the next tick.

- A second `immediate_dispatch_error` site exists at **line 3949** in
  `_schedule_add`'s immediate-fire branch (generic scheduled jobs). The same
  classification helper is applied there for consistency.

- Config mirrors at **lines 428–431**:
  `GA_MIN_FREE_MEM_GB`, `GA_SPAWN_MIN_MEMORY_GB`, `GA_RESOURCE_PRESSURE_GB`,
  `GA_RESOURCE_CRITICAL_GB` are already imported from `cfg`.

### `transport/lifecycle.py`

- `_crew_api_with_recovery` (**line 589**) recovers exactly three classes:
  503-still-spawning (`_phase0_transient_503`), 400/401/403 stale cookie
  (`_phase1_stale_cookie`), connection errors (`_phase2_dead_gateway`). A
  memory-pressure refusal (503/429 with a pressure reason) is intentionally NOT
  one of these, so it propagates to the caller — which is what we want (defer to
  next cron tick, do not thrash in-cycle). **Do not** add a memory-pressure
  retry phase here (would violate the non-reentrant-lock contract documented in
  that function's docstring and the "defer, don't thrash" intent).
- The existing pre-launch memory gate pattern at **lines 856–863** shows the
  house style for a memory threshold check:
  ```python
  if GA_MIN_FREE_MEM_GB > 0:
      free_gb = _wait_for_memory(podman, GA_MIN_FREE_MEM_GB, 60)
      if free_gb < GA_MIN_FREE_MEM_GB:
          raise RuntimeError("Insufficient available memory ...")
  ```
  The check-in probe mirrors this but is non-blocking (no `_wait_for_memory`
  loop — a check-in must not sit and block the cron thread).

### `transport/podman.py`

- `_get_host_memory_gb(podman)` (**line 931**) prefers `memAvailable` over
  `memFree`. `_get_host_memory_gb_cached(podman)` (**~line 945**) wraps it with a
  5-second TTL cache and returns `float | None`. This is the probe source — no
  change required, reuse as-is.

### `transport/config.py`

- `TransportConfig` thresholds at **lines 226–229**; loader entries at
  **lines 374–377**. New key slots in alongside them.

### Order templates

- `academy/orders/spec-driven-development.md`: the dispatch-coordination section
  already documents the intent-marker protocol and explicitly says *"If
  `/api/spawn` fails, write no confirmation and let the pending marker become
  stale ..."* — the memory-pressure branch extends this with a named cause and
  escalation.
- `academy/orders/independent-review.md`: dispatch phase uses the same
  intent/idempotency protocol; same extension applies.

## Proposed implementation

### D1 — `transport/config.py`: new escalation-cycles key

Add to `TransportConfig` (after line 229):
```python
    ga_spawn_pressure_escalate_cycles: int = 3
```
Add to the loader (after line 377):
```python
    ga_spawn_pressure_escalate_cycles=_env_int("GA_SPAWN_PRESSURE_ESCALATE_CYCLES", "3"),
```
Mirror the import in `server.py` alongside lines 428–431:
```python
GA_SPAWN_PRESSURE_ESCALATE_CYCLES = cfg.ga_spawn_pressure_escalate_cycles
```

### D2 — `transport/server.py`: pre-dispatch probe helper

Add a small module-level helper near the captain dispatch block:
```python
_MEMORY_PRESSURE_MARKER = "memory_pressure:"

def _check_in_memory_pressure() -> float | None:
    """Return host available memory (GB) when BELOW the critical threshold,
    else None. None also means 'probe unavailable → fail open'."""
    try:
        podman = _get_podman()
        free_gb = _get_host_memory_gb_cached(podman)
    except Exception:
        return None
    if free_gb is None:
        return None  # fail open: no probe, do not block the crew
    return free_gb if free_gb < GA_RESOURCE_CRITICAL_GB else None
```

### D3 — `transport/server.py`: probe inside `_dispatch_captain_checkin`

Immediately before the `/api/spawn` call at line 3212, add:
```python
    low_gb = _check_in_memory_pressure()
    if low_gb is not None:
        raise _MemoryPressureSkip(
            f"{_MEMORY_PRESSURE_MARKER} host at {low_gb}GB free "
            f"(< {GA_RESOURCE_CRITICAL_GB}GB critical) — check-in deferred"
        )
```
`_MemoryPressureSkip` is a thin `RuntimeError` subclass so the fire path can
classify it without string-sniffing. Define it near the helper:
```python
class _MemoryPressureSkip(RuntimeError):
    """Raised when a check-in dispatch is skipped for host memory pressure."""
```

### D4 — `transport/server.py`: classify a gateway refusal

Wrap the `_crew_api_with_recovery` call so a gateway-side memory-pressure
refusal (that slipped past the probe) is re-raised as the same typed error:
```python
    try:
        result = _crew_api_with_recovery(crew, crew_id, "POST", "/api/spawn", json=spawn_body)
    except httpx.HTTPStatusError as e:
        if _is_memory_pressure_refusal(e.response):
            raise _MemoryPressureSkip(
                f"{_MEMORY_PRESSURE_MARKER} gateway refused spawn under memory pressure"
            ) from e
        raise
```
with:
```python
def _is_memory_pressure_refusal(resp) -> bool:
    if resp.status_code not in (429, 503):
        return False
    body = (resp.text or "").lower()
    return "memory" in body and ("pressure" in body or "insufficient" in body)
```

### D5 — `transport/server.py`: counter + edge-triggered escalation in the fire path

Replace the generic `except` at lines 3480–3482 with:
```python
            except _MemoryPressureSkip as exc:
                result["immediate_dispatch_error"] = str(exc)
                _record_memory_pressure_cycle(reg_entry, crew_id)
            except Exception as exc:
                result["immediate_dispatch_error"] = str(exc)
```
and on the success branch reset the counter to 0 while persisting
`current_task_id`/`next_fire_at`:
```python
                        s["consecutive_memory_pressure_skips"] = 0
```
`_record_memory_pressure_cycle` reads the captain schedule entry, increments
`consecutive_memory_pressure_skips` (treating a missing field as 0), persists it
under `_registry_lock`, and when the post-increment value **equals**
`GA_SPAWN_PRESSURE_ESCALATE_CYCLES` (equality, so it fires exactly once on the
crossing — edge-triggered) mails `admiral@localhost`:
```python
def _record_memory_pressure_cycle(reg_entry, crew_id):
    with _registry_lock:
        reg = _load_registry()
        for s in _get_crew_schedules(reg, crew_id):
            if s.get("type") == "captain":
                n = int(s.get("consecutive_memory_pressure_skips", 0)) + 1
                s["consecutive_memory_pressure_skips"] = n
                break
        _save_registry(reg)
    if n == GA_SPAWN_PRESSURE_ESCALATE_CYCLES:
        _mail_admiral(
            crew_id,
            subject=f"captain check-in deferred — sustained memory pressure {crew_id}",
            body=(f"{n} consecutive check-in cycles for crew {crew_id} were "
                  f"deferred because host available memory stayed below "
                  f"{GA_RESOURCE_CRITICAL_GB}GB. SDD progress is paused until "
                  f"pressure drops."),
        )
```
`_mail_admiral` reuses whatever maildeliver path the transport already uses for
Admiral signals (deliver via the container's `/usr/local/bin/maildeliver
admiral@localhost`, consistent with the mail conventions in STANDING_ORDERS.md);
if no such helper exists, add a minimal one that shells `maildeliver` inside the
crew container via `podman.container_exec`.

### D6 — Raven order templates: memory-pressure branch

In `academy/orders/spec-driven-development.md`, in the dispatch-coordination
section where it currently says *"If `/api/spawn` fails, write no confirmation
..."*, append:

> **Spawn refused under memory pressure.** A `/api/spawn` call may be refused by
> the gateway when the host is under critical memory pressure (HTTP 503/429 whose
> body names memory). Treat this exactly like any other failed spawn — write no
> confirmation and leave the pending intent marker so the dispatch is retried on
> a later check-in — but ALSO count it. If this check-in sees a memory-pressure
> refusal on `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` (default 3) consecutive cycles
> for the same dispatch, mail `admiral@localhost` with subject
> `captain check-in deferred — sustained memory pressure` and then hold. Do not
> treat a memory-pressure refusal as a completed dispatch, and do not retry it
> within the same cycle.

Add the equivalent paragraph to `academy/orders/independent-review.md`'s dispatch
phase, scoped to its four reviewer spawns.

## Testing strategy

- Unit: `_check_in_memory_pressure` returns the free value below threshold, None
  at/above, None on probe exception, None on `None` probe (fail-open).
- Unit: `_is_memory_pressure_refusal` true for 503/429 bodies naming memory
  pressure, false otherwise (incl. a 503-still-spawning body).
- Unit: `_record_memory_pressure_cycle` increments, treats missing field as 0,
  fires the Admiral mail exactly once at the boundary (equality), does not re-mail
  while the counter stays at/above the bound, resets on success.
- Integration (mock gateway): a `/api/spawn` returning a memory-pressure 503 sets
  `immediate_dispatch_error` with the `memory_pressure:` marker and does not
  advance `current_task_id`; `_crew_api_with_recovery` does not retry it in-cycle.

## Risks / tradeoffs

- **Fail-open probe.** When the memory probe is unavailable we dispatch anyway;
  the gateway's own refusal is still the backstop (D4). This keeps a probe outage
  from freezing the crew.
- **Probe/gateway threshold skew.** The transport probe uses
  `GA_RESOURCE_CRITICAL_GB`; the gateway's own threshold is independent. D4
  catches the window where the gateway is stricter than the transport.
- **Edge-triggered escalation.** One mail per crossing avoids spamming the
  Admiral every cycle; the counter resetting on success means a flap re-arms the
  escalation, which is intended.
