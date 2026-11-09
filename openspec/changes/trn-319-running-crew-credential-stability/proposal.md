# Proposal

## Why

Credential changes currently reach into running crews in two harmful ways. A login that saves successfully reports failure when pushing the credential into any running crew fails, and a rotated static credential makes every call to an already-running crew fail, evac included. Ghostship's operating rule is that existing crews keep what they were launched with and are touched as little as possible; these paths break that rule.

## What Changes

- Login commits the credential first and reports success once it is durably stored. Propagation to running crews of the same backend and profile becomes best-effort, reported per crew, and never turns a stored credential into a login failure or keeps the pending flow retrying.
- Propagation no longer runs Podman work while holding the credential transaction lock on the event loop.
- The static-credential check in crew wake runs only when a stopped crew is being started. A running crew keeps serving dispatch, pickup, steer, schedule, captain and file transfers with the credential it was launched with, even after the stored credential rotates.
- Kiro login regains its earlier behaviour of logging a per-crew injection failure and still completing.

## Capabilities

### New Capabilities

### Modified Capabilities
- `auth/credential-profiles`: login success depends only on durable storage; propagation to running crews is best-effort; running crews keep their launch-time credential and static validation applies only at start.

## Impact

- `transport/login.py`: `_store` for Claude, Codex and Kiro; `_propagate_oauth`.
- `transport/launcher.py`: `ensure_running` static-credential check placement.
- Tests: `tests/unit/test_login.py`, `tests/unit/test_credentials_routes.py`, `tests/unit/test_lifecycle.py`.
- No API shape change. Operators who rotate a static key and want running crews on the new key still relaunch them, as today.
