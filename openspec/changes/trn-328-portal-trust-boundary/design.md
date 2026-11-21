# Design

## Context

See proposal.md for motivation and intended trust boundaries. Compose places Caddy, Transport, and Radar on ga-portside; Caddy's admin listener is bound inside the container network on port 2019, which is not published to the host. Dashboard proxy authorization must also be enforced at the Transport route because internal callers can bypass Caddy's browser-session layer.

## Goals / Non-Goals

**Goals:**
- Give Transport access to Caddy's admin API through a filesystem permission boundary.
- Require a valid dashboard session at the keyed Transport UI proxy.
- Preserve network memberships and public listener ports.

**Non-Goals:**
- Add a network or publish the admin API to the host.
- Change Radar's fleet-reading API or grant Radar Caddy configuration authority.

## Decisions

- Configure Caddy's admin endpoint as a Unix-domain socket in a dedicated shared volume mounted only by Caddy and Transport. Before choosing ownership and mode bits, verify both processes' runtime UID/GID from the pinned images; use restrictive shared-group permissions that allow Transport and deny Radar and crews.
- Keep the admin listener off TCP. A host firewall or Origin check is not an adequate substitute because other containers can reach portside.
- Enforce the dashboard session check in Transport before the HTTP proxy opens an upstream connection. Keep open-install behavior when API-key auth is disabled.
- Test generated Compose and exercise authorized socket requests and denied callers. Confirm port 2019 is absent from host mappings.

## Risks / Trade-offs

- [Container UID/GID differences prevent socket access] → Verify identities against the actual image and test a fresh install.
- [Socket removal disrupts route reconciliation] → Cover registration, removal, and startup reconciliation.
- [Internal dashboard callers depended on the secret alone] → Return 401 before any crew proxy connection and test that path.

## Proxy ownership

The two deltas target the first two capabilities. The HTTP proxy gate uses the existing session contract and preserves dashboard routing.

- `transport/caddy-proxy` covers Caddy admin listener and socket access.
- `transport/dashboard-proxy` covers Transport UI proxy admission for HTTP requests.
- `transport/dashboard-session-auth` covers issuance, expiry and revocation of dashboard sessions.
- `transport/dashboard-routing` covers public dashboard listener and forwarding behavior.
