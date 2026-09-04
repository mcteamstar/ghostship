# Design: TRN-107 — Portside/Per-Crew Network Split

## Context

See `proposal.md` — Why for motivation.

**Current state:**
- Single Podman network `ga-net` contains: `ga-portal`, `ga-transport`, all `gs-*` crew containers, and ephemeral `ga-login-*` containers.
- `ga-transport` is declared as `GA_NETWORK = "ga-net"` in both `lifecycle.py` and `server.py`.
- `install.sh` creates `ga-net` with `podman network exists ga-net || podman network create ga-net` and emits it in `compose.yml` as an external network for both `ga-portal` and `ga-transport`.
- `podman.py` `container_create` takes a single `network: str` parameter and sets `"Networks": {network: {}}`.
- `worker_run` already uses `"netns": {"nsmode": "none"}` — no change needed.
- `_start_login_container` in `lifecycle.py` calls `podman.network_create(GA_NETWORK)` then `"Networks": {GA_NETWORK: {}}`.

**Key constraint:** Podman per-network DNS means every container on a network can resolve every other container on that network by hostname. Per-crew private networks provide per-crew DNS namespaces: `gs-alpha` is not resolvable from `gs-beta`'s network.

```
  Internet / host
       │
  [ga-portal]
       │  ga-portside
  [ga-transport]  ← joins portside + every ga-crew-{id}
       │  ga-crew-alpha        ga-crew-beta
  [gs-alpha]                 [gs-beta]
       (isolated)              (isolated)
```

## Goals / Non-Goals

**Goals:**
- `ga-portal` cannot reach crew containers by hostname.
- Crew containers cannot reach `ga-portal` by hostname.
- Crew containers cannot reach each other by hostname (default).
- `ga-transport` remains reachable from each crew on its per-crew network.
- Explicit opt-in crew-to-crew peering is possible when the Admiral requires it.
- `BearerAuthMiddleware` remains as defence-in-depth.
- Existing crews are migrated without requiring operator intervention.

**Non-goals:**
- Prevent crew containers from reaching `ga-transport` on their per-crew network at the network layer — Podman DNS will resolve `ga-transport` from each `ga-crew-{id}` network, and that is acceptable because the transport's own auth middleware handles rejection. Full network-layer blocking of crew → transport would require additional Podman network policies not available in rootless mode.
- Firewall or iptables rules — Podman rootless mode has limited network policy support.

## Decisions

### D1: Migration path — detect and migrate on startup (Option A)

**Choice:** Option A — `_reconcile_registry` detects crews on `ga-net` and migrates each to its own `ga-crew-{crew_id}` network at transport startup.

**Rationale:**
- Option B (nuke required) forces operators to destroy crew workspaces on upgrade — too disruptive.
- Option C (parallel `ga-net` + per-crew support) adds ongoing complexity and indefinite support burden.
- Option A is a one-time cost at the first startup after the upgrade. The migration is stop → disconnect → connect → start → wait for gateway, which is already idempotent via `_ensure_crew_running`.

**Migration algorithm in `_reconcile_registry`:**
1. For each crew in registry, check if its container is attached to `ga-net` but not `ga-crew-{crew_id}` via `podman inspect`.
2. If so: create `ga-crew-{crew_id}`, connect transport to it, stop container, call `podman network disconnect ga-net <container>`, call `podman network connect ga-crew-{crew_id} <container>`, start container, wait for gateway, refresh cookie.
3. Update registry status.
4. After all crews processed, if `ga-net` has no containers left, attempt `podman network rm ga-net` (best-effort, log warning on failure).

### D2: DNS — does ga-transport resolve gs-* hostnames on per-crew networks?

**Answer: Yes.** When `gs-{crew_id}` joins `ga-crew-{crew_id}`, it is resolvable as `gs-{crew_id}` from any container also on that network — including `ga-transport`. The transport dials `http://gs-{crew_id}:5476` and this continues to work unchanged.

**Isolation benefit over shared starboard:** `gs-alpha` is NOT on `ga-crew-beta`, so it cannot resolve `gs-beta` by hostname — and vice versa. This is stronger isolation than the original shared `ga-starboard` design.

**Verification from codebase:** `_crew_url` returns `f"http://{crew['container']}:{CREW_GATEWAY_PORT}"`. Container-name DNS confirmed working per the `server.py` module docstring. No change required here.

### D3: Worker containers — no network (unchanged)

`worker_run` already uses `"netns": {"nsmode": "none"}`. Workers mount the crew volume read-only and run git/Python commands with no network access. This is correct and unchanged.

### D4: MCP catalogue containers — not managed by ghostship

The `/mcp` catalogue files are JSON descriptors mounted from the host into `ga-transport` at `/mcp:ro`. There are no "MCP catalogue containers" — the MCP servers referenced in `academy/mcp/*.json` are network-addressed external services resolved at crew runtime inside the crew container. They are not managed by ghostship and this change does not affect them.

### D5: Does ga-portal need per-crew access?

No. `ga-portal` only dials `ga-transport:{PORT}` (portside) and `ga-transport:2019` (Caddy admin API). It has no reason to reach `gs-*` containers directly. `_caddy_register_crew` targets `ga-transport:8000` not `gs-*` (confirmed in `server.py`).

### D6: Three design options considered

**Option A — Per-crew networks, no built-in peering (rejected as incomplete)**

Each crew gets its own `ga-crew-{crew_id}` network. No mechanism for cross-crew communication. Rejected as the sole option because it provides no escape hatch for use cases where the Admiral needs to wire two crews together.

**Option B — Per-crew networks + opt-in peering via `peer_crews` (chosen)**

Same per-crew isolation as Option A, plus `launch()` gains an optional `peer_crews: list[str]` parameter. When specified, the new crew also joins each named peer's `ga-crew-{peer_id}` network. This allows explicit wiring — e.g. a coordinator crew that needs to reach worker crews directly. Default is no peering: `peer_crews=[]`.

Peering is asymmetric unless the peer is also launched with the caller in its `peer_crews`. The Admiral decides which crews are peered. The transport does not enforce or validate peer existence at launch time (log a warning if a peer's network does not exist).

**Option C — Shared `ga-starboard` for all crews (original design, kept for comparison only)**

Single shared network `ga-starboard` for all `gs-*` containers. Simpler to implement but weaker isolation:
- `gs-alpha` can resolve and dial `gs-beta:5476` directly.
- All crew containers can reach `ga-transport` on the same flat network.

**Recommendation: Option B.** Per-crew isolation is the correct default; opt-in peering handles the coordinator use case cleanly without compromising the default.

### D7: podman.py container_create — multi-network support

`container_create` currently takes a single `network: str`. Two approaches:

- Change the `network` parameter to `networks: list[str]`. The Podman API body `"Networks"` is already a dict — passing multiple keys is straightforward.

**Choice:** Change `container_create` to accept `networks: list[str]` and build `"Networks": {n: {} for n in networks}`. All existing call sites pass a single network today; they will pass `[f"ga-crew-{crew_id}"]` after this change. The `ContainerRuntime` ABC signature is updated accordingly.

### D8: Constant naming — dynamic per-crew names

Replace `GA_NETWORK = "ga-net"` with a single constant and a naming function:

```python
GA_PORTSIDE_NETWORK = "ga-portside"

def crew_network(crew_id: str) -> str:
    return f"ga-crew-{crew_id}"
```

`GA_PORTSIDE_NETWORK` is defined in `lifecycle.py` (authoritative) and imported by `server.py`. There is no `GA_STARBOARD_NETWORK` constant — per-crew network names are computed dynamically. `compose.yml` declares only `ga-portside` as external; per-crew networks are created and destroyed at runtime.

### D9: Network lifecycle — launch and nuke

**launch:**
1. Compute `net = crew_network(crew_id)`.
2. `podman.network_create(net)` (idempotent).
3. `podman.network_connect("ga-transport", net)` — transport joins the crew's network.
4. Create crew container with `networks=[net]`.
5. If `peer_crews` specified: for each `peer_id` in `peer_crews`, `podman.network_connect(container, crew_network(peer_id))` — connect the new crew to each peer's network (log warning if peer network doesn't exist).

**nuke:**
1. Stop and remove crew container.
2. `podman.network_disconnect("ga-transport", net)` (best-effort — transport may already have left).
3. `podman.network_rm(net)` (best-effort — log warning on failure, never raise).

## Risks / Trade-offs

**[Risk] Crew containers can still DNS-resolve `ga-transport` on their per-crew network** → Mitigation: `BearerAuthMiddleware` enforces auth on all non-exempt routes; rate limiting applies. This was always the case. The per-crew split closes crew-to-crew reachability, which is stronger than shared starboard.

**[Risk] Many active crews = many network_connect calls on transport** → Mitigation: each connect call is a fast local Podman API call. At normal scale (tens of crews) this is negligible. At very high scale (hundreds) a future optimisation could batch this.

**[Risk] Asymmetric peering confusion** → Mitigation: document that `peer_crews` is one-directional. If bidirectional peering is needed, both `launch()` calls must name each other. This is intentional — the Admiral controls wiring explicitly.

**[Risk] Migration stop/start during transport restart causes brief crew downtime** → Mitigation: `_reconcile_registry` already restarts stopped crews; the migration is the same code path. Downtime is bounded by `_wait_gateway` (30s timeout per crew).

**[Risk] `ga-net` removal fails if a container still references it** → Mitigation: removal is best-effort and logged as a warning; ghostship does not fail to start.

**[Risk] macOS: `podman network connect` inside a machine VM** → Mitigation: all podman calls go through the dedicated machine socket via `_PODMAN_CMD` and `PodmanClient`. The connect/disconnect calls use the same `self._req("POST", ...)` path and work on both macOS (inside VM) and Linux.

**[Trade-off] Tests that mock network constants** → Tests currently patch `GA_NETWORK` on both `lifecycle` and `server`. After this change they must patch `GA_PORTSIDE_NETWORK` and use `crew_network(crew_id)` directly. This is a bounded test-only change.

## Migration Plan

1. **Install upgrade** (`install.sh` re-run):
   - Creates `ga-portside` (idempotent). Does NOT create per-crew networks — those are dynamic.
   - Stops and recreates `ga-transport` container (now on portside only in compose) and `ga-portal` container (portside only, unchanged).
   - Existing `ga-net` is left in place — it may still have crew containers attached.

2. **Transport startup** (`_reconcile_registry`):
   - Detects any `gs-{crew_id}` container attached to `ga-net` but not `ga-crew-{crew_id}`.
   - For each such crew: creates `ga-crew-{crew_id}`, connects transport to it, migrates container (disconnect `ga-net`, connect `ga-crew-{crew_id}`), starts, waits, refreshes cookie.
   - After all crews migrated, attempts to remove `ga-net` if empty.

3. **Rollback**:
   - Re-run the previous `install.sh` version (which recreates `ga-net` and uses the old images).
   - The old transport restarts; old `_reconcile_registry` doesn't know about per-crew networks and won't disconnect crews from `ga-crew-{id}` — those containers will have an extra network attached. This is harmless for rollback.
   - Clean rollback: `podman network connect ga-net <container>` for each crew, then remove per-crew networks when empty.

## Open Questions

None — all design questions resolved above.
