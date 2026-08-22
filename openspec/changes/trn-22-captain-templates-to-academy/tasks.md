## 1. Create template files in academy/orders/

- [ ] 1.1 Create `academy/orders/` directory
- [ ] 1.2 Create `academy/orders/sdd.md` with YAML front-matter (`description`) and the template body from the current `_ORDER_TEMPLATES["sdd"]["body"]`, replacing f-string interpolations of `_RAVEN_GATEWAY_ORIENTATION`, `_RAVEN_STORE_RESOLUTION`, and `_RAVEN_SELF_CANCEL` with `{{RAVEN_GATEWAY_ORIENTATION}}`, `{{RAVEN_STORE_RESOLUTION}}`, and `{{RAVEN_SELF_CANCEL}}` placeholders respectively

## 2. Implement template loading in transport

- [ ] 2.1 Add a helper function `_load_order_template(name: str) -> tuple[str, str]` that resolves `ACADEMY_PATH` (or falls back to `../academy`), reads `academy/orders/<name>.md`, parses optional YAML front-matter for `description`, and returns `(description, body)`
- [ ] 2.2 Add a helper function `_substitute_placeholders(body: str) -> str` that replaces `{{RAVEN_GATEWAY_ORIENTATION}}`, `{{RAVEN_STORE_RESOLUTION}}`, and `{{RAVEN_SELF_CANCEL}}` with the corresponding module-level constants
- [ ] 2.3 Update `_resolve_order_template` to call `_load_order_template` + `_substitute_placeholders` + the existing `<change>` substitution, raising `ValueError` for missing files or missing `change_name`
- [ ] 2.4 Add a warning log if any `{{…}}` pattern remains in the resolved body after substitution

## 3. Update transport://orders resource

- [ ] 3.1 Update `resource_orders()` to scan `academy/orders/*.md`, load each template, and render the same `## name\ndescription\n\nbody` format
- [ ] 3.2 Handle empty/missing directory case returning `No standing-order templates are available.`

## 4. Remove legacy dict

- [ ] 4.1 Remove the `_ORDER_TEMPLATES` dict definition from `transport/server.py`

## 5. Update tests

- [ ] 5.1 Update `test_transport.py` tests that reference `server._ORDER_TEMPLATES` to use `_resolve_order_template` or read `academy/orders/sdd.md` directly
- [ ] 5.2 Add test: template loaded from disk matches expected resolved content
- [ ] 5.3 Add test: unknown template name raises ValueError
- [ ] 5.4 Add test: `resource_orders()` returns dynamic listing from `academy/orders/`
- [ ] 5.5 Add test: placeholder residual warning when an unknown `{{…}}` remains

## 6. Build / deployment

- [ ] 6.1 Verify Dockerfile copies or mounts `academy/orders/` into the transport container (confirm existing `academy/` COPY covers the new subdirectory)
