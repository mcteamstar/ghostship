## Why

The `sdd` captain order already dispatches Ghost for the post-archive worktree merge in parallel multi-change mode, but Ghost's current instructions tell it to escalate to the Admiral immediately on any conflict or test failure. Since Ghost has access to the change specs and tasks as context, it can resolve most merge conflicts without human intervention — the escalation path should only fire after Ghost has made a genuine attempt at resolution.

## What Changes

- **Ghost reconciliation task: attempt conflict resolution before escalating** — update the Reconciliation phase in `academy/orders/sdd.md` so that Ghost's merge task instructs it to read each conflicting change's `specs/` and `tasks.md` to understand intent, resolve conflicts accordingly, re-run the test suite, and only escalate to the Admiral if conflicts remain unresolvable or tests cannot be made to pass.
- **Clear resolution strategy guidance** — give Ghost explicit strategy: resolve conflicts by preferring the intent expressed in both changes' specs, treating conflicting hunks as additive where possible, and noting every resolution decision in the Admiral mail.

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities
_(none — this change only modifies `academy/orders/sdd.md`, which is an order template file, not a spec-governed capability. No spec-level behaviour of the transport or tools changes.)_

## Impact

- `academy/orders/sdd.md` — Reconciliation phase Ghost task description updated with conflict resolution strategy and escalation criteria.
- No code changes. No transport changes. No test changes.
- Behaviour change is purely in what Ghost is instructed to do during the reconciliation task.
