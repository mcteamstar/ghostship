# Manual Install (Unsupported Package Managers)

`install.sh` requires `podman` and `podman-compose` to already be installed
before it runs — it does not install them itself. For `apt` (Debian/Ubuntu)
and `dnf` (Fedora/RHEL/CentOS), the standard install commands are in the
README. For other distros, install the prerequisites below manually, then
re-run `install.sh`.

## Prerequisites

| Package          | Minimum version | Purpose                         |
|------------------|-----------------|---------------------------------|
| `podman`         | 4.4+            | Container runtime (rootless)    |
| `podman-compose` | any             | Compose provider for `podman compose` |
| `crun` or `runc` | —               | OCI runtime backend             |
| `slirp4netns` or `pasta` | —      | Rootless network namespace      |

Optional but recommended:
- `podman-plugins` or `netavark` — DNS-enabled container networking
- `uidmap` / `shadow-utils` — for subuids if not already configured

## Example Install Commands

### Arch Linux

```bash
sudo pacman -S podman podman-compose crun slirp4netns
```

### Alpine Linux

```bash
sudo apk add podman podman-compose crun slirp4netns
# Enable cgroups v2 (required):
# Ensure /sys/fs/cgroup is mounted as cgroup2 (Alpine 3.15+ default)
```

### NixOS / Nix

```nix
# In configuration.nix:
virtualisation.podman.enable = true;
```

Or imperatively:

```bash
nix-env -iA nixpkgs.podman
```

### Gentoo

```bash
sudo emerge app-containers/podman app-containers/crun net-misc/slirp4netns
```

## Post-Install Verification

After installing, verify:

```bash
# podman is on PATH and version >= 4.0
podman --version

# Rootless mode works
podman info --format '{{.Host.Security.Rootless}}'
# Expected: true

# Socket activation is available
systemctl --user enable --now podman.socket
ls -l /run/user/$(id -u)/podman/podman.sock
```

Once Podman is verified, run:

```bash
./install.sh
```

## Troubleshooting

- **cgroup v2 required:** Podman rootless requires cgroup v2. Check with:
  `stat -fc %T /sys/fs/cgroup` — should print `cgroup2fs`. If you're on
  cgroup v1, consult your distro's documentation for migration.
- **Subuids not configured:** If `podman info` warns about subuids, ensure
  `/etc/subuid` and `/etc/subgid` have entries for your user.
- **Socket path differs:** If your podman socket is at a non-standard path,
  set `PODMAN_SOCK=/your/path` before running `install.sh`. This is a genuine
  exception to the no-ambient-environment-variable rule — `install.sh` reads
  `PODMAN_SOCK` directly from the environment before config-file sourcing to
  allow overriding the socket path without a config file. It is the only
  variable with this behaviour. For all other settings, use `--config <path>`
  or CLI flags (see [configuration.md](configuration.md)).

## Upgrading

### When to use `--skills`

Run `ghostship upgrade --skills` after pulling a new ghostship version that
ships updated academy skills (agents, steering files, or skill scripts in
`academy/`). The flag ensures that:

1. Container images are rebuilt from the new source.
2. The transport container is restarted with the updated images.
3. `ghostship setup` runs automatically to refresh the skill symlinks in
   `~/.kiro/skills/ghostship-admin` and the other registered harnesses.

Without `--skills`, `ghostship upgrade` only rebuilds and restarts the
container images — skill symlinks are not updated, so new or changed skill
files remain unreachable until `ghostship setup` is run separately.

**Rule of thumb:** if a release's changelog or `SKILL.md` mentions changes
to academy skills, use `--skills`.

### What `ghostship upgrade --skills` does

```
ghostship upgrade --skills
```

Internally this is equivalent to:

```bash
# 1. Rebuild images and restart transport
./install.sh

# 2. Re-run setup to refresh skill symlinks for each configured harness
ghostship setup
```

### Verify skill symlinks are current

After upgrading, confirm the symlinks point to the new files:

```bash
# Check the ghostship-admin skill symlink target
ls -la ~/.kiro/skills/ghostship-admin
# The symlink should point into the current ghostship source tree

# Or re-run setup explicitly to force a refresh
ghostship setup --agent kiro    # for the kiro harness
ghostship setup --agent claude  # for the claude harness
```

### Manual fallback steps

If `ghostship upgrade --skills` is unavailable (older version) or fails
partway through, run the steps manually:

```bash
# Step 1: rebuild images and restart
./install.sh

# Step 2: refresh skill symlinks
ghostship setup
```

Each step is idempotent — re-running either one is safe.
