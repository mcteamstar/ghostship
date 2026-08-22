# Proposal: trn-22-captain-templates-to-academy

## Why

Captain order templates (`_ORDER_TEMPLATES` in `transport/server.py`) are agent behaviour guidance — curriculum — but are hardcoded in the transport because they contain transport-specific substitution strings. This means updating a template requires redeploying the transport, templates can't vary by composition, and curriculum is split across two locations (transport and academy).

## What Changes

- Move template bodies to `academy/orders/<name>.md` files, with `{{RAVEN_GATEWAY_ORIENTATION}}` and `{{RAVEN_STORE_RESOLUTION}}` placeholders for transport-injected content
- Transport loads templates from the mounted academy path at resolution time instead of from the hardcoded `_ORDER_TEMPLATES` dict
- `_resolve_order_template` substitutes placeholders (including `<change>`) before writing to `captain@localhost`
- `transport://orders` MCP resource lists available templates dynamically from the academy path
- Remove `_ORDER_TEMPLATES` dict from `transport/server.py`

## Capabilities

### Modified Capabilities

- `autonomous-orchestration` — The mechanism by which captain order templates are discovered and resolved changes: templates are now filesystem-backed in the academy rather than hardcoded in the transport. Observable behaviour (template names, resolved content) is unchanged for existing templates.

## Impact

- `transport/server.py` — `_ORDER_TEMPLATES`, `_resolve_order_template`, `transport://orders` resource handler
- `academy/orders/` — new directory, `sdd.md` initial template
- `Dockerfile` / image build — `academy/orders/` must be bind-mounted or copied into the transport container alongside existing academy paths
- No change to the captain MCP tool interface or scheduling behaviour
