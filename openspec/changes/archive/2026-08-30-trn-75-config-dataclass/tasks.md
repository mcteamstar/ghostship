## 1. Create Config dataclass

- [x] 1.1 Create `transport/config.py` with a `@dataclass Config` containing all env var fields and their defaults, matching current `os.environ.get()` calls in `server.py`
- [x] 1.2 Add `Config.from_env()` classmethod that reads all env vars and constructs the instance
- [x] 1.3 Instantiate `cfg = Config.from_env()` at module level in `server.py`

## 2. Replace os.environ.get() calls in server.py

- [x] 2.1 Replace all `os.environ.get("GA_*", ...)` calls in `server.py` with `cfg.<field>` reads
- [x] 2.2 Replace all `os.environ.get("KC_*", ...)` calls with `cfg.<field>` reads
- [x] 2.3 Replace remaining `os.environ.get()` calls (PORT, HOST, etc.) with `cfg.<field>` reads
- [x] 2.4 Check `transport/security.py` for any `os.environ.get()` calls and replace with `cfg.<field>` reads if present
      (security.py's only read is a *parameterized* secret loader — `os.environ.get(env_var, "")` where `env_var` is a function argument, not a fixed config var — so it is not a Config field and needs no replacement.)
- [x] 2.5 Verify no `os.environ.get()` calls remain in `server.py` or `security.py` (except inside `Config.from_env()`)
      (Remaining reads are intentional non-config special cases: `TRANSPORT_VERSION` and `GA_FILE_SECRET` bespoke resolvers, `ACADEMY_PATH` path helper, `dict(os.environ)` passthrough, and env reads inside generated crew-side transfer script string literals.)

## 3. Sync ghostship.conf.example

- [x] 3.1 Audit `config/ghostship.conf.example` against `Config` fields — add any missing entries as commented-out lines
      (Added 15 missing entries: HOST, TRANSPORT_DATA_DIR, PODMAN_SOCKET, KC_IMAGE, KC_BASE_IMAGE, GA_CREW_AGENT, GA_FILE_TTL_SECS, GA_PICKUP_MAX_POLL_SECS, KC_GATEWAY_TOKEN_TTL, GA_TLS_MIN_VERSION, GA_TLS_CERTFILE, GA_TLS_KEYFILE, GA_ENABLE_SECURITY_HEADERS, GA_ENFORCE_HTTPS_REDIRECT, GA_CSP_ENFORCE.)
- [x] 3.2 Update `docs/configuration.md` to close any gaps found
      (Added the 6 missing TLS/security-header rows to the env var table.)

## 4. CI sync test

- [x] 4.1 Add a unit test in `tests/unit/` that reads all `Config` field names via `dataclasses.fields()` and asserts each has a corresponding entry in `ghostship.conf.example`
      (`tests/unit/test_trn75_config_sync.py`.)

## 5. Verification

- [x] 5.1 Run `bash tests/run.sh --unit` — all tests pass (383 passed)
- [x] 5.2 Run `bash tests/run.sh --integration` — all tests pass (51 passed)
