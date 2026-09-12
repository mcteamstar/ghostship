## Context

See proposal.md — Why.

`dispatch()` in `transport/server.py` builds a body dict and calls `_crew_api_with_recovery(crew, crew_id, "POST", "/api/spawn", json=body)`. The body currently contains `task`, `agent`, `keep=True`, and optionally `model`. The KiroCrew gateway's `/api/spawn` handler already accepts `parent_session` as an optional field — it is passed straight to `state.subagents.spawn(parent_session_key=...)`. No gateway changes are needed.

KiroCrew's `session_surface.has_dashboard_surface()` returns `True` unconditionally for any key beginning with `"dashboard:"`, so passing `parent_session="dashboard:<name>"` without pre-creating a session routes completion *notifications* to the dashboard bell. However, this does NOT create a visible session in the Sessions list — sessions are materialised only via `POST /api/chat/slots` on the crew gateway. For `anchored` and `free` modes to show up in the Sessions panel, the transport must call `POST /api/chat/slots {"name": "<slot-name>"}` before dispatching.

## Goals / Non-Goals

**Goals:**
- Add `mode: "headless" | "anchored" | "free"` to `dispatch()` and `_dispatch_batch()`
- Derive the default mode at dispatch time from the crew's current `dashboard_url` registry field
- Echo the effective mode in the dispatch response
- No regression for callers that do not pass `mode`

**Non-Goals:**
- Applying `mode` to Captain/Raven cron sessions (they use `/api/crons`)
- Per-agent dispatch modes (one mode per call is sufficient)
- Persisting `mode` in the schedule registry for `schedule()` tool

## Decisions

**D1 — Live lookup, not a stored default**
Derive the default mode at dispatch time from `crew.get("dashboard_url")` in the registry, rather than storing a `mode_default` field. `dashboard_url` is already updated when the dashboard is enabled or disabled (`POST`/`DELETE /crews/{id}/dashboard`), so this approach self-corrects when the dashboard is toggled mid-flight — no extra registry writes, no stale defaults.

```python
effective_mode = mode or ("anchored" if crew.get("dashboard_url") else "headless")
```

**D2 — Caller override wins over derived default**
Explicit `mode` on a `dispatch()` call overrides the derived default for that call only.

**D3 — `unique` mode: task-id suffix format**
`dashboard:<crew-id>-<task-id>` — the task ID is the gateway-assigned `id` from the `/api/spawn` response. For `unique` mode in `_dispatch_batch`, the `parent_session` key per task must therefore be constructed *after* each `/api/spawn` response is received, not before. This is already the natural order since batch dispatch iterates sequentially.

**D4 — Batch: anchored mode sends one key for all tasks**
All tasks in a `tasks=[...]` batch with `mode="anchored"` share the same `parent_session="dashboard:<crew-id>"`. This is the point of `anchored` — one slot, all completions visible together. Concurrent completions serialising into one transcript is the documented tradeoff.

**D5 — Validation at call time, not at registry load**
Invalid `mode` values are rejected immediately with a validation error, before any `/api/spawn` call is made — consistent with how `agent` and `model` are validated.

**D6 — Pre-create the dashboard session slot before dispatching**
`anchored` and `free` modes must call `POST /api/chat/slots` on the crew gateway before each `/api/spawn` call to materialise the session in the Sessions list. Without this, tasks route completion notifications to the bell icon but never appear as visible sessions.

- `anchored`: call `POST /api/chat/slots {"name": "<crew-id>"}` once before the first dispatch (or before each dispatch — the endpoint returns 409 if the slot already exists, which is safe to ignore).
- `free`: call `POST /api/chat/slots {"name": "<crew-id>-<suffix>"}` once per task, before its `/api/spawn` call, using the same UUID suffix that will be used in `parent_session`.

The slot `name` is the key without the `dashboard:` prefix — the gateway stores it normalised and addresses it as `dashboard:<name>` in the session surface registry. A 409 response means the slot already exists and should be treated as success.

## Implementation Plan

### 1. `transport/server.py` — `dispatch()`

Add `mode: str | None = None` parameter. After the existing model/agent validation:
```python
VALID_DISPATCH_MODES = ("headless", "anchored", "free")
effective_mode = mode or ("anchored" if crew.get("dashboard_url") else "headless")
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

### 2. `transport/server.py` — `_dispatch_batch()`

Pass `mode` through to the batch helper. Apply the same resolution logic. For `unique` mode, generate a distinct UUID suffix per task in the batch loop.

### 3. Response shape

Single dispatch — add `"mode"` and, for `unique` mode, `"parent_session"` to the returned dict so the caller knows which slot to watch.

Batch dispatch — add `"mode"` at the top level; per-task entries include `"parent_session"` when `unique`.

### 4. Tests

- Unit: `mode="headless"` sends no `parent_session`
- Unit: `mode="anchored"` sends `parent_session="dashboard:<crew-id>"`
- Unit: `mode="free"` sends `parent_session` with unique suffix per call
- Unit: invalid `mode` returns error before spawn
- Unit: crew with `dashboard_url` set → default effective mode is `anchored`
- Unit: crew with no `dashboard_url` → default effective mode is `headless`
- Unit: dashboard toggled mid-flight — dispatch after `DELETE /dashboard` defaults to `headless`; after `POST /dashboard` defaults to `anchored`
- Unit: batch with `mode="free"` gives each task a distinct `parent_session`
- Unit: batch with `mode="anchored"` gives all tasks the same `parent_session`
