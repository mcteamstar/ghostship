## Context

`_save_registry` currently uses `Path.write_text()` on the `.tmp` file, which goes through Python's buffered I/O and does not guarantee the data is flushed to the kernel or synced to stable storage before `os.replace` is called. The `.tmp` file is also created with whatever umask is active, typically `0o644`. `_write_crew_secret` and `_write_auth_file` (in `server.py`) already implement the correct pattern: `os.open` with explicit mode, `flush()` + `os.fsync()`, wrapped in try/finally to close the raw fd.

`_load_registry` currently catches all exceptions with `logger.warning` and returns `{}`. A corrupt `crews.json` is therefore indistinguishable from a missing one — the service starts as if no crews exist and subsequent saves overwrite the corrupt file, destroying data.

See `proposal.md — Why` for motivation.

## Goals / Non-Goals

**Goals:**
- `_save_registry` guarantees data is on stable storage before returning
- The `.tmp` file is always created mode `0o600`
- Corrupt `crews.json` produces a loud failure (logged ERROR + exception) and is quarantined as `.corrupt` before the exception propagates
- Implementation exactly mirrors the `_write_auth_file` / `_write_crew_secret` pattern already in the codebase

**Non-Goals:**
- No change to `os.replace` atomicity (already correct)
- No change to `os.chmod(REGISTRY_PATH, 0o600)` on the final file (kept as-is)
- No fsync of the containing directory (out of scope; OS-level concern for most deployments)
- No retry logic on corrupt load (caller decides whether to recreate)

## Decisions

### D1: Use `os.open`/`os.fdopen` for `.tmp`, not `Path.write_text`

The project already has two precedents for durable file writes (`_write_crew_secret`, `_write_auth_file`). Reusing the same pattern keeps the codebase consistent and avoids introducing a third approach. The pattern is:

```python
fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
try:
    with os.fdopen(fd, "w") as f:
        fd = -1
        f.write(json.dumps(reg, indent=2))
        f.flush()
        os.fsync(f.fileno())
finally:
    if fd != -1:
        os.close(fd)
```

Alternative considered: `tmp.write_text(...); tmp.chmod(0o600); fd = open(tmp); os.fsync(fd.fileno())` — rejected because there is a window between `write_text` and `chmod` where the file is world-readable, and the fd acquired after `write_text` is a new open, not the one used to write.

### D2: Raise on corrupt JSON, rename to `.corrupt` first

On `json.JSONDecodeError`:
1. Log at `ERROR` (was `WARNING` for all exceptions).
2. Rename `REGISTRY_PATH` → `REGISTRY_PATH.with_suffix(".corrupt")`.
3. Re-raise (or raise `RuntimeError` wrapping the original).

Renaming before raising ensures the corrupt file is quarantined even if a caller catches the exception and retries. The `.corrupt` suffix is visible to operators without introducing a new file extension convention.

Alternative considered: delete the corrupt file — rejected because deleting destroys evidence; operators may need the file to recover data.

Alternative considered: log and return `{}` (current behavior) — rejected; see `proposal.md — Why`. Silent masking is the root cause of the ticket.

### D3: No change to missing-file behavior

`REGISTRY_PATH.exists()` returning False → return `{"crews": {}}` is correct and unchanged. The new loud-failure path is gated on the file existing AND being unreadable as JSON.

## Risks / Trade-offs

- **Service fails to start on corrupt registry** → Mitigation: operators remove or rename `crews.json.corrupt` and restart. This is the intended behavior; silent restart with data loss is worse. Document in release notes.
- **Rename-to-.corrupt fails** (e.g., disk full, permission error) → The `os.rename` call should itself raise; that exception will propagate instead of the `JSONDecodeError`. The ERROR log will still have been emitted. Acceptable: the operator knows something went wrong.
- **fsync latency** → On spinning-disk hosts, fsync adds ~5–15 ms per registry write. Registry writes are rare (crew create/delete, schedule updates) so this is negligible.

## Migration Plan

1. Deploy updated `transport/registry.py`.
2. No data migration needed; the file format is unchanged.
3. Rollback: revert the two functions. Existing `.corrupt` files are inert.
