---
description: "Drive a named OpenSpec change through the standard Spectre → Ghost → Banshee → Reaper lifecycle."
---
Drive OpenSpec change '<change>' through the standard lifecycle.

On every check-in, assess this change's real OpenSpec artifact status and its tasks.md checkbox state as a whole. Read the current state from OpenSpec and tasks.md; do not rely on memory or an earlier check-in's conclusion.

{{RAVEN_GATEWAY_ORIENTATION}}

When new standing orders arrive while a previously-dispatched persona task is still in flight, steer it with the new context rather than waiting for it to finish.

{{RAVEN_STORE_RESOLUTION}}

Before dispatching any persona, apply this layered dispatch-coordination check to the target persona, in order:

1. **Mailbox signal (primary):** Scan `raven@localhost` for an unconfirmed dispatch-intent for the target persona. A pending intent (`dispatching <persona> <intent_id>`) or a confirmed intent (`dispatching <persona> <spawn_task_id>`) means that persona is already dispatched; hold rather than dispatch again unless that intent is stale.
2. **Task-description signal (secondary):** Cross-check the `task` field in `kirocrew spawn list` for an in-flight task whose description begins with `SDD dispatch <change> <persona>`. Match on change and persona; the `intent_id` portion is always truncated in spawn list output (the field is capped at 80 characters, and the full marker exceeds that for every real change ID), so do not require an exact intent token match here. Do not use the `agent` field for this check.
3. **Agent-field signal (tertiary):** Check the `agent` field in `kirocrew spawn list` as a final confirmation only; it is asynchronous and must not be the sole dispatch guard.

All three signals must be clear before a new dispatch proceeds. If any signal indicates an in-flight or recently dispatched task, hold and reassess on the next check-in. A confirmed intent is stale when `kirocrew spawn list` shows its referenced task as completed or absent. A pending intent is stale only after one full subsequent check-in finds no task description carrying its intent token and no matching in-flight agent; until then, it blocks a retry.

If the mailbox cannot be read (unavailable or access error), treat this as a hold condition — do not dispatch. A missing mailbox is never a green light; the check-in reassesses on the next cycle.

After all three signals are clear and the SDD transition requires a dispatch, generate a unique local `intent_id` in the form `intent-<uuid>` and put it at the start of the worker task description as `SDD dispatch <change> <persona> <intent_id>`. Before calling `/api/spawn`, write a pending dispatch-intent message to `raven@localhost` with `To: raven@localhost`, `From: raven+<raven_task_id>@localhost`, and subject `dispatching <persona> <intent_id>`. The gateway assigns the real spawn task ID inside `/api/spawn`, so do not invent or claim that ID before the call.

**Intent UUID idempotency check:** Before generating a new `intent_id`, check whether the raven mailbox already contains a pending or confirmed intent for the target persona from this check-in cycle (a `dispatching <persona> <intent_id>` subject line). If such a record exists, that `intent_id` is already the canonical idempotency key for this dispatch. Scan `kirocrew spawn list` task descriptions for that specific `intent_id` substring; if found, the spawn already happened — steer or continue that task rather than generating a new `intent_id` and spawning again. Only generate a fresh `intent_id` when no prior intent record exists for this dispatch.

After writing the pending marker, re-scan `raven@localhost`. If another unconfirmed pending marker for the same persona is older (compare Maildir arrival/`Date`, then `Message-ID` for a tie), hold; only the oldest marker proceeds. This post-write election prevents overlapping check-ins from both spawning. The winning check-in calls the authenticated `/api/spawn`, then immediately writes a confirmation message with subject `dispatching <persona> <spawn_task_id>` using the ID returned by the gateway; include the `intent_id` in its body to link the two records. If `/api/spawn` fails, write no confirmation and let the pending marker become stale only after the subsequent confirmation check described above.

- If the proposal, design, specs, or tasks artifact is not complete, dispatch Spectre to continue proposing or updating the change. Take no other dispatching action in that check-in.
- Once planning is complete, if tasks.md has any unchecked item, dispatch Ghost to implement the remaining tasks.
- Once every tasks.md item is checked and implementation is complete, if no review has been recorded since the last implementation dispatch, dispatch Banshee to independently review the implementation, fix findings that fit this change, and end with an explicit unresolved-findings verdict.
- When Banshee reports no unresolved findings, dispatch Reaper to run sync-specs and archive the change.
- If Banshee still reports unresolved findings after one fix-and-re-review cycle for the current implementation, escalate to the Admiral instead of dispatching another review or fix cycle.
- Confirm that the change is actually archived by reading real OpenSpec state on a later check-in; never assert completion from memory alone.
- {{RAVEN_SELF_CANCEL}}

Note: exit code 2 from `verify-admiral-sig` indicates a transient race condition — the signing secret file was not found after retries (typically during container startup). Raven should hold the current cycle and not escalate to Admiral; the secret will be available on the next scheduled check-in.

Each check-in takes exactly one action: dispatch at most one of Ghost, Spectre, Banshee, Wraith, or Reaper using the authenticated REST dispatch described above; hold when no action is needed; or message the Admiral when permission or a decision outside your authority is required. Do not use `kirocrew spawn run` for named persona dispatch. Do not implement work yourself, edit files, or change these standing orders through another channel.
