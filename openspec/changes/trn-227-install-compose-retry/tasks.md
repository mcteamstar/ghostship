# Tasks

## 1. Retry loop in install.sh

- [x] 1.1 Replace the bare `eval "${_COMPOSE_ENV} podman compose ... up -d ..."` call in `scripts/install.sh` with the retry loop from design.md, reading `GA_COMPOSE_RETRY_ATTEMPTS` (default 3) and `GA_COMPOSE_RETRY_DELAY_SECS` (default 2). Verify manually: set `GA_COMPOSE_RETRY_ATTEMPTS=1` and confirm a failing compose exits with a non-zero code immediately.
- [x] 1.2 Add a guard: if `GA_COMPOSE_RETRY_ATTEMPTS` is set to 0 or a non-integer, treat it as 1 and print a warning to stderr. Verify: `GA_COMPOSE_RETRY_ATTEMPTS=0 bash -c 'source scripts/install.sh ...'` produces a warning and does not loop.

## 2. Documentation

- [x] 2.1 Add `GA_COMPOSE_RETRY_ATTEMPTS` and `GA_COMPOSE_RETRY_DELAY_SECS` entries to `docs/configuration.md` (defaults, valid range ≥ 1, purpose). Verify the section renders correctly in a Markdown viewer and the variable names match the implementation.
- [x] 2.2 Add commented-out entries for both vars to `config/ghostship.conf.example` with their default values. Verify the entries are present and commented out: `grep GA_COMPOSE_RETRY config/ghostship.conf.example`.

## 3. Tests

- [x] 3.1 Add a unit test in `tests/unit/` (e.g. `test_trn227_compose_retry.py` or a new shell test) that stubs `podman compose up` to fail N-1 times then succeed, and asserts the install proceeds. Verify: `tests/run.sh --unit` passes with the new test included.
- [x] 3.2 Add a test case where `podman compose up` always fails, asserting the script exits non-zero after exactly `GA_COMPOSE_RETRY_ATTEMPTS` attempts. Verify: test passes.

## Workflow follow-up

- Archive the change once tests pass and the PR is merged.
