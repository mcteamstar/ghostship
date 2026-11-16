# Proposal

## Why

The idle monitor can stop a crew after a concurrent caller has begun waking it, leaving runtime state inconsistent with the registry. Also, restart leader election currently precedes the leader's cleanup `try/finally`, so an early probe or stop failure can leave waiters blocked on an event that is never signalled.

## What Changes

- Coordinate idle-stop claims with wake/restart operations so only one lifecycle transition proceeds at a time per crew.
- Ensure all restart leader exits record an outcome and release waiters.
- Add deterministic regression coverage for stop/wake overlap and failures before restart setup.

## Capabilities

### New Capabilities

### Modified Capabilities
- `crew-lifecycle`: make idle stopping and crew wake mutually coherent, and guarantee waiter release on every leader exit.
- `idle-and-recovery`: specify failure propagation for early restart-leader failures.

## Impact

The idle monitor, restart leader election and waiter signaling in Transport, plus lifecycle and recovery tests. MCP/API shapes remain unchanged.
