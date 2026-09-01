## Why

The crew UI proxy works for the initial page load but breaks immediately after: SPAs served by the KiroCrew gateway use root-absolute asset paths (`/static/app.js`, `/static/app.css`) that the browser fetches from the transport root, which has no handler for them and returns 404. Additionally, `KIROCREW_CORS_ORIGINS` is set to only the crew's internal origin at container start time, so browser requests issued from the transport's public origin are CORS-rejected. Found by Steve Mactaggart (stevemac007) in PR #3.

## What Changes

- The transport intercepts root-absolute requests (`GET /static/**`, `/assets/**`, and any path not matching an existing transport route) when the browser's `Referer` header points to a `/crews/{id}/ui/` page, and re-routes them through the crew UI proxy for that crew.
- A `crew_ui_context` cookie is set on the browser when the initial `/crews/{id}/ui/` page loads, providing a fallback crew identity for service-worker and no-Referer fetches.
- The transport's public origin (`GA_HOST_URL` or `http://localhost:{PORT}`) is injected into `KIROCREW_CORS_ORIGINS` when the crew container is started, so browser requests from the transport origin are accepted by the crew gateway's CORS policy.

## Capabilities

### New Capabilities

- `crew-ui-spa-routing`: Root-absolute SPA asset requests are resolved to the originating crew's gateway using Referer header or cookie fallback, then proxied transparently.

### Modified Capabilities

- `proxy-hosting`: Two new requirements — SPA asset re-routing and transport-origin CORS injection at crew start.

## Impact

- `transport/server.py` — new catch-all route (lowest priority) for SPA assets; sets `crew_ui_context` cookie on UI proxy responses.
- `transport/server.py` (container create) — inject transport public origin into `KIROCREW_CORS_ORIGINS` env var when starting a crew container.
- `openspec/specs/proxy-hosting/spec.md` — two new requirements added.
- No API or MCP tool changes. No breaking changes.
