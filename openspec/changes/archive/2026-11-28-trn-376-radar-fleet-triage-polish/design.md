# Design

## Context

Radar App, fleet badges and summary, responsive CSS, and the task and mail read lifecycles. The existing read endpoints suffice.

## Goals / Non-Goals

Keep crew names, health and primary actions easy to identify while inspecting a crew.

The fleet remains the only top-level destination. Crew navigation follows the current results inside the inspector. Transport endpoints are outside scope.

## Decisions

- Use neutral stopped badges and explicit Captain wording. Keep the existing attention criteria and text warnings.
- Adapt columns to fleet pane width and retain secondary fields in details. Use a compact mobile summary and plain data typography alongside the serif headings.
- Label the header counts Active and Asleep. Show the running count against the limit under Active when the limit is available. Derive the numerator from the same running rows as the fleet list.
- Keep search, status filters, sort and layout controls above the results. List uses one column header and Active, Asleep and Other row groups. Keep the column header available on scroll in the desktop results pane. When space is tight, move the active count and available last-task time into the crew summary as their columns disappear. Use the same explicit sort menu above both layouts. The group heading conveys Active or Asleep and rows show extra status only for warnings, Captain state or an Other status. A confirmed stop is required for the Asleep label. Give dashboard and copy controls consistent positions and independent hit targets. Place the inspector actions next to the view switch, and put task refresh beside the task heading. Use named Lucide icons for list and cards, clear search, and ordinary dashboard and refresh actions. Keep a visible wake label when opening the dashboard also starts a crew. A stopped crew with an assigned URL gets a wake and open action. This still opens the existing portal link in a new tab. An unassigned dashboard is labeled in Overview.
- Keep the fleet alongside a wider crew inspector on desktop and use a dedicated crew view on narrower screens. Put crew identity and quick actions in the inspector header, and put tasks, Captain details, credentials and metadata in Overview. Messages is the default when entering from the fleet. Preserve the view while switching crews, and keep the crew hash, filters and selection in sync. The crew navigator follows the filtered, sorted results, and is omitted for a crew outside those results. In the narrow inspector, pin the short crew navigation row when viewport height permits. A return-to-heading action scrolls to the crew title and moves focus there. On phones, use the available height for the selected crew and show fleet totals again on return to the fleet. Fleet connection errors remain visible.
- Use manual refresh for mailbox history and running task snapshots. Keep the previous success visible on failure, label that it may be outdated, and use the last successful read time. Stopped task details continue to use the fleet payload and its freshness.

## Risks / Trade-offs

Multiple snapshots can have different ages. Keep freshness next to the section it describes. Use the pane width to drive list density, since the same viewport has different available widths with the inspector open.
