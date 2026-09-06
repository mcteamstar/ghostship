## 1. Harden `_save_registry` in `transport/registry.py`

- [ ] 1.1 Replace `tmp.write_text(json.dumps(reg, indent=2))` with an `os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)` / `os.fdopen` block that calls `f.flush()` then `os.fsync(f.fileno())` before the context manager exits, using the same try/finally fd-guard pattern as `_write_auth_file` in `server.py`
- [ ] 1.2 Verify the existing `os.chmod(REGISTRY_PATH, 0o600)` call on the final file is retained after the `os.replace` line

## 2. Harden `_load_registry` in `transport/registry.py`

- [ ] 2.1 Split the single broad `except Exception` into two branches: catch `json.JSONDecodeError` separately before the general handler
- [ ] 2.2 In the `json.JSONDecodeError` branch: log at `ERROR` level (not `WARNING`), rename `REGISTRY_PATH` to `REGISTRY_PATH.with_suffix(".corrupt")` via `os.replace`, then re-raise the original exception
- [ ] 2.3 Keep the existing general `except Exception` branch (for I/O errors on a non-existent or unreadable file) logging at `WARNING` and returning `{"crews": {}}` unchanged

## 3. Add unit tests in `tests/unit/test_registry.py`

- [ ] 3.1 Add a test that calls `_save_registry` with a tmp dir as `DATA_DIR`, then asserts `os.fsync` was called (mock `os.fsync` via `patch("os.fsync")`) and that the resulting `crews.json` contains the expected data
- [ ] 3.2 Add a test that calls `_save_registry` and asserts the `.tmp` file was opened with mode `0o600` — patch `os.open` to capture the `mode` argument while still delegating to the real `os.open`
- [ ] 3.3 Add a test that writes invalid JSON to `REGISTRY_PATH`, calls `_load_registry`, and asserts: (a) an exception is raised, (b) `crews.json.corrupt` exists, (c) `crews.json` no longer exists, (d) an `ERROR`-level log message was emitted
- [ ] 3.4 Add a test that confirms `_load_registry` still returns `{"crews": {}}` when the registry file is absent (no regression)

## 4. Validate

- [ ] 4.1 Run `openspec validate --change trn-124-registry-durability` and confirm no errors
- [ ] 4.2 Run existing registry unit tests (`python -m pytest tests/unit/test_registry.py -v`) and confirm all pass
