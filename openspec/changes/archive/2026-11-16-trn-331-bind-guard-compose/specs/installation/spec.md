# Spec Delta

## MODIFIED Requirements

### Requirement: HOST controls only the Caddy host bind address

`HOST` (`network.host`) SHALL set only the host address `ga-portal` publishes on, for both `PORT` and the dashboard port range. It SHALL default to `127.0.0.1`. The transport container SHALL always listen on `0.0.0.0` internally, whatever `HOST` is, and Caddy's upstream dial strings SHALL remain `ga-transport:64057`. `docs/configuration.md` and `README.md` SHALL describe the loopback-only default and distinguish the portal host bind from the transport's in-container listen address.

#### Scenario: Default install is reachable only from the local machine
- **WHEN** `install.sh` regenerates `compose.yml` with `HOST` unset
- **THEN** `ga-portal` publishes `PORT` and the dashboard port range on `127.0.0.1` only
- **AND** the transport container listens on `0.0.0.0` inside its container
- **AND** the README and configuration docs state that the default portal bind is loopback-only

#### Scenario: Loopback HOST still reaches the transport through the portal
- **WHEN** `HOST=127.0.0.1` and a client on the host requests `http://localhost:{PORT}/mcp`
- **THEN** Caddy proxies the request to `ga-transport:64057` and the transport answers it, with no `502` from a refused upstream connection

#### Scenario: Custom HOST changes only the portal bind
- **WHEN** `HOST=192.168.1.10` is set and `install.sh` regenerates `compose.yml`
- **THEN** `ga-portal` publishes `PORT` and the dashboard port range on `192.168.1.10`
- **AND** the transport container's listen address remains `0.0.0.0`
- **AND** Caddy's upstream dial string remains `ga-transport:64057`

#### Scenario: Wildcard HOST exposes the portal on all interfaces
- **WHEN** `HOST=0.0.0.0` is set and `install.sh` regenerates `compose.yml`
- **THEN** `ga-portal` publishes `PORT` and the dashboard port range on all host interfaces
