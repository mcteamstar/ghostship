## Context

See proposal.md. Two file-safety bugs found in review: double-close hazard on `os.fdopen()` failure, and missing parent-directory fsync in `_write_crew_secret()`.

## Goals / Non-Goals

**Goals:**
- Fix `fd = -1` placement in `_write_auth_file()` and `_save_registry()`
- Add parent-directory fsync to `_write_crew_secret()`

**Non-Goals:**
- Restructuring the file write helpers
- Adding async alternatives

## Decisions

**D1: Move `fd = -1` to immediately after `os.fdopen()` succeeds**

Current pattern:
```python
fd = os.open(...)
try:
    with os.fdopen(fd, "w") as f:
        fd = -1   # ← WRONG: set inside the with block, after fdopen already succeeded
        ...
finally:
    if fd != -1: os.close(fd)
```

If `os.fdopen(fd)` itself raises, control goes to `finally` with `fd` still holding the original value — `os.close(fd)` attempts to close an fd that `os.fdopen` has already internally closed, causing a double-close. The fix: set `fd = -1` on the line immediately after `os.fdopen()` returns, before entering the `with` block.

Correct pattern:
```python
fd = os.open(...)
try:
    f = os.fdopen(fd, "w")
    fd = -1   # ← transfer ownership; finally won't double-close
    with f:
        ...
finally:
    if fd != -1: os.close(fd)
```

**D2: Parent-directory fsync in `_write_crew_secret()`**
After atomically writing and renaming a file, the file content is durable but the directory entry pointing to it may not be on a crash. `_save_registry()` already does `os.fsync` on file content; add the parent-dir fsync pattern. Overhead is one additional syscall per write — negligible.

## Risks / Trade-offs

- [Risk] The double-close is a theoretical hazard — `os.fdopen()` rarely raises in practice on a valid fd. → Still a correctness fix worth landing.

## Migration Plan

No migration needed. Pure code fixes. No behaviour change under normal operation.

## Open Questions

None.
