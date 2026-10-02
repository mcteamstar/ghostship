# TRN-186 Angle D — Transport Attestation Gap

**Investigator:** Wraith  
**Date:** 2026-10-02  
**Angle:** D — How does the transport POST /api/spawn, what headers does it carry, does it hold a session token, and is there a REST path external callers can use differently?

---

## 1. The Dispatch Call: Headers Sent by the Transport

### 1.1 Primary path: `_crew_api` / `_crew_api_with_recovery`

Every time the transport sends a task to a crew's gateway, it goes through `_crew_api` in `transport/lifecycle.py` (lines 225–232):

```python
def _crew_api(crew: dict, method: str, path: str, **kw: Any) -> Any:
    url = _crew_url(crew)
    r = _http.request(
        method, f"{url}{path}",
        headers={"Cookie": _crew_cookie(crew), "Origin": url},
        **kw,
    )
    r.raise_for_status()
    return r.json()
```

**Exactly two headers are sent:**

| Header | Value | Purpose |
|--------|-------|---------|
| `Cookie` | `mc_token_5476=<session_cookie>` | Gateway session authentication |
| `Origin` | `http://gs-<crew_id>:5476` | CSRF origin check |

**No session token is present.** There is no `X-Session-Key`, no `Authorization`, no `X-Internal-Secret`, no `X-Caller` or attestation header of any kind. The transport authenticates to the gateway **purely via the session cookie** (`mc_token_5476`), which was minted by `_mint_cookie` using a gateway token issued by `kirocrew token --ttl 24h`.

### 1.2 The POST body

The body sent to `POST /api/spawn` is built in `dispatch()` (`server.py` ~line 3760):

```python
body = {"task": task, "agent": agent, "keep": True}
if model is not None:
    body["model"] = model
# Optionally:
body["parent_session"] = "dashboard:<slot_name>"  # if slot is set
```

The body fields:
- `task` — the task string
- `agent` — persona name (ghost, spectre, etc.)
- `keep` — always `True` (makes the run continuable)
- `model` — optional model override
- `parent_session` — optional `"dashboard:<slot>"` string when a slot is resolved

**No session token in the body.** No `X-Session-Key` is included. No attestation data.

### 1.3 Idle monitor path (monitors.py ~line 245)

The schedule monitor fires jobs via the same `_crew_api_with_recovery` call:

```python
tick_body = {"task": ..., "agent": ..., "keep": True}
_crew_api_with_recovery(crew, crew_id, "POST", "/api/spawn", json=tick_body)
```

Same two headers (`Cookie` + `Origin`), same body shape, no session token.

The idle-monitor GET /api/spawn liveness check uses the same cookie + Origin pattern. No attestation.

---

## 2. What the Gateway's `/api/spawn` Actually Checks

The KiroCrew gateway's `POST /api/spawn` handler (`kiro_crew/dashboard/handlers/messaging.py`) accepts requests from two caller classes:

| Class | Auth mechanism | Header |
|-------|---------------|--------|
| Internal (MCP loopback processes, CLI) | `X-Internal-Secret` constant-time match | `X-Internal-Secret` |
| Browser / dashboard owner | Session cookie | `Cookie: mc_token_5476=...` |

`/api/spawn` is in `_MIXED_INTERNAL_API_PATHS` — it accepts **both** internal-secret callers and cookie-auth callers (`kiro_crew/dashboard/server.py` line 884).

The transport's cookie-only approach means it presents itself as a **browser/dashboard-owner caller**. This is the key architectural fact: the transport holds no `X-Internal-Secret` and sends no `X-Session-Key`, so it is treated as a cookie-authenticated non-internal caller.

**Consequence for the spawn scope check:** The `_spawn_scope_refusal` check applies to internal callers (those with `internal_auth = True`). The transport is a cookie caller so `internal_auth` is not set — `_spawn_scope_refusal` returns `None` immediately (it's the "dashboard owner's own surface"). The scope check does not apply to the transport.

**Consequence for `member_session_key`:** The `_is_host_cli_spawn` check (which infers whether the caller is the operator's CLI) returns `False` for the transport's cookie-auth path because `internal_auth` is not `True`. This means the transport spawn goes through the `internal_memory_scope(request, "spawn.create", claimed_session=parent_session)` path with `parent_session = "dashboard:<slot>"` or `""`. The transport never provides a `member_session_key` because it has no concept of one — it just supplies a cookie and a parent_session string.

---

## 3. The External REST API Path

### 3.1 The route

The transport exposes `_handle_crew_api_proxy` at `GET/POST /crews/{crew_id}/api/{path}` (`server.py` lines 1285+). This route proxies requests **through** the transport to the crew gateway at `http://gs-{crew_id}:5476/api/{path}`.

**For `POST /crews/{crew_id}/api/spawn`:**

1. The inbound request must pass `BearerAuthMiddleware` (when `GA_API_KEY` is set), which checks `Authorization: Bearer <key>` at the transport level.
2. The following headers are **stripped** before forwarding to the gateway (`_STRIPPED_CREW_PROXY_HEADERS`):
   - `host`
   - `cookie`
   - `authorization`
   - `x-transport-token`
3. The transport **injects** its own `Cookie: mc_token_5476=<session_cookie>` into the forwarded request.
4. All other inbound headers pass through.

**So an external caller:**
- Authenticates to the transport with `Authorization: Bearer <GA_API_KEY>`
- Their `Authorization` header is stripped before reaching the gateway
- The transport substitutes its own session cookie
- The gateway receives a cookie-auth request identical to what the MCP dispatch path sends

This means an external REST caller ends up in the same position as the internal MCP `dispatch()` call: cookie-only auth at the gateway, no session key, no attestation.

### 3.2 No dedicated external-dispatch endpoint

There is no separate REST endpoint that offers a different trust level or session identity for external callers. The `/crews/{crew_id}/api/spawn` proxy and the MCP `dispatch()` tool both converge on the same cookie-auth POST to the gateway.

---

## 4. What Changed in 0.7.0 That Broke External Dispatches

### 4.1 The old fence (pre-0.7.0 / pre-0.6.0)

In the CHANGELOG entry for **0.6.0** (notable breaking changes, emphasis mine):

> **The command gate no longer fences credential paths by reading the command text**: the sandbox's bind masks are the fence now, so check that `agent.sandbox` in `config.json` is not `off` if you were relying on that text gate.

And the `lifecycle.py` comment at line ~1020 (in `_patch_crew_config`) confirms:

```python
# ``sandbox: "off"`` left no protection. ``sandbox_allow_unsandboxed_exec: true``
# is the explicit opt-in for hosts that cannot sandbox: it skips only
# the failing bind-mount step while keeping all other credential guards
# in place.
```

Pre-0.7.0 (specifically pre-0.6.0), the gateway used **text-based credential scanning** as an additional fence alongside the sandbox bind masks. When `agent.sandbox` was `"off"` (as it must be for rootless Podman containers), the text-based fence still provided a guard on what credentials could be accessed.

**0.6.0 removed the text-based credential gate.** The bind masks became the sole fence.

### 4.2 What 0.7.0 introduced: `sandbox_allow_unsandboxed_exec`

The `lifecycle.py` comment (lines 1017–1022) makes the ghostship side explicit:

```python
# ``sandbox_allow_unsandboxed_exec=True`` is the correct rootless escape
# hatch introduced in KiroCrew 0.7.0. Podman rootless cannot perform
# user-namespace bind mounts (errno EPERM), so we must opt out of the
# inner namespace sandbox. In 0.7.0 the text-based credential gate was
# removed — bind masks are now the only fence — so the prior ``sandbox:
# "off"`` left no protection.
```

So in 0.7.0:
- `sandbox: "off"` was previously a valid rootless escape that still had the text gate as backup
- 0.7.0 removed the text gate entirely
- The new escape hatch is `sandbox_allow_unsandboxed_exec: true`, which **skips only the bind-mount step** while keeping other guards

Ghostship sets `sandbox_allow_unsandboxed_exec: true` in `_patch_crew_config` to accommodate rootless Podman.

### 4.3 The session token / attestation gap

The bigger 0.7.0 change relevant to dispatch attestation is the **stub session token / member identity mechanism** — documented in TRN-185's findings:

- **0.6.0** introduced crew member dispatch with `member_session_key`, `mint_stub_session_token`, `publish_session_token`, and the claim/attestation system.
- **0.7.0** reworked the claim-and-token ordering ("Sessions on the managed KAS backend start instead of timing out") but **did not update the HTTP `/api/spawn` route** to derive and forward `member_session_key` from the calling session.

The transport's `dispatch()` and the `_handle_crew_api_proxy` path both produce cookie-authenticated POSTs with no `X-Session-Key`. The gateway's `/api/spawn` handler, on receiving a cookie-auth call, does not associate the request with a crew-member identity (`member_session_key` is never derived for the transport's path).

This means:
- Pre-0.6.0: no member identity concept existed; all spawns were equivalent.
- Post-0.6.0: internal MCP spawns (from agents calling `spawn_run`) carry session identity via `X-Session-Key` + `X-Internal-Secret`. Transport cookie-auth spawns (from ghostship) do not.
- Post-0.7.0: the KAS backend stricter attestation requirements mean an identity-less spawn (as seen from the transport's cookie-auth path) either raises `member_identity_unavailable` or proceeds without member execution context depending on the requesting session type.

**The specific breakage:** When the transport dispatches via the cookie path, the gateway creates a session without a `member_session_key`. On KAS, this means:
1. `member_dispatch=False` → no `@kirocrew-dashboard` server mounted
2. No execution identity granted to the KAS custom agent descriptor
3. The session cannot attest itself to KiroCrew's own MCP tools (e.g. `kirocrew-core`)
4. Crew tools like `spawn_run`, `cron_add`, etc. fail with attestation errors inside the dispatched task

**The transport does not use `X-Internal-Secret`** because it has no access to the gateway's internal secret (that secret lives inside the container; the transport authenticates externally via the minted cookie, not via the gateway's own IPC secret).

---

## 5. Is There a Different External Caller Path?

**Short answer: no.** There is no endpoint or auth mechanism that gives an external caller (including the transport itself) a different trust level or session identity at the gateway.

The available paths and their trust levels:

| Caller | Auth to transport | Auth at gateway | Identity at gateway |
|--------|------------------|-----------------|---------------------|
| Transport MCP `dispatch()` | N/A (same process) | `Cookie: mc_token_5476=...` | None (cookie-auth, no session key) |
| External REST via `/crews/{id}/api/spawn` | `Authorization: Bearer <GA_API_KEY>` | `Cookie: mc_token_5476=...` (injected by transport) | None (same as above) |
| Agent in container calling `/api/spawn` via MCP | `X-Internal-Secret` | `X-Internal-Secret` | `X-Session-Key` (set by MCP server layer) |
| Agent CLI (`kirocrew spawn run`) | `X-Internal-Secret` | `X-Internal-Secret` | No `X-Session-Key`, no `parent_session` |

The transport has no way to obtain or forward `X-Internal-Secret` (it is a per-container-startup random value stored as `app["local_secret"]` inside the gateway process, not accessible externally). The transport has no way to set `X-Session-Key` because it has no session identity within the gateway.

---

## 6. Summary of the Attestation Gap

The gap is structural:

1. The transport authenticates to the gateway via a **minted session cookie** — an external credential that maps to the dashboard-owner role, not to any crew member identity.
2. The gateway's `/api/spawn` handler, when called with cookie auth, creates sessions without `member_session_key`, so the spawned task runs without crew member execution context.
3. In KiroCrew ≥0.6.0, crew-member identity is required for the spawned session to access the full `kirocrew-core` MCP tool surface (it gates on attestation via the stub session token).
4. The transport has no mechanism to acquire or forward the gateway's `X-Internal-Secret`, and no mechanism to set `X-Session-Key`. These only exist for in-process callers.
5. The 0.7.0 tightening of sandbox + removal of text-based credential gate made the missing `sandbox_allow_unsandboxed_exec` flag the new required opt-in — which ghostship correctly sets. But the session/attestation gap is a separate issue that predates 0.7.0 and was exposed by the 0.7.0 KAS session start rework.

**The transport is not the right caller for attested member-identity spawns.** An attested dispatch requires the session to originate from inside the container, via `X-Internal-Secret` + `X-Session-Key`. The transport's role is container lifecycle and external routing; it cannot impersonate an in-container session with crew-member identity.

---

## 7. Files Examined

- `/home/kirocrew/workplace/kirocrew-workspace/repo/transport/lifecycle.py` — `_crew_api` (headers: Cookie + Origin only), `_patch_crew_config` (sandbox_allow_unsandboxed_exec comment)
- `/home/kirocrew/workplace/kirocrew-workspace/repo/transport/server.py` — `dispatch()` (body building, ~line 3760), `_dispatch_batch()` (~line 3088), `_handle_crew_api_proxy` (~line 1285), `_STRIPPED_CREW_PROXY_HEADERS` (~line 916), `BearerAuthMiddleware`
- `/home/kirocrew/workplace/kirocrew-workspace/repo/transport/monitors.py` — schedule/idle monitor spawn body (~line 245)
- `/home/kirocrew/workplace/kirocrew-workspace/repo/CHANGELOG.md` — ghostship version history (no 0.7.0 entry here; ghostship bumped to KC 0.6.0 image in v0.5.0)
- `/home/kirocrew/workplace/kirocrew-workspace/kirocrew/CHANGELOG.md` — KiroCrew 0.7.0 (2026-09-15), 0.6.0 breaking changes (credential gate / sandbox)
- `/home/kirocrew/workplace/kirocrew-workspace/kirocrew/kiro_crew/dashboard/handlers/messaging.py` — `api_spawn`, `_is_host_cli_spawn`, `_spawn_scope_refusal`
- `/home/kirocrew/workplace/kirocrew-workspace/kirocrew/kiro_crew/dashboard/server.py` — `_MIXED_INTERNAL_API_PATHS` (includes `/api/spawn`)
- `/home/kirocrew/workplace/kirocrew-workspace/repo/research/trn-185-kirocrew-072-spawn-regression.md` — prior angle findings for context
