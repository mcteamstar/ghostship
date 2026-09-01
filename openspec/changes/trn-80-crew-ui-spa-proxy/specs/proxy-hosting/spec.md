# proxy-hosting Specification (delta)

## ADDED Requirements

### Requirement: Transport origin added to crew CORS origins at start

The transport SHALL inject its own public origin (the base of `GA_HOST_URL`, or `http://localhost:{PORT}` when `GA_HOST_URL` is unset) into the `KIROCREW_CORS_ORIGINS` environment variable when starting a crew container. This ensures the crew gateway accepts browser requests that originate from the transport's public URL after an initial `/crews/{id}/ui/` page load.

#### Scenario: CORS origin injected when GA_HOST_URL is set
- **WHEN** a crew container is started and `GA_HOST_URL=https://academy.example.com`
- **THEN** `KIROCREW_CORS_ORIGINS` passed to the container includes `https://academy.example.com`

#### Scenario: CORS origin injected when GA_HOST_URL is unset
- **WHEN** a crew container is started and `GA_HOST_URL` is not set
- **THEN** `KIROCREW_CORS_ORIGINS` passed to the container includes `http://localhost:{PORT}`

#### Scenario: Existing CORS origins are preserved
- **WHEN** `KIROCREW_CORS_ORIGINS` is already set (e.g. from a crew composition config)
- **THEN** the transport appends its public origin to the existing value rather than replacing it

### Requirement: Root-absolute SPA asset requests re-routed through crew UI proxy

The transport SHALL handle `GET` requests for root-absolute paths that do not match any existing transport route by routing them through the crew UI proxy when the request can be attributed to an originating crew (via `Referer` header or `crew_ui_context` cookie). Full behavior and scenarios are specified in `crew-ui-spa-routing/spec.md`.

#### Scenario: SPA asset request routed to originating crew
- **WHEN** a browser fetches `/static/app.js` after loading `/crews/my-crew/ui/`
- **AND** the `Referer` header points to `/crews/my-crew/ui/`
- **THEN** the transport proxies the request to `http://gs-my-crew:5476/static/app.js`

#### Scenario: SPA asset request with no crew context returns 404
- **WHEN** a `GET /static/app.js` request has no `Referer` matching a crew UI path and no `crew_ui_context` cookie
- **THEN** the transport returns HTTP 404
