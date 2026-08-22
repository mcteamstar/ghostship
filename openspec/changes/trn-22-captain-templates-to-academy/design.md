## Context

`_ORDER_TEMPLATES` is a module-level dict in `transport/server.py` (line ~766)
containing one entry (`"sdd"`). Its body uses f-string interpolation of three
module-level constants (`_RAVEN_GATEWAY_ORIENTATION`, `_RAVEN_STORE_RESOLUTION`,
`_RAVEN_SELF_CANCEL`) and a `<change>` marker replaced at call time by
`_resolve_order_template`. The `resource_orders()` handler iterates the same
dict to expose `transport://orders`.

The academy directory (`academy/`) already holds agents, skills, policies, and
steering — this change adds `academy/orders/` as the canonical home for
standing-order templates. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Templates editable without redeploying the transport
- Templates co-located with other curriculum material in the academy
- Dynamic discovery of templates (add a file → immediately available)
- Clean placeholder syntax distinguishing transport-injected constants from
  per-call parameters

**Non-Goals:**
- Supporting multiple template directories or overlay paths
- Versioning or history for individual template files (git handles this)
- Changing the captain MCP tool's external interface or scheduling behaviour
- Migrating `_CAPTAIN_CHECKIN_TASK` (it is not exposed as a user-selectable
  template; only `_ORDER_TEMPLATES` entries are)

## Decisions

### D1: Template file format — plain Markdown with optional YAML front-matter

Each file `academy/orders/<name>.md` is a plain Markdown body. An optional YAML
front-matter block may carry a `description` field:

```yaml
---
description: "Drive a named OpenSpec change through the standard lifecycle."
---
```

If front-matter is absent, `description` defaults to `""`.

**Rationale:** Keeps templates human-readable and editable with any text editor.
YAML front-matter is a well-understood convention (Jekyll, Hugo, Docusaurus) and
avoids inventing a custom metadata format.

**Alternative considered:** Separate `<name>.yaml` metadata sidecar files —
rejected because it doubles file count and couples two files per template.

### D2: Placeholder syntax — `{{NAME}}`

Transport-injected constants use `{{RAVEN_GATEWAY_ORIENTATION}}`,
`{{RAVEN_STORE_RESOLUTION}}`, `{{RAVEN_SELF_CANCEL}}`. The per-call
`<change>` marker keeps its existing angle-bracket syntax for backward
compatibility.

**Rationale:** Double-brace is unambiguous in Markdown (not valid heading,
link, or HTML), easy to grep, and visually distinct from `<change>`. It avoids
conflict with Jinja/Mustache tooling because this is server-side substitution,
not user-facing templating.

**Alternative considered:** Keep using f-strings and Python constants — rejected
because it ties template content to Python source and prevents non-developer
editing.

### D3: Loading strategy — read from disk on each resolution call

`_resolve_order_template` reads `academy/orders/<name>.md` on every call rather
than caching at import time.

**Rationale:** Templates are called infrequently (once per captain order) so the
I/O cost is negligible. Reading live means a file edit is picked up immediately
without restarting the transport — essential for the "editable without redeploy"
goal.

**Alternative considered:** Load-once-at-startup with `importlib.resources` or a
module-level scan — rejected because it re-introduces the redeploy requirement
this change exists to eliminate.

### D4: Academy path resolution

The transport resolves the academy root from an environment variable
(`ACADEMY_PATH`, already used for other academy resources) or falls back to
`../academy` relative to the transport package. `academy/orders/` is a
sub-directory under that root.

**Rationale:** Reuses the existing mechanism for locating academy content,
requiring no new configuration.

### D5: `transport://orders` resource scans the directory

`resource_orders()` lists `*.md` files in the resolved `academy/orders/`
directory, reads each, strips front-matter, and returns the same
`## name\ndescription\n\nbody` format the current implementation produces.

**Rationale:** Dynamic scan means adding a template file is sufficient — no
registry or configuration update needed.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| File-not-found at resolution time if `academy/orders/` is not mounted in container | Dockerfile/compose must COPY or bind-mount `academy/orders/`; the existing `academy/` mount already covers this path if it mounts the whole directory |
| Template syntax error (unclosed placeholder) silently passes through | `_resolve_order_template` logs a warning if any `{{…}}` pattern remains after substitution; unit test asserts zero residual placeholders for known templates |
| Breaking existing tests that reference `_ORDER_TEMPLATES` dict directly | Tests are updated to use the new resolution path; a compatibility shim `_ORDER_TEMPLATES` property (read-only, populated from disk) may ease transition but is non-goal if tests are updated |

## Migration Plan

1. Create `academy/orders/sdd.md` containing the current `_ORDER_TEMPLATES["sdd"]["body"]` with f-string interpolations replaced by `{{…}}` placeholders.
2. Add optional YAML front-matter with the existing description string.
3. Update `_resolve_order_template` to read from disk and perform placeholder substitution.
4. Update `resource_orders()` to scan `academy/orders/` instead of iterating the dict.
5. Remove `_ORDER_TEMPLATES` dict from `transport/server.py`.
6. Update `test_transport.py` assertions that reference `_ORDER_TEMPLATES` to use the public API or read the file directly.
7. Verify the Dockerfile copies `academy/orders/` into the image alongside other academy content.

Rollback: revert the commit and the `_ORDER_TEMPLATES` dict returns.
