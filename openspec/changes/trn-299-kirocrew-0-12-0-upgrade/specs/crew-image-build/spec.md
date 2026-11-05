# Spec Delta: crew-image-build

## MODIFIED: Base-image pin tracks the target KiroCrew gateway version

The crew-image build SHALL pin the base image to the KiroCrew gateway version the
crew is intended to run, expressed as an immutable tag or digest, and the pin
default SHALL be identical in the admission build definition and the shipped
configuration default so that a build with no override matches an install build.
The pin SHALL be advanced to KiroCrew v0.12.0 (kiro-cli 3.0.0, released
2026-11-05). The immutable multi-arch index digest for v0.12.0 must be obtained
via `podman manifest inspect ghcr.io/kirodotdev/kirocrew:v0.12.0` and recorded in
`crews/_base/admission/Containerfile` as the `KC_BASE_IMAGE` default. The comment
block above the ARG SHALL record: KiroCrew version v0.12.0, the digest, and the
verification date.

## MODIFIED: kiro-cli DB seed matches the base-image migration schema

The build-time kiro-cli database seed SHALL pre-seed the exact migration rows and
table schema present in the pinned base image's kiro-cli database, so that at
launch the crew only needs to insert authentication rows with no migration wait or
restart cycle. The seed SHALL record, in a human-readable annotation, the gateway
version it was verified against, the verification date, and the observed migration
count and maximum version.
Before the v0.12.0 image is released, `seed_kiro_db.py` MUST be re-verified
against the v0.12.0 image's kiro-cli migration schema using:
```
podman run --rm ghcr.io/kirodotdev/kirocrew:0.12.0 python3 -c \
  "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
   print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())"
```
If the result differs from the v0.11.2 baseline of `(6, 5)`, the seed MUST be
updated before the image is released.
