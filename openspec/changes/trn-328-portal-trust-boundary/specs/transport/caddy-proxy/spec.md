# Spec Delta

## MODIFIED Requirements

### Requirement: `ga-portal` is always present

`ga-portal` SHALL always be included in the generated `compose.yml` and started by `install.sh`. There is no opt-out flag. The `GA_PORTAL_ENABLED` environment variable is removed and SHALL NOT be read or honoured. The service SHALL bind `GA_PORTAL_PORT` (default 64057) AND the dashboard port range (default 64058–64107) — Caddy owns those port bindings, not the transport. The Caddy admin API SHALL use a Unix-domain socket shared only with `ga-transport` and SHALL NOT be exposed on a TCP listener or published to the host. The `ga-transport` service SHALL NOT bind the dashboard port range. `ga-portal` SHALL be attached to `ga-portside` only and SHALL NOT be attached to `ga-starboard`.

#### Scenario: Install always starts ga-portal
- **WHEN** `install.sh` runs
- **THEN** `compose.yml` always contains a `ga-portal` service
- **THEN** `ga-portal` is started alongside `ga-transport`

#### Scenario: Fresh install includes Caddy config
- **WHEN** `install.sh` runs
- **THEN** `compose.yml` contains a `ga-portal` service with the `caddy:2` image, `GA_PORTAL_PORT` and the dashboard range bound, and no `2019:2019` port mapping
- **THEN** the `ga-transport` service does not bind the dashboard port range
- **THEN** `ga-portal` and `ga-transport` share the Caddy admin socket directory
- **THEN** no other service mounts the Caddy admin socket directory

## REMOVED Requirements

### Requirement: Caddy admin API restricted to transport-origin requests
**Reason**: An HTTP `Origin` allowlist is not caller authentication and must not be relied on to protect Caddy's configuration API from another container on the same network.
**Migration**: Use a permissioned Unix-domain socket mounted only into `ga-portal` and `ga-transport`; Transport connects to the socket directly. Caddy's public listeners and network topology remain unchanged.

## ADDED Requirements

### Requirement: Caddy admin API is accessible only to Transport
The Caddy admin API SHALL listen on a Unix-domain socket in a directory shared by `ga-portal` and `ga-transport`. Filesystem permissions on the socket SHALL allow the Transport process to connect. The admin API SHALL NOT listen on a TCP address. `ga-radar` and crew containers SHALL NOT receive a mount of the socket directory. Caddy origin or host checks SHALL NOT be treated as authentication for admin API callers.

#### Scenario: Transport manages dashboard routes through the socket
- **WHEN** Transport registers, removes, or reconciles a crew dashboard route
- **THEN** its admin API request reaches Caddy through the shared Unix-domain socket and Caddy applies the change

#### Scenario: Radar cannot reach the Caddy admin API
- **WHEN** Radar attempts to connect to the Caddy admin API
- **THEN** it has no mounted socket and no TCP admin listener is available to it
- **THEN** the request cannot change Caddy configuration

#### Scenario: Public Caddy listeners remain available
- **WHEN** the admin API is moved to a Unix-domain socket
- **THEN** the portal listener and per-crew dashboard listeners remain available on their configured host ports

#### Scenario: Admin API is not published to the host
- **WHEN** the generated Compose configuration is inspected
- **THEN** no host port mapping exposes the Caddy admin API
