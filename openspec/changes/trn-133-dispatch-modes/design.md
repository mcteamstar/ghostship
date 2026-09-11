## Context

See proposal.md — Why.

`dispatch()` in `transport/server.py` builds a body dict and calls `_crew_api_with_recovery(crew, crew_id, "POST", "/api/spawn", json=body)`. The body currently contains `task`, `agent`, `keep=True`, and optionally `model`. The KiroCrew gateway's `/api/spawn` handler already accepts `parent_session` as an optional field — it is passed straight to `state.subagents.spawn(parent_session_key=...)`. No gateway changes are needed.

KiroCrew's `session_surface.has_dashboard_surface()` returns `True` unconditionally for any key beginning with `"dashboard:"`, so passing `parent_session="dashboard:<name>"` without pre-creating a session is the correct and intended pattern. Sessions are created lazily by the dashboard on first navigation to the slot.

## Goals / Non-Goals

**Goals:**
- Add `mode: "headless" | "anchored" | "free"` to `dispatch()` and `_dispatch_batch()`
- Store `mode_default` in the crew registry at launch, derived from the `dashboard` flag
- Echo the effective mode in the dispatch response
- No regression for callers that do not pass `mode`

**Non-Goals:**
- Pre-creating dashboard sessions via API (not possible; 405)
- Applying `mode` to Captain/Raven cron sessions (they use `/api/crons`)
- Per-agent dispatch modes (one mode per call is sufficient)
- Persisting `mode` in the schedule registry for `schedule()` tool

## Decisions

**D1 — Registry default, not a live lookup**
Store `mode_default` in `crews.json` at launch time rather than re-examining the `dashboard` flag on every dispatch. The registry is the single source of truth for crew state; adding a derived field keeps dispatch fast and avoids coupling dispatch to the launch path.

Stored value: `"anchored"` if `dashboard=True` at launch, `"headless"` otherwise.

**D2 — Caller override wins over registry default**
Explicit `mode` on a `dispatch()` call overrides the registry default for that call only. The registry default is not mutated.

**D3 — `unique` mode: task-id suffix format**
`dashboard:<crew-id>-<task-id>` — the task ID is the gateway-assigned `id` from the `/api/spawn` response. For `unique` mode in `_dispatch_batch`, the `parent_session` key per task must therefore be constructed *after* each `/api/spawn` response is received, not before. This is already the natural order since batch dispatch iterates sequentially.

**D4 — Batch: anchored mode sends one key for all tasks**
All tasks in a `tasks=[...]` batch with `mode="anchored"` share the same `parent_session="dashboard:<crew-id>"`. This is the point of `anchored` — one slot, all completions visible together. Concurrent completions serialising into one transcript is the documented tradeoff.

**D5 — Validation at call time, not at registry load**
Invalid `mode` values are rejected immediately with a validation error, before any `/api/spawn` call is made — consistent with how `agent` and `model` are validated.

## Implementation Plan

### 1. `transport/lifecycle.py` — store default at launch

In `_finish_crew_setup()`, after the `dashboard` flag is resolved, add to the registry entry:
```python
"mode_default": "anchored" if dashboard else "headless"
```

### 2. `transport/server.py` — `dispatch()`

Add `mode: str | None = None` parameter. After the existing model/agent validation:
```python
VALID_DISPATCH_MODES = ("headless", "anchored", "free")
effective_mode = mode or crew.get("mode_default", "headless")
if effective_mode not in VALID_DISPATCH_MODES:
    return {"error": f"mode must be one of: {', '.join(VALID_DISPATCH_MODES)}"}
```

In the body construction:
```python
body = {"task": task, "agent": agent, "keep": True}
if model:
    body["model"] = model
if effective_mode == "anchored":
    body["parent_session"] = f"dashboard:{crew_id}"
```

After receiving the spawn response (to get `task_id` for `unique`):
```python
if effective_mode == "free" and task_id:
    # Can't set parent_session before we have task_id — for unique mode,
    # re-dispatch is not needed; the parent_session is only used by the
    # dashboard for completion routing, not by the gateway to start the run.
    # Store it in the registry for pickup to report.
    pass
```

Wait — for `unique`, `parent_session` must be in the *spawn body* before the call, but we don't have `task_id` yet. The slot name must be known at spawn time for the dashboard to route the completion correctly.

**Revised D3:** For `unique` mode, use a transport-generated UUID as the slot suffix rather than the gateway task ID. This makes the key predictable before the spawn call:
```python
import uuid
if effective_mode == "free":
    slot_suffix = uuid.uuid4().hex[:8]
    body["parent_session"] = f"dashboard:{crew_id}-{slot_suffix}"
```
Return `slot_suffix` (or the full `parent_session` value) in the response alongside `task_id`.

### 3. `transport/server.py` — `_dispatch_batch()`

Pass `mode` through to the batch helper. Apply the same resolution logic. For `unique` mode, generate a distinct UUID suffix per task in the batch loop.

### 4. Response shape

Single dispatch — add `"mode"` and, for `unique` mode, `"parent_session"` to the returned dict so the caller knows which slot to watch.

Batch dispatch — add `"mode"` at the top level; per-task entries include `"parent_session"` when `unique`.

### 5. Tests

- Unit: `mode="headless"` sends no `parent_session`
- Unit: `mode="anchored"` sends `parent_session="dashboard:<crew-id>"`
- Unit: `mode="free"` sends `parent_session` with unique suffix per call
- Unit: invalid `mode` returns error before spawn
- Unit: registry default `"anchored"` used when crew launched with `dashboard=True` and no explicit mode
- Unit: registry default `"headless"` used when crew launched without dashboard and no explicit mode
- Unit: batch with `unique` mode gives each task a distinct `parent_session`
