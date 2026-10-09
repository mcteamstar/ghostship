# Proposal

Source: independent review of `release/0.6.0` at `ee0b3b8` (2026-10-09), run on the Claude backend. Reviewers: **S** security, **Q** quality, **T** test coverage, **D** docs. "Reproduced" means the reviewer or a live check ran code to confirm it; everything else is from reading the code and needs confirming during assessment. Target: a release after 0.6.0.

Full reviewer reports: crew `ghostship-indy-060` tasks `169e9101b28e91e4` (security), `d615d73e3b7c9e37` (quality), `408dea89af5f6789` (test coverage), `45df3b672a262c4c` (docs) — retrieve with `pickup(task_id, crew_id)` while the crew exists. Line numbers refer to `ee0b3b8` and may drift. Next step for whoever picks this up: work through **Assess first**, then write specs, design and tasks with `openspec instructions <artifact> --change <name>`.

## Why

The login flows share a PTY helper and per-backend state that lose output, never expire, and can report success that didn't happen. Codex ships for the first time in 0.6.0, and its login internals are the least tested.

## Findings

| Severity | Finding | Where | Who | Status |
|---|---|---|---|---|
| High | PTY bytes received in the same chunk as the 101 upgrade headers are discarded, so the login URL is lost intermittently (kiro, Claude, Codex). No socket timeout. | `podman.py:371-396` | T, Q | Reproduced with a fake socket |
| High | Kiro and Codex logins never expire: an abandoned flow keeps its container and returns 409 until restart. Claude's expiry only runs when someone polls (seen live: a container ran two hours). | `lifecycle.py:2375`, `:2896`; `server.py:1553`, `:1971` | Q, T, live | Reproduced (Claude poll-only); read (kiro, Codex) |
| Medium | Codex device-code regex matches prose: "The code will expire…" yields `will`. | `lifecycle.py:3004` | T | Reproduced |
| Low | `sendall` on the Claude PTY under `_claude_login_pending_lock` on a blocking socket; a failed prompt answer is swallowed and reported as a URL timeout. | `lifecycle.py:2664`, `:2281` | Q | Read only |
| Related | Claude OAuth refresh-token rotation leaves `ga-claude-auth` stale after the first crew refresh. Tracked separately; design owned by the Admiral. | `lifecycle.py` `_inject_claude_auth` | live | Strong evidence, not proven |

## Assess first

- Run one real Codex login end to end; capture its PTY output as a fixture for the code-pattern fix.
- Measure how often the PTY drop happens on a real Podman before choosing the fix.

## What Changes

- PTY attach keeps bytes after the header delimiter and sets a socket timeout.
- One periodic sweep expires pending logins for all three backends, independent of polling.
- Tighten the Codex code pattern.

## Capabilities

### New Capabilities

- None expected.

### Modified Capabilities

- `codex-auth`: abandoned flows expire.
- `crew-login`: kiro flows expire.
- `claude-auth`: expiry runs without a poll.

## Impact

`transport/lifecycle.py`, `transport/podman.py`, `transport/server.py`. Socketpair tests for the PTY helper; Codex tests that don't patch the poll.
