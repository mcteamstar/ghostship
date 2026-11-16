# Design

## Context

See proposal.md — Why. The current crew-image default is the immutable KiroCrew v0.12.0 digest. It is declared in `crews/_base/admission/Containerfile` and twice in `transport/config.py`; operator-facing configuration and dependency inventory also describe the pin. The graduation image bakes a Kiro CLI SQLite database seed used by launch-time authentication injection.

Prior upgrades (TRN-293, TRN-307, and TRN-299) established the sequence: verify the published multi-architecture digest, inspect the image's Kiro CLI migration schema, update the pin and annotations, then build and smoke-test a fresh crew. TRN-299's initial plan expected Kiro CLI 3.0.0 but the image actually contained 2.27.1, so release notes and gateway version alone are not evidence of the bundled CLI version.

## Goals / Non-Goals

**Goals:**

- Pin all built-in image defaults to the verified v0.12.2 multi-architecture digest.
- Establish the image's actual bundled Kiro CLI version and SQLite schema before changing the seed.
- Record release-note compatibility findings and verify fresh-crew startup, auth injection, and dispatch.

**Non-Goals:**

- Adopting KiroCrew's KAS runtime or other new upstream features; retain Ghostship's existing Kiro CLI path.
- Changing the image seed unless inspection shows its schema is stale.
- Deploying the change to Corsair, Carrier, or another fleet. Any remote deployment requires separate explicit approval.

## Decisions

### Pin the immutable multi-architecture digest

Resolve the v0.12.2 tag to its top-level manifest digest and confirm the index contains the supported Linux architectures before updating defaults. Store the digest in the admission `ARG` and the matching transport defaults; keep the human-readable version, digest, and verification date beside the build pin. A mutable version tag is easier to read but can resolve to different content on a later rebuild, so the build remains digest-pinned.

### Inspect the built image rather than infer bundled components

Read the upstream v0.12.2 release notes, then inspect the published image's labels and contents for the actual Kiro CLI version and migration table. Compare both migration rows and the auth-related table schema with `seed_kiro_db.py`. If schema is unchanged, preserve seed logic and refresh its evidence annotation. If it differs, update the seed to match the image before building. Do not use the gateway release number as a proxy for the Kiro CLI version or database schema.

### Keep the upgrade on the existing image-build path

Update the existing pin sites and the `crew-image-build` contract instead of introducing another configuration key or a new image-selection path. Refresh the dependency inventory and operator docs, including the stale KiroCrew version in `docs/architecture.md`. Add the upgrade details under the Ghostship v0.12.2 changelog entry because this branch's `VERSION` is already 0.12.2.

### Validate the current Kiro CLI integration

The v0.12.2 release notes describe many fixes across KAS, channels, security, and session handling. Review them for changes that touch Ghostship's current gateway, credential, policy, or image assumptions. Keep the release patch mechanical unless inspection or tests show an integration change is required. Build the image and exercise a fresh crew through startup, authentication, and a dispatch; do not treat a successful image build alone as compatibility evidence.

## Risks / Trade-offs

- **The published tag may not resolve to a usable multi-architecture image yet.** → Do not advance the pin until the registry digest and required platform manifests are verified.
- **The bundled Kiro CLI migration schema may differ from v0.12.0.** → Treat schema and auth-table comparison as a release gate; update the seed before the image build if needed.
- **Gateway or policy behavior may have changed in the upstream hot patch.** → Review release notes and use the fresh-crew smoke test plus the relevant test suite to catch incompatibilities.
- **Existing crews retain their current image.** → Rebuilding the default affects newly built crews; an existing crew changes only when it is recreated with the rebuilt image.

## Migration Plan

1. Verify the v0.12.2 release, registry digest, architecture manifests, bundled Kiro CLI version, and database schema.
2. Update the image pin and synchronized defaults, then update the seed only if its schema comparison requires it.
3. Build and smoke-test the crew image in an isolated development environment; record the observed versions and results.
4. Keep remote fleet deployment outside this change until explicitly approved. If local validation fails, restore the previous v0.12.0 digest and matching annotations, then rebuild the prior image.
