# Proposal: TRN-107 — Portside/Starboard Network Split

## Why

All ghostship containers — `ga-portal`, `ga-transport`, and every `gs-*` crew container — currently share a single `ga-net` network. This creates two attack surfaces:

1. A crew container can dial `ga-portal` directly and issue Caddy admin API commands, including hijacking the reverse-proxy configuration to redirect arbitrary traffic.
2. A crew container can dial `ga-transport:8000` directly. While `BearerAuthMiddleware` enforces auth, it does not carry the context of which token type is expected from which caller — adding network-layer enforcement is defence-in-depth.
3. Crew containers can resolve and dial each other over `ga-net`, enabling lateral movement between crew workspaces.

The fix is a two-network topology that closes the crew→portal hijack at the network layer, adds an internal-only token that closes crew→transport MCP access, and closes crew→crew access via IP-bound session cookies.

## What Changes

- Replace `ga-net` with two Podman networks:
  - `ga-portside` — `ga-portal` ↔ `ga-transport` only. No crew containers on this network. Closes the crew→portal Caddy admin API hijack at the network layer.
  - `ga-starboard` — `ga-transport` ↔ all `gs-*` crew containers (shared). Crews can reach `ga-transport` but NOT `ga-portal`.
- `ga-transport` joins **both** `ga-portside` and `ga-starboard`, bridging the portal tier and the crew tier.
- `ga-portal` joins **portside only** — it cannot resolve `gs-*` crew containers.
- All `gs-*` crew containers join **ga-starboard** — shared, not per-crew.
- `ga-login-*` ephemeral login containers join **ga-starboard**.
- `ga-worker-*` disposable worker containers retain `netns: none` — unchanged.
- **GA_TRANSPORT_SECRET** — a secret token generated at install time. `ga-portal` injects it as `X-Transport-Token` on every upstream request to `ga-transport`. The transport rejects any request missing this header. Crew containers on `ga-starboard` never receive the secret and cannot forge it, closing crew→transport MCP access.
- `install.sh` creates both `ga-portside` and `ga-starboard`; assigns all existing containers; generates the Podman secret `ga-transport-secret`; injects the `X-Transport-Token` header into the Caddy config.
- `lifecycle.py` replaces `GA_NETWORK = "ga-net"` with `GA_PORTSIDE_NETWORK = "ga-portside"` and `GA_STARBOARD_NETWORK = "ga-starboard"` constants. All crew containers are created on `ga-starboard`. `peer_crews` parameter removed — not needed: the shared starboard is intentional, crew→crew is blocked by IP-bound cookies, not network isolation.
- `transport/server.py` gains GA_TRANSPORT_SECRET middleware that rejects any request missing `X-Transport-Token`, regardless of caller.
- `transport/config.py` gains `ga_transport_secret` field (loaded at startup via `_load_transport_secret()`).
- **Migration**: existing crews on `ga-net` are migrated to `ga-starboard` by `_reconcile_registry` at transport startup (same Option A as previous design).
- **BREAKING**: `ga-net` is retired. `peer_crews` parameter is removed.

## Three-Control Security Model

1. **ga-portside/ga-starboard network split** — closes crew→portal (Caddy admin API hijack) at the network layer. Crew containers are on `ga-starboard` and cannot resolve `ga-portal` by hostname.
2. **GA_TRANSPORT_SECRET internal token** — always generated at install. Caddy injects `X-Transport-Token: {env.GA_TRANSPORT_SECRET}` on every upstream request to transport. Transport rejects any request missing this header. Crew containers on `ga-starboard` never have this token and cannot reach transport MCP routes.
3. **IP-bound mc_token_5476 cookies** — closes crew→crew:5476. Empirically confirmed to return 403 when a crew attempts to authenticate to another crew's gateway.

## Why NOT Per-Crew Networks

Shared `ga-starboard` is the correct design. The internal token (GA_TRANSPORT_SECRET) closes crew→transport MCP access. IP-bound cookies close crew→crew. Per-crew networks add operational complexity (dynamic network create/destroy, transport reconnect on every launch/nuke, `peer_crews` wiring) without providing additional security benefit beyond what the token and cookie controls already provide.

## Capabilities

### New Capabilities

- `transport/network-split`: Portside/starboard network topology — two-network model, GA_TRANSPORT_SECRET, migration path, per-container network assignment rules

### Modified Capabilities

- `transport/caddy-proxy`: Network topology requirement — `ga-portal` joins `ga-portside` only; Caddy injects `X-Transport-Token` header on all upstream requests
- `transport/dashboard-proxy`: Network topology requirement — crew containers are on `ga-starboard`, not on `ga-portside`; all routing goes portal → transport → crew

## Impact

- `scripts/install.sh` — creates `ga-portside` and `ga-starboard`; assigns containers; generates `ga-transport-secret` Podman secret; updates `compose.yml`; injects `X-Transport-Token` into Caddy config
- `transport/lifecycle.py` — `GA_PORTSIDE_NETWORK`, `GA_STARBOARD_NETWORK` constants; all crew containers on starboard; migration in `_reconcile_registry`; remove `peer_crews`
- `transport/server.py` — GA_TRANSPORT_SECRET middleware; reject requests missing `X-Transport-Token`; import updated constants
- `transport/config.py` — `ga_transport_secret` field; `_load_transport_secret()` startup loader
- `transport/podman.py` — `network_connect`, `network_disconnect`, `container_networks` methods for migration; `container_create` keeps `network: str` (single network per container)
- `openspec/specs/transport/caddy-proxy/spec.md` — update network topology requirement; add `X-Transport-Token` injection requirement
- `openspec/specs/transport/dashboard-proxy/spec.md` — update network topology requirement to portside/starboard
- Existing running crews on `ga-net` — migrated to `ga-starboard` at transport startup; `ga-net` removed when empty
