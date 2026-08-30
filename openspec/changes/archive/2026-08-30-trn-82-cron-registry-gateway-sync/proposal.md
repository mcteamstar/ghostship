## Why

The transport maintains a schedule registry in `crews.json` as a bootstrap cache: when a crew container restarts after an idle-stop, `_reseed_cron_jobs` re-registers any scheduled jobs into the fresh gateway. The current implementation treats the registry as the source of truth and pushes its state into the gateway on every restart — overwriting any changes made inside the container since the last restart.

This is inverted. The gateway is the source of truth for schedule state; the registry is just a reseed bootstrap for the stopped-container case. Any mutation made from inside the container — `kirocrew cron pause`, `cron resume`, `cron delete` — is visible in the gateway but invisible to the registry. On the next restart the registry's stale state overwrites the gateway, silently undoing the in-container change.

Observed consequence (TRN-75): Raven correctly paused the captain cron via `kirocrew cron pause`. The gateway showed `"enabled": false`. But the registry still had `"enabled": true`. On every container restart, `_reseed_cron_jobs` re-registered the captain cron as active. The resurrected cron fired Ravens, touching `last_used`, preventing the crew from ever idle-stopping — indefinitely.

## What Changes

- `_reseed_cron_jobs` reconciles the registry **from** the gateway before reseeding — on every container wake, read `/api/crons`, update the registry to match the gateway's current state (enabled, interval, existence), then only register jobs that are missing from the gateway entirely
- The registry entry for a job that the gateway reports as paused is updated to `enabled: false` — the next idle check sees no enabled cron, and the crew stops cleanly
- Jobs deleted inside the container are removed from the registry on reconcile

## Capabilities

### Modified Capabilities

- `schedule`: on container restart, schedule state is reconciled gateway → registry before reseeding; the gateway is the source of truth for enabled/paused/deleted state

## Impact

- `transport/server.py` — `_reseed_cron_jobs`: add reconcile pass before reseed loop
- `tests/unit/` — new tests for reconcile behaviour: paused-in-gateway updates registry, deleted-in-gateway removes registry entry, missing-from-gateway triggers re-registration
