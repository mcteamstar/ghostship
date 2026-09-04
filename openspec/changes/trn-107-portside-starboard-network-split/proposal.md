## Why

All ghostship containers — `ga-portal`, `ga-transport`, and every `gs-*` crew container — currently share a single `ga-net` network. This means a crew container can dial `ga-transport:8000` directly, bypassing Caddy's Bearer-token auth and the transport's own rate limiting, API-key checks, and audit logging. The fix is a network split that uses Podman's per-network DNS to isolate who can reach what.

## What Changes

- Rename / replace `ga-net` with two separate Podman networks:
  - `ga-portside` — `ga-portal` ↔ `ga-transport` only; no crew containers
  - `ga-crew-{crew_id}` — `ga-transport` ↔ one specific `gs-{crew_id}` crew container; no other crews, no portal
- `ga-transport` joins **both** `ga-portside` and each per-crew `ga-crew-{crew_id}` network (one per launched crew), acting as the bridge between the portal tier and each crew
- `ga-portal` joins **portside only** — it has no reason to reach crew containers directly
- Every `gs-{crew_id}` crew container joins **only its own** `ga-crew-{crew_id}` network — crew containers are fully isolated from each other by default and cannot reach `ga-portal`
- `ga-login-*` ephemeral login containers join the **relevant per-crew network** for the crew they are authenticating
- `ga-worker-*` disposable worker containers join **no network** (`netns: none`) — unchanged from current behaviour
- MCP catalogue containers — no change; they are not run by ghostship
- `install.sh` creates `ga-portside`, generates `compose.yml` with portside-only declarations for `ga-portal` and `ga-transport` (per-crew networks are created dynamically at launch, not in compose)
- `lifecycle.py` and `server.py` drop the single `GA_NETWORK` constant; per-crew network names are computed dynamically as `f"ga-crew-{crew_id}"`
- `launch()` gains an optional `peer_crews: list[str]` parameter — when specified, the launched crew also joins each named peer's `ga-crew-{peer_id}` network, enabling explicit opt-in crew-to-crew communication
- Network lifecycle: `launch` creates `ga-crew-{crew_id}`, attaches transport, creates crew container; `nuke` removes crew container, disconnects transport, removes `ga-crew-{crew_id}` (best-effort)
- Migration: on startup, detect and migrate existing crews on `ga-net` → each migrated to its own `ga-crew-{crew_id}` network
- **BREAKING**: any external tooling or documentation that references `ga-net` or `ga-starboard` will need updating; both are removed

## Capabilities

### New Capabilities

- `transport/network-split`: Portside/starboard network topology — two-network model, migration path, per-container network assignment rules

### Modified Capabilities

- `transport/caddy-proxy`: Network topology requirement — `ga-portal` joins `ga-portside` only, not `ga-net`; the Caddy admin API is no longer on `ga-net`
- `transport/dashboard-proxy`: Network topology requirement — crew containers are NOT on the same network as `ga-portal`; all routing goes portal → transport → crew

## Impact

- `scripts/install.sh` — network creation section (portside only in compose; per-crew networks are created dynamically)
- `transport/lifecycle.py` — drop `GA_NETWORK` constant; per-crew network names computed dynamically; `launch()` gains `peer_crews` parameter; network created/destroyed in `launch`/`nuke`; `_start_login_container`, `_finish_crew_setup`, `_reconcile_registry`, `_ensure_crew_running`
- `transport/server.py` — drop `GA_NETWORK` import; update any direct usages
- `transport/podman.py` — `container_create` signature changed to `networks: list[str]`; add `network_connect` / `network_disconnect` / `container_networks` methods; `worker_run` already uses `netns: none` (no change)
- `openspec/specs/transport/caddy-proxy/spec.md` — network topology requirement update
- `openspec/specs/transport/dashboard-proxy/spec.md` — network topology requirement update
- Existing running crews on `ga-net` — require migration on transport startup: each migrated to its own `ga-crew-{crew_id}` network
