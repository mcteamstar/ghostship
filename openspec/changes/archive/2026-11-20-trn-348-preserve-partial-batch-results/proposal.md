## Why

A later gateway refusal can escape the batch loop before it persists earlier accepted task IDs. Operators need those IDs to collect results without repeating work.

## What Changes

Return and persist partial results when a later gateway refusal ends dispatch. Preserve the existing error contract when no spawn succeeds.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `batch-dispatch`

## Impact

Transport behavior and focused regression coverage.
