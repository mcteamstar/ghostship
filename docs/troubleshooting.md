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

## Dedicated Podman Machine

These issues apply only when `GA_DEDICATED_MACHINE=true`.

### Dedicated machine not starting (macOS)

If `install.sh` fails with a machine-related error:

1. List all machines and check their state:
   ```bash
   podman machine list
   ```
2. If the `ghostship` machine shows as "stopped", start it manually:
   ```bash
   podman machine start ghostship
   ```
3. If `init` failed (machine doesn't appear in the list), check available
   disk and memory — the machine requires the configured `GA_MACHINE_DISK`
   (default 100 GB) free disk space.
4. Check for conflicting machine names:
   ```bash
   podman machine inspect ghostship
   ```

### Dedicated socket not found (Linux)

If `install.sh` reports the dedicated socket was not found:

1. Check the systemd socket unit:
   ```bash
   systemctl --user status podman-ghostship.socket
   journalctl --user -u podman-ghostship.service --since "5 min ago"
   ```
2. Verify the socket file exists:
   ```bash
   ls -la /run/user/$(id -u)/podman/ghostship.sock
   ```
3. If the socket unit failed, reload and restart:
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart podman-ghostship.socket
   ```
4. Ensure the `ListenStream` path directory exists:
   ```bash
   mkdir -p /run/user/$(id -u)/podman
   ```

### Storage space on dedicated root (Linux)

The dedicated instance stores all containers and images under
`~/.local/share/ghostship/containers/storage`. This is separate from your
default Podman storage, so images are NOT shared — base images are pulled
separately into the dedicated storage.

To check disk usage:
```bash
du -sh ~/.local/share/ghostship/
```

To prune unused images on the dedicated instance:
```bash
podman --root=~/.local/share/ghostship/containers/storage \
  --runroot=$XDG_RUNTIME_DIR/ghostship-containers \
  image prune -a
```

### Identifying which containers are on which instance

**macOS** — use the named connection:
```bash
# Default machine containers:
podman ps

# Dedicated machine containers (requires connection setup):
podman machine ssh ghostship -- podman ps
```

**Linux** — pass the storage root:
```bash
# Default instance containers:
podman ps

# Dedicated instance containers:
podman --root=~/.local/share/ghostship/containers/storage \
  --runroot=$XDG_RUNTIME_DIR/ghostship-containers \
  ps
```

You can alias this for convenience:
```bash
alias podman-gs='podman --root=~/.local/share/ghostship/containers/storage --runroot=$XDG_RUNTIME_DIR/ghostship-containers'
podman-gs ps
podman-gs images
```

## Known workarounds

These are deliberate hacks for upstream bugs or limitations. Each is marked with
`# WORKAROUND:` in the source and should be removed when the upstream issue is fixed.

### spawn_min_memory_gb not read from config files (KiroCrew bug)

**Symptom:** Agent spawns are refused with "only N GB available (need 4 GB)" even
after setting `spawn_min_memory_gb: 0` in `config.local.json` or `config.json`.

**Root cause:** KiroCrew's `AgentConfig` loader explicitly constructs the config
object from a dict but never reads `spawn_min_memory_gb` — the field always uses
its dataclass default of `4.0`. Other fields (`resource_pressure_gb`,
`resource_critical_gb`) are read correctly. Only `spawn_min_memory_gb` is affected.

**Workaround (in `_ensure_crew_running`):** After every container restart, re-run
`_patch_crew_config` (which writes `spawn_min_memory_gb=0` into `config.json`),
then stop and restart the gateway so it re-seeds `config.json` before the loader
runs. This adds one extra stop/start cycle to every auto-restart but is the only
reliable way to keep the spawn gate disabled across restarts.

**Remove when:** KiroCrew upstream fixes `AgentConfig.load()` to read
`spawn_min_memory_gb` from `config.local.json`.

### Direct SQLite writes into kiro-cli's internal database

**Location:** `_inject_auth`, `_read_auth_from_crew` in `transport/server.py`.

**What we do:** Write auth rows directly into kiro-cli's `auth_kv` SQLite table
using `INSERT OR REPLACE`, bypassing kiro-cli's own migration and ORM layer. We
also read rows back the same way to copy auth between containers.

**Why it's fragile:** If kiro-cli changes the `auth_kv` schema (renames the table,
adds a NOT NULL column, changes key names, or moves to a different storage
backend), auth injection silently fails — no error is raised, crews just fail to
authenticate. The comment "schema and migrations are pre-seeded in the crew image"
is true but only holds as long as the upstream schema is stable.

**Why we do it:** kiro-cli provides no external API for injecting auth. The only
alternative is running `kiro-cli login` inside every new crew container, which
requires a full device auth flow per crew. Direct DB writes let us authenticate
once and propagate to all crews.

**Remove when:** kiro-cli exposes an official mechanism for pre-seeding auth
(config file, env var, or CLI flag).

### Cookie minting via `kirocrew token` + HTTP Set-Cookie header scraping

**Location:** `_mint_cookie` in `transport/server.py`.

**What we do:** Run `kirocrew token --ttl <ttl>` inside the container to get a
short-lived token, then make an HTTP GET to the gateway with that token as a query
param and scrape the `mc_token_5476=` value from the `Set-Cookie` response header
by string splitting.

**Why it's fragile:** The cookie name `mc_token_5476` is port-specific — it
embeds the gateway port. If the port changes, the scraping logic breaks silently
(no cookie found, all crew operations fail). The token-exchange flow is also
undocumented internal KiroCrew API that could change without notice.

**Why we do it:** The gateway requires a session cookie for all API calls. There
is no documented way to mint one from outside the gateway. The `kirocrew token`
subcommand is the only path we found.

**Remove when:** KiroCrew exposes a stable, documented way to obtain a session
credential for the gateway REST API.

### Idle-stop vs. nuke

These are two distinct lifecycle operations and should not be confused:

- **Idle-stop** — automatic, transparent, reversible, no data loss. The container
  stops after a timeout and restarts on the next command. This is the normal
  resource management path; operators do not need to take any action.
- **Nuke** — explicit, permanent, workspace-destroying. Removes the container and
  both volumes entirely. Use only when you intentionally want to discard the
  crew's workspace, history, and context. Not a routine post-task step.

Idle-stop is what keeps a fleet of crews from consuming resources when inactive.
Nuke is for when a crew's purpose is fully served and its data is no longer needed.
