## Context

See proposal.md for motivation. Three scripts manage the container lifecycle: `scripts/install.sh`, `scripts/start.sh`, and `scripts/uninstall.sh`. All invoke `podman compose`, which delegates to an external provider. The provider is selected by Podman's documented precedence: `$PODMAN_COMPOSE_PROVIDER` env var > `podman-compose` binary > `docker-compose` binary. Currently none of the scripts set `PODMAN_COMPOSE_PROVIDER`, so on hosts where Docker Compose is installed and `podman-compose` is not, Docker Compose silently wins.

`install.sh`'s prerequisite guard (lines 228–240 of `scripts/install.sh`) currently passes if any compose provider is found — including Docker Compose — rather than requiring `podman-compose` specifically.

## Goals / Non-Goals

**Goals:**
- Fail fast before any build work when `podman-compose` is absent
- Pin `PODMAN_COMPOSE_PROVIDER` in all three scripts so provider selection is deterministic regardless of what else is installed
- Handle `uninstall.sh` when `podman-compose` has already been removed

**Non-Goals:**
- Adding Docker Compose support — Ghostship uses external Podman secrets and this is not changing
- Changing how the compose file is generated

## Decisions

**D1: Check for `podman-compose` specifically, not any compose provider**

The prerequisite guard becomes a simple `command -v podman-compose` check. The multi-provider OR condition is removed. Rationale: Docker Compose cannot work with this Compose file; accepting it at the prerequisite stage only delays the failure to a less informative point.

**D2: Set `PODMAN_COMPOSE_PROVIDER` inline, not as a permanent env export**

Each script sets `PODMAN_COMPOSE_PROVIDER="$(command -v podman-compose)"` as a local variable before every `podman compose` call (or prepends it to the eval). This is the Podman-documented override mechanism and ensures correctness even if the user's shell already has the variable set to something else.

**D3: `uninstall.sh` falls back to direct `podman rm` if `podman-compose` is absent**

If someone manually removed `podman-compose` before uninstalling Ghostship, `uninstall.sh` should still work. When `podman-compose` is not found, skip the `podman compose down` step and remove containers directly with `podman rm -f ga-transport ga-portal`. This matches existing fallback logic already present in `uninstall.sh` for the Compose file being absent.

## Risks / Trade-offs

- [Risk] A user who deliberately uses Docker Compose for other Podman projects may be confused by the explicit rejection. → Mitigation: clear error message explaining why `podman-compose` is specifically required (external Podman secret).
- [Risk] `PODMAN_COMPOSE_PROVIDER` may already be set in the user's environment to a different value. → Mitigation: scripts override it explicitly rather than relying on inherited value.

## Migration Plan

No migration needed — this is an installer behaviour change. Existing installations are unaffected; the fix applies on the next `./install.sh` run. No rollback strategy needed as the change is additive (stricter checks, same outcome when `podman-compose` is present).

## Open Questions

None.
