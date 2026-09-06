## Context

Four captain order templates exist after TRN-110:
- `sdd.md` — single change lifecycle, uses `<change>` required token
- `sdd-parallel.md` — multi-change lifecycle, uses `<changes>` required token; lacks worktree isolation and merge reconciliation
- `independent-review.md` — change-scoped review, uses `<change>` required token
- `independent-review-all.md` — whole-codebase review, same as above but with hardcoded `all` scope, no `<change>` token

`transport/captain.py` already has:
- `<change>` — required token, raises if `change_name` is None
- `<changes>` — required comma-separated token, raises if `change_name` is None or empty

A new optional token `<change?>` is needed for `independent-review` — when present but `change_name` is None, substitutes a default string rather than raising.

## Goals / Non-Goals

**Goals:**
- Two templates replacing four: `sdd` (single + multi) and `independent-review` (scoped + whole-codebase)
- `sdd` multi-change path has proper worktree isolation and merge reconciliation baked in
- `independent-review` works with or without `change_name`
- `captain.py` gains `<change?>` optional token support
- All existing test_captain.py tests continue to pass; new tests cover the new paths

**Non-Goals:**
- No changes to `sdd` single-change behaviour
- No changes to any other templates (`captain.md` check-in task is unaffected)
- No MCP API changes

## Decisions

### `<change?>` optional token

In `_resolve_order_template()`, add a third substitution branch after the existing `<change>` and `<changes>` blocks:

```python
if "<change?>" in body:
    if "<change>" in body or "<changes>" in body:
        raise ValueError("Template body must not mix <change?> with <change> or <changes>")
    scope = change_name if change_name else "entire codebase"
    if change_name:
        _validate_captain_change_name(change_name)
    body = body.replace("<change?>", scope)
```

### `sdd.md` multi-change structure

The updated `sdd.md` detects whether `<change>` contains a comma on the first check-in:

- **No comma** → existing single-change behaviour, no worktree
- **Comma present** → parse into list; create worktrees; per-change lifecycle; merge reconciliation phase at the end

The `<changes>` token is retired from the template (the `sdd-parallel` description token). The `sdd` template uses `<change>` for both cases — Raven parses the value at runtime.

The `<changes>` token support in `captain.py` is kept (it may be used by other templates in future), but `sdd-parallel.md` which was the only user is deleted.

### Worktree lifecycle in sdd.md (multi-change)

```
First check-in:
  for each change in list:
    git -C repo worktree add ../repo-<change> -b <change> HEAD

Per-change dispatch:
  task descriptions embed the worktree path so agents cd into it

Completion phase (all changes archived):
  for each change in list:
    git -C repo merge --no-ff <change> -m "merge: <change> into <branch>"
  bash tests/run.sh --unit
  git worktree remove ../repo-<change> --force  (for each)
  mail admiral@localhost with result
  self-cancel
```

### `independent-review.md` optional scope

Replace `Scope: change <change>` with `Scope: <change?>` — the token substitutes either the change name or `"entire codebase"`. Mail subjects use the same substituted value. The description front-matter is updated to reflect the optional nature.

## Risks / Trade-offs

- `sdd.md` grows significantly in length — the multi-change section adds ~40 lines. Still manageable.
- The worktree merge step could produce conflicts if the two changes touch the same file — the template should mail the Admiral on conflict rather than failing silently
- Ghost sessions reading the worktree amendment in the current TRN-105/109 run figured this out without explicit worktree path injection — the new template should be more explicit to avoid needing mid-flight amendments
