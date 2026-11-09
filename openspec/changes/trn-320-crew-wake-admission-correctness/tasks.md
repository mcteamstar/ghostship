# Tasks

## 1. Failed wake cleanup

- [ ] 1.1 Wrap the post-`container_start` wake steps in `transport/launcher.py` so any failure stops the container, releases the reservation and marks the registry stopped before re-raising; verify with unit tests that fail the config patch, the gateway wait and the cookie mint in turn and assert `container_stop` was called and registry status is `stopped`.
- [ ] 1.2 Make waiters receive the leader's actual failure when the cookie mint fails; verify with a two-caller test asserting the waiter's error matches the leader's.

## 2. Memory admission

- [ ] 2.1 Add `GA_START_MEM_ESTIMATE_GB` (default 1.0) to config and docs/configuration.md; verify config tests load the default and an override.
- [ ] 2.2 Subtract the in-flight estimate in `_check_memory_gate`; delete `test_pending_start_is_included_in_memory_admission` and replace it with a test that feeds a constant live reading and asserts the second concurrent start is refused or waits while the first is in flight.
- [ ] 2.3 Restructure the memory wait so the capacity lock is released between checks; verify with a test that a second crew's admission completes while the first is still waiting for memory.

## 3. Cleanup and verification

- [ ] 3.1 Remove `_run_restart_cycle` and its tests; `grep -rn _run_restart_cycle transport tests` returns nothing.
- [ ] 3.2 Run `.venv/bin/python -m pytest -q -p no:xdist tests/unit tests/integration` with no failures.
- [ ] 3.3 Add a CHANGELOG entry for failed-wake cleanup and in-flight memory admission.
