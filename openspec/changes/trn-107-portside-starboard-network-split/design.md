# Design: TRN-107 — Portside/Starboard Network Split

## Context

See `proposal.md` — Why for motivation.

**Current state:**
- Single Podman network `ga-net` contains: `ga-portal`, `ga-transport`, all `gs-*` crew containers, and ephemeral `ga-login-*` containers.
- `ga-transport` is declared as `GA_NETWORK = "ga-net"` in both `lifecycle.py` and `server.py`.
- `install.sh` creates `ga-net` with `podman network exists ga-net || podman network create ga-net` and emits it in `compose.yml` as an external network for both `ga-portal` and `ga-transport`.
- `podman.py` `container_create` takes a single `network: str` parameter and sets `"Networks": {network: {}}`.
- `worker_run` already uses `"netns": {"nsmode": "none"}` — no change needed.
- `_start_login_container` in `lifecycle.py` calls `podman.network_create(GA_NETWORK)` then `"Networks": {GA_NETWORK: {}}`.

**Key constraint:** Podman per-network DNS means every container on a network can resolve every other container on that network by hostname. Adding a container to a second network gives it a second DNS entry on that network. `ga-transport` on both networks therefore resolves as `ga-transport` from both `ga-portside` and `ga-starboard` — this is the intended design.

```
  Internet / host
       │
  [ga-portal]
       │  ga-portside
  [ga-transport]  ← bridges both
       │  ga-starboard
  [gs-*] [ga-login-*]
```

## Goals / Non-Goals

**Goals:**
- `ga-portal` cannot reach crew containers by hostname.
- Crew containers cannot reach `ga-portal` by hostname.
- `ga-transport` remains reachable from both segments.
- `BearerAuthMiddleware` remains as defence-in-depth (network isolation is not the only layer).
- Existing crews are migrated without requiring operator intervention.

**Non-goals:**
- Prevent crew containers from reaching `ga-transport` on `ga-starboard` at the network layer — Podman DNS will resolve `ga-transport` from starboard, and that is acceptable because the transport's own auth middleware handles rejection. Full network-layer blocking of crew → transport would require additional Podman network policies not available in rootless mode.
- Firewall or iptables rules — Podman rootless mode has limited network policy support.

## Decisions

### D1: Migration path — detect and migrate on startup (Option A)

**Choice:** Option A — `_reconcile_registry` detects crews on `ga-net` and migrates them to `ga-starboard` at transport startup.

**Rationale:**
- Option B (nuke required) forces operators to destroy crew workspaces on upgrade — too disruptive. Crew workspaces are persistent (spec: "frames crews as persistent workspaces").
- Option C (parallel `ga-net` + `ga-starboard` support) adds ongoing complexity: two network constants, conditional logic, indefinite support burden.
- Option A is a one-time cost at the first startup after the upgrade. The migration is stop → disconnect → connect → start → wait for gateway, which is already idempotent and tested via `_ensure_crew_running`.

**Migration algorithm in `_reconcile_registry`:**
1. For each crew in registry, check if its container is attached to `ga-net` but not `ga-starboard` via `podman inspect`.
2. If so: stop container, call `podman network disconnect ga-net <container>`, call `podman network connect ga-starboard <container>`, start container, wait for gateway, refresh cookie.
3. Update registry status.
4. After all crews processed, if `ga-net` has no containers left, attempt `podman network rm ga-net` (best-effort, log warning on failure).

**What to check for `ga-net` attachment:** `podman inspect <container>` returns `NetworkSettings.Networks` — check for a `ga-net` key and absence of `ga-starboard`.

### D2: DNS — does ga-transport resolve gs-* hostnames on ga-starboard?

**Answer: Yes.** Podman per-network DNS assigns a hostname to each container on each network it joins. When `gs-<crew_id>` joins `ga-starboard`, it is resolvable as `gs-<crew_id>` (and its full name) from any container also on `ga-starboard` — including `ga-transport`. The transport dials `http://gs-<crew_id>:5476` and this continues to work unchanged because both the transport and crew containers are on `ga-starboard`.

**Verification from codebase:** `_crew_url` returns `f"http://{crew['container']}:{CREW_GATEWAY_PORT}"` where `container = "gs-{crew_id}"`. Container-name DNS confirmed working per the server.py module docstring ("Container-name DNS confirmed working."). No change required here.

### D3: Worker containers — no network (unchanged)

`worker_run` already uses `"netns": {"nsmode": "none"}`. Workers mount the crew volume read-only and run git/Python commands with no network access. This is correct and unchanged.

### D4: MCP catalogue containers — not managed by ghostship

The `/mcp` catalogue files are JSON descriptors mounted from the host into `ga-transport` at `/mcp:ro`. There are no "MCP catalogue containers" — the MCP servers referenced in `academy/mcp/*.json` are network-addressed external services resolved at crew runtime inside the crew container. They are not managed by ghostship and this change does not affect them.

### D5: Does ga-portal need starboard access?

No. `ga-portal` only dials `ga-transport:{PORT}` (for reverse-proxying MCP, files, health, and dashboard routes) and `ga-transport:2019` (the Caddy admin API — same host, same portside network). It has no reason to reach `gs-*` containers directly. The current `_caddy_register_crew` implementation already targets `ga-transport:8000` not `gs-*` (confirmed in `server.py`).

### D6: podman.py container_create — multi-network support

`container_create` currently takes a single `network: str`. The Podman REST API accepts `"Networks": {name: {}}` for multiple networks as a dict with multiple keys. Two options:

- **Option A (chosen):** Keep `container_create` signature unchanged; add crew containers to a second network via `podman network connect` after start, OR change the parameter to accept a list.
- **Recommendation:** Change the `network` parameter to `networks: list[str]` (or keep `network: str` for backwards compatibility and add an optional `extra_networks: list[str]`). The Podman API body `"Networks"` is already a dict — passing multiple keys is straightforward.

**Choice:** Change `container_create` to accept `networks: list[str]` and build `"Networks": {n: {} for n in networks}`. All existing call sites pass a single network today; they will pass `[GA_STARBOARD_NETWORK]` after this change. The `ContainerRuntime` ABC signature is updated accordingly.

### D7: Constant naming

Replace `GA_NETWORK = "ga-net"` with:
```python
GA_PORTSIDE_NETWORK = "ga-portside"
GA_STARBOARD_NETWORK = "ga-starboard"
```

Both constants are defined in `lifecycle.py` (authoritative) and imported by `server.py` (exactly as `GA_NETWORK` is today). Crew containers use `GA_STARBOARD_NETWORK`; login containers use `GA_STARBOARD_NETWORK`; `compose.yml` declares both networks.

## Risks / Trade-offs

**[Risk] Crew containers can still DNS-resolve `ga-transport` on starboard** → Mitigation: `BearerAuthMiddleware` enforces auth on all non-exempt routes; rate limiting applies; this was always the case. The network split closes the `ga-portal` bypass, which is the primary threat.

**[Risk] Migration stop/start during transport restart causes brief crew downtime** → Mitigation: `_reconcile_registry` already restarts stopped crews; the migration is the same code path. Crews are expected to survive transport restarts. Downtime is bounded by `_wait_gateway` (30s timeout per crew).

**[Risk] `ga-net` removal fails if a container still references it** → Mitigation: removal is best-effort and logged as a warning; ghostship does not fail to start. Operators can manually remove `ga-net` later.

**[Risk] macOS: `podman network connect` inside a machine VM** → Mitigation: all podman calls go through the dedicated machine socket via `_PODMAN_CMD` in `install.sh` and via `PodmanClient` (which uses the socket). The connect/disconnect calls use the same `self._req("POST", ...)` path and will work on both macOS (inside VM) and Linux.

**[Trade-off] Tests that mock `GA_NETWORK`** → Tests currently patch `GA_NETWORK` on both `lifecycle` and `server`. After this change they must patch both `GA_PORTSIDE_NETWORK` and `GA_STARBOARD_NETWORK`. This is a bounded test-only change.

## Migration Plan

1. **Install upgrade** (`install.sh` re-run):
   - Creates `ga-portside` and `ga-starboard` (idempotent).
   - Stops and recreates `ga-transport` container (now on both networks) and `ga-portal` container (now on portside only).
   - Existing `ga-net` is left in place — it may still have crew containers attached.

2. **Transport startup** (`_reconcile_registry`):
   - Detects any `gs-*` container attached to `ga-net`.
   - Migrates each: disconnect from `ga-net`, connect to `ga-starboard`, start, wait, refresh cookie.
   - After all crews migrated, attempts to remove `ga-net` if empty.

3. **Rollback**:
   - Re-run the previous `install.sh` version (which recreates `ga-net` and uses the old images).
   - The old transport restarts; old `_reconcile_registry` doesn't know about portside/starboard and won't disconnect crews from `ga-starboard` — those crew containers will have an extra network attached. This is harmless for rollback; they'll be re-migrated forward on next upgrade.
   - Clean rollback: `podman network connect ga-net <container>` for each crew, then remove `ga-starboard`/`ga-portside` when empty.

## Open Questions

None — all design questions resolved above.
