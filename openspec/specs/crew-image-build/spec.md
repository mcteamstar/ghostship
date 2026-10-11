# crew-image-build Specification

## Purpose

Defines how crew container images are pinned to a specific KiroCrew gateway
version and how the build-time kiro-cli database seed is kept in agreement with
that version's migration schema, so that crews start on the intended gateway and
agents authenticate on first launch without a silent schema mismatch.

## Requirements

### Requirement: Base-image pin tracks the target KiroCrew gateway version

The crew-image build SHALL pin the base image to the KiroCrew gateway version the
crew is intended to run, expressed as an immutable tag or digest, and the pin
default SHALL be identical in the admission build definition and the shipped
configuration default so that a build with no override matches an install build.

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

### Requirement: kiro-cli DB seed matches the base-image migration schema

The build-time kiro-cli database seed SHALL pre-seed the exact migration rows and
table schema present in the pinned base image's kiro-cli database, so that at
launch the crew only needs to insert authentication rows with no migration wait or
restart cycle. The seed SHALL record, in a human-readable annotation, the gateway
version it was verified against, the verification date, and the observed migration
count and maximum version.

#### Scenario: seed verified and matching the base image

- **WHEN** the base image's kiro-cli migration table reports a migration count and
  maximum version
- **AND** the seed pre-seeds exactly those migration rows and that table schema
- **THEN** the auth-injection step finds the authentication table present with the
  expected columns and the auth insert succeeds
- **AND** agents authenticate on first launch with no migration or restart cycle.

#### Scenario: base-image migration schema unchanged from the prior pin

- **WHEN** the newly pinned base image reports the same migration count, maximum
  version, and table set as the previously verified base image
- **THEN** the seed's migration rows and table-creation statements remain unchanged
- **AND** only the seed's verification annotation is updated to record the new
  verified version and date.

#### Scenario: base-image migration schema changed from the prior pin

- **WHEN** the newly pinned base image reports a different migration count, maximum
  version, or table set than the previously verified base image
- **THEN** the seed MUST be updated so its migration rows span every version the
  base image reports and its table-creation statements reflect every added,
  removed, or altered table before the image is released
- **AND** the authentication table MUST remain present with the columns the
  auth-injection step requires.

#### Scenario: base image bumped without re-verifying the seed (regression guard)

- **WHEN** the base-image pin is advanced to a new gateway version whose migration
  schema differs from the seed
- **AND** the seed is not re-verified or updated
- **THEN** the crew image still builds with no build-time error
- **BUT** the auth-injection step fails at launch (for example, a missing
  authentication table or an incomplete auth insert) and agents cannot
  authenticate.
- The re-verification of the seed against the newly pinned base image is therefore
  a release gate, not optional.

### Requirement: OpenSpec Node runtime satisfies the gateway Node floor

The spec-ops crew image SHALL install a Node runtime that meets or exceeds the Node
version floor required by the pinned KiroCrew gateway, for the OpenSpec CLI layer,
and this runtime SHALL be independent of the gateway's own internal Node runtime.
The Node installer SHALL be integrity-checked so that a drift in the upstream
installer is detected at build time.

#### Scenario: Node runtime meets the gateway floor

- **WHEN** the crew image is built for a gateway version with a given Node version
  floor
- **THEN** the spec-ops image installs a Node runtime at or above that floor for
  the OpenSpec CLI
- **AND** the OpenSpec CLI runs on that runtime independently of the gateway's
  internal Node.

#### Scenario: Node installer integrity drift is detected

- **WHEN** the upstream Node installer script content differs from the pinned
  integrity hash recorded in the build
- **THEN** the integrity check fails and the build stops
- **SO THAT** an unverified installer is never executed in the image.
