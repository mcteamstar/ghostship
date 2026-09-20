## 1. Delete migration function and call sites

- [x] 1.1 Delete `_migrate_crew_network` from `transport/lifecycle.py` (~L1392–1465)
- [x] 1.2 Remove the migration call site in `_reconcile_registry` (~L1510–1515): the `migrated = _migrate_crew_network(...)` call and surrounding conditional
- [x] 1.3 Remove the best-effort `ga-net` cleanup block from `_reconcile_registry` (~L1574–1592): the `try/except` block that calls `podman.network_rm("ga-net")`
- [x] 1.4 Remove any comments in `_reconcile_registry` that describe the migration step (e.g. `# ── Network migration (D3)` header)

## 2. Clean up tests

- [x] 2.1 Search `tests/unit/` for tests referencing `_migrate_crew_network`, `ga-net`, or the migration path
- [x] 2.2 Delete any tests that exist solely to test the migration function
- [x] 2.3 Run `python -m pytest tests/unit/ -x -q` and confirm all tests pass

## 3. Verify

- [x] 3.1 Confirm `ga-net` no longer appears in `transport/lifecycle.py` (except in any historical comments that are purely informational and not describing active logic)
- [x] 3.2 Confirm `openspec validate --change trn-177-remove-ga-net-migration-shim` passes
