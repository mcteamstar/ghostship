# Proposal

## Why

`HOST` predates the Caddy portal. It used to choose where the transport listened when the transport was published straight to the host. Since `ga-portal` became the only published container, `HOST` still sets the transport's in-container listen address but has no effect on what is actually exposed. That breaks two ways:

- **Loopback breaks the portal.** An install with `HOST=127.0.0.1` (for example one migrated from an old `ghostship.conf` by TRN-253) makes the transport listen on its own container loopback. Caddy dials `ga-transport:64057` over `ga-portside`, gets `connection refused`, and every request (`/mcp`, `/login/*`, dashboards) returns 502.
- **The exposure check guards the wrong thing.** `ga-portal` is published on a hardcoded `0.0.0.0:${PORT}`, and the dashboard port range has no bind address at all. So every install is reachable from the LAN whatever `HOST` says. Meanwhile the `GA_REQUIRE_API_KEY` guard reads `HOST` as if it described that exposure. An operator can set `HOST=127.0.0.1`, pass the guard with no API key, and still expose an unauthenticated portal on all interfaces. The `X-Transport-Token` secret doesn't help, because Caddy attaches it to every request it forwards.

`PORT` already went through this split ("PORT controls only the Caddy host port; transport internal port is fixed"). `HOST` needs the same treatment.

The API-key settings around that guard are also more complicated than they need to be:

- Two keys express one decision: `network.api_key` and `network.require_api_key` (`error` | `warn` | `off`).
- A `network.api_key` in the YAML is silently overridden by a key persisted from an earlier `--api-key`.
- `network.api_key: false` would become the literal key `"false"`.

## What Changes

- **BREAKING:** `HOST` (`network.host`) SHALL control only the host address `ga-portal` publishes on, covering both the main `PORT` and the dashboard port range. Its default changes from `0.0.0.0` to `127.0.0.1`. An install that never set `HOST` and relied on remote access must now set `HOST` (and an API key, or the explicit opt-out).
- The transport's in-container listen address SHALL be fixed (`0.0.0.0`) and no longer read from `HOST`. The compose file hardcodes it, as it already does for `PORT: "64057"`.
- **BREAKING:** `network.api_key` becomes the single API-key setting, with three states: a string (authentication on), unset (required on non-loopback installs), or `false` (explicit opt-out). `network.require_api_key`/`GA_REQUIRE_API_KEY` is deprecated:
  - `off` maps to `api_key: false`, with a warning.
  - `error` and `warn` are ignored. The `warn` mode's continue-anyway behaviour is gone.
- On a non-loopback `HOST` with an unset key, `install.sh` SHALL warn and abort, and the transport SHALL refuse to start. Both checks SHALL evaluate the portal's published address, never the transport's listen address. Loopback means `127.0.0.0/8`, `::1` or `localhost`. With the opt-out, both still warn that the endpoint is unauthenticated.
- API key resolution order becomes: `--api-key` flag, then `network.api_key`, then the key persisted in `DATA_DIR`. A leftover `require_api_key: off` can never disable a key from any source.
- Install and start readiness SHALL be checked through `ga-portal`, so a transport the portal can't reach fails the install instead of passing silently, which is how this break shipped.
- The CLI's installed-URL discovery inspects `ga-portal`, not `ga-transport` (which publishes nothing). That fixes an existing `trn-cli` spec violation, and the CLI follows `HOST` automatically.
- When `GA_HOST_URL` is unset, the default public URL SHALL follow `HOST`: `http://localhost:{PORT}` for loopback or wildcard values, and `http://{HOST}:{PORT}` for a specific address. Crew CORS origins and presigned file URLs inherit this.
- Docs, `config/ghostship.yaml.example`, and the stale `server.py` bind comment are updated to match.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `installation`:
  - `HOST` becomes portal-only, with a loopback default. The requirement mirrors the existing `PORT` one.
  - API key resolution order is defined.
  - Readiness is verified through the portal.
  - The three `GA_REQUIRE_API_KEY` requirements are replaced by requirements keyed on the portal address and the `network.api_key` opt-out.
- `mcp-server`: the streamable-HTTP listener requirement no longer binds to `HOST`. It listens on a fixed in-container address, and host-side exposure is defined by the portal.
- `proxy-hosting`: the `GA_HOST_URL`-unset fallback (presigned URLs and the crew CORS origin) derives from `HOST` instead of always using `localhost`.
- `yaml-config`:
  - `network.require_api_key` is removed from the schema.
  - `network.api_key` accepts a string or `false`.
  - The deprecated `require_api_key` value, and the legacy `GA_REQUIRE_API_KEY` conf entry, are mapped with a warning.

## Impact

- **Code:**
  - `scripts/install.sh`: `ga-portal` compose `ports:`, `ga-transport` environment, API-key resolution and persistence, the exposure check, the `GA_HOST_URL` default, the readiness probe.
  - `scripts/start.sh`: the readiness probe.
  - `ghostship` (CLI): `_inspect_installed_url`.
  - `scripts/lib/yaml_config.py`: defaults, the `api_key` boolean handling, `require_api_key` deprecation, conf migration.
  - `transport/config.py`, `transport/server.py` (listen address, the check and warning functions, stale comment), `transport/tools.py` (CORS origin fallback), `transport/files.py` (URL fallback).
- **Config and docs:** `config/ghostship.yaml.example` (`network.host`, `network.api_key`, remove `require_api_key`), `docs/configuration.md` (`HOST`, `network.api_key`, `GA_REQUIRE_API_KEY` deprecation, `GA_HOST_URL`).
- **Tests:** `tests/unit/test_config.py`, `tests/unit/test_yaml_config.py`, plus new unit coverage for the exposure check, the opt-out, resolution order, and the URL fallback.
- **Operators:**
  - `host: 127.0.0.1` installs start working again with no config change.
  - Installs that copied the example's explicit `host: "0.0.0.0"` keep LAN exposure and must have a key or `api_key: false`.
  - Installs that never set `host` become loopback-only after `ghostship install`.
  - `require_api_key: warn` installs without a key now abort.
- **CLI:** `ghostship` installed-URL discovery (no spec change; it implements the existing `trn-cli` requirement).
- **Out of scope:**
  - `ghostship setup`/`init`'s default registration URL. Operators binding a specific `HOST` pass `--url`.
  - An `--api-key`-style CLI flag for the opt-out (YAML only).
  - `ga-portside`/`ga-starboard` topology and the `X-Transport-Token` portal secret.
