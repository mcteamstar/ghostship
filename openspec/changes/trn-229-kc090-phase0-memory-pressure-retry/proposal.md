# TRN-229 — Phase 0 retries memory-pressure 503s (follow-on to TRN-225)

**Plane ticket:** TRN-229
**Upgrade context:** KiroCrew 0.8.0 → 0.9.0 (`0.9.0-insider.4`)
**Priority verdict:** LOW IMPACT — design oversight discovered during Banshee review of TRN-225. Partial violation of the "defer, don't thrash" intent in the narrow D4 edge case only.

## What was found

During the Banshee independent review of TRN-225, a gap was identified between the design's intent and the actual execution path for a gateway-side memory-pressure 503 (D4 of TRN-225).

`_crew_api_with_recovery` in `transport/lifecycle.py` intercepts every 503 response and passes it to `_phase0_transient_503` before re-raising. `_phase0_transient_503` retries all 503 responses up to 4× with 1-second sleep intervals, without inspecting the response body. It only re-raises after all retries are exhausted.

TRN-225 D4 classifies the memory-pressure 503 in `_dispatch_captain_checkin` **after** `_crew_api_with_recovery` raises. But because Phase 0 intercepts the 503 first, the gateway is retried 4× (~4 seconds) before the error propagates to D4's classification. This violates the design's stated goal: "A memory-pressure refusal… is intentionally NOT one of these [recovery phases], so it propagates to the caller — defer to next cron tick, do not thrash in-cycle."

## Impact

- The pre-dispatch probe (D3 of TRN-225) prevents this in the common case: when the host is already below `GA_RESOURCE_CRITICAL_GB`, the probe fires before `/api/spawn` is called at all.
- The Phase 0 retry overhead (4× retries + ~4 s) only occurs in the **narrow window** where the gateway's own threshold is stricter than the transport probe's `GA_RESOURCE_CRITICAL_GB` setting — i.e., the probe passed but the gateway refused.
- The final outcome is still correct: D4's classification fires after Phase 0 exhausts, `memory_pressure:` marker is set, the counter is incremented, and `current_task_id` is not advanced.
- This is a **performance/intent violation**, not a correctness bug. However, it contradicts a stated TRN-225 requirement: "SHALL NOT be routed through `_crew_api_with_recovery`'s in-cycle retry phases."

## What this change does

Add a memory-pressure body check inside `_phase0_transient_503` in `transport/lifecycle.py`. When a 503 response body names memory pressure (matching `_is_memory_pressure_refusal`'s criteria — "memory" AND ("pressure" OR "insufficient")), Phase 0 immediately re-raises without retrying. This restores the "single attempt, no thrash" behavior on the D4 path without adding a new recovery phase.

The check is intentionally placed inside Phase 0, not as a new phase, so the non-reentrant-lock contract on `_crew_api_with_recovery` is not affected (Phase 0 does not acquire any lock; it calls `_crew_api` directly).

## Affected files

| File | Symbol | Change |
|---|---|---|
| `transport/lifecycle.py` | `_phase0_transient_503()` (~line 448) | Add body check: immediately re-raise if 503 body is a memory-pressure response |

## Non-goals

- No change to `_crew_api_with_recovery` structure or recovery phases.
- No change to TRN-225's D3 (pre-dispatch probe), D4 (classification in server.py), or D5 (counter/escalation).
- No change to the 429 path (429 already propagates immediately from `_crew_api_with_recovery` since 429 is not in the 400/401/403 set and is not 503).
