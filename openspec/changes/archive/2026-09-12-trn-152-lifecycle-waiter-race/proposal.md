## Why

Two correlated gaps in `lifecycle.py` around crew restart and API recovery, found by the 0.4.0 independent review:

1. **Waiter race**: when `_ensure_crew_running`'s leader fails (memory gate, crew limit, gateway timeout), `finally` still sets the Event but doesn't record the failure. Waiters read stale "running" status and proceed against a crew that never started.
2. **Recovery engine untested**: `_crew_api_with_recovery` and its three `_phaseN` helpers have no tests — a regression in the retry/cookie-refresh/dead-gateway path would be silent.

## What Changes

- Fix `_ensure_crew_running` so the leader records a success/failure outcome on the Event; waiters propagate the error rather than proceeding blindly.
- Add unit tests for `_crew_api_with_recovery` and `_phase0_transient_503` / `_phase1_stale_cookie` / `_phase2_dead_gateway`.

## Capabilities

### Modified Capabilities

- `idle-and-recovery`: `_ensure_crew_running` waiter behaviour on leader failure changes from "proceed on stale status" to "propagate leader error".
- `transport-test-coverage`: adds required test coverage for crew recovery engine.

## Impact

- `transport/lifecycle.py` — `_ensure_crew_running` event signalling
- `tests/unit/test_lifecycle.py` — recovery engine tests
