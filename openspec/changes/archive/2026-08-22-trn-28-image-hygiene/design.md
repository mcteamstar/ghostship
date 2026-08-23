## Context

See proposal.md for motivation. The transport Containerfile uses `python:3.12-slim` (floating minor), the crew Containerfile pulls `ghcr.io/kirodotdev/kirocrew:stable` (floating tag with no upstream versioned alternative yet) and installs Node.js via an unverified NodeSource curl-pipe-to-bash. `install.sh` has three reliability gaps: unguarded `podman machine ssh`, a `sleep 3` stand-in for a readiness probe, and an undocumented `source "$CONFIG_FILE"`.

## Goals / Non-Goals

**Goals:**
- Pin transport base image to a reproducible patch-version tag
- Document the crew base image floating-tag risk
- Add integrity verification to the NodeSource install
- Make `podman machine ssh` failures visible and fatal
- Replace the fixed sleep with a bounded retry readiness probe
- Document the config-source trust assumption

**Non-Goals:**
- Full digest pinning (requires CI automation to rotate; out of scope for this change)
- Switching away from NodeSource entirely (e.g. to `fnm` or distro packages)
- Adding automated image-update tooling (Renovate/Dependabot config)
- Changing install.sh's config-file interface or adding validation of config content

## Decisions

### 1. Tag pinning strategy: patch-version tag, not digest

**Choice:** Pin `python:3.12.10-slim` (current patch at time of implementation).

**Why not digest?** A digest pin (`python@sha256:...`) is maximally reproducible but requires a CI job or bot to rotate it when security patches land. This project has no such automation yet. A patch-version tag balances reproducibility (won't drift on minor bumps) with maintainability (gets security patches on rebuild without manual hash rotation).

**Alternative considered:** `python:3.12-slim` with a `# TODO: pin to digest` comment — rejected because it changes nothing and the comment will rot.

### 2. Crew Containerfile: comment-only for the base image

**Choice:** Add a `# WARNING: floating tag` comment explaining the risk and stating "pin to a versioned tag when upstream publishes one."

**Rationale:** `ghcr.io/kirodotdev/kirocrew:stable` has no versioned alternative today. A digest pin would lock to a specific build with no way to know when to rotate. The comment makes the risk visible for future action.

### 3. NodeSource hardening: pinned URL + checksum

**Choice:** Download the NodeSource setup script from a versioned GitHub release URL (tagged commit), verify its SHA-256 checksum against a value stored in the Containerfile, then execute.

**Pattern:**
```dockerfile
ARG NODESOURCE_SETUP_SHA256=<hash>
RUN curl -fsSL https://deb.nodesource.com/setup_24.x -o /tmp/nodesource_setup.sh && \
    echo "${NODESOURCE_SETUP_SHA256}  /tmp/nodesource_setup.sh" | sha256sum -c - && \
    bash /tmp/nodesource_setup.sh && \
    rm /tmp/nodesource_setup.sh
```

**Alternative considered:** Switch to the official Node.js binary tarball — rejected because it requires managing PATH and creates a non-standard layout that breaks npm global installs.

### 4. podman machine ssh error handling

**Choice:** Wrap each `podman machine ssh` call with `|| { echo "Error: <context>" >&2; exit 1; }`.

The script already uses `set -eo pipefail`, but `podman machine ssh` failures inside subshells (e.g. `GUEST_UID="$(podman machine ssh -- id -u)"`) do propagate under `set -e`. The explicit guard adds a diagnostic message that names what failed, rather than just a silent exit.

### 5. Readiness probe: bounded curl retry loop

**Choice:** Replace `sleep 3 && podman ps` with a bounded retry loop that curls the MCP health endpoint:

```bash
_max_wait=30
_interval=2
for (( _i=0; _i<_max_wait; _i+=_interval )); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "✓ Transport is ready"
    break
  fi
  sleep "$_interval"
done
if ! curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "✗ Transport did not become ready within ${_max_wait}s" >&2
  podman logs ga-transport --tail 20 >&2
  exit 1
fi
```

**Endpoint:** `/health` on the MCP port. If server.py doesn't expose `/health`, fall back to a TCP connect check (`curl -sf http://127.0.0.1:${PORT}/` or `podman exec ga-transport curl ...`). The probe must hit the actual service, not just check that the container process exists.

**Alternative considered:** `podman wait --condition=healthy` with a HEALTHCHECK instruction — rejected because it requires modifying the transport Containerfile's CMD/HEALTHCHECK and adds container-engine coupling.

### 6. Config source trust comment

**Choice:** Add a comment block directly above `source "$CONFIG_FILE"`:

```bash
# TRUST ASSUMPTION: this executes arbitrary shell code from the path the user
# passed via --config. The caller is trusted — this is intentional: config
# files export env vars that control identity provider, region, API keys, etc.
# Do NOT source untrusted paths.
```

## Risks / Trade-offs

- **[Checksum rotation]** → The NodeSource SHA-256 must be updated when bumping Node.js versions. Mitigated by making the hash a build ARG that's easy to grep for.
- **[Readiness probe endpoint]** → If `/health` doesn't exist in server.py, the probe needs a fallback (TCP connect or root `/`). Implementer should verify the endpoint exists or add a minimal one.
- **[Patch-version drift]** → `python:3.12.10-slim` still floats at the build-layer level (Docker Hub can republish the same tag). Acceptable: the window is tiny and digest pinning is explicitly deferred.
