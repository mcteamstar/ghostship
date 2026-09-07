## Why

When both Docker Compose and `podman-compose` are installed on macOS, Podman's documented provider precedence selects Docker Compose. Ghostship's generated `compose.yml` uses an external Podman secret (`ga-transport-secret`) that Docker Compose does not support, so installation fails silently after images are already built. The installer must require and explicitly select `podman-compose`.

## What Changes

- `install.sh` prerequisite check requires `podman-compose` explicitly — fails fast before building if absent, rather than accepting `docker-compose` or `docker compose` as alternatives
- All three scripts (`install.sh`, `start.sh`, `uninstall.sh`) set `PODMAN_COMPOSE_PROVIDER=$(command -v podman-compose)` before every `podman compose` invocation to prevent Docker Compose from taking precedence
- `uninstall.sh` falls back to direct `podman rm` if `podman-compose` has already been removed, rather than risking Docker Compose provider selection
- README and docs updated to reflect `podman-compose` as a hard prerequisite (not one of several alternatives)

## Capabilities

### New Capabilities
- none

### Modified Capabilities
- `installation`: prerequisite check and compose invocation behaviour change — installer now requires `podman-compose` and pins the provider on every invocation

## Impact

- `scripts/install.sh` — prerequisite guard, `PODMAN_COMPOSE_PROVIDER` export before all `podman compose` calls
- `scripts/start.sh` — `PODMAN_COMPOSE_PROVIDER` export before `podman compose up`
- `scripts/uninstall.sh` — `PODMAN_COMPOSE_PROVIDER` export, fallback to direct `podman rm` if `podman-compose` absent
- `README.md` / `docs/manual-install.md` — clarify `podman-compose` as required, not optional alternative
