# Design: crew-lifecycle-resilience

See `proposal.md` for motivation and scope.

## Context

The transport layer is a single Python process. Worker threads call the crew
gateway over HTTP; a background thread runs the idle reaper; async Starlette
handlers serve the MCP tools. All share a `threading.Lock` for registry I/O
(`_registry_lock`) and, per crew, a non-reentrant `threading.Lock` for
recovery serialisation (`_get_recovery_lock`).

Key structural facts:

- `_crew_api_with_recovery(crew, crew_id, method, path)` acquires
  `_get_recovery_lock(crew_id)` for the life of the call, including any
  phase-1/phase-2 sub-call (lines 590–608 in `lifecycle.py`).
- `_enroll_crew_members` (line 1860) calls `_crew_api_with_recovery` for
  every slug — so it tries to *re-acquire the same per-crew lock*.
- `_enroll_crew_members` is called from inside `_ensure_crew_running` (the
  leader path, lines 851 and 1651) — which is itself invoked by the
  phase-1/phase-2 handlers *while the recovery lock is held*.
- Result: the recovery lock is non-reentrant; a second HTTP failure during
  enrolment deadlocks the crew indefinitely.

```
Thread A: _crew_api_with_recovery
  → acquires lock(crew_id)                     ← HELD
  → _phase2_dead_gateway
    → _ensure_crew_running                      (leader path)
      → _enroll_crew_members
        → _crew_api_with_recovery              ← tries to acquire same lock
          → BLOCKED FOREVER
```

`_load_registry` already handles JSON corruption (raises `RegistryCorruptError`)
but catches all other I/O errors with a `return {"crews": {}}` fallback, which
the caller in `server.py:2428` immediately saves — clobbering every other crew.

The idle reaper snapshots the registry and evaluates `last_used` *before* its
multi-second HTTP checks; a crew touched during those checks can still be
stopped.

Podman helpers (`container_exists`, `container_is_running`) return `False` on
any non-200 status, conflating a transient I/O error with a genuinely absent
container.

## Goals / Non-Goals

**Goals:**
- Eliminate the recovery self-deadlock without restructuring the three-phase
  recovery state machine.
- Prevent a single I/O error from silently destroying the registry.
- Prevent the idle reaper from stopping a recently-touched crew.
- Make Podman error semantics precise: `False` only on 404; raise on other
  errors so callers can decide.
- Prevent a concurrent stop from racing a restart in progress.
- Prevent non-idempotent POSTs from being retried on connection reset.
- Clean up dangling resources (login containers, running containers left with
  a stopped registry entry, admiral secret files).

**Non-Goals:**
- Restructuring the three-phase recovery state machine.
- Moving blocking I/O out of async handlers (medium-severity; separate change).
- Resolving the unexplained idle-reaper observation from the live check
  (logged to confirm on 0.8.0; deferred to a follow-up).
- Fixing the six 404 enrolment warnings per restart (enrolment scope filter;
  deferred — proposal marks this low-severity).
- Any schema changes to the registry file format.

## Decisions

### D1 — Break the deadlock by bypassing recovery in `_enroll_crew_members`

**Decision:** Replace the `_crew_api_with_recovery` call in
`_enroll_crew_members` with a direct `_crew_api` call wrapped in its own
try/except. Failures are logged but non-fatal (existing semantics preserved).

**Rationale:** Enrolment runs immediately after a fresh gateway start — the
gateway is confirmed live by `_ensure_crew_running` before enrolment is
invoked. Recovery logic (cookie refresh, restart) is irrelevant here: if the
gateway just started and is already dead, enrolment failing is acceptable
(it's best-effort). The fix is surgical and keeps the recovery state machine
intact everywhere it legitimately applies.

**Alternatives considered:**
- Make `_get_recovery_lock` reentrant (`threading.RLock`): would suppress the
  deadlock symptom but allow nested recovery loops that could cascade into
  multiple restart attempts for the same crew. Rejected: masks the logical
  error rather than fixing it.
- Factor out a `_crew_api_no_recovery` wrapper: equivalent to calling
  `_crew_api` directly with try/except; no benefit to an extra layer of
  indirection.
- Call `_enroll_crew_members` *after* releasing the recovery lock: requires
  structural changes to `_ensure_crew_running`'s call sites. Disproportionate
  for what is a straightforward fix.

### D2 — Registry I/O errors propagate instead of returning empty

**Decision:** In `_load_registry`, the bare `except Exception` clause that
returns `{"crews": {}}` is replaced with a `raise`. Callers that must not
fail hard (background threads, recovery paths) catch the exception locally
and continue without writing. The `server.py` handler that calls
`_load_registry` → `_save_registry` in the same block is updated to skip
the save on error.

**Rationale:** Returning empty is the wrong default. The empty-return exists
today because `_load_registry` is called everywhere; converting it to raise
is strictly safer — it makes every call site explicitly decide what to do on
failure rather than silently proceeding with a blank registry.

**Alternatives considered:**
- Retry on transient I/O errors before raising: adds complexity; the correct
  behaviour on EACCES is still to fail the request, not to retry.
- Return a sentinel `None` instead of raising: requires every call site to
  check for `None`, which is the same work as a try/except but less idiomatic.

### D3 — Idle reaper re-checks `last_used` under lock before stopping

**Decision:** After completing all HTTP activity checks, the reaper
re-acquires `_registry_lock`, re-reads `last_used` from the live registry
for that crew, and skips the stop if `last_used` is now within
`GA_IDLE_TIMEOUT_SECS`. The stop itself is performed while that lock is held.

**Rationale:** The TOCTOU window between snapshot and stop is bounded by the
HTTP check time (~10 s). The re-check closes the window at minimal cost: one
additional lock acquisition and one registry read per candidate crew.

**Alternatives considered:**
- Hold the lock across all HTTP checks: would block other threads (including
  request handlers that need the registry) for the full check duration.
  Rejected.
- Use per-crew stop flags: more state to manage; the registry already holds
  `last_used`, so re-reading it is sufficient.

### D4 — Podman helpers raise on non-404 errors

**Decision:** `container_exists` and `container_is_running` raise an
exception on any non-200 status other than 404. `container_exists` returns
`False` only on 404. `container_is_running` returns `False` only on 404 or
when the container is not in state `running`. Callers that previously treated
`False` as "gone" are updated to catch the new exception and handle it
explicitly (skip, fail-open, or log-and-continue as appropriate to the call
site).

**Rationale:** The current behaviour hides transient socket errors and Podman
daemon restarts as "container absent", which leads to erroneous registry
removals and spurious crew restarts. The change is a pure semantic correction.

**Alternatives considered:**
- Add a third return value or a separate `container_check_error` flag: more
  surface area; callers still need branching, and exceptions are the natural
  Python idiom for unexpected conditions.

### D5 — Restart guard: check `_startup_events` before probe-and-stop

**Decision:** In `_ensure_crew_running`, before the `container_is_running`
probe and the subsequent stop call, check whether a restart is already in
progress for `crew_id` (i.e. `crew_id in _startup_events`). If so, take the
waiter path immediately rather than probing and potentially stopping a
container that a concurrent leader is restarting.

**Rationale:** The existing waiter path is already correct; the bug is that
the check happens *after* the `container_is_running` probe. Moving the check
to before the probe eliminates the race without adding new state.

**Alternatives considered:**
- Use a separate "stop inhibit" flag per crew: more state, same effect.
  Rejected.

### D6 — Retry only idempotent methods in phase-0/phase-1

**Decision:** `_phase0_transient_503` and `_phase1_stale_cookie` only retry
when `method` is `GET`, `HEAD`, or `PUT` (idempotent). POST requests are not
retried; they raise the last exception instead.

**Rationale:** Non-idempotent POSTs (e.g. task dispatch) retried after a
connection reset can duplicate work. The current code retries unconditionally.

**Alternatives considered:**
- Rely on callers to not retry POST: doesn't fix the existing code, and future
  callers might not know about the constraint.
- Add a `retry=False` parameter: more surface area than needed; the HTTP
  method is already available.

### D7 — Error-path resource cleanup

Three distinct leaks addressed:

1. **Login container left after failed `launch()`** (`lifecycle.py:1984`):
   Wrap the start-failure path in a finally block that calls
   `_nuke_login_container` when a login container was created.
2. **Registry says stopped while container keeps running** (`lifecycle.py:765`):
   On the registry-write failure path in `_ensure_crew_running`, stop the
   container before returning the error.
3. **Admiral secret file left after failed launch** (`server.py:2592`):
   Add the secret file path to the existing `_cleanup_crew` call or handle
   it in a finally block at the launch failure path.

**Rationale:** Each leak is an independent, narrowly-scoped fix. Grouping them
here because they share a pattern (finally blocks around resource creation) and
can be implemented together.

## Risks / Trade-offs

[Podman error semantics change] → Any call site that currently silently ignores
a `False` from `container_exists`/`container_is_running` and proceeds without
crashing must be reviewed. Mitigation: audit all direct callers in D4
implementation; update each one explicitly.

[Registry raise-on-error] → Background threads that call `_load_registry`
without a try/except will now propagate the exception up to the thread's loop.
Mitigation: each affected background thread (`_idle_monitor`, `_reconcile_registry`,
startup scan) is reviewed and given an explicit except clause that logs and
continues — consistent with the existing fail-open pattern for those threads.

[Reaper re-check under lock] → The stop and the re-check are now inside a
single lock acquisition; if the stop call itself is slow (Podman latency), the
lock is held longer. Mitigation: the stop call uses a short timeout; in the
worst case the lock hold time is bounded by that timeout, not unbounded.

## Migration Plan

All changes are in-process; no schema migrations, no container rebuilds, no
data migration. Rolling restart of the transport process is sufficient.

Rollback: revert the commit; restart the transport. No persistent state is
touched by these changes.

## Open Questions

None — all design-blocking questions resolved above.
