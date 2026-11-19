# Proposal

## Why

The dependency inventory describes inputs across the entire Ghostship repository, including crew images, transport and Radar packages, CI actions, and host prerequisites. Keeping this repository-wide maintenance metadata under `config/` makes it look like runtime configuration and gives it an unclear owner.

## What Changes

- Move the inventory from `config/dependencies.yaml` to the repository root as `dependencies.yaml`.
- Update the dependency checker default path, documentation, release guidance, and links to use the new location.
- Keep the `--inventory` option and its ability to point at fixture inventories.
- Preserve inventory contents and dependency review behavior; this is a location change only.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. Existing dependency-management requirements remain unchanged. This is a repository organization change with no spec-level behavior changes (`skip_specs: true`).

## Impact

The root inventory file, `scripts/dependency_check.py`, current user-facing documentation and release guidance, and tests that assert the default inventory path. Historical review records and test fixtures may retain their own historical or fixture-specific paths where changing them would obscure what they record.
