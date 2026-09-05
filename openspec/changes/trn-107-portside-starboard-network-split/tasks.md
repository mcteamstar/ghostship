## 1. podman.py — Network helpers for migration

- [ ] 1.1 Add `PodmanClient.network_connect(container: str, network: str)` wrapping `POST /libpod/networks/{network}/connect` — used for migration (connecting crews to `ga-starboard`) and for connecting `ga-transport` to `ga-starboard` idempotently at startup
- [ ] 1.2 Add `PodmanClient.network_disconnect(container: str, network: str)` wrapping `POST /libpod/networks/{network}/disconnect` — used for migration cleanup (disconnecting containers from `ga-net`)
- [ ] 1.3 Add `PodmanClient.container_networks(container: str) -> list[str]` parsing `NetworkSettings.Networks` from `container_inspect` output — used by migration detection to check whether a crew is already on `ga-starboard`
- [ ] 1.4 `container_create` keeps its existing `network: str` single-network parameter — no signature change required; all crew containers go to `ga-starboard`, login containers go to `ga-starboard`

## 2. lifecycle.py — Network constants and crew container assignment

- [ ] 2.1 Replace `GA_NETWORK = "ga-net"` with two constants: `GA_PORTSIDE_NETWORK = "ga-portside"` and `GA_STARBOARD_NETWORK = "ga-starboard"`; remove any dynamic `crew_network()` function
- [ ] 2.2 Update `_start_login_container`: pass `network=GA_STARBOARD_NETWORK` to `container_create`
- [ ] 2.3 Update `launch` / `_finish_crew_setup`: pass `network=GA_STARBOARD_NETWORK` to `podman.container_create`; remove any per-crew `network_create`/`network_connect` calls; remove `peer_crews` parameter
- [ ] 2.4 Update `nuke`: remove any per-crew `network_disconnect`/`network_rm` calls — no dynamic per-crew network lifecycle

## 3. lifecycle.py — Migration in `_reconcile_registry`

- [ ] 3.1 Add `_migrate_crew_network(podman, crew_id, container)` helper:
  - Call `container_networks(container)`
  - If `ga-starboard` already in list: return immediately (no-op)
  - If `ga-net` in list:
    1. `podman.network_connect("ga-transport", GA_STARBOARD_NETWORK)` (idempotent — transport already on starboard after compose restart, but safe to repeat)
    2. Stop container
    3. `podman.network_disconnect(container, "ga-net")` (best-effort — catch and log)
    4. `podman.network_connect(container, GA_STARBOARD_NETWORK)`
    5. Start container → `_wait_gateway` → refresh cookie
- [ ] 3.2 Call `_migrate_crew_network` inside `_reconcile_registry` for each crew before the existing start/stop logic; log `INFO` for each migration, `WARNING` on failure; mark crew `stopped` on failure and continue
- [ ] 3.3 After all crews processed, add best-effort `ga-net` removal: if `ga-net` exists and has no containers, call `podman.network_rm("ga-net")`; log warning on failure, never raise

## 4. install.sh — Network provisioning and GA_PORTAL_SECRET

- [ ] 4.1 Replace the single `ga-net` creation block with two idempotent creates:
  ```bash
  ${_PODMAN_CMD} network exists ga-portside 2>/dev/null || ${_PODMAN_CMD} network create ga-portside
  ${_PODMAN_CMD} network exists ga-starboard 2>/dev/null || ${_PODMAN_CMD} network create ga-starboard
  ```
- [ ] 4.2 Update `compose.yml` generation: `ga-portal` declares only `ga-portside`; `ga-transport` declares both `ga-portside` and `ga-starboard`; top-level `networks:` declares both as `{external: true}`; remove `ga-net`
- [ ] 4.3 Generate `GA_PORTAL_SECRET` and write Podman secret (idempotent — skip if already exists):
  ```bash
  if ! ${_PODMAN_CMD} secret inspect ga-portal-secret >/dev/null 2>&1; then
    openssl rand -hex 32 | ${_PODMAN_CMD} secret create ga-portal-secret -
  fi
  ```
- [ ] 4.4 Update Caddy config generation: add `header_up X-Portal-Token {env.GA_PORTAL_SECRET}` to every `reverse_proxy` block targeting `ga-transport`
- [ ] 4.5 Mount `ga-portal-secret` into `ga-transport` at `/run/secrets/ga-portal-secret` in the compose service definition; inject `GA_PORTAL_SECRET` env var into the `ga-portal` service from the same secret
- [ ] 4.6 Add best-effort `ga-net` cleanup: if `ga-net` exists and has no containers, remove it; skip silently if it has containers

## 5. transport/config.py — GA_PORTAL_SECRET field

- [ ] 5.1 Add `ga_portal_secret: str` field to the transport config dataclass
- [ ] 5.2 Add `_load_portal_secret()` function following the `_load_api_key()` pattern: reads from `/run/secrets/ga-portal-secret`; raises `RuntimeError` with a safe message (not the secret value) if absent; registers the loaded value with the log redaction filter
- [ ] 5.3 Call `_load_portal_secret()` during transport startup config initialisation, immediately after `_load_api_key()`

## 6. transport/server.py — GA_PORTAL_SECRET middleware and constant updates

- [ ] 6.1 Update imports from `lifecycle`: replace `GA_NETWORK` import with `GA_PORTSIDE_NETWORK` and `GA_STARBOARD_NETWORK`
- [ ] 6.2 Update all `server.py` references to `GA_NETWORK` to use `GA_PORTSIDE_NETWORK` or `GA_STARBOARD_NETWORK` as appropriate
- [ ] 6.3 Add `PortalSecretMiddleware` (or equivalent ASGI/Starlette middleware) that:
  - Reads `config.ga_portal_secret`
  - On every incoming request: checks for `X-Portal-Token` header
  - If header absent or value does not match secret: return HTTP 401 immediately, before any other middleware
  - If header matches: pass to next handler
  - Install this middleware as the outermost layer, before `BearerAuthMiddleware`

## 7. Tests

- [ ] 7.1 Update any test that mocks or patches `GA_NETWORK` to patch `GA_PORTSIDE_NETWORK` and/or `GA_STARBOARD_NETWORK`
- [ ] 7.2 Update any test that calls `container_create` with network=`"ga-net"` to pass `network=GA_STARBOARD_NETWORK`
- [ ] 7.3 Add unit test for `PortalSecretMiddleware`: missing header → 401; correct header → passes through; wrong header value → 401
- [ ] 7.4 Add unit test for `_migrate_crew_network`: mock `container_networks` returning `["ga-net"]` for `gs-alpha`; verify: `network_connect("ga-transport", "ga-starboard")`, stop, `network_disconnect(container, "ga-net")`, `network_connect(container, "ga-starboard")`, start, wait sequence
- [ ] 7.5 Add unit test for `_migrate_crew_network` with container already on `ga-starboard`: verify no migration steps are called
- [ ] 7.6 Add unit test for migration failure: mock `_wait_gateway` raising; verify crew is marked `stopped`, remaining crews continue, transport does not raise
- [ ] 7.7 Add unit test for best-effort `ga-net` removal in `_reconcile_registry`: verify removal attempted when `ga-net` has no containers; verify failure is logged as warning without raising
- [ ] 7.8 Update `GA_NETWORK` constant tests: verify `GA_PORTSIDE_NETWORK = "ga-portside"` and `GA_STARBOARD_NETWORK = "ga-starboard"`

## 8. Docs

- [ ] 8.1 Update `docs/architecture.md` (or equivalent networking section) to describe the portside + starboard topology — ASCII diagram showing `ga-portside` (portal ↔ transport), `ga-starboard` (transport ↔ all crews); three-control security model (network split, GA_PORTAL_SECRET, IP-bound cookies); note that `ga-net` is retired
- [ ] 8.2 Update `docs/configuration.md`: remove `ga-net` references; document `GA_PORTAL_SECRET` generation and purpose; document `ga-portside` and `ga-starboard` as the two static networks; add migration note for operators upgrading from an older version
- [ ] 8.3 Check `README.md` for `ga-net` or per-crew network references and update to portside/starboard
