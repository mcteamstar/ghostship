## Why

All ghostship containers — `ga-portal`, `ga-transport`, and every `gs-*` crew container — currently share a single `ga-net` network. This means a crew container can dial `ga-transport:8000` directly, bypassing Caddy's Bearer-token auth and the transport's own rate limiting, API-key checks, and audit logging. The fix is a network split that uses Podman's per-network DNS to isolate who can reach what.

## What Changes

- Rename / replace `ga-net` with two separate Podman networks:
  - `ga-portside` — `ga-portal` ↔ `ga-transport` only; no crew containers
  - `ga-starboard` — `ga-transport` ↔ `gs-*` crew containers only; no portal
- `ga-transport` joins **both** networks, acting as the sole bridge
- `ga-portal` joins **portside only** — it has no reason to reach crew containers directly
- Every `gs-*` crew container joins **starboard only** — crew containers cannot dial `ga-portal` or reach each other via DNS (they get separate DNS namespaces per network)
- `ga-login-*` ephemeral login containers join **starboard** (they need to reach transport for auth exchange)
- `ga-worker-*` disposable worker containers join **no network** (`netns: none`) — this is already the case in `podman.py worker_run` and remains unchanged
- MCP catalogue containers — no change; they are not run by ghostship
- `install.sh` creates both networks, generates `compose.yml` with dual-network declarations for `ga-transport`, and attaches `ga-portal` to `portside` only
- `lifecycle.py` and `server.py` update `GA_NETWORK` constant → two constants `GA_PORTSIDE_NETWORK` / `GA_STARBOARD_NETWORK`; crew containers and login containers attach to `ga-starboard`
- Migration: on startup, detect and migrate existing single-network crews to `ga-starboard` (option A — described in detail in design.md)
- **BREAKING**: any external tooling or documentation that references `ga-net` will need updating; the network is removed

## Capabilities

### New Capabilities

- `transport/network-split`: Portside/starboard network topology — two-network model, migration path, per-container network assignment rules

### Modified Capabilities

- `transport/caddy-proxy`: Network topology requirement — `ga-portal` joins `ga-portside` only, not `ga-net`; the Caddy admin API is no longer on `ga-net`
- `transport/dashboard-proxy`: Network topology requirement — crew containers are NOT on the same network as `ga-portal`; all routing goes portal → transport → crew

## Impact

- `scripts/install.sh` — network creation section, compose.yml generation
- `transport/lifecycle.py` — `GA_NETWORK` constant, `_start_login_container`, `_finish_crew_setup`, `_reconcile_registry`, `_ensure_crew_running`
- `transport/server.py` — `GA_NETWORK` constant (mirror of lifecycle), login container helpers
- `transport/podman.py` — `container_create` signature may need a `networks` list; `worker_run` already uses `netns: none` (no change)
- `openspec/specs/transport/caddy-proxy/spec.md` — network topology requirement update
- `openspec/specs/transport/dashboard-proxy/spec.md` — network topology requirement update
- Existing running crews on `ga-net` — require migration on transport startup
