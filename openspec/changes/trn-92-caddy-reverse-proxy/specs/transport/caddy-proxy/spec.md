## Purpose

Manages a Caddy reverse-proxy container as an optional transport layer: generates its initial JSON config at install time, registers per-crew routes when a crew is launched, and removes them when a crew is nuked — all without downtime or Caddy restarts.

## ADDED Requirements

### Requirement: Caddy container lifecycle
When `GA_CADDY_ENABLED=true`, `install.sh` SHALL add a `ga-caddy` service to the generated `compose.yml`. The service SHALL expose exactly one public HTTPS port (default 443) and one HTTP port (default 80) for ACME HTTP-01 challenges and redirects. The Caddy admin API (port 2019) SHALL be bound to the internal `ga-net` network only and SHALL NOT be published to the host.

#### Scenario: Fresh install with Caddy enabled
- **WHEN** `install.sh` runs with `GA_CADDY_ENABLED=true`
- **THEN** `compose.yml` contains a `ga-caddy` service with the `caddy:2` image, ports `80:80` and `443:443`, and no `2019:2019` host mapping

#### Scenario: Fresh install with Caddy disabled
- **WHEN** `install.sh` runs with `GA_CADDY_ENABLED=false` (the default)
- **THEN** `compose.yml` does not contain a `ga-caddy` service and transport behavior is unchanged

### Requirement: Initial Caddy JSON configuration
`install.sh` SHALL write an `initial-config.json` under `DATA_DIR` that bootstraps Caddy with: a single HTTP server listening on port 443 (or configured port), MCP routes (`/mcp` prefix), file-transfer routes (`/files/` prefix), health route (`/health`), and an empty per-crew route list. The transport MAY forward `Authorization: Bearer` headers for MCP and file routes. The initial config SHALL be loaded into Caddy via `POST /load` on first start.

#### Scenario: Caddy starts with initial config
- **WHEN** the `ga-caddy` container starts for the first time
- **THEN** the Caddy entrypoint loads `initial-config.json` via `caddy run --config /config/initial-config.json`
- **THEN** `GET /health` on the configured port returns 200

### Requirement: Per-crew route registration
When a crew is successfully launched and `GA_CADDY_ENABLED=true`, the transport SHALL call `POST /config/apps/http/servers/ga/routes/.` on the Caddy admin API to append a route block that matches the path prefix `/crews/{crew_id}/ui/` and reverse-proxies to `gs-{crew_id}:5476`. The route block SHALL carry an `@id` field equal to `crew-{crew_id}` so it can be addressed directly for removal.

#### Scenario: Crew launch registers Caddy route
- **WHEN** `launch(crew_id="alpha")` completes successfully and Caddy is enabled
- **THEN** `GET /config/id/crew-alpha` on the Caddy admin API returns a route object with `match.path_regexp` or `match.path` targeting `/crews/alpha/ui/*`
- **THEN** the route upstream is `gs-alpha:5476`

#### Scenario: Crew launch without Caddy
- **WHEN** `launch(crew_id="alpha")` completes and `GA_CADDY_ENABLED=false`
- **THEN** no Caddy admin API calls are made

### Requirement: Per-crew route deregistration
When a crew is nuked and `GA_CADDY_ENABLED=true`, the transport SHALL call `DELETE /config/id/crew-{crew_id}` on the Caddy admin API to remove the corresponding route. Failure to contact the Caddy admin API SHALL be logged but SHALL NOT cause `nuke` to fail.

#### Scenario: Crew nuke removes Caddy route
- **WHEN** `nuke(crew_id="alpha", confirm=True)` is called and Caddy is enabled
- **THEN** `GET /config/id/crew-alpha` on the Caddy admin API returns 404 after nuke completes

#### Scenario: Caddy unreachable during nuke
- **WHEN** `nuke` is called and the Caddy admin API is unreachable
- **THEN** nuke completes and removes the crew from the registry
- **THEN** a warning is logged referencing the Caddy removal failure
