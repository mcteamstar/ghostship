## 1. SDD Template Update

- [x] 1.1 Add layered dispatch-coordination instructions to `academy/orders/sdd.md`: before dispatching any persona, Raven must (a) scan `raven@localhost` for pending or confirmed dispatch-intents for the target persona, (b) cross-check `kirocrew spawn list` by the stable task-description marker, (c) check the `agent` field as tertiary confirmation; all three must be clear
- [x] 1.2 Add the two-phase dispatch-intent protocol to the SDD template: Raven writes `dispatching <persona> <intent_id>` with a locally generated `intent-<uuid>` token BEFORE `/api/spawn`, then records the gateway-returned ID as `dispatching <persona> <spawn_task_id>` after a successful call
- [x] 1.3 Add stale-intent resolution instruction to the SDD template: a confirmed intent is stale when its task is completed or absent; a pending intent is stale only after a full subsequent check finds no matching task marker or worker

## 2. STANDING_ORDERS Cross-Reference

- [x] 2.1 Add a brief cross-reference in `academy/steering/STANDING_ORDERS.md` noting the dispatch-coordination pattern exists in the SDD template and applies to all SDD transitions (Ghost, Banshee, Reaper dispatch)

## 3. Verification

- [x] 3.1 Manually verify the updated SDD template text is coherent: layered-check instructions appear in the correct location within the dispatch decision logic, and the tokenized pre-spawn intent, assigned-ID confirmation, election, and stale detection are unambiguous
- [x] 3.2 Verify that the STANDING_ORDERS cross-reference does not duplicate the full pattern (pointer only, not a restatement)

## 4. Review Correction

- [x] 4.1 Reconcile the protocol with the gateway contract, which assigns the real spawn task ID only inside `POST /api/spawn`; do not require Raven to invent that ID before the call
- [x] 4.2 Add a stable task-description marker and deterministic post-write pending-intent election so the mailbox and description signals remain actionable across async or overlapping check-ins
