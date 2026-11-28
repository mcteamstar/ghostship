# Design

## Context

Radar App, fleet badges and summary, responsive CSS, and the task and mail read lifecycles. The existing read endpoints suffice.

## Goals / Non-Goals

Keep crew names, health and primary actions easy to identify while inspecting a crew.

The fleet remains the only top-level destination. Crew navigation follows the current results inside the inspector. Transport endpoints are outside scope.

## Decisions

- Use neutral stopped badges and explicit Captain wording. Keep the existing attention criteria and text warnings.
- Adapt columns to fleet pane width and retain secondary fields in details. Use a compact mobile summary and plain data typography alongside the serif headings.
- Keep search, status filters, sort and layout controls above the results. List uses one column header and Running and Inactive row groups. Keep the column header available on scroll in the desktop results pane. When space is tight, move the active count into the crew summary and keep sort reachable above the list. Give dashboard and copy controls consistent positions and independent hit targets.
- Keep the fleet alongside a wider crew inspector on desktop and use a dedicated crew view on narrower screens. Put crew identity and quick actions in the inspector header, and put tasks, Captain details, credentials and metadata in Overview. Messages is the default when entering from the fleet. Preserve the view while switching crews, and keep the crew hash, filters and selection in sync. The crew navigator follows the filtered, sorted results, and is omitted for a crew outside those results.
- Use manual refresh for mailbox history and running task snapshots. Keep the previous success visible on failure, label that it may be outdated, and use the last successful read time. Stopped task details continue to use the fleet payload and its freshness.

## Risks / Trade-offs

Multiple snapshots can have different ages. Keep freshness next to the section it describes. Use the pane width to drive list density, since the same viewport has different available widths with the inspector open.
