## MODIFIED Requirements

### Requirement: `ga-portal` network topology

The requirement that `ga-portal` and `ga-transport` share `ga-net` is superseded. `ga-portal` SHALL be on `ga-portside` only; `gs-*` crew containers SHALL be on `ga-starboard` only. The invariant that `ga-portal` SHALL NOT make direct connections to crew containers (`gs-*`) continues to hold and is now additionally enforced at the network layer: crew container hostnames are not resolvable from `ga-portside`.

The routing path — browser → `ga-portal` → `ga-transport:/crews/{id}/ui/` → `gs-<crew_id>:5476` — continues to work because `ga-transport` bridges both networks: it is reachable by `ga-portal` over `ga-portside`, and can reach `gs-*` containers over `ga-starboard`.

#### Scenario: ga-portal and ga-transport share ga-portside

- **WHEN** `install.sh` generates `compose.yml`
- **THEN** both `ga-portal` and `ga-transport` services declare `ga-portside` in their `networks:` block
- **THEN** `ga-portal` does NOT declare `ga-starboard`
- **THEN** no Caddy upstream in the initial config or in any `_caddy_register_crew` call dials a `gs-*` address directly — all upstreams target `ga-transport`

#### Scenario: Dashboard request still reaches crew gateway

- **WHEN** a browser requests a crew dashboard port (e.g. `https://host:64058/`)
- **THEN** `ga-portal` proxies to `ga-transport:{PORT}/crews/{crew_id}/ui/` over `ga-portside`
- **THEN** `ga-transport` proxies to `gs-{crew_id}:5476` over `ga-starboard`
- **THEN** the KiroCrew SPA loads authenticated

#### Scenario: Crew containers not reachable directly from ga-portal

- **WHEN** `ga-portal` has a misconfigured upstream targeting `gs-<crew_id>:5476`
- **THEN** the connection fails — `gs-*` are not on `ga-portside`
