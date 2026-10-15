## Purpose

Defines unit-test coverage requirements for `transport/caddy.py`, covering port
pool management, reverse proxy configuration generation, virtual host
registration and deregistration via the Caddy admin API, TLS configuration
handling, and retry/error behaviour — all verifiable without a live Caddy
process.

## ADDED Requirements

### Requirement: CaddyPortal port pool allocation

The test suite SHALL exercise `CaddyPortal.allocate_port` and `release_port`,
confirming correct scan behaviour and the exhaustion guard.

#### Scenario: First available port is returned

- **WHEN** a `CaddyPortal` is constructed with a range of N ports and none are
  in use
- **THEN** `allocate_port()` returns the range start port and adds it to
  `_dashboard_ports_in_use`

#### Scenario: Already-in-use port is skipped

- **WHEN** the range-start port is already in `_dashboard_ports_in_use`
- **THEN** `allocate_port()` returns the next free port in the range

#### Scenario: Exhausted pool raises RuntimeError

- **WHEN** every port in the configured range is in `_dashboard_ports_in_use`
- **THEN** `allocate_port()` raises `RuntimeError`

#### Scenario: Released port becomes available for reallocation

- **WHEN** a port is released via `release_port()` and `allocate_port()` is
  called again
- **THEN** the released port is returned

#### Scenario: release_port is idempotent for absent port

- **WHEN** `release_port()` is called with a port not in `_dashboard_ports_in_use`
- **THEN** no exception is raised and `_dashboard_ports_in_use` is unchanged

### Requirement: Module-level port wrappers delegate to default portal

The thin-wrapper functions `_allocate_dashboard_port` and
`_release_dashboard_port` SHALL delegate to the module-default `CaddyPortal`
built from the current module globals.

#### Scenario: _allocate_dashboard_port allocates from module range

- **WHEN** `_allocate_dashboard_port()` is called with the module globals set to
  a known range
- **THEN** it returns a port within that range and `_dashboard_ports_in_use` is
  updated

#### Scenario: _release_dashboard_port removes the port

- **WHEN** `_release_dashboard_port(port)` is called with a previously allocated
  port
- **THEN** the port is removed from `_dashboard_ports_in_use`

### Requirement: CaddyPortal.register_crew builds correct reverse-proxy config

`CaddyPortal.register_crew` SHALL issue a `PUT` to the Caddy admin API with a
server object whose routes satisfy the documented routing contract.

#### Scenario: Happy-path PUT 200 registers crew

- **WHEN** `register_crew(crew_id, port)` is called and the mocked HTTP client
  returns 200
- **THEN** exactly one PUT request is made to
  `http://ga-portal:2019/config/apps/http/servers/crew-{crew_id}` with a valid
  server object, and no exception is raised

#### Scenario: PUT 201 is also treated as success

- **WHEN** the mocked client returns 201
- **THEN** no exception is raised and no retry is attempted

#### Scenario: PUT 409 (already exists) is treated as idempotent success

- **WHEN** the mocked client returns 409
- **THEN** no exception is raised and no retry is attempted

#### Scenario: Server object listen port matches argument

- **WHEN** `register_crew("abc", 8765)` is called
- **THEN** the PUT body contains `"listen": [":8765"]`

#### Scenario: Server object uses crew-scoped @id

- **WHEN** `register_crew("abc", 8765)` is called
- **THEN** the PUT body contains `"@id": "crew-abc"`

#### Scenario: Reverse proxy rewrite uses correct crew path prefix

- **WHEN** `register_crew("abc", 8765)` is called
- **THEN** the reverse proxy handler's `rewrite.uri` starts with
  `/crews/abc/ui`

#### Scenario: Transport-token header is injected in proxy handler

- **WHEN** `register_crew` generates the server object
- **THEN** the reverse proxy handler's `headers.request.set` contains
  `X-Transport-Token` set to `{file./run/secrets/ga-transport-secret}`

#### Scenario: WebSocket route appears before HTTP catch-all route

- **WHEN** `register_crew` generates the server object
- **THEN** `routes[0]` matches on `Connection: Upgrade` (the WebSocket route)
  and `routes[1]` is the HTTP catch-all, ensuring upgrades bypass forward-auth

#### Scenario: Forward-auth handler included when api_key is set

- **WHEN** `CaddyPortal` is constructed with a non-empty `api_key` and
  `register_crew` is called
- **THEN** the HTTP catch-all route's `handle` list contains a forward-auth
  handler targeting `/dashboard/auth` before the reverse-proxy handler

#### Scenario: Forward-auth handler absent when api_key is empty

- **WHEN** `CaddyPortal` is constructed with `api_key=""` and `register_crew`
  is called
- **THEN** the HTTP catch-all route's `handle` list contains only the
  reverse-proxy handler (no forward-auth handler)

#### Scenario: Transient failure retries and succeeds

- **WHEN** the mocked client returns 500 on the first attempt and 200 on the
  second
- **THEN** register_crew retries and returns without raising, and exactly two
  PUT requests are made

#### Scenario: All retries exhausted — no exception raised

- **WHEN** the mocked client returns 500 on all three attempts
- **THEN** `register_crew` returns without raising (it only logs a warning)

### Requirement: CaddyPortal.deregister_crew calls Caddy admin DELETE

`CaddyPortal.deregister_crew` SHALL call `DELETE` on the correct admin URL and
handle non-fatal response codes gracefully.

#### Scenario: DELETE 200 deregisters crew

- **WHEN** `deregister_crew("abc")` is called and the mocked client returns 200
- **THEN** the DELETE is made to `http://ga-portal:2019/id/crew-abc` and no
  exception is raised

#### Scenario: DELETE 204 is also treated as success

- **WHEN** the mocked client returns 204
- **THEN** no exception is raised

#### Scenario: DELETE 404 is handled gracefully

- **WHEN** the mocked client returns 404
- **THEN** no exception is raised (crew was already removed)

#### Scenario: DELETE non-2xx/404 logs warning but does not raise

- **WHEN** the mocked client returns 500
- **THEN** no exception is raised (nuke must not be blocked by Caddy errors)

#### Scenario: DELETE connection error logs warning but does not raise

- **WHEN** the HTTP call raises an exception
- **THEN** `deregister_crew` catches it and returns without re-raising

### Requirement: Module-level thin wrappers delegate to default portal

`_caddy_register_crew` and `_caddy_deregister_crew` SHALL delegate to
`_get_default_portal()` and produce the same observable HTTP calls as the
direct portal methods.

#### Scenario: _caddy_register_crew issues PUT to admin API

- **WHEN** `_caddy_register_crew("test", 9000)` is called with mocked httpx
- **THEN** a PUT request is made to the Caddy admin URL for `crew-test`

#### Scenario: _caddy_deregister_crew issues DELETE to admin API

- **WHEN** `_caddy_deregister_crew("test")` is called with mocked httpx
- **THEN** a DELETE request is made to the Caddy admin URL for `crew-test`

### Requirement: _caddy_admin_url returns correct constant

The `_caddy_admin_url` helper SHALL always return the fixed Caddy admin base
URL.

#### Scenario: Admin URL is the expected constant

- **WHEN** `_caddy_admin_url()` is called
- **THEN** it returns `"http://ga-portal:2019"`

### Requirement: CaddyPortal constructor stores fields correctly

`CaddyPortal.__init__` SHALL store all constructor arguments as instance
attributes accessible by the instance methods.

#### Scenario: Constructor fields are correctly stored

- **WHEN** a `CaddyPortal` is constructed with explicit `port`, `api_key`,
  `port_range_start`, and `port_range_size`
- **THEN** `portal._port`, `portal._api_key`, `portal._range_start`, and
  `portal._range_size` match the supplied values
