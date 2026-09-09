## Why

`tests/unit/test_file_transfer.py` installs fake `httpx`, `mcp`, `starlette`, and `uvicorn` stubs into `sys.modules` at module load time when `transport.server` cannot be imported directly. These stubs are never restored, so when `unittest-parallel` schedules `test_recovery.py` in the same process, it picks up the stub `httpx.HTTPStatusError` instead of the real one — causing all 11 `test_recovery` tests to error. The parallel runner (`bash tests/run.sh --unit`) is therefore an unreliable CI signal despite all tests passing in isolation.

## What Changes

- Add a `tearDownModule` to `test_file_transfer.py` that restores the original `sys.modules` state after the module's tests complete, removing the stub entries that were injected at load time
- The stubs remain in place for the duration of `test_file_transfer`'s own tests (behaviour unchanged); only the cleanup is new
- No changes to production code, other test files, or the parallel runner configuration

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

_(none — `skip_specs: true` — pure test infrastructure change, no spec-level behaviour)_

## Impact

- `tests/unit/test_file_transfer.py` — add module-level stub save/restore
- `bash tests/run.sh --unit` should now pass cleanly with no errors from `test_recovery`
