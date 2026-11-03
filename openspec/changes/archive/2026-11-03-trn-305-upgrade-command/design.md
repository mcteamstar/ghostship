# Design

## Context

`cmd_upgrade()` in the `ghostship` CLI script currently fast-paths straight to `_exec_script("bin/install.sh", ...)`. The new flow inserts a git fetch + version check before that. All paths still end with the same install call.

## Decisions

### D1 — Tag detection with `git describe --tags --exact-match`

If HEAD is not exactly on a tag (dev checkout, between releases, adjutant submodule pinned mid-release), this command exits non-zero. We catch that and skip the pull — just rebuild. This is the correct behaviour for `starport` and for any developer running off a branch.

### D2 — Latest tag via `git tag --list 'v*' --sort=-version:refname`

Sorts version tags semantically (v0.11.1 > v0.11.0 > v0.9.0). Takes the first result. Filters to `v*` to avoid matching non-release tags. Run after `git fetch origin --tags` so remote tags are available.

### D3 — Version comparison: string equality only

We don't need semver comparison — if `current != latest` after a fetch, latest is newer by definition (we only ever move forward, and the latest remote tag is always ≥ current). So `current == latest` → no-op; `current != latest` → offer upgrade.

### D4 — Prompt is `[y/N]` (default no)

Upgrade is a meaningful action (checkout + full rebuild, ~2 min). Defaulting to no is safer. Non-interactive environments (CI, `--yes` flag) can bypass: add `--yes` flag support to `cmd_upgrade` to skip the prompt.

### D5 — `git checkout tags/vX.Y.Z --quiet`

Puts HEAD in detached state on the tag. This is the correct state for a user install — not on a branch, on a pinned release. The subsequent `install.sh` run builds from this exact tree.

### D6 — No rollback

Out of scope. If the upgrade fails mid-install, the user can `git checkout tags/vX.Y.0` and re-run.

## Edge cases

- **No remote tags**: `git tag --list 'v*'` returns empty → treat as already up to date, just rebuild
- **Fetch fails** (no network): print a warning, skip to rebuild with local state
- **Dirty working tree**: `git checkout` would fail — detect with `git status --porcelain`, warn and skip pull

## Migration Plan

The `ghostship` CLI script is installed by `install.sh` from `transport/cli.py` (the source). Editing `transport/cli.py` and running `ghostship upgrade` (or `install`) will update the installed script.
