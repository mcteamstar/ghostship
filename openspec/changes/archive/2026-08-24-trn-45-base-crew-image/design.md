## Context

`crews/spec-ops/Containerfile` mixes two concerns: generic crew infrastructure (mail stack, kiro-cli auth, admiral verification) and SDD tooling (Node.js, OpenSpec CLI). Any new composition needs the first layer but not necessarily the second. Extracting the generic layer into `crews/_base/` lets compositions inherit it and add only what they need.

The `_base` prefix follows the convention for internal build artifacts — it signals this is a build dependency, not a usable composition, and won't be surfaced in `crews/registry.json`.

## Final Layer Split

**`localhost/base:latest`** (`crews/_base/Containerfile`):
- `FROM ghcr.io/kirodotdev/kirocrew:0.3.0`
- mailutils + msmtp + msmtp-mta
- Maildir provisioning (7 mailboxes: ghost spectre banshee wraith reaper raven captain)
- `msmtprc`, `maildeliver`, `sendmail-local` (local mail infrastructure)
- `verify-admiral-sig` (HMAC verification for Admiral mail)
- `seed_kiro_db.py` + kiro-cli DB pre-seed (auth injection prereq)

**`localhost/spec-ops:latest`** (`crews/spec-ops/Containerfile`):
- `FROM localhost/base:latest`
- Node.js 24 LTS via NodeSource (with `NODESOURCE_SETUP_SHA256` integrity check)
- `@fission-ai/openspec@1.9.0` (SDD tooling — spec-ops only)
- `ARG VERSION` + `LABEL org.ghostship.version=$VERSION`

## Directory Layout

```
crews/
  _base/
    Containerfile
    maildeliver         ← moved from spec-ops/
    sendmail-local      ← moved from spec-ops/
    verify-admiral-sig  ← moved from spec-ops/
    msmtprc             ← moved from spec-ops/
    seed_kiro_db.py     ← moved from spec-ops/
  spec-ops/
    Containerfile       ← simplified: FROM localhost/base:latest + Node + OpenSpec + label
    manifest.json       ← unchanged
  registry.json         ← unchanged; _base not listed
```

## install.sh Changes

Add the base build before the spec-ops build. Base receives `VERSION`; spec-ops receives `VERSION-spec-ops` so the OCI label identifies both the ghostship release and the composition:

```bash
podman build -t localhost/base:latest \
  --build-arg VERSION="${VERSION}" \
  "${GHOSTSHIP_DIR}/crews/_base"

podman build -t localhost/spec-ops:latest \
  --build-arg VERSION="${VERSION}-spec-ops" \
  "${GHOSTSHIP_DIR}/crews/spec-ops"
```

This means `crews()` reports `crew_image_version: "0.1.0-spec-ops"` for spec-ops crews. Future compositions follow the same pattern: `"0.1.0-research"`, `"0.1.0-tooluse"`, etc. The base image carries no version label — only the final composition image does.

## Key Decisions

**Node.js in spec-ops, not base:** Node.js is only installed because OpenSpec requires it. A non-SDD composition (e.g. a research crew, a tool-use crew) has no reason to include it. It belongs with OpenSpec in spec-ops.

**`_base` not in registry.json:** The base image is a build artifact, not a launchable composition. Listing it would create confusion and invite accidental use.

**No multi-stage build:** Multi-stage (`FROM x AS base`) works within one file, not across files. Separate Containerfiles with explicit `FROM localhost/base:latest` is more readable and auditable.
