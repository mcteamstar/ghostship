## 1. Container Image Pinning

- [x] 1.1 Pin `transport/Containerfile` FROM line to `python:3.12.10-slim` (verify current patch version at implementation time)
- [x] 1.2 Add floating-tag warning comment to `crews/spec-ops/Containerfile` above the `FROM ghcr.io/kirodotdev/kirocrew:stable` line

## 2. NodeSource Install Hardening

- [x] 2.1 Determine the SHA-256 of the current `https://deb.nodesource.com/setup_24.x` script
- [x] 2.2 Refactor NodeSource install in `crews/spec-ops/Containerfile` to download, verify checksum, then execute (per design decision 3)
- [x] 2.3 Rebuild crew image locally and verify Node.js installs correctly

## 3. install.sh Error Handling

- [x] 3.1 Add error guard with diagnostic message to `podman machine ssh -- systemctl --user enable podman-restart.service`
- [x] 3.2 Add error guard with diagnostic message to `GUEST_UID="$(podman machine ssh -- id -u)"` assignment
- [x] 3.3 Verify `set -eo pipefail` propagation by testing with a simulated ssh failure (optional: add a comment noting pipefail coverage)

## 4. install.sh Readiness Probe

- [x] 4.1 Check whether `server.py` exposes a `/health` endpoint; if not, add a minimal one (return 200 OK)
- [x] 4.2 Replace the `sleep 3 && podman ps` block with a bounded curl retry loop (30s timeout, 2s interval, per design decision 5)
- [x] 4.3 Add failure path: print last 20 lines of container logs and exit non-zero on timeout

## 5. install.sh Config Source Documentation

- [x] 5.1 Add trust-assumption comment block above the `source "$CONFIG_FILE"` line (per design decision 6)

## 6. Verification

- [x] 6.1 Run `podman build` for both Containerfiles and confirm successful builds
- [x] 6.2 Run `install.sh --config /dev/null` on a fresh podman machine to exercise the readiness probe path
