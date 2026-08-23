## 1. Linger Fix

- [x] 1.1 Add `loginctl enable-linger $(whoami)` to the Linux branch of `install.sh`, immediately after the `systemctl --user enable --now podman.socket` line
- [x] 1.2 Add install-time output line explaining what linger does (e.g. "✓ Linger enabled — transport survives logout/reboot")

## 2. Socket Path Validation

- [x] 2.1 After setting `PODMAN_SOCK` in the Linux branch, add a bounded retry loop (up to 5 s, 1 s intervals) that checks `test -S "$PODMAN_SOCK"`
- [x] 2.2 On timeout, emit a clear error message with the expected path, suggest checking `podman info` output, and mention the `PODMAN_SOCK` env-var override escape hatch
- [x] 2.3 Support an override: if `PODMAN_SOCK` is already set in the environment before `install.sh` runs, skip the default path assignment and use the user-supplied value

## 3. Unsupported Package Manager Fallback

- [x] 3.1 Replace the `exit 1` in the "no supported package manager" branch with a message listing minimum requirements (podman >= 4.0, crun or runc, slirp4netns or pasta) and pointing to `docs/manual-install.md`
- [x] 3.2 After the message, prompt (if interactive) or re-check `command -v podman` and continue if podman is now on PATH; exit only if it's truly absent
- [x] 3.3 Create `docs/manual-install.md` with: prerequisite list, example install commands for Arch/Alpine/Nix, post-install verification steps, and a pointer back to `install.sh` to continue setup

## 4. SELinux Documentation

- [x] 4.1 Expand the existing inline comment in `install.sh` (Linux branch, near `--security-opt label=disable`) into a clear explanation of the trade-off: what's disabled, why, blast-radius note (rootless + localhost-only), and pointer to troubleshooting doc
- [x] 4.2 Create a "SELinux and container labels" section in `docs/troubleshooting.md` (create the file if it doesn't exist) covering: why `label=disable` is used, what it means on non-SELinux hosts (no-op), and how to supply a custom policy if desired

## 5. Verification on Real Hosts

- [ ] 5.1 Run `install.sh` end-to-end on Ubuntu 22.04+ (or equivalent apt-based distro): confirm podman installs, socket appears, linger enables, transport container starts
- [ ] 5.2 Run `install.sh` end-to-end on Fedora 39+ (dnf, SELinux enforcing): confirm same plus `label=disable` does not produce denials in `ausearch`
- [ ] 5.3 Document any additional fixes discovered during verification as commits (fixes feed back into tasks 1–4 as needed)

> **Blocked:** Tasks 5.1–5.3 require running install.sh on real Ubuntu and Fedora hosts. This environment is a containerized agent sandbox without systemd, podman, or the ability to provision real VMs. Verification cannot be performed here and is deferred to a human operator with access to the target environments.

## 6. Architecture Doc Update

- [x] 6.1 Update the "Reboot recovery" section of `docs/architecture.md` to mention linger as a requirement and note that `install.sh` now enables it automatically
- [x] 6.2 Add a brief "Linux platform support" paragraph to the README or `docs/architecture.md` noting verified distros and linking to `docs/manual-install.md` for others
