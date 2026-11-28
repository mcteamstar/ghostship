## Why

Radar helps an operator answer three questions: what is running, what needs attention, and what should I open next? The React migration shipped the underlying behavior. The current table puts the same visual weight on most fields, hides the only sort control inside a clipped header on phones, and inserts all detail sections into the fleet list. That makes it harder to scan or compare crews.

## What Changes

- Remove the one-item Fleet sidebar. Use Ghostship Radar as the page title in a full-width header with Ghost Academy fleet totals and freshness, and place search, status filters and sorting above the results.
- Offer List and Cards views of the same fleet. Retain crew stats, warnings and available dashboard and copy actions in both views.
- Open one crew at a time in a dedicated inspector alongside the fleet on wide screens and in a full-width detail view on phones.
- Preserve the crew dashboard link, copy ID, task history, Captain information, Refresh auth and mailbox access. Derive attention cues from the existing fleet payload and stale Captain rule.
- Combine the crew overview and mailbox history in one inspector. Keep the crew identity, status, actions and overview at the top, with messages in the body and grouping by time, sender or receiving mailbox.

- Keep the last successful refresh visible during outages and label stale fleet data in text. Load mailbox history when the operator selects a crew.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/radar-ui`: Fleet triage controls, responsive crew inspection, and selection and focus behavior.

## Impact

Radar React components, CSS, UI tests and operator documentation. Extend Radar and transport with an authenticated mailbox history read. Keep the existing subjects endpoint compatible. Mail bodies, attachments, sending mail, Academy browsing, a gateway directory and multiple fleet instances are outside scope.
