## 1. Delete the no-op function and its call-site comment

- [x] 1.1 In `transport/lifecycle.py`, delete `_inject_git_identity` (the two-line empty stub at ~L1715–1716)
- [x] 1.2 Delete the comment block at the former call site in `_finish_crew_setup` (~L1903–1906) that explains the removal — no longer needed once the function doesn't exist

## 2. Delete the pinning tests

- [x] 2.1 In `tests/unit/test_server.py`, delete the test method `test_inject_git_identity_is_noop_does_not_exec` (~L3017–3028)
- [x] 2.2 Delete the test method `test_finish_crew_setup_completes_successfully_without_inject_git_identity` (~L3031–end of method)

## 3. Verify

- [x] 3.1 Run `bash tests/run.sh --unit` and confirm all tests pass with the two test methods removed
- [x] 3.2 Confirm `_inject_git_identity` no longer appears anywhere in the codebase: `grep -r "_inject_git_identity" transport/ tests/` should return zero results
