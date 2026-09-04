## 1. podman.py — Multi-network container_create and network helpers

- [ ] 1.1 Update `ContainerRuntime` ABC: change `container_create` signature from `network: str` to `networks: list[str]`; update the abstract method and any type annotations
- [ ] 1.2 Update `PodmanClient.container_create` implementation: build `"Networks": {n: {} for n in networks}` from the list; update all call sites that previously used the single `network` argument
- [ ] 1.3 Add `PodmanClient.network_connect(container: str, network: str)` wrapping `POST /libpod/networks/{network}/connect` — needed for attaching transport to per-crew networks at launch and for peering
- [ ] 1.4 Add `PodmanClient.network_disconnect(container: str, network: str)` wrapping `POST /libpod/networks/{network}/disconnect` — needed for transport detach at nuke and migration cleanup
- [ ] 1.5 Add `PodmanClient.container_networks(container: str) -> list[str]` method that parses `NetworkSettings.Networks` from `container_inspect` output — needed for migration detection
- [ ] 1.6 Add `PodmanClient.network_rm(network: str)` method wrapping `DELETE /libpod/networks/{network}` — needed for per-crew network removal at nuke and post-migration `ga-net` cleanup

## 2. lifecycle.py — Network constants and helper

- [ ] 2.1 Replace `GA_NETWORK = "ga-net"` with `GA_PORTSIDE_NETWORK = "ga-portside"`; add a helper `def crew_network(crew_id: str) -> str: return f"ga-crew-{crew_id}"` — there is no static starboard constant
- [ ] 2.2 Update `_start_login_container`: create `crew_network(crew_id)` if needed; change container `networks` to `[crew_network(crew_id)]` only
- [ ] 2.3 Update `launch` / `_finish_crew_setup` call chain:
  - Call `podman.network_create(crew_network(crew_id))` (idempotent) before container creation
  - Call `podman.network_connect("ga-transport", crew_network(crew_id))` to attach transport
  - Change `podman.container_create(..., networks=[crew_network(crew_id)], ...)`
- [ ] 2.4 Add `peer_crews: list[str] = []` parameter to `launch()` (and any internal helper that propagates it); after crew container is created and running, call `podman.network_connect(container, crew_network(peer_id))` for each `peer_id` in `peer_crews`; log a warning and skip if `ga-crew-{peer_id}` does not exist

## 3. lifecycle.py — Nuke network cleanup

- [ ] 3.1 In `nuke()` (or its internal helper): after container stop/removal, call `podman.network_disconnect("ga-transport", crew_network(crew_id))` (best-effort — catch and log, never raise)
- [ ] 3.2 After transport disconnect, call `podman.network_rm(crew_network(crew_id))` (best-effort — catch and log, never raise)

## 4. lifecycle.py — Migration in `_reconcile_registry`

- [ ] 4.1 Add `_migrate_crew_network(podman, crew_id, container)` helper:
  - Calls `container_networks(container)`; if `ga-crew-{crew_id}` already present, return immediately (no-op)
  - If `ga-net` present but `ga-crew-{crew_id}` absent:
    1. `podman.network_create(crew_network(crew_id))` (idempotent)
    2. `podman.network_connect("ga-transport", crew_network(crew_id))`
    3. Stop container
    4. `podman.network_disconnect(container, "ga-net")` (best-effort)
    5. `podman.network_connect(container, crew_network(crew_id))`
    6. Start container → `_wait_gateway` → refresh cookie
- [ ] 4.2 Call `_migrate_crew_network` inside `_reconcile_registry` for each crew before the existing start/stop logic; log `INFO` for each migration, `WARNING` on failure; mark crew `stopped` on failure and continue
- [ ] 4.3 After all crews processed, add best-effort `ga-net` removal: if `ga-net` exists and has no containers, call `podman.network_rm("ga-net")`; log warning on failure, never raise

## 5. server.py — Import updated constants

- [ ] 5.1 Update `server.py` imports from `lifecycle`: replace `GA_NETWORK` import with `GA_PORTSIDE_NETWORK` and `crew_network`
- [ ] 5.2 Update all `server.py` references to `GA_NETWORK` to use `GA_PORTSIDE_NETWORK` or `crew_network(crew_id)` as appropriate

## 6. install.sh — Portside-only network provisioning

- [ ] 6.1 Replace the single `ga-net` network creation block with a single idempotent create: `${_PODMAN_CMD} network exists ga-portside 2>/dev/null || ${_PODMAN_CMD} network create ga-portside`
- [ ] 6.2 Update `compose.yml` generation: both `ga-transport` and `ga-portal` declare only `ga-portside` in their `networks:` block; no per-crew network entries in compose.yml
- [ ] 6.3 Update compose.yml `networks:` top-level block: replace `ga-net: {external: true}` with `ga-portside: {external: true}` only
- [ ] 6.4 Add a best-effort `ga-net` cleanup step: if `ga-net` exists and has no containers, remove it; skip silently if it has containers

## 7. Tests

- [ ] 7.1 Update any test that mocks or patches `GA_NETWORK` to patch `GA_PORTSIDE_NETWORK` and/or `crew_network` as appropriate
- [ ] 7.2 Update any test that calls `container_create` with `network=...` kwarg to pass `networks=[...]`
- [ ] 7.3 Add unit test for `_migrate_crew_network`: mock `container_networks` returning `["ga-net"]` for `gs-alpha`; verify: `network_create("ga-crew-alpha")`, `network_connect("ga-transport", "ga-crew-alpha")`, stop, `network_disconnect(container, "ga-net")`, `network_connect(container, "ga-crew-alpha")`, start, wait sequence
- [ ] 7.4 Add unit test for `_migrate_crew_network` with container already on `ga-crew-alpha`: verify no migration steps are called
- [ ] 7.5 Add unit test for `peer_crews` wiring in `launch()`: mock `launch("coordinator", peer_crews=["worker-a"])`; verify `network_connect("gs-coordinator", "ga-crew-worker-a")` is called after container creation
- [ ] 7.6 Add unit test for `peer_crews` with missing peer network: mock network_connect raising for `ga-crew-nonexistent`; verify warning is logged and launch succeeds
- [ ] 7.7 Add unit test for nuke network cleanup: verify `network_disconnect("ga-transport", "ga-crew-alpha")` and `network_rm("ga-crew-alpha")` are called (best-effort); verify failure does not raise
- [ ] 7.8 Add unit test for the best-effort `ga-net` removal path in `_reconcile_registry`: verify removal is attempted when `ga-net` exists with no containers, and failure is logged as a warning without raising

## 8. Documentation

- [ ] 8.1 Update `docs/architecture.md` (or equivalent networking section) to describe the portside + per-crew topology — ASCII diagram showing `ga-portside` (portal ↔ transport), `ga-crew-alpha` (transport ↔ gs-alpha), `ga-crew-beta` (transport ↔ gs-beta); note that per-crew networks are created/destroyed dynamically
- [ ] 8.2 Update `docs/configuration.md` to note that `ga-net` and `ga-starboard` are removed by TRN-107; describe `ga-portside` (static) and `ga-crew-{id}` (dynamic per launch); add migration note for operators upgrading from an older version
- [ ] 8.3 Update `README.md` if it references `ga-net` or `ga-starboard` anywhere (check with `grep -r ga-net && grep -r ga-starboard`)
- [ ] 8.4 Document `peer_crews` parameter in any user-facing launch API documentation or CLI help text
