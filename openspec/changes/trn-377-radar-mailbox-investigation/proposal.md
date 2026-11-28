# Proposal

## Why

Task-qualified sender addresses dominate mailbox rows and messages with missing dates are hard to scan. Operators cannot narrow the retained history to a subject or participant.

## What Changes

- Clarify sender and timestamp presentation.
- Put the history in the default crew view with a separate scroll area in the desktop inspector.
- Search the selected crew’s retained message metadata and narrow the results to a receiving mailbox independently of grouping.
- Assess whether message previews merit a follow-up.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/radar-ui`

## Impact

Radar MailHistory currently receives retained subjects, sender addresses, receiving mailbox names and optional timestamps from the mail history route.
