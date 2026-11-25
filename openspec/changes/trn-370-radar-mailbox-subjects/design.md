# Design

## Context

Radar currently proxies fleet and per-crew agent data from Transport, and loads per-crew details only when a row expands. Browser requests pass through Caddy's existing Portal session gate; Radar authenticates to Transport with `X-Transport-Token`.

The crew mail reader supports all eight mailboxes and reads stopped containers through Podman's archive API. Its existing best-effort helper returns subject and date values and can convert read failures into empty lists, so the Radar endpoint needs a stricter result boundary.

## Goals / Non-Goals

**Goals:**
- Add a lazy, per-crew subject view for all eight mailboxes.
- Keep the browser response to mailbox names and subject strings, with a distinct unavailable state.
- Read both running and stopped crews without changing mailbox contents or starting a stopped crew.

**Non-Goals:**
- Display message bodies, senders, dates, counts, attachments, or message actions.
- Add mailbox reads to the fleet polling response or alter `pickup` behavior.

## Decisions

### Use the existing Radar-to-Transport boundary

Add `GET /api/crews/{crew_id}/mail-subjects` in Radar and proxy it to a transport-secret-protected `GET /internal/crews/{crew_id}/mail-subjects`. This follows the per-crew agents route, keeps Podman access in Transport, and leaves browser access behind Caddy's existing session gate. Calling Transport directly from the browser would bypass Radar's ownership of browser-facing fleet APIs.

### Return only mailbox labels and subject strings

Return `{"mailboxes": {"ghost": ["..."], ...}}` for the established eight mailbox names. Strip dates and every other message field before returning data. This makes the data boundary explicit; returning the existing helper objects unchanged would leak timestamps the user did not request.

### Reuse parsing, but preserve read failures

Reuse the existing message-header parsing and Maildir/mbox support. For a running crew, read through the container exec path; for a stopped crew, use the Podman archive path without starting it. Extend archive parsing for legacy mbox files as well as the current Maildir format so stopped older crews retain subject visibility. The endpoint must distinguish an empty or absent mailbox from an unavailable mailbox source. Do not use the current best-effort skim result unchanged because it collapses read errors into empty lists.

### Load and render subjects only in expanded details

Fetch subjects when the operator expands a crew row, alongside the existing on-demand details, rather than on every five-second fleet poll. Render each subject through Radar's HTML escaping helper. Show a clear empty state for mailboxes with no subject entries and an unavailable state when the request fails.

## Risks / Trade-offs

- Subjects can contain sensitive text or markup → Keep the existing Portal session gate and transport-token boundary, return no message bodies, and HTML-escape subjects before rendering.
- Reading stopped containers adds archive calls → Do it only on expansion, not during fleet polling; if the archive source is unavailable, show unavailable rather than a false empty state.
- Mailbox contents can change after expansion → Treat the display as a snapshot and refresh it when the detail is reopened; do not mark messages as read.

## Migration Plan

No mailbox data migration is needed. Ship the Transport route and Radar proxy/UI together. Rollback removes the new endpoint and detail section; mailbox contents remain untouched throughout.
