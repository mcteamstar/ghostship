# Delta Spec: File Transfer Security

Target: `openspec/specs/file-transfer-security/spec.md`
Action: create

---

## Overview

The file transfer subsystem (supply/evac MCP tools and their HTTP handlers) must defend against:
- Token forgery via weak HMAC
- Operation confusion (read token used as write token)
- Path traversal out of the crew workspace
- Git argument injection via the `ref` parameter

## Requirements

### Requirement: Full-length HMAC
The HMAC-SHA256 digest used in presigned URLs MUST use the full 64-character hexdigest.
Truncation to any shorter length is not permitted.

### Requirement: Operation-typed tokens
Download tokens and upload tokens MUST be cryptographically non-interchangeable.
The HMAC payload MUST include the operation type (`get` or `put`) as a prefix.
A token issued for download MUST be rejected when presented for upload, and vice versa.

### Requirement: Path canonicalisation
All user-supplied paths MUST be resolved with `Path.resolve()` relative to the crew workspace
root before use. Any path that resolves outside the workspace root MUST be rejected with a 400
error. Checking for `..` components alone is not sufficient.

### Requirement: `ref` validation
The `ref` parameter in evac requests MUST be validated against `^[a-zA-Z0-9_./-]+$` before
being passed to any git subprocess. Values beginning with `-` MUST be rejected. git invocations
MUST pass `--` before any user-supplied ref as an additional defence-in-depth measure.

### Requirement: Token expiry
Presigned URLs MUST include a server-side expiry timestamp. Expired tokens MUST be rejected
regardless of HMAC validity.

### Requirement: Path canonicalisation — known limitation
`Path.resolve()` follows symlinks. A symlink planted inside the workspace pointing outside it
would bypass the resolve-and-compare check. This is accepted as a residual risk for 0.2.0
(workspace volumes are operator-controlled; crew containers run as a non-root user). A future
hardening pass SHOULD add lstat-based symlink detection or equivalent.

---

# Delta Spec: Transport Auth

Target: `openspec/specs/crew-governance/spec.md`
Action: modify — add to auth section

---

### Requirement: Auth-disabled startup warning
When the transport starts without an API key configured, it MUST emit a WARNING-level log
entry clearly stating that all endpoints are publicly accessible. An INFO-level message is
not sufficient. The warning MUST appear before any request is served.

---

# Delta Spec: Crew Proxy

Target: `openspec/specs/crew-governance/spec.md`
Action: modify — add to proxy section

---

### Requirement: Query string sanitisation
The transport MUST sanitise query strings before forwarding them to crew gateways. At minimum,
query strings containing CR, LF, or NUL characters MUST be rejected. Re-encoding via a
parse-then-encode round-trip is required to normalise encoding. A closed parameter allowlist
is the preferred long-term approach and SHOULD be added once all proxied parameters are
documented.
