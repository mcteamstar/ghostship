# Tasks

## 1. Login commits before propagating

- [x] 1.1 Restructure Claude and Codex `_store` in `transport/login.py` so `commit_if_current` covers only the envelope write and flow completion; verify with a unit test where storage succeeds and propagation raises, asserting a success response and a closed pending flow.
- [x] 1.2 Run propagation off the event loop with per-crew exception handling, re-reading the stored profile before each injection; verify with a test that one failing crew does not stop injection into a second matching crew and that the failing crew id is reported.
- [x] 1.3 Apply the same commit-then-propagate pattern to Kiro login, restoring log-and-continue on injection failure; verify with a Kiro test mirroring 1.1.
- [x] 1.4 Confirm existing persistence-failure tests still assert a 500 and a retained pending flow when the store write itself fails; `pytest tests/unit/test_login.py tests/unit/test_credentials_routes.py`.

## 2. Running crews keep launch-time credentials

- [x] 2.1 Move `_validate_static_credential` in `transport/launcher.py` `ensure_running` into the stopped-crew start path only; verify with a test that rotates a static credential and then calls `ensure_running` on a running crew without error and without `container_inspect`.
- [x] 2.2 Add a test that a stopped crew woken after an incompatible rotation fails with an error naming crew and profile, and stays stopped.
- [x] 2.3 Add a file-transfer test showing directory evac succeeds on a running crew after rotation.

## 3. Verification

- [x] 3.1 Run `.venv/bin/python -m pytest -q -p no:xdist tests/unit tests/integration` with no failures.
- [x] 3.2 Add a CHANGELOG entry describing that running crews keep their launch-time credential and that login success no longer depends on propagation.
