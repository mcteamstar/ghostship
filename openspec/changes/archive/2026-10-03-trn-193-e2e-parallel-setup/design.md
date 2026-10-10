## Context

See proposal.md for motivation.

pytest-xdist offers three dist modes:
- `--dist load` (default, `-n auto`): distributes individual test items
  across workers without regard for which file they came from. Module
  setup/teardown may run on different workers from the tests.
- `--dist loadfile`: all tests from a single file go to the same worker.
  `setUpModule` and `tearDownModule` are guaranteed to run on the same
  worker as the tests they bracket.
- `--dist loadscope`: groups by test class scope — finer than loadfile.

The two test files have distinct shared crew IDs (`e2e-shared-main` and
`e2e-shared-ext`) so they don't conflict on crew names. The only race is
`max_active_crews` which with `max_active_crews=6` and 2 test crews is
not a problem.

## Goals / Non-Goals

**Goals:**
- `pytest tests/e2e -n 2 --dist loadfile` passes reliably
- Remove the fragile `time.sleep(35)` from `setUpModule`
- Total wall clock time ≤ sequential baseline (~370s)

**Non-Goals:**
- Changing test logic or assertions
- Reducing the number of crews launched during the test run
- Supporting more than 2 concurrent e2e test files without further changes

## Decisions

**D1 — `-n 2 --dist loadfile` not `-n auto --dist loadfile`**

`-n auto` with `--dist loadfile` would spin up as many workers as CPU
cores, most of them idle (only 2 files). `-n 2` is the exact right number:
one worker per file, both running in parallel. Explicitly setting it avoids
wasted process forks.

**D2 — Remove `time.sleep(35)`, not keep it as extra safety margin**

The sleep was added to prevent the race that `--dist loadfile` eliminates
structurally. Keeping it adds 35s to the extended file's worker every run
with no benefit. Remove it cleanly.

**Alternative considered: pytest-xdist fixtures / conftest.py**

A `conftest.py` with a session-scoped fixture and a file-lock could
serialise module setup across workers. Rejected — more complex, more code,
and `--dist loadfile` solves the problem at the scheduler level with zero
test code changes.

## Risks / Trade-offs

- **`--dist loadfile` behaviour**: within a file, xdist may still run test
  items from different classes in parallel on the same worker via threads
  (it doesn't — xdist uses separate processes, not threads; within a
  worker, tests run sequentially). This is safe.
- **Future third file**: adding a third e2e file would still work with
  `-n 2` (the third file gets round-robined to one of the two workers and
  runs after that worker's file teardown). Bump to `-n 3` when a third
  file lands.
