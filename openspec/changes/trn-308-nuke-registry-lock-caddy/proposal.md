# Proposal

## Why

`nuke()` calls `_caddy_portal.deregister_crew()` and `_caddy_portal.release_port()` inside a
`with registry:` block, holding `_registry_lock` for the duration of a blocking Caddy admin HTTP
call (up to ~7 s). Any concurrent operation that needs the registry — `launch`, `crews`, `pickup`,
`dispatch` — stalls for the full duration of the Caddy call, causing visible latency spikes when
a crew is nuked while other operations are in flight.

## What Changes

- Move `_caddy_portal.deregister_crew(crew_id)`, `_dashboard_gate.release_port()`, and
  `_caddy_portal.release_port()` in `transport/tools.py:nuke()` to execute **after** the
  `with registry:` block that removes the crew entry.
- The registry write (pop the crew entry, clear batch records) remains inside the lock as before.
- The Caddy deregister call is already best-effort (failure is logged, not fatal) — moving it
  outside the lock does not change that contract.
- Add a unit test covering the new call order: `deregister_crew` must be called after the
  registry lock is released.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

_(none — this is a pure internal refactor; the externally observable behavior of `nuke()` is
unchanged. No spec-level requirements change.)_

## Impact

- `transport/tools.py` — `nuke()` function only
- `tests/unit/test_tools.py` — new call-order assertion
