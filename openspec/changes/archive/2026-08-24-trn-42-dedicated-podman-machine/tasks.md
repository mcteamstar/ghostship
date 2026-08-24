# Tasks: trn-42-dedicated-podman-machine

## Phase 1: install.sh — Dedicated Machine Provisioning

- [x] Add `GA_DEDICATED_MACHINE`, `GA_MACHINE_CPUS`, `GA_MACHINE_MEMORY`, `GA_MACHINE_DISK`, `GA_MACHINE_NAME` to the config-file sourcing section (with defaults)
- [x] Add macOS path: detect `GA_DEDICATED_MACHINE=true`, check if machine `$GA_MACHINE_NAME` exists, init if not, start if not running
- [x] Enable `podman-restart.service` inside the dedicated machine's guest (same pattern as today but targeting named machine)
- [x] Resolve dedicated machine guest UID and socket path: `podman machine ssh $GA_MACHINE_NAME -- id -u`
- [x] Add Linux path: write `podman-ghostship.socket` and `podman-ghostship.service` systemd user units to `~/.config/systemd/user/`
- [x] Linux: `systemctl --user daemon-reload && enable --now podman-ghostship.socket`
- [x] Linux: validate dedicated socket exists with bounded retry (same 5s pattern as current socket check)
- [x] Linux: set `PODMAN_SOCK` to `/run/user/$(id -u)/podman/ghostship.sock`
- [x] Gate: when `GA_DEDICATED_MACHINE=false` or unset, skip all of the above and use existing default-socket logic unchanged
- [x] Ensure the `ga-net` network is created on the dedicated instance (it's instance-local)
- [x] Update the `podman run -d --name ga-transport ...` block to use the dedicated socket path when enabled

## Phase 2: uninstall.sh — Teardown

- [x] Detect whether a dedicated machine/instance exists (check for machine name on macOS, check for unit files on Linux)
- [x] macOS: `podman machine stop $GA_MACHINE_NAME && podman machine rm $GA_MACHINE_NAME`
- [x] Linux: `systemctl --user disable --now podman-ghostship.socket podman-ghostship.service`, remove unit files
- [x] Linux: optionally remove dedicated storage root (`~/.local/share/ghostship/`)
- [x] Print clear status messages indicating what was removed

## Phase 3: Configuration & Documentation

- [x] Add `── Dedicated Podman Machine ──` section to `config/ghostship.conf.example` with commented-out variables
- [x] Update `docs/configuration.md` variable table with `GA_DEDICATED_MACHINE`, `GA_MACHINE_CPUS`, `GA_MACHINE_MEMORY`, `GA_MACHINE_DISK`, `GA_MACHINE_NAME`
- [x] Update `docs/architecture.md` Components section to mention optional dedicated machine
- [x] Add troubleshooting entries to `docs/troubleshooting.md`: machine not starting, socket not found, storage on dedicated root, identifying which containers are on which instance

## Phase 4: Testing

- [x] Add test cases to `tests/test_install_config.sh` verifying: config variable parsing for new vars, socket path resolution logic for both platforms
- [x] Add dedicated-machine scenario to transport test suite: mock socket at dedicated path, verify `PodmanClient` connects correctly
- [x] Test idempotency: running `install.sh` twice with `GA_DEDICATED_MACHINE=true` does not error or re-init an existing machine
- [x] Test fallback: `GA_DEDICATED_MACHINE=false` uses default socket (regression)
- [x] Document manual test procedure for operators: verify with `podman --connection ghostship ps` and `podman machine list`
