# TRN-274: Docs Refresh

## Why

Independent review (indy-0.9.0, review ID 016025f5038b) found stale or incorrect
documentation. Most items are pre-existing; several relate to the TRN-271 base image
upgrade.

Source-verified correction: H-12 firewall range — the correct end port is `64121`, not
`65121` as the review stated. `GA_DASHBOARD_PORT_RANGE_SIZE` defaults to 64, so the
range is `64058`–`64121` (64 ports). The docs currently say `64058:65081` (1024 ports).

## What Changes

### H-10: Stale base-image references
`docs/architecture.md` lines 9 and 11 still reference `kirocrew:0.9.0-insider.4`.
`docs/configuration.md` line 58 shows the old v0.9.0 SHA (`108e6b94...`) and description.
Fix: update both to reference `kirocrew:0.10.0` / the new index digest `b6d0b9a3...`.

### H-11: Missing v0.9.0 changelog entry
`CHANGELOG.md` top entry is `v0.8.1`; `VERSION` is now `0.9.0`.
Fix: add `## v0.9.0` section covering: base image bump to KC 0.10.0, multi-arch index
digest (arm64/amd64), ghostship version bump, gateway timeout revert.

### H-12: `docs/portal.md` port range wrong
Line 206 says "1024 ports allocated". Default is 64 (`GA_DASHBOARD_PORT_RANGE_SIZE=64`).
Firewall example `64058:65081` is wrong — should be `64058:64121/tcp`.
Fix: correct "1024 ports" to "64 ports (default; configurable via
`GA_DASHBOARD_PORT_RANGE_SIZE`)"; update firewall example to `64058:64121/tcp`.

### M-9: `CREW_GATEWAY_PORT` attributed to wrong file
`docs/configuration.md:102` says it's hardcoded in `server.py` — actually defined in
`transport/constants.py:21` and imported everywhere else.
Fix: update reference to `transport/constants.py`.

### M-10: `KIRO_API_KEY` description wrong
Docs describe it as "removed in TRN-233"; it was moved to the credential store, not
removed.
Fix: update description to "stored in credential store via `ghostship auth login kiro
--method api-key`".

### M-11: `docs/troubleshooting.md` references TRN-16 as pending
TRN-16 is fully archived.
Fix: remove the pending annotation; add a resolution note if relevant.

### M-12: `docs/release-notes-0.6.0.md` uses retired config names
Upgrading section references `ghostship.conf` and `GA_AGENT_BACKENDS`.
Fix: update to current `ghostship.yaml` and equivalent config keys.

### L-6: `GA_DASHBOARD_PORT_RANGE_SIZE` missing from `docs/portal.md` config table
Fix: add row to the configuration table.

### L-7: `PODMAN_SOCKET` duplicated in config tables
Appears in both main and advanced tables in `docs/configuration.md`.
Fix: remove the duplicate; keep the more complete entry.

### L-8: `GA_REQUIRE_API_KEY` entry in docs
Docs describe it as deprecated — it has been fully removed from the transport.
Fix: remove the entry or mark as "removed (see `network.api_key`)".

### I-8: Gaps in architecture.md project layout
`transport/constants.py` and `container_scripts/` missing from the project layout tree.
Fix: add both entries with brief descriptions.

### I-9: `images.agents_ref` undocumented
`config/ghostship.yaml.example` contains `images.agents_ref` but it's absent from
`docs/configuration.md`.
Fix: add a row to the config reference table.

### I-11: TRN-267 partially superseded
TRN-267 (`indy-081-doc-fixes`) covers some of the same ground as TRN-274.
Action: review TRN-267's open tasks; close any superseded by TRN-274; keep the rest.

## Impact

- `CHANGELOG.md` — add v0.9.0 section
- `docs/architecture.md` — base image ref (lines 9, 11), project layout tree
- `docs/configuration.md` — base image SHA/description (line 58), `CREW_GATEWAY_PORT`
  file ref, `KIRO_API_KEY` description, `PODMAN_SOCKET` dedup, `GA_REQUIRE_API_KEY`,
  `images.agents_ref`
- `docs/portal.md` — port range count, firewall example, `GA_DASHBOARD_PORT_RANGE_SIZE`
- `docs/troubleshooting.md` — TRN-16 annotation
- `docs/release-notes-0.6.0.md` — retired config names
- TRN-267 pylon — review and close/update superseded items
