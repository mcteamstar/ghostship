## 1. Async HTTP Client

- [x] 1.1 Add a module-level `httpx.AsyncClient` instance (`_async_http`) in `transport/server.py`, declared near the existing `_http` synchronous client, with the same 60-second default timeout

## 2. UI Proxy Handler

- [x] 2.1 Add `async def _handle_crew_ui_proxy(request: Request) -> Response` in `transport/server.py`: extract `crew_id` and optional sub-path from the ASGI scope path, call `_require_crew` / `_ensure_crew_running`, build the upstream URL `http://gs-{crew_id}:5476/{sub_path}?{query}`, forward method and headers (strip `host`), and return a `StreamingResponse` that streams the upstream response body; strip hop-by-hop headers from the forwarded response
- [x] 2.2 Return HTTP 404 with a plain-text "crew not found" message when `_require_crew` or `_get_crew` raises `KeyError` or `ValueError`
- [x] 2.3 Handle the no-trailing-path case (`/crews/{id}/ui` with no slash) by mapping it to the upstream root `/`

## 3. API Proxy Handler

- [x] 3.1 Add `async def _handle_crew_api_proxy(request: Request) -> Response` in `transport/server.py`: same structure as the UI proxy but with upstream path prefixed with `/api/`, and inject `Cookie: mc_token_5476=<crew["cookie"]>` into the upstream request headers
- [x] 3.2 On upstream 401 or 403, call `_refresh_cookie(crew, crew_id)` and retry the proxied request once with the refreshed cookie; if the retry also fails, stream back the upstream error response as-is
- [x] 3.3 Return HTTP 404 for unknown crew, same as UI proxy

## 4. BearerAuthMiddleware Routing

- [x] 4.1 In `BearerAuthMiddleware.__call__`, add a path-prefix check for `/crews/<id>/ui` and `/crews/<id>/ui/` after auth passes (not in the public-routes block), dispatching to `_handle_crew_ui_proxy`
- [x] 4.2 Add a path-prefix check for `/crews/<id>/api/` after auth passes, dispatching to `_handle_crew_api_proxy`
- [x] 4.3 Verify the checks are placed *after* the existing file-routes prefix check and *after* the API-key auth gate, so `GA_API_KEY` enforcement applies to both proxy routes

## 5. Tests

- [x] 5.1 Add tests for `_handle_crew_ui_proxy` in `test_transport.py` (or a new `test_proxy.py` following the project's existing test-file naming): mock `_require_crew`, `_ensure_crew_running`, and `_async_http`; assert that path, query string, and non-host headers are forwarded; assert response is streamed back
- [x] 5.2 Add a test asserting the UI proxy does NOT inject a `Cookie` header into the upstream request
- [x] 5.3 Add tests for `_handle_crew_api_proxy`: assert `mc_token_5476` cookie is injected; assert single-retry on 401/403 upstream response after `_refresh_cookie`
- [x] 5.4 Add a test for the stopped-crew path: mock `_ensure_crew_running` to simulate a restart and confirm the proxy proceeds after wake
- [x] 5.5 Add tests for the unknown-crew 404 path for both handlers
- [x] 5.6 Extend `BearerAuthMiddlewareTests` with cases for the `/crews/*/ui` and `/crews/*/api/` prefix dispatch: assert they reach the proxy handlers when auth passes; assert 401 when `GA_API_KEY` is set and bearer is missing/wrong

## 6. Documentation

- [x] 6.1 Add entries for `GET /crews/{crew_id}/ui` and `GET|POST|PUT|PATCH|DELETE /crews/{crew_id}/ui/{path:path}` to `docs/reference.md`, including auth note and browser-session note
- [x] 6.2 Add entry for `GET|POST|PUT|PATCH|DELETE /crews/{crew_id}/api/{path:path}` to `docs/reference.md`, including auth note, cookie-injection note, and example `curl` commands for common gateway REST calls (`GET /api/spawn`, `POST /api/spawn`)
