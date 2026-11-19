# Spec Delta

## MODIFIED Requirements

### Requirement: Composite caller-identity key
The middleware SHALL derive a per-caller key from available request signals:

- **No API key presented**: key is the source IP address.
- **API key presented (valid or not yet verified)**: key is
  `SHA-256(api_key)[:8]:<source_ip>` — a fixed-length prefix of the key's hash
  concatenated with the source IP. The raw key value is never stored in limiter
  state.

The source IP SHALL be the immediate ASGI peer address unless that peer belongs
to a CIDR configured in `GA_TRUSTED_PROXY_CIDR`. For a trusted peer with an
`X-Forwarded-For` header, the source IP SHALL be the first address in that header.
When the header is absent, the source IP SHALL fall back to the ASGI peer address.
When `GA_TRUSTED_PROXY_CIDR` is unset or empty, the middleware SHALL ignore
`X-Forwarded-For`. The CIDR value is parsed during startup and does not change at
runtime.

#### Scenario: No API key uses an IP-only bucket
- **WHEN** a request arrives without an Authorization header
- **THEN** its limiter key is the resolved source IP alone

#### Scenario: API key is hashed into the caller key
- **WHEN** a request presents an API key, valid or not yet verified
- **THEN** its limiter key uses SHA-256(api_key)[:8] and the resolved source IP without storing the raw key

#### Scenario: Untrusted peer cannot spoof the source address
- **WHEN** a request comes from a peer outside `GA_TRUSTED_PROXY_CIDR` and supplies `X-Forwarded-For`
- **THEN** the source IP is the ASGI peer address and the header is ignored

#### Scenario: Trusted peer uses the first forwarded hop
- **WHEN** a trusted proxy sends `X-Forwarded-For: 10.0.0.1, 192.168.1.5`
- **THEN** the source IP is `10.0.0.1`

#### Scenario: Trusted peer without a forwarded header falls back
- **WHEN** a request comes from a trusted peer without an `X-Forwarded-For` header
- **THEN** the source IP is the ASGI peer address

#### Scenario: Same IP and same key share a bucket
- **WHEN** two requests arrive from the same source IP with the same API key
- **THEN** they share the same rate-limit bucket

#### Scenario: Same IP and different keys use separate buckets
- **WHEN** two requests arrive from the same source IP with different API keys
- **THEN** they use separate rate-limit buckets

#### Scenario: Unset trusted-proxy configuration ignores forwarded headers
- **WHEN** `GA_TRUSTED_PROXY_CIDR` is unset or empty and a request carries `X-Forwarded-For`
- **THEN** the middleware uses the ASGI peer address
