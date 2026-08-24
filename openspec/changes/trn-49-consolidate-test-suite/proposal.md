## Why

Tests are currently split across two unrelated locations with no shared entry point: `transport/test_*.py` (6 files, Python `unittest`, discovered via `python3 -m unittest discover -s transport -p "test_*.py"` in CI) and `tests/*.sh` at the repo root (2 bash integration tests plus a manual-test doc, run individually by hand, not wired into CI at all). There's no single place to run "everything," no shared pass/fail summary across suite types, and no home for the E2E-style tests this session's manual `install → launch → dispatch → pickup` smoke test showed real value in having (it caught two real bugs `unittest` couldn't have — a podman-targeting bug and a `USER kirocrew` regression that only surfaced against a live container). Consolidating into one `tests/` root with one orchestrator makes "run the tests" a single, discoverable command with room to add E2E coverage going forward.

## What Changes

- Move `transport/test_*.py` (6 files) into the root `tests/` tree, alongside the existing bash integration tests.
- Add a single orchestrator entry point (e.g. `tests/run.sh`) that runs unit, integration, and (future) E2E suites, with per-suite selection flags and one aggregate pass/fail summary and exit code.
- Preserve the existing Podman-dependent-test auto-skip behavior (`@unittest.skipUnless(shutil.which("podman"), ...)`) and the dual import-resolution shim already present in `test_transport.py`/`test_file_transfer.py` (package-style `transport.server` import vs. flat fallback) — reconcile it against whatever new directory layout is chosen rather than leaving both branches to accidentally still work.
- Establish a placeholder for E2E tests (a `tests/e2e/` — or equivalent — location, even if it starts with zero or one test) as a first-class suite category alongside unit and integration, not an afterthought.
- Update `.github/workflows/test.yml` to invoke the new orchestrator instead of the current direct `python3 -m unittest discover -s transport` call.
- Update the `transport-test-coverage` spec's requirement that hardcodes the old path and discovery command ("Test suite runs safely inside crew containers": `python -m unittest discover -s transport -p "test_*.py"`), since the file location and command are moving.

## Capabilities

### New Capabilities
- `test-orchestration`: the root `tests/` tree as the single home for all test suites (unit, integration, E2E), the orchestrator script that runs them, and the suite-category contract (what belongs in which category, how each is invoked, how results are reported and aggregated).

### Modified Capabilities
- `transport-test-coverage`: the "Test suite runs safely inside crew containers" requirement's scenarios hardcode `python -m unittest discover -s transport -p "test_*.py"` and the `transport/` location — these need updating to the new location/command once the suite moves. The actual per-branch coverage requirements (reconcile_registry, idle_monitor, etc.) are unaffected in substance, only in where/how the suite that verifies them is invoked.

## Impact

- `transport/test_*.py` → new location under `tests/` (exact subpath TBD in design.md).
- New: `tests/run.sh` (or equivalent orchestrator), a `tests/e2e/` placeholder.
- `.github/workflows/test.yml`: invocation command changes.
- `transport/requirements.txt` / crew or transport Containerfiles: verify nothing depends on `transport/test_*.py` being colocated with `server.py` at build or runtime (none found in this session's check of the Containerfiles, but worth re-confirming during implementation).
- `README.md`: the `tests` badge points at the workflow file, not a path, so no change expected there — but worth a final check.
- No production code behavior changes — this is test/tooling infrastructure only.
