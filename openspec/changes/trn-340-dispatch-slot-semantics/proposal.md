# Proposal

## Why

Current dispatch behavior routes enrolled personas with `slot=None` to their member DM session, while unenrolled personas are headless and `slot=False` forces headless dispatch. The task-orchestration spec and some docs still describe older bridge/null-slot semantics, which can mislead operators and future changes.

## What Changes

- Update the task-orchestration requirement and scenarios to state current slot resolution.
- Reconcile README, architecture, and configuration guidance, including the member-session memory cost.
- Make clear that `slot=False` is the explicit headless setting for enrolled agents.

## Capabilities

### New Capabilities

### Modified Capabilities

- `task-orchestration`: define the current null, false, and enrolled-member slot behavior.

## Impact

The task-orchestration spec and dispatch tool descriptions and docs. Dispatch runtime behavior is not changing.
