## Why

`GA_API_KEY` is currently passed to `ga-portal` (Caddy) as a plain environment variable and interpolated into `initial-config.json` via `{env.GA_API_KEY}` in the Bearer-matching expression. Environment variables in a compose service are visible in `podman inspect` output and process listings, leaking the secret outside the container boundary. Moving to a Podman secret file keeps the key on disk only as a secret object (readable by the container at `/run/secrets/ga-api-key`) and never surfaces it through process inspection. This follows the same pattern already in use for `ga-transport-secret`.

## What Changes

- **`scripts/install.sh` — secret creation**: the existing `ga-api-key` Podman secret and `GA_SECRET_FLAG` variable already handle creation of the Podman secret; the compose.yml secrets block for `ga-portal` needs to add `ga-api-key` to its secrets mount.
- **`scripts/install.sh` — compose.yml generation**: add `ga-api-key` to the `ga-portal` service's `secrets:` list (alongside `ga-transport-secret`) when the API key is set; add `ga-api-key` to the top-level `secrets:` block (already done conditionally for `ga-transport`).
- **`scripts/install.sh` — `initial-config.json` generation**: replace `{env.GA_API_KEY}` with `{file./run/secrets/ga-api-key}` in the Caddy Bearer matching expressions for the `/mcp*` and `/files/*` routes.
- **`scripts/install.sh` — compose.yml generation**: remove `GA_API_KEY` from the `ga-portal` service `environment:` block.

No other files change. This is a pure installation-script change; no transport, crew, or API behavior is modified.

## Capabilities

### New Capabilities
<!-- None — skip_specs: true -->

### Modified Capabilities
<!-- None — no spec-level behavior changes; the externally observable auth behavior (Bearer token required) is identical. -->

## Impact

- **`scripts/install.sh`**: all changes are within the `compose.yml` and `initial-config.json` generation sections.
- **Existing installs**: operators must re-run `install.sh` to pick up the change; existing `ga-api-key` Podman secrets created by the current code are compatible (the secret content is unchanged, only its consumption path changes).
- **Caddy `{file.*}` placeholder**: requires Caddy ≥ 2.7 — already satisfied by `docker.io/caddy:2` (current latest is 2.9+). `ga-transport-secret` already uses this placeholder (`{file./run/secrets/ga-transport-secret}`), so the feature is confirmed working in the current setup.
