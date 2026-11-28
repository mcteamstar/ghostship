# Design

## Context

Radar MailHistory currently receives retained subjects, sender addresses, receiving mailbox names and optional timestamps from the mail history route.

## Goals / Non-Goals

Make it easy to find a retained message and identify who sent or received it.

Message bodies, attachments and server-side search are outside implementation scope.

## Decisions

- Keep the subject prominent and show recognizable local personas with the exact sender address available through an accessible disclosure. Preserve distinct full addresses in sender grouping.
- Keep search, mailbox scope, grouping and snapshot refresh above the independently scrolling desktop history. Use clock and direction icons with short Time, From and To grouping labels. Keep the named refresh icon and its freshness beside the grouping controls. Lay out each entry with its subject first and participants and time as secondary details. Keep the current day or group heading visible while scrolling through that section. On smaller screens, let the controls wrap and history scroll with the page. Offer a jump selector when multiple nonempty groups match the current scope. Choose a destination and confirm it to scroll and focus the group heading. Show full sender addresses as jump destinations so same-persona addresses remain distinguishable.
- Place undated deliveries after dated ones in the chronological view. Make the unknown-date section clear without inventing timestamps.
- Match case-insensitive text against subject, full and displayed sender, and recipient before grouping. Combine text search with the receiving mailbox selector. Show the total or matching delivery count, and reset the desktop results scroll when the search, mailbox or grouping changes. Preserve the retained-history limit notice and distinguish no results from an empty mailbox. Keep query state local to the selected crew.

## Risks / Trade-offs

Search covers only the retained snapshot. Message previews may require a separate authorized read and decisions about content limits and rendering. Document feasibility before proposing that expansion.

## Preview feasibility

A bounded preview is feasible as a separate read through the existing Radar session and internal transport token boundary. The transport already resolves a crew and reads retained Maildir and mbox data from Podman without waking a stopped crew. The history route only projects headers. A preview route would need to identify one retained delivery within the requested crew and receiving mailbox. Use an opaque reference tied to the delivery and return unavailable if the message moves, changes, or falls outside the retained window. A row index can shift between reads and is unsuitable as a reference.

Keep eligibility within the existing limit of 50 recent deliveries per mailbox and preserve the 64 MiB archive ceiling. As initial follow-up limits, cap parsing at 256 KiB of message input and responses at 2 KiB of decoded plain text, with an explicit truncation indicator. Return preview unavailable for unsupported or oversized messages. Extract inline text/plain only, omit attachments and HTML, and render as text in Radar. Fetch on demand and avoid logging or caching preview content. Confirm that the current operator session is intended to grant access to message content before enabling the route.
