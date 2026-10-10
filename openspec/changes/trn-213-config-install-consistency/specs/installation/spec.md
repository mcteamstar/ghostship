## ADDED Requirements

### Requirement: compose.yml includes all transport-readable env vars

`install.sh` SHALL include every environment variable that `Config.from_env()` or `auth.py` reads in the generated `compose.yml` transport service environment block. Missing entries cause operator-set values to be silently ignored at runtime.

The following variables SHALL be added to the compose template:
- `GA_PREWARM_ENABLED`
- `GA_PREWARM_TTL_SECS`
- `KC_IMAGE`
- `KC_BASE_IMAGE`
- `GA_RATE_LIMIT_DASHBOARD_AUTH`

#### Scenario: GA_PREWARM_ENABLED wired through compose
- **WHEN** `GA_PREWARM_ENABLED=true` is set in `ghostship.conf` and `install.sh` regenerates `compose.yml`
- **THEN** the transport container environment contains `GA_PREWARM_ENABLED=true` and the prewarm feature activates at runtime

#### Scenario: KC_IMAGE wired through compose
- **WHEN** `KC_IMAGE=localhost/my-custom-crew:latest` is set in `ghostship.conf` and `install.sh` regenerates `compose.yml`
- **THEN** the transport container environment contains `KC_IMAGE=localhost/my-custom-crew:latest` and the transport uses that image when spawning crews

#### Scenario: GA_RATE_LIMIT_DASHBOARD_AUTH wired through compose
- **WHEN** `GA_RATE_LIMIT_DASHBOARD_AUTH=300:60` is set in `ghostship.conf` and `install.sh` regenerates `compose.yml`
- **THEN** the transport container environment contains `GA_RATE_LIMIT_DASHBOARD_AUTH=300:60` and the `/dashboard/auth` endpoint enforces that limit

### Requirement: compose.yml adds volume mounts for host-path vars when set

When an operator-configurable variable contains a host filesystem path that the transport reads at runtime, `install.sh` SHALL add a corresponding volume mount to the `ga-transport` service so the path is reachable inside the container.

**GA_ORDERS_DIR:** When `GA_ORDERS_DIR` is non-empty, `install.sh` SHALL:
1. Require it to be an absolute path (error and abort if relative).
2. Warn (but continue) if the directory does not exist.
3. Add a read-only volume mount `<host_path>:/mnt/orders` to the compose `ga-transport` volumes.
4. Write `GA_ORDERS_DIR: "/mnt/orders"` (the fixed container path) into the compose environment block.

**GA_TLS_CERTFILE / GA_TLS_KEYFILE:** When both are non-empty, `install.sh` SHALL:
1. Error and abort if only one is set.
2. Error and abort if they do not share the same parent directory (same-directory requirement).
3. Add a read-only volume mount `<shared_parent_dir>:/mnt/tls` to the compose `ga-transport` volumes.
4. Write `GA_TLS_CERTFILE: "/mnt/tls/<cert_basename>"` and `GA_TLS_KEYFILE: "/mnt/tls/<key_basename>"` into the compose environment block.

#### Scenario: GA_ORDERS_DIR produces a volume mount and rewritten path
- **WHEN** `GA_ORDERS_DIR=/home/user/my-orders` is set and `install.sh` regenerates `compose.yml`
- **THEN** `compose.yml` contains `- /home/user/my-orders:/mnt/orders:ro` in the `ga-transport` volumes
- **AND** the transport environment contains `GA_ORDERS_DIR=/mnt/orders`

#### Scenario: GA_ORDERS_DIR relative path aborts install
- **WHEN** `GA_ORDERS_DIR=relative/path` is set and `install.sh` runs
- **THEN** `install.sh` exits non-zero with an error explaining an absolute path is required

#### Scenario: GA_ORDERS_DIR missing directory warns but continues
- **WHEN** `GA_ORDERS_DIR=/nonexistent/path` is set and `install.sh` runs
- **THEN** `install.sh` prints a warning that the directory does not exist but continues; the transport will log its own warning at startup

#### Scenario: GA_TLS_CERTFILE and GA_TLS_KEYFILE produce a shared mount
- **WHEN** `GA_TLS_CERTFILE=/etc/tls/server.crt` and `GA_TLS_KEYFILE=/etc/tls/server.key` are set
- **THEN** `compose.yml` contains `- /etc/tls:/mnt/tls:ro` in the `ga-transport` volumes
- **AND** the transport environment contains `GA_TLS_CERTFILE=/mnt/tls/server.crt` and `GA_TLS_KEYFILE=/mnt/tls/server.key`

#### Scenario: Only one TLS var set aborts install
- **WHEN** `GA_TLS_CERTFILE=/etc/tls/server.crt` is set but `GA_TLS_KEYFILE` is unset
- **THEN** `install.sh` exits non-zero with an error stating both must be set together

#### Scenario: TLS cert and key in different directories aborts install
- **WHEN** `GA_TLS_CERTFILE=/etc/tls/cert.pem` and `GA_TLS_KEYFILE=/etc/pki/key.pem` are set (different parent directories)
- **THEN** `install.sh` exits non-zero with an error explaining the same-directory requirement

### Requirement: PORT controls only the Caddy host port; transport internal port is fixed

The transport container SHALL always listen on port `64057` internally. `PORT` controls the host port that Caddy (`ga-portal`) binds on. The compose `environment:` block for `ga-transport` SHALL hard-code `PORT: "64057"` regardless of the operator-configured `PORT` value. Caddy's upstream dial strings shall reference `ga-transport:64057` unconditionally.

`docs/configuration.md` SHALL clarify this decoupling in the `PORT` entry: "PORT controls the Caddy host port only. The transport always listens on 64057 inside its container."

#### Scenario: Custom PORT does not change transport internal port
- **WHEN** `PORT=9000` is set in `ghostship.conf` and `install.sh` regenerates `compose.yml`
- **THEN** Caddy binds on host port `9000`
- **AND** the transport container's `PORT` env var remains `64057`
- **AND** Caddy's upstream dial string remains `ga-transport:64057`
