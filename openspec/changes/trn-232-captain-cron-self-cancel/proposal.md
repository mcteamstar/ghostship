# Proposal

## Why

When Raven completes an SDD or independent-review cycle, it attempts to stop the captain
check-in loop via `kirocrew cron pause`. This fails silently because the captain schedule
is a transport-level construct registered in the ghostship schedule registry — it is not
visible to `kirocrew cron list` inside the crew container. The result: completed crews
stay alive indefinitely, Raven check-ins keep firing on an empty workload, and the crew
never idles. TRN-230 fixed the inverse problem (captain couldn't restart after a dead
session); this change fixes the symmetric problem.

## What Changes

- Add `POST /crews/{crew_id}/captain/stop` REST endpoint to the transport. Callable from
  inside the crew container using the existing dashboard cookie auth. Stops the captain
  schedule the same way `captain(action="stop")` does from outside.
- Update `_RAVEN_SELF_CANCEL` in `transport/captain.py` to instruct Raven to call this
  new endpoint via curl (using the dashboard cookie) instead of `kirocrew cron pause`.
- Update the `captain` spec's `{{RAVEN_SELF_CANCEL}}` placeholder requirement to reflect
  that self-cancel now uses the transport endpoint, not the KiroCrew CLI.
- No change to the `captain(action="stop")` MCP tool or the external `captain` API
  surface — this only adds an internal path callable from inside the crew.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `captain`: The self-cancel mechanism available to Raven changes. The
  `{{RAVEN_SELF_CANCEL}}` placeholder SHALL instruct Raven to call
  `POST /crews/{crew_id}/captain/stop` via the transport REST API rather than
  `kirocrew cron pause`, since the captain schedule lives in the transport registry and
  is not visible inside the crew container.

## Impact

- `transport/server.py` — new route `POST /crews/{crew_id}/captain/stop`
- `transport/captain.py` — updated `_RAVEN_SELF_CANCEL` constant
- `openspec/specs/captain/spec.md` — update `{{RAVEN_SELF_CANCEL}}` placeholder requirement
- `tests/unit/test_captain.py` — new tests for the endpoint
