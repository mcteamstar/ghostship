## Purpose

Defines the per-crew network topology that isolates each crew container onto its own private network, preventing direct crew-to-crew communication and crew-to-portal communication. `ga-transport` bridges the portal tier (`ga-portside`) and each per-crew network (`ga-crew-{crew_id}`). Opt-in peering allows the Admiral to explicitly wire crews together when needed.

## ADDED Requirements

### Requirement: Network model — portside plus per-crew

The system SHALL provision one fixed Podman network (`ga-portside`) replacing `ga-net`, plus one dynamic Podman network per crew (`ga-crew-{crew_id}`) created at launch and removed at nuke.

- `ga-portside` SHALL be used exclusively by `ga-portal` and `ga-transport`. No `gs-*` crew container, login container, or worker container SHALL be attached to `ga-portside`.
- Each `ga-crew-{crew_id}` network SHALL be used by `ga-transport` and its corresponding `gs-{crew_id}` crew container only. No other crew container and no `ga-portal` container SHALL be attached to `ga-crew-{crew_id}` unless explicitly peered.
- `ga-transport` SHALL be attached to `ga-portside` at all times, and SHALL be dynamically connected to each `ga-crew-{crew_id}` network when a crew is launched and disconnected when a crew is nuked.
- Per-crew network names SHALL be computed as `f"ga-crew-{crew_id}"` — there is no single static `GA_STARBOARD_NETWORK` constant.

#### Scenario: Portal cannot reach crew containers directly

- **WHEN** `ga-portal` attempts to connect to `gs-<crew_id>:5476` via DNS
- **THEN** the connection fails — `gs-*` hostnames are not resolvable from `ga-portside`

#### Scenario: Crew containers cannot reach ga-portal directly

- **WHEN** a `gs-*` crew container attempts to connect to `ga-portal` via DNS
- **THEN** the connection fails — `ga-portal` hostname is not resolvable from `ga-crew-{crew_id}`

#### Scenario: Crew containers cannot reach each other by default

- **WHEN** `gs-alpha` attempts to connect to `gs-beta:5476` via DNS
- **THEN** the connection fails — `gs-beta` is not on `ga-crew-alpha` and is not resolvable from it

#### Scenario: Transport is reachable from portside

- **WHEN** `ga-portal` reverse-proxies to `ga-transport:{PORT}`
- **THEN** Caddy can reach `ga-transport` over `ga-portside` DNS

#### Scenario: Transport is reachable from each per-crew network

- **WHEN** `gs-<crew_id>` dials `ga-transport:{PORT}` on `ga-crew-{crew_id}`
- **THEN** the connection reaches `ga-transport` — `ga-transport` is attached to that network and is DNS-resolvable from it

### Requirement: Auth enforcement on per-crew transport access

Crew containers on `ga-crew-{crew_id}` SHALL be able to dial `ga-transport:{PORT}`. This is unavoidable with Podman rootless DNS. The transport SHALL enforce Bearer-token authentication on all non-exempt routes, regardless of which network the caller is on.

**Note on Podman per-network DNS**: `ga-transport` joined on `ga-crew-{crew_id}` will be resolvable as `ga-transport` from that crew's container. The isolation benefit of per-crew networks is that each crew is on its own private segment, not a shared flat network — crews cannot reach each other, and the threat surface is bounded per-crew rather than fleet-wide. The transport's own `BearerAuthMiddleware` enforces auth for all callers.

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
| `ga-transport` | `ga-portside` + `ga-crew-{id}` for each active crew |
| `gs-{crew_id}` (crew) | `ga-crew-{crew_id}` only (plus any opted-in peer networks) |
| `ga-login-{token}` (ephemeral) | `ga-crew-{crew_id}` for the crew being authenticated |
| `gs-worker-{token}` (disposable) | none (`netns: none`) |

These assignments SHALL be enforced at container-create time. The `GA_PORTSIDE_NETWORK` constant SHALL be defined for the static portside network; per-crew network names SHALL be computed dynamically as `f"ga-crew-{crew_id}"` and SHALL NOT be assigned via environment variable or config file.

#### Scenario: Crew container joins only its own network

- **WHEN** `launch` creates a `gs-{crew_id}` container
- **THEN** `podman inspect gs-{crew_id>` shows the container attached to `ga-crew-{crew_id}` and NOT attached to `ga-portside` or any other crew's network (unless peered)

#### Scenario: Login container joins the correct per-crew network

- **WHEN** `_start_login_container` creates a `ga-login-*` container for crew `{crew_id}`
- **THEN** the container is attached to `ga-crew-{crew_id}` and NOT attached to `ga-portside`

#### Scenario: Worker container joins no network

- **WHEN** `worker_run` creates a `gs-worker-*` container
- **THEN** the container has `netns: none` — unchanged from current behaviour

### Requirement: Per-crew network lifecycle

The system SHALL create and destroy `ga-crew-{crew_id}` networks as part of the crew lifecycle, not at install time.

**launch SHALL:**
1. Create `ga-crew-{crew_id}` (idempotent — no error if it already exists).
2. Connect `ga-transport` to `ga-crew-{crew_id}` via `network_connect`.
3. Create the `gs-{crew_id}` container with `networks=["ga-crew-{crew_id}"]`.
4. If `peer_crews` is specified, connect `gs-{crew_id}` to each `ga-crew-{peer_id}` network.

**nuke SHALL:**
1. Stop and remove the `gs-{crew_id}` container.
2. Disconnect `ga-transport` from `ga-crew-{crew_id}` via `network_disconnect` (best-effort).
3. Remove `ga-crew-{crew_id}` (best-effort — log warning on failure, never raise).

#### Scenario: Network created at launch

- **WHEN** `launch("alpha")` is called
- **THEN** the network `ga-crew-alpha` exists and `ga-transport` is attached to it

#### Scenario: Network removed at nuke

- **WHEN** `nuke("alpha")` is called
- **THEN** `ga-transport` is disconnected from `ga-crew-alpha` and the network is removed (best-effort)

### Requirement: Opt-in crew-to-crew peering via `peer_crews`

`launch()` SHALL accept an optional `peer_crews: list[str]` parameter (default: empty). When `peer_crews` is non-empty, the launched crew's container SHALL also be connected to each named peer's `ga-crew-{peer_id}` network after creation. This allows the Admiral to explicitly wire crews together.

- Peering is one-directional from the launched crew's perspective: `gs-new` is connected to `ga-crew-peer`, but `gs-peer` is NOT automatically connected to `ga-crew-new`.
- If a named peer's network does not exist at launch time, the system SHALL log a warning and skip that peer rather than failing the launch.
- `peer_crews` SHALL NOT be alterable after launch without a nuke/relaunch.

#### Scenario: Peered crew can reach peer by hostname

- **WHEN** `launch("coordinator", peer_crews=["worker-a", "worker-b"])` is called
- **THEN** `gs-coordinator` is attached to `ga-crew-coordinator`, `ga-crew-worker-a`, and `ga-crew-worker-b`
- **THEN** `gs-coordinator` can resolve and dial `gs-worker-a:5476` and `gs-worker-b:5476`

#### Scenario: Peer crew is not automatically aware of the new crew

- **WHEN** `launch("coordinator", peer_crews=["worker-a"])` is called
- **THEN** `gs-worker-a` is NOT attached to `ga-crew-coordinator` and cannot resolve `gs-coordinator` unless `gs-worker-a` was also launched with `peer_crews=["coordinator"]`

#### Scenario: Missing peer network is skipped with a warning

- **WHEN** `launch("coordinator", peer_crews=["nonexistent"])` is called and `ga-crew-nonexistent` does not exist
- **THEN** launch succeeds, a warning is logged, and `gs-coordinator` is NOT attached to `ga-crew-nonexistent`

### Requirement: install.sh provisions portside only

`install.sh` SHALL create `ga-portside` (idempotent) and SHALL remove any pre-existing `ga-net` network only if it has no attached containers. Per-crew networks are NOT created by `install.sh`. `compose.yml` SHALL declare `ga-portside` as external and attach both `ga-transport` and `ga-portal` to `ga-portside`; there is no static per-crew entry in compose.yml.

#### Scenario: Fresh install creates portside network

- **WHEN** `install.sh` runs on a machine without `ga-portside`
- **THEN** `ga-portside` is created and `compose.yml` references it as external

#### Scenario: Re-install is idempotent

- **WHEN** `install.sh` runs again with `ga-portside` already present
- **THEN** the script does not error and does not recreate the network

#### Scenario: compose.yml portside-only transport

- **WHEN** `install.sh` writes `compose.yml`
- **THEN** `ga-transport` declares only `ga-portside` in its `networks:` block (per-crew networks are attached dynamically)
- **THEN** `ga-portal` declares only `ga-portside` in its `networks:` block

### Requirement: Migration of existing crews on startup

When the transport starts and `_reconcile_registry` runs, it SHALL detect any running crew container that is attached to `ga-net` but NOT attached to its `ga-crew-{crew_id}` network. For each such container the transport SHALL:

1. Create `ga-crew-{crew_id}` (idempotent).
2. Connect `ga-transport` to `ga-crew-{crew_id}`.
3. Stop the container.
4. Disconnect it from `ga-net` (best-effort — `ga-net` may already be absent).
5. Connect it to `ga-crew-{crew_id}`.
6. Start the container.
7. Wait for the gateway to become ready.
8. Refresh the session cookie.

If migration of a specific crew fails, the transport SHALL log a warning, mark that crew `stopped` in the registry, and continue migrating remaining crews. The transport SHALL NOT refuse to start because of migration failures.

After all crews are processed, if `ga-net` exists and has no attached containers, the transport SHALL attempt `podman network rm ga-net` (best-effort — log warning on failure, never raise).

#### Scenario: Existing crew on ga-net is migrated to its own network

- **WHEN** the transport starts and `gs-alpha` is attached to `ga-net` but not `ga-crew-alpha`
- **THEN** `ga-crew-alpha` is created, `ga-transport` is connected to it, `gs-alpha` is reconnected to `ga-crew-alpha`, and its registry status is `running` after migration

#### Scenario: Migration failure does not block startup

- **WHEN** migration of one crew fails (e.g. container refuses to restart)
- **THEN** the transport logs a warning, marks that crew `stopped`, and proceeds to start serving requests

#### Scenario: Already-migrated crew is skipped

- **WHEN** the transport starts and `gs-alpha` is already attached to `ga-crew-alpha`
- **THEN** no migration action is taken for that crew
