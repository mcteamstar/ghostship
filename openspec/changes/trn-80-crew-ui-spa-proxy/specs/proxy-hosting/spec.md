# proxy-hosting Specification (delta)

## MODIFIED Requirements

### Modified Requirement: Crew UI access

The crew UI is now served directly on a dedicated host port per crew (see `crew-ui-spa-routing/spec.md`) rather than via a path-prefix proxy. The existing Python-layer `_handle_crew_ui_proxy` is removed from the default code path and retained only as a fallback behind `GA_UI_PORT_ENABLED=false`.

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
