## Why

The TRN-79 e2e suite covers happy-path smoke tests only. Non-happy-path flows (error responses, invalid inputs, idempotent operations) and deterministic tool surface (schedule, steer, response schemas) are untested. Extending coverage now, while the transport API is fresh, locks in correct error behaviour before TRN-71 modularisation lands.

## What Changes

- Add `tests/e2e/helpers.py` — shared `mcp_call()` helper and constants extracted from the two test files; eliminates duplication and provides a single place to update the SSE parsing logic
- Add `tests/e2e/test_transport_e2e_extended.py` — extended test suite with five new test classes:
  - `TestErrorPaths` — non-happy-path: nuke/dispatch/evac non-existent crew, pickup non-existent task, duplicate launch, nuke dry-run (no confirm)
  - `TestScheduleTool` — create + list + cancel a scheduled job; idempotent cancel of non-existent job
  - `TestSteerTool` — steer a running task (transport accepts call); steer non-existent task returns error
  - `TestResponseSchemas` — all expected fields present on launch, crews, dispatch, pickup-list, supply responses
  - `TestAuthExtended` — auth gate applies to launch, dispatch, nuke (not just crews)
- Update `tests/e2e/test_transport_e2e.py` — import `mcp_call` from helpers instead of duplicating it; add progress logging to long-running operations

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — adds tests only. No production code changes.

## Impact

- `tests/e2e/helpers.py` — new shared module
- `tests/e2e/test_transport_e2e_extended.py` — new test file
- `tests/e2e/test_transport_e2e.py` — updated to use shared helpers + logging
- No changes to `transport/`, `install.sh`, or any docs
