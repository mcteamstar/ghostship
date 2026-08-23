## ADDED Requirements

### Requirement: Crew UI reverse proxy
The transport SHALL expose `GET /crews/{crew_id}/ui` and `GET|POST|PUT|PATCH|DELETE /crews/{crew_id}/ui/{path:path}` routes that reverse-proxy all matching requests to `http://gs-{crew_id}:5476/{path}` on the crew's internal gateway. The crew SHALL be auto-woken via the existing restart mechanism before any proxied request is forwarded. The transport SHALL forward the original request method, path, query string, and all headers (excluding `host`) to the upstream gateway. Response status, headers, and body SHALL be streamed back to the caller without modification. The route SHALL NOT inject the internal session cookie; callers interact with the crew UI as a fresh browser session, including any login page the crew gateway serves.

#### Scenario: UI proxy reaches a running crew
- **WHEN** `GET /crews/my-crew/ui/` is requested and the crew container is running
- **THEN** the transport forwards the request to `http://gs-my-crew:5476/` and streams the response back with the original status code and headers

#### Scenario: UI proxy auto-wakes a stopped crew
- **WHEN** `GET /crews/my-crew/ui/` is requested and the crew container is stopped
- **THEN** the transport starts the container and waits for the gateway to become ready before forwarding the request, consistent with how other crew-touching endpoints behave

#### Scenario: UI proxy path forwarding
- **WHEN** `GET /crews/my-crew/ui/some/page?q=1` is requested
- **THEN** the transport proxies to `http://gs-my-crew:5476/some/page?q=1`, preserving path and query string

#### Scenario: UI proxy with no trailing path segment
- **WHEN** `GET /crews/my-crew/ui` is requested (no trailing slash)
- **THEN** the transport forwards to `http://gs-my-crew:5476/` (root of the crew gateway UI)

#### Scenario: UI proxy for unknown crew
- **WHEN** `GET /crews/unknown-crew/ui/` is requested and no such crew exists in the registry
- **THEN** the transport returns HTTP 404 with a message indicating the crew does not exist

#### Scenario: UI proxy with GA_API_KEY configured
- **WHEN** `GA_API_KEY` is set and a request to `/crews/{crew_id}/ui/` omits or supplies an incorrect `Authorization: Bearer` header
- **THEN** the transport returns HTTP 401 before proxying, consistent with all other authenticated routes

### Requirement: Crew REST API reverse proxy
The transport SHALL expose `GET|POST|PUT|PATCH|DELETE /crews/{crew_id}/api/{path:path}` routes that reverse-proxy to `http://gs-{crew_id}:5476/api/{path}` on the crew's internal gateway. The crew SHALL be auto-woken before any request is forwarded. The transport SHALL forward the original method, path, query string, body, and headers (excluding `host`). The transport SHALL inject the internal session cookie (`mc_token_5476=<value>`) so that REST calls succeed without a separate browser login. Response status, headers, and body SHALL be streamed back to the caller.

#### Scenario: API proxy forwards internal session cookie
- **WHEN** `GET /crews/my-crew/api/spawn` is requested
- **THEN** the transport injects `Cookie: mc_token_5476=<stored-value>` into the upstream request, and the crew gateway processes it as an authenticated call

#### Scenario: API proxy routes POST with body
- **WHEN** `POST /crews/my-crew/api/spawn` is requested with a JSON body
- **THEN** the transport proxies the full request including body to `http://gs-my-crew:5476/api/spawn` and returns the crew gateway's response

#### Scenario: API proxy auto-wakes a stopped crew
- **WHEN** any request to `/crews/my-crew/api/` is made and the crew is stopped
- **THEN** the transport starts the container and refreshes the session cookie before forwarding the request

#### Scenario: API proxy for unknown crew
- **WHEN** any request is made to `/crews/unknown-crew/api/` and the crew does not exist in the registry
- **THEN** the transport returns HTTP 404 with a message indicating the crew does not exist

#### Scenario: API proxy with GA_API_KEY configured
- **WHEN** `GA_API_KEY` is set and a request to `/crews/{crew_id}/api/` omits or supplies an incorrect `Authorization: Bearer` header
- **THEN** the transport returns HTTP 401 before proxying

### Requirement: Proxy routes documented in reference
The transport's user-facing documentation SHALL describe both new proxy route families, their URL patterns, their auth requirements, their auto-wake behaviour, and the difference in session-cookie handling between the UI proxy (no injection) and the API proxy (cookie injected).

#### Scenario: Reference covers UI proxy
- **WHEN** an operator reads `docs/reference.md`
- **THEN** they find the `/crews/{crew_id}/ui` and `/crews/{crew_id}/ui/{path:path}` entries with method, auth, and a note about browser-facing use

#### Scenario: Reference covers API proxy
- **WHEN** an operator reads `docs/reference.md`
- **THEN** they find the `/crews/{crew_id}/api/{path:path}` entry with method, auth, cookie-injection note, and example curl commands for common gateway REST calls
