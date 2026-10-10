# Tasks

Specs: `specs/installation/spec.md` (ADDED requirements), `specs/config-file/spec.md` (MODIFIED + ADDED requirements).

## 1. Wire missing env vars into compose.yml (install.sh)

- [ ] 1.1 Add `GA_PREWARM_ENABLED: "${GA_PREWARM_ENABLED:-}"` and `GA_PREWARM_TTL_SECS: "${GA_PREWARM_TTL_SECS:-300}"` to the `ga-transport` environment block in the compose template inside `scripts/install.sh` (alongside other prewarm-adjacent vars).
- [ ] 1.2 Add `KC_IMAGE: "${KC_IMAGE:-localhost/spec-ops:latest}"` and `KC_BASE_IMAGE: "${KC_BASE_IMAGE:-ghcr.io/kirodotdev/kirocrew:0.8.0}"` to the `ga-transport` environment block in the compose template.
- [ ] 1.3 Add `GA_RATE_LIMIT_DASHBOARD_AUTH: "${GA_RATE_LIMIT_DASHBOARD_AUTH:-600:60}"` to the `ga-transport` environment block alongside the other `GA_RATE_LIMIT_*` vars.

## 2. Add conditional volume mounts for host-path vars

- [ ] 2.1 In `scripts/install.sh`, before writing `compose.yml`, add a check: if `GA_ORDERS_DIR` is non-empty and not an absolute path, print an error and abort. If the path does not exist, print a warning (but continue).
- [ ] 2.2 In the compose template, add a conditional `- ${GA_ORDERS_DIR}:/mnt/orders:ro` volume entry for `ga-transport` when `GA_ORDERS_DIR` is non-empty, and set `GA_ORDERS_DIR: "/mnt/orders"` (fixed container path) in the environment block instead of the raw host path. Use a shell conditional (`if [[ -n "${GA_ORDERS_DIR:-}" ]]; then ...`) analogous to the existing `GA_API_KEY` conditional in the secrets block.
- [ ] 2.3 In `scripts/install.sh`, add a check: if either `GA_TLS_CERTFILE` or `GA_TLS_KEYFILE` is set but not both, error with a clear message. If both are set and do not share the same parent directory, error with a clear message explaining the same-directory requirement.
- [ ] 2.4 In the compose template, add a conditional `- <cert_dir>:/mnt/tls:ro` volume entry for `ga-transport` when both TLS vars are set. Set `GA_TLS_CERTFILE: "/mnt/tls/<cert_basename>"` and `GA_TLS_KEYFILE: "/mnt/tls/<key_basename>"` (container-side paths) in the environment block. Derive `<cert_dir>` using `dirname "$GA_TLS_CERTFILE"` and basenames via `basename`.

## 3. Fix code comment in lifecycle.py

- [ ] 3.1 In `transport/lifecycle.py` around line 280, remove "Both TTLs floor at one hour." from the comment block (the warm-marker TTL is floored via `_warm_marker_ttl_secs()`; `_TASK_TIMESTAMP_TTL_SECS` is not). Replace with a factually accurate comment, e.g.: "The warm-marker TTL is floored at one hour; `_TASK_TIMESTAMP_TTL_SECS` has no floor."

## 4. Update docs/configuration.md

- [ ] 4.1 `PORT` table entry: add a sentence clarifying that `PORT` controls the Caddy host-side port only; the transport always listens on 64057 inside its container regardless of `PORT`.
- [ ] 4.2 `GA_ORDERS_DIR` entry: update to note that `install.sh` adds a volume mount automatically when this is set; operators supply a host-side absolute path in `ghostship.conf` and the transport sees it at `/mnt/orders`.
- [ ] 4.3 `GA_TLS_CERTFILE` / `GA_TLS_KEYFILE` entries: update to note the same-directory requirement and that `install.sh` mounts the directory at `/mnt/tls` and rewrites the paths; existing table entry says the vars have no effect unless install.sh is aware of them.
- [ ] 4.4 `GA_FILE_SECRET` entry: add a sentence confirming the absence from compose is by design (auto-generated and persisted; no operator override needed).
- [ ] 4.5 `TRANSPORT_DATA_DIR` entry: add a note that this is effectively pinned to `/data` in the standard install; the volume mount target would need to change to make this meaningful.
- [ ] 4.6 `GA_MAX_ACTIVE_CREWS` entry: update to clarify that values ≤ 0 all disable the active-crew limit (current text says "Set to 0 to disable" but does not mention negative values).
- [ ] 4.7 Add `GA_RATE_LIMIT_DASHBOARD_AUTH` to the rate-limiting table in `docs/configuration.md` (currently listed in `ghostship.conf.example` but absent from the docs table).

## 5. Update config/ghostship.conf.example

- [ ] 5.1 Add `GA_RATE_LIMIT_DASHBOARD_AUTH` commented entry in the HTTP rate limiting section with default value `600:60` and a description matching the docs table (`/dashboard/auth` — Caddy `forward_auth` endpoint).
- [ ] 5.2 Update `GA_ORDERS_DIR` comment to reflect that a host-side absolute path is required and that install.sh adds the volume mount; mention the same-directory-not-required caveat does not apply here.
- [ ] 5.3 Update `GA_TLS_CERTFILE` / `GA_TLS_KEYFILE` comments to note the same-directory requirement and that install.sh handles the volume mount.
- [ ] 5.4 Update `GA_MAX_ACTIVE_CREWS` comment to match Decision 10: "Set to 0 (or any value ≤ 0) to disable."
