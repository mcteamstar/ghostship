# TRN-186 Angle A — Token Flow Investigation

**Investigator:** Wraith  
**Date:** 2026-10-02  
**Sources:** `kirocrew/kiro_crew/mcp_core.py`, `kirocrew/kiro_crew/session_token_sig.py`, `kirocrew/kiro_crew/mcp_gateway/claim.py`, `kirocrew/kiro_crew/mcp_gateway/session_servers.py`, `kirocrew/kiro_crew/acp/client.py`

---

## 1. `_session_token_header()` — What It Sends and Where It Gets the Token

**Location:** `mcp_core.py`

```python
def _session_token_header() -> dict[str, str]:
    from kiro_crew.session_token_sig import session_token_header

    ctx = current_caller()
    return session_token_header(ctx.session_token if ctx is not None and ctx.from_gateway else "")
```

**What it sends:** Returns a dict `{"X-Session-Token": "<token>"}`, or `{}` if no token is available. This header is attached to **every** outbound loopback gateway request — GETs, POSTs, PATCHes, PUTs, and DELETEs — via the `_send()` helper that all of `_get()`, `_post()`, `_patch()`, `_put()`, and `_delete()` route through.

**Where it gets the token — two-stage resolution:**

1. **Primary: per-call caller context** (`ctx.session_token` when `ctx.from_gateway` is True). In pooled backends, gatewayd injects a per-call `kirocrew.caller` block carrying the session token on every forwarded call. This is stamped per CALL and cannot go stale. Only used when `ctx.from_gateway` is True.

2. **Fallback: `os.environ.get(STUB_SESSION_TOKEN_ENV, "")`** — i.e. the process environment variable `KIROCREW_STUB_SESSION_TOKEN`. This is consulted inside `session_token_header()` in `session_token_sig.py` when the `token` argument passed to it is empty.

The delegation chain is: `_session_token_header()` → `session_token_sig.session_token_header(token)` → uses `token` arg if non-empty, else reads `os.environ.get("KIROCREW_STUB_SESSION_TOKEN", "")`.

**Why every request carries it:** The gateway authorizes session-scoped reads/writes based on `X-Session-Key`. A loopback TCP request has no kernel peer attestation (only the unix socket path has SO_PEERCRED), so the `X-Session-Token` header is the attestation that the declared `X-Session-Key` is correct. Omitting it causes the gateway to treat the caller as unnamed.

---

## 2. `_session_key_from_token()` in `mcp_core.py`

```python
def _session_key_from_token() -> str:
    try:
        return session_key_from_env_token()
    except Exception:
        pass
    return ""
```

This is a thin, never-raising wrapper over `session_key_from_env_token()` (in `session_token_sig.py`). It is called from both `_resolve_session_key()` (lenient) and `_resolve_session_key_strict()` (strict), placed **above** the `KIROCREW_SESSION_KEY` env var in both resolution chains. The ordering is load-bearing: after a warm-pool rekey, the env var is stale (names the previous session) while the token's signed mapping file is current.

---

## 3. `session_key_from_env_token()` in `session_token_sig.py`

```python
def session_key_from_env_token() -> str:
    try:
        from kiro_crew.mcp_gateway.claim import STUB_SESSION_TOKEN_ENV
        token = os.environ.get(STUB_SESSION_TOKEN_ENV, "")
        if not token:
            return ""
        return verify_session_token(token)
    except Exception:
        return ""
```

**What it does:**
1. Reads `KIROCREW_STUB_SESSION_TOKEN` from `os.environ`.
2. If present, calls `verify_session_token(token)` which:
   - Computes `sha256(token)` to find the mapping file at `config_dir()/session_token_<hash>.sig`.
   - Opens with `O_NOFOLLOW` (symlink-safe), checks it is a regular file, enforces a size cap.
   - Splits the file: wire format is `"<mac_hex>\n<session_key>"`.
   - Derives the signing subkey via `HMAC(sel_hmac_key, b"kirocrew.session_token.sig.v1")`.
   - Verifies the MAC over `"<token>:<session_key>"` using `hmac.compare_digest`.
   - Returns the `session_key` body on success, `""` on any failure.

**Result semantics:** Returns the actual session key string (e.g. `dashboard:chat-3-1234`) that the token maps to, or `""` on any failure. The MAC binding includes the token itself (not just the filename hash), so copying another session's mapping file to a name derived from a different token fails verification.

**Never memoised:** Explicitly documented as such. The token survives a warm-pool rekey while the mapping file is rewritten — memoising would make a rekey invisible to an already-running MCP child.

---

## 4. `KIROCREW_STUB_SESSION_TOKEN` — Inheritance Scope

**Definition:** `STUB_SESSION_TOKEN_ENV = "KIROCREW_STUB_SESSION_TOKEN"` in `mcp_gateway/claim.py`.

### Who sets it and how:

| Site | Method | Target |
|---|---|---|
| `acp/client.py` (`_apply_session_identity_env`) | `env[STUB_SESSION_TOKEN_ENV] = self._stub_session_token` | One `AcpClient` child process (the kiro-cli process driving one session) |
| `mcp_gateway/session_servers.py` (`attach_stub_session_token`) | Injects into ACP element `env` array as `{"name": ..., "value": ...}` | MCP server processes started by the gateway via the session's element array |
| `cron_script.py` | `clean_env[STUB_SESSION_TOKEN_ENV] = token` | Cron job subprocesses |
| `providers/mirrors/identity.py` | `env[STUB_SESSION_TOKEN_ENV] = session_token` | Mirror/control-plane identity env |

### Inherited by shell subprocesses?

**No — not by default.** The env var is injected **selectively** at specific spawn sites, not into `os.environ` of the MCP server process globally:

- `session_servers.py` injects it **per ACP element** (each MCP server's element array). It is present in the child environment of MCP server processes spawned from a session's element list.
- `acp/client.py` injects it into the child env for the kiro-cli process it spawns as a child (`AcpClient._apply_session_identity_env` mutates the env dict passed to `subprocess.Popen` or equivalent, **not** `os.environ`).
- `mcp_gateway/stub.py` **explicitly removes** it before exec-ing a fallback backend: `exec_env.pop(STUB_SESSION_TOKEN_ENV, None)`. The comment says: "Never hand the backend this session's stub token. It is a bearer name for the session's identity at gatewayd, and the process about to replace this one is the operator's third-party server binary."

**Consequence for shell subprocesses inside the MCP server:** An MCP server process (e.g. `kirocrew-core`) that was given `KIROCREW_STUB_SESSION_TOKEN` in its environment **will** inherit it to any shell subprocesses it spawns via `subprocess` or `os.system`, because Python subprocesses inherit the parent's `os.environ` by default unless `env=` is passed explicitly. However:

- The MCP server itself reads the token from `os.environ` (via `session_key_from_env_token()`).
- Shell subprocesses spawned BY the MCP server (e.g. `execute_bash`) would also inherit it.
- The token is stripped in `stub.py` when exec-ing a third-party backend precisely because this inheritance is a risk.

**In practice:** The var is an MCP-element-level injection. It exists in MCP server process envs (kirocrew-core, etc.) and kiro-cli child envs. It is **not** set in a user's interactive shell session and is not present in environment-cleared cron invocations by default.

---

## 5. Resolution Order Summary

Both `_resolve_session_key()` (lenient) and `_resolve_session_key_strict()` (strict) consult these sources in order:

1. **Gateway-injected per-call caller context** (`current_caller().session_key`) — pooled backends only, stamped per call.
2. **`session_key_from_env_token()`** — reads `KIROCREW_STUB_SESSION_TOKEN`, verifies the HMAC-signed mapping file → returns session key. **Above the env var** intentionally.
3. **`KIROCREW_SESSION_KEY` env var** — present in non-pooled (one-session) process envs; stale after a warm-pool rekey.
4. *(Lenient only)* **`KIROCREW_HOST_PID` → `session_pid_<pid>.txt`** walk — sandbox launcher path.
5. *(Lenient only)* **`/proc` ancestor PID walk** — walks up parent PIDs looking for `session_pid_<pid>.txt`. Excluded from strict resolver because a subagent shares its parent's process tree and would resolve to the parent's session.

---

## 6. Key Findings

1. `_session_token_header()` reads the token from **the gateway-injected per-call caller context first**, then falls back to `KIROCREW_STUB_SESSION_TOKEN` in `os.environ`. It is **not** reading the env var directly; it delegates to `session_token_sig.session_token_header()` which does the env read.

2. `KIROCREW_STUB_SESSION_TOKEN` **is** the env var that `_session_token_header()` ultimately reads (via the fallback path), and that `session_key_from_env_token()` reads for identity resolution.

3. The token is injected into **MCP server process environments** and **kiro-cli child process environments** via the element `env` array — it is **not** set in user shell sessions.

4. It **is** inherited by shell subprocesses of the MCP server (normal `os.environ` inheritance) **unless** the spawning code explicitly scrubs it (as `stub.py` does before exec-ing a third-party backend).

5. The mapping file is the live source of truth; the env var is only the **bearer** of the token. After a warm-pool rekey the env var names the old session while the mapping file names the current one — which is why `session_key_from_env_token()` is placed above `KIROCREW_SESSION_KEY` in the resolution chain.
