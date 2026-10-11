# transport/crew-api-auth Specification

## Purpose

Defines how the transport host authenticates its REST calls to a crew gateway, pinning the invariant that it uses the external dashboard-cookie path only and never the peer-cred-gated internal-secret path.

## Requirements

### Requirement: Transport authenticates to the crew gateway with the dashboard cookie only

The transport host process SHALL authenticate every REST call to a crew gateway
using the dashboard session-cookie path, and SHALL NOT send the internal-API
headers `X-Internal-Secret` or `X-Session-Key` from the transport host.

A crew-gateway REST request issued from the transport host SHALL carry exactly
these auth-bearing headers and no others: `Cookie: mc_token_<port>=<cookie>`
and `Origin: <crew_url>`.

KiroCrew 0.9.0 (PR #2424 / issue #302) adds unix-socket peer-credential
validation to the internal-API path. The transport host runs under a different
OS UID than the crew container's `kirocrew` process, so an internal-secret call
originating on the transport host would be rejected by the peer-cred check even
when the shared secret is valid. Possession of the shared secret is therefore
no longer sufficient on its own for that path.

Any process that legitimately requires the internal-secret path SHALL run
**inside** the crew container as the `kirocrew` user, so that the peer-cred UID
check (`kirocrew` == `kirocrew`) passes.

#### Scenario: Transport issues a crew REST call

- **WHEN** the transport calls any `/api/*` route on a crew gateway from the transport host
- **THEN** the request carries a `Cookie` header and an `Origin` header
- **AND** the request carries no `X-Internal-Secret` header
- **AND** the request carries no `X-Session-Key` header
- **AND** the gateway authenticates the request on the external cookie path, which is not subject to peer-cred validation

#### Scenario: Crew member issues a REST call from inside the container

- **WHEN** a crew member (e.g. Raven) calls a crew-gateway REST route from inside the container
- **THEN** it reads the dashboard cookie from `/home/kirocrew/.kiro/crew/.dashboard_cookie` and sends it as `Cookie: mc_token_<port>=<value>` with the allowed `Origin`
- **AND** it sends neither `X-Internal-Secret` nor `X-Session-Key`
- **AND** the call succeeds on the cookie path, independent of the 0.9.0 peer-cred change

#### Scenario: Internal-secret call from the transport host is rejected under 0.9.0

- **WHEN** a process on the transport host sends `X-Internal-Secret` to a crew gateway running KiroCrew 0.9.0
- **THEN** the gateway rejects the request on the peer-cred check because the transport-host UID does not match the container `kirocrew` UID
- **AND** the rejection occurs even if the shared internal secret is correct

### Requirement: Forbidden internal-API headers are rejected before leaving the transport host

The transport's crew-gateway REST entry point SHALL reject any attempt to attach
`X-Internal-Secret` or `X-Session-Key` to an outbound crew-gateway request, so
that a code change which would route an internal-API call across the UID
boundary fails loudly rather than silently reaching a gateway that will reject
it. The failure SHALL be observable at build/test time.

#### Scenario: A caller attempts to attach a forbidden header

- **WHEN** a caller passes `X-Internal-Secret` or `X-Session-Key` to the transport's crew-gateway REST entry point
- **THEN** the request is refused before it is sent
- **AND** the refusal names the invariant so the author can see why the header is forbidden

#### Scenario: Regression guard fails in CI

- **WHEN** the automated test suite runs against the transport
- **THEN** a test asserts the crew-gateway REST entry point emits `Cookie` + `Origin` only and never `X-Internal-Secret` or `X-Session-Key`
- **AND** the test fails if any future change adds an internal-secret header to the transport-host REST path
