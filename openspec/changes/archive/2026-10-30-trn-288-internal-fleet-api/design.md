# Design — TRN-288 Internal Fleet API

## Context

See `proposal.md — Why` for motivation.

`GET /internal/crews` (added in TRN-286) currently calls
`_build_crews_payload(podman)`, which was written for the public `GET /api/crews`
endpoint and the MCP `crews()` tool. That function makes a live gateway call
(`_crew_api(info, "GET", "/api/spawn")`) into every running crew to populate the
`agents` list. With Radar polling every 5 s this is a gateway-hammering side
effect.

`captain.last_checkin_at` is already written to the crew registry by
`captain_engine.py` (at task completion) and `monitors.py` (on task completion
event). It just isn't plumbed through to the response.

## Goals / Non-Goals

**Goals:**
- `GET /internal/crews` is registry-reads-only — no gateway calls on any poll tick
- `captain.last_checkin_at` exposed in the internal payload
- Public `GET /api/crews` and MCP `crews()` are unchanged

**Non-Goals:**
- Live `agents` list in the internal endpoint (requires a registry-backed task
  cache — out of scope)
- Mail counts (require exec into container)
- Renaming the endpoint to `/internal/fleet`
- Changes to auth model (already correct: `X-Transport-Token` only)

## Decisions

### D1 — Add `_build_internal_fleet_payload` in `transport/tools.py`

Rather than adding a conditional flag to `_build_crews_payload`, extract a
separate function with the same structure but two deliberate differences:
skip the `_crew_api` call entirely and read `last_checkin_at` from the
captain schedule entry.

**Why not a flag?** A boolean `gateway_calls=False` parameter on the existing
function would make the function harder to reason about and test. Two functions
with a clear naming contract (`_build_crews_payload` = full, gateway-calling;
`_build_internal_fleet_payload` = registry-only) is cleaner.

**Why not inline in the handler?** The handler in `server.py` is already crowded
with import fallbacks. Keeping payload assembly in `tools.py` matches the
existing pattern and keeps the handler thin.

### D2 — `agents: []` always in the internal payload

The internal endpoint is polled every 5 s by Radar. Active task data requires
a gateway call to `/api/spawn` on each crew. Until a registry-backed task cache
exists (future work), returning `[]` is the correct trade-off: Radar gets a
fast, reliable snapshot without hammering gateways, and the UI can note that
live task data is unavailable.

**Alternative considered:** Cache the last known agents list in the registry on
each dispatch/completion event and return the stale list. Rejected for now —
stale agent data may mislead operators. A proper cache belongs in a follow-on
pylon with an explicit staleness policy.

### D3 — Read `last_checkin_at` directly from the registry schedule entry

`captain_engine.py` writes `s["last_checkin_at"]` into the crew's schedule
entry in the registry on every completed check-in. `_build_internal_fleet_payload`
reads it with `captain_entry.get("last_checkin_at")` — a one-line addition to
the existing captain dict construction, no new registry schema needed.

### D4 — Radar SPA displays `last_checkin_at` in expanded captain row

The `app.js` expanded-row detail already renders `captain.schedule` and
`captain.current_task_id`. Adding `last_checkin_at` as a relative timestamp
("last check-in 3m ago") is a small UI addition with no architectural impact.

## Risks / Trade-offs

- **Duplicated payload logic** — `_build_internal_fleet_payload` is structurally
  similar to `_build_crews_payload`. If new fields are added to the public payload,
  they must be deliberately considered for the internal one too. Mitigation: the
  two functions are named clearly and documented; the test suite enforces their
  contract independently.
- **`agents: []` may confuse operators** — Radar will show no active tasks even
  when agents are running. Mitigation: add a UI note in the expanded row ("live
  task data unavailable at this endpoint") until a cache is built.

## Migration Plan

Straightforward replacement: `_handle_internal_crews_get` switches from
`_build_crews_payload` to `_build_internal_fleet_payload`. No data migration
needed — the registry schema is unchanged. Deploy via `ghostship upgrade`.

Rollback: revert the handler call and redeploy. No state to undo.
