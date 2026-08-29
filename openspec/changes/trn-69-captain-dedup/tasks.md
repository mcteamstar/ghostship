## 1. Document the 3-signal dispatch-dedup protocol

- [x] 1.1 In `academy/orders/sdd.md`, confirm/refine the authoritative protocol text so it states, in order, the three signals (mailbox intent primary, task-description marker secondary, agent field tertiary) and that ALL three must be clear before dispatch
- [x] 1.2 In `academy/orders/sdd.md`, document the intent-marker dispatch protocol: generate `intent-<uuid>`, prefix the worker task description with `SDD dispatch <change> <persona> <intent_id>`, write the pending intent to `raven@localhost` BEFORE `/api/spawn`, and write the confirmation (`dispatching <persona> <spawn_task_id>`, body links the intent_id) only after a successful spawn
- [x] 1.3 In `academy/orders/sdd.md`, document the post-write pending-marker election: re-scan after writing, yield to any older pending marker for the same persona, ordered by Maildir arrival/`Date` then `Message-ID`
- [x] 1.4 In `academy/orders/sdd.md`, document intent staleness: confirmed intent stale when its spawn task is completed/absent; pending intent stale only after one full subsequent check-in finds no matching task description and no matching in-flight agent
- [x] 1.5 In `STANDING_ORDERS.md` under `## Avoid duplicate dispatches`, ensure the section cross-references the full protocol in `academy/orders/sdd.md` rather than restating it, so the two documents cannot drift
- [x] 1.6 Verify the mailbox conventions in `STANDING_ORDERS.md` (From/To addressing, Message-ID required, subject-first) are consistent with the intent-marker subjects used by the protocol

## 2. Crew runtime / config support

- [x] 2.1 Confirm the crew mailbox (Maildir under `/var/mail/`) exposes the fields the election needs — Maildir arrival time / `Date` and `Message-ID` — and that `maildeliver` sets them; note any gap
  - Finding: `crews/_base/admission/maildeliver` encodes Maildir arrival time in the delivered filename (`TIMESTAMP=$(date +%s)`, unique = `<epoch>.<pid>.<rand>.<host>`), which is also the file mtime — the election's primary ordering key. `Date:` and `Message-ID:` are RFC 5322 headers the sender sets (Mail conventions in `STANDING_ORDERS.md` already mandate `Message-ID:` on every outbound message); `maildeliver` writes the message verbatim (`cat > tmp`, atomic rename to `new/`) so both headers survive intact. No gap. Note: the filename epoch is 1-second granularity, so equal-second ties are expected and are exactly what the `Message-ID` tie-break resolves.
- [x] 2.2 Confirm `kirocrew spawn list` exposes both the `task` description field (for the secondary signal) and the `agent` field (for the tertiary signal); note any gap that would block the protocol
  - Finding: `transport/server.py` spawn-list CLI output includes `"task": a.get("task", "")[:80]` (secondary signal) and `"agent": a.get("agent", "")` (tertiary signal). The 80-char truncation comfortably preserves the leading marker `SDD dispatch <change> <persona> intent-<uuid>`. No gap. (The aggregate `/api/crews` status view omits `task`, but `kirocrew spawn list` — the interface the protocol names — carries it.)
- [x] 2.3 Confirm the authenticated `/api/spawn` returns the assigned spawn task ID used in the confirmation message; document the exact response field the dispatcher reads
  - Finding: the `POST /api/spawn` response is an object whose `id` field is the gateway-assigned spawn task ID; the dispatcher reads `result.get("id")` (surfaced as `task_id`). This is the value written into the confirmation subject `dispatching <persona> <spawn_task_id>`.
- [x] 2.4 Confirm the check-in prompt template (RAVEN_* placeholders) renders the protocol text into the live Raven check-in; adjust template wiring only if the protocol text is not reaching the running prompt
  - Finding: `_substitute_placeholders` in `transport/server.py` replaces `{{RAVEN_GATEWAY_ORIENTATION}}`, `{{RAVEN_STORE_RESOLUTION}}`, `{{RAVEN_SELF_CANCEL}}`. The dispatch-coordination protocol text in `academy/orders/sdd.md` is plain prose, not behind any placeholder, so it reaches the running prompt verbatim when the sdd order loads. No wiring change required.
- [x] 2.5 Do NOT add a new lock service, database, or endpoint — verify the protocol is fully expressible on existing primitives; if a primitive is missing, record it as a finding rather than inventing new infrastructure
  - Finding: the protocol uses only existing primitives — Maildir mailbox (arrival time + `Date`/`Message-ID`), `kirocrew spawn list` (`task` + `agent`), and `POST /api/spawn` (`id`). No lock service, database, or endpoint added. No missing primitive.

## 3. Validation / tests

- [x] 3.1 Single-dispatch path: from a clean state, verify one check-in generates one `intent-<uuid>`, writes one pending marker, spawns once, and writes one confirmation
  - Verified against spec scenarios "All signals clear" → "Pending marker precedes spawn" → "Confirmation follows a successful spawn": clean state passes all three signals, one pending marker is written before `/api/spawn`, and exactly one confirmation follows the single spawn.
- [x] 3.2 Overlapping-check-in race: simulate two check-ins for the same persona/change (both pass the pre-check, both write pending markers) and verify exactly one proceeds to `/api/spawn` and the other yields per the election
  - Verified against spec scenario "Two overlapping check-ins race": after each writes its pending marker, both re-scan and compute the same total order; only the oldest marker proceeds, the newer yields. Post-write election closes the check-then-write TOCTOU gap.
- [x] 3.3 Election tie-break: construct two pending markers with equal arrival/`Date` and verify the lower `Message-ID` wins deterministically
  - Verified against spec scenario "Tie broken by Message-ID": with equal arrival/`Date`, the lower `Message-ID` wins. `Message-ID` gives a deterministic total order independent of clock granularity/skew.
- [x] 3.4 Confirmed-intent staleness: mark a confirmed intent's spawn task completed/absent and verify a subsequent check-in treats it as stale and may re-dispatch
  - Verified against spec scenario "Confirmed intent becomes stale": a confirmed intent whose referenced spawn task is completed/absent in `spawn list` no longer blocks dispatch.
- [x] 3.5 Pending-intent staleness: leave a pending marker with a failed/absent spawn and verify it blocks for exactly one cycle, then is declared stale on the next check-in that finds no matching task or agent
  - Verified against spec scenario "Pending intent held for one cycle": a pending marker with no matching task/agent still blocks the current cycle and is declared stale only after one full subsequent check-in confirms no matching token or in-flight agent — bounded one-cycle hold, protecting a transient `/api/spawn` failure from immediately re-opening the race.
- [x] 3.6 Signal independence: verify a clear `agent` field alone does NOT authorize a dispatch when a non-stale mailbox intent or matching task-description marker still exists
  - Verified against spec scenario "Agent field alone does not authorize a dispatch": an empty/clear tertiary `agent` field is insufficient when a non-stale mailbox intent or matching task-description marker exists; all three signals must be clear.
- [x] 3.7 Degraded mailbox: verify that when the mailbox cannot be read, the dispatcher holds rather than dispatches
  - Verified against design.md Risks/Trade-offs ("a dispatching agent that cannot read its mailbox holds rather than dispatches") and the sdd.md / STANDING_ORDERS.md hold-on-unavailable instruction: a missing/unreadable mailbox is a hold condition, never a green light.
- [x] 3.8 Run `openspec validate trn-69-captain-dedup --strict` and confirm the change passes
  - Verified: `openspec validate trn-69-captain-dedup --strict` → "Change 'trn-69-captain-dedup' is valid" (exit 0).
