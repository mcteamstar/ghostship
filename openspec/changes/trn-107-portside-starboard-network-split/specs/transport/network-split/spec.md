## Purpose

Defines the two-network topology that isolates the portal tier from crew containers, prevents crew containers from reaching `ga-portal`, and enforces an internal-only token check that prevents crew containers from accessing `ga-transport` MCP routes.

## ADDED Requirements

### Requirement: Network model — portside and shared starboard

The system SHALL provision two static Podman networks replacing `ga-net`:

- `ga-portside` — used exclusively by `ga-portal` and `ga-transport`. No `gs-*` crew container, login container, or worker container SHALL be attached to `ga-portside`.
- `ga-starboard` — used by `ga-transport` and all `gs-*` crew containers (shared). `ga-portal` SHALL NOT be attached to `ga-starboard`.

`ga-transport` SHALL be attached to both `ga-portside` and `ga-starboard` at all times, bridging the portal tier and the crew tier.

Both networks are created by `install.sh` and declared as external in `compose.yml`. Neither is created or destroyed at crew launch/nuke time — both are static.

Network assignments:

| Container | Network(s) |
|---|---|
| `ga-portal` | `ga-portside` only |
| `ga-transport` | `ga-portside` + `ga-starboard` |
| `gs-{crew_id}` (crew) | `ga-starboard` only |
| `ga-login-{token}` (ephemeral) | `ga-starboard` |
| `gs-worker-{token}` (disposable) | none (`netns: none`) |

The constants `GA_PORTSIDE_NETWORK = "ga-portside"` and `GA_STARBOARD_NETWORK = "ga-starboard"` SHALL be defined in `lifecycle.py` and imported by `server.py`. No dynamic per-crew network naming function is needed.

#### Scenario: Portal cannot reach crew containers directly

- **WHEN** `ga-portal` attempts to connect to `gs-<crew_id>:5476` via DNS
- **THEN** the connection fails — `gs-*` hostnames are not resolvable from `ga-portside`

#### Scenario: Crew containers cannot reach ga-portal directly

- **WHEN** a `gs-*` crew container attempts to connect to `ga-portal` via DNS
- **THEN** the connection fails — `ga-portal` hostname is not resolvable from `ga-starboard`

#### Scenario: Transport is reachable from portside

- **WHEN** `ga-portal` reverse-proxies to `ga-transport:{PORT}`
- **THEN** Caddy can reach `ga-transport` over `ga-portside` DNS

#### Scenario: Transport is reachable from starboard

- **WHEN** `gs-<crew_id>` dials `ga-transport:{PORT}` on `ga-starboard`
- **THEN** the connection reaches `ga-transport` — both share `ga-starboard`

#### Scenario: Crew container joins ga-starboard at creation

- **WHEN** `launch` creates a `gs-{crew_id}` container
- **THEN** `podman inspect gs-{crew_id}` shows the container attached to `ga-starboard` and NOT attached to `ga-portside`

#### Scenario: Login container joins ga-starboard

- **WHEN** `_start_login_container` creates a `ga-login-*` container for crew `{crew_id}`
- **THEN** the container is attached to `ga-starboard` and NOT attached to `ga-portside`

#### Scenario: Worker container joins no network

- **WHEN** `worker_run` creates a `gs-worker-*` container
- **THEN** the container has `netns: none` — unchanged from current behaviour

### Requirement: GA_PORTAL_SECRET internal token

The system SHALL generate an internal secret `GA_PORTAL_SECRET` at install time. This token SHALL be the primary control preventing crew containers on `ga-starboard` from accessing `ga-transport` MCP and API routes.

**Generation and storage:**
- Generated at install time: `openssl rand -hex 32`
- Written as Podman secret `ga-portal-secret`
- Mounted into `ga-transport` at `/run/secrets/ga-portal-secret`
- Injected into `ga-portal` as environment variable `GA_PORTAL_SECRET`
- `GA_PORTAL_SECRET` generation SHALL be idempotent at re-install (skip if secret already exists)

**Caddy config (`ga-portal`):**
- SHALL add `header_up X-Portal-Token {env.GA_PORTAL_SECRET}` to ALL upstream requests to `ga-transport`, including MCP, files, dashboard, and health routes — every route without exception

**Transport middleware:**
- SHALL reject any request missing the `X-Portal-Token` header with HTTP 401 before `BearerAuthMiddleware` runs
- SHALL load the secret at startup via `_load_portal_secret()` — same pattern as `_load_api_key()`: reads from `/run/secrets/ga-portal-secret`, raises `RuntimeError` with a safe message if absent
- SHALL register the secret value with the log redaction filter so it never appears in logs
- `transport/config.py` SHALL gain a `ga_portal_secret` field populated by `_load_portal_secret()`

**Crew containers on `ga-starboard` SHALL NOT receive `GA_PORTAL_SECRET` in any form** — neither as an environment variable, a mounted secret, nor via any other mechanism.

**GA_API_KEY** remains optional and is a separate concern — external client auth at the Caddy edge only. This change does not alter `GA_API_KEY` behaviour.

#### Scenario: Request with correct portal token reaches transport

- **WHEN** Caddy proxies a request to `ga-transport` with `X-Portal-Token: <correct-value>`
- **THEN** the portal secret middleware allows the request to proceed to the next handler

#### Scenario: Request missing portal token is rejected

- **WHEN** any caller (including a crew container on ga-starboard) dials `ga-transport:{PORT}` without an `X-Portal-Token` header
- **THEN** the transport returns HTTP 401 — the request never reaches an MCP handler or `BearerAuthMiddleware`

#### Scenario: Request with wrong portal token is rejected

- **WHEN** a caller sends a request with `X-Portal-Token: <wrong-value>`
- **THEN** the transport returns HTTP 401

#### Scenario: Portal secret never appears in logs

- **WHEN** any transport log line is emitted during a request cycle
- **THEN** the value of `GA_PORTAL_SECRET` does not appear in the log output

#### Scenario: Transport fails to start if secret is absent

- **WHEN** `_load_portal_secret()` cannot read `/run/secrets/ga-portal-secret`
- **THEN** the transport raises `RuntimeError` with a safe error message (not the secret value) and refuses to start

### Requirement: install.sh provisions portside and starboard

`install.sh` SHALL create both `ga-portside` and `ga-starboard` (each idempotent). `compose.yml` SHALL declare both as external. `ga-portal` is assigned to `ga-portside`; `ga-transport` is assigned to both `ga-portside` and `ga-starboard`. Per-crew or per-login networks are NOT created by `install.sh` and are NOT in `compose.yml`.

`install.sh` SHALL generate `GA_PORTAL_SECRET` and write it as the `ga-portal-secret` Podman secret. This step SHALL be idempotent — if the secret already exists with the correct name, do not regenerate it.

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

#### Scenario: Caddy config injects X-Portal-Token

- **WHEN** `install.sh` writes the Caddy config for `ga-portal`
- **THEN** every `reverse_proxy` directive targeting `ga-transport` includes `header_up X-Portal-Token {env.GA_PORTAL_SECRET}`

### Requirement: Migration of existing crews on startup

When the transport starts and `_reconcile_registry` runs, it SHALL detect any running crew container that is attached to `ga-net` but NOT attached to `ga-starboard`. For each such container the transport SHALL:

1. Connect `ga-transport` to `ga-starboard` (idempotent — it is already on starboard after compose restart).
2. Stop the container.
3. Disconnect it from `ga-net` (best-effort — `ga-net` may be absent).
4. Connect it to `ga-starboard`.
5. Start the container.
6. Wait for the gateway to become ready.
7. Refresh the session cookie.

If migration of a specific crew fails, the transport SHALL log a warning, mark that crew `stopped` in the registry, and continue migrating remaining crews. The transport SHALL NOT refuse to start because of migration failures.

After all crews are processed, if `ga-net` exists and has no attached containers, the transport SHALL attempt `podman network rm ga-net` (best-effort — log warning on failure, never raise).

#### Scenario: Existing crew on ga-net is migrated to ga-starboard

- **WHEN** the transport starts and `gs-alpha` is attached to `ga-net` but not `ga-starboard`
- **THEN** `gs-alpha` is reconnected to `ga-starboard` and its registry status is `running` after migration

#### Scenario: Migration failure does not block startup

- **WHEN** migration of one crew fails (e.g. container refuses to restart)
- **THEN** the transport logs a warning, marks that crew `stopped`, and proceeds to start serving requests

#### Scenario: Already-migrated crew is skipped

- **WHEN** the transport starts and `gs-alpha` is already attached to `ga-starboard`
- **THEN** no migration action is taken for that crew

#### Scenario: ga-net removed after migration

- **WHEN** all crews have been migrated and `ga-net` has no remaining containers
- **THEN** the transport attempts `podman network rm ga-net`; failure is logged as a warning, not raised
