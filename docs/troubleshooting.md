# Troubleshooting

## SELinux and Container Labels

### What `--security-opt label=disable` does

The `ga-transport` container is launched with `--security-opt label=disable`.
This tells Podman to skip SELinux label transitions — the container process
runs under the user's own SELinux context rather than being confined to a
container-specific domain (`container_t`).

### Why it's needed

The podman socket (`/run/user/<uid>/podman/podman.sock`) carries the
`user_tmp_t` label. When SELinux is enforcing (Fedora, RHEL, CentOS), a
confined container domain (`container_t`) is not permitted to connect to a
`user_tmp_t` socket — the access is silently denied even though DAC
permissions (Unix uid/gid) are correct. The result is a cryptic "Permission
denied" deep in the Python podman client.

### On non-SELinux hosts

On distributions without SELinux (Debian, Ubuntu, Arch, etc.), this flag is a
no-op and has no security impact.

### Blast-radius on SELinux hosts

The trade-off is intentional:

- The container is **rootless** — it cannot escalate to host root.
- It binds only to **localhost** — no network-accessible attack surface.
- It mounts a limited set of paths (data dir, agents, skills, socket).

For this deployment model, the practical risk of running without MAC-layer
confinement is low.

### Supplying a custom SELinux policy (advanced)

If your security requirements mandate full SELinux enforcement, you can:

1. Write a custom policy module that grants the container's domain access to
   the `user_tmp_t` socket and the mounted volume labels.
2. Install it:
   ```bash
   sudo semodule -i ghostship-transport.pp
   ```
3. Remove `--security-opt label=disable` from the `podman run` invocation in
   `install.sh` (or add `--security-opt label=type:ghostship_transport_t`
   to assign your custom domain).
4. Verify with: `sudo ausearch -m AVC -ts recent | grep ga-transport`

A template policy module is not shipped — it depends on your exact SELinux
policy version and custom local modules. Start with `audit2allow` against the
AVC denials you see when running without `label=disable`.

## Podman Socket Not Found

If `install.sh` reports the socket was not found:

1. Check systemd socket activation:
   ```bash
   systemctl --user status podman.socket
   ```
2. Verify the actual path:
   ```bash
   podman info --format '{{.Host.RemoteSocket.Path}}'
   ```
3. If the path differs from the default, set it before running install:
   ```bash
   export PODMAN_SOCK=/actual/path/podman.sock
   ./install.sh
   ```

## Linger and Reboot Recovery

`install.sh` enables linger automatically (`loginctl enable-linger`). This
keeps your systemd user slice alive after logout, so the transport container
and podman socket survive reboots and disconnected sessions.

To verify:
```bash
loginctl show-user "$(whoami)" --property=Linger
# Expected: Linger=yes
```

If your sysadmin has disabled linger at the system level, the transport will
stop when your last login session ends. In that case, either:
- Re-run `install.sh` after each login, or
- Ask your admin to allow linger for your account.

## Crew Launch Failures

### Image not found

If `launch` returns an error about the crew image:

```
Error: localhost/spec-ops:latest: image not known
```

The crew image was never built or has been pruned. Re-run `./install.sh` —
it rebuilds both images (`localhost/transport:latest` and
`localhost/spec-ops:latest`) unconditionally.

### Socket not reachable during launch

If `launch` times out waiting for the gateway:

```
Timed out waiting for crew gateway (30s)
```

1. Check that the container actually started:
   ```bash
   podman ps -a --filter name=gs-
   ```
2. Check container logs for early crashes:
   ```bash
   podman logs gs-<crew_id>
   ```
3. Verify the `ga-net` network exists and the container joined it:
   ```bash
   podman network inspect ga-net
   ```

If the container exits immediately, it's usually a missing auth file or a
corrupt volume. Try `nuke(crew_id, confirm=True)` and re-launch.

### Cookie mint failure

If launch succeeds but operations fail with authentication errors, the
session cookie may have failed to mint. Symptoms:

- `pickup` or `dispatch` returns 401/403
- Transport logs show `_mint_cookie: no cookie in response`

**Cause:** The `kirocrew token --ttl` command inside the crew container
failed (often because the gateway hadn't fully started when the cookie
was requested).

**Fix:** The next `dispatch`, `pickup`, or `steer` call triggers
`_ensure_crew_running`, which re-mints the cookie automatically. If the
problem persists, restart the crew manually:
```bash
podman restart gs-<crew_id>
```

## Memory Pressure (OOM)

The transport has a pre-launch memory gate controlled by `GA_MIN_FREE_MEM_GB`
(default `2.0`). Before starting a crew container, the transport checks
available host memory and waits up to `GA_MEMORY_WAIT_SECS` (default `60`)
for sufficient headroom.

### Symptoms

- `launch` returns: `Insufficient memory: <N> GB free, need <M> GB`
- Existing crews become unresponsive or are OOM-killed by the host

### Workarounds

1. **Reduce concurrent crews:** Lower `GA_MAX_CREWS` to limit how many
   containers run simultaneously.
2. **Disable the gate (not recommended):** Set `GA_MIN_FREE_MEM_GB=0` to
   skip the pre-launch check entirely. This allows launches to proceed
   regardless of available memory but risks OOM kills.
3. **Tune per-crew subagent limits:** `GA_SPAWN_MIN_MEMORY_GB` (default
   `1.5`) controls how much memory a crew requires before spawning
   sub-agents inside itself. Lower it to allow sub-agents under tighter
   memory, or raise it to back-pressure earlier.
4. **Add swap or increase VM memory:** On macOS (`podman machine`), increase
   the VM's memory allocation:
   ```bash
   podman machine set --memory 8192
   podman machine stop && podman machine start
   ```

### Resource pressure tiers

The transport patches three thresholds into each crew's KiroCrew config:

| Variable | Default | Effect inside the crew |
|:---------|:--------|:-----------------------|
| `GA_SPAWN_MIN_MEMORY_GB` | `1.5` | Hard floor — no sub-agents below this |
| `GA_RESOURCE_PRESSURE_GB` | `2.0` | Throttles sub-agent spawning |
| `GA_RESOURCE_CRITICAL_GB` | `1.0` | Refuses all sub-agent spawning |

Set `GA_SPAWN_MIN_MEMORY_GB` lower than `GA_MIN_FREE_MEM_GB` so the
transport's outer gate triggers first and provides a clearer error.

## Bootstrap crash (`_bootstrap.p`)

**Status:** Known issue, tracked in TRN-16. A fix is pending.

If a crew container crashes during early startup with a traceback referencing
`_bootstrap.p` or `pickle` deserialization, this is a known race condition in
the crew image's initial setup. The workaround is to nuke and relaunch:

```bash
# Via MCP:
nuke(crew_id="<id>", confirm=True)
launch(crew_id="<id>")
```

This section will be expanded with root cause and permanent fix once TRN-16
is applied.