# Proposal

## Why

`GET /internal/crews` (added in TRN-286) reuses `_build_crews_payload` — the same
function that serves the public MCP `crews()` tool. That function makes a live
gateway call (`GET /api/spawn`) into every running crew to populate the `agents`
list. Radar polls this endpoint every 5 s, so the current implementation hammers
crew gateways on every tick. Additionally, `captain.last_checkin_at` is already
written to the registry but not exposed — Radar needs it to show how stale a
captain check-in is.

## What Changes

- Add `_build_internal_fleet_payload(podman)` to `transport/tools.py` — same
  shape as `_build_crews_payload` but registry-reads-only: no `_crew_api` call,
  `agents` always `[]`, `captain.last_checkin_at` included from the registry
  schedule entry
- Wire `_handle_internal_crews_get` in `transport/server.py` to use the new
  builder instead of `_build_crews_payload`
- Public `GET /api/crews` and the MCP `crews()` tool are unchanged
- Add `captain.last_checkin_at` to the internal fleet payload response shape
- Update `tests/unit/test_fleet.py` with new coverage for the internal endpoint
- Update `radar/static/app.js` to display `last_checkin_at` in the expanded row

## Capabilities

### New Capabilities

- `transport/internal-fleet-api`: Portside-internal fleet data endpoint
  (`GET /internal/crews`) that serves a registry-sourced fleet snapshot to
  `ga-radar` — no gateway calls, no bearer auth, `X-Transport-Token` only.

### Modified Capabilities

_(none — the public fleet-overview and caddy-proxy requirements are unchanged)_

## Impact

- `transport/tools.py` — new function `_build_internal_fleet_payload`
- `transport/server.py` — `_handle_internal_crews_get` wired to new builder
- `tests/unit/test_fleet.py` — new tests for registry-only payload and
  `last_checkin_at`
- `radar/static/app.js` — display `last_checkin_at` in captain expanded detail
