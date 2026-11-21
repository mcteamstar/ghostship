# Recover Captain after Raven fails to resume

## Why

The Carrier and Corsair multi Specky runs stalled after the gateway accepted a Raven continuation and returned a task ID. That task later reported `resume_failed`, leaving Captain enabled without advancing the order.

## What Changes

- Recover from an explicit session restore failure returned by the continuation request or recorded on the resulting Raven task.
- Retire the failed task ID and start one fresh check-in for the same standing order. Reconcile existing work before admitting new tasks.
- Preserve current handling of busy or missing sessions and unrelated gateway failures.

## Capabilities

### Modified Capabilities

- `captain`: Recover a standing order after Raven's session fails to restore.

## Impact

Captain check-in and schedule state, Raven's recovery instructions, and Captain regression tests. The change applies across standing orders.
