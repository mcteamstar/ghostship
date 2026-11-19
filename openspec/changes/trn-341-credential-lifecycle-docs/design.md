# Design

## Context

See proposal.md. OAuth refresh may propagate updated credentials into running crews, while static values are fixed at launch for a running crew and picked up on a later restart.

## Goals / Non-Goals

**Goals:**
- State the different lifecycle behavior in plain operator language.
- Keep CLI recovery advice consistent with launch gating and credential propagation.

**Non-Goals:**
- Change credential storage, injection, logout, or crew restart behavior.

## Decisions

- Use transport/login.py propagation behavior and launcher credential injection behavior as the source for doc edits.
- Distinguish OAuth from static credential methods rather than making one blanket statement for all backends.
- Keep OpenSpec behavior requirements unchanged; this is documentation-only.

## Risks / Trade-offs

- [A statement incorrectly generalizes across methods or backends] → Check each sentence against backend-specific login and injection paths.
