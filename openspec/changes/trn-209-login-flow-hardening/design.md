# Design

See `proposal.md` for motivation and the full finding inventory.

## Context

Three login flows share infrastructure in `transport/`:

- **kiro** (`_initiate_login` → `_run_pty_login_flow`) — device-flow via kiro-cli.
- **Claude** (`_initiate_claude_login` → `_run_pty_login_flow`) — device-flow via claude CLI.
- **Codex** (`_initiate_codex_login` → `_run_pty_login_flow`) — device-flow via codex-acp CLI.

All three call `PodmanClient.container_exec_pty_stdin`, which returns `(exec_id, sock)`.
The returned socket is a raw Unix socket that has already been upgraded from HTTP to a
plain TCP tunnel; any PTY bytes Podman sent in the same read-chunk as the 101 headers are
in `response_buf` after `\r\n\r\n` and are currently discarded. The `_run_pty_login_flow`
helper starts with an empty `collected` bytearray, so those bytes are never seen.

Expiry:
- **kiro**: `_login_pending` has a `started_at` timestamp but no expiry is ever evaluated.
  The pending state and container persist until the next poll completes or the gateway
  restarts. `_login_pending` is cleared only on poll-completion or on error paths inside
  `_initiate_login` itself.
- **Codex**: same structure as kiro — `_codex_login_pending` has `started_at` but no
  expiry check; the poll handler in `server.py` returns `{status: pending}` forever.
- **Claude**: `_claude_login_code_expired` exists but is only invoked inside the
  `POST /login/claude/code` and poll handlers. A flow with no poller runs until restart.

Codex code pattern:
```
re.compile(r"(?:[?&]user_code=|[Cc]ode[:\\s]+)([A-Za-z0-9_-]{4,})")
```
The `[Cc]ode[:\\s]+` branch matches any 4+-character word after "Code:" or "code:" —
including prose like "The code will expire…" → captures `will`.

## Goals / Non-Goals

**Goals:**
- Return leftover PTY bytes from `container_exec_pty_stdin` so `_run_pty_login_flow` seeds
  its accumulator from them.
- Add a socket timeout to `container_exec_pty_stdin` so a hung Podman socket does not
  block a login thread indefinitely.
- Expire kiro and Codex pending-login state on a periodic sweep (not poll-dependent).
- Align Claude's expiry so it also runs on the sweep, independent of polling.
- Tighten the Codex device-code regex to avoid matching prose words.

**Non-Goals:**
- Claude OAuth refresh-token rotation / `ga-claude-auth` staleness (tracked separately).
- Changes to login container provisioning, networking, or the Podman image.
- UI changes to the login flow.
- New endpoints or new state fields visible to callers beyond what is needed for expiry.

## Decisions

### D1 — Return leftover bytes from `container_exec_pty_stdin`

**Decision:** Change the return type from `tuple[str, socket.socket]` to
`tuple[str, socket.socket, bytes]`, where the third element is any bytes already read
past the `\r\n\r\n` header boundary.

**Rationale:** The fix is at the source — the bytes are in `response_buf` right there.
Alternatives:
- *Fix in `_run_pty_login_flow`*: would require an optional `initial_bytes` parameter
  and changes at every call-site; equivalent work for less clarity at the source.
- *Retry on URL timeout*: masks, doesn't fix; makes the window smaller at best.

**Consequences:** Three call-sites in `lifecycle.py` must be updated to unpack three
values and pass `initial_bytes` into `_run_pty_login_flow`. `_run_pty_login_flow` gains
an `initial_bytes: bytes = b""` parameter.

### D2 — Socket timeout on the raw exec socket

**Decision:** Call `sock.settimeout(PTY_SOCKET_TIMEOUT_SECS)` (default 120 s) on the
raw socket before returning it from `container_exec_pty_stdin`. The timeout applies to
the initial header-read loop and to all subsequent reads by the caller.

**Rationale:** Without a timeout, a connection that Podman accepts but never writes to
blocks a lifecycle thread permanently. 120 s is well above the 45 s `_run_pty_login_flow`
deadline, giving the select-loop its full budget while still bounding total exposure.

**Alternatives:**
- *Timeout only on header read, then set non-blocking*: callers already call
  `setblocking(False)` immediately after receiving the socket, so the timeout set here
  only affects the header-read phase. That is acceptable and simpler.

### D3 — Periodic expiry sweep for all three backends

**Decision:** Add a single `_sweep_expired_logins(podman)` function that checks all
three pending-login dicts and expires any that have exceeded their TTL. Wire it into the
existing periodic maintenance path (the startup sweep already in `lifecycle.py` around
line 1581, or a new lightweight timer).

**Expiry TTLs:**
| Backend | Proposed TTL | Rationale |
|---------|-------------|-----------|
| kiro    | 900 s       | Matches `CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS` — same device-flow window. |
| Codex   | 900 s       | Same; spec permits code-less flows, so a generous window is fine. |
| Claude  | Re-use existing `CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS` / `CLAUDE_LOGIN_CODE_DEADLINE_SECS` | Consistent with existing logic. |

The sweep runs the existing expiry test for Claude (`_claude_login_code_expired`) and
equivalent `started_at`-based tests for kiro and Codex.

**Alternatives:**
- *Expire inside each poll handler*: already done for Claude; kiro and Codex need it too.
  A sweep is better because it fires without polling, matching the proposal's requirement.
- *Per-flow timer thread*: more complex, same effect.

**Implementation note:** The sweep must acquire each backend's lock before inspecting
and clearing the pending dict. It must also nuke the orphaned container before clearing
state (same as the poll-completion path) to avoid leaked containers.

### D4 — Tighten the Codex device-code regex

**Decision:** Replace:
```python
re.compile(r"(?:[?&]user_code=|[Cc]ode[:\\s]+)([A-Za-z0-9_-]{4,})")
```
with:
```python
re.compile(r"(?:[?&]user_code=([A-Za-z0-9_-]{4,})|[Cc]ode[:\s]+([A-Z0-9]{4,8})\b)")
```

Rationale:
- URL-param branch: require the code immediately after `=` (no gap) — already safe but
  made explicit with an inline capture group.
- Prose branch: restrict to all-uppercase-or-digit tokens of 4–8 chars with a word
  boundary. Device codes from OpenAI/Codex are uppercase hex; prose words like `will`,
  `expire`, `The` are lowercase and do not match.
- `group(1)` callers must be updated to use `group(1) or group(2)` (or the pattern
  restructured to keep a single capture group).

**Alternative:** require the prose branch to be at least 6 chars. Rejected: `will`
(4 chars) is the reproduced failure mode; restricting to uppercase is more principled.

## Risks / Trade-offs

**[Risk] Changing `container_exec_pty_stdin` return arity breaks callers.**
→ Mitigation: there are exactly three call-sites, all in `lifecycle.py`. Update all three
in the same commit. The type annotation change makes a missed call-site a type-check
failure.

**[Risk] Sweep running concurrently with poll handler creates a TOCTOU window.**
→ Mitigation: both paths acquire the same per-backend lock before reading/clearing the
pending dict. Standard lock discipline already used throughout the file; no new pattern
required.

**[Risk] Regex tightening rejects a real Codex device code that is lowercase.**
→ Mitigation: The URL-param branch (`user_code=...`) is unchanged and case-insensitive;
only the prose fallback branch is tightened. If codex-acp ever prints a lowercase code
in prose (not in a URL), this is a real risk. The "Assess first" item in the proposal
(run a real Codex login) should verify code format before this lands.

**[Risk] 120 s socket timeout conflicts with `setblocking(False)` callers.**
→ Mitigation: all three callers call `pty_sock.setblocking(False)` immediately after
`container_exec_pty_stdin` returns. `setblocking(False)` overrides the timeout for
subsequent reads; the 120 s timeout therefore only guards the header-read phase in
`container_exec_pty_stdin` itself, which is the intended scope.

## Migration Plan

1. Apply all changes in a single PR against `release/0.6.0` or its successor.
2. The changes are gateway-internal; no database migration, no config file change, no
   API surface change visible to external callers.
3. Rollback: revert the PR. No persistent state is affected.

## Open Questions

- What code format does a real codex-acp device flow actually produce? (uppercase hex,
  alphanumeric mixed-case, numeric-only?) The regex fix in D4 assumes uppercase; the
  proposal's "Assess first" item should confirm before this lands.
