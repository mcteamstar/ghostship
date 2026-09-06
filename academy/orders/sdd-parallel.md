---
description: "Drive multiple named OpenSpec changes concurrently through the standard SDD lifecycle."
---
Drive OpenSpec changes '<changes>' concurrently through the standard lifecycle.

On the first check-in, parse `<changes>` into a list of individual change names (comma-separated). Maintain a per-change state table in your working notes:

```
change name → current phase, last dispatched persona, pending intent IDs
```

On every subsequent check-in, assess EACH change's real OpenSpec artifact status and tasks.md checkbox state independently. Read the current state from OpenSpec and tasks.md for each change; do not rely on memory or an earlier check-in's conclusion.

{{RAVEN_GATEWAY_ORIENTATION}}

When new standing orders arrive while a previously-dispatched persona task is still in flight, steer it with the new context rather than waiting for it to finish.

{{RAVEN_STORE_RESOLUTION}}

## Dispatch coordination (per change, independently)

Before dispatching any persona for a given change, apply the standard three-signal dispatch-coordination check. All intent markers and task description prefixes embed the change name, so cross-change collision cannot occur:

1. **Mailbox signal (primary):** Scan `raven@localhost` for an unconfirmed dispatch-intent for the target persona+change. A pending intent (`dispatching <persona> <intent_id>`) with a task description containing both the change name and persona means that persona is already dispatched for that change.
2. **Task-description signal (secondary):** Cross-check `kirocrew spawn list` for an in-flight task whose description contains the specific change name and persona. Best-effort only.
3. **Agent-field signal (tertiary):** Check the `agent` field as final confirmation only.

All three signals must be clear before a new dispatch proceeds for that change. A confirmed intent is stale when `kirocrew spawn list` shows its referenced task as completed or absent.

## Intent format

Generate intent IDs as `intent-<uuid>`. Task descriptions MUST use the existing format:

```
SDD dispatch <intent_id> <change-name> <persona>
```

The `intent_id` comes immediately after the literal `SDD dispatch` prefix, before the change name and persona, so its fixed length always survives `kirocrew spawn list`'s 80-character field cap.

## Lifecycle rules (apply independently to each change)

- If the proposal, design, specs, or tasks artifact is not complete for a change, dispatch Spectre to continue proposing or updating it. Take no other dispatching action for that change in that check-in.
- Once planning is complete for a change, if tasks.md has any unchecked item, dispatch Ghost to implement the remaining tasks.
- Once every tasks.md item is checked, if no review has been recorded since the last implementation dispatch, dispatch Banshee to independently review, fix findings that fit this change, and end with an explicit unresolved-findings verdict.
- When Banshee reports no unresolved findings, dispatch Reaper to run sync-specs and archive the change.
- If Banshee still reports unresolved findings after one fix-and-re-review cycle, escalate to the Admiral instead of dispatching another cycle.
- Confirm each change is actually archived by reading real OpenSpec state on a later check-in; never assert completion from memory alone.

## Independent progress

A change that reaches archive does not block or affect other changes still in progress. When each individual change is archived, send a per-change completion mail to `admiral@localhost` with subject `SDD complete <change-name>` and a brief summary.

## Completion

When ALL changes in the list are archived, send a final summary mail to `admiral@localhost` with subject `SDD parallel complete` listing each change and its outcome. Then {{RAVEN_SELF_CANCEL}}.

## Single-action rule

Each check-in takes exactly one action across all changes: dispatch at most one persona (for the change that needs it most urgently); hold when no action is needed; or message the Admiral when a decision outside your authority is required. Do not implement work yourself, edit files, or change these standing orders.

Note: exit code 2 from `verify-admiral-sig` indicates a transient race condition — hold and reassess on the next cycle.
