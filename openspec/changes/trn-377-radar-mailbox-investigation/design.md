# Design

## Context

Radar MailHistory currently receives retained subjects, sender addresses, receiving mailbox names and optional timestamps from the mail history route.

## Goals / Non-Goals

Make it easy to find a retained message and identify who sent or received it.

Message bodies, attachments and server-side search are outside implementation scope.

## Decisions

- Keep the subject prominent and show recognizable local personas with the exact sender address available through an accessible disclosure. Preserve distinct full addresses in sender grouping.
- Place undated deliveries after dated ones in the chronological view. Make the unknown-date section clear without inventing timestamps.
- Match case-insensitive text against subject, full and displayed sender, and recipient before grouping. Preserve the retained-history limit notice and distinguish no results from an empty mailbox. Keep query state local to the selected crew.

## Risks / Trade-offs

Search covers only the retained snapshot. Message previews may require a separate authorized read and decisions about content limits and rendering. Document feasibility before proposing that expansion.
