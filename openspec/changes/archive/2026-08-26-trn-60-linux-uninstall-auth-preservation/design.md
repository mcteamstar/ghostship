## Context

On Linux with a dedicated instance, `~/.local/share/${GA_MACHINE_NAME}` contains two subdirectories:

- `containers/` — the dedicated Podman storage root (containers, images, overlay layers)
- `data/` — transport state: `crews.json`, `compose.yml`, `ga-kiro-auth`, `ga-file-secret`

The machine teardown block in `uninstall.sh` currently does:

```bash
rm -rf "${HOME}/.local/share/${_MACHINE_NAME}"
```

This wipes both subdirectories. The data-dir cleanup at the bottom of the script then has nothing left to protect, making `--purge-auth` irrelevant on Linux without `--keep-machine`.

See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Make `--purge-auth` the sole control over `ga-kiro-auth` removal, on all platforms.
- Scope the Linux machine teardown wipe to `containers/` only.
- Update docs to accurately describe flag behaviour.

**Non-Goals:**
- Changing macOS teardown behaviour (machines are a separate VM, no shared directory structure).
- Changing what `--keep-machine` does on Linux (it still skips the `containers/` wipe entirely).

## Decisions

### Wipe `containers/` only, not `~/.local/share/${GA_MACHINE_NAME}`

Replacing `rm -rf "${HOME}/.local/share/${_MACHINE_NAME}"` with `rm -rf "${HOME}/.local/share/${_MACHINE_NAME}/containers"` is the minimal correct fix. The `data/` subdirectory continues through to the existing data-dir cleanup step, which already correctly handles `--purge-auth`. Runtime dirs (`${_RUNTIME_DIR}/${_MACHINE_NAME}*`) are removed separately and are unaffected.

**Alternative considered:** save/restore the auth file around the `rm -rf` — rejected as more complex and error-prone (temp file, edge cases on failure).

**Alternative considered:** document that `--keep-machine` is required to preserve auth on Linux — rejected as poor UX; the flag name implies machine VM preservation, not auth preservation.

### No change to `--keep-machine` semantics

`--keep-machine` on Linux currently skips the entire `rm -rf` of the storage root. After this fix it still skips the `containers/` wipe. Semantics unchanged.

## Risks / Trade-offs

- **Stale overlay layers after reinstall**: If `containers/` is not wiped, Podman could reuse stale image layers. This is already the case with `--keep-machine`. Wiping `containers/` (without `--keep-machine`) clears this. No change in behaviour.
- **`data/` left behind on full teardown without `--purge-auth`**: `data/` now always survives machine teardown. The data-dir cleanup at the bottom removes everything except `ga-kiro-auth`. After uninstall, `~/.local/share/${GA_MACHINE_NAME}/data/ga-kiro-auth` remains. This is the intended behaviour.

## Migration Plan

No migration needed. The fix is a one-line change to `uninstall.sh`. Existing installs are unaffected until they next run `uninstall.sh`.
