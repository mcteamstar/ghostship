# TRN-193 — Fix e2e test parallelism

## Why

`pytest tests/e2e -n auto` fails reliably. Both test files have a
`setUpModule` that launches a shared crew. With 8 xdist workers, both
`setUpModule` calls fire simultaneously, race on the host's
`max_active_crews` limit, and fail. The existing `time.sleep(35)` stagger
in `test_transport_e2e_extended.py` is fragile and adds 35s to wall clock
time even when it works.

## What Changes

Serialise only the module-level shared-crew setup — not the test functions
themselves. pytest-xdist's `--dist loadfile` assigns all tests from a
single file to the same worker, which guarantees that:

- `test_transport_e2e.py` runs entirely on worker 0
- `test_transport_e2e_extended.py` runs entirely on worker 1
- Both workers run in parallel — no serialisation penalty on test functions

The two files' `setUpModule` calls still overlap in real time (both workers
start simultaneously), but since each file has its own distinct
`SHARED_CREW_ID` (`e2e-shared-main` and `e2e-shared-ext`), there is no
naming conflict. The only remaining race is on `max_active_crews`, which
with 2 crews + any pre-existing crews on academy is fine.

## Changes

- `tests/run.sh` — change `-n auto` to `-n 2 --dist loadfile` for the `e2e`
  category
- `tests/e2e/test_transport_e2e_extended.py` — remove `time.sleep(35)` from
  `setUpModule` and update the comment that explains it

## Constraints

- No changes to test logic or assertions
- Wall clock time MUST improve or stay the same vs the sequential baseline
- The fix MUST work with the existing pytest-xdist version (already a dep)
