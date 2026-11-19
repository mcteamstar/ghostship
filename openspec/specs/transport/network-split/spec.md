# transport/network-split Specification

## Purpose

Defines the two-network topology that isolates the portal tier from crew containers, prevents crew containers from reaching `ga-portal`, and enforces an internal-only token check that prevents crew containers from accessing `ga-transport` MCP routes.

## Requirements

### Requirement: Network model — portside and shared starboard

The system SHALL provision two static Podman networks replacing `ga-net`:

- `ga-portside` — used by `ga-portal`, `ga-transport`, and `ga-radar`. Crew, login, and worker containers SHALL NOT be attached to `ga-portside`.
- `ga-starboard` — used by `ga-transport`, all `gs-*` crew containers, and ephemeral Kiro (`ga-login-*`), Claude (`ga-claude-login-*`), and Codex (`ga-codex-login-*`) login containers. `ga-portal` and `ga-radar` SHALL NOT be attached to `ga-starboard`; disposable workers use `netns: none`.

`ga-transport` SHALL be attached to both `ga-portside` and `ga-starboard` at all times, bridging the portal and crew tiers. Both networks are static install-time networks and are not created or destroyed at crew launch or nuke time.

The install process SHALL create both networks idempotently and declare them as external in Compose.

Network assignments:

| Container | Network(s) |
|---|---|
| `ga-portal` | `ga-portside` only |
| `ga-radar` | `ga-portside` only |
| `ga-transport` | `ga-portside` + `ga-starboard` |
| `gs-{crew_id}` (crew) | `ga-starboard` only |
| `ga-login-*` (Kiro), `ga-claude-login-*`, `ga-codex-login-*` (ephemeral) | `ga-starboard` only |
| `gs-worker-{token}` (disposable) | none (`netns: none`) |


The constants `GA_PORTSIDE_NETWORK = "ga-portside"` and `GA_STARBOARD_NETWORK = "ga-starboard"` SHALL be defined in `lifecycle.py` and imported by `server.py`. No dynamic per-crew network naming function is needed.

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

The system SHALL generate an internal secret `GA_TRANSPORT_SECRET` at install time. This token SHALL be the primary control preventing crew containers on `ga-starboard` from accessing `ga-transport` MCP and API routes.

**Generation and storage:**
- Generated at install time: `openssl rand -hex 32`
- Written as Podman secret `ga-transport-secret`
- Mounted into `ga-transport` at `/run/secrets/ga-transport-secret`
- Injected into `ga-portal` as environment variable `GA_TRANSPORT_SECRET`
- `GA_TRANSPORT_SECRET` generation SHALL be idempotent at re-install (skip if secret already exists)

**Caddy config (`ga-portal`):**
- SHALL add `header_up X-Transport-Token {env.GA_TRANSPORT_SECRET}` to ALL upstream requests to `ga-transport`, including MCP, files, dashboard, and health routes — every route without exception

**Transport middleware:**
- SHALL reject any request missing the `X-Transport-Token` header with HTTP 401 before `BearerAuthMiddleware` runs
- SHALL load the secret at startup via `_load_transport_secret()` — same pattern as `_load_api_key()`: reads from `/run/secrets/ga-transport-secret`, raises `RuntimeError` with a safe message if absent
- SHALL register the secret value with the log redaction filter so it never appears in logs
- `transport/config.py` SHALL gain a `ga_transport_secret` field populated by `_load_transport_secret()`

**Crew containers on `ga-starboard` SHALL NOT receive `GA_TRANSPORT_SECRET` in any form** — neither as an environment variable, a mounted secret, nor via any other mechanism.

**GA_API_KEY** remains optional and is a separate concern — external client auth at the Caddy edge only. This requirement does not alter `GA_API_KEY` behaviour.

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

`install.sh` SHALL create both `ga-portside` and `ga-starboard` (each idempotent). `compose.yml` SHALL declare both as external. `ga-portal` is assigned to `ga-portside`; `ga-transport` is assigned to both `ga-portside` and `ga-starboard`. Per-crew or per-login networks are NOT created by `install.sh` and are NOT in `compose.yml`.

`install.sh` SHALL generate `GA_TRANSPORT_SECRET` and write it as the `ga-transport-secret` Podman secret. This step SHALL be idempotent — if the secret already exists with the correct name, do not regenerate it.

`install.sh` SHALL also include a best-effort `ga-net` cleanup step: if `ga-net` exists and has no containers, remove it silently; skip if it has containers.

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

