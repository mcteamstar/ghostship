# ga-radar Specification

## Purpose

`ga-radar` is a dedicated microservice container on `ga-portside` that owns the
Radar fleet dashboard SPA and its browser-facing API. It is the only entry point
for UI traffic — browsers never reach `ga-transport` directly for fleet
observability.

## Requirements

### Requirement: ga-radar runs as a dedicated portside container

`ga-radar` SHALL run as a standalone container on `ga-portside` only. It SHALL
NOT be on `ga-starboard`. It SHALL expose port `8080` internally with no host port
published and no data volume.

Image: `localhost/ga-radar:latest`, built from `radar/Containerfile`.

#### Scenario: Container network isolation

- **WHEN** `ga-radar` is started by `ghostship upgrade`
- **THEN** it is attached to `ga-portside` only
- **THEN** crew containers on `ga-starboard` cannot reach it by hostname

### Requirement: ga-radar serves the Radar SPA and fleet API

`ga-radar` SHALL expose four routes:

| Method | Path | Description |
|:-------|:-----|:------------|
| `GET /` | | Serve `static/index.html` |
| `GET /static/*` | | Serve static assets (CSS, JS) |
| `GET /api/crews` | | Proxy fleet data from `ga-transport /internal/crews` |
| `GET /health` | | Return `{"status": "ok"}` — no auth required |

Static files in `radar/static/` (`index.html`, `style.css`, `app.js`) are baked
into the image at build time. `app.js` polls `GET /api/crews` every 5s with no
external dependencies.

#### Scenario: SPA served at root

- **WHEN** `GET /` is requested through Caddy with a valid session
- **THEN** `ga-radar` returns HTTP 200 with `Content-Type: text/html`
- **THEN** the response body is `static/index.html`

#### Scenario: Static assets served

- **WHEN** `GET /static/app.js` or `GET /static/style.css` is requested
- **THEN** `ga-radar` returns the asset with the correct content-type

#### Scenario: Fleet API proxied to transport

- **WHEN** `GET /api/crews` is requested
- **THEN** `ga-radar` calls `GET http://ga-transport:64057/internal/crews` with `X-Transport-Token`
- **THEN** the response payload is returned to the browser unchanged

#### Scenario: Health endpoint needs no auth

- **WHEN** `GET /health` is requested without any credentials
- **THEN** `ga-radar` returns HTTP 200 `{"status": "ok"}`

### Requirement: ga-radar authenticates to ga-transport with the shared secret

`ga-radar` SHALL read the transport secret from `/run/secrets/ga-transport-secret`
at startup (delivered as a Podman secret). It SHALL include the secret as
`X-Transport-Token` on every call to `ga-transport /internal/crews`. If the
secret file is absent, `ga-radar` SHALL start with an empty token and log a
warning.

| Variable | Source | Description |
|:---------|:-------|:------------|
| `TRANSPORT_URL` | compose.yml env | Base URL of ga-transport |
| `ga-transport-secret` | Podman secret | Shared token for `X-Transport-Token` |

#### Scenario: Secret absent at startup

- **WHEN** `/run/secrets/ga-transport-secret` does not exist
- **THEN** `ga-radar` starts successfully and logs a warning
- **THEN** requests to `/api/crews` return 502 (transport rejects the empty token)

### Requirement: Caddy routes browser traffic to ga-radar

Caddy (`ga-portal`) SHALL route `GET /`, `GET /api/crews*`, and `GET /static/*`
to `ga-radar:8080` via `reverse_proxy`. Session gating (`forward_auth`,
`/dashboard/login` redirect on 401) is unchanged — it runs at the Caddy layer
before the proxy.

#### Scenario: Unauthenticated request redirected to login

- **WHEN** `GET /` is requested without a valid `gs_session` cookie and `GA_API_KEY` is set
- **THEN** Caddy redirects the browser to `/dashboard/login?next=/`

#### Scenario: Authenticated request served by ga-radar

- **WHEN** `GET /` is requested with a valid `gs_session` cookie
- **THEN** Caddy proxies the request to `ga-radar:8080/`
- **THEN** the Radar SPA HTML is returned
