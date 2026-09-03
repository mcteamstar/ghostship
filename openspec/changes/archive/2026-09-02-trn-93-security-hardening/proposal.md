## Why

Three residual security exposures were deferred from TRN-27 and TRN-70: the `admiral_secret`
is passed as a plaintext CLI argument (visible in `ps aux` inside the container), `crews.json`
stores live crew secrets in plaintext (noted as TRN-16 future work in `docs/auth.md`), and
crew containers are created with no Linux capability restrictions or `no-new-privileges` flag.
These are the remaining medium-risk gaps after rate limiting (TRN-52) and secret separation
(TRN-53) have closed the higher-priority issues.

## What Changes

- **Secret delivery to container scripts via stdin** — replace positional CLI arg delivery of
  `admiral_secret` in `inject_admiral_secret.py` with stdin-based delivery so the secret never
  appears in `podman exec` argument lists or `/proc/<pid>/cmdline`.
- **`crews.json` at-rest secret hashing** — store an HMAC-keyed truncated hash of each crew's
  `admiral_secret` and `policy_signing_key` in `crews.json` instead of the plaintext values
  after they have been injected into the container. The plaintext values remain in memory only
  for the duration of the injection call and are not needed afterward for any read path.
- **Container hardening flags** — add `no_new_privileges: true` and a minimal capability
  drop-list (`CAP_NET_RAW`, `CAP_SYS_ADMIN`) to the `container_create` Podman spec for crew
  containers. The worker container (`worker_run`) is already network-isolated; apply the same
  no-new-privileges flag there too.
- **`GA_GATEWAY_TOKEN_TTL` validation at startup** — validate the
  `KC_GATEWAY_TOKEN_TTL` value on `Config.from_env()` to reject obviously malformed durations
  (non-positive, non-numeric suffix), log a warning, and fall back to the `24h` default rather
  than forwarding a garbage string to `kirocrew token`.
- **Audit log extension: file-transfer events** — extend `audit_auth_event` to cover
  presigned-URL issuance (supply/evac) and token verification outcomes so file-transfer
  access leaves an audit trail alongside auth events.

## Capabilities

### New Capabilities

- `secret-delivery-hardening`: Covers the requirement that live secret values are never
  passed as process arguments to container-exec scripts; secrets must be delivered via stdin
  or environment only.

### Modified Capabilities

- `crew-auth`: The at-rest secret storage requirement — `crews.json` MUST NOT contain
  plaintext `admiral_secret` or `policy_signing_key` values after injection completes. Only
  a non-reversible (hashed) identifier sufficient for correlation/audit is retained.
- `file-transfer-security`: Extend to require that every presigned-URL issuance and every
  token-verification outcome is recorded as an audit event (action, outcome, crew_id, source).

## Impact

- `transport/lifecycle.py` — `inject_admiral_secret.py` call site; `container_create` hardening
  flags; `crews.json` write path after successful injection.
- `transport/podman.py` — `container_create` spec; `worker_run` spec.
- `transport/container_scripts/inject_admiral_secret.py` — switch from `argv[2]` to stdin read.
- `transport/security.py` — minor: extend `audit_auth_event` with file-transfer audit support.
- `transport/server.py` — call `audit_auth_event` at presigned-URL issuance and verification.
- `transport/config.py` — add `KC_GATEWAY_TOKEN_TTL` validation in `from_env()`.
- `tests/unit/test_trn93_security_hardening.py` — new unit test file covering all scenarios.
- No API changes; no breaking changes to external callers.
