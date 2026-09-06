# Security hardening (TRN-70)

This document is the operational companion to the OpenSpec change
`trn-70-security-hardening`. It records how the four security capabilities are
enforced in the transport, how secrets are rotated without a code change, and
how the one **BREAKING** change (plaintext HTTP → HTTPS redirect) is staged and
communicated to clients.

The security primitives live in `transport/security.py`; the transport wires
them in `transport/server.py`. Every protection is togglable via configuration
so a rollback needs no code change.

## Secrets management

- **Single accessor.** All secret reads go through `security.get_secret(...)`
  (and the transport's `_load_api_key` / `_load_or_create_file_secret`, which
  register their values for redaction). The API key is a Podman secret
  mounted at `/run/secrets/ga-api-key`.
- **Redaction.** `SecretRedactionFilter` is installed on the root logger at
  startup. Any value passed to `security.register_secret` is scrubbed from every
  log record, error, and audit line (replaced with `***REDACTED***`).
- **CI secret scan.** `tests/security_scan.py` runs in the `security-scan` CI
  job and fails the build on a likely committed live secret.
- **Admiral secret delivery via stdin.** The `admiral_secret` is delivered to
  container scripts via stdin, not process arguments. `inject_admiral_secret.py`
  reads the secret from `sys.stdin.read().strip()` so it never appears in
  `podman exec` argument lists or `/proc/<pid>/cmdline` during the exec's
  lifetime.
- **crews.json stores identifiers only.** After `admiral_secret` and
  `policy_signing_key` are injected into the crew container, `crews.json`
  retains only a non-reversible identifier for each secret
  (`"admiral_secret_id": "sha256:<hex[:16]>"`, `"policy_signing_key_id": "sha256:<hex[:16]>"`).
  The plaintext values exist in memory only for the duration of the injection
  call and are never written to disk. This closes the residual exposure noted
  as TRN-16 in earlier versions.

### Rotating a secret (no code change)

The `GA_API_KEY` is a Podman secret, not baked into the image or source, so
rotation is a re-create + restart — no rebuild, no code edit:

```sh
# Rotate the transport API key.
podman secret rm ga-api-key
printf '%s' "$NEW_KEY" | podman secret create ga-api-key -
podman restart ghost-academy   # container re-reads /run/secrets/ga-api-key
```

The file-URL signing secret (`ga-file-secret`) is persisted under the data
mount and can be overridden with the `GA_FILE_SECRET` env var; rotating it
invalidates outstanding presigned URLs (which are short-lived by design).

Because the value is read at process start through the single accessor, the new
value is picked up on restart with no source change — satisfying the
"secret rotation without a code change" requirement.

## Authentication security

The transport is a single-bearer-key gateway; `transport/security.py` provides
the credential, throttle, and session primitives for any account-bearing
surface:

- **Credential storage** — `hash_password` / `verify_password` use Argon2id when
  the `argon2-cffi` library is present (OWASP first choice) and stdlib scrypt as
  the accepted memory-hard fallback. The hash string is self-describing (algo +
  params + salt); cleartext is never stored. `needs_rehash` drives opportunistic
  rehash-on-login to upgrade legacy hashes.
- **No credential in responses** — no API returns a password, hash, or reversible
  form; the auth extract/inject path moves only opaque `auth_kv` rows over an
  internal channel and never returns them to clients.
- **Brute-force throttling** — `Throttle` keeps a sliding window of failures
  keyed on account + source, locks out past the threshold with a generic error,
  and resets on a successful login. Backed by the shared fast store in
  production so it holds across instances.
- **Bounded, revocable sessions** — `SessionStore` issues short-lived tokens and
  keeps a server-side revocation set so logout/admin-revoke takes effect
  immediately, before natural expiry.
- **Audit logging** — `audit_auth_event` writes a structured event (action,
  outcome, account, source, timestamp) for every auth/authz decision and never
  includes a credential or token value; the redaction filter is a second line of
  defence.

## Transport security

`SecurityHeadersMiddleware` (outermost in the ASGI stack) emits the baseline
headers on every response — `X-Content-Type-Options: nosniff`, `X-Frame-Options:
DENY` (plus CSP `frame-ancestors 'none'`), and a Content-Security-Policy — and
adds HSTS (`max-age` two years, `includeSubDomains`) on HTTPS responses. HTTPS is
detected from the scheme or `X-Forwarded-Proto` (TLS is terminated at the edge).

Minimum TLS is 1.2. When the app terminates TLS directly (non-edge installs),
set `GA_TLS_CERTFILE` / `GA_TLS_KEYFILE`; `GA_TLS_MIN_VERSION` sets the floor.

### HTTPS redirect and CSP enforcement

HTTPS redirect is handled unconditionally by Caddy. CSP is unconditionally enforced. Neither behaviour is configurable via environment variables.

## Input validation

- **Server-side validation** — `security.validate_str` checks type, length, and
  format and rejects invalid input; the transport already validates `crew_id`
  (`CREW_ID_RE`), `agent` (`_validate_agent`), and change names server-side,
  independent of any client checks.
- **Injection-safe data access** — all `auth_kv` access uses parameterized SQL
  (`VALUES (?, ?)` with bound rows); untrusted file paths are passed to transfer
  scripts via environment variables, never concatenated into the script body.
- **Context-aware output encoding** — `encode_html_text`, `encode_html_attr`,
  and `encode_url_component` encode untrusted data for its rendering context.
- **CI static check** — `tests/security_scan.py` flags string-built SQL and
  fails the build (`security-scan` job).

## Verification

- Spec-scenario tests: `tests/unit/test_trn70_security.py` (one test per spec
  scenario across the four capabilities plus audit logging).
- Prior hardening tests: `tests/unit/test_security_hardening.py` (TRN-27:
  Podman secrets, login TOCTOU).
- `openspec validate trn-70-security-hardening --strict` passes.
