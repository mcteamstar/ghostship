# Design

## Context

Radar App, fleet badges and summary, responsive CSS, and the task and mail read lifecycles. The existing read endpoints suffice.

## Goals / Non-Goals

Keep crew names, health and primary actions easy to identify while inspecting a crew.

Navigation and transport endpoints are outside scope.

## Decisions

- Use neutral stopped badges and explicit Captain wording. Keep the existing attention criteria and text warnings.
- Adapt columns to fleet pane width and retain secondary fields in details. Use a compact mobile summary and plain data typography alongside the serif headings.
- Use manual refresh for mailbox history and running task snapshots. Keep the previous success visible on failure, label that it may be outdated, and use the last successful read time. Stopped task details continue to use the fleet payload and its freshness.

## Risks / Trade-offs

Multiple snapshots can have different ages. Keep freshness next to the section it describes. Use the pane width to drive list density, since the same viewport has different available widths with the inspector open.
