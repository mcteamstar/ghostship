## Why

Captain-based crews never idle-stop even after the captain is paused. The idle monitor in `lifecycle.py` queries the crew gateway's `/api/crons` directly — if any job is `"enabled": true`, the crew is kept alive. When `captain(action="stop")` is called via MCP, the transport calls the gateway cron disable API and, on success, updates the ghostship schedule registry. If the disable API call fails (or returns a non-ok response), the error is returned and the registry is **never updated** — both the gateway and registry stay `enabled: true`, permanently blocking idle-stop.

This is a consequence of the TRN-82 source-of-truth flip: the gateway is now authoritative for schedule state, and the registry syncs from it on restart. But `captain stop` conflates two operations — disabling the gateway cron and updating the registry — and only does the registry update if the gateway call succeeds. A failed API call leaves the system in a broken state with no recovery path short of a container restart.

## What Changes

- `captain stop` SHALL update the ghostship registry entry to `enabled: false` **independently of the gateway API call result**. The registry write is not conditional on the API call succeeding.
- This ensures TRN-82's reconcile-on-restart sees the correct state, and the idle monitor can eventually stop the crew.
- The gateway API call is still attempted (best-effort), but a failure no longer blocks the registry update or traps the crew in a never-idle state.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `captain`: `captain stop` decouples the registry `enabled: false` update from the gateway cron disable API call. The registry is always updated; the gateway call is best-effort.

## Impact

- `transport/server.py` — the `captain stop` block: move the registry update outside the `if standing_job.get("enabled", False)` guard so it always runs
- No config changes
- Existing behaviour unchanged for the gateway API call (still attempted when the job is enabled in the gateway)
