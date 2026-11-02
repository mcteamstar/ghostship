# crew-image-build — Delta Spec (TRN-293)

## MODIFIED Requirements

### Requirement: Base-image pin tracks the target KiroCrew gateway version

The crew-image build SHALL pin the base image to the KiroCrew gateway version the
crew is intended to run, expressed as an immutable tag or digest, and the pin
default SHALL be identical in the admission build definition and the shipped
configuration default so that a build with no override matches an install build.

The pin SHALL be advanced to KiroCrew v0.11.1 (commit `fe6f5be`, released
2026-10-31). The immutable multi-arch index digest for v0.11.1 must be obtained
via `podman manifest inspect ghcr.io/kirodotdev/kirocrew:v0.11.1` and recorded in
`crews/_base/admission/Containerfile` as the `KC_BASE_IMAGE` default. The comment
block above the ARG SHALL record: KiroCrew version v0.11.1, the digest, and the
verification date.

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

#### Scenario: operator builds with the v0.11.1 base image

- **WHEN** an operator builds the crew image after this change is applied
- **THEN** the admission image builds from the KiroCrew v0.11.1 base image
- **AND** the resulting crew runs the v0.11.1 gateway (memory WAL fix, shell
  reader security fix, and three CVE fixes included)

### Requirement: kiro-cli DB seed matches the base-image migration schema

The build-time kiro-cli database seed SHALL pre-seed the exact migration rows and
table schema present in the pinned base image's kiro-cli database, so that at
launch the crew only needs to insert authentication rows with no migration wait or
restart cycle. The seed SHALL record, in a human-readable annotation, the gateway
version it was verified against, the verification date, and the observed migration
count and maximum version.

Before the v0.11.1 image is released, `seed_kiro_db.py` MUST be re-verified
against the v0.11.1 image's kiro-cli migration schema using:

```bash
podman run --rm ghcr.io/kirodotdev/kirocrew:v0.11.1 python3 -c \
  "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
  print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())"
```

If the result differs from the v0.10.0 baseline of `(6, 5)`, the seed MUST be
updated before the image is released.

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

#### Scenario: migration schema unchanged from v0.10.0

- **WHEN** the v0.11.1 image reports migration result `(6, 5)` (identical to v0.10.0)
- **THEN** only the verification annotation in `seed_kiro_db.py` is updated
- **AND** no migration rows or table-creation statements change

#### Scenario: migration schema changed from v0.10.0

- **WHEN** the v0.11.1 image reports a different migration count or max version
- **THEN** `seed_kiro_db.py` migration rows and table-creation statements are updated
  to match before the image is released
