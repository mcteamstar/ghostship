# Proposal

## Why

Ghostship v0.9.1 shipped three fixes that are not yet reflected in the user-facing
docs: the dotted model-ID correction (`claude-haiku-5.5` not `claude-haiku-5-5`), the
`steer()` follow-up fallback for claude/codex backends, and the stale port-range
figure in `docs/portal.md`. Users hitting the `profileArn is required` error have no
troubleshooting entry to guide them; operators reading `portal.md` see the wrong
firewall range; and the README still links only to the v0.8.1 release notes.

## What Changes

- **`docs/portal.md`** — correct stale port-range `64058–65081` (implied 1024 ports) to
  `64058–64121` (64 ports, matching `GA_DASHBOARD_PORT_RANGE_SIZE=64`).
- **`docs/architecture.md` (`steer()` section)** — document v0.9.1 `follow_up` fallback:
  when a backend returns `steer_unsupported`, transport retries with `mode=follow_up`;
  a `503 session_starting` now returns a retry hint rather than suggesting `force=True`.
- **`docs/troubleshooting.md`** — add a `profileArn is required for this request` section
  covering both causes: stale kiro credential _and_ wrong model-ID spelling
  (`claude-haiku-5-5` vs `claude-haiku-5.5`). The CHANGELOG already covers the fix; this
  surfaces it to operators in the right troubleshooting context.
- **`README.md`** — add links to the v0.9.0 and v0.9.1 release note sections (CHANGELOG
  anchors); the existing v0.8.1 release-notes link remains.

## Capabilities

### New Capabilities

_(none — pure documentation change, no spec-level behavior introduced)_

### Modified Capabilities

_(none — existing behaviors are unchanged; only documentation describing them is
updated)_

## Impact

- No code changes; docs only.
- No API, dependency, or spec changes.
- Files touched: `docs/portal.md`, `docs/architecture.md`, `docs/troubleshooting.md`,
  `README.md`.
