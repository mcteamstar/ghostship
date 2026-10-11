# TRN-225 — Cron spawn refused under critical memory pressure

**Plane ticket:** TRN-225
**Upgrade context:** KiroCrew 0.8.0 → 0.9.0 (`0.9.0-insider.4`)
**Priority verdict (from Wraith's 0.9.0 research report):** **LOW IMPACT / behaviour change** — *not* a hard break. The crew does not crash; a check-in cycle is skipped and work resumes when memory pressure drops. The residual risk is that a *sustained* memory-pressured host silently skips crew check-ins for extended periods, which can time out long-running SDD runs.

## What is changing in KiroCrew 0.9.0

0.9.0 adds "defer crons and refuse spawns under critical memory pressure" (upstream PR #2432). When the host is under critical memory pressure, the gateway refuses `POST /api/spawn` with an error response instead of launching the subagent process. In 0.8.0 the spawn would simply be attempted.

## Why this matters to ghostship

Ghostship's Captain check-in loop is the only thing that keeps an SDD run moving: every scheduled check-in, Raven dispatches the next persona via `POST /api/spawn`. Two call sites are affected:

1. **Transport side** — `transport/server.py:_dispatch_captain_checkin()` calls `/api/spawn` through `_crew_api_with_recovery`. On a refusal the exception is caught in `_captain_do_add`/the fire path and stored as `result["immediate_dispatch_error"] = str(exc)` (server.py ~line 3482). `_crew_api_with_recovery` (`transport/lifecycle.py:589`) recovers only 503-still-spawning, 400/401/403 stale-cookie, and connection errors — a memory-pressure refusal is none of those, so it propagates. The check-in cycle is skipped and the error is logged; nothing retries except the next scheduled cron tick.

2. **Raven side (inside the container)** — the SDD and independent-review order templates (`academy/orders/spec-driven-development.md`, `academy/orders/independent-review.md`) instruct Raven to call the authenticated `/api/spawn` directly. Neither template has an explicit "spawn refused under memory pressure" branch. The existing intent-marker staleness logic *accidentally* produces correct bounded-retry behaviour (a failed spawn writes no confirmation; the pending marker holds the next cycle, then goes stale and Raven retries), but:
   - Raven cannot distinguish a memory-pressure refusal from any other `/api/spawn` failure, so it cannot report the condition or back off intelligently.
   - A refusal that persists across many cycles produces silent, unbounded skipping with no escalation to the Admiral.

## What this change does

This change makes the memory-pressure refusal **observed, bounded, and escalated** rather than silently absorbed:

1. **Pre-dispatch memory probe (transport).** Before `_dispatch_captain_checkin` calls `/api/spawn`, probe host available memory via the existing `transport/podman.py:_get_host_memory_gb_cached()` helper and the already-defined `GA_RESOURCE_CRITICAL_GB` threshold (`transport/config.py:229`, default `1.0`). When below the critical threshold, skip the dispatch deterministically on the transport side with a typed, logged reason (`memory_pressure`) and increment a per-crew consecutive-skip counter in the registry — instead of making a doomed REST call the gateway will reject anyway.
2. **Typed refusal propagation (transport).** When the gateway *does* refuse the spawn (host crosses the threshold between probe and call, or the gateway's own threshold is stricter), classify that specific refusal and surface it as `immediate_dispatch_error` with a recognisable `memory_pressure` marker and increment the same counter. A successful dispatch resets the counter.
3. **Escalation on sustained pressure (transport).** When the consecutive memory-pressure skip/refusal counter crosses a configurable bound (`GA_SPAWN_PRESSURE_ESCALATE_CYCLES`, new, default `3`), emit a single Admiral-facing signal (mail to `admiral@localhost`) so a sustained-pressure host is no longer silent.
4. **Order-template guidance (Raven).** Add an explicit "spawn refused under memory pressure" branch to `spec-driven-development.md` and `independent-review.md` so Raven recognises the refusal, holds without burning the intent-marker incorrectly, and mails `admiral@localhost` after N consecutive refused cycles.

## Affected ghostship files / functions

| File | Symbol | Change |
|---|---|---|
| `transport/server.py` | `_dispatch_captain_checkin()` (~line 3131) | Add pre-dispatch memory probe + typed refusal classification |
| `transport/server.py` | captain fire path (`immediate_dispatch_error`, ~line 3482) | Record typed `memory_pressure` outcome; drive the consecutive-skip counter |
| `transport/config.py` | `TransportConfig` (lines 226–229) + loader (lines 374–377) | Add `ga_spawn_pressure_escalate_cycles` key |
| `transport/podman.py` | `_get_host_memory_gb_cached()` (~line 945) | Reused as-is (the probe source) |
| `academy/orders/spec-driven-development.md` | dispatch-coordination section | Add memory-pressure refusal branch + escalation note |
| `academy/orders/independent-review.md` | dispatch phase | Add memory-pressure refusal branch + escalation note |

## Non-goals

- No change to the gateway's own refusal behaviour (that is upstream KiroCrew, PR #2432).
- No change to `_crew_api_with_recovery`'s recovery phases — a memory-pressure refusal is deliberately *not* auto-retried in-cycle; it is deferred to the next scheduled check-in, matching the gateway's "defer, don't thrash" intent.
- No change to `GA_MIN_FREE_MEM_GB` (crew *launch* gate) or `GA_SPAWN_MIN_MEMORY_GB` semantics.
