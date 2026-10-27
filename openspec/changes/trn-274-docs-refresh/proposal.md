# TRN-274: Docs Refresh

## Why

Independent review (indy-0.9.0, review ID 016025f5038b) found multiple stale or incorrect
documentation entries. Several relate to the TRN-271 base image upgrade; others are
pre-existing inaccuracies.

## What Changes

### H-10: Stale base-image references
`docs/architecture.md` lines 9 and 11 still reference `kirocrew:0.9.0-insider.4`.
`docs/configuration.md` line 58 shows the old v0.9.0 SHA.
Fix: update both to reference `kirocrew:0.10.0` / the new index digest.

### H-11: Missing v0.9.0 changelog entry
`CHANGELOG.md` top entry is `v0.8.1`; `VERSION` is now `0.9.0`.
Fix: add `## v0.9.0` section covering TRN-271 (base image bump, multi-arch digest fix,
version bump).

### H-12: `docs/portal.md` port range wrong
States "1024 ports allocated"; firewall example uses wrong range.
Fix: correct to "64 ports" and update firewall example to `64058:65121/tcp`.

### M-9: `CREW_GATEWAY_PORT` attributed to wrong file
Docs say it's in `server.py`; it's in `transport/constants.py`.
Fix: correct the file reference.

### M-10: `KIRO_API_KEY` description wrong
Docs say "removed in TRN-233"; it was moved to the credential store, not removed.
Fix: update description to reflect current behaviour.

### M-11: `docs/troubleshooting.md` references TRN-16 as pending
TRN-16 is fully archived.
Fix: remove the pending annotation or replace with the resolution note.

### M-12: `docs/release-notes-0.6.0.md` Upgrading section uses retired config names
References `ghostship.conf` and `GA_AGENT_BACKENDS` which no longer exist.
Fix: update to current `ghostship.yaml` / config key names.

### L-6/L-7/L-8: Minor docs table issues
- `GA_DASHBOARD_PORT_RANGE_SIZE` missing from `portal.md` config table
- `PODMAN_SOCKET` duplicated in main and advanced config tables
- `GA_REQUIRE_API_KEY` described as deprecated; it's been fully removed

### I-8/I-9: Architecture diagram and config reference gaps
- `transport/constants.py` and `container_scripts/` missing from project layout in `architecture.md`
- `images.agents_ref` in `ghostship.yaml.example` undocumented in `configuration.md`

### I-11: TRN-267 partially superseded by TRN-271
Review TRN-267 (`indy-081-doc-fixes`) and either close it or note which items TRN-271
already addressed.

## Impact

- `CHANGELOG.md` — add v0.9.0 section
- `docs/architecture.md` — base image ref, project layout
- `docs/configuration.md` — base image SHA, `images.agents_ref`, `PODMAN_SOCKET` dupe, `GA_REQUIRE_API_KEY`
- `docs/portal.md` — port range, `GA_DASHBOARD_PORT_RANGE_SIZE`
- `docs/troubleshooting.md` — TRN-16 annotation
- `docs/release-notes-0.6.0.md` — retired config names
- TRN-267 pylon — review and close/update
