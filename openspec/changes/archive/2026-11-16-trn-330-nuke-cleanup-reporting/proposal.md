# Proposal

## Why

Explicit `nuke` currently uses best-effort cleanup that suppresses stop, container-removal, and volume-removal errors, then removes the registry record and reports success. Operators can therefore be told a crew was destroyed while Podman resources remain.

## What Changes

- Preserve best-effort cleanup for rollback paths where resources may never have been created.
- Make confirmed `nuke` collect and report resource cleanup failures rather than returning an unqualified success.
- Add coverage for partial cleanup and the resulting registry and response state.

## Capabilities

### New Capabilities

### Modified Capabilities
- `crew-lifecycle`: define truthful outcomes for confirmed teardown when one or more Podman removals fail.

## Impact

Crew teardown helpers, the `nuke` tool response, registry handling, and lifecycle tests. The existing confirmation requirement and destructive intent remain unchanged.
