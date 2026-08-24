# Design: Dedicated Podman Machine

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Host (macOS / Linux)                                           │
│                                                                 │
│  ┌──────────────────────┐     ┌──────────────────────────────┐  │
│  │ Default Podman        │     │ Dedicated "ghostship" Podman  │  │
│  │ (user's dev work)     │     │ (GA-exclusive)                │  │
│  │                       │     │                               │  │
│  │ socket: default path  │     │ socket: /run/user/UID/podman/ │  │
│  │                       │     │         ghostship.sock (Linux) │  │
│  │                       │     │   or: ~/.local/share/          │  │
│  │                       │     │         ghostship/podman.sock  │  │
│  │                       │     │         (macOS guest)          │  │
│  └──────────────────────┘     │                               │  │
│                                │  ┌─────────────────────────┐  │  │
│                                │  │ ga-transport            │  │  │
│                                │  │ (binds dedicated sock)  │  │  │
│                                │  ├─────────────────────────┤  │  │
│                                │  │ gs-crew-1  gs-crew-2    │  │  │
│                                │  │ (crew containers)       │  │  │
│                                │  └─────────────────────────┘  │  │
│                                └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Platform Strategies

### macOS: Dedicated `podman machine`

**Approach**: Create a second machine named `ghostship` with dedicated resources.

```bash
podman machine init ghostship \
  --cpus ${GA_MACHINE_CPUS:-4} \
  --memory ${GA_MACHINE_MEMORY:-8192} \
  --disk-size ${GA_MACHINE_DISK:-60}
podman machine start ghostship
```

**Socket resolution**: The dedicated machine exposes its own API socket. On macOS, `podman machine inspect ghostship` returns the host-side forwarded socket path. However, the transport runs *inside* the guest VM, so it needs the in-guest socket path:

```bash
GUEST_UID=$(podman machine ssh ghostship -- id -u)
PODMAN_SOCK="/run/user/${GUEST_UID}/podman/podman.sock"
```

This is the same pattern as today, except scoped to the `ghostship` machine instead of the default one.

**Connection identity**: Register as a named Podman connection for operator convenience:
```bash
podman system connection add ghostship \
  --identity ~/.ssh/ghostship \
  ssh://core@localhost:<port>/run/user/501/podman/podman.sock
```

### Linux: Dedicated Podman Instance (Separate Storage Root)

**Approach**: Run a second rootless Podman daemon under a dedicated systemd socket unit with isolated storage.

**Systemd units** (`~/.config/systemd/user/`):

`podman-ghostship.socket`:
```ini
[Unit]
Description=Ghost Academy dedicated Podman socket

[Socket]
ListenStream=%t/podman/ghostship.sock
SocketMode=0660

[Install]
WantedBy=sockets.target
```

`podman-ghostship.service`:
```ini
[Unit]
Description=Ghost Academy dedicated Podman API
Requires=podman-ghostship.socket

[Service]
Type=exec
ExecStart=/usr/bin/podman \
  --root=%h/.local/share/ghostship/containers/storage \
  --runroot=%t/ghostship-containers \
  system service --time=0 unix://%t/podman/ghostship.sock
Restart=on-failure

[Install]
WantedBy=default.target
```

**Socket path**: `/run/user/<UID>/podman/ghostship.sock`

**Isolation**: Using `--root` and `--runroot` ensures:
- `podman ps` on the default instance never sees GA containers
- Container images, layers, and volumes are fully separate
- No lock contention between the two Podman instances

## Configuration

### New Environment Variables

| Variable | Default | Description |
|:---------|:--------|:------------|
| `GA_DEDICATED_MACHINE` | `false` | Enable dedicated Podman machine/instance |
| `GA_MACHINE_CPUS` | `4` | CPUs for the dedicated machine (macOS only) |
| `GA_MACHINE_MEMORY` | `8192` | Memory in MB for the dedicated machine (macOS only) |
| `GA_MACHINE_DISK` | `60` | Disk size in GB for the dedicated machine (macOS only) |
| `GA_MACHINE_NAME` | `ghostship` | Name of the dedicated machine/service |

### Config File Example

```bash
# ghostship.conf additions
GA_DEDICATED_MACHINE=true
GA_MACHINE_CPUS=6
GA_MACHINE_MEMORY=12288
GA_MACHINE_DISK=100
```

## Install Flow Changes

### With `GA_DEDICATED_MACHINE=true`

**macOS:**
1. Check if machine `ghostship` exists → if not, `podman machine init ghostship ...`
2. Check if machine `ghostship` is running → if not, `podman machine start ghostship`
3. Enable `podman-restart.service` inside the ghostship guest
4. Resolve guest socket path from the ghostship machine
5. Proceed with transport container creation using the dedicated socket

**Linux:**
1. Write `podman-ghostship.socket` and `podman-ghostship.service` unit files
2. `systemctl --user daemon-reload`
3. `systemctl --user enable --now podman-ghostship.socket`
4. Validate socket exists at `/run/user/<UID>/podman/ghostship.sock`
5. Proceed with transport container creation using the dedicated socket

### With `GA_DEDICATED_MACHINE=false` (default)

Behaviour is unchanged from today — uses the default Podman socket.

## Uninstall Flow Changes

When `GA_DEDICATED_MACHINE` was enabled:

**macOS:**
1. Stop and remove all GA containers on the ghostship machine
2. `podman machine stop ghostship`
3. `podman machine rm ghostship` (optionally; flag `--keep-machine` to preserve)

**Linux:**
1. Stop and remove all GA containers on the dedicated instance
2. `systemctl --user disable --now podman-ghostship.socket podman-ghostship.service`
3. Remove unit files
4. Optionally remove storage root (`~/.local/share/ghostship/`)

## Network Considerations

The `ga-net` network must exist within the dedicated Podman instance (it is instance-local by nature). Since the transport container runs inside the dedicated instance, all crew containers also run there — they naturally share `ga-net` within that instance. No cross-instance networking is needed.

## Migration Path

For operators with existing crews on the default machine:
1. `nuke` existing crews (volumes are ephemeral by design)
2. Enable `GA_DEDICATED_MACHINE=true` in config
3. Re-run `install.sh`
4. `launch` crews fresh on the new instance

No volume migration tool is needed because crew state is ephemeral (workspace data is transferred via bundles, and auth is re-injected at launch).

## Risks and Mitigations

| Risk | Mitigation |
|:-----|:-----------|
| macOS: Two machines double host memory usage | Document sizing guidance; default resources match current single-machine defaults |
| Linux: Separate storage root doubles image disk usage | Share base image layers via `--imagestore` (Podman 5+) or accept the duplication and document `podman --root=... image prune` |
| Operator confusion about which machine is which | `install.sh` prints clear status; `podman machine list` / `podman system connection list` shows both |
| Dedicated machine not started after reboot | Same `podman-restart.service` pattern as today; documented in troubleshooting |
