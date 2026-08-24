## 1. Relocate existing tests

- [x] 1.1 Create `tests/unit/`, `tests/integration/`, `tests/e2e/`, `tests/manual/` directories
- [x] 1.2 `git mv` the 6 files from `transport/test_*.py` into `tests/unit/`, and verify `git status` shows renames (not delete+add) for each
- [x] 1.3 `git mv tests/test_install_config.sh tests/test_dedicated_transport.sh` into `tests/integration/`, and verify the same
- [x] 1.4 `git mv tests/MANUAL_TEST_DEDICATED_MACHINE.md` into `tests/manual/`
- [x] 1.5 Update the discovery/invocation command to `python3 -m unittest discover -s tests/unit -p "test_*.py" -t .` (explicit repo-root top-level dir) and verify the full relocated suite passes locally with Podman available
- [x] 1.6 Verify the relocated suite also passes with Podman unavailable (e.g. temporarily renaming/hiding the `podman` binary from `PATH`, or running inside an environment without it) — confirms the self-skip behavior survived the move unchanged

## 2. Orchestrator

- [x] 2.1 Write `tests/run.sh` supporting `--unit`, `--integration`, `--e2e` flags and a default (no-flag) "run everything" mode
- [x] 2.2 Implement per-category subprocess invocation with captured exit codes and a per-category summary line
- [x] 2.3 Implement the aggregate summary and non-zero exit if any invoked category failed, and verify by deliberately breaking one test to confirm the orchestrator's exit code reflects it
- [x] 2.4 Add a placeholder E2E test under `tests/e2e/` (even a trivial one) so `--e2e` has something real to report on, and verify `tests/run.sh --e2e` runs it and reports success

## 3. CI and spec sync

- [x] 3.1 Update `.github/workflows/test.yml` to call `tests/run.sh --unit` in place of the current direct `python3 -m unittest discover -s transport` invocation, and verify the workflow still passes in CI
- [x] 3.2 Confirm the CI job's coverage is unchanged (same 6 files' worth of unit tests run, same skip behavior) — this task is a verification, not new code
- [x] 3.3 Sync `openspec/specs/transport-test-coverage/spec.md`'s "Test suite runs safely inside crew containers" requirement per this change's delta spec (new location, new command, import-resolution scenario)

## 4. Optional cleanup

- [x] 4.1 (Optional) Remove the now-dead flat-import fallback branch in `tests/unit/test_transport.py` (`except ModuleNotFoundError: ... importlib.import_module("transport.server")`) now that `-t .` guarantees the package-style branch always resolves — only do this after 1.5/1.6 are confirmed green, and re-run the full suite after removing it
- [x] 4.2 (Optional) Add a short `tests/unit/README.md` (or header comment) documenting the `-t .` requirement for anyone invoking discovery directly instead of through `tests/run.sh`

## 5. Verification

- [x] 5.1 Run `tests/run.sh` (all categories) locally end-to-end and confirm a clean aggregate pass
- [x] 5.2 Confirm `git log --follow` on at least one relocated file (e.g. `tests/unit/test_transport.py`) still traces back through its history in `transport/`
- [x] 5.3 `openspec validate consolidate-test-suite --strict` passes
