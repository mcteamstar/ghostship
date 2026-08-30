## Context

`tests/e2e/` has two test files after TRN-79: `test_transport_e2e.py` (smoke suite) and `test_transport_e2e_extended.py` (extended suite). Both duplicated the `_mcp_call` helper and config constants. The transport uses Streamable HTTP (MCP spec) — a plain POST to `/mcp` returns an SSE `event: message / data: {...}` frame. Two response shapes exist: JSON-body results (normal) and `isError: true` with plain-text content (transport-level errors).

**Non-obvious transport behaviours discovered during implementation:**
- `nuke confirm=False` returns a dry-run `warning` preview, not an error — it lists what would be destroyed without acting
- `schedule cancel` with a non-existent `job_id` is idempotent — returns `{status: cancelled}`, not an error
- `pickup` and `steer` with a non-existent `task_id` return `isError: true` with a plain-text 404 message, not JSON

## Goals / Non-Goals

**Goals:** Shared helper module; extended deterministic test coverage; progress logging so long-running tests are visibly working not hung.

**Non-Goals:** Agent behaviour testing (non-deterministic, belongs in eval). Full API surface coverage. Performance benchmarking.

## Decisions

### Shared helpers module

**Decision:** Extract `mcp_call()`, `is_error()`, `GHOSTSHIP_E2E_URL`, `GHOSTSHIP_API_KEY`, and `_SKIP_REASON` into `tests/e2e/helpers.py`. Both test files import from it.

**Rationale:** The SSE parsing + `isError` handling is non-trivial. Duplicating it means any fix must be applied twice. A shared module is the standard Python test pattern.

**Alternative:** Base test class with helper methods. Rejected — unittest inheritance adds complexity; a plain module import is simpler and doesn't constrain class hierarchy.

### `isError` handling in `mcp_call`

**Decision:** When `isError: true`, return `{"error": <text>}` rather than raising. Let tests assert on the error shape.

**Rationale:** Tests that verify error paths need to inspect the response. Raising would require `assertRaises`, which is awkward for checking the error message content.

### Progress logging

**Decision:** Add `print()` statements at key points in long-running tests (crew launch, task dispatch, poll iterations). Use `flush=True` so output appears immediately even when stdout is buffered.

**Rationale:** Without logging, a 7-9 minute suite run looks hung. A line like `[e2e] launching e2e-dispatch...` makes it clear the test is progressing.

### Steer test reliability

**Decision:** Poll `pickup` until `elapsed_secs > 0` (task has started) before steering, rather than `time.sleep(3)`.

**Rationale:** A fixed sleep is fragile — if the crew is under load or slow to start, 3s may not be enough. Polling until the task is confirmed running makes the test deterministic regardless of startup time.

## Risks / Trade-offs

- Stale `e2e-*` crews if `tearDown` fails mid-test. Mitigated by `setUp` nuking any stale crew with the same name before creating a fresh one.
- Suite runtime ~7-9 min total. Acceptable for a pre-release gate, not for rapid iteration. Mitigated by supporting per-class invocation.

## Migration Plan

No migration needed. Tests are additive and skip cleanly without `GHOSTSHIP_E2E_URL`.
