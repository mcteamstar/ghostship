## 1. Add `<change?>` optional token to `transport/captain.py`

- [ ] 1.1 In `_resolve_order_template()`, after the existing `<changes>` block, add a `<change?>` branch: if `change_name` is not None, validate it and substitute; if None, substitute `"entire codebase"`. Raise if `<change?>` is mixed with `<change>` or `<changes>` in the same body.
- [ ] 1.2 Add unit tests in `tests/unit/test_captain.py`:
  - `test_optional_change_token_with_name` — `<change?>` substitutes the provided name
  - `test_optional_change_token_without_name` — `<change?>` substitutes `"entire codebase"` when `change_name` is None
  - `test_optional_change_token_conflict_with_required` — raises when body contains both `<change?>` and `<change>`
- [ ] 1.3 Run `bash tests/run.sh --unit 2>&1 | tail -5` — confirm all tests pass

## 2. Update `academy/orders/independent-review.md`

- [ ] 2.1 Update front-matter description to: `"Dispatch four concurrent independent reviewers and consolidate their findings. Scoped to a named change when change_name is provided; reviews the entire codebase when omitted."`
- [ ] 2.2 Replace `Scope: change <change>` with `Scope: <change?>` on the first body line
- [ ] 2.3 Replace all remaining `<change>` occurrences in the body with `<change?>` (task prefixes, mail subjects, consolidation subject line)
- [ ] 2.4 Delete `academy/orders/independent-review-all.md`
- [ ] 2.5 Run `bash tests/run.sh --unit 2>&1 | tail -5` — confirm all tests pass (the existing `independent-review` tests should still pass; `independent-review-all` tests should be removed or updated)

## 3. Update `academy/orders/sdd.md` — multi-change support

- [ ] 3.1 Update front-matter description to: `"Drive one or more named OpenSpec changes through the standard Spectre → Ghost → Banshee → Reaper lifecycle. Pass a comma-separated list for parallel multi-change execution with automatic worktree isolation."`
- [ ] 3.2 Add a **Multi-change mode** section after the existing preamble: on first check-in, detect if `<change>` contains a comma; if so, parse the list and create a git worktree per change (`git -C repo worktree add ../repo-<change-name> -b <change-name> HEAD`)
- [ ] 3.3 Add per-change dispatch coordination: task descriptions embed the worktree path (`cd /home/kirocrew/workplace/kirocrew-workspace/repo-<change-name> && SDD dispatch ...`); all three dispatch-coordination signals include the change name for namespace safety
- [ ] 3.4 Add **Reconciliation phase**: when all changes are archived, for each change: `git -C repo merge --no-ff <change-name> -m "merge: <change-name>"`. Run `bash tests/run.sh --unit`. On success, remove worktrees and mail Admiral `sdd complete — all changes merged, tests green`. On conflict or test failure, mail Admiral `sdd merge failed — manual intervention needed` with the error output. Then self-cancel.
- [ ] 3.5 Delete `academy/orders/sdd-parallel.md`

## 4. Update `transport/server.py` docstring

- [ ] 4.1 Remove `sdd-parallel` and `independent-review-all` from the `captain` tool docstring examples
- [ ] 4.2 Update `sdd` example to show both single and comma-separated usage
- [ ] 4.3 Update `independent-review` example to show both with and without `change_name`

## 5. Verification

- [ ] 5.1 Run `bash tests/run.sh --unit 2>&1 | tail -5` — confirm all tests pass
- [ ] 5.2 Confirm `openspec status --change trn-120-captain-template-consolidation` reports planning complete
- [ ] 5.3 Verify `academy/orders/` contains exactly: `sdd.md`, `independent-review.md`, `captain.md` (and no `sdd-parallel.md` or `independent-review-all.md`)
