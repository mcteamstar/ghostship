# Proposal

## Why

Ghostship currently pins its crew image to KiroCrew v0.12.0. KiroCrew v0.12.2, released on 2026-11-12, is a follow-up hot patch with security, reliability, and data-loss fixes; upgrading lets newly built crews receive those fixes while preserving Ghostship's reproducible image and authentication setup. The [upstream release notes](https://github.com/kirodotdev/KiroCrew/releases/tag/v0.12.2) are the compatibility review starting point.

## What Changes

- Advance the immutable `KC_BASE_IMAGE` pin to the verified KiroCrew v0.12.2 multi-architecture image digest in the admission build default and matching configuration default.
- Inspect the published image for its actual bundled Kiro CLI version and SQLite migration schema. Update the database seed only if the verified schema requires it; record the inspected version and evidence.
- Update the `crew-image-build` requirements, dependency inventory/review evidence, and image-version documentation to describe the verified v0.12.2 image.
- Build the crew image and smoke-test a fresh crew's startup, authentication, and dispatch. Record the release note findings relevant to Ghostship's existing integration.
- Add the upgrade note to the existing Ghostship v0.12.2 changelog entry; the current branch already declares Ghostship version 0.12.2.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `crew-image-build`: advance the required KiroCrew image version and require the v0.12.2 image's bundled CLI migration schema to be verified before release.

## Impact

- `crews/_base/admission/Containerfile` and `transport/config.py` — immutable image pin and version annotations
- `crews/_base/graduation/seed_kiro_db.py` and `crews/_base/graduation/Containerfile` — verified migration/version annotations, with seed logic changed only if the schema differs
- `openspec/specs/crew-image-build/spec.md` — target image and migration verification requirement
- `config/dependencies.yaml` and a dated dependency review — pin review and compatibility evidence
- `docs/configuration.md`, `docs/architecture.md`, and `CHANGELOG.md` — operator-facing image version and upgrade notes
- Crew image build and fresh-crew smoke verification
