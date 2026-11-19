# Proposal

## Why

The dispatch contract is enrollment-based, but the active task-orchestration spec and some operator guidance still describe bridge, per-task, or arbitrary named slots. This change reconciles that documentation with the supported routing behavior while preserving runtime behavior.

## What Changes

- Specify that `slot=None` routes enrolled personas to their pre-created member DM slot and leaves unenrolled personas headless.
- Specify that `slot=False` explicitly forces headless dispatch.
- Reject `slot=True` as a distinct per-task slot mode. Preserve the current compatibility behavior: the resolver warns and treats it as `slot=None`.
- Treat string-valued slots as unsupported; the MCP tool contract exposes `slot` as boolean or null, so string values are invalid tool inputs.
- Reconcile batch dispatch with the same slot rules; one resolution is shared across every task in a batch.
- Reconcile the task-orchestration spec, README, architecture, configuration, and dispatch tool description.

## Capabilities

### New Capabilities

### Modified Capabilities

- `task-orchestration`: define the enrollment-based default and supported explicit headless mode.

## Impact

The task-orchestration spec, operator documentation, dispatch tool description, and focused single and batch dispatch tests. Dispatch routing and runtime input handling are not changing.
