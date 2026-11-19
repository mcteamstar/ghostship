# Spec Delta

## ADDED Requirements

### Requirement: Caller identity uses a trusted source address

The middleware SHALL derive a per-caller key from the source IP, adding a fixed SHA-256 prefix of any presented API key. It SHALL consult X-Forwarded-For only when the immediate ASGI peer is within GA_TRUSTED_PROXY_CIDR.

#### Scenario: No API key uses an IP-only bucket
- **WHEN** a request arrives without an Authorization header
- **THEN** its limiter key is the resolved source IP alone

#### Scenario: API key is hashed into the caller key
- **WHEN** a request presents an API key, valid or not yet verified
- **THEN** its limiter key uses SHA-256(api_key)[:8] and the resolved source IP without storing the raw key

#### Scenario: Untrusted peer cannot spoof the source address
- **WHEN** a request comes from a peer outside GA_TRUSTED_PROXY_CIDR and supplies X-Forwarded-For
- **THEN** the source IP is the ASGI peer address and the header is ignored

#### Scenario: Trusted peer uses the first forwarded hop
- **WHEN** a trusted proxy sends X-Forwarded-For: 10.0.0.1, 192.168.1.5
- **THEN** the source IP is 10.0.0.1

#### Scenario: Trusted peer without a forwarded address falls back
- **WHEN** a request comes from a trusted peer without a usable X-Forwarded-For value
- **THEN** the source IP is the ASGI peer address

#### Scenario: Same IP and same key share a bucket
- **WHEN** two requests arrive from the same source IP with the same API key
- **THEN** they share the same rate-limit bucket

#### Scenario: Same IP and different keys use separate buckets
- **WHEN** two requests arrive from the same source IP with different API keys
- **THEN** they use separate rate-limit buckets

#### Scenario: Unset trusted-proxy configuration ignores forwarded headers
- **WHEN** GA_TRUSTED_PROXY_CIDR is unset or empty and a request carries X-Forwarded-For
- **THEN** the middleware uses the ASGI peer address

## REMOVED Requirements

### Requirement: Composite caller-identity key

**Reason**: The documented GA_TRUSTED_PROXY switch and last-hop behavior do not match the implemented CIDR-based peer check and first-hop extraction.

**Migration**: Use GA_TRUSTED_PROXY_CIDR to list trusted proxy CIDRs. Forwarded headers from peers outside those ranges are ignored.
