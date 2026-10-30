# Spec — ga-lighthouse container

## Overview

`ga-lighthouse` is a dedicated microservice container on `ga-portside` that owns the Lighthouse fleet dashboard SPA and its browser-facing API. It is the only entry point for UI traffic — browsers never reach `ga-transport` directly for fleet observability.

## Container

- Image: `localhost/ga-lighthouse:latest`, built from `lighthouse/Containerfile`
- Network: `ga-portside` only
- Internal port: `8080`
- No host port published
- No data volume

## Routes

| Method | Path | Description |
|:-------|:-----|:------------|
| `GET /` | | Serve `static/index.html` |
| `GET /static/*` | | Serve static assets (CSS, JS) |
| `GET /api/crews` | | Proxy fleet data from `ga-transport /internal/crews`; return to browser |
| `GET /health` | | Return `{"status": "ok"}` — no auth required |

## SPA

Static files in `lighthouse/static/`:
- `index.html` — page shell and markup
- `style.css` — all styles; no inline styles in HTML
- `app.js` — all JS; polls `GET /api/crews` every 5s; no external dependencies

The SPA is functionally identical to the current Lighthouse heredoc. Visual design, polling behaviour, and response handling are unchanged. The split into separate files is a structural change only.

## Internal transport call

Lighthouse fetches fleet data by calling:
```
GET http://ga-transport:64057/internal/crews
X-Transport-Token: <GA_TRANSPORT_SECRET>
```

The response shape is identical to the current public `/api/crews` payload. Lighthouse forwards it to the browser unchanged.

## Environment / secrets

| Variable | Source | Description |
|:---------|:-------|:------------|
| `TRANSPORT_URL` | compose.yml env | Base URL of ga-transport (`http://ga-transport:64057`) |
| `ga-transport-secret` | Podman secret at `/run/secrets/ga-transport-secret` | Shared token read at startup for `X-Transport-Token` header |

## Transport changes required

- Add `GET /internal/crews` route — same payload as current `/api/crews`
- Route is only valid with correct `X-Transport-Token` header
- Remove `GET /api/crews` public route
- Remove `GET /` Lighthouse SPA route and `LIGHTHOUSE_HTML` constant
- Remove `_handle_lighthouse_get()` and `_handle_api_crews_get()` from `server.py`

## Portal (Caddy) changes required

- `_LIGHTHOUSE_ROUTE` in `bin/install.sh`: update `reverse_proxy` target from `ga-transport:64057` to `ga-lighthouse:8080`
- All other route config (forward_auth, redirect on 401, session gating) unchanged

## Acceptance criteria

1. `GET /` in a browser serves the Lighthouse SPA — same visual appearance as current
2. `GET /api/crews` returns the fleet JSON payload (same schema as current)
3. Transport no longer serves `GET /` or `GET /api/crews` on the main port
4. `ga-lighthouse` container is on `ga-portside` and not on `ga-starboard`
5. `ghostship upgrade` starts the `ga-lighthouse` container automatically
6. Auth gating (redirect to `/dashboard/login` when `GA_API_KEY` set) still works — handled at portal layer, unchanged
7. Existing unit tests for `_handle_lighthouse_get` and `_handle_api_crews_get` are replaced with tests for the new `GET /internal/crews` transport route
8. New unit tests for the lighthouse `server.py` cover: `/health`, `/api/crews` (mock transport response), static file serving
