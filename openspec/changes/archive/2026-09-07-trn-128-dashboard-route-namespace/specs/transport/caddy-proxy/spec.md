# transport/caddy-proxy Specification — TRN-128 delta

## Purpose

Updates the Caddy initial-config passthrough list to use the `/dashboard/*`
glob instead of four explicit dash-flat paths.

## MODIFIED Requirements

### Requirement: Initial Caddy config passthrough uses /dashboard/* glob

`install.sh` SHALL write the public-passthrough match list as:

```
["/health", "/version", "/dashboard/*", "/login", "/login*", "/logout"]
```

The previous four explicit paths (`/dashboard-auth`, `/dashboard-auth*`,
`/login-ui`, `/dashboard-login`, `/dashboard-logout`) are replaced by the
single glob. The device-auth routes (`/login`, `/login*`, `/logout`) are
unchanged.

#### Scenario: /dashboard/* matches all dashboard sub-paths

- **WHEN** a request arrives at `/dashboard/login`, `/dashboard/logout`,
  `/dashboard/auth`, or `/dashboard/login-ui`
- **THEN** Caddy forwards it to `ga-transport` without requiring a Bearer
  token (because `/dashboard/*` is in the public-passthrough list)

#### Scenario: Non-dashboard paths still require Bearer when key is set

- **WHEN** a request arrives at `/mcp` without a Bearer token and `GA_API_KEY` is set
- **THEN** Caddy returns 401 (not matched by `/dashboard/*`)
