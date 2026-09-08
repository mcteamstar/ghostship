## 1. captain.py — template enumeration and GA_ORDERS_DIR

- [x] 1.1 Add `GA_ORDERS_DIR` to `transport/config.py` as an optional string field (default empty), and wire it into `captain.py` as a module-level variable read at import time (same pattern as `_ORDERS_DIR`)
- [x] 1.2 Add a `_list_order_templates()` function in `captain.py` that returns `list[tuple[str, str]]` — `(name, description)` — by enumerating built-in templates first, then merging user-defined templates from `GA_ORDERS_DIR` (user-defined overrides built-in on name collision); log a one-time warning if `GA_ORDERS_DIR` is set but the path does not exist
- [x] 1.3 Write unit tests for `_list_order_templates()` covering: (a) built-ins only when `GA_ORDERS_DIR` unset, (b) user-defined templates added when `GA_ORDERS_DIR` set, (c) user-defined overrides built-in with same stem, (d) non-existent `GA_ORDERS_DIR` path logs warning and falls back to built-ins

## 2. server.py — resource changes

- [x] 2.1 Modify `resource_orders()` to call `_list_order_templates()` and return a summary index (name + description per entry, no body); update the MCP resource description to reflect the new format
- [x] 2.2 Register a new `transport://orders/{name}` MCP resource handler that calls `_load_order_template(name)`, applies `_substitute_placeholders()`, and returns the resolved body; return a clear not-found message if the template doesn't exist
- [x] 2.3 Confirm FastMCP URI template support for `transport://orders/{name}` during implementation; if not supported in the pinned version, register individual resources per known template name as a fallback and note it
- [x] 2.4 Write unit tests for the updated `resource_orders()` confirming: (a) response contains only name + description, no body text, (b) user-defined templates appear in the index
- [x] 2.5 Write unit tests for the `transport://orders/{name}` resource covering: (a) known template returns resolved body without front-matter, (b) unknown template returns a not-found message

## 3. Documentation and validation

- [x] 3.1 Add `GA_ORDERS_DIR` to `docs/configuration.md` with description, type, and default
- [x] 3.2 Run the full unit test suite (`tests/unit/`) and confirm all tests pass
- [x] 3.3 Run `openspec validate trn-135-orders-resource-optimisation` and confirm no errors
