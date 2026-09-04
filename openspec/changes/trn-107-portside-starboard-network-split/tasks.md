## 1. podman.py — Multi-network container_create

- [ ] 1.1 Update `ContainerRuntime` ABC: change `container_create` signature from `network: str` to `networks: list[str]`; update the abstract method and any type annotations
- [ ] 1.2 Update `PodmanClient.container_create` implementation: build `"Networks": {n: {} for n in networks}` from the list; update all four volume/spec fields that previously used the single `network` argument
- [ ] 1.3 Add `PodmanClient.network_connect(container: str, network: str)` and `network_disconnect(container: str, network: str)` methods wrapping `POST /libpod/networks/{network}/connect` and `POST /libpod/networks/{network}/disconnect` — needed for migration in `_reconcile_registry`
- [ ] 1.4 Add `PodmanClient.container_networks(container: str) -> list[str]` method that parses `NetworkSettings.Networks` from `container_inspect` output — needed for migration detection

## 2. lifecycle.py — Network constants and container attachment

- [ ] 2.1 Replace `GA_NETWORK = "ga-net"` with `GA_PORTSIDE_NETWORK = "ga-portside"` and `GA_STARBOARD_NETWORK = "ga-starboard"`
- [ ] 2.2 Update `_start_login_container`: change `podman.network_create(GA_NETWORK)` → create both networks; change `"Networks": {GA_NETWORK: {}}` → `GA_STARBOARD_NETWORK` only
- [ ] 2.3 Update `launch` / `_finish_crew_setup` call chain: change `podman.container_create(..., network=GA_NETWORK, ...)` → `networks=[GA_STARBOARD_NETWORK]` (crew containers join starboard only)
- [ ] 2.4 Ensure `podman.network_create` is called for both `GA_PORTSIDE_NETWORK` and `GA_STARBOARD_NETWORK` before container creation (idempotent — `network_create` already swallows 409 Conflict)

## 3. lifecycle.py — Migration in `_reconcile_registry`

- [ ] 3.1 Add `_migrate_crew_network(podman, container)` helper: calls `container_networks`, checks for `ga-net` attachment without `ga-starboard`; if migration needed: stop → `network_disconnect(container, "ga-net")` → `network_connect(container, GA_STARBOARD_NETWORK)` → start → `_wait_gateway` → refresh cookie
- [ ] 3.2 Call `_migrate_crew_network` inside `_reconcile_registry` for each crew before the existing start/stop logic; log `INFO` for each migration, `WARNING` on failure
- [ ] 3.3 After all crews processed, add best-effort `ga-net` removal: if `ga-net` exists and has no containers, call `podman network rm ga-net`; log warning on failure, never raise

## 4. server.py — Import updated constants

- [ ] 4.1 Update `server.py` imports from `lifecycle`: replace `GA_NETWORK` import with `GA_PORTSIDE_NETWORK, GA_STARBOARD_NETWORK`
- [ ] 4.2 Update all `server.py` references to `GA_NETWORK` (module-level assignment and any direct usages) to use the appropriate new constant (`GA_STARBOARD_NETWORK` for crew/login containers, `GA_PORTSIDE_NETWORK` for Caddy admin URL context if referenced)

## 5. install.sh — Network provisioning

- [ ] 5.1 Replace the single `ga-net` network creation block with two idempotent creates: `${_PODMAN_CMD} network exists ga-portside 2>/dev/null || ${_PODMAN_CMD} network create ga-portside` and same for `ga-starboard`
- [ ] 5.2 Update compose.yml generation: `ga-transport` networks block → declare both `ga-portside` and `ga-starboard`; `ga-portal` networks block → declare `ga-portside` only
- [ ] 5.3 Update compose.yml `networks:` top-level block: replace `ga-net: {external: true}` with `ga-portside: {external: true}` and `ga-starboard: {external: true}`
- [ ] 5.4 Add a best-effort `ga-net` cleanup step near the end of `install.sh`: if `ga-net` exists and has no containers (`${_PODMAN_CMD} network inspect ga-net --format '{{.Containers}}'` returns `{}`), remove it with a log message; skip silently if it has containers

## 6. Tests

- [ ] 6.1 Update any test that mocks or patches `GA_NETWORK` to patch `GA_PORTSIDE_NETWORK` and/or `GA_STARBOARD_NETWORK` as appropriate
- [ ] 6.2 Update any test that calls `container_create` with `network=...` kwarg to pass `networks=[...]`
- [ ] 6.3 Add unit test for `_migrate_crew_network`: mock `container_networks` returning `["ga-net"]`; verify stop → disconnect → connect → start → wait sequence is called
- [ ] 6.4 Add unit test for `_migrate_crew_network` with a container already on `ga-starboard`: verify no migration steps are called
- [ ] 6.5 Add unit test for the best-effort `ga-net` removal path in `_reconcile_registry`: verify that removal is attempted when network exists and has no containers, and that failure is logged as a warning without raising

## 7. Documentation

- [ ] 7.1 Update `docs/architecture.md` (or equivalent networking section) to describe the portside/starboard topology — ASCII diagram showing the two networks and which containers join each
- [ ] 7.2 Update `docs/configuration.md` to note that `ga-net` is removed by TRN-107 and replaced by `ga-portside`/`ga-starboard`; add any migration note for operators upgrading from an older version
- [ ] 7.3 Update `README.md` if it references `ga-net` anywhere (check with `grep -r ga-net`)
