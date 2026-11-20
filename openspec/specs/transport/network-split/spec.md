# transport/network-split Specification

## Purpose

Defines the two-network topology that isolates the portal tier from crew containers, prevents crew containers from reaching `ga-portal`, and enforces an internal-only token check that prevents crew containers from accessing `ga-transport` MCP routes.

## Requirements

### Requirement: Network model — portside and shared starboard

The system SHALL replace `ga-net` with static `ga-portside` (portal/transport/Radar) and `ga-starboard` (transport/crews/logins). Portal/Radar SHALL NOT join starboard; crews/logins SHALL NOT join portside; workers use `netns: none`. Transport bridges both. Install SHALL create them idempotently as external networks. Define constants in `lifecycle.py`, import into `server.py`, and use no per-crew names.

#### Scenario: Portal cannot reach crew containers directly
- **WHEN** `ga-portal` attempts to connect to `gs-<crew_id>:5476` via DNS
- **THEN** the connection fails because crew hostnames are not resolvable from `ga-portside`

#### Scenario: Crew containers cannot reach ga-portal directly
- **WHEN** a crew container attempts to connect to `ga-portal` via DNS
- **THEN** the connection fails because `ga-portal` is not attached to `ga-starboard`

#### Scenario: Transport is reachable from portside
- **WHEN** `ga-portal` or `ga-radar` connects to `ga-transport:{PORT}`
- **THEN** the connection reaches Transport over `ga-portside`

#### Scenario: Transport is reachable from starboard
- **WHEN** a crew container connects to `ga-transport:{PORT}` on `ga-starboard`
- **THEN** the connection reaches Transport over `ga-starboard`

#### Scenario: Radar is isolated from crew containers
- **WHEN** `ga-radar` attempts to resolve or connect directly to a crew container
- **THEN** the connection fails because Radar is not attached to `ga-starboard`

#### Scenario: Crew container joins ga-starboard at creation
- **WHEN** `launch` creates a crew container
- **THEN** it is attached to `ga-starboard` and not to `ga-portside`

#### Scenario: Login container joins ga-starboard
- **WHEN** an ephemeral Kiro, Claude, or Codex login container is created
- **THEN** it is attached to `ga-starboard` and not to `ga-portside`

#### Scenario: Worker container joins no network
- **WHEN** a disposable worker container is created
- **THEN** it has `netns: none`

#### Scenario: Fresh install provisions both networks
- **WHEN** installation runs on a host where neither network exists
- **THEN** it creates ga-portside and ga-starboard and Compose declares both as external

#### Scenario: Network provisioning is idempotent
- **WHEN** installation runs again while both networks already exist
- **THEN** it completes without attempting to replace or recreate either network

### Requirement: GA_TRANSPORT_SECRET internal token

Install SHALL generate a 32-byte hex `GA_TRANSPORT_SECRET` as idempotent Podman secret `ga-transport-secret`, mounted in transport and passed to portal. Caddy SHALL inject it as `X-Transport-Token` on every upstream request to transport. Middleware SHALL load it at startup, fail safely if absent, populate `transport/config.py`, redact it from logs, and reject missing tokens with 401 before Bearer auth. Crew containers SHALL never receive it. `GA_API_KEY` remains optional client auth at Caddy.

#### Scenario: Request with correct portal token reaches transport

- **WHEN** Caddy proxies a request to `ga-transport` with `X-Transport-Token: <correct-value>`
- **THEN** the portal secret middleware allows the request to proceed to the next handler

#### Scenario: Request missing portal token is rejected

- **WHEN** any caller (including a crew container on ga-starboard) dials `ga-transport:{PORT}` without an `X-Transport-Token` header
- **THEN** the transport returns HTTP 401 — the request never reaches an MCP handler or `BearerAuthMiddleware`

#### Scenario: Request with wrong portal token is rejected

- **WHEN** a caller sends a request with `X-Transport-Token: <wrong-value>`
- **THEN** the transport returns HTTP 401

#### Scenario: Portal secret never appears in logs

- **WHEN** any transport log line is emitted during a request cycle
- **THEN** the value of `GA_TRANSPORT_SECRET` does not appear in the log output

#### Scenario: Transport fails to start if secret is absent

- **WHEN** `_load_transport_secret()` cannot read `/run/secrets/ga-transport-secret`
- **THEN** the transport raises `RuntimeError` with a safe error message (not the secret value) and refuses to start

### Requirement: install.sh provisions portside and starboard

`install.sh` SHALL create both networks idempotently and Compose SHALL declare them external; portal uses portside and transport both. Install SHALL create the secret only when absent and SHALL NOT create crew/login networks. It SHALL silently remove empty `ga-net` but keep it when containers remain.

#### Scenario: Fresh install creates both networks

- **WHEN** `install.sh` runs on a machine without `ga-portside` or `ga-starboard`
- **THEN** both networks are created and `compose.yml` references them as external

#### Scenario: Re-install is idempotent

- **WHEN** `install.sh` runs again with both networks already present
- **THEN** the script does not error

#### Scenario: compose.yml network assignments

- **WHEN** `install.sh` writes `compose.yml`
- **THEN** `ga-portal` declares only `ga-portside` in its `networks:` block
- **THEN** `ga-transport` declares `ga-portside` and `ga-starboard` in its `networks:` block
- **THEN** the top-level `networks:` block declares both as `{external: true}`

#### Scenario: Caddy config injects X-Transport-Token

- **WHEN** `install.sh` writes the Caddy config for `ga-portal`
- **THEN** every `reverse_proxy` directive targeting `ga-transport` includes `header_up X-Transport-Token {env.GA_TRANSPORT_SECRET}`
