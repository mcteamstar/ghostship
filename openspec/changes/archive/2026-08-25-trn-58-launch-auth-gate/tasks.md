## 1. Extract `_initiate_login` helper

- [x] 1.1 In `transport/server.py`, extract the core login-start logic from `_handle_login_post` into a new sync function `_initiate_login(podman: PodmanClient) -> dict`. The function should:
  - Acquire `_login_pending_lock`, check the already-pending guard, set the sentinel, release the lock — same TOCTOU-safe sequence as `_handle_login_post`
  - Start the login container via `_start_login_container(podman)`
  - Run the PTY exec, answer prompts, extract `login_url` and `code`
  - Start the background drain thread
  - Return `{"login_url": login_url, "code": login_code}` on success, or `{"login_pending": True}` if a flow was already running, or raise on hard error
- [x] 1.2 Refactor `_handle_login_post` to call `_initiate_login(podman)` and wrap the result into the existing `JSONResponse` — no behaviour change for direct `POST /login` callers.

## 2. Move auth check in `launch`

- [x] 2.1 In `launch()`, move the `_read_auth_file()` check to immediately after `_get_podman()` succeeds, before the `with _registry_lock:` block.
- [x] 2.2 When auth is absent, call `_initiate_login(podman)` and return the enriched error response:
  ```python
  # flow started:
  {"error": "not_authenticated", "login_url": ..., "code": ...,
   "instructions": "Open login_url to authenticate, then call launch again."}
  # flow already pending:
  {"error": "not_authenticated", "login_pending": True,
   "instructions": "Login already in progress. Poll GET /login, then call launch again."}
  ```
- [x] 2.3 Remove the old auth check that was inside the registry lock block.

## 3. Tests

- [x] 3.1 Add a unit test: `launch` with no auth file returns `error: not_authenticated` and `login_url` is present (mock `_initiate_login` to return a fake URL).
- [x] 3.2 Add a unit test: `launch` with no auth file and a pending flow returns `error: not_authenticated` and `login_pending: true`.
- [x] 3.3 Add a unit test: after the auth check move, `launch` with no auth does NOT write a registry entry (registry is unchanged after the call).
- [x] 3.4 Verify existing `launch` happy-path tests still pass — no regression on authenticated callers.

## 4. Verification

- [x] 4.1 Run `bash tests/run.sh --unit` — all tests pass.
- [x] 4.2 Update the `launch` tool docstring to reflect the new behaviour (no longer says "call POST /login first").
