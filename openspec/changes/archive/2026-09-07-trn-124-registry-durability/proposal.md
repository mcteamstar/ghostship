## Why

`crews.json` is the single source of truth for all crew state, yet `_save_registry` writes through Python's buffered I/O without flushing or fsyncing, the `.tmp` file is created with default umask permissions, and a corrupt registry silently returns an empty dict — hiding data loss and allowing corrupt state to propagate undetected. These gaps risk silent data loss on crash and expose registry content to other local users.

## What Changes

- `_save_registry`: replace `tmp.write_text(...)` with an `os.open`/`os.fdopen` sequence that calls `flush()` then `os.fsync()` before closing, using mode `0o600` on the `.tmp` file — matching the pattern already used by `_write_auth_file` and `_write_crew_secret`.
- `_load_registry`: on `json.JSONDecodeError`, log at `ERROR` level (was `WARNING` for all exceptions), rename the corrupt file to `<name>.corrupt`, and re-raise rather than returning `{}`.
- `tests/unit/test_registry.py`: add unit tests covering (a) fsync is called on save, (b) `.tmp` is created with mode `0o600`, (c) corrupt JSON raises and renames to `.corrupt`.

## Capabilities

### New Capabilities

- `registry/durability`: Durability and integrity guarantees for the crew registry file — atomic write with fsync, restricted permissions on the temp file, and loud failure on corrupt data.

### Modified Capabilities

<!-- No existing spec-level behavior changes — this is a new durability guarantee with no prior spec. -->

## Impact

- **`transport/registry.py`**: `_save_registry` and `_load_registry` functions modified.
- **`tests/unit/test_registry.py`**: new test cases added; no existing tests broken.
- No API surface changes; no callers are affected by the `_save_registry` signature change.
- On corrupt `crews.json` the service will now raise at startup rather than continuing with an empty registry — operators must resolve or remove the `.corrupt` file to restart cleanly. This is intentional: silent empty-registry masking is worse than a loud failure.
