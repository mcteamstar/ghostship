## Why

`install.sh` launches `ga-transport` with a 40-line `podman run` block. `start.sh` needs an identical copy of those args as a fallback for when `podman start` fails after a cold reboot. Any new env var, volume, or port added to `install.sh` must also be added to `start.sh` manually — two places to maintain that will drift.

The right fix: generate a Compose file at install time and use `podman compose up -d` everywhere. Compose handles "already running", "stopped", and "container doesn't exist" transparently, removing the need for the cold-boot fallback entirely.

## What Changes

- **`install.sh`**: After building images, generate `${DATA_DIR}/compose.yml` with the full `ga-transport` service definition (image, ports, volumes, env vars, network, restart policy, security options, Podman socket path) baked in. Replace the `podman run` block with `podman compose -f "${DATA_DIR}/compose.yml" up -d`.
- **`start.sh`**: Replace the entire `podman start` + cold-boot `podman run` fallback block with `podman compose -f "${DATA_DIR}/compose.yml" up -d`. Drop the fallback — compose handles all cases.
- **`uninstall.sh`**: Replace `podman stop ga-transport && podman rm ga-transport` with `podman compose -f "${DATA_DIR}/compose.yml" down`.
- **Minimum Podman version**: Document `>= 4.4` requirement (compose is bundled). Already satisfied on all supported platforms.

## Capabilities

### Modified Capabilities
- `installation`: `ga-transport` lifecycle is now managed via a generated Compose file rather than raw `podman run`/`stop`/`rm` calls.

## Impact

- `install.sh`: Replace `podman run` block with compose file generation + `podman compose up`
- `start.sh`: Simplify dramatically — compose replaces all container start/fallback logic
- `uninstall.sh`: Replace stop/rm with compose down
- `docs/architecture.md`: Update "Starting and restarting" section to mention compose file
- `docs/manual-install.md`: Note Podman >= 4.4 requirement
- No changes to transport or crew container logic
