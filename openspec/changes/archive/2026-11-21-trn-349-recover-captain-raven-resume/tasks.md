## 1. Recover the Captain check-in

- [x] 1.1 Detect an explicit Raven restore failure in a terminal task outcome and in an immediate continuation error where supported. Preserve existing busy, missing-session and unrelated failure behavior.
- [x] 1.2 Retire the matching task ID and start one fresh Raven through normal schedule, admission and task ID persistence. Cover changed or disabled schedules, deferred admission, and uncertain spawn acceptance.
- [x] 1.3 Give replacement Raven the standing order and require it to reconcile durable progress, mailbox intents and existing task IDs before dispatching additional work.

## 2. Verify recovery

- [x] 2.1 Add focused tests for failure classification, schedule state, replacement dispatch, and preservation of existing 400/404 and 409 handling.
- [x] 2.2 Add an integration or Corsair smoke check where continuation returns an ID, that task later fails to restore, one replacement check-in progresses, and an already accepted worker task is not dispatched twice.
