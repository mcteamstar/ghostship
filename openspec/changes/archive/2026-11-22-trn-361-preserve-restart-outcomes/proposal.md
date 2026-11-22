# Proposal

## Why

A startup waiter can wake after its leader has recorded a successful result, then find that a new restart generation began before it reads the outcome. The current generation check rejects that waiter even though the outcome for the cycle it actually waited on is available, turning a successful wake into a spurious failure.

## What Changes

- Retain restart outcomes by crew and generation long enough for all registered waiters to read the generation they joined.
- Keep failures isolated to their own restart generation and continue propagating the leader's failure to its waiters.
- Add deterministic concurrency coverage for a new restart beginning between event signaling and a prior waiter's outcome read.

## Capabilities

- `crew-lifecycle/startup`
- `testing/launcher`

## Impact

Per-crew restart coordination state and concurrency tests change. The caller still fails when its own restart cycle fails or no outcome is recorded; only cross-generation outcome corruption is removed.
