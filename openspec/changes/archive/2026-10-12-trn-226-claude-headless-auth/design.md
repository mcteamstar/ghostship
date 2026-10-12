# Design — TRN-226: Claude headless auth via `claude setup-token`

## D1 — What does `claude setup-token` actually produce?

**Verify before implementing.** The exact output format of `claude setup-token` needs
to be confirmed against the version of the Claude CLI shipped in the spec-ops image.
Two plausible shapes:

1. Writes `~/.claude/.credentials.json` (same file as OAuth completion) — if so,
   `_archive_has_claude_credential` and `_inject_claude_auth` work unchanged.
2. Writes a different file (e.g. `~/.claude/setup-token.json`) — if so, the archive
   check and injection need a second path.

**Decision gate:** run `claude setup-token` inside a `ga-claude-login-*` container and
inspect the resulting filesystem before writing any handler code. This is task 1.1.

## D2 — PTY vs exec

`claude setup-token` is documented as non-interactive and outputs the token to stdout.
Use `container_exec` (not `container_exec_pty_stdin`) — simpler, no PTY drain thread,
no select loop. If it turns out `claude setup-token` requires a TTY, fall back to PTY.
Default: exec.

## D3 — Timeout

`claude setup-token` makes a network call to get a token. Use a 60s timeout on the
`container_exec` call — same order as the PTY login flows but simpler to implement
since we're waiting on exec completion, not a polling loop.

## D4 — Route naming

`POST /login/claude/setup-token` is a sub-path of the existing `/login/claude` tree.
Consistent with `/login/claude/code`. Auth middleware exempts it the same way as
`/login/claude` and `/login/claude/code` — i.e., it does NOT require a valid
`ga-claude-auth` to exist (that's the credential it's creating).

## D5 — Interaction with OAuth pending state

If `_claude_login_pending` is not None (OAuth flow in progress), setup-token returns
409. The two flows share the `ga-claude-auth` destination — running them simultaneously
would be a bug. The lock check is a single read under `_claude_login_pending_lock`
before any container work starts.

## D6 — Container reuse

Same `ga-claude-login-*` container image as the OAuth path (requires `claude` in
`GA_CREW_AGENT`). The guard that checks for the `claude` binary (`which claude`)
is reused. Same nuke-on-error pattern.

## Implementation sequence

1. Verify `claude setup-token` output format (D1) — spike in a throwaway container
2. Implement `_initiate_claude_setup_token` in `lifecycle.py`
3. Implement `_handle_claude_setup_token_post` in `server.py` + route registration
4. Add public route exemption in `auth.py`
5. Unit tests
6. Update `docs/auth.md`
