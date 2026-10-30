# Spec Delta

## MODIFIED Capabilities

### crew-ui-proxy

#### ADDED Requirement: Transport strips Accept-Encoding from crew proxy requests

The transport's crew UI proxy (`_handle_crew_ui_proxy`) MUST strip the
`Accept-Encoding` header from all outbound requests to crew gateways. This
ensures crew gateways always return uncompressed responses that the transport
can pass through transparently.

**Rationale:** The transport proxies raw bytes using `_async_http.stream()`
without decompressing the response body. If `Accept-Encoding` is forwarded,
the crew gateway may return compressed content. The transport strips
`Content-Encoding` from all proxied responses (hop-by-hop header handling),
so the browser receives compressed bytes with no encoding hint and cannot
decompress them — causing a JS parse failure.

#### Scenario: Crew gateway always receives uncompressed request

- **WHEN** a browser sends `GET /crews/{id}/ui/assets/main.js` with
  `Accept-Encoding: gzip, br`
- **THEN** the transport forwards the request to the crew gateway WITHOUT
  an `Accept-Encoding` header
- **AND** the crew gateway returns an uncompressed response
- **AND** the browser successfully parses the JS asset

#### Scenario: Asset response is valid JS, not binary

- **GIVEN** a running crew with a dashboard port
- **WHEN** `GET /crews/{id}/ui/assets/main.js` is proxied through the transport
- **THEN** the response body starts with valid JS text (e.g. `const `)
- **AND** the response does NOT contain gzip magic bytes (`0x1f 0x8b`)
