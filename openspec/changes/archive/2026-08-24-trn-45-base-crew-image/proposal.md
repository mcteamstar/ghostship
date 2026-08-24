## Why

Every crew composition duplicates the same infrastructure: mailutils/msmtp, maildeliver/sendmail-local, verify-admiral-sig, seed_kiro_db.py, and the Maildir provisioning block. Adding a new composition today means copying ~60 lines of Containerfile and maintaining them independently. Extracting a shared base image lets compositions inherit the common layer and only add what's unique to them.

## What Changes

- `crews/_base/Containerfile` — new base image (`localhost/base:latest`) containing generic crew infrastructure that every composition needs: the KiroCrew upstream image, mailutils + msmtp, Maildir provisioning for all 7 mailboxes, maildeliver, sendmail-local, verify-admiral-sig, msmtprc, seed_kiro_db.py, and the kiro-cli DB pre-seed. The `_base` prefix signals this is an internal build dependency, not a usable composition.
- `crews/_base/` — shared scripts moved from `crews/spec-ops/`: maildeliver, sendmail-local, verify-admiral-sig, msmtprc, seed_kiro_db.py
- `crews/spec-ops/Containerfile` — `FROM localhost/base:latest`, then installs Node.js (required for OpenSpec) and the OpenSpec CLI (SDD-specific tooling), then adds the `VERSION` arg and `org.ghostship.version` OCI label
- `install.sh` — add `podman build` for the base image before building spec-ops; `_base` must build first. Pass `VERSION` arg to both builds.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `installation`: add a base image build step before composition builds

## Impact

- `crews/_base/Containerfile` — new file
- `crews/_base/maildeliver`, `sendmail-local`, `verify-admiral-sig`, `msmtprc`, `seed_kiro_db.py` — moved from `crews/spec-ops/`
- `crews/spec-ops/Containerfile` — slimmed down; Node.js + OpenSpec remain here as SDD-specific
- `install.sh` — one extra `podman build` step
- `crews/registry.json` — no change; `_base` is not a composition
- No change to transport, MCP tools, crew lifecycle, or Academy config
- Existing installs: `install.sh` rebuild will produce the same `spec-ops:latest` image — no behaviour change
