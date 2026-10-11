# Design — TRN-205: `POST /logout` aborts a pending login flow

## D1 — Lock ordering

`_abort_pending_login` acquires `_login_pending_lock`. The logout handler must NOT
hold any other lock when calling it. Current logout handlers hold no locks before
the credential delete — safe.

## D2 — Best-effort nuke

`_nuke_login_container` is already best-effort (logs but doesn't raise). The abort
helper follows the same pattern — a failed container stop is logged, `_login_pending`
is still set to `None`. The goal is to unblock the operator; a leaked container is
recoverable, a stuck pending state is not.

## D3 — Claude PTY socket

`_claude_login_pending` may hold an open `pty_sock`. Close it before nuking the
container — same cleanup as the timeout path in `_poll_claude_login_container`.

## D4 — Response field

`"aborted_pending_login": true` is informational. Callers that don't check for it
get the same 200 they always did. No breaking change.

## D5 — Codex pending state

`_codex_login_pending` has no PTY socket (Codex login uses a different flow). The
abort is just: nuke container + set None. Simpler than kiro/claude.
