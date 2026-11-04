# Proposal

## Why

`ghostship upgrade` currently rebuilds images from whatever is checked out locally. Users who haven't run `git pull` silently rebuild stale code. `upgrade` should mean "get to the latest release" — fetch, show the version diff, confirm, checkout, install.

For dev checkouts (HEAD not on a release tag), skip the pull entirely — just rebuild. This means `upgrade` is tag-to-tag only and never interferes with active development or the adjutant submodule pin.

## What Changes

All changes are in the `ghostship` CLI script (installed at `~/.local/bin/ghostship` or equivalent). No changes to `bin/install.sh`, `bin/lib/install_main.py`, or any other file.

- **`cmd_upgrade()`** in the `ghostship` CLI script:
  1. `git fetch origin --tags --quiet`
  2. Determine current version: `git describe --tags --exact-match HEAD` → if this fails (not on a tag), skip to install
  3. Determine latest remote tag: `git tag --list 'v*' --sort=-version:refname` → first result
  4. If current == latest: print `"Already on vX.Y.Z — rebuilding"` → skip to install
  5. If current < latest: print `"vX.Y.Z → vY.Z.A  Upgrade? [y/N]"` → on 'y': `git checkout tags/vY.Z.A --quiet` → install; on 'n': exit 0
  6. Falls through to `_exec_script("bin/install.sh", install_args)` in all continuing paths

## Capabilities

_(none — no spec-level changes)_

## Impact

- `ghostship` CLI script (`cmd_upgrade` function only)
