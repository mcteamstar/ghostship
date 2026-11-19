# Troubleshooting

## Podman Command Context

Ghostship uses a dedicated Podman machine or instance by default. Set
`GA_MACHINE_NAME` and `GA_DEDICATED_MACHINE` to the values used by your
installation before running these examples; the defaults are
`ghost-academy` and `true`. On Linux, the dedicated container store is under
`$HOME/.local/share/<machine-name>` even when `XDG_DATA_HOME` changes
Ghostship's data directory.

Run this Bash setup once in the shell where you will run the examples:

```bash
MACHINE_NAME=${GA_MACHINE_NAME:-ghost-academy}
RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}

if [[ "${GA_DEDICATED_MACHINE:-true}" != "true" ]]; then
  podman-gs() { podman "$@"; }
elif [[ "$(uname -s)" == "Darwin" ]]; then
  podman-gs() { podman --connection="$MACHINE_NAME" "$@"; }
else
  STORAGE_ROOT="$HOME/.local/share/${MACHINE_NAME}/containers/storage"
  RUN_ROOT="${RUNTIME_DIR}/${MACHINE_NAME}-containers"
  CONTAINERS_CONF="$HOME/.config/${MACHINE_NAME}/containers.conf"
  podman-gs() {
    env CONTAINERS_CONF="$CONTAINERS_CONF" podman \
      --root="$STORAGE_ROOT" --runroot="$RUN_ROOT" "$@"
  }
fi
```

## SELinux and Container Labels

### What `--security-opt label=disable` does

The `ga-transport` container is launched with `--security-opt label=disable`.
This tells Podman to skip SELinux label transitions — the container process
runs under the user's own SELinux context rather than being confined to a
container-specific domain (`container_t`).

### Why it's needed

The `PODMAN_SOCK` path is configured by the installer. On Linux, the default
dedicated socket is `/run/user/<uid>/ghost-academy/podman.sock` (or
`${XDG_RUNTIME_DIR:-/run/user/<uid>}/${GA_MACHINE_NAME}/podman.sock` with
custom values); when `GA_DEDICATED_MACHINE=false`, the default socket is
`/run/user/<uid>/podman/podman.sock`. The socket carries the
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
3. Remove the `label=disable` entry from `security_opt` for `ga-transport` in
   the `compose.yml` that `install.sh` generates (or add `--security-opt label=type:ghostship_transport_t`
   to assign your custom domain).
4. Verify with: `sudo ausearch -m AVC -ts recent | grep ga-transport`

A template policy module is not shipped — it depends on your exact SELinux
policy version and custom local modules. Start with `audit2allow` against the
AVC denials you see when running without `label=disable`.

## Podman Socket Not Found

These steps apply when `GA_DEDICATED_MACHINE=false` or when you intentionally
use the default Podman socket. For the default dedicated setup, use the
dedicated service instructions below.

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

The crew image was never built or has been pruned. Re-run `./install.sh` to
build the five main images: `localhost/base-admission:latest`,
`localhost/gs-worker:latest`, `localhost/spec-ops:latest`,
`localhost/transport:latest`, and `localhost/ga-radar:latest`. Building
`spec-ops` also creates `localhost/spec-ops-mid:latest` as an intermediate
image.

### Socket not reachable during launch

If `launch` times out waiting for the gateway:

```
Timed out waiting for crew gateway (30s)
```

1. Check that the container actually started on Ghostship's instance:
   ```bash
   podman-gs ps -a --filter name=gs-
   ```
2. Check container logs for early crashes:
   ```bash
   podman-gs logs gs-<crew_id>
   ```
3. Verify the `ga-starboard` network exists and the container joined it:
   ```bash
   podman-gs network inspect ga-starboard
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
podman-gs restart gs-<crew_id>
```

## Memory Pressure (OOM)

The transport has a pre-launch memory gate controlled by `GA_MIN_FREE_MEM_GB`
(default `2.0`). Before starting a crew container, the transport checks
available host memory and waits up to 60 seconds for sufficient headroom
(this wait duration is hardcoded and is not configurable via environment variable).

### Symptoms

- `launch` returns: `Insufficient memory: <N> GB free, need <M> GB`
- Existing crews become unresponsive or are OOM-killed by the host

### Workarounds

1. **Reduce concurrent crews:** Lower `GA_MAX_ACTIVE_CREWS` to limit how many
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
   podman machine set --memory 8192 "$MACHINE_NAME"
   podman machine stop "$MACHINE_NAME" && podman machine start "$MACHINE_NAME"
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

## "profileArn is required for this request"

This error occurs during dispatch or authentication. Two common causes:

**Stale kiro credential** — the stored token has expired or become invalid. Fix by cycling auth:

```bash
ghostship auth logout kiro
ghostship auth login kiro
```

**Wrong model-ID spelling** — for example `claude-haiku-5-5` instead of `claude-haiku-5.5` (hyphens vs dots). Update the model ID in your configuration and re-run `./install.sh` to apply it.

Backend selection is configured separately from model selection. Set a scalar
`backends.default` for the implicit backend; Kiro is always built in, while Claude
and Codex are bundled only when their sections are present. Use an empty mapping to
enable an optional backend with its built-in defaults:

```yaml
backends:
  default: kiro
  claude: {}
  codex: {}
```

The legacy list form (`backends.default: [kiro, claude]`) is no longer accepted.

## Dedicated Podman Machine

These issues apply when `GA_DEDICATED_MACHINE=true` (the default). Run the
Podman command-context setup above first. On Linux, `XDG_RUNTIME_DIR` defaults
to `/run/user/$(id -u)`; `XDG_DATA_HOME` changes Ghostship's data directory,
but not the dedicated container store.

### Dedicated machine not starting (macOS)

If `install.sh` fails with a machine-related error:

1. List all machines and check their state:
   ```bash
   podman machine list
   ```
2. If the dedicated machine shows as "stopped", start it manually:
   ```bash
   podman machine start "$MACHINE_NAME"
   ```
3. If `init` failed (machine doesn't appear in the list), check available
   disk and memory — the machine requires the configured `GA_MACHINE_DISK`
   (default 100 GB) free disk space.
4. Check for conflicting machine names:
   ```bash
   podman machine inspect "$MACHINE_NAME"
   ```

### Dedicated socket not found (Linux)

If `install.sh` reports the dedicated socket was not found:

1. Check the dedicated systemd service:
   ```bash
   systemctl --user status "podman-${MACHINE_NAME}.service"
   journalctl --user -u "podman-${MACHINE_NAME}.service" --since "5 min ago"
   ```
2. Verify the socket file exists:
   ```bash
   ls -la "${RUNTIME_DIR}/${MACHINE_NAME}/podman.sock"
   ```
3. If the service failed, reload and restart it:
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart "podman-${MACHINE_NAME}.service"
   ```
4. The service unit creates `${RUNTIME_DIR}/${MACHINE_NAME}` with systemd's
   `RuntimeDirectory` setting. If the directory is missing, check the service
   journal after restarting it.

### Storage space on dedicated root (Linux)

The dedicated instance stores all containers and images under
`$HOME/.local/share/${MACHINE_NAME}/containers/storage`. This is separate from
your default Podman storage, so images are not shared. The installer uses
`${RUNTIME_DIR}/${MACHINE_NAME}-containers` as the runroot. `XDG_DATA_HOME`
changes the Ghostship data directory; it does not relocate these container
storage paths.

To check disk usage:
```bash
du -sh "$STORAGE_ROOT"
```

To prune unused images on the dedicated instance:
```bash
podman-gs image prune -a
```

### Identifying which containers are on which instance

**macOS** — use the named connection:
```bash
# Host's default Podman instance (separate from Ghostship):
podman ps

# Containers on Ghostship's dedicated machine:
podman machine ssh "$MACHINE_NAME" -- podman ps
```

**Linux** — pass the storage root:
```bash
# Host's default Podman instance (separate from Ghostship):
podman ps

# Dedicated Ghostship instance containers:
podman-gs ps
```

The `podman-gs` helper targets the dedicated storage for convenience:
```bash
podman-gs ps
podman-gs images
```

## Known workarounds

These are deliberate hacks for upstream limitations, marked `# WORKAROUND:` in the source.

### spawn_min_memory_gb not read from config files (KiroCrew)

**Symptom:** Agent spawns are refused with "only N GB available (need 4 GB)" even after setting `spawn_min_memory_gb: 0` in config.

**Root cause:** KiroCrew's config loader does not read `spawn_min_memory_gb` from config files — the field always uses its dataclass default of `4.0`. Other threshold fields are read correctly.

**Workaround:** After every container restart, `_patch_crew_config` re-writes `spawn_min_memory_gb=0` into `config.json` and restarts the gateway. This adds one extra stop/start cycle to every auto-restart.

### Direct SQLite writes into kiro-cli's internal database

**Location:** `_inject_auth`, `_read_auth_from_crew` in `transport/lifecycle.py`.

**What we do:** Write auth rows directly into kiro-cli's `auth_kv` SQLite table using `INSERT OR REPLACE`, bypassing kiro-cli's own ORM layer. We also read rows back to copy auth between containers.

**Why:** kiro-cli provides no external API for injecting auth. Direct DB writes let us authenticate once and propagate to all crews without running a full device auth flow per container.

### Cookie minting via `kirocrew token` + HTTP Set-Cookie header scraping

**Location:** `_mint_cookie` in `transport/lifecycle.py`.

**What we do:** Run `kirocrew token --ttl <ttl>` inside the container to get a short-lived token, then make an HTTP GET to the gateway with that token as a query param and scrape the `mc_token_5476=` value from the `Set-Cookie` response header.

**Why:** The gateway requires a session cookie for all API calls. There is no documented way to mint one from outside the gateway.

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

## Podman Runtime Failures

These sections cover Podman failures that occur after a successful install — the
machine or socket was working before and stopped working (e.g. after a reboot,
a permission change, or a corrupted storage state).

Run the Podman command-context setup at the top of this guide before these
examples; it resolves `MACHINE_NAME` and `RUNTIME_DIR` and defines the
`podman-gs` helper.

### Podman version below the documented minimum

Ghostship documents Podman 4.4 or newer as its minimum prerequisite. The
installer checks that `podman` is available, but it does not enforce a version
floor. Check the installed version with:

```bash
podman --version
```

### Podman machine not started (macOS)

**Symptom:** The Podman socket path exists but every command returns "connection
refused" or "failed to connect to socket".

This usually means the dedicated Podman machine was stopped (e.g. after a
reboot or `podman machine stop`). Its name is `$MACHINE_NAME` (default
`ghost-academy`).

1. Check which machines exist and their state:
   ```bash
   podman machine list
   ```
2. Start the dedicated machine:
   ```bash
   podman machine start "$MACHINE_NAME"
   ```
3. Verify the machine is running and the socket is live:
   ```bash
   podman machine list
   # Look for "$MACHINE_NAME" in the list with state "Running"

   podman --connection="$MACHINE_NAME" info --format '{{.Host.RemoteSocket.Path}}'
   # Should print a non-empty socket path
   ```
4. Once the machine is running, retry your ghostship command.

If the machine does not appear in `podman machine list`, it was never
initialised — run `./install.sh` to create it.

### Dedicated Podman service socket permissions (Linux)

**Symptom:** `ghostship status` or any podman command fails with "permission
denied" on the socket, or the socket file is owned by a different user.

When `GA_DEDICATED_MACHINE=true`, Ghostship runs a dedicated systemd service
(`podman-${MACHINE_NAME}.service`). The service creates its socket at
`${RUNTIME_DIR}/${MACHINE_NAME}/podman.sock`. If the socket is owned by root or
by another user, the rootless Podman client cannot connect.

1. Check ownership and permissions of the runtime directory:
   ```bash
   ls -la "$RUNTIME_DIR"
   # Expected: the directory and its contents are owned by your uid
   ```
2. Check the status of the dedicated service:
   ```bash
   systemctl --user status "podman-${MACHINE_NAME}.service"
   ```
3. If the unit is failed or the socket is missing, reload and restart:
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart "podman-${MACHINE_NAME}.service"
   ```
4. Verify the socket is available and connectable:
   ```bash
   ls -la "${RUNTIME_DIR}/${MACHINE_NAME}/podman.sock"
   podman --url "unix://${RUNTIME_DIR}/${MACHINE_NAME}/podman.sock" info
   ```

If the unit file itself is missing, re-run `./install.sh` — it writes and
enables the dedicated service unit.

### Socket exists but Podman returns errors

**Symptom:** The socket file exists and the service is running, but podman
commands fail with errors like:

```
ERRO[0000] cannot set up namespace: ...
ERRO[0000] exec container process ...
```

This typically indicates a rootless namespace conflict.

1. Check that `newuidmap` and `newgidmap` are installed and have the `setuid`
   bit set:
   ```bash
   which newuidmap
   ls -la $(which newuidmap)
   # Expected: -rwsr-xr-x ... (the 's' in the owner execute bit is the setuid bit)
   ```
   If the bit is missing, install the `shadow-utils` or `uidmap` package
   and verify the setuid bit is restored:
   ```bash
   sudo chmod u+s $(which newuidmap) $(which newgidmap)
   ```
2. Verify `/etc/subuid` and `/etc/subgid` have entries for your user:
   ```bash
   grep "^$(whoami):" /etc/subuid
   grep "^$(whoami):" /etc/subgid
   # Expected: myuser:100000:65536
   ```
   If entries are missing, add them:
   ```bash
   sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$(whoami)"
   ```
3. Re-run the migration to apply the new sub-id ranges:
   ```bash
   podman-gs system migrate
   ```

**Last resort — reset Ghostship's dedicated Podman storage:**

> ⚠️ **Data loss warning:** `podman-gs system reset --force` permanently
> deletes all containers, images, and volumes in Ghostship's dedicated
> instance, including crew containers and their workspaces. Run `evac` on all
> active crews before proceeding. This cannot be undone.

```bash
podman-gs system reset --force
```

After a reset, rebuild the ghostship images and restart:

```bash
./install.sh
```
