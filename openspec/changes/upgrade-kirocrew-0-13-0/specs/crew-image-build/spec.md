# Spec Delta

## MODIFIED Requirements

### Requirement: Base-image pin tracks the target KiroCrew gateway version

The crew-image build SHALL pin the base image to the KiroCrew gateway version the
crew is intended to run, expressed as an immutable tag or digest, and the pin
default SHALL be identical in the admission build definition and the shipped
configuration default so that a build with no override matches an install build.
For validation the pin SHALL be KiroCrew `0.13.0-rc.3` at immutable multi-arch
index digest
`sha256:189c57160526f6864120184893d21d4f4905107a3886b8c7f85d93ca27c509e9`,
which provides Linux amd64 and arm64 images. A Ghostship release that targets
KiroCrew 0.13.0 SHALL NOT ship on a release-candidate pin: before release the pin
SHALL be advanced to the final `0.13.0` immutable index digest, and the image
inspection, seed verification and fresh-crew smoke checks SHALL be repeated
against it. The bundled Kiro CLI version SHALL be verified from the image rather
than inferred from the gateway release number. The digest SHALL be recorded as the
`KC_BASE_IMAGE` default in `crews/_base/admission/Containerfile`. The comment
block above the ARG SHALL record the KiroCrew version, actual Kiro CLI version,
digest, and verification date.

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

#### Scenario: release blocked on a release-candidate pin

- **WHEN** a Ghostship release targeting KiroCrew 0.13.0 is prepared
- **AND** the `KC_BASE_IMAGE` default still names a `0.13.0-rc.*` image
- **THEN** the release SHALL NOT proceed
- **UNTIL** the pin names the final `0.13.0` index digest and the image, seed and
  smoke checks have passed against it.

#### Scenario: login containers use the pinned image

- **WHEN** an operator runs a backend login after this change is applied
- **THEN** the ephemeral login container runs the same pinned KiroCrew image as
  new crews
- **AND** the Kiro CLI that captures the kiro credential is the image's bundled
  version.

### Requirement: kiro-cli DB seed matches the base-image migration schema

The build-time kiro-cli database seed SHALL pre-seed the migration rows and
resulting SQLite schema used by the pinned image's active Kiro CLI chat runtime,
so that at launch the crew only needs to insert authentication rows with no
migration wait or restart cycle. The seed SHALL record, in a human-readable
annotation, the gateway version and actual bundled Kiro CLI version it was
verified against, the verification date, and the observed migration count and
maximum version. The seed SHALL match the migration rows and table definitions
observed in the pinned image, including `auth_kv` with the columns the
auth-injection step writes and `state` with the column that holds
`api.codewhisperer.profile`. The previously verified v0.12.2 baseline is Kiro CLI
2.27.1 with 11 migration rows, versions 0 through 10. Verification MAY inspect and
query the image directly or inspect its published layers when direct execution is
unavailable. Every base-image pin change, including the move from a release
candidate to the final release, SHALL re-verify both migration rows and the
resulting table and auth schema before release.

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

#### Scenario: v0.12.2 chat schema is fully pre-seeded

- **WHEN** the previously pinned v0.12.2 image's active chat runtime is initialized
- **THEN** its seed contained 11 migration rows for versions 0 through 10
- **AND** that baseline is what the newly pinned image's schema is compared
  against when deciding whether the seed must change.

#### Scenario: injected Identity Center credential carries its profile

- **WHEN** a kiro IAM Identity Center credential that includes
  `api.codewhisperer.profile` is injected into a fresh crew built on the pinned
  image
- **THEN** the profile row lands in the seeded `state` table
- **AND** a kiro task on that crew completes without a "No profile selected"
  error.
