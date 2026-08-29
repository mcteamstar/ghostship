## 1. Create Config dataclass

- [ ] 1.1 Create `transport/config.py` with a `@dataclass Config` containing all env var fields and their defaults, matching current `os.environ.get()` calls in `server.py`
- [ ] 1.2 Add `Config.from_env()` classmethod that reads all env vars and constructs the instance
- [ ] 1.3 Instantiate `cfg = Config.from_env()` at module level in `server.py`

## 2. Replace os.environ.get() calls in server.py

- [ ] 2.1 Replace all `os.environ.get("GA_*", ...)` calls in `server.py` with `cfg.<field>` reads
- [ ] 2.2 Replace all `os.environ.get("KC_*", ...)` calls with `cfg.<field>` reads
- [ ] 2.3 Replace remaining `os.environ.get()` calls (PORT, HOST, etc.) with `cfg.<field>` reads
- [ ] 2.4 Check `transport/security.py` for any `os.environ.get()` calls and replace with `cfg.<field>` reads if present
- [ ] 2.5 Verify no `os.environ.get()` calls remain in `server.py` or `security.py` (except inside `Config.from_env()`)

## 3. Sync ghostship.conf.example

- [ ] 3.1 Audit `config/ghostship.conf.example` against `Config` fields — add any missing entries as commented-out lines
- [ ] 3.2 Update `docs/configuration.md` to close any gaps found

## 4. CI sync test

- [ ] 4.1 Add a unit test in `tests/unit/` that reads all `Config` field names via `dataclasses.fields()` and asserts each has a corresponding entry in `ghostship.conf.example`

## 5. Verification

- [ ] 5.1 Run `bash tests/run.sh --unit` — all tests pass
- [ ] 5.2 Run `bash tests/run.sh --integration` — all tests pass
