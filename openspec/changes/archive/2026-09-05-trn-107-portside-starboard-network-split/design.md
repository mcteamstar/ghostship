# Design: TRN-107 — Portside/Starboard Network Split

## Context

See `proposal.md` — Why for motivation.

**Current state:**
- Single Podman network `ga-net` contains: `ga-portal`, `ga-transport`, all `gs-*` crew containers, and ephemeral `ga-login-*` containers.
- `ga-transport` declared as `GA_NETWORK = "ga-net"` in both `lifecycle.py` and `server.py`.
- `install.sh` creates `ga-net` and emits it in `compose.yml` as external for both `ga-portal` and `ga-transport`.
- `podman.py` `container_create` takes a single `network: str` parameter.
- `worker_run` already uses `"netns": {"nsmode": "none"}` — no change needed.

**Final topology:**

```
  Internet / host
       │
  [ga-portal]──────────────────────────────┐
       │              ga-portside          │
  [ga-transport]                           │
       │              ga-starboard         │
  [gs-alpha]  [gs-beta]  [gs-gamma]  ...   │
  (all crews, shared)                      │
                                           │
  GA_TRANSPORT_SECRET flows on ga-portside ───┘
  (ga-transport rejects any request missing X-Transport-Token)
```

## Goals / Non-Goals

**Goals:**
- `ga-portal` cannot reach crew containers by hostname — crew containers not on `ga-portside`.
- Crew containers cannot reach `ga-portal` by hostname — `ga-portal` not on `ga-starboard`.
- Crew containers cannot reach `ga-transport` MCP routes — `GA_TRANSPORT_SECRET` token required; crew containers never have it.
- Crew containers cannot authenticate to each other's gateways — IP-bound `mc_token_5476` cookies return 403.
- `ga-transport` remains reachable from each crew via DNS on `ga-starboard`.
- `BearerAuthMiddleware` and `GA_TRANSPORT_SECRET` middleware both remain as defence-in-depth.
- Existing crews are migrated without requiring operator intervention.
- Simple, static network model — no dynamic network create/destroy per crew.

**Non-goals:**
- Block crew containers from reaching `ga-transport` at the TCP layer — crews are on `ga-starboard` and can dial `ga-transport`. The `GA_TRANSPORT_SECRET` middleware closes this at the application layer.
- Firewall or iptables rules — Podman rootless mode has limited network policy support.
- Per-crew DNS isolation — not needed; the token and cookie controls are the relevant security barriers.

## Decisions

### D1: Network topology — shared ga-starboard (not per-crew)

**Choice:** `ga-portside` (static, portal↔transport only) + `ga-starboard` (static, transport↔all crews).

**Rationale:** Per-crew networks were the original design (D6 below covers the comparison). The security goals — close crew→portal, close crew→transport MCP, close crew→crew — are all achieved by the token and cookie controls. Per-crew networks add dynamic create/destroy on every launch/nuke, transport reconnect operations, and `peer_crews` wiring complexity. None of these costs provide additional security benefit beyond what `GA_TRANSPORT_SECRET` and IP-bound cookies already provide. Shared `ga-starboard` is operationally simpler and equally secure.

### D2: GA_TRANSPORT_SECRET — always present, always enforced

**Choice:** Generate at install time (`openssl rand -hex 32`). Store as Podman secret `ga-transport-secret`. Mount into `ga-transport` at `/run/secrets/ga-transport-secret`. Inject into `ga-portal` as env var `GA_TRANSPORT_SECRET`.

**Caddy config** adds header on ALL upstream requests (MCP, files, dashboard, health — every route):
```
header_up X-Transport-Token {env.GA_TRANSPORT_SECRET}
```

**Transport middleware** rejects any request missing `X-Transport-Token` with 401. This check runs before `BearerAuthMiddleware` — it is the outermost gate. Crew containers on `ga-starboard` never receive `GA_TRANSPORT_SECRET` and cannot forge the header.

**Transport startup** loads the secret via `_load_transport_secret()` — same pattern as `_load_api_key()`. The secret is registered with the redaction filter so it never appears in logs.

**GA_API_KEY** remains optional — it is external client auth at the Caddy edge only. Separate concern, unchanged.

### D3: Migration path — detect and migrate on startup (Option A)

**Choice:** `_reconcile_registry` detects crews on `ga-net` and migrates each to `ga-starboard` at transport startup.

**Rationale:**
- Option B (nuke required) forces operators to destroy crew workspaces on upgrade — too disruptive.
- Option C (parallel support) adds ongoing complexity and indefinite support burden.
- Option A is a one-time cost at the first startup after the upgrade.

**Migration algorithm in `_reconcile_registry`:**
1. For each crew in registry, call `container_networks(container)`.
2. If `ga-starboard` already present: skip — no migration needed.
3. If `ga-net` present but `ga-starboard` absent:
   1. `podman.network_connect("ga-transport", "ga-starboard")` (idempotent — transport is already on starboard after compose restart, but call is safe to repeat)
   2. Stop container.
   3. `podman.network_disconnect(container, "ga-net")` (best-effort).
   4. `podman.network_connect(container, "ga-starboard")`.
   5. Start container → `_wait_gateway` → refresh cookie.
4. After all crews processed, if `ga-net` exists and is empty: `podman.network_rm("ga-net")` (best-effort, log warning on failure).

### D4: DNS — does ga-transport resolve gs-* on ga-starboard?

**Yes.** When `gs-{crew_id}` joins `ga-starboard`, it is resolvable as `gs-{crew_id}` from any container also on that network, including `ga-transport`. The transport dials `http://gs-{crew_id}:5476` and this continues to work unchanged.

**Crew→crew:** `gs-alpha` CAN resolve `gs-beta` by hostname on `ga-starboard`. However, `gs-beta`'s gateway port 5476 uses IP-bound `mc_token_5476` cookies. Empirically confirmed: a cross-crew request returns 403. This is the crew→crew control.

**Crew→portal:** `ga-portal` is NOT on `ga-starboard`. Crew containers cannot resolve `ga-portal` by hostname.

### D5: Worker containers — no network (unchanged)

`worker_run` already uses `"netns": {"nsmode": "none"}`. Workers mount the crew volume read-only and run git/Python commands with no network access. Unchanged.

### D6: Why NOT per-crew networks

**Per-crew design (previous):** Each crew gets its own `ga-crew-{crew_id}` network. Transport joins every per-crew network dynamically. Stronger DNS isolation — `gs-alpha` cannot resolve `gs-beta`.

**Shared starboard (final):** All crews share `ga-starboard`. Simpler lifecycle. `GA_TRANSPORT_SECRET` closes crew→transport MCP. IP-bound cookies close crew→crew session auth (confirmed: 403 empirically).

**Decision:** The DNS isolation benefit of per-crew networks is real but not the relevant security boundary. The actual threats are: (a) crew→portal API hijack, closed at network layer; (b) crew→transport MCP, closed by `GA_TRANSPORT_SECRET`; (c) crew→crew, closed by IP-bound cookies. Per-crew networks add significant operational complexity — dynamic network lifecycle, transport reconnect calls, `peer_crews` parameter, peering asymmetry — without neutralising any remaining threat. Shared starboard is correct.

### D7: podman.py — network_connect / network_disconnect / container_networks

Three new methods needed for migration (D3) and the container assignment changes:

- `network_connect(container, network)` — `POST /libpod/networks/{network}/connect`
- `network_disconnect(container, network)` — `POST /libpod/networks/{network}/disconnect`
- `container_networks(container) -> list[str]` — parse `NetworkSettings.Networks` from `container_inspect`

`container_create` keeps `network: str` (single network per container — all crew containers go to `ga-starboard`, login containers go to `ga-starboard`). No signature change required.

### D8: Constant naming

Replace `GA_NETWORK = "ga-net"` with two static constants:

```python
GA_PORTSIDE_NETWORK = "ga-portside"
GA_STARBOARD_NETWORK = "ga-starboard"
```

Defined in `lifecycle.py` (authoritative), imported by `server.py` and any other module that references network names. No dynamic naming functions needed — both networks are static.

### D9: GA_TRANSPORT_SECRET redaction

The secret is registered with the transport's log redaction filter on startup (same mechanism as `GA_API_KEY`). It must never appear in any log line, error message, or debug trace. The `_load_transport_secret()` function follows the same pattern as `_load_api_key()`: reads from `/run/secrets/ga-transport-secret`, raises `RuntimeError` with a safe message if absent, registers the value with the redactor.

## Risks / Trade-offs

**[Risk] Crew containers can DNS-resolve and dial ga-transport on ga-starboard** → Mitigation: `GA_TRANSPORT_SECRET` middleware rejects all requests missing `X-Transport-Token`. Crew containers never receive the secret. `BearerAuthMiddleware` remains as a second layer.

**[Risk] Crew containers can DNS-resolve each other on ga-starboard** → Mitigation: IP-bound `mc_token_5476` cookies return 403 for cross-crew attempts. Confirmed empirically.

**[Risk] GA_TRANSPORT_SECRET leaks into logs** → Mitigation: registered with redaction filter at startup. Never passed as a CLI argument or environment variable visible in `ps`.

**[Risk] Migration stop/start causes brief crew downtime** → Mitigation: `_reconcile_registry` already restarts stopped crews; migration uses the same code path. Downtime is bounded by `_wait_gateway` (30s timeout per crew).

**[Risk] `ga-net` removal fails if a container still references it** → Mitigation: removal is best-effort and logged as a warning; transport does not fail to start.

**[Risk] Tests that mock GA_NETWORK** → Tests patching `GA_NETWORK` on `lifecycle` and `server` must be updated to patch `GA_PORTSIDE_NETWORK` and `GA_STARBOARD_NETWORK`. Bounded test-only change.

**[Trade-off] Crew containers can resolve each other by hostname** → Accepted. DNS visibility without auth is not a meaningful attack vector — the auth controls (cookies, `GA_TRANSPORT_SECRET`) are the actual barrier. The per-crew DNS isolation was defence-in-depth at a level that is not needed given the other two controls.

## Migration Plan

1. **Install upgrade** (`install.sh` re-run):
   - Creates `ga-portside` and `ga-starboard` (both idempotent).
   - Generates `ga-transport-secret` Podman secret (idempotent — skip if already exists).
   - Recreates `ga-transport` container (now on both portside and starboard in compose) and `ga-portal` container (portside only).
   - Updates Caddy config to inject `X-Transport-Token` header on all upstream requests.
   - Existing `ga-net` left in place — may still have crew containers attached.

2. **Transport startup** (`_reconcile_registry`):
   - Detects any `gs-{crew_id}` container on `ga-net` but not `ga-starboard`.
   - For each such crew: connects transport to starboard (idempotent), migrates container (disconnect `ga-net`, connect `ga-starboard`), starts, waits, refreshes cookie.
   - After all crews migrated, removes `ga-net` if empty (best-effort).

3. **Rollback**:
   - Re-run the previous `install.sh` version to restore `ga-net` and use old images.
   - Old transport's `_reconcile_registry` does not know about `ga-starboard` — will not disconnect crews. Containers may have an extra network attached. Harmless for rollback.
   - Clean rollback: `podman network connect ga-net <container>` for each crew, then remove `ga-starboard` and `ga-portside` when empty.

## Open Questions

None — all design questions resolved above.
