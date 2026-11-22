## Why

The general limiter uses a presented bearer value before authentication and only prunes the key being consulted. This allows inactive state to accumulate.

## What Changes

Use verified identity for token buckets and cap tracked state while keeping trusted proxy resolution and endpoint quotas.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rate-limiting`

## Impact

Transport, operator configuration and focused tests.
