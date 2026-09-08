## 1. Update sdd.md reconciliation phase

- [x] 1.1 In `academy/orders/sdd.md`, in the Reconciliation phase Ghost task, replace the existing merge success and failure instructions (steps 3 and 4 of the Ghost task) with the updated resolution strategy:
  - On merge conflict: before mailing the Admiral, read each conflicting change's `specs/` and `tasks.md` to understand intent; resolve additively where both changes' intents can coexist; choose one side only when changes are genuinely mutually exclusive, using the specs to determine which is correct; re-run `bash tests/run.sh --unit` after resolution
  - On test failure after resolution (or unresolvable conflict): mail `admiral@localhost` with subject `sdd merge failed — manual intervention needed` including the full error output AND a per-conflict summary of every resolution decision attempted
  - On success (tests pass, with or without conflict resolution): remove each worktree, then mail `admiral@localhost` with subject `sdd complete — all changes merged, tests green` listing each change merged and, if any conflicts were resolved automatically, a summary of what conflicted and how Ghost resolved it

## 2. Validation

- [x] 2.1 Read the updated `sdd.md` reconciliation phase and confirm the resolution strategy, escalation criteria, and Admiral mail content are clearly described for Ghost
- [x] 2.2 Run `openspec validate trn-140-sdd-parallel-ghost-merge` and confirm no errors
