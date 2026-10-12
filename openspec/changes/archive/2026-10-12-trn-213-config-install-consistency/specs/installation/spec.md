## ADDED Requirements

### Requirement: Nine internal vars hardcoded as constants

The following environment variables SHALL be removed from `Config.from_env()` and from
the `compose.yml` template. Their values SHALL be hardcoded as Python literals or
module-level constants:

| Variable | Hardcoded value |
|----------|----------------|
| `GA_CREW_AGENT` (KiroCrew internal agent name) | `"kiro"` constant |
| `TRANSPORT_DATA_DIR` | `"/data"` literal |
| `GA_ENABLE_SECURITY_HEADERS` | always `True` |
| `GA_TLS_MIN_VERSION` | `"1.2"` constant |
| `GA_PREWARM_ENABLED` | removed; prewarm always runs when triggered |
| `GA_PREWARM_TTL_SECS` | `300` module-level constant |
| `GA_SUBAGENT_MAX_TURNS` | `200` module-level constant |
| `GA_COMPOSE_RETRY_ATTEMPTS` | `3` constant in install.sh |
| `GA_COMPOSE_RETRY_DELAY_SECS` | `2` constant in install.sh |

#### Scenario: Removed vars have no effect when set in environment
- **WHEN** any of the nine removed vars is set in the environment or `ghostship.conf`
- **THEN** the transport ignores it and uses the hardcoded value; install.sh does not
  pass it through to compose

### Requirement: GA_CREW_AGENT replaces GA_CREW_ACP_BACKEND and GA_AGENT_BACKENDS

`GA_CREW_AGENT` SHALL be the single variable controlling which ACP backend is built into
the crew image and used at runtime. It replaces both `GA_CREW_ACP_BACKEND` (runtime
default) and `GA_AGENT_BACKENDS` (build-time list).

Valid values: `kiro` (default), `claude`, `codex`, `opencode`. A comma-separated list
(e.g. `GA_CREW_AGENT=claude,codex`) builds multiple toolchains; the first entry is the
runtime default.

`install.sh` SHALL derive `AGENT_TOOLCHAINS` (the set of toolchain scripts to install
into the crew image) from `GA_CREW_AGENT`. `GA_CREW_ACP_BACKEND` and `GA_AGENT_BACKENDS`
SHALL be accepted as deprecated aliases for one release cycle, with a printed warning
directing operators to use `GA_CREW_AGENT` instead.

#### Scenario: GA_CREW_AGENT=claude builds and runs Claude backend
- **WHEN** `GA_CREW_AGENT=claude` is set in `ghostship.conf` and `install.sh` runs
- **THEN** the crew image is built with the `claude.sh` toolchain
- **AND** the transport environment contains `GA_CREW_AGENT=claude`
- **AND** new crew containers use the Claude ACP backend by default

#### Scenario: Deprecated GA_CREW_ACP_BACKEND maps to GA_CREW_AGENT
- **WHEN** `GA_CREW_ACP_BACKEND=claude` is set and `GA_CREW_AGENT` is unset
- **THEN** install.sh prints a deprecation warning and treats `GA_CREW_AGENT=claude`
  for this run

#### Scenario: Deprecated GA_AGENT_BACKENDS maps to GA_CREW_AGENT
- **WHEN** `GA_AGENT_BACKENDS=claude,codex` is set and `GA_CREW_AGENT` is unset
- **THEN** install.sh prints a deprecation warning and treats `GA_CREW_AGENT=claude,codex`
  for this run

### Requirement: compose.yml adds volume mounts for host-path vars when set

When an operator-configurable variable contains a host filesystem path that the transport
reads at runtime, `install.sh` SHALL add a corresponding volume mount to the `ga-transport`
service so the path is reachable inside the container.

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
- **THEN** `install.sh` prints a warning that the directory does not exist but continues

#### Scenario: GA_TLS_CERTFILE and GA_TLS_KEYFILE produce a shared mount
- **WHEN** `GA_TLS_CERTFILE=/etc/tls/server.crt` and `GA_TLS_KEYFILE=/etc/tls/server.key` are set
- **THEN** `compose.yml` contains `- /etc/tls:/mnt/tls:ro` in the `ga-transport` volumes
- **AND** the transport environment contains `GA_TLS_CERTFILE=/mnt/tls/server.crt` and `GA_TLS_KEYFILE=/mnt/tls/server.key`

#### Scenario: Only one TLS var set aborts install
- **WHEN** `GA_TLS_CERTFILE=/etc/tls/server.crt` is set but `GA_TLS_KEYFILE` is unset
- **THEN** `install.sh` exits non-zero with an error stating both must be set together

#### Scenario: TLS cert and key in different directories aborts install
- **WHEN** `GA_TLS_CERTFILE=/etc/tls/cert.pem` and `GA_TLS_KEYFILE=/etc/pki/key.pem` are set
- **THEN** `install.sh` exits non-zero with an error explaining the same-directory requirement

### Requirement: PORT controls only the Caddy host port; transport internal port is fixed

The transport container SHALL always listen on port `64057` internally. `PORT` controls
the host port that Caddy (`ga-portal`) binds on. The compose `environment:` block for
`ga-transport` SHALL hard-code `PORT: "64057"` regardless of the operator-configured
`PORT` value. Caddy's upstream dial strings shall reference `ga-transport:64057`
unconditionally.

`docs/configuration.md` SHALL clarify this decoupling in the `PORT` entry.

#### Scenario: Custom PORT does not change transport internal port
- **WHEN** `PORT=9000` is set in `ghostship.conf` and `install.sh` regenerates `compose.yml`
- **THEN** Caddy binds on host port `9000`
- **AND** the transport container's `PORT` env var remains `64057`
- **AND** Caddy's upstream dial string remains `ga-transport:64057`
