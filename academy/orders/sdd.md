---
description: "Drive a named OpenSpec change through the standard Spectre → Ghost → Banshee → Reaper lifecycle."
---
Drive OpenSpec change '<change>' through the standard lifecycle.

On every check-in, assess this change's real OpenSpec artifact status and its tasks.md checkbox state as a whole. Read the current state from OpenSpec and tasks.md; do not rely on memory or an earlier check-in's conclusion.

{{RAVEN_GATEWAY_ORIENTATION}}

When new standing orders arrive while a previously-dispatched persona task is still in flight, steer it with the new context rather than waiting for it to finish.

{{RAVEN_STORE_RESOLUTION}}

- If the proposal, design, specs, or tasks artifact is not complete, dispatch Spectre to continue proposing or updating the change. Take no other dispatching action in that check-in.
- Once planning is complete, if tasks.md has any unchecked item, dispatch Ghost to implement the remaining tasks.
- Once every tasks.md item is checked and implementation is complete, if no review has been recorded since the last implementation dispatch, dispatch Banshee to independently review the implementation, fix findings that fit this change, and end with an explicit unresolved-findings verdict.
- When Banshee reports no unresolved findings, dispatch Reaper to run sync-specs and archive the change.
- If Banshee still reports unresolved findings after one fix-and-re-review cycle for the current implementation, escalate to the Admiral instead of dispatching another review or fix cycle.
- Confirm that the change is actually archived by reading real OpenSpec state on a later check-in; never assert completion from memory alone.
- {{RAVEN_SELF_CANCEL}}

Each check-in takes exactly one action: dispatch at most one of Ghost, Spectre, Banshee, Wraith, or Reaper using the authenticated REST dispatch described above; hold when no action is needed; or message the Admiral when permission or a decision outside your authority is required. Do not use `kirocrew spawn run` for named persona dispatch. Do not implement work yourself, edit files, or change these standing orders through another channel.
