# Proposal

## Why

The authentication guide conflates OAuth reauthentication with static credential rotation. OAuth refresh can be propagated to running crews, while a running crew retains a static credential from launch until it is restarted; the distinction affects operator recovery advice.

## What Changes

- Explain OAuth reauthentication propagation separately from static credential updates.
- Recheck nearby launch and recovery guidance against current credential gating and propagation code.
- Keep the change documentation-only; authentication behavior remains governed by existing specifications and implementation.

## Capabilities

### New Capabilities

### Modified Capabilities

None. This change clarifies existing documented behavior and does not change system behavior.

## Impact

`docs/auth.md` and any linked operator guidance. No runtime or credential storage changes.
