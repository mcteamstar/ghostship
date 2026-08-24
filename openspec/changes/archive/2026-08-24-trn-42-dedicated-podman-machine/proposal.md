# Proposal: Dedicated Podman Machine for KiroCrew Subagent Containers

## Problem

Today, Ghost Academy's transport container (`ga-transport`) manages crew containers via the host's default Podman socket — the same socket that all other containerised workloads on the host share. This coupling introduces several problems:

1. **Resource contention**: Crew containers compete with unrelated workloads for cgroup budgets, network bandwidth, and storage I/O on the same Podman runtime.
2. **Blast radius**: A misbehaving crew container (OOM, fork bomb, runaway I/O) can destabilise other host containers because they share the same runtime kernel namespace tree.
3. **Socket permission conflicts**: On macOS, the default `podman machine` is shared with IDE integrations, Docker-compatibility shims, and developer tooling — any of those can inadvertently stop or reconfigure it, taking Ghost Academy offline.
4. **Configuration rigidity**: Transport needs specific runtime settings (SELinux label=disable, memory limits, restart policies) that may conflict with the host operator's preferred defaults for other workloads.
5. **Upgrade isolation**: Updating the host Podman or its machine restarts all containers, including crew containers mid-task.

## Proposed Solution

Give Ghost Academy a **dedicated Podman machine** (on macOS) or a **dedicated rootless Podman instance with its own socket** (on Linux), exclusively for crew container management. The transport binds to this dedicated socket rather than the host's default.

### Key Properties

- **macOS**: A second `podman machine` named `ghostship` with its own VM, memory budget, and socket path — completely independent of the user's default machine.
- **Linux**: A dedicated systemd user service (`podman-ghostship.socket`) providing an isolated socket at a well-known path, with its own storage root (`--root`/`--runroot`) so containers are invisible to `podman ps` on the default instance.
- **Transport binding**: `ga-transport` mounts the dedicated socket instead of the default one; `PODMAN_SOCKET` env var points to the new path.
- **Backward compatible**: A config flag (`GA_DEDICATED_MACHINE=true|false`, default `false`) controls whether install.sh provisions the dedicated instance. Existing installs continue to work unchanged until the operator opts in.

## Motivation

- Enables running Ghost Academy alongside developer Podman usage without interference.
- Provides a clear resource boundary: operators can size the dedicated machine/instance independently.
- Simplifies troubleshooting: `podman --connection ghostship ps` shows only Ghost Academy containers.
- Allows independent lifecycle management (stop/upgrade the dedicated machine without touching dev containers, and vice versa).

## Scope

- `install.sh` changes to provision and manage the dedicated Podman machine/socket.
- `uninstall.sh` changes to tear down the dedicated instance.
- `server.py` — no logic changes required (already parameterised via `PODMAN_SOCKET` env var).
- Configuration documentation updates.
- New config variables: `GA_DEDICATED_MACHINE`, `GA_MACHINE_CPUS`, `GA_MACHINE_MEMORY`, `GA_MACHINE_DISK`.

## Out of Scope

- Migrating existing crew volumes from the default machine to the dedicated one (manual, documented).
- Multi-machine load balancing across multiple Podman instances.
- Rootful Podman support (the project is rootless-only).
