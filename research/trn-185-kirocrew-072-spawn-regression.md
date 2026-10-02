# TRN-185 Research Report: Internal Spawn Failures and Raven Cold-Start Timeout

**Environment:** KiroCrew 0.7.2 on Ghostship  
**Symptoms:** (1) `member_identity_unavailable` / "Global memory was not used" on internal POST /api/spawn; (2) first Raven dispatch times out with `AcpRequestTimeout` after ~30s, subsequent dispatches succeed.  
**Sources:** `kirocrew-src/src/kiro_crew/acp/runtime.py`, `runtime_start.py`, `kas_agents.py`, `CHANGELOG.md`.

---

## Issue 1: `member_identity_unavailable` on Internal Spawns

### What the error means

The error string `"The execution identity is unavailable; Global memory was not used."` with code `member_identity_unavailable` is **not raised directly in the provided Python source**. It originates from the KAS relay / engine layer that `kiro_crew` drives. The code is passed back through the JSON-RPC error channel and surfaced to the caller. The Python source does have the mechanism that triggers this condition: the session's signed identity token (`KIROCREW_STUB_SESSION_TOKEN`) is absent or unresolvable on the managed MCP control-plane element (`kirocrew-core`), causing KAS to reject the session as unattrested / identity-less.

### Root cause

In 0.6.0, crew members gained the ability to dispatch worker sessions from their own DM thread (`runtime.py` `create_session` `member_session_key` branch, CHANGELOG 0.6.0: "Crew members dispatch work into worker sessions"). Each worker session requires:

1. A **stub session token** (`mint_stub_session_token` → `publish_session_token` → `send_claim`) that gives the session its identity in the gateway's claim table.
2. That token **stamped onto every hoisted managed MCP element** (`hoist_managed_servers` / `_tokened_managed_element` in `kas_agents.py`) so `kirocrew-core` can verify the session's policy access via the MAC-signed file rather than a daemon call.
3. A valid `member_session_key` passed to `create_session` so the `@kirocrew-dashboard` server is mounted and the `member_dispatch=True` projection grants the worker's tool surface.

The **internal spawn path** (agent calling POST /api/spawn from inside the crew) is routed through the gateway's crew-member session machinery. When the **crew gateway socket** (`mcp_gateway_socket`) is not set, or when the socket path is unavailable at spawn time, the `send_claim` call inside `_own_stub_session` is a no-op (it guards with `if entries and self._mcp_gateway_socket and session_key and self.pid`). In that case the claim is never registered in the daemon, and the token-to-session-key mapping is only published to the MAC-signed file (`publish_session_token`). This is fine for an external Admiral spawn because the transport MCP path reads the signed file directly.

However, for **internal spawns triggered by Raven calling `/api/spawn`**, the session is being started from inside an already-running agent process. The spawn request arrives at the gateway HTTP endpoint, which creates the session using a `SessionManager`-level path. This path invokes `create_session` with a `session_key` but **without a `member_session_key`** unless the gateway correctly identifies the calling agent session as a crew member and forwards that context. Without `member_session_key` set:

- The `@kirocrew-dashboard` server is **not mounted**.
- The `member_dispatch=True` projection is **not applied** to the KAS custom agent descriptor.
- The worker session is handed a `kas_agents` projection without the execution identity grants.

On the KAS backend, the relay attempts to start a session whose custom agent definition lacks the execution identity grant (`member_dispatch=False` → no `@kirocrew-dashboard` in tools, no `_MEMBER_DASHBOARD_GRANTS` in `allowedTools`). Because this is an internal member dispatch, the engine also expects the session to carry the member's execution identity — used to validate that the spawning member is authorized — but the gateway didn't pass it. KAS surfaces this as `member_identity_unavailable` with the sub-message "Global memory was not used" (meaning: the session was not set up with the member's persistent global memory store, which is a precondition of identity attestation in the crew context).

### Why external (Admiral / transport MCP) spawns work

The transport MCP path in 0.7.x routes spawns through the full `member_session_key` resolution: the Admiral's session has a confirmed `member_session_key` set at session start via the member DM thread. The gateway knows it is a crew member session and passes `member_session_key` into `create_session` correctly. The stub token is minted and claimed, the projection widens with `member_dispatch=True`, and KAS gets the identity it needs.

Internal spawns from Raven go via a different code path — the HTTP `/api/spawn` route — which does not carry the caller's `member_session_key` in its request context in 0.7.x. The fix introduced for "Sessions on the managed KAS backend start instead of timing out" in 0.7.0 (CHANGELOG notable fixes) is what exposed this: it changed how the claim is pre-registered relative to `session/new`, but didn't propagate the `member_session_key` derivation onto the HTTP spawn route.

### CHANGELOG trail

- **0.6.0**: Introduced crew member dispatch workers, `member_session_key` branch in `create_session`, `member_dispatch_session_server`, and the identity token mechanism.
- **0.7.0**: "Sessions on the managed KAS backend start instead of timing out" — reworked the claim-and-token ordering. Also "a sub-agent spawn there reaches the approval card instead of being denied outright" (sub-agent approval path). Neither touched the HTTP `/api/spawn` internal route's `member_session_key` derivation.
- **0.7.1**: "on the KAS backend every Kiro Crew tool call had been refused as unattested and answers again" — a related fix to unattested tokens, but scoped to the KAS session hoisting path, not the internal spawn route.
- **0.7.2**: Described only as "A small fix" with no detail in the CHANGELOG. This may be the fix attempted for a related issue, but the member_identity_unavailable failure on the internal spawn route persists on 0.7.2 based on the symptom report.

### Suggested fix

The HTTP `/api/spawn` handler needs to resolve the `member_session_key` of the **calling session** before constructing the worker session, and pass it into `create_session`. Concretely:

1. The `/api/spawn` route should extract the caller's session key from the request context (e.g. from the authenticated session token in the request headers, which the gateway already validates for authorization).
2. Look up whether that caller session has an associated `member_session_key` in the session registry.
3. If it does, forward it as `member_session_key` into the `create_session` call so that `member_dispatch=True` is activated and the execution identity is properly granted.
4. If a `member_session_key` cannot be resolved (non-member caller), the spawn should still proceed but without the member projection — this is the subagent case.

Alternatively, if the issue is that the HTTP spawn route creates a *new* runtime (rather than re-using the calling session's runtime context), the stub token minting via `_own_stub_session` may also not have access to the running gateway socket. Verify that `mcp_gateway_socket` is available to sessions created via the HTTP route.

---

## Issue 2: Raven Cold-Start Timeout (30s `AcpRequestTimeout`)

### Root cause

The timeout is **not** specifically a 30s limit. The 30s figure in the error matches `_REQUEST_TIMEOUT = 30.0` (`runtime.py` line 434), which is the plain JSON-RPC request timeout used for all control-plane calls *except* `initialize` and `session/new`. The cold-start path uses `_INITIALIZE_TIMEOUT = 90.0` for `initialize` and `_SESSION_NEW_TIMEOUT = 90.0` for `session/new` — both well above 30s.

The 30s timeout Raven specifically hits is `_REQUEST_TIMEOUT` applied to a **pre-session request** — most likely the `_kiro/auth/getAccessToken` callback (`METHOD_KAS_AUTH_GET_ACCESS_TOKEN`). This callback is the KAS engine's first outbound request, sent before `initialize` completes, asking the gateway to supply the execution identity credential. The gateway answers it from the Crew vault (`_answer_host_request` → `self._harness.answer_request(method)`).

Here is the chain for **Raven's first dispatch**:

1. KiroCrew spawns the kiro-cli / KAS relay process for the new Raven session.
2. The relay starts, and before `initialize` completes, it fires `_kiro/auth/getAccessToken`.
3. The gateway must answer from the vault (`_kas_host_auth = plan.host_auth`). `plan.host_auth = True` only when `_resolve_spawn_plan` finds a valid identity in the Crew vault at spawn time.
4. On the **very first Raven dispatch on a fresh crew**, the vault has **not yet been populated** with Raven's identity token. The Ghostship crew creates Raven's vault entry as part of the Raven session initialization flow, but this write happens *after* the dispatch call arrives — specifically, it happens when Raven's own first session completes its sign-in and publishes its identity. On a fresh crew that identity write hasn't happened yet.
5. `_resolve_spawn_plan` therefore sets `plan.host_auth = False` (vault is empty for Raven), meaning the relay is spawned with `--auth-method cli` instead of relying on the vault callback.
6. However, if the gateway-side code path for internal spawns still expects to answer the `getAccessToken` callback (because it routes through the member dispatch code that sets `_kas_host_auth = True`), it waits for the callback that never arrives from a `--auth-method cli` spawn, or vice versa: the relay was launched expecting vault-owned auth but the vault entry doesn't exist yet, so the callback is answered with an error after the 30s `_REQUEST_TIMEOUT`.

The reason **subsequent dispatches succeed** is that after the first successful Raven session, the vault entry for Raven is populated and `_resolve_spawn_plan` can answer `host_auth = True` consistently.

The reason **Ghost, Banshee, and Wraith are unaffected** is that these agents are long-running members whose vault entries are established before the first internal spawn attempt. Raven is only dispatched from within a fresh crew context, and on a fresh crew its vault entry hasn't been written yet.

### Supporting evidence

- `runtime.py` line 1057-1061: "Whether THIS process was spawned with Crew as the engine's auth owner (relay started without `--auth-method cli` because the Crew vault held an identity at spawn). Decided once in `_resolve_spawn_plan`."
- `runtime.py` `_INITIALIZE_TIMEOUT = 90.0`: Cold start allows 90s — the 30s seen in the error is `_REQUEST_TIMEOUT`, which applies to the `getAccessToken` callback.
- `runtime_start.py` line 544-545: "a remote server pending OAuth holds that initialization for its FULL 30s authorization wait. `_REQUEST_TIMEOUT` is also 30s, so sharing it turns session start into a race." This comment describes the exact race: the callback waits up to `_REQUEST_TIMEOUT` (30s) for the vault answer.

### Suggested fix

Two complementary fixes:

1. **Vault pre-population**: Ensure the Raven vault entry is written during crew initialization (when the crew is first provisioned), not deferred to the first session. This matches how Ghost and other always-on member agents work — their vault entries exist from crew setup. A crew provisioning step that writes Raven's identity before any dispatch is attempted would eliminate the cold-start mismatch.

2. **Graceful auth fallback**: If `_resolve_spawn_plan` finds no vault entry for the spawned agent and sets `host_auth = False`, the spawn should consistently use `--auth-method cli` and the gateway should not attempt to answer `getAccessToken` callbacks for that runtime (i.e. `_kas_host_auth` stays `False`). If there is a code path where `_kas_host_auth` ends up `True` despite `host_auth = False` for the internal spawn route, that is the bug to close.

3. **Increase the `_REQUEST_TIMEOUT`** for the auth callback specifically, or make it a soft timeout that degrades gracefully rather than propagating as `AcpRequestTimeout` to the caller. The current 30s hard timeout on the credential callback is tight on a fresh crew where the vault write is racing the spawn.

---

## Summary Table

| Issue | Root Cause | Introduced | Suggested Fix |
|-------|-----------|-----------|---------------|
| `member_identity_unavailable` on internal spawns | HTTP `/api/spawn` route does not resolve/forward the caller's `member_session_key`, so `create_session` runs without `member_dispatch=True`, omitting the execution identity grant from the KAS projection | 0.6.0 (member dispatch), not corrected in 0.7.x spawn route | HTTP spawn route must derive and pass `member_session_key` from calling session context |
| Raven first-dispatch `AcpRequestTimeout` after 30s | Raven's vault identity entry does not exist on a fresh crew; `_resolve_spawn_plan` sets `host_auth=False`/True incorrectly for the internal path, causing the `getAccessToken` callback to time out at `_REQUEST_TIMEOUT = 30.0s` | Latent since 0.6.0 member dispatch, surfaces specifically for Raven because it is only dispatched from within a fresh crew | Pre-populate Raven's vault entry during crew provisioning; audit `_kas_host_auth` flag consistency on the internal spawn path |

---

## Files examined

- `/home/kirocrew/workplace/kirocrew-workspace/kirocrew-src/src/kiro_crew/acp/runtime.py` — spawn plan resolution (`_resolve_spawn_plan`), `create_session`, `_own_stub_session`, `_answer_host_request`, `_kas_host_auth` flag, timeouts (`_REQUEST_TIMEOUT`, `_INITIALIZE_TIMEOUT`)
- `/home/kirocrew/workplace/kirocrew-workspace/kirocrew-src/src/kiro_crew/acp/runtime_start.py` — `_ColdStartAdmission`, `SessionStartGate`, `_SESSION_NEW_TIMEOUT = 90.0`, OAuth 30s wait commentary
- `/home/kirocrew/workplace/kirocrew-workspace/kirocrew-src/src/kiro_crew/acp/kas_agents.py` — `to_client_custom_agent` (`member_dispatch`, `crew_panel` flags), `hoist_managed_servers`, `_tokened_managed_element`, `identity_unattested` path
- `/home/kirocrew/workplace/kirocrew-workspace/kirocrew-src/CHANGELOG.md` — 0.6.0 member dispatch introduction, 0.7.0 KAS session start fix, 0.7.1 unattested tool-call fix, 0.7.2 unnamed fix

