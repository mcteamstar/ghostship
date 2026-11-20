# Spec Delta

## MODIFIED Requirements

### Requirement: API-key opt-out and trusted proxy CIDRs documented in configuration docs
`docs/configuration.md` SHALL document `network.api_key` (string to enable,
unset to require one on non-loopback installs, `false` to opt out explicitly)
and the deprecation of `network.require_api_key`/`GA_REQUIRE_API_KEY`, together
with `GA_TRUSTED_PROXY_CIDR` (trusted proxy CIDRs, its default, and how to set
it for Caddy-fronted installs).

`config/ghostship.yaml.example` SHALL show `network.api_key` with a comment
describing all three states, and SHALL NOT include `network.require_api_key`.

#### Scenario: Operator reads docs to understand authentication posture options
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `network.api_key` documented with its three states and
  the abort behaviour, a deprecation note for `network.require_api_key`, and
  `GA_TRUSTED_PROXY_CIDR` documented with its effect on rate-limit source-IP
  extraction for peers within configured CIDRs

#### Scenario: Example config shows the opt-out
- **WHEN** an operator opens `config/ghostship.yaml.example`
- **THEN** `network.api_key` is present with a comment explaining string, unset,
  and `false`, and `network.require_api_key` is absent
