# Proposal

## Why

An all-stopped fleet looks like a fault, the list gets cramped when inspecting a crew, and the fleet refresh clock gives no indication of task or mailbox snapshot age.

## What Changes

- Distinguish routine stops from warnings.
- Organize fleet controls above a single grouped table with aligned row actions. Preserve the card layout.
- Make the crew inspector a workspace with shared crew actions, separate Messages and Overview views, and previous and next controls that follow the visible fleet order.
- Improve fleet density at narrow and split pane widths. Keep available last-task times in compact rows and keep crew navigation accessible during a long read on narrow screens.
- Show independent freshness and refresh controls for task and mailbox snapshots.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/radar-ui`

## Impact

Radar App, fleet badges and summary, responsive CSS, and the task and mail read lifecycles. The existing read endpoints suffice.
