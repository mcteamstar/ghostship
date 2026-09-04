## Purpose

Defines the two-network topology that isolates crew containers from the portal, preventing direct crew-to-transport connections that would bypass Caddy's authentication layer. `ga-transport` bridges both networks; no other container spans them.

## ADDED Requirements

### Requirement: Two-network model

The system SHALL provision two Podman networks — `ga-portside` and `ga-starboard` — replacing the single `ga-net` network.

- `ga-portside` SHALL be used exclusively by `ga-portal` and `ga-transport`. No `gs-*` crew container, login container, or worker container SHALL be attached to `ga-portside`.
- `ga-starboard` SHALL be used by `ga-transport`, `gs-*` crew containers, and `ga-login-*` ephemeral login containers. `ga-portal` SHALL NOT be attached to `ga-starboard`.
- `ga-transport` SHALL be attached to both `ga-portside` and `ga-starboard` simultaneously, acting as the sole bridge between the two network segments.

#### Scenario: Portal cannot reach crew containers directly

- **WHEN** `ga-portal` attempts to connect to `gs-<crew_id>:5476` via DNS
- **THEN** the connection fails — `gs-*` hostnames are not resolvable from `ga-portside`

#### Scenario: Crew containers cannot reach ga-portal directly

- **WHEN** a `gs-*` crew container attempts to connect to `ga-portal` via DNS
- **THEN** the connection fails — `ga-portal` hostname is not resolvable from `ga-starboard`

#### Scenario: Transport is reachable from both segments

- **WHEN** `ga-portal` dials `ga-transport:{PORT}` (portside)
- **THEN** the connection succeeds

- **WHEN** `gs-<crew_id>` dials `ga-transport:{PORT}` (starboard)
- **THEN** the connection fails — crew containers MUST NOT be able to reach `ga-transport` directly; see the starboard isolation requirement below

#### Scenario: Transport is reachable by ga-portal on portside

- **WHEN** `ga-portal` reverse-proxies to `ga-transport:{PORT}`
- **THEN** Caddy can reach `ga-transport` over `ga-portside` DNS

### Requirement: Starboard isolation of transport

Crew containers SHALL be able to reach `ga-transport` only indirectly — via `ga-portal` on `ga-portside`, which enforces Bearer-token auth. A crew container on `ga-starboard` SHALL NOT be able to dial `ga-transport:{PORT}` and bypass Caddy's auth layer.

**Note on Podman per-network DNS**: Podman assigns each container a separate DNS entry for each network it joins. `ga-transport` joined on `ga-starboard` will be resolvable as `ga-transport` from crew containers on that network. The starboard isolation requirement is therefore enforced at the application layer (transport MUST reject unauthenticated requests from any caller) rather than at the network layer alone. The two-network split prevents `ga-portal` from reaching crew containers and prevents crew containers from reaching `ga-portal` directly; the transport's own `BearerAuthMiddleware` enforces auth for all callers.

#### Scenario: Transport rejects unauthenticated requests regardless of caller network

- **WHEN** a crew container dials `ga-transport:{PORT}/mcp` without a valid Bearer token and `GA_API_KEY` is set
- **THEN** the transport returns 401 — the request never reaches an MCP handler

#### Scenario: Portal-mediated path enforces auth at the edge

- **WHEN** an external client dials `ga-portal` without a valid Bearer token
- **THEN** Caddy returns 401 before the request reaches `ga-transport`

### Requirement: Network assignment rules

The following SHALL govern which network each container type joins:

| Container | Network(s) |
|---|---|
| `ga-portal` | `ga-portside` only |
| `ga-transport` | `ga-portside` AND `ga-starboard` |
| `gs-<crew_id>` (crew) | `ga-starboard` only |
| `ga-login-<token>` (ephemeral) | `ga-starboard` only |
| `gs-worker-<token>` (disposable) | none (`netns: none`) |

These assignments SHALL be enforced at container-create time and SHALL NOT be alterable via environment variable or config file at runtime.

#### Scenario: Crew container joins starboard only

- **WHEN** `launch` creates a `gs-<crew_id>` container
- **THEN** `podman inspect gs-<crew_id>` shows the container attached to `ga-starboard` and NOT attached to `ga-portside`

#### Scenario: Login container joins starboard only

- **WHEN** `_start_login_container` creates a `ga-login-*` container
- **THEN** the container is attached to `ga-starboard` and NOT attached to `ga-portside`

#### Scenario: Worker container joins no network

- **WHEN** `worker_run` creates a `gs-worker-*` container
- **THEN** the container has `netns: none` — unchanged from current behaviour

### Requirement: install.sh provisions both networks

`install.sh` SHALL create both `ga-portside` and `ga-starboard` networks (idempotent — no error if they already exist) and SHALL remove any pre-existing `ga-net` network only if it has no attached containers. `compose.yml` SHALL declare both networks as external and attach `ga-transport` to both and `ga-portal` to `ga-portside` only.

#### Scenario: Fresh install creates both networks

- **WHEN** `install.sh` runs on a machine with neither `ga-portside` nor `ga-starboard`
- **THEN** both networks are created and the compose.yml network block references them as external

#### Scenario: Re-install is idempotent

- **WHEN** `install.sh` runs again with both networks already present
- **THEN** the script does not error and does not recreate the networks

#### Scenario: compose.yml dual-network transport

- **WHEN** `install.sh` writes `compose.yml`
- **THEN** `ga-transport` declares both `ga-portside` and `ga-starboard` in its `networks:` block
- **THEN** `ga-portal` declares only `ga-portside` in its `networks:` block

### Requirement: Migration of existing crews on startup

When the transport starts and `_reconcile_registry` runs, it SHALL detect any running crew container that is attached to `ga-net` but NOT attached to `ga-starboard`. For each such container the transport SHALL:

1. Stop the container
2. Disconnect it from `ga-net` (if the network still exists)
3. Connect it to `ga-starboard`
4. Start the container
5. Wait for the gateway to become ready
6. Refresh the session cookie

If migration of a specific crew fails, the transport SHALL log a warning, mark that crew `stopped` in the registry, and continue migrating remaining crews. The transport SHALL NOT refuse to start because of migration failures.

#### Scenario: Existing crew on ga-net is migrated

- **WHEN** the transport starts and a crew container is attached to `ga-net` but not `ga-starboard`
- **THEN** the container is reconnected to `ga-starboard` and its registry status is `running` after migration

#### Scenario: Migration failure does not block startup

- **WHEN** migration of one crew fails (e.g. container refuses to restart)
- **THEN** the transport logs a warning, marks that crew `stopped`, and proceeds to start serving requests

#### Scenario: Already-migrated crew is skipped

- **WHEN** the transport starts and a crew container is already attached to `ga-starboard`
- **THEN** no migration action is taken for that crew
