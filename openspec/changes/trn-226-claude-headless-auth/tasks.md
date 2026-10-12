# Tasks — TRN-226: Claude headless auth via `claude setup-token`

## 1. Verify `claude setup-token` output (spike)

- [x] 1.1 Start a `ga-claude-login-*` container and run `claude setup-token` inside it
- [x] 1.2 Record exactly which file(s) are written under `~/.claude/` and their format
- [x] 1.3 Confirm whether `_archive_has_claude_credential` (checks `.credentials.json`)
      covers the setup-token output, or whether a second check is needed
- [x] 1.4 Confirm the command is non-interactive (no TTY required), or note if PTY is needed
- [x] 1.5 Record the command's exit code on success and on failure

## 2. `lifecycle.py` — `_initiate_claude_setup_token`

- [x] 2.1 Add `_initiate_claude_setup_token(podman)` function mirroring the structure
      of `_initiate_claude_login` but using `container_exec` instead of PTY
- [x] 2.2 Start container via `_start_claude_login_container`
- [x] 2.3 Verify `claude` binary present (reuse `which claude` guard)
- [x] 2.4 Run `claude setup-token` via `container_exec` with 60s timeout
- [x] 2.5 Verify credential file present via `_poll_claude_login_container` or equivalent
- [x] 2.6 Write `ga-claude-auth` via `_write_claude_auth_file`
- [x] 2.7 Nuke login container via `_nuke_claude_login_container`
- [x] 2.8 Return `{"status": "complete"}` on success, `{"error": ...}` on any failure

## 3. `server.py` — route handler + registration

- [x] 3.1 Add `_handle_claude_setup_token_post(request)` handler
- [x] 3.2 409 if `_claude_auth_exists()` (already authenticated)
- [x] 3.3 409 if `_claude_login_pending is not None` (OAuth flow in progress)
- [x] 3.4 Call `_initiate_claude_setup_token`, surface error as 500
- [x] 3.5 Register `("POST", "/login/claude/setup-token")` in the route table alongside
      the existing claude login routes (~line 4636)

## 4. `auth.py` — public route exemption

- [x] 4.1 Add `/login/claude/setup-token` to the public route list in
      `BearerAuthMiddleware._dispatch_public_route` so it doesn't require
      an existing `ga-claude-auth` to be authenticated

## 5. Tests

- [x] 5.1 `_initiate_claude_setup_token` — success path: mock container_exec returning
      credential bytes, assert `_write_claude_auth_file` called with correct data
- [x] 5.2 `_initiate_claude_setup_token` — no `claude` binary: assert error returned,
      container nuked
- [x] 5.3 `_initiate_claude_setup_token` — exec timeout: assert error, container nuked
- [x] 5.4 `_handle_claude_setup_token_post` — already authenticated: assert 409
- [x] 5.5 `_handle_claude_setup_token_post` — OAuth pending: assert 409
- [x] 5.6 `_handle_claude_setup_token_post` — success: assert 200, `{"status": "complete"}`
- [x] 5.7 Route registration: assert `POST /login/claude/setup-token` is in the public
      route exemption list

## 6. Docs

- [x] 6.1 Update `docs/auth.md`: add `## Claude headless auth (recommended)` section
      documenting `POST /login/claude/setup-token`
- [x] 6.2 Retitle existing section to `## Claude OAuth login (interactive)`
- [x] 6.3 Scope the token-expiry known-limitation note to the OAuth path only
- [x] 6.4 Update `docs/configuration.md` if any new config is introduced (not expected)
