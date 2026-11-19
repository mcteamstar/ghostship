# Spec Delta

## MODIFIED Requirements

### Requirement: Network model — portside and shared starboard

The system SHALL provision two static Podman networks replacing `ga-net`:

- `ga-portside` — used by `ga-portal`, `ga-transport`, and `ga-radar`. Crew, login, and worker containers SHALL NOT be attached to `ga-portside`.
- `ga-starboard` — used by `ga-transport` and all `gs-*` crew containers. `ga-portal` and `ga-radar` SHALL NOT be attached to `ga-starboard`.

`ga-transport` SHALL be attached to both `ga-portside` and `ga-starboard` at all times, bridging the portal and crew tiers. Both networks are static install-time networks and are not created or destroyed at crew launch or nuke time.

The install process SHALL create both networks idempotently and declare them as external in Compose.

Network assignments:

| Container | Network(s) |
|---|---|
| `ga-portal` | `ga-portside` only |
| `ga-radar` | `ga-portside` only |
| `ga-transport` | `ga-portside` + `ga-starboard` |
| `gs-{crew_id}` (crew) | `ga-starboard` only |
| `ga-login-{token}` (ephemeral) | `ga-starboard` |
| `gs-worker-{token}` (disposable) | none (`netns: none`) |

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
- **WHEN** an ephemeral login container is created
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
