# Proposal

## Why

KiroCrew 0.13.1 is now the current stable release, while Ghostship pins 0.13.0. Upgrade the bundled crew runtime through the repository's existing image, seed-database, and release gates so crews receive upstream fixes without silently changing persistent crew state or exposing new credentials.

## What Changes

- Pin the verified multi-architecture KiroCrew 0.13.1 image consistently in the admission build and runtime default.
- Verify the bundled Kiro CLI and compare the release's SQLite schema and migrations with Ghostship's seeded database; update the seed only if required.
- Review upstream changes that intersect Ghostship's enabled workflows, especially restart/cancel message handoff and the change to local sign-in token delivery.
- Update dependency inventory, runtime documentation, changelog, and the crew-image specification with verified release details.
- Validate fresh crew creation, persistence, authentication, dispatch, pickup, and wake behavior on Corsair and Carrier; leave existing crews intact and record rollback guidance.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `installation/crew-images`: advance the supported KiroCrew image pin to 0.13.1 and require release-specific image, CLI, seeded-schema, and smoke verification before adoption.

## Impact

The admission Containerfile and transport image default, graduation seed database and its tests if the upstream schema changed, `dependencies.yaml`, runtime documentation, changelog, and the `installation/crew-images` contract. No transport API changes are expected. Existing crew containers retain their current image until their normal lifecycle replaces them; the upgrade must not nuke or recreate them automatically.
