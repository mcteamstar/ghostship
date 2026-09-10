## Context

See proposal.md for motivation.

Current state: `resource_orders()` in `server.py` calls `_resolve_orders_dir()`, globs `*.md`, calls `_load_order_template(name)` for each, calls `_substitute_placeholders(body)`, and concatenates everything into one string. `_load_order_template()` lives in `captain.py` and returns `(description, body)`. `_resolve_orders_dir()` returns `/orders` (container mount) if it exists, else the `academy/orders/` path relative to the module. No enumeration helper exists — the glob is done inline.

MCP resource templates (`transport://orders/{name}`) require the FastMCP `@mcp.resource("transport://orders/{name}")` pattern with a parameter in the URI — the same mechanism used for other parameterised resources in the codebase if any exist, otherwise a straightforward FastMCP feature.

## Goals / Non-Goals

**Goals:**
- `transport://orders` returns name + description only.
- `transport://orders/{name}` returns the full resolved body of a single template.
- `GA_ORDERS_DIR` enables operator-added/overriding templates without code changes.
- The `captain` tool's `template=` parameter continues to work identically.

**Non-Goals:**
- Hot-reload of templates at runtime — templates are read on each resource access, which is sufficient.
- Template validation or schema enforcement for user-defined templates.
- Exposing `GA_ORDERS_DIR` as a container mount point — operators set it to a host-accessible path injected via the compose env block.

## Decisions

### Decision: Introduce a `_list_order_templates()` helper in captain.py

Extract template enumeration into a shared helper that returns `list[tuple[str, str]]` — `(name, description)` — merging built-in and user-defined sources. Both `resource_orders()` (index) and any per-template resource handler use this same helper. Keeps enumeration logic in one place alongside the existing `_load_order_template()` and `_resolve_orders_dir()`.

### Decision: Merge user-defined templates at enumeration time, not at startup

`_list_order_templates()` reads both directories on every call. Templates are small files; the cost is negligible. This avoids any need for a file-watcher or startup-time caching, and means `GA_ORDERS_DIR` changes take effect immediately on the next resource read without a transport restart.

**User-defined takes precedence**: build a dict keyed by stem, populate built-ins first, then overwrite with user-defined. The result is the merged effective set.

### Decision: `GA_ORDERS_DIR` is a plain env var read at module level in captain.py

Same pattern as `_ORDERS_DIR` (already derived from `ACADEMY_PATH` env var at module load). `GA_ORDERS_DIR` is read once at import time; the resolved path is checked for existence on each `_list_order_templates()` call. If the path doesn't exist, log a warning once (not on every call — use a module-level flag) and skip it.

### Decision: MCP resource template for `transport://orders/{name}`

FastMCP supports URI templates with `{name}` parameters. Register a second resource at `"transport://orders/{name}"`. The handler receives `name: str`, calls `_load_order_template(name)` (which already raises `ValueError` for unknown names), catches that and returns a not-found message, or returns the resolved body on success.

**Alternative considered**: a single `transport://orders` resource that detects a query parameter for the name. Rejected — MCP resource templates are the idiomatic approach and give clients proper URI-based addressability.

### Decision: Summary index format

Plain text, one entry per line or a simple `## name\n<description>` block (without body). The index is intended to be cheap to read; a minimal format serves this better than Markdown prose. Format: `name: <description>` per line, or the existing `## name\ndescription\n` pattern without the body section. The latter is consistent with the existing resource and easier to parse.

## Risks / Trade-offs

**MCP resource template support in FastMCP version in use** → If the transport's FastMCP version doesn't support URI templates, a different approach (one registered resource per known template name, or a catch-all) would be needed. Low risk — FastMCP has supported URI templates since early versions; confirm during implementation.

**User-defined templates with malformed front-matter** → `_load_order_template()` already handles missing/malformed YAML front-matter gracefully (defaults to empty description). No additional hardening needed.

**Warning log spam if GA_ORDERS_DIR is set to a non-existent path** → Mitigated by the one-time warning pattern (log once, not on every enumeration call).

## Migration Plan

No breaking changes. The `transport://orders` response format changes (no more full bodies), but the old resource had no documented consumers beyond agents choosing a template name — who now have a lighter read. Any agent that was reading the full body can read `transport://orders/{name}` instead. No transport restart required beyond deploying the new image.
