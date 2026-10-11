# Spec Delta — TRN-219: Node 24 LTS crew image

Capability: **crew-image-build** (base-image pinning + kiro-cli DB seed)

This delta describes the behaviour and configuration after the change. It is a
delta against the current (0.8.0-pinned) crew image build.

## MODIFIED Requirement: base-image pin tracks the target KiroCrew version

The crew-image build SHALL pin `KC_BASE_IMAGE` to the KiroCrew gateway version the
crew is intended to run, by immutable tag or digest.

### Before (0.8.0)
- `crews/_base/admission/Containerfile`: `ARG KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.8.0`
- `ghostship.conf` default: `KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.8.0`

### After (0.9.0)
- `crews/_base/admission/Containerfile`: `ARG KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`
- `ghostship.conf` default: same value (Containerfile default and config default
  MUST remain identical so a plain `podman build` matches an install build).
- The pin SHOULD prefer the immutable digest
  `ghcr.io/kirodotdev/kirocrew@sha256:f4f4801898572175a1988e61a8696769821528860edceaf5ca253f8123a77009`
  over the floating `insider` tag for reproducibility.

#### Scenario: operator builds with the default base image
- **WHEN** an operator runs the install without overriding `KC_BASE_IMAGE`
- **THEN** the admission image builds `FROM ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`
- **AND** the resulting crew runs the 0.9.0 gateway.

## MODIFIED Requirement: kiro-cli DB seed matches the base image migration schema

The build-time seed in `crews/_base/graduation/seed_kiro_db.py` SHALL pre-seed the
exact migration rows and table schema present in the pinned base image's kiro-cli
database, so that transport only needs to INSERT `auth_kv` rows at launch with no
migration wait.

### Interface / seed contract after the change

The seed is re-verified against the new base image. The verification command
(already documented in the file header) is authoritative:

```
podman run --rm ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4 python3 -c \
  "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
   print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())"
```

- **IF** the result equals `(6, 5)` (unchanged from 0.8.0): the `INSERT INTO
  migrations` block and `CREATE TABLE` statements remain as-is; only the ⚠️ header
  annotation is updated to record the new verified tag and date.
- **IF** the result differs (e.g. `(N, M)` with `M > 5`): the seed MUST be updated —
  the `migrations` INSERT extended to versions `0..M` (N rows), and any
  added/renamed/dropped tables reflected in the `executescript` body — before the
  image is released.

#### Scenario: 0.9.0 added migrations and the seed was updated
- **WHEN** the base image is `0.9.0-insider.4` and its migration table reads `(N, M)`
- **AND** `seed_kiro_db.py` has been updated to seed versions `0..M` across `N` rows
- **THEN** `inject_auth.py` finds the `auth_kv` table present with the expected
  columns and the auth insert succeeds
- **AND** agents authenticate on first launch with no migration/restart cycle.

#### Scenario: base image bumped without re-verifying the seed (regression guard)
- **WHEN** `KC_BASE_IMAGE` is bumped but `seed_kiro_db.py` still seeds the 0.8.0
  schema and 0.9.0 changed it
- **THEN** the crew image builds successfully (no build-time error)
- **BUT** `inject_auth.py` fails at launch with `no such table: auth_kv` or a
  silently-incomplete auth insert, and agents cannot authenticate.
- This scenario is the failure this change exists to prevent; the re-verify step is
  therefore a release gate, not optional.

## UNCHANGED (verified) Requirement: spec-ops installs Node 24 for OpenSpec

`crews/spec-ops/Containerfile` already installs Node 24 LTS via NodeSource
(`setup_24.x`, integrity-checked by `NODESOURCE_SETUP_SHA256`). This satisfies the
0.9.0 Node 24 floor for the OpenSpec CLI layer and is independent of the gateway's
internal Node. No change is required unless the NodeSource setup script's SHA-256
drifts, in which case `NODESOURCE_SETUP_SHA256` is recomputed.

## New / modified config keys

| Key | Scope | Before | After |
|---|---|---|---|
| `KC_BASE_IMAGE` | `ghostship.conf` + `admission/Containerfile` `ARG` default | `ghcr.io/kirodotdev/kirocrew:0.8.0` | `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` (prefer digest) |

No new config keys are introduced; this change re-pins an existing one and
re-verifies a build-time data seed.
