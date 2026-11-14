# Dependency review — 2026-11-14

## Scope and outcome

Reviewed KiroCrew v0.12.2 release notes and the published GHCR image before
changing the Ghostship base-image pin. The image index and image contents were
verified through the public registry API. The image label identifies bundled
Kiro CLI 2.27.1, and static inspection found the active chat runtime carries
migrations through version 10; the seed has been updated to match.

The release-note review found no required change to Ghostship's login command,
credential-injection interface, or configured gateway update policy. Image
inspection did find a database-schema change in the chat runtime, which is
covered by the seed update below. Runtime compatibility remains unverified:
Podman, Docker, and Buildah are not installed in this environment, so image
build, fresh-crew startup, authentication, and dispatch checks remain pending.
The dependency inventory retains compatibility status unknown.

## Release-note review

Reviewed the [KiroCrew v0.12.2 release notes](https://github.com/kirodotdev/KiroCrew/releases/tag/v0.12.2),
released 2026-11-12.

- The release changes how KiroCrew installs updates: a running gateway is not
  restarted, and an update is applied on a later start. Ghostship pins the base
  image by digest, and transport/lifecycle.py sets auto_update to false, so the
  upstream self-update behavior is disabled for this integration.
- KAS changes include policy handling for allowedCommands, allowedPaths,
  trustedAgents, and MCP settings. Ghostship's upstream build keeps BUNDLE_KAS
  disabled and continues using its existing Kiro CLI backend, so these KAS
  changes do not alter the current policy path.
- The release notes mention a CLI update prompt when kiro-cli rejects
  --auth-method. Ghostship's login flow invokes kiro-cli login
  --use-device-flow and does not pass that option.
- The release also lists gateway, security, channel, and session fixes. No
  release-note item requires a change to Ghostship's existing auth_kv injection
  contract or gateway health/readiness integration. This is a static review
  conclusion; the fresh-image smoke test is still pending.

## Registry and platform evidence

The GHCR OCI registry API resolved
ghcr.io/kirodotdev/kirocrew:0.12.2 to the immutable multi-architecture index
digest:

  sha256:e5c09209758348ec658c45a06853d4faa3b19fb93c0699ab8eca9c39e32d569e

The index contains Linux amd64 manifest
sha256:6f177f87c3850b7dd1f4a81f55f835ca516be55564910ff0a769f6dc9013bc72
and Linux arm64 manifest
sha256:69acfdc7fb82c8e35aaec39d30a4a8132c0a44bb980e7725f72243fe00959ac3.
Podman was unavailable, so the registry API was used as allowed by the change
tasks.

## Image label and content evidence

The amd64 manifest config blob is
sha256:94fd326e74c92d702606b0e9e39b0b2caef7d33064944b02e7f5e78e524323f4.
Its labels report:

- org.opencontainers.image.version: 0.12.2
- org.opencontainers.image.revision: b6599234221cfc492c0dd95fdd53643e710c9f28
- dev.kirocrew.kiro-cli.version: 2.27.1

The CLI install layer is
sha256:0e379673fd4478ede08d7b098838c62f39a4da711d9497dcd726f1fc05176cdc.
It contains /usr/local/bin/kiro-cli, kiro-cli-chat, kiro-cli-term, and
/usr/local/share/kirocrew/kiro-cli-version. Image config history shows the
version marker is written from the Kiro CLI build pin of 2.27.1.

The main kiro-cli settings module contains migrations
000_migration_table through 005_auth_table, matching the former seed's six
migration rows, versions 0–5, maximum 5. The active kiro-cli-chat and
kiro-cli-chat-v2 database modules contain migrations through
010_pinned_bin_versions: eleven rows, versions 0–10, maximum 10. The final
schema includes:

- migrations: id INTEGER PRIMARY KEY, version INTEGER NOT NULL,
  migration_time INTEGER NOT NULL
- history: id, command, shell, pid, session_id, cwd, start_time, hostname,
  exit_code, end_time, duration
- auth_kv: key TEXT PRIMARY KEY, value TEXT
- state: key TEXT PRIMARY KEY, value BLOB
- conversations: key TEXT PRIMARY KEY, value TEXT
- conversations_v2: key, conversation_id, value, created_at, updated_at;
  composite primary key (key, conversation_id), with indexes on
  (key, updated_at DESC) and (updated_at DESC)
- extracted_kas_versions and pinned_bin_versions: version TEXT PRIMARY KEY,
  last_used_at INTEGER NOT NULL

The image migration SQL leaves auth_kv unchanged. Migration 006 changes the
state value affinity to BLOB; migrations 007–010 add conversation and version
tables. Empty conversation tables are seeded with the same definitions and
indexes so the chat runtime does not need to migrate them at launch.

## Baseline comparison and compatibility status

The prior v0.12.0 pin was
sha256:d7eeab57ff9d4b265fcf05a2fa1352f1b238f730cfd6c65ebda4b36dcdef5d0f.
Its amd64 CLI layer was
sha256:c2600d096e31eaa4b7dadf7326ecc39413939082da83b9fc85ed54df2c9ffc87.
The baseline label also reports Kiro CLI 2.27.1, and its main binary contains
migrations 000–005. The v0.12.2 image adds the chat binary migration sequence
through version 10, so the former seed was incomplete for the active chat
runtime despite the unchanged CLI version label.

The seed now pre-creates the final schema and rows 0–10. The auth table remains
compatible with Ghostship's INSERT OR REPLACE path, and state values retain
SQLite's dynamic storage behavior. A focused test checks migration rows, table
definitions, and indexes. The seed was statically compared against the image's
embedded migration SQL; no live database query was possible without Podman.

Compatibility outcome: image digest, labels, embedded migration definitions,
and release-note integration points were reviewed. Runtime compatibility is
unknown until a Podman host completes the build and fresh-crew startup,
authentication, enrollment, and dispatch checks.
