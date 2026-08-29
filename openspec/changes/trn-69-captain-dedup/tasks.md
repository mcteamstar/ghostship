# TRN-69 Tasks — Captain Escalation Deduplication

## Section 1: Transport changes

- [ ] 1.1 **Update `_RAVEN_SELF_CANCEL`** — extend with the report-and-pause clause as specified in D1. The new text must make explicit that for monitoring orders, the standing order is satisfied the moment the completion report is sent, and Raven should pause immediately.

- [ ] 1.2 **Update `_CAPTAIN_CHECKIN_TASK`** — add the deduplication paragraph as specified in D2. Insert after the standing-orders reading section, before the action list.

## Section 2: Tests

- [ ] 2.1 Add a test asserting `_RAVEN_SELF_CANCEL` contains the phrase "completion report" (regression guard for the new clause).

- [ ] 2.2 Add a test asserting `_CAPTAIN_CHECKIN_TASK` contains the deduplication instruction (substring: "prior message" or "/var/mail/admiral").

## Section 3: Docs

- [ ] 3.1 Update `docs/architecture.md` — add a note under the Captain section explaining the report-and-pause pattern for monitoring orders and the dedup check.

## Section 4: Integration verification

- [ ] 4.1 Deploy to vm23. Launch a crew, set a monitoring captain order (watch a one-shot Banshee), let it complete, and count admiral mails after 3 cron cycles. Expected: 1 mail (or at most 2 if the race fires before pause completes). Before this change: 19–24.
