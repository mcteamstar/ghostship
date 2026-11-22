## Why

Transport currently resolves upload paths in its own filesystem, while the mutations happen in the crew. The authorization check must apply to the destination filesystem.

## What Changes

Enforce workspace containment for plain uploads, archive unpack, bundle clone, and forced replacement.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `file-transfer-security`

## Impact

Transport behavior and focused regression coverage.
