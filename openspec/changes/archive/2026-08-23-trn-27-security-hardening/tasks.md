## 1. GA_API_KEY → Podman Secret (install.sh)

- [x] 1.1 Add `podman secret rm ga-api-key 2>/dev/null || true` + `podman secret create ga-api-key` from the persisted key file in install.sh
- [x] 1.2 Replace `-e "GA_API_KEY=${GA_API_KEY:-}"` with `--secret ga-api-key` on the transport container invocation (conditional on key being configured)
- [x] 1.3 Remove the env-var line from the container invocation entirely

## 2. Transport reads secret from filesystem

- [x] 2.1 In `transport/server.py`, replace `os.environ.get("GA_API_KEY")` with a read of `/run/secrets/ga-api-key` (file-not-found → fallback to env var with deprecation warning)
- [x] 2.2 Log deprecation warning at startup when falling back to env var
- [x] 2.3 Log info when neither source provides a key (auth disabled)

## 3. Login TOCTOU: early sentinel in _handle_login_post

- [x] 3.1 Move `_login_pending = {...}` assignment inside the existing `with _login_pending_lock:` block that performs the guard checks (immediately after both guards pass, before lock release)
- [x] 3.2 Use a lightweight sentinel value (`{"container": None, "started_at": ..., "state": "starting"}`) for the initial write
- [x] 3.3 After `_start_login_container` succeeds, re-acquire lock and update sentinel with real container name and `"state": "started"`
- [x] 3.4 If `_start_login_container` raises, re-acquire lock, clear `_login_pending = None`, then return 500
- [x] 3.5 Remove the second `with _login_pending_lock:` block that previously set `_login_pending` (~line 2025)

## 4. Login GET: guarded clear in _handle_login_get

- [x] 4.1 Before `_login_pending = None` (line 2085), compare `_login_pending["container"]` with `pending["container"]` (the container just completed)
- [x] 4.2 Only clear if they match; otherwise leave `_login_pending` untouched

## 5. Tests

- [x] 5.1 Unit test: concurrent `POST /login` — two threads call simultaneously; assert exactly one gets 200 and the other gets 409
- [x] 5.2 Unit test: `GET /login` clear guard — mock `_login_pending` with a different container name than the one completing; assert `_login_pending` is NOT cleared
- [x] 5.3 Unit test: transport reads `/run/secrets/ga-api-key` when file exists
- [x] 5.4 Unit test: transport falls back to env var with deprecation warning when file absent
- [x] 5.5 Integration test: `install.sh` creates Podman secret and `podman inspect ga-transport` does not show GA_API_KEY in Env

## 6. Documentation

- [x] 6.1 Update `docs/auth.md` to document secrets-based API key (how it's stored, how to rotate)
- [x] 6.2 Update `docs/configuration.md` to note the env-var is deprecated
