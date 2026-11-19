# Proposal

## Why

Tracked archived OpenSpec notes contain a small number of personal machine paths that are not useful to future readers. Remove those host-specific details while preserving generic examples and useful historical context.

## What Changes

- Replace the identified personal paths in archived notes with generic descriptions or portable examples.
- Review surrounding text so the edits do not remove useful technical context.
- Treat public commit identity metadata as an audit question only; do not rewrite repository history in this change.

## Capabilities

### New Capabilities

### Modified Capabilities

None. This is a bounded cleanup of historical documentation, not a new runtime privacy control.

## Impact

The identified tracked files under `openspec/changes/archive/`. Untracked clone-local `.git` files and commit history are out of scope.
