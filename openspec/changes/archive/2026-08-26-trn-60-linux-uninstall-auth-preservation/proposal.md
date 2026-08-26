## Why

On Linux with a dedicated instance (the default), `uninstall.sh` wipes `~/.local/share/${GA_MACHINE_NAME}` entirely during machine teardown — unless `--keep-machine` is passed. This includes `data/ga-kiro-auth`, even when `--purge-auth` is not set. The `--purge-auth` flag is documented and intended as the sole opt-in for removing auth; the machine teardown path silently bypasses it, forcing users to re-authenticate after every reinstall unless they remember to pass `--keep-machine`.

## What Changes

- On Linux, the dedicated machine teardown SHALL wipe only the `containers/` subdirectory, not the entire `~/.local/share/${GA_MACHINE_NAME}` tree.
- The existing data-dir cleanup logic (which already respects `--purge-auth`) handles `data/` correctly — no separate change needed there.
- Documentation (`docs/configuration.md` and/or `uninstall.sh` help text) updated to accurately describe when auth is preserved vs. removed.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `installation`: The dedicated machine uninstall requirement and the file-based transport auth persistence requirement gain a new scenario clarifying that Linux machine teardown does not remove `ga-kiro-auth` unless `--purge-auth` is passed.

## Impact

- `uninstall.sh`: single-line change to the Linux machine teardown path.
- `docs/configuration.md` or inline help text: clarify `--purge-auth` / `--keep-machine` interaction on Linux.
