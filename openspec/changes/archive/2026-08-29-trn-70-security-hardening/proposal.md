# TRN-70 — Security Hardening: File Transfer, Auth, Input Validation

## Summary

A security review of `transport/server.py` (release/0.2.0) identified 2 Critical and 4 High
vulnerabilities. This change fixes all 6.

## Problems

### C-1: HMAC truncated to 128 bits
`_sign_file_url`, `_sign_upload_url`, and `_verify_file_token` all call `.hexdigest()[:32]`,
producing a 128-bit tag from a 256-bit HMAC-SHA256. This halves the security margin of every
presigned URL the transport issues. An attacker with one valid URL can attempt offline forgery
of other URLs for the same crew at half the expected cost.

### C-2: `ref` parameter — git argument injection
In `_handle_file_get`, `ref` from the HTTP query string is passed directly to
`git bundle create ... <ref>` and `git diff <ref> -- <path>` with no validation. A value
beginning with `-` or `--` is interpreted as a git flag rather than a revision. An attacker
with MCP access can pass `ref="--output=/path/inside/container"` to write arbitrary content
inside the crew container, escalating to code execution via a planted skill or steering file.

### H-1: Path traversal — no canonicalisation
The `..` component check (`if ".." in clean.split("/")`) is the only guard. No call to
`Path.resolve()` confirms the resolved path stays under the workspace root. A path like
`repo/./../../etc/passwd` (no `..` component) bypasses the check.

### H-2: GET and PUT presigned tokens are interchangeable
The HMAC payload for downloads (`_sign_file_url`) and uploads (`_sign_upload_url`) is
identical: `"crew_id:path:ref:bundle:expires"`. A read-only evac URL doubles as a valid
upload token — a user handed a download URL can POST arbitrary bytes to the same URL,
overwriting the file.

### H-3: Auth disabled by default — no warning
When `GA_API_KEY` is unset (the install default), `BearerAuthMiddleware` is a transparent
passthrough. The startup log emits only an `INFO` message. Operators who miss it expose all
MCP tools (launch, nuke, supply, evac, dispatch, steer, captain) to unauthenticated callers.

### H-4: Raw query string forwarded to crew gateway verbatim
The proxy handler concatenates the raw query string directly into the upstream crew gateway
URL. This enables CRLF injection and exposes internal gateway parameters to external callers.

## Decisions

- **C-1**: Remove `[:32]` from all three HMAC sites. Use full 64-char hexdigest. Signing and
  verification must change atomically — all outstanding presigned URLs are invalidated on
  deploy (acceptable: short-lived tokens, no long-lived sharing).
- **C-2**: Validate `ref` against `^[a-zA-Z0-9_./-]+$`; reject leading `-`. Also pass `--`
  as an option terminator before `ref` in all git invocations as defence-in-depth.
- **H-1**: After cleaning, resolve the path relative to the workspace root using `Path.resolve()`
  and assert it is a sub-path of the root. Apply in both MCP tool functions and HTTP handlers.
- **H-2**: Prefix the HMAC payload with the operation type: `"get:crew_id:path:..."` for
  downloads, `"put:crew_id:path:..."` for uploads. All three sign/verify sites must align.
- **H-3**: Downgrade to `WARNING` when `GA_API_KEY` is unset. Add a visible banner to the
  startup log. **This is not a complete fix** — the transport still starts unauthenticated by
  default. The warning is the minimum acceptable change for 0.2.0 given that the default-open
  behaviour is intentional for local installs. Requiring `GA_API_KEY` for non-local deployments
  or flipping the default to auth-required is deferred to a separate breaking-change ticket
  (0.3.0 candidate).
- **H-4**: Forward only a known-safe allowlist of query parameters to the crew gateway
  (`task_id`, `timeout`, `agent` — whatever is legitimately proxied). Strip everything else.
  Reject query strings containing CR or LF characters.

## Out of Scope

- M-5 (starlette CVE-2024-47874 dependency pinning) — separate chore ticket
- M-1 (Containerfile `USER` directive) — separate hardening ticket
- M-2/M-3 (exec f-string injection in `_inject_auth`/steering copy) — separate ticket
- Low items — deferred
