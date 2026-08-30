## Prerequisites

- [ ] 0.1 TRN-71 fully landed (lifecycle.py committed, all tests passing)

## 1. Setup

- [ ] 1.1 Create `tests/unit/helpers.py` — move any shared mock factories or setUp helpers from `test_transport.py` that are used by multiple test classes
- [ ] 1.2 Create empty stub files: `test_registry.py`, `test_podman.py`, `test_files.py`, `test_captain.py`, `test_lifecycle.py`, `test_server.py` — each with a comment indicating which module it covers and imports for that module

## 2. Migrate test classes

For each migration step: move the class, update patch targets to the owning module, remove dual-patch workarounds, run `bash tests/run.sh --unit`, comment out the class from `test_transport.py`.

- [ ] 2.1 Migrate registry tests → `test_registry.py`; patch via `transport.registry`
- [ ] 2.2 Migrate podman/http tests → `test_podman.py`; patch via `transport.podman`
- [ ] 2.3 Migrate file transfer tests → `test_files.py`; patch via `transport.files`
- [ ] 2.4 Migrate captain tests → `test_captain.py`; patch via `transport.captain`
- [ ] 2.5 Migrate lifecycle tests (`_ensure_crew_running`, `_finish_crew_setup`, `_crew_api_with_recovery`, `_patch_crew_config`, etc.) → `test_lifecycle.py`; patch via `transport.lifecycle`
- [ ] 2.6 Migrate MCP tool tests (`crews`, `launch`, `dispatch`, `pickup`, `steer`, `nuke`, `captain`, `schedule`, `evac`, `supply`) and login state machine tests → `test_server.py`

Each migration step in section 2 ends with its own commit:
- `refactor(trn-85): migrate registry tests to test_registry.py`
- `refactor(trn-85): migrate podman tests to test_podman.py`
- etc.

## 3. Cleanup

- [ ] 3.1 Delete `tests/unit/test_transport.py` (now empty after all classes removed)
- [ ] 3.2 Run full suite `bash tests/run.sh` — all pass, no duplicate test IDs
- [ ] 3.3 Commit: `refactor(trn-85): delete test_transport.py — migration complete`

## 4. Verification

- [ ] 4.1 Confirm test count is the same or higher (no tests lost in migration): compare `Ran N tests` before and after
- [ ] 4.2 Confirm no stale server patches remain: `grep -r 'patch.object(server' tests/unit/test_registry.py tests/unit/test_podman.py tests/unit/test_files.py tests/unit/test_captain.py tests/unit/test_lifecycle.py` — should return nothing
