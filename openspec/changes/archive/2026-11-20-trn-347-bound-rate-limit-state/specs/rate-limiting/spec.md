## MODIFIED Requirements

### Requirement: Composite caller-identity key

Rate limiting SHALL group unauthenticated requests by resolved source IP. Only an authenticated API key SHALL add its hash to the existing composite key. Raw keys SHALL NOT be stored. Trusted peers retain existing forwarded-address resolution; other peers use their ASGI address.

#### Scenario: Presented bearer is invalid
- **WHEN** requests from one source present different invalid bearer values
- **THEN** they share the unauthenticated source bucket

#### Scenario: No API key uses an IP-only bucket
- **WHEN** a request arrives without an Authorization header
- **THEN** its limiter key is the resolved source IP alone

#### Scenario: API key is hashed into the caller key
- **WHEN** a request presents the currently configured API key
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
- **WHEN** two requests arrive from the same source IP with the same valid API key
- **THEN** they share the same rate-limit bucket

#### Scenario: Same IP and different keys use separate buckets
- **WHEN** two requests arrive from the same source IP with different valid API keys
- **THEN** they use separate rate-limit buckets

#### Scenario: Unset trusted-proxy configuration ignores forwarded headers
- **WHEN** `GA_TRUSTED_PROXY_CIDR` is unset or empty and a request carries `X-Forwarded-For`
- **THEN** the middleware uses the ASGI peer address
## ADDED Requirements

### Requirement: Endpoint limiter state has a finite capacity

Each endpoint limiter SHALL cap tracked keys and reclaim expired keys across callers while preserving atomic quota checks.

#### Scenario: Limiter has no free bucket
- **WHEN** a new key arrives at capacity after expiry reclamation
- **THEN** it receives the existing HTTP 429 response and active buckets are preserved

#### Scenario: Inactive bucket expires
- **WHEN** a key has no hits left in its window
- **THEN** its capacity is reclaimed without needing another request from that key
