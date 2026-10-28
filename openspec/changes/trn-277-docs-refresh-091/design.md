# Design

## Context

See `proposal.md` — Why. All four doc files are in the current worktree and are the
only files in scope. Each fix is a targeted textual edit; no generated assets or build
steps are involved.

Key current-state facts relevant to the approach:

| File | Stale element | Current (wrong) | Correct |
|---|---|---|---|
| `docs/portal.md` line 47 | Port-range upper bound | `64058–65081` | `64058–64121` |
| `docs/architecture.md` `steer()` para | `follow_up` mode missing | No mention | Document `mode=follow_up` fallback + `session_starting` retry hint |
| `docs/troubleshooting.md` | No `profileArn` section | Absent | Add entry covering both causes |
| `README.md` | Release-notes links | Only v0.8.1 | Add v0.9.0 and v0.9.1 anchors |

The `steer()` prose lives in the Dispatch model section of `docs/architecture.md`
(around line 132). The existing paragraph accurately describes the `force=True` path
but predates the v0.9.1 `follow_up` fallback.

## Goals / Non-Goals

**Goals:**
- Correct the four stale doc elements identified in the proposal.
- Ensure the `steer()` section gives operators a correct mental model of when
  `mode=follow_up` is used and what `action: "follow_up_queued"` means.
- Provide operators a troubleshooting entry that covers the `profileArn` error
  in both its v0.9.1-diagnosed causes (stale credential and wrong model ID spelling).

**Non-Goals:**
- No new sections, restructures, or prose beyond what is needed to fix the four
  specific gaps.
- No changes to any other doc files or to code.
- No new release-notes file — v0.9.1 notes exist in `CHANGELOG.md`.

## Decisions

**D1: Edit `portal.md` line 47 in-place.**
The `64058–65081` range appears once (line 47) as the human-readable description of
the per-crew dashboard port block. The table at line 206 and the firewall example at
line 189 already say `64058–64121` / 64 ports. The fix is a single string replacement
on line 47.

**D2: Extend the existing `steer()` paragraph in `architecture.md`; no new section.**
A new subsection would imply `steer()` has changed significantly; the v0.9.1 change is
a backend-compatibility refinement. Two sentences appended to the existing paragraph
keep the context intact:
1. "For claude/codex backends that cannot interrupt mid-turn, `steer()` falls back to
   `mode=follow_up` when the gateway returns `steer_unsupported`; the response carries
   `action: "follow_up_queued"` and the continuation appears in `pickup(crew_id=...)`.
2. "A `503 session_starting` response means the task hasn't started a tool call yet —
   retry `steer()` rather than using `force=True`."

**D3: Add a dedicated `profileArn is required for this request` section to
`troubleshooting.md`.**
This error has two distinct causes (stale credential, wrong model ID) and is actionable
without reading the full CHANGELOG. Adding a new H2 section after the existing
`Bootstrap crash` section keeps the alphabetical/topical flow. The section lists both
causes with a one-step fix each.

**D4: Append v0.9.0 and v0.9.1 CHANGELOG anchors to the README resource list.**
The existing entry `[docs/release-notes-0.8.1.md](docs/release-notes-0.8.1.md)`
stays. Add two more entries pointing to `CHANGELOG.md#v090` and `CHANGELOG.md#v091`
anchors (GitHub auto-generates heading anchors from H2 text). These belong alongside
the existing release-notes link rather than in a separate section.

## Risks / Trade-offs

**[Risk] GitHub anchor for v0.9.1 section heading.**
GitHub derives anchors from H2 text by lowercasing and replacing spaces/dots with
hyphens. The CHANGELOG heading is `## v0.9.1` → anchor `#v091`. If the heading
changes, the link silently 404s inside the page. → _Mitigation_: use the anchor as-is
and note the pattern in the task; a future rename of the heading would also update the
README link.

**[Risk] Minimal prose for `steer()` extension may under-explain.**
Two sentences keep the section concise but may not cover edge cases (e.g. what happens
if `mode=follow_up` itself fails). → _Mitigation_: the CHANGELOG is the authoritative
source for the full behaviour; the architecture doc should be an accurate overview,
not a spec. Operators needing full detail will read the CHANGELOG.

## Migration Plan

No deployment steps. All changes are to `.md` files already in the repo. The worktree
branch is committed and opened for review via the normal Ghost → PR flow.

## Open Questions

None.
