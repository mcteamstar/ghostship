## Why

The indy-0.8.1 release shipped code fixes and a default-model change that are
partially reflected in the docs, but several files still carry 0.8.0-era wording,
`ghostship.conf`-era references, and stale Known Limitations. Users reading the docs
get incorrect instructions and see limitations that were resolved in 0.8.1.

## What Changes

- **VERSION file**: bump `0.8.0` → `0.8.1` to match CHANGELOG and codebase state.
- **`docs/architecture.md` — `start.sh` config discovery order** (lines 177, 184-186):
  The code block and numbered list still show `ghostship.conf` paths. `start.sh` was
  migrated to `ghostship.yaml` in the 0.8.0 TRN-253 work. Fix the example command
  (`--config ~/ghostship.conf` → `--config ~/ghostship.yaml`) and the three numbered
  paths (all `.conf` → `.yaml`, and update the XDG paths to match the actual
  `ghost-academy/ghostship.yaml` layout in `start.sh`).
- **`docs/portal.md` — Setup section** (lines 147-152): The setup example still uses
  `# ghostship.conf` and `./install.sh --config ./ghostship.conf`. Update to
  `ghostship.yaml`.
- **`docs/release-notes-0.6.0.md` — Known Limitations — Captain autopilot** (lines
  122-125 and 208-210): Lists "Captain autopilot does not work on Claude or Codex
  backend crews" as a current limitation. This was resolved in v0.8.1 via the
  `ghostship-spawn` Academy skill (TRN-263/TRN-264). Add a resolved note pointing to
  0.8.1.
- **`docs/release-notes-0.6.0.md` — Claude OAuth `GA_CREW_ANTHROPIC_API_KEY`**
  (lines 59, 82): Still references the old config-file key that was removed in
  TRN-233. Add a note that credential management moved to `ghostship auth login`.
- **Add `docs/release-notes-0.8.1.md`**: A 0.8.1 release notes page covering the
  four fixes shipped in the hotfix (gateway error detail, Caddy CA cert volume name,
  skill bytecode exclusion, Raven order-template wording), the TRN-263 `ghostship-spawn`
  skill, and the TRN-264 academy backend delivery change. The CHANGELOG has this
  content but there is no standalone release-notes page for 0.8.1 (only 0.6.0 has one).
- **`docs/configuration.md` — `KC_BASE_IMAGE` description**: The table row still
  describes the pinned image as `0.9.0-insider.4`; the actual pinned image in
  `crews/_base/admission/Containerfile` or architecture.md should be the current
  stable `0.9.0`. Update description to reflect the current stable pin.
- **`README.md` — model access note**: The callout box says `claude-haiku-5-5`
  "requires a Pro subscription or higher." This is true for the kiro backend but
  is potentially confusing alongside the multi-backend install path. Clarify that
  this note applies to the kiro backend default; other backends use their own model
  namespaces.

## Capabilities

### New Capabilities

- `release-notes-081`: Standalone release notes page for ghostship v0.8.1 —
  captures the hotfix items, ghostship-spawn, and academy backend delivery that
  shipped in this version. Parallels the existing `docs/release-notes-0.6.0.md`.

### Modified Capabilities

_(None — all other changes are doc-only corrections to existing content; no
spec-level behaviour changes. Marking `skip_specs: true` applies for the
file corrections; the release-notes page is new content with no behaviour.)_

## Impact

- Files changed: `VERSION`, `docs/architecture.md`, `docs/portal.md`,
  `docs/release-notes-0.6.0.md`, `docs/configuration.md`, `README.md`,
  new file `docs/release-notes-0.8.1.md`.
- No code changes, no API changes, no breaking changes.
- No tests required (doc-only).
