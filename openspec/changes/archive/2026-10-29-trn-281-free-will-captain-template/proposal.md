## Why

The Captain supports two structured lifecycle templates (`sdd`, `independent-review`)
but has no named template for open-ended autonomous work. Users who want the Captain
to execute a freeform instruction currently pass `message=` raw — there is no
discoverable "just do this" template. This makes the default behaviour invisible and
gives it no name to reference in documentation or skill guidance.

## What Changes

- Add `academy/orders/free-will.md` — a new built-in order template with aliases
  `free` and `willy`. The template resolves the standing order message directly and
  instructs Raven to execute it with full autonomy, using the standard
  intent/idempotency protocol, memory pressure handling, and self-cancel on
  completion. Open-ended/recurring instructions continue on each check-in without
  self-cancelling.
- Update the `captain` MCP tool docstring to document `free-will` / `free` / `willy`
  alongside `sdd` and `indy` as a built-in template.
- Update the `ghostship-command` skill to reference `free-will` / `willy` as the
  default open-ended template.

## Capabilities

### New Capabilities

- `captain-free-will-template`: The `free-will` built-in order template (aliases:
  `free`, `willy`). Defines Raven's behaviour when executing a freeform standing
  order: full autonomy over agent selection and approach, standard
  intent/idempotency dispatch protocol, memory-pressure handling, open-ended
  recurrence vs completion self-cancel detection.

### Modified Capabilities

- `captain`: The `captain` tool description SHALL list `free-will` / `free` /
  `willy` as an available template alongside `sdd` and `indy`.

## Impact

- `academy/orders/free-will.md` — new file (~30 lines)
- `transport/tools.py` — captain tool docstring updated
- `.claude-plugin/skills/ghostship-command/SKILL.md` — template reference updated
