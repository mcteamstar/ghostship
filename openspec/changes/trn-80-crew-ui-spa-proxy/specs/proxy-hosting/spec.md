# proxy-hosting Specification (delta)

## MODIFIED Requirements

### Modified Requirement: Crew UI access

The crew UI is now served via dedicated per-port listeners on the transport itself. Each crew gets a port in the range `[GA_UI_PORT_RANGE_START, GA_UI_PORT_RANGE_START + GA_UI_PORT_RANGE_SIZE)`. All requests on that port are reverse-proxied by the transport to the crew gateway over the internal ghost-academy Podman network. Crew containers do not bind any host ports. Full behavior specified in `crew-ui-spa-routing/spec.md`.

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
