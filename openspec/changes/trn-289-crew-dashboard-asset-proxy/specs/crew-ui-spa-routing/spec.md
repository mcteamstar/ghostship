# Spec Delta

## ADDED Requirements

### Requirement: Main port returns a useful response for crew dashboard paths

The transport's main Caddy port (`:64057`) SHALL NOT return an empty HTTP 200
for requests to `/crews/{crew_id}/ui` or `/crews/{crew_id}/ui/*`. When a crew
has an allocated `dashboard_port`, the main port SHALL redirect the browser to
the per-crew dedicated port URL (`http://<host>:<dashboard_port>/`). When the
crew has no allocated dashboard port, the main port SHALL return HTTP 404.

#### Scenario: Main port redirects to per-crew dashboard port

- **WHEN** `GET /crews/my-crew/ui` is requested on the main port
- **AND** the crew has an allocated `dashboard_port`
- **THEN** the main port returns HTTP 302 redirecting to `http://<host>:<dashboard_port>/`

#### Scenario: Main port returns 404 when no dashboard port allocated

- **WHEN** `GET /crews/my-crew/ui` is requested on the main port
- **AND** the crew has no allocated `dashboard_port` (launched without `dashboard=True`)
- **THEN** the main port returns HTTP 404

#### Scenario: Main port does not return empty 200 for crew UI paths

- **WHEN** `GET /crews/my-crew/ui/assets/main.js` is requested on the main port
- **THEN** the response is NOT HTTP 200 with `Content-Length: 0`
