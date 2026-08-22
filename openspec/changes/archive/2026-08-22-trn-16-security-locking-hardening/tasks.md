## 1. Fix `_inject_auth` exit-code check (unblocks crew launches)

- [x] 1.1 In `transport/server.py`, replace `podman.container_exec(container, ["python3", "-c", inject])` with `podman.container_exec_checked(...)` in `_inject_auth`
- [x] 1.2 Remove the `"injected" in result` string check and `return "injected" in result` — replace with `return True` after the checked call
- [x] 1.3 Update the log line to `logger.info("Auth injected for %s", container)` (no result string to log)
- [x] 1.4 Run `python3 -m unittest discover -s transport -p "test_*.py" -q` — all 18 tests pass

## 2. Fix `POST /login` concurrent guard

- [x] 2.1 In `_handle_login_post`, move the `_read_auth_file()` check inside the `with _login_pending_lock:` block so both guards are evaluated atomically
- [x] 2.2 Run tests — all pass

## 3. Narrow `_reconcile_registry` lock hold time

- [x] 3.1 In `_reconcile_registry`, snapshot the registry under the lock, then release the lock before the per-crew restart loop
- [x] 3.2 Re-acquire the lock per crew to write back updated cookie/status after each restart completes
- [x] 3.3 Run tests — all pass

## 4. Deploy and verify

- [x] 4.1 Commit: `fix(trn-16): auth injection exit-code check, login TOCTOU, reconcile lock narrowing`
- [x] 4.2 Push and deploy: `./deploy.sh academy`
- [x] 4.3 Call `launch("trn-16-verify")` — confirm no `"Failed to mint session cookie"` error
- [x] 4.4 Nuke the verify crew
