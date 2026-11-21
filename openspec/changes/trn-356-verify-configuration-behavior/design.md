## Context

Some config wiring tests match exact Python source expressions for signed URLs, launch origins and startup API-key enforcement.

## Decisions

Assert the host in generated supply and evac URLs, the CORS origin passed into the crew at launch, and startup enforcement for key, loopback, wildcard and explicit opt-out cases. Use real config values and fake external I/O. Keep textual assertions for shipped assets such as orders where text is the contract. Build on TRN-354's local fixtures.

Use the real link-producing MCP entry points and parse each URL. Check that an explicit external base takes precedence and the portal fallback uses the operator-facing host and port. For launch, capture the container environment and assert the scheme, host and port of its CORS origin, including removal of a public URL path. Exercise the startup wiring through the server entry path in an isolated subprocess or equivalent harness that invokes the real startup function with controlled I/O.

## Risks / Trade-offs

A helper-only assertion can miss a disconnected caller. Exercise tool or startup entry points for each wiring claim.

## Spec references

- `configuration/yaml` covers configuration precedence and explicit overrides.
- `transport/proxy-hosting` covers public URLs and crew CORS origin wiring.
- `installation` covers non-loopback API-key startup enforcement and the explicit opt-out.
- `file-transfer/supply` covers presigned upload URLs.
- `file-transfer/evac` covers presigned download URLs.
