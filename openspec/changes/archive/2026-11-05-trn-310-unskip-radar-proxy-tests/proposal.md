# Proposal

## Why

Two test classes in `tests/unit/test_radar_server.py` — `TestRadarApiCrewsSuccess` (line 161) and
`TestRadarApiCrewsTransportDown` (line 194) — are permanently skipped with a stale skip
comment ("pending test infra fix"). The incompatibility they cited (httpx/httpx2 mock mismatch)
is already solved: `TestRadarApiCrewAgents` in the same file uses `_make_fake_httpx()`, a
minimal fake-module helper that sidesteps the incompatibility entirely. The skipped classes just
need to be rewritten to use that pattern.

## What Changes

- Remove `@unittest.skip(...)` decorators from both classes.
- Rewrite the httpx mocking in both classes to use `_make_fake_httpx()` (move the helper to
  a module-level function or mixin, or duplicate it per class following the existing pattern).
- All existing test assertions remain unchanged — only the mocking plumbing changes.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

_(none — no production code changes; no spec-level behavior changes.)_

## Impact

- `tests/unit/test_radar_server.py` — two classes unskipped, httpx mocking rewritten
