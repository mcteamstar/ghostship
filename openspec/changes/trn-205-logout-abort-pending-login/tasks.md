# Tasks — TRN-205: `POST /logout` aborts a pending login flow

## 1. `lifecycle.py` — abort helpers

- [ ] 1.1 Add `_abort_pending_login()` — acquires `_login_pending_lock`, nukes
      `_login_pending["container"]` if set (best-effort), sets `_login_pending = None`
- [ ] 1.2 Add `_abort_claude_pending_login()` — closes `pty_sock` if present, nukes
      container, sets `_claude_login_pending = None`
- [ ] 1.3 Add `_abort_codex_pending_login()` — nukes container, sets
      `_codex_login_pending = None`

## 2. `server.py` — logout handler updates

- [ ] 2.1 In `_handle_logout_post`: call `_abort_pending_login()` after credential
      delete; add `"aborted_pending_login": True` to response if it returned True
- [ ] 2.2 In `_handle_claude_logout_post`: call `_abort_claude_pending_login()` after
      credential delete; add field to response if aborted
- [ ] 2.3 In `_handle_codex_logout_post`: call `_abort_codex_pending_login()` after
      credential delete; add field to response if aborted

## 3. Tests

- [ ] 3.1 `_abort_pending_login` with active container — assert nuke called, state None
- [ ] 3.2 `_abort_pending_login` with no pending state — assert no-op, no error
- [ ] 3.3 `_handle_logout_post` with pending login — assert `aborted_pending_login: true`
      in response, state cleared
- [ ] 3.4 `_handle_logout_post` without pending login — assert existing response shape
      unchanged, no new field
- [ ] 3.5 Same two cases for claude and codex logout handlers

## 4. Verification

- [ ] 4.1 Start a login flow, call `POST /logout`, confirm `GET /login` returns 404
      (not authenticated, not pending)
- [ ] 4.2 Confirm a fresh `POST /login` succeeds immediately after the abort
