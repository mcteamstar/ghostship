## 1. Fleet triage

- [x] 1.1 Remove the one-item sidebar and use a full-width Ghostship Radar header with Ghost Academy fleet totals, freshness and the fleet toolbar. Reuse existing Captain and gateway rules and cover stopped, degraded and zero-match states.
- [x] 1.2 Build the List / Cards switch, dense table and responsive crew cards with shared filtering, sorting, selection and actions. Preserve all crew data and give creation time and uptime distinct labels.

## 2. Crew inspector

- [x] 2.1 Replace inline detail with the responsive inspector. Put the crew overview in the panel header and message history in the body. Reuse task, Captain and credential components and expose dashboard and copy actions.
- [x] 2.2 Implement single selection, hash history, list scroll and focus restoration. Cover filters hiding a selection, crew removal and viewport changes.
- [x] 2.3 Keep requests scoped to the selected crew and keep in-flight credential refresh state keyed by crew across selection changes. Preserve existing polling and error behavior.

- [x] 2.4 Add the authenticated, crew-scoped history read in transport and Radar. Cover stopped crews, denied access, missing or malformed headers, repeated deliveries, limits and exclusion of bodies and attachments. Keep the subjects endpoint compatible.
- [x] 2.5 Build the date timeline and sender and recipient groupings. Cover stable ordering, unknown metadata, wrapped subjects, empty, unavailable and capped results.

## 3. Verification and documentation

- [x] 3.1 Update frontend regression tests for the full-width header, unified inspector and history loading on crew selection. Preserve coverage for triage, history grouping, deep links, request races, focus restoration and refresh failures, then run the full frontend suite.
- [x] 3.2 Recheck stopped, mixed and degraded fixtures at 360, 768 and 1440 CSS pixels in both themes. Check keyboard navigation, contrast, long IDs and subjects, independent scrolling and absence of horizontal page overflow. Record screenshots and findings. Check focus and scroll restoration with the unified inspector and verify history in its body.
- [x] 3.3 Verify the built Radar UI through the local portal against Corsair and document the fleet and inspector workflows.

## 4. Review follow-up

- [x] 4.1 Keep freshness visible when polling fails. Test first-load failure, recovery, explicit stale and critically stale labels at the existing thresholds, and screen reader announcements.
- [x] 4.2 Load mailbox history when a crew is selected and retain its snapshot and grouping while that crew stays open. Add retry and cancel pending reads when switching crews.
- [x] 4.3 Verify populated history in Observer using representative delivery data. Check chronological, Sender and Recipient groupings, long subject wrapping, unknown metadata and failure recovery. Record the fixture or live source and distinguish it from the existing empty stopped-crew smoke check.
- [x] 4.4 Review the unified inspector in the local preview at desktop and phone widths, with empty and populated history. Correct the inspector section heading hierarchy.
- [x] 4.5 Use Lucide icons for clear actions and states. Make card information keyboard-operable as one selection control while keeping dashboard and copy actions separate. Announce clipboard failure accurately.

### Verification notes

- The current layout uses a full-width Ghostship Radar header, with no one-item sidebar. A selected crew inspector shows the overview above Messages. History loads when the crew is selected.
- Observer reviewed the Corsair-backed local Vite preview at 1440 pixels with an empty history and at 390 pixels with populated history for `trn-252-indy` (23 deliveries). The layout had no horizontal page overflow in those views. Section headings were reduced to their intended hierarchy.
- A mixed fixture with 26 crews, a degraded running crew, a paused captain, a long crew ID and 32 retained messages was reviewed at 360, 768 and 1440 pixels in light and dark themes. The page had no horizontal overflow. Long IDs and subjects wrapped, Enter opened the card, focus returned after closing the inspector, and the fleet and message history scrolled independently. Mail history and recipient grouping appeared in the inspector.
- Running, stopped, paused, stale-captain and gateway-warning text contrast measured above 6.7:1 in both themes. Screenshots are in `/tmp/radar-trn372-360-light.png`, `/tmp/radar-trn372-768-light.png`, `/tmp/radar-trn372-1440-light.png` and `/tmp/radar-trn372-1440-dark.png`.
- After this UI revision the frontend suite passed (210 tests); `npm run typecheck` and `npm run build` also passed with Node 24.22.1.
