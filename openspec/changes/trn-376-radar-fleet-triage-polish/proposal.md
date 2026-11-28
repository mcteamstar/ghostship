# Proposal

## Why

An all-stopped fleet looks like a fault, the list gets cramped when inspecting a crew, and the fleet refresh clock gives no indication of task or mailbox snapshot age.

## What Changes

- Distinguish routine stops from warnings.
- Improve fleet density and data typography at narrow and split pane widths.
- Show independent freshness and refresh controls for task and mailbox snapshots.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/radar-ui`

## Impact

Radar App, fleet badges and summary, responsive CSS, and the task and mail read lifecycles. The existing read endpoints suffice.
