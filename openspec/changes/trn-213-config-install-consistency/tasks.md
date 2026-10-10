# Tasks

## 1. Prune ghostship.conf.example

- [ ] 1.1 Remove the following vars from `config/ghostship.conf.example` entirely (they are internal implementation details operators should never set): `GA_PREWARM_ENABLED`, `GA_PREWARM_TTL_SECS`, `GA_RESOURCE_PRESSURE_GB`, `GA_RESOURCE_CRITICAL_GB`, `GA_SPAWN_MIN_MEMORY_GB`, `GA_SUBAGENT_TIMEOUT_SECS`, `GA_SUBAGENT_MAX_TURNS`, `GA_TRANSPORT_SECRET`, `TRANSPORT_DATA_DIR`, `PODMAN_SOCKET`, `GA_ENABLE_SECURITY_HEADERS`, `GA_TLS_MIN_VERSION`, `GA_CREW_AGENT`, `GA_MACHINE_NAME`, `GA_DASHBOARD_PORT_RANGE_START`, `GA_DASHBOARD_PORT_RANGE_SIZE`
- [ ] 1.2 Move `KC_IMAGE` and `KC_BASE_IMAGE` out of `ghostship.conf.example` and into a brief "Advanced / dev-only" note in `docs/configuration.md` only — they're useful for development and custom images but not for production operators
- [ ] 1.3 Remove all six `GA_RATE_LIMIT_*` vars from `ghostship.conf.example` — keep defaults in code, document the master switch (`GA_RATE_LIMIT_ENABLED`) only in `docs/configuration.md` as an escape hatch

## 2. Fix GA_ORDERS_DIR — add volume mount

- [ ] 2.1 In `scripts/install.sh`, before writing `compose.yml`, add a check: if `GA_ORDERS_DIR` is set but not an absolute path, print an error and abort; if set and path doesn't exist, print a warning but continue
- [ ] 2.2 In the compose template, add a conditional `- ${GA_ORDERS_DIR}:/mnt/orders:ro` volume entry for `ga-transport` when `GA_ORDERS_DIR` is non-empty, and set `GA_ORDERS_DIR: "/mnt/orders"` (fixed container path) in the environment block instead of the raw host path

## 3. Fix GA_TLS_CERTFILE / GA_TLS_KEYFILE — add volume mount

- [ ] 3.1 In `scripts/install.sh`, add a check: if either TLS var is set but not both, error with a clear message; if both are set and don't share the same parent directory, error explaining the same-directory requirement
- [ ] 3.2 In the compose template, add a conditional `- <cert_dir>:/mnt/tls:ro` volume entry when both TLS vars are set; set `GA_TLS_CERTFILE: "/mnt/tls/<cert_basename>"` and `GA_TLS_KEYFILE: "/mnt/tls/<key_basename>"` as the container-side paths

## 4. Fix lifecycle.py comment

- [ ] 4.1 In `transport/lifecycle.py` around line 280, replace "Both TTLs floor at one hour." with an accurate comment: "The warm-marker TTL is floored at one hour via `_warm_marker_ttl_secs()`; `_TASK_TIMESTAMP_TTL_SECS` has no floor."

## 5. Update docs/configuration.md and ghostship.conf.example

- [ ] 5.1 Update `docs/configuration.md` to remove pruned vars, add PORT clarification (Caddy host port only; transport always 64057 inside container), and add brief KC_IMAGE/KC_BASE_IMAGE note in a dev/advanced section
- [ ] 5.2 Update `GA_MAX_ACTIVE_CREWS` entry in both docs and conf.example: values ≤ 0 all disable the limit (not just 0)
- [ ] 5.3 Update `GA_ORDERS_DIR` and TLS entries in docs/conf.example to reflect the new volume-mount behaviour
