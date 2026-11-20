# Proposal

## Why

Podman troubleshooting guidance contains stale machine names and data paths, an outdated image count, and inconsistent minimum-version wording. This makes recovery steps unreliable for current installs.

## What Changes

- Verify the documented Podman machine and storage paths against installer configuration and environment overrides.
- Correct image-count and Podman version statements against current scripts and supported workflows.
- Refresh troubleshooting examples and verify each command against the current CLI behavior.

## Capabilities

### New Capabilities

### Modified Capabilities

None. This change updates operator guidance to match current installation behavior.

## Impact

`docs/troubleshooting.md`, `docs/manual-install.md`, and installer configuration references. Runtime behavior is unchanged.
