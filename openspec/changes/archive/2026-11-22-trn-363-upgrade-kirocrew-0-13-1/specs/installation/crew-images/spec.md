# Spec Delta

## MODIFIED Requirements

### Requirement: Base-image pin tracks the target KiroCrew gateway version

The admission build and shipped configuration SHALL default to the verified
KiroCrew `0.13.1` multi-architecture digest. Before release, maintainers SHALL
inspect the stable image, verify its bundled Kiro CLI and seed schema, and smoke
test fresh crews. The `KC_BASE_IMAGE` comment SHALL record the gateway version,
CLI version, digest, and verification date.

#### Scenario: operator builds with the default base image

- **WHEN** an operator builds the crew image without overriding the base-image
  selection
- **THEN** the admission image builds from the pinned KiroCrew gateway version
- **AND** the resulting crew runs that gateway version.

#### Scenario: build definition and configuration default stay in sync

- **WHEN** the base-image pin is changed in the build definition
- **THEN** the configuration default SHALL be updated to the same value in the
  same change
- **AND** a plain build with no override and an install build resolve to the
  identical base image.

#### Scenario: pin prefers an immutable reference

- **WHEN** the target gateway version is published both as a floating tag and as
  an immutable digest
- **THEN** the pin SHOULD use the immutable digest
- **SO THAT** a later rebuild cannot float onto a different published image
  without an explicit change.

#### Scenario: operator builds with an explicit base-image override

- **WHEN** an operator explicitly overrides `KC_BASE_IMAGE` after this change is
  applied
- **THEN** that build uses the explicit override
- **AND** a build without an override continues to use the pinned default.

#### Scenario: release uses the verified stable pin

- **WHEN** a Ghostship release targeting KiroCrew 0.13.1 is prepared
- **THEN** the `KC_BASE_IMAGE` default names the verified stable `0.13.1` index
  digest
- **AND** image inspection, seed verification and fresh-crew smoke checks have
  passed against that image.

#### Scenario: login containers use the pinned image

- **WHEN** an operator runs a backend login after this change is applied
- **THEN** the ephemeral login container runs the same pinned KiroCrew image as
  new crews
- **AND** the Kiro CLI that captures the kiro credential is the image's bundled
  version.

## REMOVED Requirements

### Requirement: Base image version

**Reason**: This duplicates the base-image pin contract while requiring the obsolete KiroCrew 0.6.0 default and hardcoding its implementation details.

**Migration**: Use `Base-image pin tracks the target KiroCrew gateway version`, which specifies the verified 0.13.1 default, synchronized configuration, and image override behavior.
