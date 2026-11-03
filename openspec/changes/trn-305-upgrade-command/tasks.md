# Tasks

## 1. Implement `cmd_upgrade()` in `transport/cli.py`

- [x] 1.1 Add a `_git_current_tag(repo_dir)` helper: runs `git describe --tags --exact-match HEAD`; returns the tag string or `None` if not on a tag
- [x] 1.2 Add a `_git_latest_remote_tag(repo_dir)` helper: runs `git fetch origin --tags --quiet` then `git tag --list 'v*' --sort=-version:refname`; returns the first result or `None`; on fetch failure prints a warning and returns `None`
- [x] 1.3 Add a `_git_is_dirty(repo_dir)` helper: runs `git status --porcelain`; returns `True` if output is non-empty
- [x] 1.4 Rewrite `cmd_upgrade()` to:
  - If `--help`/`-h`: print updated help including `--yes` flag documentation
  - Parse `--yes` flag (skip confirmation prompt)
  - Call `_git_current_tag()` — if `None` (not on tag) or `_git_is_dirty()`: print `"Not on a release tag — rebuilding from current checkout"` and fall through to install
  - Call `_git_latest_remote_tag()` — if `None`: print `"Could not reach origin — rebuilding from current checkout"` and fall through
  - If current == latest: print `"Already on vX.Y.Z — rebuilding"` and fall through
  - If current != latest: print `"vX.Y.Z → vY.Z.A"` and prompt `"Upgrade? [y/N] "` (or skip prompt if `--yes`); on 'n'/empty: `return 0`; on 'y': `git checkout tags/vY.Z.A --quiet`
  - Fall through to existing `_exec_script("bin/install.sh", install_args)` / `--skills` path

## 2. Update help text

- [x] 2.1 Update the `--help` output for `ghostship upgrade` to describe the new behaviour
- [x] 2.2 Update the `ghostship --help` subcommand summary line

## 3. Verify and commit

- [x] 3.1 Test on a checkout that is exactly on a tag: confirm version diff shown, confirm checkout happens
- [x] 3.2 Test on a dev branch (not on tag): confirm "rebuilding from current checkout" shown, no fetch attempted
- [x] 3.3 Commit on `release/0.11.1`
