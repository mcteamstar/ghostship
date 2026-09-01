# crew-lifecycle Specification (delta)

## MODIFIED Requirements

### Modified Requirement: Crew launch registers Caddy UI route

When `GA_CADDY_UI_ENABLED=true`, `launch` SHALL register a Caddy reverse-proxy route for the crew's UI path after the container is started. The route registration SHALL be non-fatal: if the Caddy admin API is unreachable, launch SHALL log a warning and return success.

### Modified Requirement: Crew nuke removes Caddy UI route

When `GA_CADDY_UI_ENABLED=true`, `nuke` SHALL remove the crew's Caddy route via the admin API before or after container destruction. Route removal failure SHALL be logged but SHALL NOT cause nuke to fail.
