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

## Continue Setup

Once podman is installed and verified, re-run:

```bash
./install.sh
```

The script will detect podman on PATH, skip the package-manager step, and
proceed with socket setup, image builds, and transport container launch.

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
