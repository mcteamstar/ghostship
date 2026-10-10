## MODIFIED Requirements

### Requirement: Composite caller-identity key
The middleware SHALL derive a per-caller key from available request signals:

- **No API key presented**: key is the source IP address.
- **API key presented (valid or not yet verified)**: key is
  `SHA-256(api_key)[:8]:<source_ip>` — a fixed-length prefix of the key's hash
  concatenated with the source IP. The raw key value is never stored in limiter
  state.

Source IP extraction follows a **trusted-proxy rule** controlled by the
`GA_TRUSTED_PROXY` environment variable:

- `GA_TRUSTED_PROXY` unset or empty (default): use `scope["client"][0]` (the
  ASGI peer address — the address of the immediate upstream connection, which is
  the Caddy container when the standard deployment topology is in use). No
  `X-Forwarded-For` header is consulted.
- `GA_TRUSTED_PROXY=1` or a specific IP: use the **last hop** of the
  `X-Forwarded-For` header (the hop added by the trusted proxy). If XFF is
  absent, fall back to `scope["client"][0]`. The *first* hop is never used
  because it is client-controlled.

The raw `GA_TRUSTED_PROXY` value is read once at startup and does not change
at runtime.

#### Scenario: Default — ASGI client address used (no XFF consulted)
- **WHEN** `GA_TRUSTED_PROXY` is unset and a request arrives from the Caddy
  container with an `X-Forwarded-For` header
- **THEN** the rate-limit key is derived from `scope["client"][0]` (the Caddy
  container IP) and the `X-Forwarded-For` header is not read

#### Scenario: Trusted proxy enabled — last XFF hop used
- **WHEN** `GA_TRUSTED_PROXY=1` is set and a request carries
  `X-Forwarded-For: 10.0.0.1, 192.168.1.5`
- **THEN** the rate-limit source IP is `192.168.1.5` (the last hop)

#### Scenario: Trusted proxy enabled — XFF absent falls back to ASGI client
- **WHEN** `GA_TRUSTED_PROXY=1` is set and a request carries no
  `X-Forwarded-For` header
- **THEN** the rate-limit source IP is `scope["client"][0]`

#### Scenario: Same IP, same key — shared bucket
- **WHEN** two requests arrive from the same source IP with the same API key
- **THEN** they share the same rate-limit bucket

#### Scenario: Same IP, different keys — separate buckets
- **WHEN** two requests arrive from the same source IP with different API keys
- **THEN** they use separate rate-limit buckets

#### Scenario: No API key — IP-only bucket
- **WHEN** a request arrives with no `Authorization` header
- **THEN** the bucket key is the source IP alone
