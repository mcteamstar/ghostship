## Context

See proposal.md — Why for motivation.

`ga-portal` (Caddy) currently receives `GA_API_KEY` as a plain environment variable in the `ga-portal` service block of the generated `compose.yml`, and uses it via `{env.GA_API_KEY}` in Bearer-match expressions inside `initial-config.json`. The `ga-transport-secret` is already delivered as a Podman secret and consumed via `{file./run/secrets/ga-transport-secret}` in Caddy's config, so the infrastructure for file-based secrets in Caddy is already exercised.

All three changes (secret mount, config expression, env removal) happen in a single heredoc-driven code path in `scripts/install.sh`.

## Goals / Non-Goals

**Goals:**
- Mount `ga-api-key` as a Podman secret into `ga-portal` so the key is only accessible as `/run/secrets/ga-api-key` inside the container.
- Replace `{env.GA_API_KEY}` with `{file./run/secrets/ga-api-key}` in the Caddy Bearer expressions generated into `initial-config.json`.
- Remove `GA_API_KEY` from the `ga-portal` `environment:` block.

**Non-Goals:**
- Changing how the key is stored on the host or created as a Podman secret (that mechanism is unchanged).
- Modifying transport, crew, or any other service.
- Changing the observable auth behavior — a valid Bearer token is still required for `/mcp*` and `/files/*` routes when `GA_API_KEY` is set.

## Decisions

### 1. Use `{file./run/secrets/ga-api-key}` placeholder in Caddy

`ga-transport-secret` already uses `{file./run/secrets/ga-transport-secret}`. Extending the same pattern to `ga-api-key` is the only reasonable choice: it reads the secret file at request time (Caddy evaluates placeholders per-request), requires no custom Caddy modules, and keeps the config generation symmetric with the transport-secret pattern already proven working.

Alternative considered: read the secret file contents at install.sh generation time and embed the literal key value directly in `initial-config.json`. Rejected — this writes the key in plaintext to a file on disk (`DATA_DIR/caddy/initial-config.json`), which is worse than an env var.

### 2. Keep the conditional `if [[ -n "${GA_API_KEY:-}" ]]` guard on the secrets mount

The top-level `secrets:` block in `compose.yml` and the per-service secrets list for `ga-portal` are already written conditionally on `GA_API_KEY` being non-empty (same pattern as for `ga-transport`). No key → no secret created → no mount needed. This avoids a compose validation failure when no key is configured.

The `{file./run/secrets/ga-api-key}` reference in `initial-config.json` is already inside the `if [[ -n "${GA_API_KEY:-}" ]]` branch of `_AUTH_ROUTES`, so it is only emitted when a key is actually set. No guard change needed there.

### 3. No migration step for existing secret objects

The `ga-api-key` Podman secret is already created by the current code (the `GA_SECRET_FLAG` variable and surrounding block handle creation). Its content is unchanged; only how Caddy reads it changes. Re-running `install.sh` recreates the secret and regenerates both `compose.yml` and `initial-config.json` atomically, so no separate migration is needed.

## Risks / Trade-offs

- **Caddy placeholder evaluation at request time**: `{file.*}` reads the file on every request match. For a secret that never changes after install, this is negligible; the file is a small string and will be OS-cached after the first read. Risk: negligible.
- **No rollback complexity**: the change is entirely within generated files (`compose.yml`, `initial-config.json`). A rollback is simply reverting `install.sh` and re-running it. Risk: none.
- **Caddy version floor**: `{file.*}` requires Caddy ≥ 2.7. `docker.io/caddy:2` resolves to the current latest (2.9+) at pull time, and `ga-transport-secret` already uses this placeholder in production installs, so the version floor is already met. Risk: none for current pinning strategy; future operators pinning an older tag would get an error, which is self-diagnosing.
