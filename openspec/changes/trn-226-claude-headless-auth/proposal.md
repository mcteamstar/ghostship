# TRN-226 — Claude headless auth via `claude setup-token`

**Plane ticket:** TRN-226
**Change:** `trn-226-claude-headless-auth`

## Problem

The current Claude auth path (`POST /login/claude`) stores an OAuth refresh token in
`ga-claude-auth`. Refresh tokens are scoped to the login container that obtained them and
cannot be refreshed from inside a crew container — the container runs as a different
process context and the OAuth client state doesn't transfer. The result: the first crew
to hit the ~8h expiry refreshes inside its own volume, invalidating all other running
crews simultaneously.

This is documented as a known limitation in the 0.6.0 release notes and is a real
operator pain point for anyone running multiple Claude-backend crews.

## Solution

Claude Code ships `claude setup-token` — a command that issues a **long-lived headless
token** (a personal access token or equivalent) designed specifically for non-interactive
server deployments. Unlike the OAuth refresh token, this token:

- Does not expire on a short TTL
- Does not require a container-local refresh cycle
- Can be copied to multiple crew containers without invalidating

Add `POST /login/claude/setup-token` as a new auth route that runs `claude setup-token`
inside the existing login container, captures the resulting credential, and stores it
as `ga-claude-auth` — exactly where `_inject_claude_auth` already expects it.

The existing OAuth flow (`POST /login/claude` + `POST /login/claude/code`) is kept
unchanged for users who prefer it or don't have a Pro/Max subscription that supports
`setup-token`.

## What changes

### New route: `POST /login/claude/setup-token`

Runs `claude setup-token` via PTY exec inside a `ga-claude-login-*` container
(same container image as the OAuth flow). The command is non-interactive — it prints
a token directly to stdout. Capture, wrap in the same `~/.claude/` tar format as the
OAuth completion path, and write to `ga-claude-auth` via `_write_claude_auth_file`.

No URL extraction, no browser redirect, no code submission step. The operator calls
`POST /login/claude/setup-token` and gets back `{"status": "complete"}` when done,
or an error.

### `lifecycle.py`
- `_initiate_claude_setup_token(podman)` — starts the login container, execs
  `claude setup-token`, reads output via `container_exec` (not PTY — no interaction
  needed), extracts the token, tars `~/.claude/`, calls `_write_claude_auth_file`.
- Reuses `_start_claude_login_container`, `_nuke_claude_login_container`,
  `_write_claude_auth_file`, `_archive_has_claude_credential` from the OAuth path.

### `server.py`
- `_handle_claude_setup_token_post` — `POST /login/claude/setup-token`
  - Returns 409 if already authenticated (same guard as `POST /login/claude`)
  - Returns 409 if an OAuth flow is already in progress
  - Calls `_initiate_claude_setup_token`, returns `{"status": "complete"}` on success
  - Route registered alongside the existing claude login routes

### `docs/auth.md`
- New section documenting `POST /login/claude/setup-token` as the **recommended
  path for headless/server deployments**
- OAuth flow remains documented as the alternative for interactive use
- Known limitation about token expiry removed (or scoped to OAuth-only path)

## Non-goals

- Replacing the OAuth flow — it stays, setup-token is additive
- Automatic token rotation or expiry detection
- Supporting `claude setup-token` for Codex or other backends

## Affected files

| File | Change |
|:-----|:-------|
| `transport/lifecycle.py` | `_initiate_claude_setup_token()` — new function |
| `transport/server.py` | `_handle_claude_setup_token_post()` + route registration |
| `transport/auth.py` | Public route exemption for `/login/claude/setup-token` |
| `docs/auth.md` | Document the new route as recommended headless path |
| `tests/unit/test_trn226_claude_setup_token.py` | Unit tests |
