# Design

## Context

See proposal.md. The cross-check found four personal machine-path examples in tracked archived OpenSpec notes. Local Git internals are untracked and are not part of the repository content being cleaned.

## Goals / Non-Goals

**Goals:**
- Remove host-specific personal paths from identified archived documents.
- Preserve generic technical meaning and historical details.

**Non-Goals:**
- Rewrite commit history or alter Git author metadata.
- Remove generic paths such as container-home examples.

## Decisions

- Edit only tracked archive locations already identified by the review; search for adjacent copies before finalizing.
- Replace personal paths with portable placeholders or generic descriptions, not another personal machine path.
- Keep the public-history identity question as a review note only.

## Risks / Trade-offs

- [Scrubbing paths removes needed reproduction context] → Preserve each path's technical role using a generic placeholder.
- [Broad scan flags generic examples] → Review matches in context and limit edits to confirmed host-specific values.
