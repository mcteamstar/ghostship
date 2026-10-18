# Proposal

## Why

`ghostship upgrade` rebuilds images and restarts the transport but leaves skill files stale — operators with repo installs rely on symlinks (auto-updating), but operators who installed via the Claude Code plugin or Kiro Power get static skill copies that are never refreshed. There is no single obvious answer to "how do I update my ghostship skills?", and `ghostship upgrade` is the natural place to provide one.

## What Changes

- `ghostship upgrade` gains a `--skills` flag that re-runs `ghostship setup` (skill symlink refresh + MCP re-registration) after the transport rebuild. The flag is opt-in for now; a future release may make it the default.
- A standalone `ghostship skills` subcommand is added as a direct alias for `ghostship setup`, giving a more discoverable entry point specifically for skill refresh without running a full install.
- `scripts/setup.py` already creates symlinks correctly when the repo is present. For plugin-only installs (no local repo), `ghostship upgrade --skills` SHALL print a clear message explaining how to update: reinstall the plugin from the marketplace or re-run `ghostship setup --url <remote>`.
- `install.sh` wizard post-auth step is updated to call `ghostship setup` so skills are wired after first install without a separate manual step (currently the wizard already offers this but only under certain paths — make it unconditional when `ghostship setup` is available).

## Capabilities

### New Capabilities

- (none — all behavior is extensions to existing capabilities)

### Modified Capabilities

- `trn-cli`: `ghostship upgrade` gains `--skills` flag; new `ghostship skills` subcommand added as alias for `ghostship setup`.
- `installation`: `install.sh` wizard unconditionally runs `ghostship setup` after transport start when the binary is available, so skills are wired on first install without a manual step.

## Impact

- `ghostship` CLI script — `cmd_upgrade` extended, `cmd_skills` added, dispatch table updated
- `scripts/install.sh` — wizard's post-transport-start block updated (small change)
- `tests/unit/test_ghostship_cli.py` — new tests for `ghostship upgrade --skills` and `ghostship skills`
- No transport changes; no breaking changes
