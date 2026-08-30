## 1. Shared helpers

- [x] 1.1 Create `tests/e2e/helpers.py` with `mcp_call()`, `is_error()`, `GHOSTSHIP_E2E_URL`, `GHOSTSHIP_API_KEY`, `_SKIP_REASON`
- [x] 1.2 Update `tests/e2e/test_transport_e2e.py` to import from helpers (remove duplicated helper)
- [x] 1.3 Add progress logging (`print(..., flush=True)`) to long-running operations in `test_transport_e2e.py` — crew launch, dispatch, pickup poll iterations

## 2. Extended test suite

- [x] 2.1 Create `tests/e2e/test_transport_e2e_extended.py` importing from helpers
- [x] 2.2 `TestErrorPaths` — nuke/dispatch/evac non-existent crew, pickup non-existent task, duplicate launch, nuke dry-run
- [x] 2.3 `TestScheduleTool` — create + list + cancel job; idempotent cancel of non-existent job
- [x] 2.4 `TestSteerTool` — steer running task (poll until started first); steer non-existent task
- [x] 2.5 `TestResponseSchemas` — launch, crews, dispatch, pickup-list, supply response fields
- [x] 2.6 `TestAuthExtended` — auth gate on launch, dispatch, nuke
- [x] 2.7 Add progress logging to `test_transport_e2e_extended.py` — crew launch, poll iterations, key checkpoints

## 3. Verification

- [x] 3.1 Run `GHOSTSHIP_E2E_URL=http://your-academy-host bash tests/run.sh --e2e` — all tests pass, progress output visible during run
- [x] 3.2 Run `bash tests/run.sh --e2e` (no env var) — all 25 tests skip cleanly
