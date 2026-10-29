## Context

Order templates live in `academy/orders/` as `.md` files with YAML front matter.
The transport's `captain.py` discovers them via `_list_order_templates()`, loads
them via `_load_order_template()`, and substitutes `{{RAVEN_GATEWAY_ORIENTATION}}`,
`{{RAVEN_STORE_RESOLUTION}}`, and `{{RAVEN_SELF_CANCEL}}` placeholders via
`_substitute_placeholders()`. The `<message>` and `<change>` substitutions happen
in `_resolve_captain_order()` in `tools.py`.

`free-will.md` is already written. The remaining work is docstring and skill updates.

See `proposal.md` for motivation.

## Goals / Non-Goals

**Goals:**
- `free-will.md` discoverable as a named template with aliases `free` and `willy`
- `captain` tool docstring lists `free-will` / `free` / `willy`
- `ghostship-command` skill updated to reference `willy` as the go-to open-ended template

**Non-Goals:**
- Changing the Captain scheduling infrastructure
- Making `free-will` the automatic default when `template=None` (the current `message=`
  path already works; adding a silent resolution would change behaviour for existing
  callers who rely on the raw message path)
- Changing SDD or independent-review templates

## Decisions

### D1: free-will.md uses `<message>` placeholder — same substitution path as SDD uses `<change>`

The `_resolve_captain_order()` function in `tools.py` already handles `<change>`
substitution for SDD. The `free-will` template uses `<message>` — this substitution
is also already in place for the raw `message=` path. No new substitution logic needed.

### D2: No silent default resolution — explicit template= required

Making `template=None` + `message=` silently resolve to `free-will` would change
observable behaviour (the resolved text would gain the template scaffolding). The
value of `free-will` is discoverability and naming, not behavioural change. Callers
who want the template use `template="willy"`; callers who use raw `message=` continue
unchanged.

### D3: Skill update targets ghostship-command only

`ghostship-capability` and `ghostship-admin` don't need updating — they're about
transport configuration, not fleet operation. `ghostship-command` is the Admiral's
playbook and is where template guidance lives.

## Risks / Trade-offs

- The template file is already written — the main risk is stale docstrings or skill
  text that doesn't mention `willy`. Low risk, easy to fix post-ship.
