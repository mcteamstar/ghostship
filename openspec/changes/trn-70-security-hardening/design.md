# TRN-70 Design — Security Hardening

## D1: Full-length HMAC (C-1)

Three sites in `transport/server.py`:

```python
# Before (all three sites):
sig = hmac.new(...).hexdigest()[:32]

# After:
sig = hmac.new(...).hexdigest()
```

Sites:
- `_sign_file_url` (~line 4896)
- `_sign_upload_url` (~line 4928)
- `_verify_file_token` (~line 5358) — compare `expected` not `expected[:32]`

All three must change together. No other behaviour change. Existing tokens are invalidated
on deploy — acceptable because presigned URLs are single-use and short-lived (5 min expiry).

## D2: `ref` validation and git option terminator (C-2)

Add a `_validate_ref(ref: str) -> str` helper:

```python
_REF_RE = re.compile(r"^[a-zA-Z0-9_./-]+$")

def _validate_ref(ref: str) -> str:
    """Validate a git ref/range. Raises ValueError on invalid input."""
    if not ref:
        return ref
    if not _REF_RE.match(ref):
        raise ValueError(f"Invalid ref: {ref!r}")
    return ref
```

Call it:
1. In `evac()` (MCP tool) before `_sign_file_url` — rejects at the tool layer.
2. In `_handle_file_get` before the git exec — defence-in-depth at the HTTP layer.

Also add `--` before `ref` in all git invocations:
```python
# bundle:
["git", "-C", repo_root, "bundle", "create", bundle_path, "--", bundle_ref]
# diff:
["git", "-C", repo_path, "diff", "--", ref, "--", file_path]
```

## D3: Path canonicalisation (H-1)

Replace the `".." in clean.split("/")` check with a canonical resolution check:

```python
def _safe_path(workspace_root: Path, user_path: str) -> Path:
    """Resolve user_path under workspace_root and raise if it escapes."""
    clean = user_path.lstrip("/")
    resolved = (workspace_root / clean).resolve()
    try:
        resolved.relative_to(workspace_root.resolve())
    except ValueError:
        raise ValueError(f"Path escapes workspace root: {user_path!r}")
    return resolved
```

Apply in:
- `evac()` and `supply()` MCP tool functions
- `_handle_file_get` and `_handle_file_put` HTTP handlers

## D4: Operation-typed HMAC payloads (H-2)

Prefix the payload with the operation type so GET and PUT tokens are non-interchangeable:

```python
# _sign_file_url (download):
payload = f"get:{crew_id}:{clean}:{ref or ''}:{int(bundle)}:{expires}"

# _sign_upload_url (upload):
payload = f"put:{crew_id}:{clean}:{mode}:{expires}"

# _verify_file_token — pass operation as parameter:
def _verify_file_token(token: str, sig: str, crew_id: str, path: str,
                       operation: str, ...) -> bool:
    payload = f"{operation}:{crew_id}:{path}:..."
    expected = hmac.new(...).hexdigest()
    return hmac.compare_digest(sig, expected)
```

`_handle_file_get` passes `operation="get"`, `_handle_file_put` passes `operation="put"`.

## D5: Auth-off warning (H-3)

In `_configure_auth()` (or equivalent startup path):

```python
if not GA_API_KEY:
    logger.warning(
        "GA_API_KEY is not set — transport is running WITHOUT authentication. "
        "All MCP tools and file endpoints are publicly accessible. "
        "Set GA_API_KEY to require Bearer token auth."
    )
```

Change existing `logger.info("Auth disabled")` to `logger.warning(...)`.

## D6: Query string allowlist (H-4)

In the crew proxy handler, replace raw query string forwarding:

```python
# Before:
upstream_url = f"{gateway_url}{path}?{raw_query}"

# After:
PROXY_QUERY_ALLOWLIST = {"timeout", "agent", "task_id"}  # extend as needed

def _safe_proxy_query(raw: str) -> str:
    """Forward only allowlisted, control-char-clean query params."""
    if any(c in raw for c in ("\r", "\n", "\x00")):
        return ""
    params = parse_qs(raw, keep_blank_values=True)
    safe = {k: v for k, v in params.items() if k in PROXY_QUERY_ALLOWLIST}
    return urlencode(safe, doseq=True)

upstream_url = f"{gateway_url}{path}?{_safe_proxy_query(raw_query)}"
```

## Affected Files

- `transport/server.py` — all fixes
- `tests/unit/test_transport.py` — new tests for each fix
- `openspec/specs/file-transfer-security/spec.md` — new spec (delta)
