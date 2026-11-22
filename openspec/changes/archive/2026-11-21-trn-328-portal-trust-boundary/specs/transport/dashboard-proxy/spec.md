# Spec Delta

## ADDED Requirements

### Requirement: Authenticate dashboard HTTP proxy clients
When dashboard API-key authentication is enabled, the transport SHALL validate the original client's unexpired and unrevoked dashboard session before proxying an HTTP request to a crew gateway. Possession of `GA_TRANSPORT_SECRET` alone SHALL NOT authorize access to a crew dashboard. When API-key authentication is disabled, the existing open access behavior SHALL remain available.

#### Scenario: HTTP request without a session is rejected
- **WHEN** an HTTP request reaches `/crews/{crew_id}/ui` on a keyed installation without a valid `gs_session` cookie
- **THEN** the transport returns HTTP 401 and does not connect to the crew gateway

#### Scenario: Internal token alone does not authorize dashboard access
- **WHEN** an internal caller presents a valid `X-Transport-Token` but no valid dashboard session
- **THEN** the transport returns HTTP 401 and does not proxy the request

#### Scenario: Valid dashboard session permits HTTP proxying
- **WHEN** an HTTP request reaches `/crews/{crew_id}/ui` on a keyed installation with a valid dashboard session
- **THEN** the transport proxies the request to the crew gateway

#### Scenario: Open installation preserves existing access
- **WHEN** API-key authentication is disabled
- **THEN** the UI proxy continues to accept requests without a dashboard session
