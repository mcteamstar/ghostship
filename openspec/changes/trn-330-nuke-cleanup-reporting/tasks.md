# Tasks

## 1. Collect explicit teardown failures

- [ ] 1.1 Add a nuke-specific resource-removal helper that attempts container and both volume removals and returns resource-level failures, while leaving `_cleanup_crew` rollback behavior best-effort. Verify 404/already-absent resources count as removed and one failure does not skip later removals.
- [ ] 1.2 Add unit coverage for failed container removal, each failed volume removal, and stop failure followed by successful force-removal. Verify the cases in `tests/unit/test_tools.py` or `tests/unit/test_lifecycle.py`.

## 2. Return a truthful nuke result

- [ ] 2.1 Update confirmed `nuke` to log and return a distinct cleanup-failure status with resource names when removals fail, while completing the existing registry/Caddy teardown sequence. Verify successful teardown retains its existing response and partial teardown never returns unqualified success.
- [ ] 2.2 Add response-shape coverage for complete and partial cleanup, and run the focused nuke tests in `tests/unit/test_tools.py`.
