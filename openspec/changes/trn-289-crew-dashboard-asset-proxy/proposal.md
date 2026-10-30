# Proposal

## Why

When a crew is launched with `dashboard=True`, the per-crew KC dashboard is
accessible at a dedicated Caddy port (e.g. `localhost:64058/`). KiroCrew's SPA
loads correctly at that URL — assets, navigation, and WebSocket all work.

However, `GET /crews/{id}/ui/` on the **main port** (`localhost:64057`) returns
`HTTP 200 Content-Length: 0` — Caddy has no matching route for that path on the
main port, so requests fall through to Caddy's default empty-body response.
When the browser opens this URL, KiroCrew's HTML is not returned, and if a stale
page attempts to load its asset chunks they receive empty bodies, causing
`SyntaxError: illegal character U+FFFD` (null byte parsed as JS).

The transport proxy handler for `/crews/*/ui` does exist and would work — it
just isn't wired into the main Caddy port's route config.

## What Changes

- Add `/crews/*/ui*` to the main Caddy port route config in `bin/install.sh`,
  proxying to `ga-transport` the same way other crew routes are handled
- Alternatively, redirect `/crews/{id}/ui` on the main port to the per-crew
  dedicated port URL (cleaner, avoids maintaining two proxy paths)
- Either fix ensures the main port gives a useful response instead of an empty 200

## Capabilities

### Modified Capabilities

- `crew-ui-spa-routing`: Add requirement that accessing the crew dashboard via
  the main port gives a correct response (either serving the SPA or redirecting
  to the dedicated port URL) rather than an empty HTTP 200.

## Impact

- `bin/install.sh` — main Caddy port route config (`ga-transport-misc` or a
  new route entry)
- No changes to `ga-radar`, `ga-transport` proxy logic, or `caddy.py`
