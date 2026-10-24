## Context

See proposal.md for motivation. All changes are doc-only: no code, no API, no
tests. The codebase is on commit `eb9a8be` (version 0.8.1 by CHANGELOG) but
`VERSION` still reads `0.8.0`. Several docs carry `ghostship.conf` references
that were superseded in TRN-253 (0.8.0). The 0.6.0 release notes' Known
Limitations section has two items resolved in 0.8.1 but not annotated.

Relevant source of truth for each fix:
- `bin/start.sh` uses `config/ghostship.yaml` and
  `${XDG_CONFIG_HOME:-$HOME/.config}/ghost-academy/ghostship.yaml` — confirms
  architecture.md's `ghostship.conf` config-discovery list is stale.
- `CHANGELOG.md` `## v0.8.1` section is the authoritative content for the new
  release-notes page.
- `docs/release-notes-0.6.0.md` lines 122-125 and 208-210 mark Captain autopilot
  as unsupported on Claude crews — resolved in 0.8.1 per CHANGELOG.
- `docs/portal.md` Setup section uses `ghostship.conf` in its code block — stale.
- `docs/configuration.md` `KC_BASE_IMAGE` description says `0.9.0-insider.4` — the
  current stable base is `0.9.0` (architecture.md and CHANGELOG confirm the bump).

## Goals / Non-Goals

**Goals:**
- Bring `VERSION` to `0.8.1`.
- Remove all stale `ghostship.conf` references in architecture.md and portal.md.
- Annotate resolved Known Limitations in the 0.6.0 release notes.
- Add a `docs/release-notes-0.8.1.md` page that mirrors the 0.6.0 format.
- Update the `KC_BASE_IMAGE` description to drop the `0.9.0-insider.4` qualifier.
- Clarify the README model-access note's kiro-backend scope.

**Non-Goals:**
- No code changes to any `.py`, `.sh`, `.json`, or `.js` file.
- No changes to the OpenSpec specs (skip_specs: true).
- No new tests.
- Not re-documenting the full 0.8.0 or 0.7.x changelogs — those are already in
  CHANGELOG.md; the release-notes-0.8.1.md page is a reader-facing summary, not
  a full history.

## Decisions

**D1 — `release-notes-0.8.1.md` structure mirrors `release-notes-0.6.0.md`.**
The 0.6.0 page uses: Overview → Breaking Changes → Feature sections → Fixes →
Known Limitations. 0.8.1 is a hotfix + two feature additions with no breaking
changes. Use: Overview → New (ghostship-spawn, academy backend delivery) →
Fixes → Resolved Limitations (from 0.6.0). This makes the page useful as a
quick upgrade summary without duplicating the full CHANGELOG detail.

**D2 — Annotate, don't delete, the 0.6.0 Known Limitations entries.**
The 0.6.0 release notes are a historical document. Rather than deleting the
limitation entries (which would alter the historical record), prepend a
`> **Resolved in v0.8.1:** ...` callout to each affected entry. This preserves
the original limitation note and signals its resolution in context.

**D3 — Remove `GA_CREW_ANTHROPIC_API_KEY` references in 0.6.0 release notes.**
Lines 59 and 82 of `docs/release-notes-0.6.0.md` give instructions using
`GA_CREW_ANTHROPIC_API_KEY`, which was removed in TRN-233 (0.8.0). A plain note
saying "credential management moved to `ghostship auth login`" is sufficient;
the 0.8.0 CHANGELOG has full detail. Don't rewrite the 0.6.0 instructions—
add a short callout above the affected code blocks.

**D4 — architecture.md config-discovery order: update paths and example command.**
`start.sh` currently resolves:
1. `config/ghostship.yaml` (repo-local)
2. macOS: `~/Library/Application Support/ghost-academy/ghostship.yaml`
   Linux: `${XDG_CONFIG_HOME:-$HOME/.config}/ghost-academy/ghostship.yaml`

The doc lists three `.conf` paths that no longer exist in the code. Replace with
the two actual paths. The `--config` example command stays but changes extension
to `.yaml`. No change to the surrounding prose.

**D5 — `KC_BASE_IMAGE` table row: drop insider qualifier, keep digest placeholder.**
The description currently says the default is "the pinned `0.9.0` digest" with the
literal `0.9.0-insider.4` tag inline. The stable tag is now `0.9.0`. Remove the
`insider.4` qualifier and update the description to reference the stable `0.9.0`
tag, keeping the `sha256:...` digest notation as an example to show the pattern.

## Risks / Trade-offs

- **Stale 0.6.0 release notes risk** → The callout-annotation approach (D2) means
  readers of the 0.6.0 page see the resolution note, but the history is preserved.
  Low risk; no information is lost.
- **VERSION bump without a code release** → Bumping `VERSION` to `0.8.1` while
  commits dated post-0.8.1 already exist (model default change) is technically
  slightly ahead of where the project tagged. Accepted: CHANGELOG already lists
  `## v0.8.1` as the current version, and the version bump doc task is explicitly
  in scope.
