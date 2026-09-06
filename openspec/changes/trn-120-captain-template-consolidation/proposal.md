## Why

Four captain templates (`sdd`, `sdd-parallel`, `independent-review`, `independent-review-all`) have grown organically during 0.3.0–0.3.1 development. Two redundancy patterns were identified in practice during TRN-105/109:

1. `sdd-parallel` duplicates the `sdd` lifecycle with parallel execution bolted on, but the single-action rule means it's serialised anyway — and it lacks worktree isolation and merge reconciliation, requiring mid-flight captain amendments to fix both gaps.
2. `independent-review-all` is identical to `independent-review` except for the scope line — a pure duplication that could be a parameter.

The result is four templates where two would do.

## What Changes

- **`sdd.md`** — extended to accept `change_name` as either a single name or a comma-separated list:
  - Single change: existing behaviour unchanged
  - Multiple changes: on first check-in, Raven creates a dedicated git worktree per change (`git worktree add ../repo-<change-name> -b <change-name> HEAD`); dispatches each change's Spectre/Ghost/Banshee/Reaper sessions into its worktree; when all changes are archived, merges each branch back into the main checkout on the same branch, runs `bash tests/run.sh --unit`, mails the Admiral with the result, removes the worktrees, then self-cancels
- **`sdd-parallel.md`** — deleted
- **`independent-review.md`** — extended so `change_name` is optional: if provided, scopes the review to that change; if omitted, reviews the entire codebase (current `independent-review-all` behaviour)
- **`independent-review-all.md`** — deleted
- **`transport/captain.py`** — `_resolve_order_template()` gains support for an optional `<change>` token: when the token is present but `change_name` is `None`, substitute a default (e.g. `"entire codebase"`) rather than raising; this requires a new `<change?>` optional token distinct from the required `<change>` token
- **`transport/server.py`** — captain tool docstring updated: remove `sdd-parallel` and `independent-review-all` examples; update `sdd` to show both single and comma-separated usage; update `independent-review` to show optional `change_name`
- Unit tests updated to cover the new optional token behaviour and the multi-change `sdd` path

## Capabilities

### New Capabilities

_None — behaviour consolidation, no new MCP surface._

### Modified Capabilities

_None — no spec-level changes. `skip_specs: true`._

## Impact

- `academy/orders/sdd.md` — extended
- `academy/orders/sdd-parallel.md` — deleted
- `academy/orders/independent-review.md` — extended
- `academy/orders/independent-review-all.md` — deleted
- `transport/captain.py` — new `<change?>` optional token
- `transport/server.py` — docstring update
- `tests/unit/test_captain.py` — new tests for optional token and multi-change sdd path
