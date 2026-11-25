# Proposal

## Why

Radar shows crew status and active work, but operators cannot see mailbox handoffs there. Showing mailbox subjects gives fleet-level situational awareness without exposing message bodies.

## What Changes

- Add an on-demand, per-crew Radar API and expanded-detail view for the eight established mailboxes.
- Return and render subject strings only, grouped by mailbox; support running and stopped crews without marking messages as read.
- Preserve the existing Portal session and Transport secret boundaries, with clear empty and unavailable states.
- Add regression coverage and document the Radar mailbox view.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/radar`: Radar exposes authenticated, per-crew mailbox subjects through its browser API and detail view.

## Impact

`transport/server.py` internal crew routes and auth allowlist; `radar/server.py`; Radar detail rendering; existing crew mailbox subject readers; Radar documentation; transport and Radar tests. No new dependency or mailbox write behavior is required.
