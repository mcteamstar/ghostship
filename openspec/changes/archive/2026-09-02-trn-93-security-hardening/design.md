## Context

See `proposal.md — Why` for motivation. The transport already has a single secrets
accessor (`security.get_secret`), a redaction filter, audit logging, and parameterised SQL
(TRN-70). TRN-53 separated `admiral_secret` from `policy_signing_key`. What remains is:

1. `admiral_secret` arrives at `inject_admiral_secret.py` as `argv[2]` — visible in
   `podman exec` process listings inside the container for the exec's lifetime.
2. `crews.json` at `/data/crews.json` (mode 0600) contains both 32-byte hex secrets
   in plaintext after launch. This is the residual from TRN-16.
3. `container_create` spec has no `no_new_privileges` or capability drops.
4. `KC_GATEWAY_TOKEN_TTL` is forwarded to `kirocrew token` verbatim without validation.
5. File-transfer issuance and verification events are not in the audit log.

## Goals / Non-Goals

**Goals:**
- Eliminate process-argument exposure of the admiral secret.
- Remove plaintext crew secrets from `crews.json` after injection, replacing them with
  opaque identifiers (sufficient for log correlation, useless for replay).
- Harden the Podman container spec for crew and worker containers.
- Validate `KC_GATEWAY_TOKEN_TTL` at startup with a safe fallback.
- Extend audit logging to cover presigned-URL issuance and token verification.

**Non-Goals:**
- Encrypting `crews.json` at rest (would require a key-management mechanism outside
  scope of this change; the at-rest identifier approach is the pragmatic step).
- Hardening the Podman socket itself or the host filesystem.
- Changing the `GA_API_KEY` or `ga-kiro-auth` delivery mechanisms.
- Adding new rate limits or auth mechanisms.

## Decisions

### 1. stdin delivery for `inject_admiral_secret.py`

**Decision:** The transport constructs a `container_exec_with_stdin` call that writes the
secret to the process's stdin pipe. `inject_admiral_secret.py` is changed from
`argv[2]` → `sys.stdin.read().strip()`. The PodmanSocketClient already has
`container_exec_pty_stdin`; a simpler `container_exec_stdin` variant is added that feeds
a byte string to stdin without allocating a PTY (no interactive terminal needed here).

**Alternative considered:** Pass via environment variable. Rejected: environment variables
are also visible in `/proc/<pid>/environ` for the process's lifetime and are inherited by
any child processes the script spawns. stdin is consumed once and does not persist in the
process environment.

**Alternative considered:** Write to a temp file inside the container, read it, then
delete. Rejected: introduces a race window and a cleanup obligation; stdin is simpler and
atomic.

### 2. At-rest credential hygiene in `crews.json`

**Decision:** After the plaintext secrets are used for injection (and before writing the
crew entry to `crews.json`), replace each plaintext value with a SHA-256 hex digest of
the value prefixed with a label (`"admiral_secret_id": "sha256:<hex[:16]>"`). The original
plaintext is never written to disk. The hashed identifier is sufficient for log correlation
(e.g. "which crew used this secret fingerprint?") without being reversible.

No additional HMAC salt is introduced: the identifier is purely for audit-trail correlation,
not authentication, so a plain SHA-256 prefix is sufficient. If cryptographic binding were
needed we would use HMAC; for an opaque identifier SHA-256 truncated to 64 bits is enough.

**Alternative considered:** Simply omit the fields from `crews.json` after injection.
Rejected: the fields being present (as identifiers) aids debugging ("was this crew's
admiral secret correctly injected?") by giving operators something to correlate against
logs. A complete absence provides no signal.

**Alternative considered:** Encrypt the values using a master key derived from the host.
Rejected: requires key storage and rotation, outside scope; the at-rest identifier approach
closes the immediate risk (operator reading `crews.json` can no longer replay the secrets).

### 3. Container hardening flags

**Decision:** Add `"no_new_privileges": True` and `"cap_drop": ["CAP_NET_RAW", "CAP_SYS_ADMIN"]`
to the Podman container-create spec dict for crew containers and worker containers. These
flags are safe for the known workloads (agent containers run as non-root `kirocrew` user;
workers are short-lived read-only jobs). `no_new_privileges` is the single highest-value
hardening flag: it prevents a contained setuid binary from escalating. `CAP_NET_RAW`
(raw socket access, needed for ping/traceroute but not for agent work) and `CAP_SYS_ADMIN`
(broad kernel capability) are the two most commonly abused capabilities in container escapes.

**Alternative considered:** Drop all capabilities (`cap_drop: ["ALL"]`). Not applied
immediately: some capabilities may be required by the graduation layer or kiro-cli's own
startup. A conservative drop of the two highest-risk capabilities now, with a broader
audit in a follow-on.

### 4. `KC_GATEWAY_TOKEN_TTL` validation

**Decision:** Add `_validate_token_ttl(value: str, default: str) -> str` to `config.py`.
The function accepts values matching `^\d+[smhd]$` with a numeric part > 0. On mismatch,
it logs a `WARNING` (naming the env var) and returns `default`. This is called from
`Config.from_env()` for the `kc_gateway_token_ttl` field.

### 5. Audit logging extension

**Decision:** The existing `audit_auth_event` in `security.py` already accepts arbitrary
`action`/`outcome` strings — no signature change is needed. The transport calls it at
two new sites:
- In the `evac()` and `supply()` MCP tools after a presigned URL is generated.
- In `_verify_file_token()` with the token's expiry status as the outcome.

The `source` parameter carries the caller key derived by `RateLimitMiddleware._caller_key`
where available (passed down from the handler), or `None` for MCP tool calls where no
per-request source IP is available.

## Risks / Trade-offs

**[Risk] `container_exec_stdin` not available in the mock `PodmanClient`** →
The abstract base class and mock must be extended alongside the production implementation.
The mock simply passes the stdin bytes through without a real exec; tests mock at the
`container_exec_checked` level, so existing test patterns apply.

**[Risk] `cap_drop` breaks a kiro-cli capability** →
The graduation layer or `kiro-cli` startup may implicitly rely on `CAP_NET_BIND_SERVICE`
or other capabilities. Mitigation: the drop list is intentionally conservative (`NET_RAW`
and `SYS_ADMIN` only); a follow-on can broaden it after smoke-testing. The spec is written
as a concrete list, not `ALL`, so unexpected breakage only affects those two capabilities.

**[Risk] SHA-256 identifier in `crews.json` breaks any code that reads the field back** →
Audit the call sites in `lifecycle.py` and `server.py` that read `admiral_secret` or
`policy_signing_key` from `crews.json` before shipping. Based on current code review there
are no read-back paths (the secrets are generated fresh at launch and never re-read from
the registry). The identifier field has a distinct name (`admiral_secret_id`) to prevent
silent misuse.

**[Risk] Audit events add overhead to every file-transfer call** →
`audit_auth_event` does a `logger.info()` call and an `strftime` — negligible overhead
for file-transfer workloads. Not a performance risk.

## Migration Plan

1. All changes are backward-compatible at the API level.
2. `inject_admiral_secret.py` must be updated before the `lifecycle.py` call site;
   deploying only the call side change would break injection for any in-flight crew launch.
   Both files change in the same commit.
3. Existing `crews.json` entries will continue to carry plaintext secrets. A one-time
   migration script is out of scope; the plaintext fields will remain for existing crews
   until they are re-launched or the registry is cleared. Document this in the tasks.
4. Container hardening flags apply only to newly-created containers; running crews are
   unaffected until they are nuked and re-launched.
5. No install.sh or Containerfile changes are required.

## Open Questions

None — all decisions above are resolved at the spec level.
