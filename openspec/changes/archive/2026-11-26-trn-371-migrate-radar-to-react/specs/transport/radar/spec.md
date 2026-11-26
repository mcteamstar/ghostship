# Spec Delta

## MODIFIED Requirements

### Requirement: ga-radar serves the Radar SPA and fleet API

`ga-radar` SHALL serve the SPA and static assets, proxy fleet and per-crew agent data to `ga-transport`, and expose unauthenticated `/health`. The SPA SHALL be a bundle built at image build time and baked into the image; it polls fleet data every five seconds and fetches live tasks when a row expands.

#### Scenario: SPA served at root

- **WHEN** `GET /` is requested through Caddy with a valid session
- **THEN** `ga-radar` returns HTTP 200 with `Content-Type: text/html`
- **THEN** the response body is the built `index.html`

#### Scenario: Static assets served

- **WHEN** an asset referenced by the built `index.html` under `/static/` is requested
- **THEN** `ga-radar` returns the asset with the correct content-type

#### Scenario: Removed source modules not served

- **WHEN** `GET /static/main.js`, `GET /static/render.js` or `GET /static/app.js` is requested
- **THEN** `ga-radar` returns HTTP 404

#### Scenario: Fleet API proxied to transport

- **WHEN** `GET /api/crews` is requested
- **THEN** `ga-radar` calls `GET http://ga-transport:64057/internal/crews` with `X-Transport-Token`
- **THEN** the response payload is returned to the browser unchanged

#### Scenario: Per-crew agents endpoint proxied to transport

- **WHEN** `GET /api/crews/{crew_id}/agents` is requested with a valid session
- **THEN** `ga-radar` calls `GET http://ga-transport:64057/internal/crews/{crew_id}/agents` with `X-Transport-Token`
- **THEN** the response `{"agents": [...]}` is returned to the browser
- **THEN** if the crew is stopped or gateway unreachable, `{"agents": []}` is returned with HTTP 200

#### Scenario: Health endpoint needs no auth

- **WHEN** `GET /health` is requested without any credentials
- **THEN** `ga-radar` returns HTTP 200 `{"status": "ok"}`

## ADDED Requirements

### Requirement: Radar bundle is built in the image build

The `ga-radar` image build, run by `./install.sh` and `ghostship upgrade`, SHALL compile the SPA from source in a build stage and copy only the built output into the runtime image. The host SHALL need no Node. The runtime image SHALL NOT contain Node, the package manager or the frontend source tree.

#### Scenario: Runtime image contents
- **WHEN** the `ga-radar` image is built from `radar/Containerfile`
- **THEN** the runtime image holds the built bundle and the Python service, and no Node runtime or `node_modules`

#### Scenario: Build fails on a broken frontend
- **WHEN** the frontend type check or bundle build fails
- **THEN** the image build fails instead of producing an image with a stale or partial bundle

#### Scenario: Install on a host without Node
- **WHEN** an operator runs `./install.sh` or `ghostship upgrade` on a host with Podman and no Node
- **THEN** the `ga-radar` image is built with the bundle included

#### Scenario: Package registry unreachable
- **WHEN** the build cannot fetch frontend packages
- **THEN** the installer reports that the Radar bundle build failed and why, and the previously built `ga-radar` image is left in place

### Requirement: Radar assets use a safe cache policy

`ga-radar` SHALL answer `GET /` with `Cache-Control: no-cache` so each load revalidates. It SHALL serve content-hashed assets under `/static/` as long-lived and immutable, and SHALL serve any other static file with `no-cache`.

#### Scenario: Index revalidated
- **WHEN** `GET /` is requested
- **THEN** the response carries `Cache-Control: no-cache`

#### Scenario: Hashed asset cached
- **WHEN** a content-hashed asset under `/static/` is requested
- **THEN** the response carries a long-lived `immutable` cache policy

#### Scenario: Upgrade does not mix versions
- **WHEN** Radar is upgraded while a browser holds an older bundle
- **THEN** the next page load uses the new `index.html` and its new hashed assets, and never loads an old asset with a new page

### Requirement: Radar unknown paths do not fall back to the SPA for API routes

`ga-radar` SHALL return HTTP 404 for an unknown path under `/api/` or `/static/` and SHALL NOT answer it with `index.html`.

#### Scenario: Unknown API path
- **WHEN** `GET /api/unknown` is requested
- **THEN** `ga-radar` returns HTTP 404 with a non-HTML body

#### Scenario: Missing static asset
- **WHEN** `GET /static/assets/missing.js` is requested
- **THEN** `ga-radar` returns HTTP 404
