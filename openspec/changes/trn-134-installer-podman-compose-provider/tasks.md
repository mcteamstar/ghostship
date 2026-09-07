## 1. install.sh — prerequisite guard

- [x] 1.1 Replace the multi-provider compose check (lines 228–230 of `scripts/install.sh`) with a check for `podman-compose` only — fail if `command -v podman-compose` returns nothing, regardless of whether `docker-compose` or `docker compose` is available
- [x] 1.2 Update the error message to clarify that `docker-compose` is not accepted because Ghostship uses external Podman secrets
- [x] 1.3 Set `PODMAN_COMPOSE_PROVIDER="$(command -v podman-compose)"` and export it before the `podman compose up` call near line 918

## 2. start.sh — provider pin

- [x] 2.1 Set `PODMAN_COMPOSE_PROVIDER="$(command -v podman-compose)"` and export it before the `podman compose up` call in `scripts/start.sh`

## 3. uninstall.sh — provider pin and fallback

- [x] 3.1 Set `PODMAN_COMPOSE_PROVIDER="$(command -v podman-compose)"` and export it before the `podman compose down` call in `scripts/uninstall.sh`
- [x] 3.2 Add a guard: if `podman-compose` is not found, skip `podman compose down` and instead remove containers directly with `podman rm -f ga-transport ga-portal`

## 4. Documentation

- [x] 4.1 Update `README.md` prerequisites section to list `podman-compose` as required (not one of several alternatives) — remove mention of `docker-compose` as acceptable
- [x] 4.2 Update `docs/manual-install.md` similarly if it references `docker-compose` as an alternative

## 5. Validation

- [x] 5.1 Run `openspec validate` to confirm delta spec is clean
- [x] 5.2 Run `bash tests/run.sh --unit` to confirm no regressions
- [ ] 5.3 Manual smoke-test on macOS with both `podman-compose` and `docker-compose` installed — verify `podman-compose` is used
- [ ] 5.4 Manual test: remove `podman-compose`, confirm `install.sh` fails fast before building images
