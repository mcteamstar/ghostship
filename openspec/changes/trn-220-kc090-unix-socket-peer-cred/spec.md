# Delta Spec — TRN-220 Internal-API Peer-Cred Compatibility

## ADDED Requirement: Transport authenticates to the crew gateway with the dashboard cookie only

The transport host process MUST authenticate every REST call to a crew gateway
using the dashboard session cookie path and MUST NOT send the internal-API
headers (`X-Internal-Secret`, `X-Session-Key`) from the transport host.

**Rationale:** KiroCrew 0.9.0 (PR #2424) peer-cred-gates the internal-API
path. The transport host runs under a different UID than the crew container's
`kirocrew` process, so an internal-secret call from the transport host would be
rejected by the unix-socket peer-credential check even with a valid secret.

### Behaviour after the change

- `_crew_api(crew, method, path, **kw)` MUST emit exactly these auth-bearing
  headers and no others: `Cookie: mc_token_<port>=<cookie>` and
  `Origin: <crew_url>`.
- No ghostship code path on the transport host MAY add `X-Internal-Secret` or
  `X-Session-Key` to a gateway request.
- Processes that legitimately use the internal-secret path (if any are added in
  future) MUST run **inside** the crew container as the `kirocrew` user, so the
  peer-cred UID check (`kirocrew == kirocrew`) passes.

### Scenario: transport issues a crew REST call

- **WHEN** the transport calls any `/api/*` route on a crew gateway via
  `_crew_api`
- **THEN** the request carries `Cookie` + `Origin` only
- **AND** the request carries no `X-Internal-Secret` or `X-Session-Key` header
- **AND** the gateway authenticates it on the external cookie path, which is
  not subject to peer-cred validation

### Scenario: crew member (Raven) issues a REST call from inside the container

- **WHEN** Raven calls `POST /api/spawn` (or steer/continue) from inside the
  container
- **THEN** she reads `/home/kirocrew/.kiro/crew/.dashboard_cookie` and sends it
  as `Cookie: mc_token_5476=<value>` with the allowed `Origin`
- **AND** she sends neither `X-Internal-Secret` nor `X-Session-Key`
- **AND** the call succeeds on the cookie path (loopback-bound cookie minted by
  `_mint_internal_cookie`), independent of the peer-cred change

### Scenario: a future change routes an internal-API call from the transport host (regression to prevent)

- **WHEN** code on the transport host sends `X-Internal-Secret` to a crew
  gateway
- **THEN** under 0.9.0 the gateway rejects it on the peer-cred check (UID
  mismatch: transport-host UID ≠ container `kirocrew` UID)
- **AND** this proposal's regression test MUST fail at CI time before such a
  change can merge

## Configuration

No new or modified config keys. The relevant 0.9.0 config surface
(`agent.sandbox`, session timeouts, etc.) does not interact with this path.

The invariant is enforced by:
- the header contract in `_crew_api` (code), and
- `_RAVEN_GATEWAY_ORIENTATION` (prompt text already present), which must
  continue to forbid the internal-secret headers.

## Out of scope

- Any change to the gateway's own peer-cred implementation (that is KiroCrew's,
  not ghostship's).
- The loopback-cookie minting flow (`_mint_internal_cookie`), which already
  solves the related IP-mismatch problem and is unaffected.
