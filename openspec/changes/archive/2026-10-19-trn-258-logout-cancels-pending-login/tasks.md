# Tasks

## 1. Credential store and flow primitives

- [x] 1.1 Make `CredentialStore.delete` return `True` when it removed a file and `False` when none existed, and raise on `OSError` (design Decision 2). Update any other caller to handle the exception. Verify: unit tests for removed, absent and unlink-failure cases pass; `grep -rn '_cred_store.delete\|\.delete(' transport/` shows every caller handles it.
- [x] 1.2 In `LoginFlow.initiate`, after starting the container, check under the lock that `_pending` is still the dict this call created. If not, remove the container and return `{"error": "cancelled"}` (design Decision 3). Verify: a unit test aborts the flow while `start_container` is running (fake Podman that triggers `abort` from inside `container_create`/`start`) and asserts the container is removed and the result is `cancelled`; a second test starts a new flow in that window and asserts the new flow is left intact.
- [x] 1.3 Add `LoginFlow.commit_if_current(pending, store_fn)` and route the four completion paths through it: the kiro `GET` completion, the claude and codex `GET` completions, and the launch-time poll in `tools.py`. A non-current flow discards the result, removes the container, and returns `cancelled` (launch path: `not_authenticated`) (design Decision 4). Verify: unit tests where logout's abort runs between the poll and the commit show no credential stored and `GET /login/{backend}` reporting no pending flow.

- [x] 1.4 Filter the kiro completion's running-crew injection in `_handle_login_get` to crews where `info.get("acp_backend", "kiro") == "kiro"`, and inject only after `commit_if_current` succeeds (design Decision 6). Verify: a unit test with running kiro, claude and codex crews plus one entry with no `acp_backend` in the fake registry asserts `_inject_auth` is called for the kiro crew and the no-field entry only.
- [x] 1.5 Identity guard through the PTY URL read in `LoginFlow.initiate` (design Decision 3): a flow cancelled during the read returns `cancelled` with no URL, and its failure paths clear `_pending` only if it is still this call's dict. Verify: `TestLoginFlowInitiateCancelledDuringPTY` passes, and fails against the pre-fix `initiate` (a failed read cleared a newer flow's slot).

## 2. Logout routine

- [x] 2.1 Add `_logout(backend, request)` in `transport/login.py` per design Decision 1: abort first, then delete the store entry and legacy file, return 500 with a `failure` audit if a removal failed, `success` audit only if something was removed, then 200 `{"status": "logged_out"}` plus `aborted_pending_login` when it applies. Point the three `/logout/{backend}` routes at it. Verify: unit tests in `tests/unit/test_credentials_routes.py` cover, for each of kiro, claude and codex:
  - pending flow and nothing stored → 200 with `aborted_pending_login: true`, abort helper called;
  - nothing pending or stored → 200, no audit event;
  - store-only credential (kiro `api-key`, claude `setup-token`) → 200 and entry gone;
  - legacy device-flow credential → legacy file deleted;
  - store-delete failure → 500 with a `failure` audit.
- [x] 2.2 Running crews untouched: a unit test with running crews of each backend in the fake registry asserts logout makes no `container_exec`, restart or stop call. Verify: the test passes.
- [x] 2.3 Remove the legacy handlers (`_handle_logout_post`, `_handle_claude_logout_post`, `_handle_codex_logout_post`) and their crew-wipe code, drop them from both `server.py` import blocks, and delete `transport/container_scripts/wipe_auth.py`. Update the existing `TestLogoutCredentialStore` tests to the new routine. Verify: `grep -rn '_handle_logout_post\b\|_handle_claude_logout_post\b\|_handle_codex_logout_post\b\|wipe_auth' transport/ tests/` returns nothing, and the updated tests pass.
- [x] 2.4 A new login starts after cancelling: a unit test aborts a pending kiro flow via `POST /logout/kiro`, then calls `POST /login/kiro/builder-id` and gets a new flow, not 409. Verify: the test passes.
- [x] 2.5 Container runtime unavailable: `_logout` still removes the stored credential and legacy file when `_get_podman` raises, and returns 500 saying a pending login could not be cancelled (design Decision 1, steps 1 and 5). Verify: `test_podman_unavailable_still_removes_credential_and_reports_500` passes, and fails against the pre-fix `_logout`, which returned 500 before removing anything.
- [x] 2.6 Replace all ten 409 user-facing messages across kiro, claude, and codex login POST routes that referenced `POST /logout/...` with `ghostship auth logout <backend>` instructions. Verify: `grep -n "POST /logout" transport/login.py` returns only comments and docstrings, not user-facing response strings.

## 3. Docs

- [x] 3.1 Update `docs/auth.md`:
  - `ghostship auth logout <backend>` is how you both log out and abort a login.
  - It always ends with no stored credential and no pending login.
  - It's idempotent, returning 200 with `aborted_pending_login` when a flow was cancelled.
  - It does not touch running crews: relaunch or nuke them to drop their credential.

  Rewrite the kiro (~L118), claude (~L294) and codex (~L400) logout descriptions and the route docstrings to match. Verify: none of the three logout sections mentions wiping running crews or a 404/409 "not authenticated" response.
- [x] 3.2 Add CHANGELOG entries under Unreleased: "logout no longer touches running crews" marked BREAKING, and a Fixed entry "kiro login completion no longer injects auth into claude or codex crews". Verify: both entries are present.

## 4. Integration check

- [x] 4.1 Run the full unit suite. Verify: `pytest tests/unit/` exits 0.
- [x] 4.2 On the live install after `ghostship upgrade`:
  - `curl -X POST .../login/kiro/builder-id`, then `ghostship auth logout kiro`. Verify the logout succeeds, no `ga-login-*` container remains, and `GET /login/kiro` shows `pending_flow: null` and `configured: false`.
  - Run `ghostship auth logout kiro` again. Verify it succeeds.
  - With the `smoke-test` crew running, run `ghostship auth logout claude`. Verify `smoke-test` is still running and its gateway healthy (`crews()`).
