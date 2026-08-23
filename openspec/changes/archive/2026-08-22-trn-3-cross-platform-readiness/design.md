## Context

See proposal.md – Why. The Linux path in `install.sh` has never been exercised
on a real Linux host; the project is about to go open source and needs to work
for Linux users on day one. Specs are skipped for this change — it is a
verification/hardening pass, not a feature addition.

Current state:
- `install.sh` already branches on `uname -s`; the Linux `else` branch enables
  `podman.socket` + `podman-restart.service`, assumes the rootless socket lives
  at `/run/user/$(id -u)/podman/podman.sock`, and uses XDG paths for data.
- Reboot recovery relies on `podman-restart.service` + lingering, but
  `loginctl enable-linger` is never run, meaning headless boxes silently lose
  the transport after reboot.
- `--security-opt label=disable` is applied unconditionally; on SELinux-enforcing
  hosts it papers over a labeling issue rather than solving it.
- Only `apt-get` and `dnf` are handled; other package managers hit a dead-end
  error.

## Goals / Non-Goals

**Goals:**
- Verify `install.sh` runs end-to-end on at least Debian/Ubuntu (apt) and
  Fedora/RHEL (dnf) — the two package-manager families already coded.
- Fix the linger gap: headless Linux installs survive reboot without manual
  intervention.
- Confirm the podman socket path is correct across supported distros/versions
  and fail clearly at install time if it is not.
- Document or gracefully handle SELinux-enforcing hosts (Fedora/RHEL) so the
  existing `label=disable` workaround is a conscious, explained choice rather
  than a silent papering-over.
- Provide a documented manual-install fallback for distros whose package
  managers are not covered (Arch, Alpine, etc.) instead of a bare error exit.

**Non-Goals:**
- Adding CI-based Linux smoke tests (deferred to a future change; acceptable
  for v1 open-source launch to rely on manual verification + issue reports).
- First-class Windows/WSL support.
- Replacing `--security-opt label=disable` with proper SELinux policy modules —
  that is a significant effort out of proportion to the user base; documenting
  the trade-off is sufficient for v1.
- Supporting Podman < 4.0 or cgroup v1-only hosts.

## Decisions

### 1. Enable linger automatically during install

**Choice:** Run `loginctl enable-linger $(whoami)` in the Linux branch of
`install.sh`, immediately after enabling `podman.socket`.

**Rationale:** Without linger, `systemctl --user` units (and therefore the
transport container) are torn down when the user's last login session ends.
Headless servers — the most likely Linux deployment — never have an interactive
session. Enabling linger is low-risk (it only keeps the user's systemd slice
alive) and matches what containers/rootless-podman docs recommend.

**Alternatives considered:**
- Document-only (tell users to run it themselves): too easy to miss, violates
  the "works out of the box" goal.
- Ship a system-level (root) systemd unit: over-engineered for a rootless
  setup, requires `sudo`, complicates uninstall.

### 2. Socket path validation at install time

**Choice:** After enabling `podman.socket`, test that the expected socket path
actually exists (`test -S "$PODMAN_SOCK"`) with a retry/wait loop (up to 5 s)
and emit a clear error with remediation steps if it doesn't appear.

**Rationale:** Podman 5+ or non-standard XDG_RUNTIME_DIR configurations can
move the socket. Failing loudly at install time is far better than a cryptic
`PodmanClient` error at runtime.

**Alternatives considered:**
- Query `podman info --format '{{.Host.RemoteSocket.Path}}'` to discover the
  real path: adds a dependency on podman already being functional (it may not
  be before socket activation fires). Could be a future improvement.

### 3. Documented manual-install path for unsupported package managers

**Choice:** Replace the hard `exit 1` in the "no supported package manager"
branch with a message that prints minimum requirements (podman >= 4.0,
crun/runc, slirp4netns/pasta) and a link to a `docs/manual-install.md` file,
then re-check `command -v podman` and continue if the user installed it
themselves.

**Rationale:** Arch, Alpine, NixOS, and Gentoo users are capable of installing
packages themselves; they just need to know *what* to install. A dead-end exit
is hostile.

**Alternatives considered:**
- Add pacman/apk/nix paths: unbounded distro support is unscalable; better to
  empower self-service.

### 4. SELinux: keep `label=disable`, add documentation

**Choice:** Keep the existing `--security-opt label=disable` but add a comment
block in `install.sh` and a section in `docs/troubleshooting.md` explaining
*why* it exists, what it trades off, and how a user on a hardened host could
supply a custom SELinux policy for the socket label instead.

**Rationale:** Writing a proper container SELinux policy is non-trivial and
distro-specific. For a rootless, localhost-only transport container, disabling
label enforcement is the pragmatic choice and matches upstream Podman guidance
for rootless socket mounts. Documenting it moves it from "hidden hack" to
"conscious trade-off."

### 5. Verification approach: manual matrix, not CI

**Choice:** Verify by running `install.sh` on two real environments:
- Ubuntu 22.04+ (apt path)
- Fedora 39+ (dnf path, SELinux enforcing)

Record results and any fixes applied. CI automation is out of scope (see
Non-Goals).

**Rationale:** The project is small enough that manual verification plus
community issue reports is proportionate for v1. CI can be added when the
contributor base grows.

## Risks / Trade-offs

- **`enable-linger` needs user buy-in on shared systems** → Mitigated by
  explaining what it does in install output and docs; on a shared box,
  admins can pre-enable it or users can opt out by removing the line.
- **Socket path check may false-negative on slow systems** → 5 s timeout with
  retries is generous; document the override escape hatch (`PODMAN_SOCK=...`
  env var).
- **Manual-install users hit edge cases we can't anticipate** → Acceptable for
  v1; the documented requirements set expectations and community issues close
  the gap.
- **`label=disable` is a security posture regression on enforcing hosts** →
  Trade-off is documented; rootless + localhost-only limits blast radius; proper
  policy can be contributed later.

## Open Questions

- Should `install.sh` also verify that cgroup v2 is the active hierarchy
  (Podman rootless with cgroup v1 has known issues)? Low effort to check, but
  unclear whether any target distros still default to v1. Can resolve during
  implementation if trivial.
