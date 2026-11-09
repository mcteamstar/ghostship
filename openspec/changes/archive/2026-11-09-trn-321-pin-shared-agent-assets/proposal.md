# Proposal

## Why

The crew image clones `mcteamstar/.agents` from the moving `main` branch, although the Containerfile comment says it pins a commit. Since 0.12.1, crews run `.agents/setup --yolo`, which applies that repository's harness approval and permission settings. Any push to `.agents` main therefore changes crew permissions at the next image build without a Ghostship review.

## What Changes

- Default `AGENTS_REF` becomes a full commit SHA (currently `3ca5a8822a9622012a7cad9a2383e88e7919ab1d`, the commit 0.12.1 was tested against) instead of `main`.
- The clone step fetches by commit, tag or branch, so a SHA works. It records the resolved commit in the `org.ghostship.agents_ref` label.
- The `shared-agent-assets` inventory entry records the pinned SHA, and the dependency check reports a non-SHA ref as unpinned.
- Operators can still set `machine.images.agents_ref` to a branch for development builds; the installer warns when the value is not a SHA or tag.

## Capabilities

### New Capabilities

### Modified Capabilities
- `crew-image-build`: adds a requirement that shared agent assets are pinned to an immutable commit by default.

## Impact

- `crews/spec-ops/Containerfile` clone step and `AGENTS_REF` default.
- `bin/lib/install_main.py` warning for moving refs.
- `config/dependencies.yaml`, `scripts/dependency_check.py`, `docs/dependencies.md`.
- Existing crews are unaffected; new crews get the pinned assets after `ghostship install`.
