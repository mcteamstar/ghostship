## ADDED Requirements

### Requirement: HOST controls only the Caddy host bind address

`HOST` (`network.host`) SHALL set only the host address `ga-portal` publishes on, for both `PORT` and the dashboard port range. It SHALL default to `127.0.0.1`. The transport container SHALL always listen on `0.0.0.0` internally, whatever `HOST` is, and Caddy's upstream dial strings SHALL remain `ga-transport:64057`. `docs/configuration.md` SHALL describe this split in the `HOST` entry.

#### Scenario: Default install is reachable only from the local machine
- **WHEN** `install.sh` regenerates `compose.yml` with `HOST` unset
- **THEN** `ga-portal` publishes `PORT` and the dashboard port range on `127.0.0.1` only
- **AND** the transport container listens on `0.0.0.0` inside its container

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

### Requirement: Install readiness is verified through the portal

`install.sh` and `ghostship start` SHALL report the transport ready only when a `/health` request sent to the address and `PORT` that `ga-portal` publishes on succeeds, and is proxied through to the transport. A transport that answers only inside its own container SHALL NOT count as ready. Wildcard `HOST` values SHALL be probed via `127.0.0.1`.

#### Scenario: Unreachable transport behind the portal fails readiness
- **WHEN** the transport is running but `ga-portal` cannot reach it, so `/health` through the portal returns `502`
- **THEN** `install.sh` does not report the transport ready and exits non-zero once the readiness timeout expires, naming the portal-to-transport path

#### Scenario: Specific HOST is probed at that address
- **WHEN** `HOST=192.168.1.10`
- **THEN** the readiness probe targets `http://192.168.1.10:{PORT}/health`

### Requirement: API key resolution order

`install.sh` SHALL resolve the endpoint API key from, in order of precedence: the `--api-key` flag, then `network.api_key` in the resolved YAML config, then the key persisted in `DATA_DIR` by a previous `--api-key`. A key or opt-out set in the YAML config SHALL NOT be overridden by a previously persisted key.

#### Scenario: YAML key wins over a stale persisted key
- **WHEN** `DATA_DIR/ga-api-key` holds `old-key`, `network.api_key` is `new-key`, and `install.sh` runs without `--api-key`
- **THEN** the transport is configured with `new-key`

#### Scenario: YAML opt-out wins over a persisted key
- **WHEN** `DATA_DIR/ga-api-key` holds a key, `network.api_key` is `false`, and `install.sh` runs without `--api-key`
- **THEN** API-key authentication is disabled

#### Scenario: Flag wins over YAML
- **WHEN** `network.api_key` is `yaml-key` and `install.sh` runs with `--api-key flag-key`
- **THEN** the transport is configured with `flag-key`

#### Scenario: Empty flag clears the persisted key and falls through to YAML
- **WHEN** `DATA_DIR` holds a persisted key, `network.api_key` is `yaml-key`, and `install.sh` runs with `--api-key ""`
- **THEN** the persisted key is deleted and the transport is configured with `yaml-key`

#### Scenario: Persisted key used when nothing else is set
- **WHEN** `DATA_DIR/ga-api-key` holds `old-key`, `network.api_key` is unset, and `install.sh` runs without `--api-key`
- **THEN** the transport is configured with `old-key`

### Requirement: Non-loopback installs require an API key or an explicit opt-out
The check SHALL evaluate the address `ga-portal` publishes on (`HOST`), never the transport's in-container listen address. A loopback `HOST` (unset, `127.0.0.0/8`, `::1`, `localhost`) needs no key. Any other `HOST` (`0.0.0.0`, `::`, or a specific address) SHALL need a non-empty key or the explicit opt-out `network.api_key: false`. If the key is unset, the install SHALL abort before starting any containers.

#### Scenario: Remote install without API key aborts
- **WHEN** `install.sh` is run with `HOST=0.0.0.0` and the API key is unset
- **THEN** `install.sh` aborts with a non-zero exit code before starting any containers

#### Scenario: Specific non-loopback address without API key aborts
- **WHEN** `install.sh` is run with `HOST=192.168.1.10` and the API key is unset
- **THEN** the install aborts with a non-zero exit code before starting any containers

#### Scenario: Local install without API key succeeds
- **WHEN** `install.sh` is run with `HOST=127.0.0.1` (or `HOST` unset) and the API key is unset
- **THEN** the install completes normally with no API-key warning, the portal is published on loopback only, and the transport starts without authentication

#### Scenario: Remote install with explicit opt-out succeeds
- **WHEN** `install.sh` is run with `HOST=0.0.0.0` and `network.api_key: false`
- **THEN** the install completes and the transport starts without authentication

#### Scenario: API key set on non-loopback address succeeds
- **WHEN** `install.sh` runs with `--api-key <value>` and `HOST=0.0.0.0`
- **THEN** the install completes with authentication enabled and no unauthenticated-access warning is printed

### Requirement: Unauthenticated non-loopback exposure is warned about
When an install aborts for an unset key, `install.sh` SHALL print a `WARNING` naming the published address and port, stating MCP endpoints would be reachable by any host that can reach it, and listing the fixes: set an API key, set `HOST=127.0.0.1`, or set `network.api_key: false`. With the opt-out on a non-loopback `HOST`, `install.sh` and the transport at startup SHALL each emit a `WARNING` that the endpoint is unauthenticated.

#### Scenario: Abort message lists the resolution paths
- **WHEN** `install.sh` aborts because `HOST=0.0.0.0` and the API key is unset
- **THEN** the WARNING names the address and port, and lists setting an API key, `HOST=127.0.0.1`, and `network.api_key: false`

#### Scenario: Opt-out install warns
- **WHEN** `install.sh` is run with `HOST=0.0.0.0` and `network.api_key: false`
- **THEN** `install.sh` prints a WARNING that the endpoint is unauthenticated by explicit choice

#### Scenario: Transport logs startup warning when unauthenticated on non-loopback
- **WHEN** the transport process starts with no API key, the explicit opt-out set, and a non-loopback portal address
- **THEN** the transport logs a `WARNING`-level message stating that no API key
  is configured and MCP endpoints are accessible without authentication

### Requirement: Transport startup enforces the API-key requirement
The transport SHALL re-check the API-key requirement at startup against the portal's published address, not its own in-container listen address. If the portal's published address is non-loopback, no API key secret is present, and the explicit opt-out is not set, the transport SHALL refuse to start and exit with a non-zero code.

#### Scenario: Transport refuses to start unauthenticated on non-loopback
- **WHEN** the transport starts with a non-loopback portal address, no `ga-api-key` secret, and no explicit opt-out
- **THEN** the transport exits immediately with a logged error naming the missing API key

#### Scenario: Fixed wildcard listen address does not trip the check
- **WHEN** the transport starts listening on `0.0.0.0` in its container, the portal's published address is `127.0.0.1`, and no API key is present
- **THEN** the transport starts normally without the API-key error

### Requirement: API-key opt-out and GA_TRUSTED_PROXY documented in configuration docs
`docs/configuration.md` SHALL document `network.api_key` (string to enable,
unset to require one on non-loopback installs, `false` to opt out explicitly)
and the deprecation of `network.require_api_key`/`GA_REQUIRE_API_KEY`, together
with `GA_TRUSTED_PROXY` (what it does, the default, and how to set it for
Caddy-fronted installs).

`config/ghostship.yaml.example` SHALL show `network.api_key` with a comment
describing all three states, and SHALL NOT include `network.require_api_key`.

#### Scenario: Operator reads docs to understand authentication posture options
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `network.api_key` documented with its three states and
  the abort behaviour, a deprecation note for `network.require_api_key`, and
  `GA_TRUSTED_PROXY` documented with its effect on rate-limit source-IP
  extraction

#### Scenario: Example config shows the opt-out
- **WHEN** an operator opens `config/ghostship.yaml.example`
- **THEN** `network.api_key` is present with a comment explaining string, unset,
  and `false`, and `network.require_api_key` is absent

## REMOVED Requirements

### Requirement: GA_REQUIRE_API_KEY defaults to error on non-loopback installs
**Reason**: `GA_REQUIRE_API_KEY` is replaced by the three-state `network.api_key` (key, unset, or `false`), and the check now evaluates the portal's published address instead of the transport's in-container listen address. The `warn` mode is retired: an unset key on a non-loopback install always warns and aborts.
**Migration**: Replace `network.require_api_key: off` (or `GA_REQUIRE_API_KEY=off`) with `network.api_key: false`; `install.sh` performs this mapping with a deprecation warning. Drop `error`/`warn`. See "Non-loopback installs require an API key or an explicit opt-out".

### Requirement: Transport startup enforces GA_REQUIRE_API_KEY=error
**Reason**: Superseded by "Transport startup enforces the API-key requirement", which checks the portal's published address and the explicit opt-out instead of `GA_REQUIRE_API_KEY` and the transport's own bind address.
**Migration**: No operator action beyond the `network.api_key` migration above.

### Requirement: GA_REQUIRE_API_KEY and GA_TRUSTED_PROXY documented in configuration docs
**Reason**: `GA_REQUIRE_API_KEY` is deprecated and `config/ghostship.conf.example` no longer exists (replaced by `config/ghostship.yaml.example`, TRN-253/257).
**Migration**: Superseded by "API-key opt-out and GA_TRUSTED_PROXY documented in configuration docs".
