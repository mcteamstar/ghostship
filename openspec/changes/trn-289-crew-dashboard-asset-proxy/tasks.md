# Tasks — TRN-289 Crew Dashboard Main-Port Response

## T1 — Add `_handle_crew_ui_redirect` to `transport/server.py`

Add a new async handler in `transport/server.py`:

```python
async def _handle_crew_ui_redirect(request: Request) -> Response:
    """GET /crews/{crew_id}/ui[/*] — redirect to the per-crew dedicated port.

    Returns:
      302  to  http://<host>:<dashboard_port>/   when the crew has a port
      404  when the crew is unknown or has no dashboard_port
    """
    parsed = _extract_crew_proxy_parts(request.scope["path"])
    if parsed is None:
        return PlainTextResponse("Not found", status_code=404)
    crew_id, _segment, _sub = parsed

    try:
        crew = _require_crew(crew_id)
    except (KeyError, ValueError):
        return PlainTextResponse("Not found", status_code=404)

    dashboard_port = crew.get("dashboard_port")
    if not dashboard_port:
        return PlainTextResponse(
            f"Crew '{crew_id}' has no dashboard port allocated. "
            "Launch with dashboard=True or call POST /crews/{crew_id}/dashboard.",
            status_code=404,
        )

    # Build redirect URL using the same scheme/host logic as dashboard_url in _build_crews_payload
    _caddy_scheme = "http" if cfg.ga_portal_tls_mode == "off" else "https"
    if cfg.ga_host_url:
        from urllib.parse import urlparse as _up
        _ph = _up(cfg.ga_host_url)
        redirect_url = f"{_caddy_scheme}://{_ph.hostname}:{dashboard_port}/"
    else:
        redirect_url = f"{_caddy_scheme}://localhost:{dashboard_port}/"

    return RedirectResponse(url=redirect_url, status_code=302)
```

Import `RedirectResponse` from starlette at the top of the file (or wherever
other response types are imported).

## T2 — Register the handler in the route dicts

In `transport/server.py`, add `_handle_crew_ui_redirect` to both the no-key
and api-key route dicts (both blocks that build `_openapi_schema_routes` /
`_openapi_schema_public_routes`):

```python
(\"GET\",  \"/crews/*/ui\"): _handle_crew_ui_redirect,
```

This replaces or supplements the existing `_handle_crew_ui_proxy` entry — check
whether `_handle_crew_ui_proxy` is already registered there and if so, replace
it with `_handle_crew_ui_redirect`. The actual proxy continues to work via the
per-crew dedicated Caddy port, not the main port.

## T3 — Add `/crews/*/ui*` to the `ga-transport-misc` Caddy route in `install.sh`

In `bin/install.sh`, find the `ga-transport-misc` route (the one that matches
`/health`, `/version`, `/dashboard/*`, `/login*`, `/logout*`, etc.) and add
`/crews/*/ui`, `/crews/*/ui/*` to its path match list.

Before:
```json
"match": [{"path": ["/health", "/version", ..., "/crews/*/captain/stop"]}]
```

After:
```json
"match": [{"path": ["/health", "/version", ..., "/crews/*/captain/stop", "/crews/*/ui", "/crews/*/ui/*"]}]
```

Both the API-key and no-key variants of this route need updating.

## T4 — Add unit test in `tests/unit/test_server.py`

Add a test class `TestCrewUiRedirect`:

- `test_redirect_to_dashboard_port` — registry has a crew with `dashboard_port=64058`; `GET /crews/{id}/ui` returns 302 with `Location` pointing to `http://localhost:64058/`
- `test_404_when_no_dashboard_port` — crew exists but has no `dashboard_port`; returns 404
- `test_404_unknown_crew` — unknown crew_id; returns 404

## T5 — Run tests and smoke-test

```bash
bash scripts/run.sh --unit
```

All tests must pass. Manual smoke test:
```bash
ghostship upgrade
curl -I http://localhost:64057/crews/my-crew/ui/
# → HTTP/1.1 302 Found
# → Location: http://localhost:64058/
```
