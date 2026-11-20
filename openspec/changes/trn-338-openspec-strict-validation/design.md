# Design

## Context

The 2026-11-20 baseline in proposal.md covers 87 items (29 passed, 58 failed) and 178 warnings: 168 overlong requirements, 2 placeholder Purpose sections, 5 missing SHALL/MUST wording findings, and 3 unsupported `ticket` metadata keys. Strict mode reports warning-bearing items as failed; there are no error-level findings. Findings are spread across main specs and active changes, so cleanup needs a stable baseline and reviewable batches.

## Goals / Non-Goals

**Goals:**
- Make strict validation reproducible and actionable.
- Preserve requirement intent while addressing length, placeholder, and RFC wording findings.
- Preserve Plane traceability using metadata accepted by OpenSpec v2.

**Non-Goals:**
- Rewrite archived history or alter runtime code.
- Suppress findings without documenting an explicit exception.

## Decisions

- Capture the command, date, counts, and categorized findings before editing.
- Use OpenSpec v2-recognized extension metadata for Plane identifiers after aligning repository workflow guidance.
- Shorten overlong requirements by separating distinct behaviors only where semantics can be preserved; compare each against its current main spec before syncing.
- Handle placeholder sections and RFC wording as separate cleanup categories.

## Risks / Trade-offs

- [Shortening text changes a requirement's meaning] → Preserve scenarios and review altered requirements against prior wording.
- [New metadata convention diverges from agent guidance] → Update tracked workflow guidance and verify a new change is recognized by strict validation.
- [Large warning count obscures regressions] → Record category counts and run strict validation after each batch.
