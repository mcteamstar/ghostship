## MODIFIED Requirements

### Requirement: `ga-portal` network topology

`ga-portal` SHALL be attached to `ga-portside` only. The previous requirement that `ga-portal` and `ga-transport` share `ga-net` is superseded: they now share `ga-portside`. `ga-portal` SHALL NOT be attached to `ga-starboard` and SHALL NOT be able to make direct DNS connections to `gs-*` crew containers.

The Caddy admin API (port 2019) SHALL remain bound to `0.0.0.0` inside the `ga-portal` container (so it is reachable from `ga-transport` over `ga-portside`) and SHALL NOT be published to the host. The `_caddy_register_crew` and `_caddy_deregister_crew` helpers in the transport dial `ga-portal:2019` over `ga-portside`; this continues to work because `ga-transport` is on both networks.

The requirement that no Caddy upstream in the initial config or in any `_caddy_register_crew` call dials a `gs-*` address directly is unchanged and further enforced by the network split — even if a Caddy config error introduced a `gs-*` upstream, the connection would fail because `gs-*` containers are not on `ga-portside`.

### Requirement: `X-Portal-Token` header injection

Caddy's Caddyfile/JSON config SHALL add `header_up X-Portal-Token {env.GA_PORTAL_SECRET}` on every `reverse_proxy` directive targeting `ga-transport`. This applies to ALL upstream routes — MCP, files, dashboard, health — without exception. The header value is the `GA_PORTAL_SECRET` environment variable, which is mounted into `ga-portal` from the `ga-portal-secret` Podman secret at install time.

No Caddy route SHALL forward a request to `ga-transport` without this header. The transport middleware will reject any request that arrives without it.

#### Scenario: ga-portal attaches to ga-portside only

- **WHEN** `install.sh` generates `compose.yml`
- **THEN** the `ga-portal` service declares `ga-portside` (and only `ga-portside`) in its `networks:` block
- **THEN** `ga-portal` does NOT declare `ga-starboard`

#### Scenario: Caddy admin API reachable from transport

- **WHEN** `_caddy_register_crew` dials `ga-portal:2019`
- **THEN** the connection succeeds because both `ga-portal` and `ga-transport` are on `ga-portside`

#### Scenario: ga-portal cannot resolve crew container hostnames

- **WHEN** Caddy is given a misconfigured upstream pointing to `gs-<crew_id>:5476`
- **THEN** the DNS lookup fails — `gs-*` names are not resolvable from `ga-portside`

#### Scenario: X-Portal-Token is injected on all upstream routes

- **WHEN** Caddy proxies any request to `ga-transport` (MCP, dashboard, files, health)
- **THEN** the request includes `X-Portal-Token: <value of GA_PORTAL_SECRET>`
