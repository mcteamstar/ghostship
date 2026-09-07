## 1. Fix fd sentinel in _write_auth_file()

- [x] 1.1 In `transport/server.py`, refactor `_write_auth_file()` to set `fd = -1` immediately after `os.fdopen()` returns, before the `with` block body:
  ```python
  f = os.fdopen(fd, "w")
  fd = -1
  with f:
      f.write(value)
      f.flush()
      os.fsync(f.fileno())
  ```

## 2. Fix fd sentinel in _save_registry()

- [x] 2.1 In `transport/registry.py`, apply the same fix to `_save_registry()` — set `fd = -1` immediately after `os.fdopen()` returns, before the `with` block body

## 3. Add parent-directory fsync to _write_crew_secret()

- [x] 3.1 In `transport/server.py`, after `_write_crew_secret()` closes the file, add:
  ```python
  dir_fd = os.open(str(path.parent), os.O_RDONLY)
  try:
      os.fsync(dir_fd)
  finally:
      os.close(dir_fd)
  ```
- [x] 3.2 Verify this pattern matches `_save_registry()`'s existing approach (or adapt to the local style)

## 4. Validation

- [x] 4.1 Run `openspec validate trn-139-fd-file-safety`
- [x] 4.2 Run `bash tests/run.sh --unit` — all tests pass
