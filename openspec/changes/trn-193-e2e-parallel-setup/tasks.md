# TRN-193 Tasks

## 1. Fix the e2e runner

- [x] 1.1 In `tests/run.sh`, change the e2e pytest invocation from
  `python3 -m pytest tests/e2e -n auto` to
  `python3 -m pytest tests/e2e -n 2 --dist loadfile`

## 2. Remove the stagger sleep

- [x] 2.1 In `tests/e2e/test_transport_e2e_extended.py::setUpModule`,
  remove the `time.sleep(35)` call
- [x] 2.2 Remove or update the comment above the sleep that explains it
  (references the parallel-launch race that `--dist loadfile` now prevents)

## 3. Verify

- [x] 3.1 Run `pytest tests/e2e -n 2 --dist loadfile` against academy —
  confirm 25 passed, 4 skipped, 0 errors
- [x] 3.2 Confirm wall clock time is less than the sequential baseline
  (~370s) — actual: 251s (33% faster)
