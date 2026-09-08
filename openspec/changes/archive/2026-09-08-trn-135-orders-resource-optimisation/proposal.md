## Why

`transport://orders` returns the full body of every standing-order template in one payload. Agents reading it to discover available templates pay the full context cost of all template bodies — the SDD order in particular is substantial — even when they only need to know what templates exist before passing one to `captain`. This drives up per-call context cost for every captain-planning interaction.

## What Changes

- **`transport://orders` becomes a summary index** — returns only template name and one-line description for each available template, not the full body.
- **`transport://orders/{name}` per-template resource** — exposes each template's complete resolved body on demand, so an agent that needs the full content of a specific template can fetch only that one.
- **`GA_ORDERS_DIR` configurable user-defined orders directory** — operators can point this env var at a directory of additional `.md` template files. User-defined templates are merged with built-in `academy/orders/` templates; user-defined templates with the same name as a built-in template take precedence (override). No forking required to customise the template set.

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities
- `mcp-server`: `transport://orders` requirement changes from full-body listing to summary index; adds `transport://orders/{name}` per-template resource and `GA_ORDERS_DIR` configurable directory behaviour.
- `captain`: `_resolve_orders_dir()` is extended to merge a user-defined directory with the built-in academy orders directory, respecting `GA_ORDERS_DIR`.

## Impact

- `transport/server.py` — modify `resource_orders()` to return a summary index; add a new `transport://orders/{name}` resource handler using MCP resource templates.
- `transport/captain.py` — `_resolve_orders_dir()` / `_load_order_template()` / template enumeration updated to merge user-defined templates with built-in ones; `GA_ORDERS_DIR` support added.
- `transport/config.py` — add `ga_orders_dir: str` config field.
- `docs/configuration.md` — document `GA_ORDERS_DIR`.
- `tests/unit/` — update tests for `resource_orders()` summary format; add tests for per-template resource and user-defined directory merge.
- No breaking changes to the `captain` tool interface — `template=` parameter continues to work exactly as before.
