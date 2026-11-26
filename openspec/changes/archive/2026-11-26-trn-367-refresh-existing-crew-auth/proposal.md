# Proposal

## Why

Credential rotation already refreshes matching running crews for login-flow methods, but an injection failure has no operator retry path, and static credential or method changes cannot update an existing container. TRN-367 needs a clear operator API and Portal action for checking and refreshing a crew's assigned auth, with recovery guidance that preserves its workspace.

## What Changes

- Add an authenticated operator REST operation to refresh the credential currently assigned to one crew, with explicit results for refreshed, deferred until wake, recreate required, missing credential, and failed injection states.
- Expose the same operation to Portal/Radar through its session-gated API and an operator control on each crew; do not add an agent-facing MCP tool.
- Keep credential values out of request and response bodies. Use the bearer-protected transport API for direct operator clients and the transport-secret-protected internal API for Radar's server-side proxy.
- Document session lifetime observations as estimates, flow refresh behavior, and workspace-preserving recovery for static credential changes.

## Capabilities

### New Capabilities
- `transport/crew-auth-admin`: Operator REST API for refreshing a crew's currently assigned credential, with safe outcomes for running, stopped, and static-credential crews.

### Modified Capabilities
- `auth/crew-credentials`: Clarify the distinction between login-flow refresh for running crews and static credentials that require container recreation after a change.
- `transport/radar`: Add the Portal/Radar operator action and its browser-facing API proxy for the credential-refresh operation.

## Impact

Transport auth and crew lifecycle routes, credential injection helpers, OpenAPI output, `ga-radar` server and SPA, Caddy session-gated routing, auth documentation, and related unit tests. Existing MCP tools remain unchanged.
