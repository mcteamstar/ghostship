## Why

The six bind-mounts that project `academy/` subdirectories (`agents`, `skills`, `steering`, `policies`, `orders`) and `crews/` into the transport container use absolute paths baked at install time from the git checkout location. Moving or deleting the repo breaks the container silently — the paths no longer resolve but Compose reports the container as running, so the failure mode is invisible until agent dispatches start failing.

## What Changes

- **install.sh** — instead of writing six bind-mount lines into `compose.yml` pointing at `${GHOSTSHIP_DIR}/academy/*` and `${GHOSTSHIP_DIR}/crews`, copy those directories into the data volume (`${DATA_DIR}/academy/` and `${DATA_DIR}/crews/`) at install time, then mount from the data volume in the generated `compose.yml`.
- **Generated compose.yml** — replace the six host-path bind-mount lines with volume-local paths (`${DATA_DIR}/academy/agents`, etc.) that live inside the already-present `/data` mount, so the transport container has no dependency on the repo checkout at all.
- **docs/configuration.md** — add a note that `academy/` and `crews/` are snapshotted into the data volume at install time; changes to those directories require re-running `./install.sh` to take effect.
- **README.md** — add the same reinstall-to-update note in the Setup / extending-the-crew-image section.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `installation`: The install contract changes — `academy/` and `crews/` are now copied into the data volume at install time rather than bind-mounted live from the repo. The transport container paths (`/agents`, `/skills`, `/steering`, `/policies`, `/orders`, `/crews`) remain identical inside the container; only the backing source changes from host bind-mount to a copy inside the existing data volume. Updating these assets requires a reinstall.

## Impact

- `install.sh` — gains a copy step after image build, before `compose.yml` generation; the six academy/crews bind-mount entries in the generated `compose.yml` are replaced with data-volume-relative paths.
- `${DATA_DIR}/compose.yml` (generated artifact) — six volume entries change source from `${GHOSTSHIP_DIR}/academy/*` to `${DATA_DIR}/academy/*` (all still `:ro`).
- `docs/configuration.md` and `README.md` — documentation updated.
- No changes to `transport/`, `uninstall.sh`, or `start.sh` — the compose file remains the source of truth for mounts, so those scripts are unaffected.
- No container API or MCP interface changes.
