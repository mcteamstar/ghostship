## Why

Tony intends to open source this repo. `install.sh` already branches on `uname -s`
for the genuinely different bits (podman machine VM vs. native socket, `Application
Support` vs. XDG data dir), but the whole Linux path has only ever been exercised by
code review on a Mac — nobody has actually run `./install.sh` on a Linux box during
development. For a project that will suddenly have Linux users who aren't Tony, that
gap matters more than it does today.

This is a stub only — capturing a direction Tony wants kept alive for a future
planning pass, not a worked-out design. No implementation should start from this
proposal as written.

## What Changes (sketch, not final)

- Actually run `./install.sh` end to end on a real Linux host (or a Linux VM/CI
  runner) at least once before claiming Linux support in the README — today's
  Linux branch is unverified, not just untested-in-CI.
- Audit assumptions baked into the Linux branch that may not hold across
  distros: `docs/architecture.md`'s reboot-recovery section already flags that
  a `systemctl --user` unit needs either a user-session restart or "relogin
  with lingering enabled" to survive a reboot — but it's a caveat, not a fix:
  `install.sh` never actually runs `loginctl enable-linger`, so a headless
  Linux box that never gets an interactive relogin (a server, a CI runner)
  could still lose transport after a real reboot with no automated recovery.
- Check `--security-opt label=disable` (added for the macOS guest's SELinux
  enforcing mode) doesn't mask a real, worth-fixing labeling issue on
  SELinux-enforcing Linux distros (Fedora/RHEL/CentOS) rather than just papering
  over it the same way it does for the disposable podman-machine guest.
- Check the podman-socket path assumption (`/run/user/$(id -u)/podman/podman.sock`)
  holds across distros/podman versions, and what happens when it doesn't (today:
  a confusing failure deep in `PodmanClient`, not a clear install-time error).
- Decide whether apt/dnf are enough package-manager coverage for a public Linux
  audience, or whether arch/alpine users hitting the "no supported package
  manager found" exit need a documented manual-install path instead of just a
  dead end.
- Open questions for the real design pass: is a Linux CI smoke-test (spin up
  podman, run install.sh, calldown a crew, nuke it) worth the CI complexity for
  a project this size, or is "someone will file an issue" an acceptable bar for
  v1 open source; does rootless podman have any distro-specific gotchas (cgroup
  v2, user namespaces) worth calling out in a troubleshooting doc.

## Capabilities

### Modified Capabilities
- `installation`: Linux install path needs real verification and a linger/reboot
  gap addressed — not yet specced, pending the real design pass.

## Impact

- `install.sh`, `docs/architecture.md` (reboot recovery section), a possible new
  `docs/troubleshooting.md`.
- Not yet scoped: whether CI coverage is in scope for v1, exact linger fix,
  whether non-apt/dnf distros get first-class support or just a documented
  workaround.
