## Why

The `_migrate_crew_network` shim in `transport/lifecycle.py` exists solely to upgrade
pre-ga-starboard crew containers (created before TRN-106/107) from the old `ga-net`
network to `ga-starboard`. Every container on academy has already been migrated or
recreated; no `ga-net` containers can exist on a 0.6.0+ transport because `ga-net` is
never created for new crews. The shim is dead weight that runs on every transport
startup and complicates the reconciliation path.

## What Changes

- Delete `_migrate_crew_network` from `transport/lifecycle.py` (~L1392–1460)
- Remove the migration call site in `_reconcile_registry` (~L1510–1515)
- Remove the best-effort `ga-net` cleanup block in `_reconcile_registry` (~L1574–1585)
- Delete any unit tests that test the migration path
- Remove `ga-net` references from comments that describe the reconciliation algorithm

## Capabilities

### New Capabilities
None.

### Modified Capabilities
None — this is a pure dead-code removal. No externally observable behaviour changes;
`ga-net` is not created, read from, or written to by any current code path.

## Impact

- `transport/lifecycle.py` — deletions only, no new code
- `tests/unit/` — remove tests covering the migration function
- No config, API, or compose changes
