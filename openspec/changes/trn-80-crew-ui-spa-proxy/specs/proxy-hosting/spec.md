# proxy-hosting Specification (delta)

## MODIFIED Requirements

### Modified Requirement: Crew UI reverse proxy

The existing crew UI proxy requirement is updated. The transport SHALL delegate crew UI routing to Caddy rather than handling it in the Python layer when `GA_CADDY_UI_ENABLED=true`. The Caddy route performs path-prefix stripping and full reverse proxying including WebSocket support. Full behavior is specified in `crew-ui-spa-routing/spec.md`.

When `GA_CADDY_UI_ENABLED=false`, the existing Python-layer `_handle_crew_ui_proxy` behavior is retained unchanged.

### New Requirement: Transport origin added to crew CORS origins at start

The transport SHALL inject its own public origin (the base of `GA_HOST_URL`, or `http://localhost:{PORT}` when `GA_HOST_URL` is unset) into the `KIROCREW_CORS_ORIGINS` environment variable when starting a crew container. This ensures the crew gateway accepts browser requests that originate from the transport's public URL.

#### Scenario: CORS origin injected when GA_HOST_URL is set
- **WHEN** a crew container is started and `GA_HOST_URL=https://academy.example.com`
- **THEN** `KIROCREW_CORS_ORIGINS` passed to the container includes `https://academy.example.com`

#### Scenario: CORS origin injected when GA_HOST_URL is unset
- **WHEN** a crew container is started and `GA_HOST_URL` is not set
- **THEN** `KIROCREW_CORS_ORIGINS` passed to the container includes `http://localhost:{PORT}`

#### Scenario: Existing CORS origins are preserved
- **WHEN** `KIROCREW_CORS_ORIGINS` is already set (e.g. from a crew composition config)
- **THEN** the transport appends its public origin to the existing value rather than replacing it
